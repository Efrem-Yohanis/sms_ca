import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from django.test import TestCase

from sms_campaign_manager.models import (
    Campaign,
    Channel,
    FailedDelivery,
    FailedSent,
    MessageObject,
    SenderID,
    SuccessDelivery,
    SuccessSent,
)
from sms_status_updater import app as updater_module
from sms_status_updater.app import (
    EventConsumer,
    _deserialize_event,
    process_delivery_batch,
    process_sent_batch,
)


class StatusUpdaterBatchTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(code='sms', name='SMS')
        self.sender = SenderID.objects.create(sender_id='SMSINFO', name='SMS Info')
        self.campaign = Campaign.objects.create(
            name='Status updater test campaign',
            sender_id=self.sender.sender_id,
            channels_id=[self.channel.id],
        )

    def send_event(self, message_id='event-message-1', *, accepted=True, provider_id='provider-1'):
        timestamp = '2026-09-29T10:05:00Z'
        return {
            'event_type': 'SENT_RESPONSE',
            'accepted': accepted,
            'message_id': message_id,
            'provider_message_id': provider_id,
            'campaign_id': self.campaign.id,
            'channel_id': self.channel.id,
            'round_number': 3,
            'recipient': '251799120001',
            'sender_id': 'SMSINFO',
            'message_content': 'Hello from the sender event',
            'servicetype': 'normal',
            'servicetag': f'camp-{self.campaign.id}',
            'batch_id': 'campaign-1-round-3',
            'worker_id': 'worker-test',
            'request_payload': {'shortMessage': 'Hello from the sender event'},
            'provider_status': 'submitted' if accepted else 'failed',
            'provider_response': {'status': 'submitted' if accepted else 'failed'},
            'total_attempts': 1,
            'last_error': '' if accepted else 'SMSC rejected',
            'error_type': '' if accepted else 'SMSC',
            'error_code': '' if accepted else 'SMSC_REJECTED',
            'http_status_code': 200,
            'built_at': timestamp,
            'sending_started_at': timestamp,
            'sent_at': timestamp if accepted else None,
            'first_attempt_at': timestamp if not accepted else None,
            'final_attempt_at': timestamp if not accepted else None,
            'received_at': timestamp,
        }

    def test_send_history_uses_event_without_messageobject_and_is_idempotent(self):
        event = self.send_event()

        self.assertEqual(process_sent_batch([event]), 1)
        row = SuccessSent.objects.get(message_id=event['message_id'])
        self.assertEqual(row.campaign_id, self.campaign.id)
        self.assertEqual(row.channel_id, self.channel.id)
        self.assertEqual(row.round_number, 3)
        self.assertEqual(row.recipient, '251799120001')
        self.assertEqual(row.message_content, 'Hello from the sender event')
        self.assertFalse(MessageObject.objects.filter(message_id=event['message_id']).exists())
        self.assertEqual(process_sent_batch([event]), 0)
        self.assertEqual(SuccessSent.objects.filter(message_id=event['message_id']).count(), 1)

    def test_send_history_insert_precedes_queue_delete_in_same_batch(self):
        event = self.send_event(message_id='queued-message')
        queue_row = MessageObject.objects.create(
            message_id=event['message_id'],
            campaign=self.campaign,
            channel=self.channel,
            recipient=event['recipient'],
            sender_id=event['sender_id'],
            message_content='queue copy',
            round_number=event['round_number'],
            batch_id=event['batch_id'],
        )

        process_sent_batch([event])

        self.assertFalse(MessageObject.objects.filter(pk=queue_row.pk).exists())
        self.assertTrue(SuccessSent.objects.filter(message_id=event['message_id']).exists())

    def test_permanent_failure_is_written_even_without_provider_id(self):
        event = self.send_event(message_id='failed-message', accepted=False, provider_id='')

        self.assertEqual(process_sent_batch([event]), 1)
        failed = FailedSent.objects.get(message_id='failed-message')
        self.assertEqual(failed.provider_message_id, '')
        self.assertEqual(failed.error_code, 'SMSC_REJECTED')
        self.assertEqual(failed.last_error, 'SMSC rejected')

    def test_malformed_send_event_does_not_block_valid_event(self):
        valid = self.send_event(message_id='valid-message')
        malformed = {'event_type': 'SENT_RESPONSE', 'accepted': True}

        self.assertEqual(process_sent_batch([malformed, valid]), 1)
        self.assertTrue(SuccessSent.objects.filter(message_id='valid-message').exists())
        self.assertEqual(SuccessSent.objects.count(), 1)

    def test_orphan_delivery_is_logged_counted_and_not_retried(self):
        updater_module.ORPHAN_DLR_COUNT = 0
        event = {
            'event_type': 'DELIVERY_REPORT',
            'provider_message_id': 'unknown-provider-id',
            'msisdn': '251799120001',
            'status': 'DELIVRD',
            'doneDate': '260929100500',
            'raw_payload': {'messageId': 'unknown-provider-id'},
        }

        self.assertEqual(process_delivery_batch([event]), 0)
        self.assertEqual(updater_module.ORPHAN_DLR_COUNT, 1)
        self.assertEqual(SuccessDelivery.objects.count(), 0)
        self.assertEqual(FailedDelivery.objects.count(), 0)

    def test_delivery_maps_fixed_codes_and_parses_done_date(self):
        send = self.send_event(message_id='sent-for-dlr', provider_id='provider-dlr')
        process_sent_batch([send])
        event = {
            'event_type': 'DELIVERY_REPORT',
            'provider_message_id': 'provider-dlr',
            'msisdn': '251799120009',
            'status': 'DELIVRD',
            'doneDate': '260929100500',
            'event': 'DELIVERY RECEIPT',
            'raw_payload': {'messageId': 'provider-dlr', 'status': 'DELIVRD'},
        }

        self.assertEqual(process_delivery_batch([event]), 1)
        delivery = SuccessDelivery.objects.get(message_id='sent-for-dlr')
        self.assertEqual(delivery.delivery_status, 'DELIVERED')
        self.assertEqual(delivery.delivery_code, '000')
        self.assertEqual(delivery.delivery_description, 'Delivered')
        self.assertEqual(delivery.recipient, '251799120009')
        self.assertEqual(delivery.delivered_at, datetime(2026, 9, 29, 10, 5, tzinfo=timezone.utc))
        self.assertEqual(process_delivery_batch([event]), 0)
        self.assertEqual(SuccessDelivery.objects.count(), 1)

    def test_non_success_dlr_statuses_use_required_mapping(self):
        mapping = {
            'UNDELIV': ('UNDELIVERABLE', '008', 'Undeliverable'),
            'EXPIRED': ('EXPIRED', '001', 'Validity period expired'),
            'REJECTD': ('REJECTED', '002', 'Rejected'),
            'OTHER': ('UNKNOWN', '999', 'Unknown'),
        }
        for index, (status, expected) in enumerate(mapping.items()):
            provider_id = f'failed-provider-{index}'
            FailedSent.objects.create(
                message_id=f'failed-history-{index}',
                provider_message_id=provider_id,
                campaign=self.campaign,
                channel=self.channel,
                recipient='251799120001',
                sender_id='SMSINFO',
            )
            process_delivery_batch([{
                'event_type': 'DELIVERY_REPORT',
                'provider_message_id': provider_id,
                'msisdn': '251799120001',
                'status': status,
                'doneDate': 'invalid-date',
            }])
            row = FailedDelivery.objects.get(provider_message_id=provider_id)
            self.assertEqual((row.delivery_status, row.delivery_code, row.delivery_description), expected)
            self.assertIsNone(row.failed_at)


