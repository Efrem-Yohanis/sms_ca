import asyncio
import base64
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
logger = logging.getLogger('sms_smsc_sender')

DB_HOST = os.getenv('DB_HOST', 'postgres')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'campaign_db')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DJANGO_API = os.getenv('SMSC_SENDER_DJANGO_API', 'http://django-app:8000/api/v1').rstrip('/')
KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
KAFKA_SENT_TOPIC = os.getenv('KAFKA_SENT_TOPIC', 'sent-response')
TICK_INTERVAL = float(os.getenv('SMSC_SENDER_SCHEDULER_INTERVAL', '1'))
SENDER_WORKERS = max(1, int(os.getenv('SMSC_SENDER_WORKERS', '100')))
LOCK_TIMEOUT_SECONDS = max(1, int(os.getenv('LOCK_TIMEOUT_SECONDS', '300')))
RUN_WORKER = os.getenv('SMSC_SENDER_RUN_WORKER', 'true').lower() in {'1', 'true', 'yes'}
FIELD_ENCRYPTION_KEY = os.getenv('FIELD_ENCRYPTION_KEY', '')


class CampaignRequest(BaseModel):
    campaign_id: int = Field(gt=0)
    round_number: int = Field(default=1, ge=1)


class CampaignStopRequest(CampaignRequest):
    reason: str = 'manual_stop'


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def decrypt_database_secret(value: str | None) -> str:
    if not value:
        return ''
    if not value.startswith('gAAAA'):
        return value
    if not FIELD_ENCRYPTION_KEY:
        raise RuntimeError('FIELD_ENCRYPTION_KEY is required to decrypt SMSC credentials')
    try:
        return Fernet(FIELD_ENCRYPTION_KEY.encode()).decrypt(value.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError('Could not decrypt SMSC credentials; verify FIELD_ENCRYPTION_KEY') from exc


def unwrap_api_data(body: Any) -> Any:
    if isinstance(body, dict) and 'data' in body:
        return body['data']
    return body


def allocate_tps(global_tps: int, campaign_ids: list[int], smsc_cap: int) -> dict[int, int]:
    sorted_ids = sorted(campaign_ids)
    if not sorted_ids:
        return {}
    base, remainder = divmod(max(0, global_tps), len(sorted_ids))
    return {
        campaign_id: min(smsc_cap, base + (index < remainder))
        for index, campaign_id in enumerate(sorted_ids)
    }


def build_chunks(messages: list[dict[str, Any]], max_addresses: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[int | None, str], list[dict[str, Any]]] = {}
    for message in messages:
        key = (message.get('language_id'), message['message_content'])
        grouped.setdefault(key, []).append(message)

    chunks = []
    chunk_size = max(1, max_addresses)
    for (language_id, message_content), group in grouped.items():
        for start in range(0, len(group), chunk_size):
            chunks.append({
                'language_id': language_id,
                'message_content': message_content,
                'messages': group[start:start + chunk_size],
            })
    return chunks


def channel_service_type(channel_code: str | None) -> str:
    return 'flash' if (channel_code or '').strip().lower() == 'flash' else 'normal'


class Sender:
    def __init__(self):
        self.pool: AsyncConnectionPool | None = None
        self.http: httpx.AsyncClient | None = None
        self.django_http: httpx.AsyncClient | None = None
        self.producer: Any | None = None
        self.kafka_connected = False
        self.worker_task: asyncio.Task | None = None
        self.active_campaigns: dict[int, dict[str, Any]] = {}
        self.last_report: dict[str, Any] = {'success': True, 'tick_at': None, 'campaigns_processed': 0}
        self.tick_lock = asyncio.Lock()
        self.worker_id = f'worker_{os.getpid()}_{uuid.uuid4().hex[:6]}'
        self.current_smsc_config: dict[str, Any] | None = None

    async def start(self) -> None:
        conninfo = (
            f'host={DB_HOST} port={DB_PORT} dbname={DB_NAME} '
            f'user={DB_USER} password={DB_PASSWORD}'
        )
        self.pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=max(4, SENDER_WORKERS),
            kwargs={'row_factory': dict_row},
            open=False,
        )
        await self.pool.open(wait=True)
        self.http = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=SENDER_WORKERS),
        )
        self.django_http = httpx.AsyncClient(timeout=15)
        from aiokafka import AIOKafkaProducer

        self.producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            acks='all',
            linger_ms=10,
            compression_type='gzip',
            value_serializer=lambda value: json.dumps(value).encode('utf-8'),
            key_serializer=lambda key: key.encode('utf-8'),
        )
        await self.producer.start()
        self.kafka_connected = True
        if RUN_WORKER:
            self.ensure_worker()

    async def stop(self) -> None:
        if self.worker_task:
            self.worker_task.cancel()
            await asyncio.gather(self.worker_task, return_exceptions=True)
            self.worker_task = None
        self.kafka_connected = False
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None
        if self.django_http is not None:
            await self.django_http.aclose()
            self.django_http = None
        if self.http is not None:
            await self.http.aclose()
            self.http = None
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    def ensure_worker(self) -> None:
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker())

    def require_pool(self) -> AsyncConnectionPool:
        if self.pool is None:
            raise RuntimeError('Postgres connection pool is not initialized')
        return self.pool

    def require_django_http(self) -> httpx.AsyncClient:
        if self.django_http is None:
            raise RuntimeError('Django API client is not initialized')
        return self.django_http

    async def fetch_active_config(self, endpoint: str, key: str) -> Any:
        response = await self.require_django_http().get(f'{DJANGO_API}/{endpoint}/active/')
        if response.status_code != 200:
            raise RuntimeError(f'{endpoint} active config returned HTTP {response.status_code}: {response.text[:300]}')
        body = response.json()
        data = unwrap_api_data(body)
        if not isinstance(data, dict) or key not in data:
            raise RuntimeError(f'{endpoint} active config did not include {key}')
        return data

    async def load_smsc_config(self) -> dict[str, Any]:
        pool = self.require_pool()
        async with pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    '''SELECT * FROM sms_campaign_manager_smscconfig
                       WHERE is_active = TRUE
                       ORDER BY is_default DESC, id ASC
                       LIMIT 1''',
                )
                row = await cursor.fetchone()
        if row is None:
            raise RuntimeError('No active SMSCConfig found')
        config = dict(row)
        config['api_key'] = decrypt_database_secret(config.get('api_key'))
        config['api_secret'] = decrypt_database_secret(config.get('api_secret'))
        config['password'] = decrypt_database_secret(config.get('password'))
        if isinstance(config.get('extra_headers'), str):
            config['extra_headers'] = json.loads(config['extra_headers'] or '{}')
        self.current_smsc_config = config
        return config

    async def load_channel_codes(self) -> dict[int, str]:
        pool = self.require_pool()
        async with pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute('SELECT id, code FROM sms_campaign_manager_channel')
                rows = await cursor.fetchall()
        return {int(row['id']): str(row['code']) for row in rows}

    async def load_tick_config(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[int, str]]:
        global_config, addresses_config, smsc_config, channels = await asyncio.gather(
            self.fetch_active_config('global-tps-config', 'global_tps'),
            self.fetch_active_config('n-addresses-config', 'max_addresses_per_request'),
            self.load_smsc_config(),
            self.load_channel_codes(),
        )
        return global_config, addresses_config, smsc_config, channels

    async def campaign_action(self, campaign_id: int, action: str) -> tuple[int, Any]:
        response = await self.require_django_http().post(
            f'{DJANGO_API}/campaigns/{campaign_id}/{action}/',
            json={},
        )
        try:
            body = response.json()
        except ValueError:
            body = {'raw': response.text[:500]}
        return response.status_code, body

    async def activate_campaign(self, campaign_id: int) -> Any:
        status_code, body = await self.campaign_action(campaign_id, 'activate')
        detail = json.dumps(body, ensure_ascii=False).lower()
        already_active = status_code == 400 and 'already active' in detail
        if not (200 <= status_code < 300 or already_active):
            raise RuntimeError(f'activate campaign {campaign_id} failed: HTTP {status_code}: {body}')
        return body

    async def start_campaign(self, campaign_id: int) -> Any:
        status_code, body = await self.campaign_action(campaign_id, 'start')
        if not 200 <= status_code < 300:
            raise RuntimeError(f'start campaign {campaign_id} failed: HTTP {status_code}: {body}')
        return body

    async def pause_campaign(self, campaign_id: int) -> Any:
        status_code, body = await self.campaign_action(campaign_id, 'pause')
        if not 200 <= status_code < 300:
            raise RuntimeError(f'pause campaign {campaign_id} failed: HTTP {status_code}: {body}')
        return body

    async def pending_count(
        self,
        campaign_id: int,
        *,
        round_number: int | None = None,
        status_filter: tuple[str, ...] = ('PENDING', 'FAILED'),
    ) -> int:
        pool = self.require_pool()
        async with pool.connection() as connection:
            async with connection.cursor() as cursor:
                query = '''SELECT COUNT(*) AS count
                           FROM sms_campaign_manager_messageobject
                           WHERE campaign_id = %s AND sent_status = ANY(%s)'''
                params: tuple[Any, ...] = (campaign_id, list(status_filter))
                if round_number is not None:
                    query += ' AND round_number = %s'
                    params += (round_number,)
                await cursor.execute(
                    query,
                    params,
                )
                row = await cursor.fetchone()
        return int(row['count'])

    async def claim_messages(
        self,
        campaign_id: int,
        round_number: int,
        quota: int,
        max_retries: int,
    ) -> list[dict[str, Any]]:
        if quota <= 0:
            return []
        pool = self.require_pool()
        batch_id = f'batch_{campaign_id}_{uuid.uuid4().hex[:8]}'
        now = datetime.now(timezone.utc)
        async with pool.connection() as connection:
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        '''SELECT m.id
                           FROM sms_campaign_manager_messageobject AS m
                           INNER JOIN sms_campaign_manager_campaign AS c ON c.id = m.campaign_id
                           WHERE m.campaign_id = %s
                                                         AND m.round_number = %s
                             AND c.status IN ('active', 'in_progress')
                             AND c.is_deleted = FALSE
                             AND m.sent_status IN ('PENDING', 'FAILED')
                             AND m.send_attempts < %s
                             AND (m.locked_until IS NULL OR m.locked_until < NOW())
                           ORDER BY m.id ASC
                           LIMIT %s
                           FOR UPDATE OF m SKIP LOCKED''',
                        (campaign_id, round_number, max_retries, quota),
                    )
                    rows = await cursor.fetchall()
                    message_ids = [row['id'] for row in rows]
                    if not message_ids:
                        return []
                    await cursor.execute(
                        '''UPDATE sms_campaign_manager_messageobject
                           SET batch_id = %s,
                               worker_id = %s,
                               sending_started_at = COALESCE(sending_started_at, %s),
                               locked_until = NOW() + (%s * INTERVAL '1 second'),
                               updated_at = NOW()
                           WHERE id = ANY(%s)''',
                        (batch_id, self.worker_id, now, LOCK_TIMEOUT_SECONDS, message_ids),
                    )
                    await cursor.execute(
                        '''SELECT * FROM sms_campaign_manager_messageobject
                           WHERE id = ANY(%s)
                           ORDER BY id ASC''',
                        (message_ids,),
                    )
                    return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def build_payload(chunk: dict[str, Any], channel_codes: dict[int, str]) -> dict[str, Any]:
        messages = chunk['messages']
        campaign_id = messages[0]['campaign_id']
        recipients = []
        for message in messages:
            recipient = str(message['recipient'])
            recipients.append({'id': recipient[1:] if recipient.startswith('+') else recipient})
        channel_code = channel_codes.get(int(messages[0]['channel_id']), 'sms')
        return {
            'shortMessage': chunk['message_content'],
            'messageType': 'TEXT',
            'destAddr': recipients,
            'sourceAddr': {'name': messages[0]['sender_id']},
            'servicetag': {'name': f'camp-{campaign_id}'},
            'servicetype': {'name': 'flash' if channel_code.strip().lower() == 'flash' else 'normal'},
        }

    @staticmethod
    def auth_headers(config: dict[str, Any]) -> dict[str, str]:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        auth_type = config.get('auth_type')
        if auth_type == 'basic':
            token = base64.b64encode(
                f"{config.get('username', '')}:{config.get('password', '')}".encode(),
            ).decode()
            headers['Authorization'] = f'Basic {token}'
        elif auth_type == 'bearer':
            headers['Authorization'] = f"Bearer {config.get('api_key', '')}"
        elif auth_type == 'api_key' and config.get('api_key'):
            headers['X-API-Key'] = config['api_key']
        headers.update(config.get('extra_headers') or {})
        return headers

    async def send_chunk(
        self,
        config: dict[str, Any],
        chunk: dict[str, Any],
        channel_codes: dict[int, str],
    ) -> list[dict[str, Any]]:
        payload = self.build_payload(chunk, channel_codes)
        url = f"{config['base_url'].rstrip('/')}/{config['send_endpoint'].lstrip('/')}"
        if self.http is None:
            raise RuntimeError('SMSC HTTP client is not initialized')
        messages = chunk['messages']
        try:
            response = await self.http.post(
                url,
                json=payload,
                headers=self.auth_headers(config),
                timeout=httpx.Timeout(
                    connect=float(config['connect_timeout_seconds']),
                    read=float(config['request_timeout_seconds']),
                    write=float(config['request_timeout_seconds']),
                    pool=float(config['connect_timeout_seconds']),
                ),
            )
        except httpx.TimeoutException as exc:
            return [self.failure(message, payload, str(exc), 'TIMEOUT') for message in messages]
        except httpx.RequestError as exc:
            return [self.failure(message, payload, str(exc), 'NETWORK') for message in messages]

        if response.status_code != 200:
            error = f'SMSC returned HTTP {response.status_code}: {response.text[:500]}'
            return [self.failure(message, payload, error, 'HTTP', response.status_code) for message in messages]
        try:
            results = response.json()
        except ValueError as exc:
            error = f'SMSC returned malformed JSON: {exc}'
            return [self.failure(message, payload, error, 'SMSC', 200) for message in messages]
        if not isinstance(results, list):
            error = 'SMSC response body was not an array'
            return [self.failure(message, payload, error, 'SMSC', 200) for message in messages]

        outcomes = []
        for index, message in enumerate(messages):
            result = results[index] if index < len(results) else None
            provider_id = str(result.get('messageId') or '') if isinstance(result, dict) else ''
            if isinstance(result, dict) and result.get('status') == 'submitted' and provider_id:
                outcomes.append({
                    'message': message,
                    'accepted': True,
                    'payload': payload,
                    'provider_response': result,
                    'provider_message_id': provider_id,
                    'provider_status': 'submitted',
                    'error': '',
                    'error_type': '',
                    'error_code': '',
                    'http_status_code': 200,
                })
            else:
                status = result.get('status') if isinstance(result, dict) else 'missing'
                error = f'SMSC rejected: status={status}'
                outcomes.append(self.failure(
                    message,
                    payload,
                    error,
                    'SMSC',
                    200,
                    result if isinstance(result, dict) else {},
                    provider_id,
                ))
        return outcomes

    @staticmethod
    def failure(
        message: dict[str, Any],
        payload: dict[str, Any],
        error: str,
        error_type: str,
        http_status_code: int | None = None,
        provider_response: dict[str, Any] | None = None,
        provider_message_id: str = '',
    ) -> dict[str, Any]:
        return {
            'message': message,
            'accepted': False,
            'payload': payload,
            'provider_response': provider_response or {},
            'provider_message_id': provider_message_id,
            'provider_status': str((provider_response or {}).get('status') or 'failed'),
            'error': error,
            'error_type': error_type,
            'error_code': 'SMSC_REJECTED' if error_type == 'SMSC' else '',
            'http_status_code': http_status_code,
        }

    async def update_outcomes(
        self,
        outcomes: list[dict[str, Any]],
        max_retries: int,
    ) -> dict[str, int]:
        accepted_ids = []
        failed_ids = []
        terminal_events = []
        counts = {'accepted': 0, 'failed_retryable': 0, 'failed_permanent': 0}
        timestamp = iso_now()

        for outcome in outcomes:
            message = outcome['message']
            attempts = int(message['send_attempts']) + 1
            if outcome['accepted']:
                accepted_ids.append(message['id'])
                counts['accepted'] += 1
                terminal_events.append(self.sent_event(outcome, accepted=True, attempts=attempts, timestamp=timestamp))
            else:
                failed_ids.append(message['id'])
                permanent = attempts >= max_retries
                counts['failed_permanent' if permanent else 'failed_retryable'] += 1
                if permanent:
                    terminal_events.append(self.sent_event(outcome, accepted=False, attempts=attempts, timestamp=timestamp))

        if accepted_ids or failed_ids:
            pool = self.require_pool()
            async with pool.connection() as connection:
                async with connection.transaction():
                    async with connection.cursor() as cursor:
                        if accepted_ids:
                            await cursor.execute(
                                '''UPDATE sms_campaign_manager_messageobject
                                   SET sent_status = 'SENT', locked_until = NULL, updated_at = NOW()
                                   WHERE id = ANY(%s)''',
                                (accepted_ids,),
                            )
                        if failed_ids:
                            await cursor.execute(
                                '''UPDATE sms_campaign_manager_messageobject
                                   SET sent_status = 'FAILED', send_attempts = send_attempts + 1,
                                       locked_until = NULL, updated_at = NOW()
                                   WHERE id = ANY(%s)''',
                                (failed_ids,),
                            )

        counts['published_to_kafka'] = await self.publish_events(terminal_events)
        return counts

    @staticmethod
    def sent_event(
        outcome: dict[str, Any],
        *,
        accepted: bool,
        attempts: int,
        timestamp: str,
    ) -> dict[str, Any]:
        message = outcome['message']
        event = {
            'event_type': 'SENT_RESPONSE',
            'accepted': accepted,
            'message_id': message['message_id'],
            'provider_message_id': outcome['provider_message_id'],
            'campaign_id': message['campaign_id'],
            'channel_id': message['channel_id'],
            'round_number': message['round_number'],
            'recipient': str(message['recipient']).lstrip('+'),
            'sender_id': message['sender_id'],
            'message_content': message['message_content'],
            'servicetype': outcome['payload']['servicetype']['name'],
            'servicetag': outcome['payload']['servicetag']['name'],
            'batch_id': message['batch_id'],
            'worker_id': message['worker_id'],
            'request_payload': outcome['payload'],
            'provider_status': outcome['provider_status'],
            'provider_response': outcome['provider_response'],
            'total_attempts': attempts,
            'last_error': outcome['error'],
            'error_type': outcome['error_type'],
            'error_code': outcome['error_code'],
            'http_status_code': outcome['http_status_code'],
            'built_at': message['built_at'].isoformat() if hasattr(message['built_at'], 'isoformat') else message['built_at'],
            'sending_started_at': message['sending_started_at'].isoformat() if hasattr(message['sending_started_at'], 'isoformat') else message['sending_started_at'],
            'received_at': timestamp,
        }
        if accepted:
            event['sent_at'] = timestamp
        else:
            first_attempt = message['sending_started_at']
            event['first_attempt_at'] = first_attempt.isoformat() if hasattr(first_attempt, 'isoformat') else first_attempt or timestamp
            event['final_attempt_at'] = timestamp
        return event

    async def publish_events(self, events: list[dict[str, Any]]) -> int:
        if not events or self.producer is None:
            return 0
        futures = []
        try:
            for event in events:
                futures.append(await self.producer.send(KAFKA_SENT_TOPIC, event, key=event['message_id']))
            results = await asyncio.gather(*futures, return_exceptions=True)
            successful = sum(not isinstance(result, BaseException) for result in results)
            for result in results:
                if isinstance(result, BaseException):
                    logger.error('Kafka sent-response publish failed: %s', result)
            return successful
        except Exception:
            logger.exception('Kafka sent-response publication failed')
            return 0

    async def run_campaign_tick(
        self,
        campaign_id: int,
        allocated_tps: int,
        max_addresses: int,
        max_retries: int,
        channels: dict[int, str],
        smsc_config: dict[str, Any],
    ) -> dict[str, Any]:
        started = time.monotonic()
        quota = int(allocated_tps * max(0, TICK_INTERVAL))
        round_number = self.active_campaigns[campaign_id]['round_number']
        messages = await self.claim_messages(campaign_id, round_number, quota, max_retries)
        report = {
            'campaign_id': campaign_id,
            'round_number': self.active_campaigns[campaign_id]['round_number'],
            'claimed': len(messages),
            'accepted': 0,
            'failed_retryable': 0,
            'failed_permanent': 0,
            'published_to_kafka': 0,
            'duration_seconds': 0.0,
        }
        if not messages:
            report['duration_seconds'] = round(time.monotonic() - started, 3)
            return report

        chunks = build_chunks(messages, max_addresses)
        semaphore = asyncio.Semaphore(SENDER_WORKERS)

        async def send_limited(chunk: dict[str, Any]) -> list[dict[str, Any]]:
            async with semaphore:
                return await self.send_chunk(smsc_config, chunk, channels)

        chunk_outcomes = await asyncio.gather(*(send_limited(chunk) for chunk in chunks))
        outcomes = [outcome for chunk_result in chunk_outcomes for outcome in chunk_result]
        counts = await self.update_outcomes(outcomes, max_retries)
        report.update({key: counts[key] for key in (
            'accepted', 'failed_retryable', 'failed_permanent', 'published_to_kafka',
        )})
        report['duration_seconds'] = round(time.monotonic() - started, 3)
        return report

    async def tick(self) -> dict[str, Any]:
        global_config, addresses_config, smsc_config, channels = await self.load_tick_config()
        if not self.active_campaigns:
            return {'success': True, 'tick_at': iso_now(), 'campaigns_processed': 0, 'reports': []}

        reports = []
        allocations = allocate_tps(
            int(global_config['global_tps']),
            list(self.active_campaigns),
            int(smsc_config['rate_limit_per_second']),
        )
        for campaign_id in sorted(self.active_campaigns):
            reports.append(await self.run_campaign_tick(
                campaign_id,
                allocations[campaign_id],
                int(addresses_config['max_addresses_per_request']),
                int(smsc_config['max_retries']),
                channels,
                smsc_config,
            ))
        return {
            'success': True,
            'tick_at': iso_now(),
            'campaigns_processed': len(reports),
            'claimed': sum(report['claimed'] for report in reports),
            'accepted': sum(report['accepted'] for report in reports),
            'failed_retryable': sum(report['failed_retryable'] for report in reports),
            'failed_permanent': sum(report['failed_permanent'] for report in reports),
            'published_to_kafka': sum(report['published_to_kafka'] for report in reports),
            'duration_seconds': sum(report['duration_seconds'] for report in reports),
            'reports': reports,
        }

    async def run_once(self) -> dict[str, Any]:
        async with self.tick_lock:
            report = await self.tick()
            self.last_report = report
            return report

    async def worker(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception('Sender tick failed: %s', exc)
                self.last_report = {
                    'success': False,
                    'tick_at': iso_now(),
                    'campaigns_processed': 0,
                    'error': str(exc),
                    'reports': [],
                }
            remaining = TICK_INTERVAL - (time.monotonic() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)

    async def status_for_campaign(self, campaign_id: int) -> dict[str, Any]:
        active = self.active_campaigns.get(campaign_id)
        pending = await self.pending_count(
            campaign_id,
            round_number=active['round_number'] if active else None,
        )
        if active is None:
            return {
                'success': True,
                'data': {'campaign_id': campaign_id, 'active': False, 'pending_count': pending, 'allocation': None},
            }
        global_config = await self.fetch_active_config('global-tps-config', 'global_tps')
        smsc_config = await self.load_smsc_config()
        allocations = allocate_tps(
            int(global_config['global_tps']),
            list(self.active_campaigns),
            int(smsc_config['rate_limit_per_second']),
        )
        return {
            'success': True,
            'data': {
                'campaign_id': campaign_id,
                'active': True,
                'round_number': active['round_number'],
                'pending_count': pending,
                'allocation': {
                    'allocated_tps': allocations[campaign_id],
                    'total_global_tps': int(global_config['global_tps']),
                    'active_campaigns': len(self.active_campaigns),
                },
            },
        }

    async def status_all(self) -> dict[str, Any]:
        if not self.active_campaigns:
            return {'success': True, 'data': {'active_campaigns': []}}
        global_config = await self.fetch_active_config('global-tps-config', 'global_tps')
        smsc_config = await self.load_smsc_config()
        allocations = allocate_tps(
            int(global_config['global_tps']),
            list(self.active_campaigns),
            int(smsc_config['rate_limit_per_second']),
        )
        pool = self.require_pool()
        async with pool.connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    '''SELECT campaign_id, round_number, COUNT(*) AS count
                       FROM sms_campaign_manager_messageobject
                       WHERE campaign_id = ANY(%s) AND sent_status = ANY(%s)
                       GROUP BY campaign_id, round_number''',
                    (list(self.active_campaigns), ['PENDING', 'FAILED']),
                )
                counts = {
                    (int(row['campaign_id']), int(row['round_number'])): int(row['count'])
                    for row in await cursor.fetchall()
                }
        return {
            'success': True,
            'data': {
                'active_campaigns': [
                    {
                        'campaign_id': campaign_id,
                        'round_number': self.active_campaigns[campaign_id]['round_number'],
                        'pending_count': counts.get((campaign_id, self.active_campaigns[campaign_id]['round_number']), 0),
                        'allocated_tps': allocations[campaign_id],
                        'total_global_tps': int(global_config['global_tps']),
                        'active_campaigns': len(self.active_campaigns),
                        'worker_running': self.worker_task is not None and not self.worker_task.done(),
                    }
                    for campaign_id in sorted(self.active_campaigns)
                ],
            },
        }


