import asyncio
import base64
import binascii
import hmac
import json
import logging
import os
import random
import sqlite3
import time
from contextlib import contextmanager
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger('smsc_mock')

DATABASE_PATH = os.getenv(
    'SMSC_MOCK_DATABASE',
    os.path.join(os.path.dirname(__file__), 'smsc_mock.sqlite3'),
)
QUEUE_MAX_SIZE = int(os.getenv('SMSC_MOCK_QUEUE_MAX', '50000'))
BATCH_SIZE = int(os.getenv('SMSC_MOCK_BATCH_SIZE', '1000'))
FLUSH_INTERVAL_SECONDS = float(os.getenv('SMSC_MOCK_FLUSH_INTERVAL', '0.01'))

MIN_DELAY_SECONDS = float(os.getenv('SMSC_MOCK_MIN_DELAY_SECONDS', '1.0'))
MAX_DELAY_SECONDS = float(os.getenv('SMSC_MOCK_MAX_DELAY_SECONDS', '5.0'))
DELIVRD_WEIGHT = float(os.getenv('SMSC_MOCK_DELIVRD_WEIGHT', '0.92'))
UNDELIV_WEIGHT = float(os.getenv('SMSC_MOCK_UNDELIV_WEIGHT', '0.04'))
EXPIRED_WEIGHT = float(os.getenv('SMSC_MOCK_EXPIRED_WEIGHT', '0.02'))
REJECTD_WEIGHT = float(os.getenv('SMSC_MOCK_REJECTD_WEIGHT', '0.02'))
MAX_TPS = float(os.getenv('SMSC_MOCK_MAX_TPS', '5000'))
TPS_BURST = float(os.getenv('SMSC_MOCK_TPS_BURST', '5000'))
DLR_CALLBACK_URL = os.getenv('SMSC_MOCK_DLR_CALLBACK_URL', '').strip()
MOCK_USERNAME = os.getenv('SMSC_MOCK_USERNAME', '')
MOCK_PASSWORD = os.getenv('SMSC_MOCK_PASSWORD', '')
DLR_RETRIES = int(os.getenv('SMSC_MOCK_DLR_RETRIES', '3'))
DLR_RETRY_BACKOFF = float(os.getenv('SMSC_MOCK_DLR_RETRY_BACKOFF', '2.0'))
LOG_LEVEL = os.getenv('SMSC_MOCK_LOG_LEVEL', 'INFO').upper()

logging.basicConfig(level=LOG_LEVEL)

FinalStatus = Literal['DELIVRD', 'UNDELIV', 'EXPIRED', 'REJECTD', 'UNKNOWN']


class Destination(BaseModel):
    id: str = Field(min_length=7, max_length=20, pattern=r'^\d+$')


class NamedValue(BaseModel):
    name: str = Field(min_length=1, max_length=150)


