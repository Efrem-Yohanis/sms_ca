import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from . import app as receiver_app
from .app import DLRReceiver


class FakeProducer:
    def __init__(self, failures=0):
        self.failures = failures
        self.started = False
        self.events = []

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    async def send_and_wait(self, topic, value, key=None):
        if self.failures:
            self.failures -= 1
            raise RuntimeError('Kafka unavailable')
        self.events.append((topic, value, key))


class DLRReceiverApiTests(unittest.TestCase):
    def test_callback_queues_and_publishes_keyed_event(self):
        producer = FakeProducer()
        receiver = DLRReceiver(producer_factory=lambda: producer)
        with patch.object(receiver_app, 'receiver', receiver), TestClient(receiver_app.app) as client:
            for _ in range(100):
                health = client.get('/health')
                if health.status_code == 200:
                    break
                time.sleep(0.01)

            payload = {
                'event': 'Delivery receipt received',
                'msisdn': '251799120001',
                'messageId': '11779274578648910',
                'status': 'DELIVRD',
                'doneDate': '260928080404',
            }
            response = client.post('/api/v1/delivery-reports/callback/', json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['success'], True)
            self.assertEqual(response.json()['accepted'], True)
            self.assertRegex(response.json()['received_at'], r'Z$')
            time.sleep(0.08)

        self.assertEqual(len(producer.events), 1)
        topic, event, key = producer.events[0]
        self.assertEqual(topic, 'delivery-report')
        self.assertEqual(key, payload['messageId'])
        self.assertEqual(event['event_type'], 'DELIVERY_REPORT')
        self.assertEqual(event['provider_message_id'], payload['messageId'])
        self.assertEqual(event['raw_payload'], payload)
        self.assertIn('received_at', event)

    def test_missing_fields_and_malformed_json_return_400(self):
        receiver = DLRReceiver(producer_factory=FakeProducer)
        with patch.object(receiver_app, 'receiver', receiver), TestClient(receiver_app.app) as client:
            malformed = client.post(
                '/api/v1/delivery-reports/callback/',
                content='{',
                headers={'Content-Type': 'application/json'},
            )
            missing = client.post(
                '/api/v1/delivery-reports/callback/',
                json={'msisdn': '251799120001', 'status': 'DELIVRD'},
            )

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()['message'], 'Invalid JSON')
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()['message'], 'Missing messageId')

    def test_unconnected_and_full_queue_return_503(self):
        receiver = DLRReceiver(producer_factory=FakeProducer)
        client = TestClient(receiver_app.app)
        with patch.object(receiver_app, 'receiver', receiver):
            payload = {
                'messageId': '11779274578648910',
                'msisdn': '251799120001',
                'status': 'DELIVRD',
            }
            unconnected = client.post('/api/v1/delivery-reports/callback/', json=payload)
            receiver.kafka_connected = True
            receiver.queue = asyncio.Queue(maxsize=1)
            receiver.queue.put_nowait({'queued': True})
            full = client.post('/api/v1/delivery-reports/callback/', json=payload)
        client.close()

        self.assertEqual(unconnected.status_code, 503)
        self.assertEqual(full.status_code, 503)
        self.assertEqual(full.json()['message'], 'Queue full. Retry shortly.')


class KafkaRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_retries_and_publish_retries_then_acks(self):
        producers = [FakeProducer(), FakeProducer()]
        producers[0].start = AsyncMock(side_effect=RuntimeError('broker unavailable'))
        producers[1].failures = 1
        factory = unittest.mock.Mock(side_effect=producers)
        receiver = DLRReceiver(producer_factory=factory)
        with (
            patch('dlr_receiver.app.DLR_KAFKA_STARTUP_TIMEOUT', 10),
            patch('dlr_receiver.app.asyncio.sleep', new=AsyncMock()),
            patch('dlr_receiver.app.DLR_RETRY_BACKOFF', 0),
        ):
            await receiver.start()
            await receiver.connection_task
            self.assertTrue(receiver.kafka_connected)
            event = {
                'provider_message_id': '11779274578648910',
                'status': 'DELIVRD',
            }
            await receiver._publish_with_retry([event])
            await receiver.stop()

        self.assertEqual(factory.call_count, 2)
        self.assertEqual(receiver.published_total, 1)
        self.assertEqual(receiver.failed_total, 0)
        self.assertEqual(producers[1].events[0][2], event['provider_message_id'])


if __name__ == '__main__':
    unittest.main()
