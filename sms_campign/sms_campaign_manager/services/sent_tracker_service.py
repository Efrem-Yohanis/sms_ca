"""High-throughput SentRecord operations and campaign statistics."""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from ..constants import SENT_TERMINAL_STATUSES
from ..models import SentRecord


class SentTrackerService:
    @staticmethod
    def create_single(data):
        record = SentRecord.objects.create(**data)
        if record.sent_status in ('SUBMITTED', 'ACCEPTED') and not record.submitted_at:
            record.submitted_at = timezone.now()
            record.save(update_fields=['submitted_at', 'updated_at'])
        return record

    @staticmethod
    def bulk_create(records_data, chunk_size=5000):
        created = 0
        errors = []
        for start in range(0, len(records_data), chunk_size):
            chunk = records_data[start:start + chunk_size]
            try:
                with transaction.atomic():
                    SentRecord.objects.bulk_create([SentRecord(**data) for data in chunk], batch_size=chunk_size)
                created += len(chunk)
            except Exception as error:
                errors.append({'chunk_start': start, 'error': str(error)})
        return {'created': created, 'failed': len(records_data) - created, 'errors': errors}

    @staticmethod
    def bulk_update_status(updates, chunk_size=5000):
        records = {record.id: record for record in SentRecord.objects.filter(id__in=[item['id'] for item in updates])}
        changed = []
        errors = []
        for item in updates:
            record = records.get(item['id'])
            if not record:
                errors.append({'id': item['id'], 'error': 'not found'})
                continue
            if record.sent_status in SENT_TERMINAL_STATUSES:
                errors.append({'id': record.id, 'error': 'record has terminal status'})
                continue
            record.sent_status = item['sent_status']
            if item.get('submitted_at'):
                record.submitted_at = item['submitted_at']
            elif record.sent_status in ('SUBMITTED', 'ACCEPTED') and not record.submitted_at:
                record.submitted_at = timezone.now()
            changed.append(record)
        if changed:
            SentRecord.objects.bulk_update(changed, ['sent_status', 'submitted_at', 'updated_at'], batch_size=chunk_size)
        return {'updated': len(changed), 'failed': len(errors), 'errors': errors}

    @staticmethod
    def get_campaign_stats(campaign_id):
        aggregates = SentRecord.objects.filter(campaign_id=campaign_id).aggregate(
            total=Count('id'), pending=Count('id', filter=Q(sent_status='PENDING')),
            submitted=Count('id', filter=Q(sent_status='SUBMITTED')),
            accepted=Count('id', filter=Q(sent_status='ACCEPTED')),
            rejected=Count('id', filter=Q(sent_status='REJECTED')),
            failed=Count('id', filter=Q(sent_status='FAILED')),
        )
        return {'campaign_id': campaign_id, **{key: value or 0 for key, value in aggregates.items()}}
