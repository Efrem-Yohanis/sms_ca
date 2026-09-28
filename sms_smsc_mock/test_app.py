import asyncio
import unittest
from unittest.mock import patch

from .app import SmsStore


class FakeProducer:
    def __init__(self):
        self.events = []

    async def send_and_wait(self, topic, value, key=None):
        self.events.append((topic, value, key))


class KafkaEventPublishTests(unittest.IsolatedAsyncioTestCase):
    async def test_accept_and_delivery_publish_keyed_events(self):
        store = SmsStore(':memory:')
        producer = FakeProducer()
        store.kafka_producer = producer
        row = {
            'message_id': 'msg-test-1',
            'provider_message_id': 'smsc-test-1',
            'campaign_id': 4,
            'sender_id': 'SMSINFO',
            'recipient': '+251911000001',
            'message_content': 'Hello',
            'segment_count': 1,
            'callback_url': None,
            'received_at': '2026-09-28T08:04:01+00:00',
        }

        with (
            patch('sms_smsc_mock.app.MIN_DELIVERY_DELAY_SECONDS', 0),
            patch('sms_smsc_mock.app.MAX_DELIVERY_DELAY_SECONDS', 0),
            patch('sms_smsc_mock.app.pick_final_status', return_value='DELIVRD'),
        ):
            await store.accept(row)
            await asyncio.gather(*list(store._delivery_tasks))

        self.assertEqual(len(producer.events), 2)
        send_topic, send_event, send_key = producer.events[0]
        delivery_topic, delivery_event, delivery_key = producer.events[1]
        self.assertEqual(send_topic, 'smsc-send-response')
        self.assertEqual(send_event['event_type'], 'SEND_RESPONSE')
        self.assertEqual(send_event['status'], 'ACCEPTED')
        self.assertEqual(send_key, row['message_id'])
        self.assertEqual(delivery_topic, 'smsc-delivery-report')
        self.assertEqual(delivery_event['event_type'], 'DELIVERY_REPORT')
        self.assertEqual(delivery_event['status'], 'DELIVRD')
        self.assertEqual(delivery_key, row['message_id'])
        self.assertEqual(store.queue.qsize(), 2)
