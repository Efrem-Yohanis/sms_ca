import asyncio
import logging
import os
import random
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import AliasChoices, AnyHttpUrl, BaseModel, Field

logger = logging.getLogger('smsc_mock')

DATABASE_PATH = os.getenv(
    'SMSC_MOCK_DATABASE',
    os.path.join(os.path.dirname(__file__), 'smsc_mock.sqlite3'),
)
QUEUE_MAX_SIZE = int(os.getenv('SMSC_QUEUE_MAX_SIZE', '50000'))
BATCH_SIZE = int(os.getenv('SMSC_BATCH_SIZE', '1000'))
FLUSH_INTERVAL_SECONDS = float(os.getenv('SMSC_FLUSH_INTERVAL_SECONDS', '0.01'))

# --- Delivery simulation -----------------------------------------------
# Real SMSCs don't deliver instantly or uniformly: transit time varies, and
# a slice of traffic always ends up UNDELIV/EXPIRED/REJECTD rather than
# DELIVRD. These settings let you tune how "real" the mock behaves.
MIN_DELIVERY_DELAY_SECONDS = float(os.getenv('SMSC_MIN_DELIVERY_DELAY_SECONDS', '1.0'))
MAX_DELIVERY_DELAY_SECONDS = float(os.getenv('SMSC_MAX_DELIVERY_DELAY_SECONDS', '5.0'))

# Final-status weights. Don't need to sum to 1 — they're normalized.
DELIVRD_WEIGHT = float(os.getenv('SMSC_DELIVRD_WEIGHT', '0.92'))
UNDELIV_WEIGHT = float(os.getenv('SMSC_UNDELIV_WEIGHT', '0.04'))
EXPIRED_WEIGHT = float(os.getenv('SMSC_EXPIRED_WEIGHT', '0.02'))
REJECTD_WEIGHT = float(os.getenv('SMSC_REJECTD_WEIGHT', '0.02'))

# Throughput throttling, like a real SMSC enforcing a negotiated TPS
# (transactions per second) cap on a bind/system_id.
MAX_TPS = float(os.getenv('SMSC_MAX_TPS', '200'))
TPS_BURST_CAPACITY = float(os.getenv('SMSC_TPS_BURST_CAPACITY', str(MAX_TPS)))

# Webhook (DLR) delivery
DLR_TIMEOUT_SECONDS = float(os.getenv('SMSC_DLR_TIMEOUT_SECONDS', '5.0'))
DLR_MAX_ATTEMPTS = int(os.getenv('SMSC_DLR_MAX_ATTEMPTS', '3'))
DLR_RETRY_BACKOFF_SECONDS = float(os.getenv('SMSC_DLR_RETRY_BACKOFF_SECONDS', '2.0'))

FinalStatus = Literal['DELIVRD', 'UNDELIV', 'EXPIRED', 'REJECTD']

# (err_code, human reason) options per final status — mirrors how a real
# network returns a handful of distinct reasons per outcome, not just one.
REASON_CODES: dict[FinalStatus, list[tuple[str, str]]] = {
    'DELIVRD': [('000', 'Delivered')],
    'UNDELIV': [
        ('008', 'Absent Subscriber'),
        ('006', 'Handset Memory Full'),
        ('020', 'Network Error'),
        ('028', 'Unknown Subscriber'),
    ],
    'EXPIRED': [('001', 'Validity Period Expired')],
    'REJECTD': [
        ('002', 'Rejected by Network'),
        ('017', 'Destination Blocked'),
    ],
}


class SmsRequest(BaseModel):
    message_id: str | None = Field(default=None, max_length=100)
    campaign_id: int = Field(gt=0)
    sender_id: str = Field(min_length=1, max_length=11)
    receiver: str = Field(
        min_length=1,
        max_length=20,
        validation_alias=AliasChoices('receiver', 'recipient'),
    )
    message_content: str = Field(min_length=1)
    # Where to POST the delivery report once the simulated delivery completes.
    callback_url: AnyHttpUrl | None = Field(default=None)


