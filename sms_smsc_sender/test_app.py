import base64
import unittest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from . import app as sender_app
from .app import Sender, allocate_tps, build_chunks


class MockResponse:
    def __init__(self, status_code=200, body=None, text=''):
        self.status_code = status_code
        self.body = body
        self.text = text

    def json(self):
        return self.body


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class FakeSender:
    def __init__(self):
        self.active_campaigns = {}
        self.worker_task = None
        self.last_report = {'success': True}
        self.started_campaigns = []
        self.start_actions = []
        self.stopped_campaigns = []

    async def start(self):
        pass

    async def stop(self):
        pass

    async def activate_campaign(self, campaign_id):
        self.started_campaigns.append(campaign_id)
        return {'success': True, 'campaign_id': campaign_id}

    async def start_campaign(self, campaign_id):
        self.start_actions.append(campaign_id)
        return {'success': True, 'campaign_id': campaign_id, 'status': 'in_progress'}

    async def pause_campaign(self, campaign_id):
        self.stopped_campaigns.append(campaign_id)
        return {'success': True, 'campaign_id': campaign_id}

    def ensure_worker(self):
        self.worker_task = object()

    async def fetch_active_config(self, endpoint, key):
        return {'id': 1, key: 4000 if key == 'global_tps' else 1000}

    async def load_smsc_config(self):
        return {'id': 2, 'rate_limit_per_second': 4000, 'base_url': 'http://smsc', 'send_endpoint': '/onion/swift/duos'}

    async def pending_count(self, campaign_id, *, round_number=None, status_filter=('PENDING', 'FAILED')):
        return 42 if status_filter != ('SENT',) else 10

    async def status_for_campaign(self, campaign_id):
        return {'success': True, 'data': {'campaign_id': campaign_id, 'active': False, 'pending_count': 42, 'allocation': None}}

    async def status_all(self):
        return {
            'success': True,
            'data': {
                'active_campaigns': [
                    {
                        'campaign_id': campaign_id,
                        'round_number': details['round_number'],
                        'pending_count': 42,
                        'allocated_tps': 4000,
                    }
                    for campaign_id, details in sorted(self.active_campaigns.items())
                ],
            },
        }

    async def load_tick_config(self):
        return (
            {'id': 1, 'global_tps': 4000},
            {'id': 3, 'max_addresses_per_request': 1000},
            {'id': 2, 'rate_limit_per_second': 4000, 'base_url': 'http://smsc', 'send_endpoint': '/onion/swift/duos'},
            {},
        )

    async def run_once(self):
        return {'success': True, 'reports': []}


class SenderAllocationTests(unittest.TestCase):
    def test_tps_is_distributed_by_sorted_campaign_id_and_capped(self):
        self.assertEqual(allocate_tps(4000, [6, 5, 7], 4000), {5: 1334, 6: 1333, 7: 1333})
        self.assertEqual(allocate_tps(4000, [6, 5], 1000), {5: 1000, 6: 1000})
        self.assertEqual(allocate_tps(4000, [], 1000), {})

    def test_messages_group_by_language_and_content_then_chunk(self):
        messages = [
            {'id': 1, 'language_id': 1, 'message_content': 'Hello'},
            {'id': 2, 'language_id': 1, 'message_content': 'Hello'},
            {'id': 3, 'language_id': 2, 'message_content': 'Hello'},
        ]
        chunks = build_chunks(messages, 1)
        self.assertEqual([len(chunk['messages']) for chunk in chunks], [1, 1, 1])
        self.assertEqual([chunk['language_id'] for chunk in chunks], [1, 1, 2])


class SenderSMSCRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_posts_onion_body_and_matches_results_by_position(self):
        sender = Sender()
        sender.http = FakeHttpClient([MockResponse(body=[
            {'messageId': '10000000000000001', 'msisdn': '251799120001', 'status': 'submitted'},
            {'messageId': '10000000000000002', 'msisdn': '251799120002', 'status': 'failed'},
        ])])
        messages = [
            {
                'id': 1, 'message_id': 'msg-a', 'campaign_id': 5, 'channel_id': 1,
                'language_id': 1, 'round_number': 1, 'recipient': '+251799120001',
                'sender_id': 'SMSINFO', 'message_content': 'Hello', 'send_attempts': 0,
                'batch_id': 'batch_5_deadbeef', 'worker_id': 'worker_1_abc123',
                'built_at': None, 'sending_started_at': None,
            },
            {
                'id': 2, 'message_id': 'msg-b', 'campaign_id': 5, 'channel_id': 1,
                'language_id': 1, 'round_number': 1, 'recipient': '251799120002',
                'sender_id': 'SMSINFO', 'message_content': 'Hello', 'send_attempts': 0,
                'batch_id': 'batch_5_deadbeef', 'worker_id': 'worker_1_abc123',
                'built_at': None, 'sending_started_at': None,
            },
        ]
        chunk = {'language_id': 1, 'message_content': 'Hello', 'messages': messages}
        config = {
            'base_url': 'http://mock-smsc:8090',
            'send_endpoint': '/onion/swift/duos',
            'http_method': 'POST',
            'request_timeout_seconds': 30,
            'connect_timeout_seconds': 10,
            'auth_type': 'basic',
            'username': 'test-user',
            'password': 'test-pass',
            'extra_headers': {'X-Trace': 'test'},
        }

        outcomes = await sender.send_chunk(config, chunk, {1: 'sms'})

        self.assertTrue(outcomes[0]['accepted'])
        self.assertFalse(outcomes[1]['accepted'])
        self.assertEqual(outcomes[1]['error_type'], 'SMSC')
        url, request = sender.http.calls[0]
        self.assertEqual(url, 'http://mock-smsc:8090/onion/swift/duos')
        self.assertEqual(request['json']['destAddr'], [{'id': '251799120001'}, {'id': '251799120002'}])
        self.assertEqual(request['json']['servicetype'], {'name': 'normal'})
        token = base64.b64encode(b'test-user:test-pass').decode()
        self.assertEqual(request['headers']['Authorization'], f'Basic {token}')
        self.assertEqual(request['headers']['X-Trace'], 'test')

    async def test_empty_status_does_not_require_sender_configuration(self):
        result = await Sender().status_all()
        self.assertEqual(result, {'success': True, 'data': {'active_campaigns': []}})


class SenderEndpointTests(unittest.TestCase):
    def test_start_conflict_stop_and_status_endpoints(self):
        fake = FakeSender()
        with unittest.mock.patch.object(sender_app, 'sender', fake), TestClient(sender_app.app) as client:
            started = client.post('/sender/start', json={'campaign_id': 5, 'round_number': 2})
            duplicate = client.post('/sender/start', json={'campaign_id': 5})
            status_response = client.get('/sender/status')
            individual_status = client.get('/sender/status/5')
            stopped = client.post('/sender/stop', json={'campaign_id': 5, 'round_number': 2})
            missing = client.post('/sender/stop', json={'campaign_id': 5})

        self.assertEqual(started.status_code, 202)
        self.assertEqual(fake.start_actions, [5])
        self.assertEqual(started.json()['data'], {
            'campaign_id': 5,
            'round_number': 2,
            'status': 'active',
            'execution_status': 'PROCESSING',
            'allocated_tps': 4000,
            'total_global_tps': 4000,
            'active_campaigns': 1,
        })
        self.assertIn('campaign_response', started.json())
        self.assertIn('activation_response', started.json())
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()['data']['active_campaigns'], [{
            'campaign_id': 5,
            'round_number': 2,
            'pending_count': 42,
            'allocated_tps': 4000,
        }])
        self.assertEqual(individual_status.status_code, 200)
        self.assertEqual(stopped.status_code, 200)
        self.assertEqual(stopped.json()['data']['round_number'], 2)
        self.assertEqual(stopped.json()['data']['execution_status'], 'PAUSED')
        self.assertEqual(missing.status_code, 404)

    def test_invalid_campaign_request_returns_400(self):
        fake = FakeSender()
        with unittest.mock.patch.object(sender_app, 'sender', fake), TestClient(sender_app.app) as client:
            response = client.post('/sender/start', json={'campaign_id': 0})
            invalid_round = client.post('/sender/start', json={'campaign_id': 5, 'round_number': 0})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.assertEqual(invalid_round.status_code, 400)
        self.assertFalse(invalid_round.json()['success'])


if __name__ == '__main__':
    unittest.main()