class OnionSubmitRequest(BaseModel):
    shortMessage: str = Field(min_length=1)
    messageType: Literal['TEXT', 'BIN'] = 'TEXT'
    destAddr: list[Destination] = Field(min_length=1, max_length=10000)
    sourceAddr: NamedValue
    servicetag: NamedValue | None = None
    servicetype: NamedValue | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_segments(message_content: str) -> int:
    """
    Rough GSM-7 vs UCS-2 segmentation, same as a real SMSC's submit_sm
    handling: 160/153 chars per segment for GSM-7 (single/concatenated),
    70/67 for anything needing UCS-2 (non-ASCII).
    """
    length = len(message_content)
    if message_content.isascii():
        if length <= 160:
            return 1
        return -(-length // 153)  # ceil
    if length <= 70:
        return 1
    return -(-length // 67)


def done_date() -> str:
    return datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')


def pick_final_status() -> FinalStatus:
    statuses: list[FinalStatus] = ['DELIVRD', 'UNDELIV', 'EXPIRED', 'REJECTD']
    weights = [DELIVRD_WEIGHT, UNDELIV_WEIGHT, EXPIRED_WEIGHT, REJECTD_WEIGHT]
    return random.choices(statuses, weights=weights, k=1)[0]


class TokenBucket:
    """A file-locked token bucket shared by all Uvicorn worker processes."""

    def __init__(self, rate: float, capacity: float, state_path: str):
        self.rate = rate
        self.capacity = capacity
        self.state_path = state_path

    async def try_acquire(self, amount: float = 1.0) -> bool:
        return await asyncio.to_thread(self._try_acquire, amount)

    def _try_acquire(self, amount: float) -> bool:
        os.makedirs(os.path.dirname(self.state_path) or '.', exist_ok=True)
        with open(self.state_path, 'a+', encoding='utf-8') as state_file:
            if os.name == 'nt':
                import msvcrt

                state_file.seek(0, os.SEEK_END)
                if state_file.tell() == 0:
                    state_file.write(' ')
                    state_file.flush()
                state_file.seek(0)
                msvcrt.locking(state_file.fileno(), msvcrt.LK_LOCK, 1)
                def unlock():
                    state_file.seek(0)
                    msvcrt.locking(state_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(state_file.fileno(), fcntl.LOCK_EX)
                unlock = lambda: fcntl.flock(state_file.fileno(), fcntl.LOCK_UN)
            try:
                state_file.seek(0)
                try:
                    state = json.load(state_file)
                    tokens = float(state['tokens'])
                    updated_at = float(state['updated_at'])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    tokens = self.capacity
                    updated_at = time.time()

                now = time.time()
                tokens = min(self.capacity, tokens + max(now - updated_at, 0) * self.rate)
                if tokens < amount:
                    allowed = False
                else:
                    tokens -= amount
                    allowed = True

                state_file.seek(0)
                state_file.truncate()
                json.dump({'tokens': tokens, 'updated_at': now}, state_file)
                state_file.flush()
                return allowed
            finally:
                unlock()

    def available(self) -> float:
        try:
            with open(self.state_path, encoding='utf-8') as state_file:
                state = json.load(state_file)
            tokens = float(state['tokens'])
            elapsed = max(time.time() - float(state['updated_at']), 0)
            return min(self.capacity, tokens + elapsed * self.rate)
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return self.capacity


class SmsStore:
    """Batches queued message inserts and DLR updates through SQLite WAL."""

    def __init__(self, path: str):
        self.path = path
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.writer_task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()
        self.accepted_total = 0
        self.delivered_total = 0
        self.http_client: httpx.AsyncClient | None = None
        self._delivery_tasks: set[asyncio.Task] = set()
        self.tps_bucket = TokenBucket(
            rate=MAX_TPS,
            capacity=TPS_BURST,
            state_path=f'{path}.rate-limit',
        )

    def initialize(self) -> None:
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=NORMAL')
            connection.execute('PRAGMA busy_timeout=30000')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    msisdn TEXT NOT NULL,
                    short_message TEXT NOT NULL,
                    source_addr TEXT NOT NULL,
                    servicetag TEXT,
                    servicetype TEXT,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    received_at TEXT NOT NULL,
                    delivered_at TEXT,
                    done_date TEXT,
                    callback_url TEXT,
                    dlr_sent INTEGER NOT NULL DEFAULT 0,
                    dlr_attempts INTEGER NOT NULL DEFAULT 0,
                    dlr_last_error TEXT
                )
            ''')
            connection.execute('''
                CREATE INDEX IF NOT EXISTS messages_message_id_idx ON messages (message_id)
            ''')
            connection.execute('''
                CREATE INDEX IF NOT EXISTS messages_msisdn_idx ON messages (msisdn)
            ''')
            connection.execute('''
                CREATE INDEX IF NOT EXISTS messages_status_idx ON messages (status)
            ''')
        connection.close()

    async def start(self) -> None:
        self.initialize()
        self.stop_event.clear()
        self.http_client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=100),
        )
        self.writer_task = asyncio.create_task(self._writer())

    async def stop(self) -> None:
        for task in list(self._delivery_tasks):
            task.cancel()
        if self._delivery_tasks:
            await asyncio.gather(*self._delivery_tasks, return_exceptions=True)
        await self.queue.join()
        self.stop_event.set()
        if self.writer_task:
            await self.writer_task
            self.writer_task = None

        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

    async def _enqueue(self, item: dict[str, Any]) -> None:
        await self.queue.put(item)

    async def accept(self, row: dict[str, Any]) -> None:
        """Queue one accepted destination and schedule its independent DLR."""
        await self._enqueue({'op': 'insert', **row})
        task = asyncio.create_task(self._simulate_delivery(row))
        self._delivery_tasks.add(task)
        task.add_done_callback(self._delivery_tasks.discard)

    async def _simulate_delivery(self, row: dict[str, Any]) -> None:
        await asyncio.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
        status = pick_final_status()
        delivered_at = now_iso()
        report_done_date = done_date()

        dlr_sent = 0
        dlr_attempts = 0
        dlr_last_error: str | None = None

        if DLR_CALLBACK_URL:
            dlr_sent, dlr_attempts, dlr_last_error = await self._post_dlr(
                row=row,
                status=status,
                report_done_date=report_done_date,
            )
        else:
            dlr_last_error = 'SMSC_MOCK_DLR_CALLBACK_URL is not configured'

        await self._enqueue({
            'op': 'update',
            'message_id': row['message_id'],
            'status': status,
            'delivered_at': delivered_at,
            'done_date': report_done_date,
            'dlr_sent': dlr_sent,
            'dlr_attempts': dlr_attempts,
            'dlr_last_error': dlr_last_error,
        })
        if dlr_sent:
            self.delivered_total += 1

    async def _post_dlr(
        self,
        row: dict[str, Any],
        status: FinalStatus,
        report_done_date: str,
    ) -> tuple[int, int, str | None]:
        payload = {
            'event': 'Delivery receipt received',
            'msisdn': row['msisdn'],
            'messageId': row['message_id'],
            'status': status,
            'doneDate': report_done_date,
        }

        assert self.http_client is not None
        last_error: str | None = None
        for attempt in range(1, DLR_RETRIES + 1):
            try:
                response = await self.http_client.post(DLR_CALLBACK_URL, json=payload)
                if response.status_code != 200:
                    raise httpx.HTTPStatusError(
                        f'DLR receiver returned HTTP {response.status_code}',
                        request=response.request,
                        response=response,
                    )
                return 1, attempt, None
            except httpx.HTTPError as exc:
                last_error = str(exc)
                logger.warning('DLR attempt %s/%s failed for %s: %s', attempt, DLR_RETRIES, row['message_id'], exc)
                if attempt < DLR_RETRIES:
                    await asyncio.sleep(DLR_RETRY_BACKOFF * attempt)

        logger.error('DLR delivery exhausted retries for %s: %s', row['message_id'], last_error)
        return 0, DLR_RETRIES, last_error

    async def _writer(self) -> None:
        connection = sqlite3.connect(self.path)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=NORMAL')
        connection.execute('PRAGMA busy_timeout=30000')
        try:
            while not self.stop_event.is_set() or not self.queue.empty():
                batch = await self._next_batch()
                if not batch:
                    continue

                inserts = [item for item in batch if item['op'] == 'insert']
                updates = [item for item in batch if item['op'] == 'update']
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    if inserts:
                        cursor = connection.executemany('''
                            INSERT OR IGNORE INTO messages (
                                message_id, msisdn, short_message, source_addr,
                                servicetag, servicetype, status, received_at, callback_url
                            ) VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?, ?)
                        ''', [
                            (
                                row['message_id'], row['msisdn'], row['short_message'],
                                row['source_addr'], row['servicetag'], row['servicetype'],
                                row['received_at'], row['callback_url'],
                            )
                            for row in inserts
                        ])
                        self.accepted_total += cursor.rowcount
                    if updates:
                        connection.executemany('''
                            UPDATE messages
                            SET status = ?, delivered_at = ?, done_date = ?,
                                dlr_sent = ?, dlr_attempts = ?, dlr_last_error = ?
                            WHERE message_id = ?
                        ''', [
                            (
                                item['status'], item['delivered_at'], item['done_date'],
                                item['dlr_sent'], item['dlr_attempts'],
                                item['dlr_last_error'], item['message_id'],
                            )
                            for item in updates
                        ])
                    connection.commit()
                except Exception:
                    connection.rollback()
                    logger.exception('Failed to persist an SMSC mock write batch')
                finally:
                    for _ in batch:
                        self.queue.task_done()
        finally:
            connection.close()

    async def _next_batch(self) -> list[dict[str, Any]]:
        try:
            first = await asyncio.wait_for(
                self.queue.get(), timeout=FLUSH_INTERVAL_SECONDS,
            )
        except asyncio.TimeoutError:
            return []

        batch = [first]
        deadline = asyncio.get_running_loop().time() + FLUSH_INTERVAL_SECONDS
        while len(batch) < BATCH_SIZE:
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break
        return batch

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=30000')
        try:
            cursor = connection.execute(
                'SELECT * FROM messages WHERE message_id = ?', (message_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                'messageId': row['message_id'],
                'msisdn': row['msisdn'],
                'shortMessage': row['short_message'],
                'sourceAddr': row['source_addr'],
                'servicetag': row['servicetag'],
                'servicetype': row['servicetype'],
                'status': row['status'],
                'received_at': row['received_at'],
                'delivered_at': row['delivered_at'],
                'done_date': row['done_date'],
                'dlr_sent': row['dlr_sent'],
                'dlr_attempts': row['dlr_attempts'],
                'dlr_last_error': row['dlr_last_error'],
            }
        finally:
            connection.close()


store = SmsStore(DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await store.start()
    yield
    await store.stop()


app = FastAPI(
    title='Onion SMSC Mock',
    version='3.0.0',
    description='Development mock for the Onion SMSC submission and DLR contract.',
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    if any(error.get('type') == 'json_invalid' for error in exc.errors()):
        message = 'Invalid JSON'
    else:
        message = 'Invalid request body'
    return JSONResponse(
        status_code=400,
        content={'error': 'Bad request', 'message': message},
    )


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={'error': 'Unauthorized', 'message': 'Basic authentication required'},
        headers={'WWW-Authenticate': 'Basic'},
    )


def _authorized(authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, separator, token = authorization.partition(' ')
    if not separator or scheme.lower() != 'basic' or not token.strip():
        return False
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    if ':' not in decoded:
        return False
    username, password = decoded.split(':', 1)
    if not username and not password:
        return False
    if MOCK_USERNAME and MOCK_PASSWORD:
        return hmac.compare_digest(username, MOCK_USERNAME) and hmac.compare_digest(password, MOCK_PASSWORD)
    return True


def _new_message_id() -> str:
    return f'{int(time.time() * 1000)}{random.randint(0, 999999):06d}'


async def _build_row(
    payload: OnionSubmitRequest,
    msisdn: str,
    message_id: str,
) -> dict[str, Any]:
    return {
        'message_id': message_id,
        'msisdn': msisdn,
        'short_message': payload.shortMessage,
        'source_addr': payload.sourceAddr.name,
        'servicetag': payload.servicetag.name if payload.servicetag else None,
        'servicetype': payload.servicetype.name if payload.servicetype else None,
        'status': 'submitted',
        'received_at': now_iso(),
        'callback_url': DLR_CALLBACK_URL or None,
    }


@app.get('/health')
async def health() -> dict[str, Any]:
    return {
        'success': True,
        'status': 'ok',
        'queue_depth': store.queue.qsize(),
        'accepted_total': store.accepted_total,
        'delivered_total': store.delivered_total,
        'pending_deliveries': len(store._delivery_tasks),
        'tps_tokens_available': round(store.tps_bucket.available(), 1),
        'dlr_callback_url': DLR_CALLBACK_URL,
    }


@app.post('/onion/swift/duos', status_code=200)
async def submit_messages(request: Request) -> Any:
    if not _authorized(request.headers.get('authorization')):
        return _unauthorized()

    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
        return JSONResponse(
            status_code=400,
            content={'error': 'Bad request', 'message': 'Content-Type must be application/json'},
        )
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={'error': 'Bad request', 'message': 'Invalid JSON'},
        )
    try:
        payload = OnionSubmitRequest.model_validate(body)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={'error': 'Bad request', 'message': 'Invalid request body'},
        )

    amount = len(payload.destAddr)
    if not await store.tps_bucket.try_acquire(amount):
        return JSONResponse(
            status_code=503,
            content={
                'error': 'Service Unavailable',
                'message': 'Rate limit exceeded. Retry shortly.',
            },
        )

    response = []
    for destination in payload.destAddr:
        message_id = _new_message_id()
        row = await _build_row(payload, destination.id, message_id)
        await store.accept(row)
        response.append({
            'messageId': message_id,
            'msisdn': destination.id,
            'status': 'submitted',
        })
    return response


@app.get('/api/messages/{message_id}')
async def get_message(message_id: str) -> Any:
    row = store.get_message(message_id)
    if row is None:
        return JSONResponse(
            status_code=404,
            content={'error': 'Not Found', 'message': 'Unknown messageId'},
        )
    return row