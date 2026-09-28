import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from fastapi import FastAPI, HTTPException

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv(
    'SMSC_SENDER_DATABASE',
    os.path.join(BASE_DIR, 'sms_campign', 'db.sqlite3'),
)
SMSC_CONFIG_ID = os.getenv('SMSC_SENDER_CONFIG_ID')
RUN_WORKER = os.getenv('SMSC_SENDER_RUN_WORKER', 'false').lower() in {'1', 'true', 'yes'}
SENDER_INTERVAL_SECONDS = float(os.getenv('SMSC_SENDER_INTERVAL', '1'))
DLR_CALLBACK_URL = os.getenv(
    'SMSC_SENDER_DLR_CALLBACK_URL',
    'http://127.0.0.1:8092/api/v1/delivery-reports/callback/',
)
DJANGO_API_BASE_URL = os.getenv(
    'SMSC_SENDER_DJANGO_API_BASE_URL',
    'http://127.0.0.1:8000/api/v1',
).rstrip('/')


class Sender:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.lock = asyncio.Lock()
        self.worker_task: asyncio.Task | None = None
        self.last_report: dict[str, Any] = {"success": True, "campaigns": 0, "errors": []}
        self.active_campaigns: dict[int, dict[str, Any]] = {}

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=30000')
        return connection

    def config(self) -> sqlite3.Row:
        connection = self.connection()
        try:
            if SMSC_CONFIG_ID:
                row = connection.execute(
                    'SELECT * FROM sms_campaign_manager_smscconfig WHERE id = ?',
                    (int(SMSC_CONFIG_ID),),
                ).fetchone()
            else:
                row = connection.execute(
                    '''SELECT * FROM sms_campaign_manager_smscconfig
                       WHERE is_active = 1 ORDER BY is_default DESC, id LIMIT 1''',
                ).fetchone()
            if row is None:
                raise RuntimeError('No active SMSCConfig found.')
            return row
        finally:
            connection.close()

    def allocate_tps(self, campaign_count: int) -> dict[int, int]:
        if campaign_count <= 0:
            return {}
        config = self.config()
        global_tps = int(config['rate_limit_per_second'])
        base, remainder = divmod(global_tps, campaign_count)
        allocations: dict[int, int] = {}
        for index, campaign_id in enumerate(sorted(self.active_campaigns)):
            share = base + (1 if index < remainder else 0)
            allocations[campaign_id] = share
        return allocations

    def pending_by_campaign(self, campaign_id: int, allocated_tps: int) -> list[sqlite3.Row]:
        connection = self.connection()
        try:
            rows = connection.execute(
                '''SELECT message.*
                   FROM sms_campaign_manager_messageobject AS message
                   INNER JOIN sms_campaign_manager_campaign AS campaign
                       ON campaign.id = message.campaign_id
                   WHERE campaign.id = ?
                     AND campaign.status IN ('active', 'in_progress')
                     AND campaign.is_deleted = 0
                     AND message.sent_status IN ('PENDING', 'FAILED')
                     AND message.send_attempts < ?
                     AND (message.locked_until IS NULL OR message.locked_until < ?)
                   ORDER BY message.id ASC
                   LIMIT ?''',
                (
                    campaign_id,
                    int(self.config()['max_retries']),
                    datetime.now(timezone.utc).isoformat(),
                    max(1, allocated_tps),
                ),
            ).fetchall()
            return list(rows)
        finally:
            connection.close()

    def claim_batch(self, campaign_id: int, allocated_tps: int) -> list[sqlite3.Row]:
        messages = self.pending_by_campaign(campaign_id, allocated_tps)
        if not messages:
            return []

        batch_id = f'batch_{campaign_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}'
        worker_id = f'worker_{os.getpid()}_{uuid.uuid4().hex[:6]}'
        now = datetime.now(timezone.utc)
        lock_until = now + timedelta(minutes=5)

        connection = self.connection()
        try:
            connection.execute('BEGIN IMMEDIATE')
            message_ids = [message['id'] for message in messages]
            placeholders = ', '.join('?' for _ in message_ids)
            connection.execute(
                f'''UPDATE sms_campaign_manager_messageobject
                    SET batch_id = ?,
                        worker_id = ?,
                        sending_started_at = COALESCE(sending_started_at, ?),
                        locked_until = ?,
                        updated_at = ?
                    WHERE id IN ({placeholders})''',
                [batch_id, worker_id, now.isoformat(), lock_until.isoformat(), now.isoformat(), *message_ids],
            )
            rows = connection.execute(
                f'''SELECT * FROM sms_campaign_manager_messageobject WHERE id IN ({placeholders}) ORDER BY id''',
                message_ids,
            ).fetchall()
            connection.commit()
            return list(rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def allocation_summary(groups: dict[int, list[sqlite3.Row]]) -> dict[str, int]:
        return {str(campaign_id): len(rows) for campaign_id, rows in groups.items()}

    def apply_campaign_action(self, campaign_id: int, action: str) -> dict[str, Any]:
        endpoint = {'start': 'activate', 'stop': 'pause'}.get(action, action)
        url = f'{DJANGO_API_BASE_URL}/campaigns/{campaign_id}/{endpoint}/'
        try:
            response = requests.post(url, json={}, timeout=10)
            try:
                body = response.json()
            except ValueError:
                body = {'raw': response.text[:500]}
            if response.status_code in (200, 201, 400):
                return {'success': True, 'campaign_id': campaign_id, 'action': action, 'response': body}
            raise RuntimeError(f'Campaign {action} failed: HTTP {response.status_code}: {body}')
        except requests.RequestException as exc:
            raise RuntimeError(f'Campaign {action} failed for campaign {campaign_id}: {exc}') from exc

    def start_campaign(self, campaign_id: int, round_number: int = 1) -> dict[str, Any]:
        status = self.apply_campaign_action(campaign_id, 'start')
        self.active_campaigns[campaign_id] = {
            'started_at': datetime.now(timezone.utc).isoformat(),
            'round_number': round_number,
        }
        return {
            'success': True,
            'message': 'Campaign started',
            'data': {
                'campaign_id': campaign_id,
                'round_number': round_number,
                'status': 'active',
                'execution_status': 'PROCESSING',
                'allocated_tps': self.allocate_tps(len(self.active_campaigns)).get(campaign_id, 0),
                'total_global_tps': self.config()['rate_limit_per_second'],
                'active_campaigns': len(self.active_campaigns),
            },
            'campaign_response': status,
        }

    def stop_campaign(self, campaign_id: int, round_number: int = 1) -> dict[str, Any]:
        status = self.apply_campaign_action(campaign_id, 'stop')
        self.active_campaigns.pop(campaign_id, None)
        return {
            'success': True,
            'message': 'Campaign stopped',
            'data': {
                'campaign_id': campaign_id,
                'round_number': round_number,
                'status': 'paused',
                'execution_status': 'PAUSED',
                'active_campaigns': len(self.active_campaigns),
            },
            'campaign_response': status,
        }

    def run_once_for_campaign(self, campaign_id: int, allocated_tps: int) -> dict[str, Any]:
        config = self.config()
        messages = self.claim_batch(campaign_id, allocated_tps)
        if not messages:
            return {
                'success': True,
                'campaign_id': campaign_id,
                'sent': 0,
                'failed': 0,
                'retried': 0,
                'allocated_tps': allocated_tps,
                'batch_id': None,
                'worker_id': None,
            }

        workers = min(allocated_tps, max(1, int(os.getenv('SMSC_SENDER_WORKERS', '100'))))
        semaphore = asyncio.Semaphore(workers)

        async def submit(message: sqlite3.Row) -> dict[str, Any]:
            async with semaphore:
                return await asyncio.to_thread(self.send_one, config, message)

        async def run_async() -> list[dict[str, Any]]:
            return await asyncio.gather(*(submit(message) for message in messages), return_exceptions=False)

        outcomes = asyncio.get_event_loop().run_until_complete(run_async())
        batch_id = messages[0]['batch_id']
        worker_id = messages[0]['worker_id']
        report = {
            'success': True,
            'campaign_id': campaign_id,
            'batch_id': batch_id,
            'worker_id': worker_id,
            'allocated_tps': allocated_tps,
            'sent': 0,
            'failed': 0,
            'retried': 0,
            'errors': [],
        }
        for outcome in outcomes:
            result = self.record_outcome(outcome, config)
            report['sent'] += result['sent']
            report['failed'] += result['failed']
            report['retried'] += result['retried']
            if result.get('error'):
                report['errors'].append(result['error'])
        self.last_report = report
        return report

    async def run_once(self) -> dict[str, Any]:
        async with self.lock:
            if not self.active_campaigns:
                report = {'success': True, 'campaigns': 0, 'sent': 0, 'failed': 0, 'retried': 0, 'allocated': {}}
                self.last_report = report
                return report

            allocations = self.allocate_tps(len(self.active_campaigns))
            report = {
                'success': True,
                'campaigns': len(self.active_campaigns),
                'sent': 0,
                'failed': 0,
                'retried': 0,
                'allocated': {str(campaign_id): allocation for campaign_id, allocation in allocations.items()},
                'errors': [],
            }
            for campaign_id, allocated_tps in allocations.items():
                result = await asyncio.to_thread(self.run_once_for_campaign, campaign_id, allocated_tps)
                report['sent'] += result.get('sent', 0)
                report['failed'] += result.get('failed', 0)
                report['retried'] += result.get('retried', 0)
                report['errors'].extend(result.get('errors', []))
            self.last_report = report
            return report

    @staticmethod
    def send_one(config: sqlite3.Row, message: sqlite3.Row) -> dict[str, Any]:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        try:
            headers.update(json.loads(config['extra_headers'] or '{}'))
        except (TypeError, json.JSONDecodeError):
            pass

        payload = {
            'message_id': message['message_id'],
            'campaign_id': message['campaign_id'],
            'sender_id': message['sender_id'],
            'receiver': message['recipient'],
            'message_content': message['message_content'],
        }
        base_url = config['base_url'].rstrip('/')
        endpoint = config['send_endpoint'].strip() or '/api/send'
        url = f'{base_url}/{endpoint.lstrip("/")}'
        try:
            response = requests.request(
                config['http_method'] or 'POST',
                url,
                json=payload,
                headers=headers,
                timeout=(config['connect_timeout_seconds'], config['request_timeout_seconds']),
            )
            try:
                body = response.json()
            except ValueError:
                body = {'raw': response.text[:1000]}
            accepted = response.status_code in (200, 201) and body.get('status') in (None, 'ACCEPTED')
            return {
                'id': message['id'],
                'accepted': accepted,
                'body': body,
                'error': '' if accepted else f'HTTP {response.status_code}: {body}',
            }
        except requests.RequestException as exc:
            return {'id': message['id'], 'accepted': False, 'body': {}, 'error': str(exc)}

    def record_outcome(self, outcome: dict[str, Any], config: sqlite3.Row) -> dict[str, Any]:
        connection = self.connection()
        try:
            message = connection.execute(
                'SELECT * FROM sms_campaign_manager_messageobject WHERE id = ?',
                (outcome['id'],),
            ).fetchone()
            if message is None:
                return {'sent': 0, 'failed': 0, 'retried': 0, 'removed': 0}

            now = datetime.now(timezone.utc).isoformat()
            attempts = int(message['send_attempts']) + 1

            if outcome['accepted']:
                connection.execute(
                    '''UPDATE sms_campaign_manager_messageobject
                       SET sent_status = 'SENT', sent_at = ?, send_attempts = ?,
                           locked_until = NULL, last_error = '', updated_at = ?
                       WHERE id = ?''',
                    (now, attempts, now, message['id']),
                )
                connection.commit()
                return {'sent': 1, 'failed': 0, 'retried': 0, 'removed': 0}

            connection.execute(
                '''UPDATE sms_campaign_manager_messageobject
                   SET sent_status = 'FAILED', send_attempts = ?,
                       last_error = ?, failed_at = ?, locked_until = NULL, updated_at = ?
                   WHERE id = ?''',
                (attempts, outcome['error'], now, now, message['id']),
            )
            connection.commit()
            return {
                'sent': 0,
                'failed': 1,
                'retried': int(attempts < int(config['max_retries'])),
                'removed': 0,
                'error': outcome['error'],
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def worker(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as exc:
                self.last_report = {'success': False, 'error': str(exc)}
            await asyncio.sleep(SENDER_INTERVAL_SECONDS)


sender = Sender(DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if RUN_WORKER:
        sender.worker_task = asyncio.create_task(sender.worker())
    yield
    if sender.worker_task:
        sender.worker_task.cancel()
        try:
            await sender.worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title='SMS Campaign Sender',
    version='1.0.0',
    description='Standalone fair-TPS sender from Django MessageObject rows to an SMSC API.',
    lifespan=lifespan,
)


@app.get('/health')
async def health() -> dict[str, Any]:
    config = sender.config()
    return {
        'success': True,
        'database': DATABASE_PATH,
        'smsc_config_id': config['id'],
        'smsc_url': f"{config['base_url'].rstrip('/')}/{config['send_endpoint'].lstrip('/')}",
        'dlr_callback_url': DLR_CALLBACK_URL,
        'tps': config['rate_limit_per_second'],
        'last_report': sender.last_report,
        'worker_running': sender.worker_task is not None and not sender.worker_task.done(),
        'sender_interval_seconds': SENDER_INTERVAL_SECONDS,
    }


@app.post('/run-once')
async def run_once() -> dict[str, Any]:
    try:
        send_report = await asyncio.to_thread(sender.run_once)
        return {'success': send_report['success'], 'sender': send_report}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/sender/start')
async def sender_start(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    campaign_id = int(payload.get('campaign_id'))
    round_number = int(payload.get('round_number', 1))
    response = sender.start_campaign(campaign_id, round_number)
    if sender.worker_task is None or sender.worker_task.done():
        sender.worker_task = asyncio.create_task(sender.worker())
    return response


@app.post('/sender/stop')
async def sender_stop(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    campaign_id = int(payload.get('campaign_id'))
    round_number = int(payload.get('round_number', 1))
    return sender.stop_campaign(campaign_id, round_number)


@app.get('/sender/status/{campaign_id}')
async def sender_status(campaign_id: int) -> dict[str, Any]:
    connection = sender.connection()
    try:
        pending = connection.execute(
            '''SELECT COUNT(*) AS cnt
               FROM sms_campaign_manager_messageobject
               WHERE campaign_id = ? AND sent_status IN ('PENDING', 'FAILED')''',
            (campaign_id,),
        ).fetchone()['cnt']
        return {'success': True, 'campaign_id': campaign_id, 'pending_count': pending}
    finally:
        connection.close()


@app.post('/worker/start')
async def start_worker() -> dict[str, Any]:
    if sender.worker_task is None or sender.worker_task.done():
        sender.worker_task = asyncio.create_task(sender.worker())
    return {'success': True, 'worker_running': True}


@app.post('/worker/stop')
async def stop_worker() -> dict[str, Any]:
    if sender.worker_task:
        sender.worker_task.cancel()
        sender.worker_task = None
    return {'success': True, 'worker_running': False}
