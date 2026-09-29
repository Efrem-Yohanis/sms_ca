import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO').upper())
logger = logging.getLogger('dlr_receiver')

PORT = int(os.getenv('DLR_RECEIVER_PORT', '8003'))
KAFKA_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP', 'kafka:9092')
KAFKA_DELIVERY_TOPIC = os.getenv('KAFKA_DELIVERY_TOPIC', 'delivery-report')
DLR_QUEUE_MAX = int(os.getenv('DLR_QUEUE_MAX', '100000'))
DLR_BATCH_SIZE = int(os.getenv('DLR_BATCH_SIZE', '100'))
DLR_FLUSH_INTERVAL = float(os.getenv('DLR_FLUSH_INTERVAL', '0.05'))
DLR_MAX_RETRIES = int(os.getenv('DLR_MAX_RETRIES', '5'))
DLR_RETRY_BACKOFF = float(os.getenv('DLR_RETRY_BACKOFF', '2.0'))
DLR_KAFKA_STARTUP_TIMEOUT = float(os.getenv('DLR_KAFKA_STARTUP_TIMEOUT', '300'))
KAFKA_CONNECT_TIMEOUT = 60.0


class DeliveryReport(BaseModel):
    message_id: str = Field(alias='messageId', min_length=1)
    status: str = Field(min_length=1)
    msisdn: str = Field(min_length=1)
    event: str = 'Delivery receipt received'
    done_date: str | None = Field(default=None, alias='doneDate')


def received_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def make_producer() -> Any:
    from aiokafka import AIOKafkaProducer

    return AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        request_timeout_ms=int(KAFKA_CONNECT_TIMEOUT * 1000),
        acks='all',
        linger_ms=5,
        value_serializer=lambda value: json.dumps(value).encode('utf-8'),
        key_serializer=lambda value: value.encode('utf-8'),
    )


