"""Fair, rate-limited delivery of queued MessageObject rows to an SMSC."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timedelta
import os
import time
import uuid
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

from ..models import MessageObject, SMSCConfig, SentRecord


DLR_CALLBACK_URL = os.getenv(
    'SMSC_SENDER_DLR_CALLBACK_URL',
    '',
)


@dataclass(frozen=True)
class SendOutcome:
    message_id: int
    accepted: bool
    response: dict[str, Any]
    error: str = ''


class SmsSenderService:
    """Send queued messages fairly across campaigns.

    One process should own a given SMSC configuration. Each one-second window
    divides the SMSC's per-second capacity across campaigns with pending
    messages, then submits those messages concurrently.
    """

    def __init__(self, smsc_config: SMSCConfig, *, workers: int | None = None):
        self.smsc_config = smsc_config
        self.workers = workers or min(smsc_config.rate_limit_per_second, 100)

    def run_once(self) -> dict[str, Any]:
        campaign_rows = self._load_fair_batch()
        messages = [message for rows in campaign_rows.values() for message in rows]
        if not messages:
            return {
                'success': True,
                'sent': 0,
                'failed': 0,
                'retried': 0,
                'removed': 0,
                'campaigns': 0,
            }

        outcomes = self._submit(messages)
        report = {
            'success': True,
            'sent': 0,
            'failed': 0,
            'retried': 0,
            'removed': 0,
            'campaigns': len(campaign_rows),
            'allocated': {
                str(campaign_id): len(rows)
                for campaign_id, rows in campaign_rows.items()
            },
            'errors': [],
        }
        for outcome in outcomes:
            result = self._record_outcome(outcome)
            for key in ('sent', 'failed', 'retried', 'removed'):
                report[key] += result[key]
            if result.get('error'):
                report['errors'].append(result['error'])
        return report

    def run_forever(self, *, sleep_when_empty: float = 0.25) -> None:
        while True:
            started = time.monotonic()
            report = self.run_once()
            if not report['sent'] and not report['failed']:
                time.sleep(sleep_when_empty)
                continue
            remaining = 1.0 - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)

    def _load_fair_batch(self) -> dict[int, list[MessageObject]]:
        pending = (
            MessageObject.objects
            .filter(sent_status__in=['PENDING', 'FAILED'])
            .filter(send_attempts__lt=self.smsc_config.max_retries)
            .filter(campaign__status='in_progress', campaign__is_deleted=False)
            .select_related('campaign', 'channel')
            .order_by('campaign_id', 'id')
        )
        grouped: dict[int, list[MessageObject]] = {}
        for message in pending:
            grouped.setdefault(message.campaign_id, []).append(message)

        campaign_ids = sorted(grouped)
        if not campaign_ids:
            return {}

        capacity = self.smsc_config.rate_limit_per_second
        base, remainder = divmod(capacity, len(campaign_ids))
        allocated = {
            campaign_id: grouped[campaign_id][:base + (index < remainder)]
            for index, campaign_id in enumerate(campaign_ids)
            if base + (index < remainder) > 0
        }
        for campaign_id, rows in allocated.items():
            self._claim_batch(rows)
        return allocated

    def _claim_batch(self, messages: list[MessageObject]) -> None:
        if not messages:
            return
        now = timezone.now()
        expires_at = now + timedelta(minutes=5)
        batch_id = (
            f"batch_{messages[0].campaign_id}_{int(now.timestamp() * 1000)}_"
            f"{uuid.uuid4().hex[:8]}"
        )
        worker_id = f'worker_{uuid.uuid4().hex[:12]}_{os.getpid()}'
        for message in messages:
            if message.sending_started_at is None:
                message.sending_started_at = now
            message.batch_id = batch_id
            message.worker_id = worker_id
            message.locked_until = expires_at
            message.updated_at = now
        MessageObject.objects.bulk_update(
            messages,
            ['batch_id', 'worker_id', 'locked_until', 'sending_started_at', 'updated_at'],
            batch_size=1000,
        )

    def _submit(self, messages: list[MessageObject]) -> list[SendOutcome]:
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._submit_one, message): message.id
                for message in messages
            }
            return [future.result() for future in as_completed(futures)]

    def _submit_one(self, message: MessageObject) -> SendOutcome:
        payload = {
            'message_id': message.message_id,
            'campaign_id': message.campaign_id,
            'sender_id': message.sender_id,
            'receiver': message.recipient,
            'message_content': message.message_content,
        }
        if DLR_CALLBACK_URL:
            payload['callback_url'] = DLR_CALLBACK_URL
        try:
            response = requests.post(
                self.smsc_config.get_full_send_url(),
                json=payload,
                headers=self.smsc_config.get_headers(),
                timeout=(
                    self.smsc_config.connect_timeout_seconds,
                    self.smsc_config.request_timeout_seconds,
                ),
            )
            body = response.json() if response.content else {}
            if response.status_code in (200, 201) and body.get('status') in (None, 'ACCEPTED'):
                return SendOutcome(message.id, True, body)
            return SendOutcome(
                message.id,
                False,
                body,
                f'SMSC returned HTTP {response.status_code}: {body}',
            )
        except requests.RequestException as exc:
            return SendOutcome(message.id, False, {}, str(exc))

    def _record_outcome(self, outcome: SendOutcome) -> dict[str, Any]:
        message = MessageObject.objects.filter(pk=outcome.message_id).select_related('campaign', 'channel').first()
        if message is None:
            return {'sent': 0, 'failed': 0, 'retried': 0, 'removed': 0}

        attempt_number = message.send_attempts + 1
        now = timezone.now()

        if outcome.accepted:
            with transaction.atomic():
                MessageObject.objects.filter(pk=message.pk).update(
                    sent_status='SENT',
                    sent_at=now,
                    send_attempts=attempt_number,
                    locked_until=None,
                    last_error='',
                    updated_at=now,
                )
            return {'sent': 1, 'failed': 0, 'retried': 0, 'removed': 0}

        max_retries = self.smsc_config.max_retries
        with transaction.atomic():
            MessageObject.objects.filter(pk=message.pk).update(
                sent_status='FAILED',
                send_attempts=attempt_number,
                last_error=outcome.error,
                failed_at=now,
                locked_until=None,
                updated_at=now,
            )
        if attempt_number >= max_retries:
            return {'sent': 0, 'failed': 1, 'retried': 0, 'removed': 0}
        return {'sent': 0, 'failed': 1, 'retried': 1, 'removed': 0}
