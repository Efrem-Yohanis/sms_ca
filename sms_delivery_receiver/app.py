"""Standalone FastAPI service for SMSC delivery reports."""

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv(
    'SMSC_DELIVERY_DATABASE',
    os.path.join(BASE_DIR, 'sms_campign', 'db.sqlite3'),
)

STATUS_MAP = {
    'DELIVRD': 'DELIVERED',
    'UNDELIV': 'UNDELIVERABLE',
    'EXPIRED': 'EXPIRED',
    'REJECTD': 'REJECTED',
}
TERMINAL_STATUSES = {'DELIVERED', 'UNDELIVERABLE', 'EXPIRED', 'REJECTED', 'UNKNOWN'}


class DeliveryReport(BaseModel):
    provider_message_id: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=50)
    receiver: str | None = Field(default=None, max_length=20)
    delivered_at: datetime | None = None
    error_reason: str | None = None


class DeliveryReportStore:
    def __init__(self, database_path: str):
        self.database_path = database_path

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=30000')
        connection.execute('PRAGMA journal_mode=WAL')
        return connection

    def update(self, report: DeliveryReport, payload: dict[str, Any]) -> dict[str, Any]:
        provider_id = report.provider_message_id.strip()
        provider_status = report.status.strip().upper()
        delivery_status = STATUS_MAP.get(provider_status, 'UNKNOWN')
        delivered_at = report.delivered_at.isoformat() if delivery_status == 'DELIVERED' and report.delivered_at else None
        now = datetime.now(timezone.utc).isoformat()

        connection = self.connection()
        try:
            connection.execute('BEGIN IMMEDIATE')
            sent_record = connection.execute(
                '''SELECT id, campaign_id, channel_id, message_object_id, msisdn, batch_id
                   FROM sms_campaign_manager_sentrecord
                   WHERE provider_message_id = ?
                   ORDER BY id DESC LIMIT 1''',
                (provider_id,),
            ).fetchone()
            if sent_record is None:
                connection.rollback()
                raise HTTPException(status_code=404, detail='Unknown provider_message_id.')

            response_json = json.dumps(payload)
            connection.execute(
                '''UPDATE sms_campaign_manager_sentrecord
                   SET provider_status = ?, provider_response = ?, updated_at = ?
                   WHERE id = ?''',
                (provider_status, response_json, now, sent_record['id']),
            )

            existing = connection.execute(
                '''SELECT id, delivery_status
                   FROM sms_campaign_manager_deliveryrecord
                   WHERE sent_record_id = ?
                   ORDER BY id DESC LIMIT 1''',
                (sent_record['id'],),
            ).fetchone()
            if existing is not None and existing['delivery_status'] in TERMINAL_STATUSES:
                connection.commit()
                return {
                    'success': True,
                    'delivery_record_id': existing['id'],
                    'delivery_status': existing['delivery_status'],
                }

            if existing is None:
                cursor = connection.execute(
                    '''INSERT INTO sms_campaign_manager_deliveryrecord
                       (campaign_id, channel_id, message_object_id, sent_record_id,
                        msisdn, batch_id, delivered_at, delivery_status,
                        provider_status, provider_response, error_message,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        sent_record['campaign_id'], sent_record['channel_id'],
                        sent_record['message_object_id'], sent_record['id'],
                        report.receiver or sent_record['msisdn'], sent_record['batch_id'],
                        delivered_at, delivery_status, provider_status, response_json,
                        report.error_reason or '', now, now,
                    ),
                )
                record_id = cursor.lastrowid
            else:
                record_id = existing['id']
                connection.execute(
                    '''UPDATE sms_campaign_manager_deliveryrecord
                       SET delivered_at = ?, delivery_status = ?,
                           provider_status = ?, provider_response = ?,
                           error_message = ?, updated_at = ?
                       WHERE id = ?''',
                    (
                        delivered_at, delivery_status, provider_status, response_json,
                        report.error_reason or '', now, record_id,
                    ),
                )

            connection.commit()
            return {
                'success': True,
                'delivery_record_id': record_id,
                'delivery_status': delivery_status,
            }
        except HTTPException:
            raise
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


store = DeliveryReportStore(DATABASE_PATH)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.path.exists(DATABASE_PATH):
        raise RuntimeError(f'Database does not exist: {DATABASE_PATH}')
    yield


app = FastAPI(
    title='SMS Delivery Report Receiver',
    version='1.0.0',
    lifespan=lifespan,
)


@app.get('/health')
def health() -> dict[str, Any]:
    connection = store.connection()
    try:
        connection.execute('SELECT 1').fetchone()
    finally:
        connection.close()
    return {'success': True, 'status': 'ok'}


@app.post('/delivery-reports/callback/')
@app.post('/api/v1/delivery-reports/callback/')
def receive_delivery_report(report: DeliveryReport) -> dict[str, Any]:
    return store.update(report, report.model_dump(mode='json'))
