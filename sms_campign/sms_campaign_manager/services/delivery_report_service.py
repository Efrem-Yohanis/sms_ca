from django.db import transaction
from django.utils.dateparse import parse_datetime
from ..models import SentRecord, DeliveryRecord

class DeliveryReportService:
    @staticmethod
    @transaction.atomic
    def process(payload):
        provider_id = str(payload.get('provider_message_id') or '').strip()
        provider_status = str(payload.get('status') or '').strip().upper()
        sent = SentRecord.objects.select_related('campaign', 'channel').filter(
            provider_message_id=provider_id).first()
        if not sent:
            raise ValueError('Unknown provider_message_id.')
        status_map = {'DELIVRD':'DELIVERED','UNDELIV':'UNDELIVERABLE',
                      'EXPIRED':'EXPIRED','REJECTD':'REJECTED'}
        mapped = status_map.get(provider_status, 'UNKNOWN')
        delivered = parse_datetime(str(payload['delivered_at'])) if payload.get('delivered_at') else None
        record = DeliveryRecord.objects.filter(sent_record=sent).order_by('-id').first()
        if record and record.is_terminal():
            return record
        values = dict(campaign=sent.campaign, channel=sent.channel, message_object=sent.message_object,
                      sent_record=sent, msisdn=str(payload.get('receiver') or sent.msisdn),
                      batch_id=sent.batch_id, delivered_at=delivered if mapped == 'DELIVERED' else None,
                      delivery_status=mapped, provider_status=provider_status,
                      provider_response=payload, error_message=str(payload.get('error_reason') or ''))
        if record:
            for key, value in values.items(): setattr(record, key, value)
            record.save()
        else:
            record = DeliveryRecord.objects.create(**values)
        return record