class DLRReceiver:
    def __init__(self, producer_factory: Callable[[], Any] = make_producer):
        self.producer_factory = producer_factory
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=DLR_QUEUE_MAX)
        self.producer: Any | None = None
        self.kafka_connected = False
        self.received_total = 0
        self.published_total = 0
        self.failed_total = 0
        self.retrying_total = 0
        self.stopping = False
        self.connection_task: asyncio.Task | None = None
        self.writer_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.stopping = False
        self.connection_task = asyncio.create_task(self._connect_kafka())

    async def stop(self) -> None:
        self.stopping = True
        if self.connection_task and not self.connection_task.done():
            self.connection_task.cancel()
            await asyncio.gather(self.connection_task, return_exceptions=True)
        if self.writer_task:
            await self.queue.join()
            await self.writer_task
            self.writer_task = None
        if self.producer is not None:
            await self.producer.stop()
            self.producer = None
        self.kafka_connected = False

    async def _connect_kafka(self) -> None:
        deadline = asyncio.get_running_loop().time() + DLR_KAFKA_STARTUP_TIMEOUT
        attempt = 0
        while not self.stopping:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.error('Kafka startup timed out after %s seconds', DLR_KAFKA_STARTUP_TIMEOUT)
                return

            attempt += 1
            producer = None
            try:
                producer = self.producer_factory()
                await asyncio.wait_for(
                    producer.start(),
                    timeout=min(KAFKA_CONNECT_TIMEOUT, remaining),
                )
                self.producer = producer
                self.kafka_connected = True
                logger.info('Connected to Kafka at %s', KAFKA_BOOTSTRAP)
                self.writer_task = asyncio.create_task(self._writer())
                return
            except asyncio.CancelledError:
                if producer is not None:
                    await self._stop_producer(producer)
                raise
            except Exception:
                logger.exception('Kafka connection attempt %s failed', attempt)
                if producer is not None:
                    await self._stop_producer(producer)
                delay = min(2 ** attempt, 60, max(deadline - asyncio.get_running_loop().time(), 0))
                if delay:
                    await asyncio.sleep(delay)

    async def _stop_producer(self, producer: Any) -> None:
        try:
            await producer.stop()
        except Exception:
            logger.exception('Failed to stop Kafka producer after connection failure')

    def enqueue(self, payload: dict[str, Any]) -> bool:
        if not self.kafka_connected or self.queue.full():
            return False
        event = {
            'event_type': 'DELIVERY_REPORT',
            'provider_message_id': payload['messageId'],
            'msisdn': payload['msisdn'],
            'status': payload['status'],
            'doneDate': payload.get('doneDate'),
            'event': payload.get('event') or 'Delivery receipt received',
            'raw_payload': payload,
            'received_at': received_timestamp(),
        }
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            return False
        self.received_total += 1
        return True

    async def _writer(self) -> None:
        while not self.stopping or not self.queue.empty():
            batch = await self._next_batch()
            if not batch:
                continue
            await self._publish_with_retry(batch)
            for _ in batch:
                self.queue.task_done()

    async def _next_batch(self) -> list[dict[str, Any]]:
        try:
            first = await asyncio.wait_for(self.queue.get(), timeout=DLR_FLUSH_INTERVAL)
        except asyncio.TimeoutError:
            return []

        batch = [first]
        deadline = asyncio.get_running_loop().time() + DLR_FLUSH_INTERVAL
        while len(batch) < DLR_BATCH_SIZE:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                batch.append(await asyncio.wait_for(self.queue.get(), timeout=remaining))
            except asyncio.TimeoutError:
                break
        return batch

    async def _publish_with_retry(self, batch: list[dict[str, Any]]) -> None:
        retrying = False
        try:
            for attempt in range(1, DLR_MAX_RETRIES + 1):
                try:
                    if self.producer is None:
                        raise RuntimeError('Kafka producer is not connected')
                    results = await asyncio.gather(*[
                        self.producer.send_and_wait(
                            KAFKA_DELIVERY_TOPIC,
                            event,
                            key=event['provider_message_id'],
                        )
                        for event in batch
                    ], return_exceptions=True)
                    errors = [result for result in results if isinstance(result, BaseException)]
                    if errors:
                        raise errors[0]
                    self.published_total += len(batch)
                    return
                except Exception:
                    if attempt >= DLR_MAX_RETRIES:
                        logger.exception('Dropping %s DLR events after %s attempts', len(batch), attempt)
                        self.failed_total += len(batch)
                        return
                    if not retrying:
                        self.retrying_total += len(batch)
                        retrying = True
                    delay = DLR_RETRY_BACKOFF * (2 ** (attempt - 1))
                    logger.exception('Kafka publish failed; retry %s/%s in %.1fs', attempt, DLR_MAX_RETRIES, delay)
                    await asyncio.sleep(delay)
        finally:
            if retrying:
                self.retrying_total -= len(batch)


receiver = DLRReceiver()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await receiver.start()
    try:
        yield
    finally:
        await receiver.stop()


app = FastAPI(
    title='DLR Receiver',
    version='1.0.0',
    lifespan=lifespan,
)


def bad_request(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={'success': False, 'error': 'Bad request', 'message': message},
    )


@app.post('/api/v1/delivery-reports/callback/')
async def receive_delivery_report(request: Request) -> Any:
    try:
        raw_payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return bad_request('Invalid JSON')

    try:
        report = DeliveryReport.model_validate(raw_payload)
    except ValidationError as error:
        missing_fields = {
            str(item['loc'][0])
            for item in error.errors()
            if item.get('type') in {'missing', 'string_too_short'} and item.get('loc')
        }
        for field in ('messageId', 'status', 'msisdn'):
            if field in missing_fields:
                return bad_request(f'Missing {field}')
        return bad_request('Invalid request body')

    if not receiver.enqueue(raw_payload):
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': 'Service Unavailable',
                'message': 'Queue full. Retry shortly.' if receiver.kafka_connected else 'Kafka is not connected. Retry shortly.',
            },
        )

    return {
        'success': True,
        'accepted': True,
        'received_at': received_timestamp(),
    }


@app.get('/health')
async def health() -> Any:
    connected = receiver.kafka_connected
    return JSONResponse(
        status_code=200 if connected else 503,
        content={
            'success': connected,
            'status': 'ok' if connected else 'starting',
            'kafka_connected': connected,
            'kafka_queue_depth': receiver.queue.qsize(),
            'received_total': receiver.received_total,
            'published_total': receiver.published_total,
            'failed_total': receiver.failed_total,
            'retrying_total': receiver.retrying_total,
        },
    )