class AcceptedResponse(BaseModel):
    success: bool
    status: str
    provider_message_id: str
    message_id: str
    segment_count: int


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


def smpp_date(iso_timestamp: str) -> str:
    """Format an ISO timestamp as an SMPP-style YYMMDDhhmm string."""
    dt = datetime.fromisoformat(iso_timestamp)
    return dt.strftime('%y%m%d%H%M')


def pick_final_status() -> FinalStatus:
    statuses: list[FinalStatus] = ['DELIVRD', 'UNDELIV', 'EXPIRED', 'REJECTD']
    weights = [DELIVRD_WEIGHT, UNDELIV_WEIGHT, EXPIRED_WEIGHT, REJECTD_WEIGHT]
    return random.choices(statuses, weights=weights, k=1)[0]


class TokenBucket:
    """Simulates a real SMSC's per-account TPS (throughput) limit."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated_at = time.monotonic()
        self.lock = asyncio.Lock()

    async def try_acquire(self, amount: float = 1.0) -> bool:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.updated_at
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.updated_at = now
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False


class SmsStore:
    """
    Owns the single SQLite writer connection. All writes (the initial
    ACCEPTED insert and the later final-status update) flow through one
    asyncio.Queue and are drained sequentially by _writer(), so there is
    never more than one writer touching the database at a time.
    """

    def __init__(self, path: str):
        self.path = path
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.writer_task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()
        self.inserted = 0
        self.updated = 0
        self.http_client: httpx.AsyncClient | None = None
        self._delivery_tasks: set[asyncio.Task] = set()
        self.tps_bucket = TokenBucket(rate=MAX_TPS, capacity=TPS_BURST_CAPACITY)

    def initialize(self) -> None:
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA synchronous=NORMAL')
            connection.execute('''
                CREATE TABLE IF NOT EXISTS accepted_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    provider_message_id TEXT NOT NULL UNIQUE,
                    campaign_id INTEGER,
                    sender_id TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message_content TEXT NOT NULL,
                    segment_count INTEGER NOT NULL DEFAULT 1,
                    callback_url TEXT,
                    status TEXT NOT NULL DEFAULT 'ACCEPTED',
                    err_code TEXT,
                    error_reason TEXT,
                    received_at TEXT NOT NULL,
                    delivered_at TEXT,
                    dlr_sent INTEGER NOT NULL DEFAULT 0,
                    dlr_attempts INTEGER NOT NULL DEFAULT 0,
                    dlr_last_error TEXT
                )
            ''')
            connection.execute('''
                CREATE INDEX IF NOT EXISTS accepted_messages_campaign_idx
                ON accepted_messages (campaign_id)
            ''')

    async def start(self) -> None:
        self.initialize()
        self.stop_event.clear()
        self.http_client = httpx.AsyncClient(timeout=DLR_TIMEOUT_SECONDS)
        self.writer_task = asyncio.create_task(self._writer())

    async def stop(self) -> None:
        if self._delivery_tasks:
            await asyncio.gather(*list(self._delivery_tasks), return_exceptions=True)

        self.stop_event.set()
        if self.writer_task:
            await self.writer_task
            self.writer_task = None

        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

    async def _enqueue(self, item: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull as exc:
            raise RuntimeError('SMSC mock queue is full') from exc

    async def accept(self, row: dict[str, Any]) -> None:
        """Enqueue the initial ACCEPTED insert and schedule delivery simulation."""
        await self._enqueue({'op': 'insert', **row})
        task = asyncio.create_task(self._simulate_delivery(row))
        self._delivery_tasks.add(task)
        task.add_done_callback(self._delivery_tasks.discard)

    async def _simulate_delivery(self, row: dict[str, Any]) -> None:
        # Longer messages (more segments) realistically take a little
        # longer to fully transit the network than a single-segment SMS.
        base_delay = random.uniform(MIN_DELIVERY_DELAY_SECONDS, MAX_DELIVERY_DELAY_SECONDS)
        segment_jitter = (row['segment_count'] - 1) * random.uniform(0.1, 0.4)
        await asyncio.sleep(base_delay + segment_jitter)

        status = pick_final_status()
        err_code, reason = random.choice(REASON_CODES[status])
        delivered_at = now_iso()

        dlr_sent = 0
        dlr_attempts = 0
        dlr_last_error: str | None = None

        callback_url = row.get('callback_url')
        if callback_url:
            dlr_sent, dlr_attempts, dlr_last_error = await self._post_dlr(
                callback_url=callback_url,
                row=row,
                status=status,
                err_code=err_code,
                reason=reason,
                delivered_at=delivered_at,
            )

        try:
            await self._enqueue({
                'op': 'update',
                'message_id': row['message_id'],
                'status': status,
                'err_code': err_code,
                'error_reason': reason,
                'delivered_at': delivered_at,
                'dlr_sent': dlr_sent,
                'dlr_attempts': dlr_attempts,
                'dlr_last_error': dlr_last_error,
            })
        except RuntimeError:
            logger.error('Queue full: could not persist final status for %s', row['message_id'])

    async def _post_dlr(
        self, callback_url: str, row: dict[str, Any], status: FinalStatus,
        err_code: str, reason: str, delivered_at: str,
    ) -> tuple[int, int, str | None]:
        dlr_text = (
            f"id:{row['message_id']} sub:001 dlvrd:{'001' if status == 'DELIVRD' else '000'} "
            f"submit date:{smpp_date(row['received_at'])} done date:{smpp_date(delivered_at)} "
            f"stat:{status} err:{err_code} text:{row['message_content'][:20]}"
        )
        payload = {
            'message_id': row['message_id'],
            'provider_message_id': row['provider_message_id'],
            'campaign_id': row['campaign_id'],
            'receiver': row['recipient'],
            'status': status,
            'err_code': err_code,
            'error_reason': reason,
            'segment_count': row['segment_count'],
            'delivered_at': delivered_at,
            'dlr_text': dlr_text,
        }

        assert self.http_client is not None
        last_error: str | None = None
        for attempt in range(1, DLR_MAX_ATTEMPTS + 1):
            try:
                response = await self.http_client.post(callback_url, json=payload)
                response.raise_for_status()
                return 1, attempt, None
            except httpx.HTTPError as exc:
                last_error = str(exc)
                logger.warning(
                    'DLR webhook attempt %s/%s failed for %s: %s',
                    attempt, DLR_MAX_ATTEMPTS, row['message_id'], exc,
                )
                if attempt < DLR_MAX_ATTEMPTS:
                    await asyncio.sleep(DLR_RETRY_BACKOFF_SECONDS * attempt)

        return 0, DLR_MAX_ATTEMPTS, last_error

    async def _writer(self) -> None:
        connection = sqlite3.connect(self.path)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=NORMAL')
        try:
            while not self.stop_event.is_set() or not self.queue.empty():
                batch = await self._next_batch()
                if not batch:
                    continue

                inserts = [item for item in batch if item['op'] == 'insert']
                updates = [item for item in batch if item['op'] == 'update']

                if inserts:
                    cursor = connection.executemany('''
                        INSERT OR IGNORE INTO accepted_messages (
                            message_id, provider_message_id, campaign_id,
                            sender_id, recipient, message_content, segment_count,
                            callback_url, status, received_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACCEPTED', ?)
                    ''', [
                        (
                            row['message_id'], row['provider_message_id'],
                            row['campaign_id'], row['sender_id'], row['recipient'],
                            row['message_content'], row['segment_count'],
                            row.get('callback_url'), row['received_at'],
                        )
                        for row in inserts
                    ])
                    connection.commit()
                    self.inserted += cursor.rowcount

                if updates:
                    connection.executemany('''
                        UPDATE accepted_messages
                        SET status = ?, err_code = ?, error_reason = ?,
                            delivered_at = ?, dlr_sent = ?,
                            dlr_attempts = ?, dlr_last_error = ?
                        WHERE message_id = ?
                    ''', [
                        (
                            item['status'], item['err_code'], item['error_reason'],
                            item['delivered_at'], item['dlr_sent'],
                            item['dlr_attempts'], item['dlr_last_error'],
                            item['message_id'],
                        )
                        for item in updates
                    ])
                    connection.commit()
                    self.updated += len(updates)
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
        while len(batch) < BATCH_SIZE:
            try:
                batch.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return batch

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            cursor = connection.execute(
                'SELECT * FROM accepted_messages WHERE message_id = ?', (message_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            connection.close()


store = SmsStore(DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await store.start()
    yield
    await store.stop()


app = FastAPI(
    title='Local SMSC Mock',
    version='2.0.0',
    description=(
        'Simulates a real SMPP-style SMSC: submit acceptance, TPS throttling, '
        'randomized transit delay, realistic final delivery statuses '
        '(DELIVRD/UNDELIV/EXPIRED/REJECTD) with SMPP-style error codes, '
        'and webhook delivery reports (DLRs).'
    ),
    lifespan=lifespan,
)


@app.get('/health')
async def health() -> dict[str, Any]:
    return {
        'success': True,
        'status': 'ok',
        'queue_depth': store.queue.qsize(),
        'inserted': store.inserted,
        'updated': store.updated,
        'pending_deliveries': len(store._delivery_tasks),
        'tps_tokens_available': round(store.tps_bucket.tokens, 1),
    }


async def _build_row(payload: SmsRequest) -> dict[str, Any]:
    message_id = payload.message_id or f'msg_{uuid.uuid4().hex}'
    provider_message_id = f'smsc_{uuid.uuid4().hex}'
    return {
        'message_id': message_id,
        'provider_message_id': provider_message_id,
        'campaign_id': payload.campaign_id,
        'sender_id': payload.sender_id,
        'recipient': payload.receiver,
        'message_content': payload.message_content,
        'segment_count': compute_segments(payload.message_content),
        'callback_url': str(payload.callback_url) if payload.callback_url else None,
        'received_at': now_iso(),
    }


@app.post('/api/send', response_model=AcceptedResponse, status_code=200)
async def send_sms(payload: SmsRequest) -> AcceptedResponse:
    if not await store.tps_bucket.try_acquire(1):
        raise HTTPException(
            status_code=429,
            detail='ESME_RTHROTTLED: submit throughput exceeded, retry shortly',
        )

    row = await _build_row(payload)
    try:
        await store.accept(row)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return AcceptedResponse(
        success=True,
        status='ACCEPTED',
        provider_message_id=row['provider_message_id'],
        message_id=row['message_id'],
        segment_count=row['segment_count'],
    )


@app.post('/api/send/batch', status_code=200)
async def send_batch(payloads: list[SmsRequest]) -> dict[str, Any]:
    if not payloads:
        raise HTTPException(status_code=400, detail='At least one message is required')
    if len(payloads) > BATCH_SIZE * 10:
        raise HTTPException(status_code=413, detail='Batch is too large')

    if not await store.tps_bucket.try_acquire(len(payloads)):
        raise HTTPException(
            status_code=429,
            detail='ESME_RTHROTTLED: submit throughput exceeded, retry shortly',
        )

    accepted = []
    for payload in payloads:
        row = await _build_row(payload)
        await store.accept(row)
        accepted.append({
            'message_id': row['message_id'],
            'provider_message_id': row['provider_message_id'],
            'status': 'ACCEPTED',
            'segment_count': row['segment_count'],
        })
    return {'success': True, 'accepted': len(accepted), 'messages': accepted}


@app.get('/api/messages/{message_id}')
async def get_message(message_id: str) -> dict[str, Any]:
    row = store.get_message(message_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Unknown message_id')
    return {'success': True, 'message': row}