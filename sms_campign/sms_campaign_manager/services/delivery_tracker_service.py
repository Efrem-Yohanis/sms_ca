"""Business logic for high-throughput delivery record operations."""

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from ..constants import DELIVERY_TERMINAL_STATUSES
from ..models import DeliveryRecord


class DeliveryTrackerService:
    @staticmethod
    def create_single(data):
        record = DeliveryRecord.objects.create(**data)
        return record

    @staticmethod
    def bulk_create(records_data, chunk_size=5000):
        created = 0
        errors = []
        for start in range(0, len(records_data), chunk_size):
            chunk_data = records_data[start:start + chunk_size]
            try:
                with transaction.atomic():
                    DeliveryRecord.objects.bulk_create([
                        DeliveryRecord(**data) for data in chunk_data
                    ], batch_size=chunk_size)
                created += len(chunk_data)
            except Exception as error:
                errors.append({'chunk_start': start, 'error': str(error)})
        return {'created': created, 'failed': len(records_data) - created, 'errors': errors}

    @staticmethod
    def bulk_update_status(updates, chunk_size=5000):
        records = {
            record.id: record
            for record in DeliveryRecord.objects.filter(id__in=[item['id'] for item in updates])
        }
        changed = []
        errors = []
        for item in updates:
            record = records.get(item['id'])
            if not record:
                errors.append({'id': item['id'], 'error': 'not found'})
                continue
            if record.delivery_status in DELIVERY_TERMINAL_STATUSES:
                errors.append({'id': record.id, 'error': 'record has terminal status'})
                continue
            record.delivery_status = item['delivery_status']
            if item.get('delivered_at'):
                record.delivered_at = item['delivered_at']
            elif record.delivery_status == 'DELIVERED' and not record.delivered_at:
                record.delivered_at = timezone.now()
            changed.append(record)
        for start in range(0, len(changed), chunk_size):
            DeliveryRecord.objects.bulk_update(
                changed[start:start + chunk_size],
                ['delivery_status', 'delivered_at', 'updated_at'],
                batch_size=chunk_size,
            )
        return {'updated': len(changed), 'failed': len(errors), 'errors': errors}

    @staticmethod
    def get_campaign_stats(campaign_id):
        aggregates = DeliveryRecord.objects.filter(campaign_id=campaign_id).aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(delivery_status='PENDING')),
            delivered=Count('id', filter=Q(delivery_status='DELIVERED')),
            undeliverable=Count('id', filter=Q(delivery_status='UNDELIVERABLE')),
            expired=Count('id', filter=Q(delivery_status='EXPIRED')),
            rejected=Count('id', filter=Q(delivery_status='REJECTED')),
            unknown=Count('id', filter=Q(delivery_status='UNKNOWN')),
        )
        return {'campaign_id': campaign_id, **{key: value or 0 for key, value in aggregates.items()}}
