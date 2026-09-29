"""Kafka consumers that persist send and delivery events to campaign history."""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    Channel,
    FailedDelivery,
    FailedSent,
    MessageObject,
    SuccessDelivery,
    SuccessSent,
)

logger = logging.getLogger('sms_status_updater')

KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
SEND_TOPIC = os.getenv('KAFKA_SENT_TOPIC', 'sent-response')
DELIVERY_TOPIC = os.getenv('KAFKA_DELIVERY_TOPIC', 'delivery-report')
SEND_GROUP = os.getenv('KAFKA_SEND_GROUP', 'status-updater-send')
DELIVERY_GROUP = os.getenv('KAFKA_DELIVERY_GROUP', 'status-updater-delivery')
BATCH_SIZE = max(1, int(os.getenv('KAFKA_BATCH_SIZE', '1000')))
POLL_INTERVAL_MS = max(1, int(os.getenv('KAFKA_POLL_INTERVAL_MS', '1000')))
KAFKA_STARTUP_TIMEOUT_SECONDS = max(1, int(os.getenv('KAFKA_STARTUP_TIMEOUT_SECONDS', '300')))
RETRY_DELAY_SECONDS = 2
ORPHAN_DLR_COUNT = 0

DELIVERY_STATUS_MAP = {
    'DELIVRD': ('DELIVERED', '000', 'Delivered'),
    'UNDELIV': ('UNDELIVERABLE', '008', 'Undeliverable'),
    'EXPIRED': ('EXPIRED', '001', 'Validity period expired'),
    'REJECTD': ('REJECTED', '002', 'Rejected'),
}


def _deserialize_event(value: bytes) -> dict[str, Any]:
    raw = value.decode('utf-8', errors='replace')
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {'_malformed_kafka_message': raw}
    return decoded if isinstance(decoded, dict) else {'_malformed_kafka_message': raw}


def _timestamp(value):
    if not value:
        return None
    parsed = parse_datetime(str(value).replace('Z', '+00:00'))
    if parsed is None:
        raise ValueError(f'Invalid event timestamp: {value}')
    return parsed