class EventConsumerOffsetTests(unittest.IsolatedAsyncioTestCase):
    def test_invalid_json_decodes_to_a_committable_skip_record(self):
        decoded = _deserialize_event(b'{invalid json')
        self.assertEqual(decoded, {'_malformed_kafka_message': '{invalid json'})

    async def test_offsets_commit_only_after_handler_succeeds(self):
        partition = object()
        records = [SimpleNamespace(value={'event': 1}, offset=4), SimpleNamespace(value={'event': 2}, offset=5)]

        class FakeConsumer:
            def __init__(self):
                self.calls = 0
                self.commits = []
                self.seeks = []
                self.committed = asyncio.Event()

            async def getmany(self, **kwargs):
                self.calls += 1
                if self.calls <= 2:
                    return {partition: records}
                await asyncio.sleep(60)
                return {}

            async def commit(self, offsets):
                self.commits.append(offsets)
                self.committed.set()

            def seek(self, current_partition, offset):
                self.seeks.append((current_partition, offset))

            async def stop(self):
                pass

        handler_calls = 0

        def handler(events):
            nonlocal handler_calls
            handler_calls += 1
            if handler_calls == 1:
                raise RuntimeError('database unavailable')
            return len(events)

        fake = FakeConsumer()
        consumer = EventConsumer('topic', 'group', handler)
        consumer.consumer = fake
        with patch('sms_status_updater.app.RETRY_DELAY_SECONDS', 0.01):
            consumer.task = asyncio.create_task(consumer._run())
            await asyncio.wait_for(fake.committed.wait(), timeout=3)
            await consumer.stop()

        self.assertEqual(handler_calls, 2)
        self.assertEqual(fake.seeks, [(partition, 4)])
        self.assertEqual(len(fake.commits), 1)
        self.assertEqual(fake.commits[0][partition].offset, 6)
        self.assertEqual(consumer.total_consumed, 2)
        self.assertEqual(consumer.total_batches, 1)