sender = Sender()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await sender.start()
    try:
        yield
    finally:
        await sender.stop()


app = FastAPI(title='SMS Sender', version='2.0.0', lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={'success': False, 'detail': 'Invalid request body'})


@app.post('/sender/start', status_code=202)
async def sender_start(payload: CampaignRequest) -> Any:
    campaign_id = payload.campaign_id
    if campaign_id in sender.active_campaigns:
        return JSONResponse(
            status_code=409,
            content={'success': False, 'detail': 'Campaign is already running'},
        )
    try:
        activation_response = await sender.activate_campaign(campaign_id)
        campaign_response = await sender.start_campaign(campaign_id)
        sender.active_campaigns[campaign_id] = {
            'round_number': payload.round_number,
            'registered_at': iso_now(),
        }
        sender.ensure_worker()
        global_config = await sender.fetch_active_config('global-tps-config', 'global_tps')
        smsc_config = await sender.load_smsc_config()
        allocations = allocate_tps(
            int(global_config['global_tps']),
            list(sender.active_campaigns),
            int(smsc_config['rate_limit_per_second']),
        )
        return {
            'success': True,
            'message': 'Campaign started',
            'data': {
                'campaign_id': campaign_id,
                'round_number': payload.round_number,
                'status': 'active',
                'execution_status': 'PROCESSING',
                'allocated_tps': allocations[campaign_id],
                'total_global_tps': int(global_config['global_tps']),
                'active_campaigns': len(sender.active_campaigns),
            },
            'campaign_response': campaign_response,
            'activation_response': activation_response,
        }
    except Exception as exc:
        sender.active_campaigns.pop(campaign_id, None)
        return JSONResponse(status_code=400, content={'success': False, 'detail': str(exc)})


