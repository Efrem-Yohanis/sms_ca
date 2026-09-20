"""Fair, rate-limited delivery of queued MessageObject rows to an SMSC."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os
import time
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

from ..models import MessageObject, SMSCConfig, SentRecord
from ..kafka import enqueue_event, TOPIC_SENT
from django.conf import settings


DLR_CALLBACK_URL = os.getenv(
    'SMSC_SENDER_DLR_CALLBACK_URL',
    'http://127.0.0.1:8000/api/v1/delivery-reports/callback/',
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
        report = self._record_outcomes(outcomes, messages)
        report.update({
            'success': True,
            'campaigns': len(campaign_rows),
            'allocated': {
                str(campaign_id): len(rows)
                for campaign_id, rows in campaign_rows.items()
            },
        })
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
            .filter(campaign__status__in=['active', 'in_progress'], campaign__is_deleted=False)
            .select_related('campaign', 'channel')
            .order_by('campaign_id', 'id')
        )
        campaign_ids = list(
            pending.order_by().values_list('campaign_id', flat=True).distinct()
        )
        if not campaign_ids:
            return {}

        capacity = self.smsc_config.rate_limit_per_second
        base, remainder = divmod(capacity, len(campaign_ids))
        grouped: dict[int, list[MessageObject]] = {}
        for index, campaign_id in enumerate(campaign_ids):
            allocation = base + (index < remainder)
            if allocation:
                grouped[campaign_id] = list(
                    pending.filter(campaign_id=campaign_id)[:allocation]
                )
        return grouped

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
            'callback_url': DLR_CALLBACK_URL,
        }
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

    def _record_outcomes(
        self,
        outcomes: list[SendOutcome],
        messages: list[MessageObject],
    ) -> dict[str, Any]:
        """Persist one sender window with bounded bulk database operations."""
        messages_by_id = {message.id: message for message in messages}
        sent_records = []
        messages_to_update = []
        message_ids_to_remove = []
        sent = failed = retried = removed = 0
        errors = []
        submitted_at = timezone.now()
        max_retries = self.smsc_config.max_retries

        for outcome in outcomes:
            message = messages_by_id.get(outcome.message_id)
            if message is None:
                errors.append(
                    f'Send outcome referenced unknown message id {outcome.message_id}.'
                )
                continue

            provider_id = str(outcome.response.get('provider_message_id', ''))
            provider_status = str(outcome.response.get('status', 'FAILED'))
            sent_records.append(SentRecord(
                campaign=message.campaign,
                channel=message.channel,
                message_object=message,
                msisdn=message.recipient,
                batch_id=message.batch_id,
                submitted_at=submitted_at if outcome.accepted else None,
                sent_status='ACCEPTED' if outcome.accepted else 'FAILED',
                provider_message_id=provider_id,
                provider_status=provider_status,
                provider_response=outcome.response,
                error_message='' if outcome.accepted else outcome.error,
            ))

            if outcome.accepted:
                sent += 1
                removed += 1
                message_ids_to_remove.append(message.id)
                continue

            failed += 1
            attempt_number = message.send_attempts + 1
            message.send_attempts = attempt_number
            message.last_error = outcome.error
            message.sent_status = 'FAILED'
            message.failed_at = submitted_at
            message.updated_at = submitted_at
            if attempt_number < max_retries:
                retried += 1
                messages_to_update.append(message)
            else:
                removed += 1
                message_ids_to_remove.append(message.id)

        with transaction.atomic():
            if sent_records:
                SentRecord.objects.bulk_create(
                    sent_records,
                    batch_size=5000,
                )
                if settings.KAFKA_ENABLED:
                    for record, outcome in zip(sent_records, outcomes):
                        enqueue_event('sent.report.received', {
                            'message_id': record.message_object.message_id,
                            'provider_message_id': record.provider_message_id,
                            'status': record.provider_status,
                            'accepted': outcome.accepted,
                            'provider_response': record.provider_response,
                        }, key=record.provider_message_id or record.message_object.message_id,
                           topic=TOPIC_SENT)
            if messages_to_update:
                MessageObject.objects.bulk_update(
                    messages_to_update,
                    [
                        'send_attempts',
                        'last_error',
                        'sent_status',
                        'failed_at',
                        'updated_at',
                    ],
                    batch_size=5000,
                )
            if message_ids_to_remove:
                MessageObject.objects.filter(
                    id__in=message_ids_to_remove,
                ).delete()

        return {
            'sent': sent,
            'failed': failed,
            'retried': retried,
            'removed': removed,
            'errors': errors,
        }
