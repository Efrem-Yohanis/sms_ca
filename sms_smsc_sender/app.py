import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time as clock_time, timezone
from typing import Any

import requests
from fastapi import FastAPI, HTTPException

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv(
    'SMSC_SENDER_DATABASE',
    os.path.join(BASE_DIR, 'sms_campign', 'db.sqlite3'),
)
SMSC_CONFIG_ID = os.getenv('SMSC_SENDER_CONFIG_ID')
DJANGO_API_BASE_URL = os.getenv('SMSC_SENDER_DJANGO_API', 'http://127.0.0.1:8000/api/v1').rstrip('/')
SCHEDULER_INTERVAL_SECONDS = int(os.getenv('SMSC_SENDER_SCHEDULER_INTERVAL', '60'))
RUN_WORKER = os.getenv('SMSC_SENDER_RUN_WORKER', 'false').lower() in {'1', 'true', 'yes'}
DLR_CALLBACK_URL = os.getenv(
    'SMSC_SENDER_DLR_CALLBACK_URL',
    f'{DJANGO_API_BASE_URL}/delivery-reports/callback/',
)


class Sender:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.lock = asyncio.Lock()
        self.worker_task: asyncio.Task | None = None
        self.last_report: dict[str, Any] = {}
        self.scheduler = CampaignScheduler(database_path)

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

    def pending_by_campaign(self, capacity: int) -> dict[int, list[sqlite3.Row]]:
        connection = self.connection()
        try:
            rows = connection.execute(
                                '''SELECT message.* FROM sms_campaign_manager_messageobject AS message
                                     INNER JOIN sms_campaign_manager_campaign AS campaign
                                         ON campaign.id = message.campaign_id
                                     WHERE campaign.status IN ('active', 'in_progress')
                                         AND campaign.is_deleted = 0
                                         AND message.sent_status IN ('PENDING', 'FAILED')
                     AND send_attempts < ?
                                     ORDER BY message.campaign_id, message.id''',
                (self.config()['max_retries'],),
            ).fetchall()
        finally:
            connection.close()

        grouped: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(row['campaign_id'], []).append(row)
        campaign_ids = sorted(grouped)
        if not campaign_ids:
            return {}

        base, remainder = divmod(capacity, len(campaign_ids))
        return {
            campaign_id: grouped[campaign_id][:base + (index < remainder)]
            for index, campaign_id in enumerate(campaign_ids)
            if base + (index < remainder) > 0
        }

    @staticmethod
    def allocation_summary(groups: dict[int, list[sqlite3.Row]]) -> dict[str, int]:
        return {str(campaign_id): len(rows) for campaign_id, rows in groups.items()}

    async def run_once(self) -> dict[str, Any]:
        async with self.lock:
            config = self.config()
            capacity = int(config['rate_limit_per_second'])
            groups = self.pending_by_campaign(capacity)
            messages = [message for rows in groups.values() for message in rows]
            if not messages:
                report = {
                    'success': True,
                    'sent': 0,
                    'failed': 0,
                    'retried': 0,
                    'removed': 0,
                    'campaigns': 0,
                    'allocated': {},
                }
                self.last_report = report
                return report

            workers = min(capacity, int(os.getenv('SMSC_SENDER_WORKERS', '100')))
            semaphore = asyncio.Semaphore(workers)

            async def submit(message: sqlite3.Row) -> dict[str, Any]:
                async with semaphore:
                    return await asyncio.to_thread(self.send_one, config, message)

            outcomes = await asyncio.gather(
                *(submit(message) for message in messages),
                return_exceptions=False,
            )
            report = {
                'success': True,
                'sent': 0,
                'failed': 0,
                'retried': 0,
                'removed': 0,
                'campaigns': len(groups),
                'allocated': self.allocation_summary(groups),
                'errors': [],
            }
            for outcome in outcomes:
                result = self.record_outcome(outcome, config)
                for key in ('sent', 'failed', 'retried', 'removed'):
                    report[key] += result[key]
                if result.get('error'):
                    report['errors'].append(result['error'])
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
            body = outcome['body']
            provider_id = str(body.get('provider_message_id', ''))
            provider_status = str(body.get('status', 'FAILED'))
            sent_status = 'ACCEPTED' if outcome['accepted'] else 'FAILED'

            connection.execute('BEGIN IMMEDIATE')
            connection.execute(
                '''INSERT INTO sms_campaign_manager_sentrecord
                   (campaign_id, channel_id, message_object_id, msisdn, batch_id,
                    submitted_at, sent_status, provider_message_id, provider_status,
                    provider_response, error_message, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    message['campaign_id'], message['channel_id'], message['id'],
                    message['recipient'], message['batch_id'], now, sent_status,
                    provider_id, provider_status, json.dumps(body), outcome['error'], now, now,
                ),
            )

            if outcome['accepted'] or attempts >= int(config['max_retries']):
                connection.execute(
                    'DELETE FROM sms_campaign_manager_messageobject WHERE id = ?',
                    (message['id'],),
                )
                removed = 1
            else:
                connection.execute(
                    '''UPDATE sms_campaign_manager_messageobject
                       SET sent_status = 'FAILED', send_attempts = ?,
                           last_error = ?, failed_at = ?, updated_at = ?
                       WHERE id = ?''',
                    (attempts, outcome['error'], now, now, message['id']),
                )
                removed = 0
            connection.commit()

            if outcome['accepted']:
                return {'sent': 1, 'failed': 0, 'retried': 0, 'removed': removed}
            return {
                'sent': 0,
                'failed': 1,
                'retried': int(attempts < int(config['max_retries'])),
                'removed': removed,
                'error': outcome['error'],
            }
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def worker(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.scheduler.run_once()
                await self.run_once()
            except Exception as exc:
                self.last_report = {'success': False, 'error': str(exc)}
            delay = max(0.0, SCHEDULER_INTERVAL_SECONDS - (time.monotonic() - started))
            await asyncio.sleep(delay or 0.01)


class CampaignScheduler:
    """Synchronize scheduled campaign state through the Django API."""

    def __init__(self, database_path: str):
        self.database_path = database_path
        self.last_report: dict[str, Any] = {}

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=30000')
        return connection

    def due_campaigns(self) -> list[sqlite3.Row]:
        connection = self.connection()
        try:
            return connection.execute(
                '''SELECT campaign.id, campaign.status, schedule.schedule_type,
                          schedule.start_date, schedule.end_date,
                          schedule.run_days, schedule.time_windows,
                          schedule.schedule_status, schedule.is_active
                   FROM sms_campaign_manager_campaign AS campaign
                   INNER JOIN sms_campaign_manager_schedule AS schedule
                     ON schedule.campaign_id = campaign.id
                   WHERE campaign.is_deleted = 0
                     AND schedule.is_active = 1''',
            ).fetchall()
        finally:
            connection.close()

    @staticmethod
    def is_running_now(row: sqlite3.Row, current: datetime) -> bool:
        current_date = current.date()
        start = date.fromisoformat(row['start_date'])
        end = date.fromisoformat(row['end_date']) if row['end_date'] else None
        if current_date < start or (end and current_date > end):
            return False
        if row['schedule_status'] != 'active':
            return False
        windows = json.loads(row['time_windows'] or '[]')
        if windows:
            current_time = current.time().replace(tzinfo=None)
            in_window = any(
                clock_time.fromisoformat(window['start']) <= current_time < clock_time.fromisoformat(window['end'])
                for window in windows
            )
            if not in_window:
                return False
        if row['schedule_type'] == 'once':
            return current_date == start
        if row['schedule_type'] == 'daily':
            return True
        if row['schedule_type'] == 'weekly':
            return current_date.weekday() in (json.loads(row['run_days'] or '[]'))
        if row['schedule_type'] == 'monthly':
            return current_date.day == start.day
        return False

    def call_campaign_api(self, campaign_id: int, action: str) -> dict[str, Any]:
        response = requests.post(
            f'{DJANGO_API_BASE_URL}/campaigns/{campaign_id}/{action}/',
            json={},
            timeout=10,
        )
        try:
            body = response.json()
        except ValueError:
            body = {'raw': response.text[:500]}
        if response.status_code not in (200, 201):
            raise RuntimeError(f'{action} campaign {campaign_id} failed: HTTP {response.status_code}: {body}')
        return body

    async def run_once(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        started: list[int] = []
        stopped: list[int] = []
        errors: list[str] = []
        for row in self.due_campaigns():
            running = self.is_running_now(row, now)
            try:
                if running and row['status'] == 'draft':
                    self.call_campaign_api(row['id'], 'activate')
                    started.append(row['id'])
                elif not running and row['status'] in ('active', 'in_progress'):
                    self.call_campaign_api(row['id'], 'cancel')
                    stopped.append(row['id'])
            except (requests.RequestException, RuntimeError, ValueError, TypeError) as exc:
                errors.append(str(exc))
        self.last_report = {
            'success': not errors,
            'started': started,
            'stopped': stopped,
            'errors': errors,
        }
        return self.last_report


sender = Sender(DATABASE_PATH)
scheduler = sender.scheduler


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
        'scheduler_interval_seconds': SCHEDULER_INTERVAL_SECONDS,
        'scheduler_report': scheduler.last_report,
    }


@app.post('/run-once')
async def run_once() -> dict[str, Any]:
    try:
        schedule_report = await scheduler.run_once()
        send_report = await sender.run_once()
        return {'success': schedule_report['success'] and send_report['success'], 'scheduler': schedule_report, 'sender': send_report}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post('/scheduler/run-once')
async def scheduler_run_once() -> dict[str, Any]:
    try:
        return await scheduler.run_once()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
