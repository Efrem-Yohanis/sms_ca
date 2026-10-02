"""Build and deliver scheduled campaign progress reports."""

from datetime import timedelta

from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Max, Min, Q
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import (
    CampaignProgressReport,
    DeliveryRecord,
    EmailConfig,
    FailedDelivery,
    FailedSent,
    MessageObject,
    SentRecord,
    SuccessDelivery,
    SuccessSent,
)
from .email_delivery import get_active_email_config, get_email_connection


FREQUENCY_INTERVALS = {
    '10_minutes': timedelta(minutes=10),
    'hourly': timedelta(hours=1),
    'daily': timedelta(days=1),
}


def get_campaign_progress(campaign):
    success_sent_records = SuccessSent.objects.filter(campaign=campaign)
    failed_sent_records = FailedSent.objects.filter(campaign=campaign)
    success_sent_count = success_sent_records.count()
    failed_sent_count = failed_sent_records.count()
    if success_sent_count + failed_sent_count:
        sent_count = success_sent_count + failed_sent_count
        success_sent_times = success_sent_records.aggregate(
            started=Min('sending_started_at'),
            completed=Max('sent_at'),
        )
        failed_sent_times = failed_sent_records.aggregate(
            started=Min('first_attempt_at'),
            completed=Max('final_attempt_at'),
        )
        sent_started_at = min(
            (value for value in (success_sent_times['started'], failed_sent_times['started']) if value is not None),
            default=None,
        )
        sent_completed_at = max(
            (value for value in (success_sent_times['completed'], failed_sent_times['completed']) if value is not None),
            default=None,
        )
    else:
        legacy_sent = SentRecord.objects.filter(campaign=campaign)
        sent_counts = legacy_sent.aggregate(
            sent=Count('id', filter=Q(sent_status__in=['SUBMITTED', 'ACCEPTED'])),
            failed_sent=Count('id', filter=Q(sent_status__in=['REJECTED', 'FAILED'])),
            started_at=Min('submitted_at'),
            completed_at=Max('submitted_at'),
        )
        sent_count = (sent_counts['sent'] or 0) + (sent_counts['failed_sent'] or 0)
        success_sent_count = legacy_sent.filter(sent_status='ACCEPTED').count()
        failed_sent_count = sent_counts['failed_sent'] or 0
        sent_started_at = sent_counts['started_at']
        sent_completed_at = sent_counts['completed_at']

    success_delivery_records = SuccessDelivery.objects.filter(campaign=campaign)
    failed_delivery_records = FailedDelivery.objects.filter(campaign=campaign)
    success_delivery_count = success_delivery_records.count()
    failed_delivery_count = failed_delivery_records.count()
    if success_delivery_count + failed_delivery_count:
        delivery_counts = {
            'delivered': success_delivery_count,
            'failed_delivery': failed_delivery_count,
        }
    else:
        legacy_delivery = DeliveryRecord.objects.filter(campaign=campaign)
        delivery_counts = legacy_delivery.aggregate(
            delivered=Count('id', filter=Q(delivery_status='DELIVERED')),
            failed_delivery=Count('id', filter=Q(delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'])),
        )
        success_delivery_count = delivery_counts['delivered'] or 0
        failed_delivery_count = delivery_counts['failed_delivery'] or 0

    pending = MessageObject.objects.filter(campaign=campaign).aggregate(
        pending=Count('id', filter=Q(sent_status__in=['PENDING', 'SUBMITTED', 'ACCEPTED'])),
    )
    return {
        'campaign_id': campaign.id,
        'campaign_name': campaign.name,
        'status': campaign.status,
        'owner': ', '.join(campaign.owner_emails or []),
        'sent': sent_count,
        'success_sent': success_sent_count,
        'failed_sent': failed_sent_count,
        'delivered': success_delivery_count,
        'success_delivery': success_delivery_count,
        'failed_delivery': failed_delivery_count,
        'pending': pending['pending'] or 0,
        'started_at': sent_started_at,
        'sent_completed_at': sent_completed_at,
        'round_number': getattr(getattr(campaign, 'schedule', None), 'current_round', 0),
    }


def build_campaigns_report_content(campaigns, title):
    rows = [get_campaign_progress(campaign) for campaign in campaigns]
    generated_at = timezone.localtime().strftime('%Y-%m-%d %H:%M:%S %Z')
    for row in rows:
        row['started_at_display'] = (
            timezone.localtime(row['started_at']).strftime('%Y-%m-%d %H:%M:%S %Z')
            if row['started_at'] else '—'
        )

    totals = {
        'campaigns': len(rows),
        'success_sent': sum(row['success_sent'] for row in rows),
        'failed_sent': sum(row['failed_sent'] for row in rows),
        'success_delivery': sum(row['success_delivery'] for row in rows),
        'failed_delivery': sum(row['failed_delivery'] for row in rows),
    }
    html = render_to_string(
        'sms_campaign_manager/emails/campaign_progress_report.html',
        {'title': title, 'generated_at': generated_at, 'rows': rows, 'totals': totals},
    )
    return html, rows


def build_report_content(report):
    return build_campaigns_report_content(report.campaigns.all(), report.name)


def get_report_recipients(report):
    recipients = {email.strip().lower() for email in report.recipients if email and email.strip()}
    if report.include_campaign_owners:
        for campaign in report.campaigns.all():
            recipients.update(email.strip().lower() for email in (campaign.owner_emails or []) if email and email.strip())
    return sorted(recipients)


def send_progress_report(report):
    recipients = get_report_recipients(report)
    if not recipients:
        raise ValueError('The report has no recipients after campaign-owner expansion.')
    html, rows = build_report_content(report)
    config = get_active_email_config()
    subject = f'Campaign progress report: {report.name}'
    from_email = config.default_from_email if config else None
    message = EmailMultiAlternatives(
        subject=subject,
        body='Campaign progress report attached as HTML.',
        from_email=from_email,
        to=recipients,
        connection=get_email_connection(config),
    )
    message.attach_alternative(html, 'text/html')
    message.send(fail_silently=False)
    now = timezone.now()
    report.last_run_at = now
    report.next_run_at = now + FREQUENCY_INTERVALS[report.frequency]
    report.save(update_fields=['last_run_at', 'next_run_at', 'updated_at'])
    return {'report_id': report.id, 'recipients': recipients, 'campaigns': rows, 'sent_at': now}


def send_due_reports():
    now = timezone.now()
    results = []
    reports = CampaignProgressReport.objects.filter(
        is_active=True,
    ).filter(Q(next_run_at__isnull=True) | Q(next_run_at__lte=now)).prefetch_related('campaigns')
    for report in reports:
        try:
            results.append(send_progress_report(report))
        except Exception as exc:
            results.append({'report_id': report.id, 'success': False, 'message': str(exc)})
    return results