@app.post('/sender/stop')
async def sender_stop(payload: CampaignStopRequest) -> Any:
    campaign_id = payload.campaign_id
    if campaign_id not in sender.active_campaigns:
        return JSONResponse(
            status_code=404,
            content={'success': False, 'detail': 'Campaign is not running'},
        )
    try:
        campaign_response = await sender.pause_campaign(campaign_id)
        active_round = sender.active_campaigns[campaign_id]['round_number']
        sender.active_campaigns.pop(campaign_id, None)
        pending_count = await sender.pending_count(campaign_id, round_number=active_round)
        sent_count = await sender.pending_count(
            campaign_id,
            round_number=active_round,
            status_filter=('SENT',),
        )
        return {
            'success': True,
            'message': 'Campaign stopped',
            'data': {
                'campaign_id': campaign_id,
                'round_number': payload.round_number,
                'status': 'paused',
                'execution_status': 'PAUSED',
                'sent_count': sent_count,
                'pending_count': pending_count,
                'timestamp': iso_now(),
            },
            'campaign_response': campaign_response,
        }
    except Exception as exc:
        return JSONResponse(status_code=400, content={'success': False, 'detail': str(exc)})


@app.get('/sender/status/{campaign_id}')
async def sender_status(campaign_id: int) -> Any:
    try:
        return await sender.status_for_campaign(campaign_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/sender/status')
async def sender_status_all() -> Any:
    try:
        return await sender.status_all()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get('/health')
async def health() -> Any:
    try:
        global_config, addresses_config, smsc_config, _ = await sender.load_tick_config()
        return {
            'success': True,
            'worker_running': sender.worker_task is not None and not sender.worker_task.done(),
            'active_campaigns': sorted(sender.active_campaigns),
            'global_tps_config_id': global_config['id'],
            'global_tps': global_config['global_tps'],
            'n_addresses_config_id': addresses_config['id'],
            'max_addresses_per_request': addresses_config['max_addresses_per_request'],
            'smsc_config_id': smsc_config['id'],
            'smsc_url': f"{smsc_config['base_url'].rstrip('/')}/{smsc_config['send_endpoint'].lstrip('/')}",
            'kafka_connected': sender.kafka_connected,
            'last_report': sender.last_report,
        }
    except Exception as exc:
        return JSONResponse(status_code=503, content={'success': False, 'detail': f'DB/config error: {exc}'})


@app.post('/run-once')
async def run_once() -> Any:
    try:
        report = await sender.run_once()
        return {'success': report['success'], 'reports': report.get('reports', [])}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
