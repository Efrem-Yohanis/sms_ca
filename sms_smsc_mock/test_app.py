import asyncio
import base64
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from . import app as mock_app
from .app import SmsStore


def basic_auth(username: str, password: str) -> str:
    token = base64.b64encode(f'{username}:{password}'.encode()).decode()
    return f'Basic {token}'


class FakeHttpResponse:
    status_code = 200


class FakeHttpClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, json):
        self.posts.append((url, json))
        return FakeHttpResponse()

    async def aclose(self):
        pass


class OnionSMSCContractTests(unittest.TestCase):
    def test_batch_submit_authentication_and_debug_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SmsStore(str(Path(directory) / 'mock.sqlite3'))
            payload = {
                'shortMessage': 'Hello Alice',
                'messageType': 'TEXT',
                'destAddr': [{'id': '251799120001'}, {'id': '251799120002'}],
                'sourceAddr': {'name': 'SMSINFO'},
                'servicetag': {'name': 'camp-5'},
                'servicetype': {'name': 'normal'},
            }
            with (
                patch.object(mock_app, 'store', store),
                patch.object(mock_app, 'MOCK_USERNAME', 'test-user'),
                patch.object(mock_app, 'MOCK_PASSWORD', 'test-pass'),
                patch.object(mock_app, 'DLR_CALLBACK_URL', ''),
                TestClient(mock_app.app) as client,
            ):
                unauthorized = client.post('/onion/swift/duos', json=payload)
                self.assertEqual(unauthorized.status_code, 401)

                headers = {'Authorization': basic_auth('test-user', 'test-pass')}
                response = client.post('/onion/swift/duos', json=payload, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                results = response.json()
                self.assertEqual([result['msisdn'] for result in results], ['251799120001', '251799120002'])
                self.assertTrue(all(result['status'] == 'submitted' for result in results))
                self.assertTrue(all(re.fullmatch(r'\d{19}', result['messageId']) for result in results))

                time.sleep(0.03)
                lookup = client.get(f"/api/messages/{results[0]['messageId']}")
                self.assertEqual(lookup.status_code, 200, lookup.text)
                self.assertEqual(lookup.json()['shortMessage'], 'Hello Alice')
                self.assertEqual(lookup.json()['sourceAddr'], 'SMSINFO')
                self.assertEqual(lookup.json()['status'], 'submitted')

                health = client.get('/health').json()
                self.assertIn('accepted_total', health)
                self.assertIn('dlr_callback_url', health)

            connection = sqlite3.connect(store.path)
            try:
                columns = [row[1] for row in connection.execute('PRAGMA table_info(messages)')]
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='messages'").fetchone()[0], 1)
                self.assertIn('done_date', columns)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 2)
            finally:
                connection.close()

    def test_wrong_credentials_malformed_json_and_invalid_destinations(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SmsStore(str(Path(directory) / 'mock.sqlite3'))
            with (
                patch.object(mock_app, 'store', store),
                patch.object(mock_app, 'MOCK_USERNAME', 'test-user'),
                patch.object(mock_app, 'MOCK_PASSWORD', 'test-pass'),
                TestClient(mock_app.app) as client,
            ):
                wrong = client.post(
                    '/onion/swift/duos',
                    json={},
                    headers={'Authorization': basic_auth('test-user', 'wrong')},
                )
                self.assertEqual(wrong.status_code, 401)

                headers = {'Authorization': basic_auth('test-user', 'test-pass')}
                malformed = client.post(
                    '/onion/swift/duos',
                    content='{',
                    headers={**headers, 'Content-Type': 'application/json'},
                )
                self.assertEqual(malformed.status_code, 400)
                self.assertEqual(malformed.json()['message'], 'Invalid JSON')

                invalid = client.post(
                    '/onion/swift/duos',
                    json={
                        'shortMessage': 'Hi',
                        'destAddr': [{'id': '+251799120001'}],
                        'sourceAddr': {'name': 'SMSINFO'},
                    },
                    headers=headers,
                )
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(invalid.json()['error'], 'Bad request')

    def test_rate_limit_returns_503_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SmsStore(str(Path(directory) / 'mock.sqlite3'))
            with (
                patch.object(mock_app, 'store', store),
                patch.object(mock_app, 'MOCK_USERNAME', ''),
                patch.object(mock_app, 'MOCK_PASSWORD', ''),
                patch.object(store.tps_bucket, 'try_acquire', new=AsyncMock(return_value=False)),
                TestClient(mock_app.app) as client,
            ):
                response = client.post(
                    '/onion/swift/duos',
                    json={
                        'shortMessage': 'Hello',
                        'destAddr': [{'id': '251799120001'}],
                        'sourceAddr': {'name': 'SMSINFO'},
                    },
                    headers={'Authorization': basic_auth('any', 'credentials')},
                )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {
                    'error': 'Service Unavailable',
                    'message': 'Rate limit exceeded. Retry shortly.',
                })


class DeliveryReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_dlr_uses_onion_body_and_updates_sqlite_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SmsStore(str(Path(directory) / 'mock.sqlite3'))
            fake_client = FakeHttpClient()
            with (
                patch('sms_smsc_mock.app.MIN_DELAY_SECONDS', 0),
                patch('sms_smsc_mock.app.MAX_DELAY_SECONDS', 0),
                patch('sms_smsc_mock.app.DLR_CALLBACK_URL', 'http://dlr_app:8003/callback'),
                patch('sms_smsc_mock.app.pick_final_status', return_value='DELIVRD'),
                patch('sms_smsc_mock.app.httpx.AsyncClient', return_value=fake_client),
            ):
                await store.start()
                row = {
                    'message_id': '11779274578648910',
                    'msisdn': '251799120001',
                    'short_message': 'Hello',
                    'source_addr': 'SMSINFO',
                    'servicetag': 'camp-5',
                    'servicetype': 'normal',
                    'status': 'submitted',
                    'received_at': '2026-09-28T08:04:01.234Z',
                    'callback_url': 'http://dlr_app:8003/callback',
                }
                await store.accept(row)
                await asyncio.gather(*list(store._delivery_tasks))
                await store.queue.join()
                stored = store.get_message(row['message_id'])
                await store.stop()

        self.assertEqual(fake_client.posts[0][0], 'http://dlr_app:8003/callback')
        dlr = fake_client.posts[0][1]
        self.assertEqual(set(dlr), {'event', 'msisdn', 'messageId', 'status', 'doneDate'})
        self.assertEqual(dlr['event'], 'Delivery receipt received')
        self.assertEqual(dlr['status'], 'DELIVRD')
        self.assertRegex(dlr['doneDate'], r'^\d{12}$')
        self.assertEqual(stored['status'], 'DELIVRD')
        self.assertEqual(stored['dlr_sent'], 1)
        self.assertEqual(stored['dlr_attempts'], 1)