def _done_date_timestamp(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def process_send_batch(events: list[dict[str, Any]]) -> int:
    """Compatibility handler for the older SEND_RESPONSE event contract."""
    events = [event for event in events if isinstance(event, dict) and event.get('event_type') == 'SEND_RESPONSE']
    unique_events = {event.get('message_id'): event for event in events if event.get('message_id')}
    if not unique_events:
        return 0

    message_ids = set(unique_events)
    with transaction.atomic():
        messages = {
            item.message_id: item
            for item in MessageObject.objects.select_related('campaign', 'channel').filter(message_id__in=message_ids)
        }
        existing_ids = set(SuccessSent.objects.filter(message_id__in=message_ids).values_list('message_id', flat=True))
        existing_ids.update(FailedSent.objects.filter(message_id__in=message_ids).values_list('message_id', flat=True))
        missing = message_ids - messages.keys() - existing_ids
        if missing:
            raise RuntimeError(f'{len(missing)} legacy send events have no matching MessageObject')

        successes = []
        failures = []
        delete_ids = []
        for message_id, event in unique_events.items():
            message = messages.get(message_id)
            if message is None:
                delete_ids.append(message_id)
                continue
            provider_status = str(event.get('status') or '').upper()
            values = {
                'message_id': message.message_id,
                'provider_message_id': str(event.get('provider_message_id') or ''),
                'campaign': message.campaign,
                'channel': message.channel,
                'round_number': message.round_number,
                'recipient': str(event.get('recipient') or message.recipient),
                'sender_id': str(event.get('sender_id') or message.sender_id),
                'message_content': message.message_content,
                'servicetype': str(event.get('servicetype') or ''),
                'servicetag': str(event.get('servicetag') or ''),
                'batch_id': message.batch_id,
                'worker_id': message.worker_id,
                'request_payload': event.get('request_payload') or {},
                'total_attempts': max(message.send_attempts, 1),
                'provider_status': provider_status,
                'provider_response': event,
                'built_at': message.built_at,
                'sending_started_at': message.sending_started_at,
            }
            if provider_status == 'ACCEPTED':
                successes.append(SuccessSent(**values, sent_at=_timestamp(event.get('received_at'))))
            else:
                failures.append(FailedSent(
                    **values,
                    last_error=str(event.get('error_reason') or provider_status or 'SMSC rejected message'),
                    error_code=str(event.get('err_code') or ''),
                    error_type=str(event.get('error_type') or ''),
                    http_status_code=event.get('http_status_code'),
                    first_attempt_at=message.sending_started_at or message.built_at,
                    final_attempt_at=_timestamp(event.get('received_at')),
                ))
            delete_ids.append(message_id)

        if successes:
            SuccessSent.objects.bulk_create(successes, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if failures:
            FailedSent.objects.bulk_create(failures, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if delete_ids:
            MessageObject.objects.filter(message_id__in=delete_ids).delete()
    return len(successes) + len(failures)


def process_sent_batch(events: list[dict[str, Any]]) -> int:
    """Persist SENT_RESPONSE rows from event data, then remove queue rows."""
    unique_events = {}
    for event in events:
        if not isinstance(event, dict) or event.get('event_type') != 'SENT_RESPONSE':
            logger.warning('Skipping malformed send event: %r', event)
            continue
        message_id = str(event.get('message_id') or '').strip()
        if not message_id:
            logger.warning('Skipping send event without message_id: %r', event)
            continue
        unique_events[message_id] = event
    if not unique_events:
        return 0

    message_ids = set(unique_events)
    with transaction.atomic():
        existing_ids = set(SuccessSent.objects.filter(
            message_id__in=message_ids,
        ).values_list('message_id', flat=True))
        existing_ids.update(FailedSent.objects.filter(
            message_id__in=message_ids,
        ).values_list('message_id', flat=True))

        campaign_ids = set()
        channel_ids = set()
        candidates = {}
        for message_id, event in unique_events.items():
            if message_id in existing_ids:
                continue
            try:
                campaign_id = int(event['campaign_id'])
                channel_id = int(event['channel_id'])
                round_number = int(event.get('round_number') or 1)
                if round_number < 1 or not event.get('recipient') or not event.get('sender_id'):
                    raise ValueError('round_number, recipient, or sender_id is invalid')
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning('Skipping malformed send event message_id=%s error=%s event=%r', message_id, exc, event)
                continue
            candidates[message_id] = (event, campaign_id, channel_id, round_number)
            campaign_ids.add(campaign_id)
            channel_ids.add(channel_id)

        existing_campaigns = set(Campaign.objects.filter(pk__in=campaign_ids).values_list('pk', flat=True))
        existing_channels = set(Channel.objects.filter(pk__in=channel_ids).values_list('pk', flat=True))
        successes = []
        failures = []
        delete_ids = list(existing_ids.intersection(message_ids))

        for message_id, (event, campaign_id, channel_id, round_number) in candidates.items():
            if campaign_id not in existing_campaigns or channel_id not in existing_channels:
                logger.warning('Skipping send event with missing campaign/channel message_id=%s event=%r', message_id, event)
                continue
            try:
                values = {
                    'message_id': message_id,
                    'provider_message_id': str(event.get('provider_message_id') or ''),
                    'campaign_id': campaign_id,
                    'channel_id': channel_id,
                    'round_number': round_number,
                    'recipient': str(event['recipient']),
                    'sender_id': str(event['sender_id']),
                    'message_content': str(event.get('message_content') or ''),
                    'servicetype': str(event.get('servicetype') or ''),
                    'servicetag': str(event.get('servicetag') or ''),
                    'batch_id': str(event.get('batch_id') or ''),
                    'worker_id': str(event.get('worker_id') or ''),
                    'request_payload': event.get('request_payload') or {},
                    'provider_status': str(event.get('provider_status') or ''),
                    'provider_response': event.get('provider_response') or {},
                    'total_attempts': int(event.get('total_attempts') or 0),
                    'built_at': _timestamp(event.get('built_at')),
                    'sending_started_at': _timestamp(event.get('sending_started_at')),
                }
                if event.get('accepted') is True:
                    successes.append(SuccessSent(**values, sent_at=_timestamp(event.get('sent_at'))))
                else:
                    failures.append(FailedSent(
                        **values,
                        last_error=str(event.get('last_error') or ''),
                        error_code=str(event.get('error_code') or ''),
                        error_type=str(event.get('error_type') or ''),
                        http_status_code=event.get('http_status_code'),
                        first_attempt_at=_timestamp(event.get('first_attempt_at')),
                        final_attempt_at=_timestamp(event.get('final_attempt_at')),
                    ))
                delete_ids.append(message_id)
            except (TypeError, ValueError) as exc:
                logger.warning('Skipping malformed send timestamps or fields message_id=%s error=%s event=%r', message_id, exc, event)

        if successes:
            SuccessSent.objects.bulk_create(successes, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if failures:
            FailedSent.objects.bulk_create(failures, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if delete_ids:
            MessageObject.objects.filter(message_id__in=delete_ids).delete()
    return len(successes) + len(failures)


def process_delivery_batch(events: list[dict[str, Any]]) -> int:
    """Write each DLR from matching send history; orphan events are committed and counted."""
    global ORPHAN_DLR_COUNT
    unique_events = {}
    for event in events:
        if not isinstance(event, dict) or event.get('event_type') != 'DELIVERY_REPORT':
            logger.warning('Skipping malformed delivery event: %r', event)
            continue
        provider_id = str(event.get('provider_message_id') or '').strip()
        if not provider_id:
            logger.warning('Skipping delivery event without provider_message_id: %r', event)
            continue
        unique_events[provider_id] = event
    if not unique_events:
        return 0

    provider_ids = set(unique_events)
    with transaction.atomic():
        success_by_provider = {
            item.provider_message_id: item
            for item in SuccessSent.objects.select_related('campaign', 'channel').filter(provider_message_id__in=provider_ids)
        }
        failed_by_provider = {
            item.provider_message_id: item
            for item in FailedSent.objects.select_related('campaign', 'channel').filter(
                provider_message_id__in=provider_ids,
            ).exclude(provider_message_id__in=success_by_provider)
        }
        matched = {}
        orphan_count = 0
        for provider_id, event in unique_events.items():
            sent = success_by_provider.get(provider_id) or failed_by_provider.get(provider_id)
            if sent is None:
                logger.warning('Orphan delivery report provider_message_id=%s event=%r', provider_id, event)
                orphan_count += 1
                continue
            matched[(sent.message_id, sent.provider_message_id)] = (sent, event)

        message_ids = {message_id for message_id, _ in matched}
        matched_provider_ids = {provider_id for _, provider_id in matched}
        existing_pairs = set()
        for model in (SuccessDelivery, FailedDelivery):
            existing_pairs.update(model.objects.filter(
                message_id__in=message_ids,
                provider_message_id__in=matched_provider_ids,
            ).values_list('message_id', 'provider_message_id'))

        delivered_rows = []
        failed_rows = []
        for pair, (sent, event) in matched.items():
            if pair in existing_pairs:
                continue
            raw_payload = event.get('raw_payload')
            if not isinstance(raw_payload, dict):
                raw_payload = event
            done_date_value = str(event.get('doneDate') or event.get('done_date') or '')
            reported_at = _done_date_timestamp(done_date_value)
            raw_status = str(event.get('status') or 'UNKNOWN').upper()
            delivery_status, delivery_code, description = DELIVERY_STATUS_MAP.get(
                raw_status,
                ('UNKNOWN', '999', 'Unknown'),
            )
            values = {
                'message_id': sent.message_id,
                'provider_message_id': sent.provider_message_id,
                'campaign': sent.campaign,
                'channel': sent.channel,
                'round_number': sent.round_number,
                'recipient': str(event.get('msisdn') or ''),
                'delivery_code': delivery_code,
                'delivery_description': description,
                'provider_response': event,
                'raw_dlr_payload': raw_payload,
                'event': str(event.get('event') or ''),
                'done_date': done_date_value,
                'sent_at': getattr(sent, 'sent_at', None),
            }
            if delivery_status == 'DELIVERED':
                delivered_rows.append(SuccessDelivery(
                    **values,
                    delivery_status=delivery_status,
                    delivered_at=reported_at,
                ))
            else:
                failed_rows.append(FailedDelivery(
                    **values,
                    delivery_status=delivery_status,
                    error_code=delivery_code,
                    error_reason=description,
                    failed_at=reported_at,
                ))

        if delivered_rows:
            SuccessDelivery.objects.bulk_create(delivered_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)
        if failed_rows:
            FailedDelivery.objects.bulk_create(failed_rows, batch_size=BATCH_SIZE, ignore_conflicts=True)
    ORPHAN_DLR_COUNT += orphan_count
    return len(delivered_rows) + len(failed_rows)


def database_snapshot() -> dict[str, Any]:
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return {
            'message_object_pending': MessageObject.objects.filter(sent_status='PENDING').count(),
            'counts': {
                'messageobject': MessageObject.objects.count(),
                'success_sent': SuccessSent.objects.count(),
                'failed_sent': FailedSent.objects.count(),
                'success_delivery': SuccessDelivery.objects.count(),
                'failed_delivery': FailedDelivery.objects.count(),
            },
        }
    finally:
        connection.close()


def _run_handler(handler, events):
    try:
        return handler(events)
    finally:
        connection.close()


class EventConsumer:
    def __init__(self, topic: str, group: str, handler: Callable[[list[dict[str, Any]]], int]):
        self.topic = topic
        self.group = group
        self.handler = handler
        self.consumer = None
        self.task: asyncio.Task | None = None
        self.running = False
        self.kafka_connected = False
        self.total_consumed = 0
        self.total_batches = 0
        self.last_batch_at: str | None = None
        self.last_error: str | None = None
        self._stopping = False

    async def start(self) -> None:
        from aiokafka import AIOKafkaConsumer

        deadline = asyncio.get_running_loop().time() + KAFKA_STARTUP_TIMEOUT_SECONDS
        delay = 1
        while not self._stopping:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f'Kafka startup timed out for topic {self.topic}')
            consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                group_id=self.group,
                enable_auto_commit=False,
                auto_offset_reset='earliest',
                max_poll_records=BATCH_SIZE,
                value_deserializer=_deserialize_event,
            )
            try:
                await asyncio.wait_for(consumer.start(), timeout=remaining)
                self.consumer = consumer
                self.kafka_connected = True
                self.last_error = None
                self.task = asyncio.create_task(self._run())
                return
            except asyncio.CancelledError:
                await asyncio.gather(consumer.stop(), return_exceptions=True)
                raise
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception('Kafka startup failed topic=%s group=%s', self.topic, self.group)
                await asyncio.gather(consumer.stop(), return_exceptions=True)
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise
                await asyncio.sleep(min(delay, remaining))
                delay = min(delay * 2, 30)

    async def stop(self) -> None:
        self._stopping = True
        self.running = False
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        if self.consumer:
            await self.consumer.stop()
            self.consumer = None
        self.kafka_connected = False

    async def _run(self) -> None:
        from aiokafka.structs import OffsetAndMetadata

        self.running = True
        try:
            while not self._stopping:
                try:
                    partitions = await self.consumer.getmany(
                        timeout_ms=POLL_INTERVAL_MS,
                        max_records=BATCH_SIZE,
                    )
                    self.kafka_connected = True
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.kafka_connected = False
                    self.last_error = f'Kafka poll failed: {exc}'
                    logger.exception('Kafka poll failed topic=%s group=%s', self.topic, self.group)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                if self.last_error and self.last_error.startswith('Kafka poll failed:'):
                    self.last_error = None

                partitions = {partition: records for partition, records in partitions.items() if records}
                if not partitions:
                    continue
                events = []
                for records in partitions.values():
                    for record in records:
                        if isinstance(record.value, dict):
                            events.append(record.value)
                        else:
                            logger.warning('Skipping malformed Kafka value topic=%s value=%r', self.topic, record.value)
                try:
                    await sync_to_async(_run_handler, thread_sensitive=True)(self.handler, events)
                    await self.consumer.commit({
                        partition: OffsetAndMetadata(records[-1].offset + 1, '')
                        for partition, records in partitions.items()
                    })
                    self.total_consumed += sum(len(records) for records in partitions.values())
                    self.total_batches += 1
                    self.last_batch_at = datetime.now(timezone.utc).isoformat()
                    self.last_error = None
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = str(exc)
                    logger.exception('Kafka batch failed topic=%s group=%s size=%s', self.topic, self.group, len(events))
                    for partition, records in partitions.items():
                        try:
                            self.consumer.seek(partition, records[0].offset)
                        except Exception:
                            self.kafka_connected = False
                            logger.exception('Kafka seek failed topic=%s partition=%s', self.topic, partition)
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        finally:
            self.running = False

    def health(self) -> dict[str, Any]:
        return {
            'topic': self.topic,
            'group': self.group,
            'running': bool(self.running and self.task and not self.task.done()),
            'kafka_connected': self.kafka_connected,
            'total_consumed': self.total_consumed,
            'total_batches': self.total_batches,
            'last_batch_at': self.last_batch_at,
            'last_error': self.last_error,
        }


class StatusUpdater:
    def __init__(self):
        self.send_consumer = EventConsumer(SEND_TOPIC, SEND_GROUP, process_sent_batch)
        self.delivery_consumer = EventConsumer(DELIVERY_TOPIC, DELIVERY_GROUP, process_delivery_batch)
        self.started = False

    async def start(self) -> None:
        await sync_to_async(database_snapshot, thread_sensitive=True)()
        try:
            await asyncio.gather(
                self.send_consumer.start(),
                self.delivery_consumer.start(),
            )
        except Exception:
            await asyncio.gather(
                self.send_consumer.stop(),
                self.delivery_consumer.stop(),
                return_exceptions=True,
            )
            raise
        self.started = True

    async def stop(self) -> None:
        await asyncio.gather(
            self.send_consumer.stop(),
            self.delivery_consumer.stop(),
            return_exceptions=True,
        )
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
        kafka_connected = all(item['kafka_connected'] for item in consumers.values())
        healthy = database_connected and all(
            item['running'] and item['last_error'] is None
            for item in consumers.values()
        )
        return {
            'status': 'healthy' if healthy else 'degraded',
            'database_connected': database_connected,
            'kafka_connected': kafka_connected,
            'orphan_delivery_reports': ORPHAN_DLR_COUNT,
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