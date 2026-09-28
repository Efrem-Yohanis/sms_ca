"""FastAPI Kafka consumers that persist mock-SMSC events into campaign history."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from asgiref.sync import sync_to_async
from django.db import connection, transaction
from django.utils.dateparse import parse_datetime
from fastapi import FastAPI

PROJECT_PATH = Path(__file__).resolve().parents[1] / 'sms_campign'
if str(PROJECT_PATH) not in sys.path:
    sys.path.insert(0, str(PROJECT_PATH))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_campign.settings')

import django

django.setup()

from sms_campaign_manager.models import (  # noqa: E402
    Campaign,
    FailedDelivery,
    FailedSent,
    MessageObject,
    SuccessDelivery,
    SuccessSent,
)

logger = logging.getLogger('sms_status_updater')

KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
SEND_TOPIC = os.getenv('KAFKA_SEND_RESPONSE_TOPIC', 'smsc-send-response')
DELIVERY_TOPIC = os.getenv('KAFKA_DELIVERY_TOPIC', 'smsc-delivery-report')
SEND_GROUP = os.getenv('KAFKA_SEND_GROUP', 'status-updater-send')
DELIVERY_GROUP = os.getenv('KAFKA_DELIVERY_GROUP', 'status-updater-delivery')
BATCH_SIZE = int(os.getenv('KAFKA_BATCH_SIZE', '1000'))
POLL_INTERVAL_MS = int(os.getenv('KAFKA_POLL_INTERVAL_MS', '1000'))


class RetryBatch(Exception):
    """Leave a batch uncommitted when a prerequisite or database write fails."""


def _timestamp(value):
    if not value:
        return None
    parsed = parse_datetime(str(value).replace('Z', '+00:00'))
    if parsed is None:
        raise ValueError(f'Invalid event timestamp: {value}')
    return parsed


def process_send_batch(events: list[dict[str, Any]]) -> int:
    events = [event for event in events if event.get('event_type') == 'SEND_RESPONSE']
    unique_events = {event.get('message_id'): event for event in events if event.get('message_id')}
    if not unique_events:
        return 0

    message_ids = set(unique_events)
    with transaction.atomic():
        messages = {
            item.message_id: item
            for item in MessageObject.objects.select_related('campaign', 'channel').filter(
                message_id__in=message_ids,
            )
        }
        existing_ids = set(SuccessSent.objects.filter(message_id__in=message_ids).values_list('message_id', flat=True))
        existing_ids.update(FailedSent.objects.filter(message_id__in=message_ids).values_list('message_id', flat=True))
        missing = message_ids - messages.keys() - existing_ids
        if missing:
            raise RetryBatch(f'{len(missing)} send events have no matching MessageObject')

        success_rows = []
        failed_rows = []
        delete_ids = []
        for message_id, event in unique_events.items():
            message = messages.get(message_id)
            if message is None:
                delete_ids.append(message_id)
                continue

            provider_status = str(event.get('status') or '').upper()
            provider_id = str(event.get('provider_message_id') or '')
            if not provider_id:
                raise RetryBatch(f'Send event for {message_id} has no provider_message_id')
            values = {
                'message_id': message.message_id,
                'campaign': message.campaign,
                'channel': message.channel,
                'recipient': str(event.get('recipient') or message.recipient),
                'sender_id': str(event.get('sender_id') or message.sender_id),
                'batch_id': message.batch_id,
                'total_attempts': max(message.send_attempts, 1),
                'provider_message_id': provider_id,
                'provider_status': provider_status,
                'provider_response': event,
            }
            if provider_status == 'ACCEPTED':
                success_rows.append(SuccessSent(
                    **values,
                    sent_at=_timestamp(event.get('received_at')),
                ))
            else:
                failed_rows.append(FailedSent(
                    **values,
                    last_error=str(event.get('error_reason') or provider_status or 'SMSC rejected message'),
                    error_code=str(event.get('err_code') or ''),
                    first_attempt_at=message.sending_started_at or message.built_at,
                    final_attempt_at=_timestamp(event.get('received_at')),
                ))
            delete_ids.append(message_id)

        if success_rows:
            SuccessSent.objects.bulk_create(success_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if failed_rows:
            FailedSent.objects.bulk_create(failed_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if delete_ids:
            MessageObject.objects.filter(message_id__in=delete_ids).delete()

    return len(success_rows) + len(failed_rows)


def process_delivery_batch(events: list[dict[str, Any]]) -> int:
    events = [event for event in events if event.get('event_type') == 'DELIVERY_REPORT']
    unique_events = {
        (event.get('message_id'), event.get('provider_message_id')): event
        for event in events
        if event.get('message_id') and event.get('provider_message_id')
    }
    if not unique_events:
        return 0

    provider_ids = {provider_id for _, provider_id in unique_events}
    message_ids = {message_id for message_id, _ in unique_events}
    with transaction.atomic():
        send_records = {}
        for model in (SuccessSent, FailedSent):
            send_records.update({
                (item.message_id, item.provider_message_id): item
                for item in model.objects.select_related('campaign', 'channel').filter(
                    message_id__in=message_ids,
                    provider_message_id__in=provider_ids,
                )
            })
        missing = set(unique_events) - send_records.keys()
        if missing:
            raise RetryBatch(f'{len(missing)} delivery reports are waiting for send history')

        existing_pairs = set()
        for model in (SuccessDelivery, FailedDelivery):
            existing_pairs.update(model.objects.filter(
                message_id__in=message_ids,
                provider_message_id__in=provider_ids,
            ).values_list('message_id', 'provider_message_id'))

        delivered_rows = []
        failed_rows = []
        for pair, event in unique_events.items():
            if pair in existing_pairs:
                continue
            sent = send_records[pair]
            channel = sent.channel
            if channel is None:
                raise RetryBatch(f'Send history for {pair[0]} has no channel_id')
            raw_status = str(event.get('status') or 'UNKNOWN').upper()
            values = {
                'message_id': sent.message_id,
                'provider_message_id': sent.provider_message_id,
                'campaign': sent.campaign,
                'channel': channel,
                'recipient': str(event.get('recipient') or sent.recipient),
                'sender_id': sent.sender_id,
                'delivery_code': str(event.get('err_code') or ''),
                'delivery_description': str(event.get('error_reason') or ''),
                'provider_response': event,
            }
            if raw_status == 'DELIVRD':
                delivered_rows.append(SuccessDelivery(
                    **values,
                    delivery_status='DELIVERED',
                    delivered_at=_timestamp(event.get('delivered_at')),
                ))
            else:
                failed_rows.append(FailedDelivery(
                    **values,
                    delivery_status=raw_status,
                    failed_at=_timestamp(event.get('delivered_at')),
                ))

        if delivered_rows:
            SuccessDelivery.objects.bulk_create(delivered_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if failed_rows:
            FailedDelivery.objects.bulk_create(failed_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)

    return len(delivered_rows) + len(failed_rows)


def database_snapshot() -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        cursor.fetchone()
    return {
        'message_object_pending': MessageObject.objects.filter(sent_status='PENDING').count(),
        'counts': {
            'successsent': SuccessSent.objects.count(),
            'failedsent': FailedSent.objects.count(),
            'successdelivery': SuccessDelivery.objects.count(),
            'faileddelivery': FailedDelivery.objects.count(),
        },
    }


class EventConsumer:
    def __init__(self, topic: str, group: str, handler: Callable[[list[dict[str, Any]]], int]):
        self.topic = topic
        self.group = group
        self.handler = handler
        self.consumer = None
        self.task: asyncio.Task | None = None
        self.running = False
        self.total_consumed = 0
        self.total_batches = 0
        self.last_error: str | None = None
        self._stopping = False

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer

        self.consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=self.group,
            enable_auto_commit=False,
            auto_offset_reset='earliest',
            max_poll_records=BATCH_SIZE,
            value_deserializer=lambda value: __import__('json').loads(value.decode('utf-8')),
        )
        await self.consumer.start()
        self._stopping = False
        self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None

    async def _run(self) -> None:
        from aiokafka.structs import OffsetAndMetadata

        self.running = True
        backoff = 1
        try:
            while not self._stopping:
                partitions = await self.consumer.getmany(
                    timeout_ms=POLL_INTERVAL_MS,
                    max_records=BATCH_SIZE,
                )
                partitions = {partition: records for partition, records in partitions.items() if records}
                if not partitions:
                    continue
                events = [record.value for records in partitions.values() for record in records]
                try:
                    await sync_to_async(self.handler, thread_sensitive=True)(events)
                    await self.consumer.commit({
                        partition: OffsetAndMetadata(records[-1].offset + 1, '')
                        for partition, records in partitions.items()
                    })
                    self.total_consumed += len(events)
                    self.total_batches += 1
                    self.last_error = None
                    backoff = 1
                except Exception as exc:
                    self.last_error = str(exc)
                    logger.exception('Kafka batch failed topic=%s group=%s size=%s', self.topic, self.group, len(events))
                    for partition, records in partitions.items():
                        self.consumer.seek(partition, records[0].offset)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30)
        finally:
            self.running = False

    def health(self) -> dict[str, Any]:
        return {
            'topic': self.topic,
            'group': self.group,
            'running': bool(self.running and self.task and not self.task.done()),
            'total_consumed': self.total_consumed,
            'total_batches': self.total_batches,
            'last_error': self.last_error,
        }


class StatusUpdater:
    def __init__(self):
        self.send_consumer = EventConsumer(SEND_TOPIC, SEND_GROUP, process_send_batch)
        self.delivery_consumer = EventConsumer(DELIVERY_TOPIC, DELIVERY_GROUP, process_delivery_batch)
        self.started = False

    async def start(self) -> None:
        await sync_to_async(database_snapshot, thread_sensitive=True)()
        await self.send_consumer.start()
        try:
            await self.delivery_consumer.start()
        except Exception:
            await self.send_consumer.stop()
            raise
        self.started = True

    async def stop(self) -> None:
        await asyncio.gather(self.send_consumer.stop(), self.delivery_consumer.stop())
        self.started = False

    async def health(self) -> dict[str, Any]:
        database_connected = True
        try:
            snapshot = await sync_to_async(database_snapshot, thread_sensitive=True)()
        except Exception:
            logger.exception('Status-updater database health check failed')
            database_connected = False
            snapshot = {'message_object_pending': 0, 'counts': {}}
        consumers = {
            'send_response': self.send_consumer.health(),
            'delivery_report': self.delivery_consumer.health(),
        }
        healthy = database_connected and all(item['running'] and item['last_error'] is None for item in consumers.values())
        return {
            'status': 'healthy' if healthy else 'degraded',
            'database_connected': database_connected,
            **snapshot,
            'consumers': consumers,
        }


updater = StatusUpdater()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await updater.start()
    try:
        yield
    finally:
        await updater.stop()


app = FastAPI(
    title='SMSC Kafka Status Updater',
    version='1.0.0',
    lifespan=lifespan,
)


@app.get('/')
async def root():
    return {'service': 'smsc-kafka-status-updater', 'health': '/health'}


@app.get('/health')
async def health():
    return await updater.health()
