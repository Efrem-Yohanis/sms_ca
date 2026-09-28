"""Build and deliver scheduled campaign progress reports."""

from datetime import timedelta

from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import CampaignProgressReport, DeliveryRecord, EmailConfig, MessageObject, SentRecord
from .email_delivery import get_active_email_config, get_email_connection


FREQUENCY_INTERVALS = {
    '10_minutes': timedelta(minutes=10),
    'hourly': timedelta(hours=1),
    'daily': timedelta(days=1),
}


def get_campaign_progress(campaign):
    sent = SentRecord.objects.filter(campaign=campaign).aggregate(
        sent=Count('id', filter=Q(sent_status__in=['SUBMITTED', 'ACCEPTED'])),
        failed_sent=Count('id', filter=Q(sent_status__in=['REJECTED', 'FAILED'])),
    )
    delivered = DeliveryRecord.objects.filter(campaign=campaign).aggregate(
        delivered=Count('id', filter=Q(delivery_status='DELIVERED')),
        failed_delivery=Count('id', filter=Q(delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'])),
    )
    pending = MessageObject.objects.filter(campaign=campaign).aggregate(
        pending=Count('id', filter=Q(sent_status__in=['PENDING', 'SUBMITTED', 'ACCEPTED'])),
    )
    return {
        'campaign_id': campaign.id,
        'campaign_name': campaign.name,
        'status': campaign.status,
        'owner': ', '.join(campaign.owner_emails or []),
        'sent': sent['sent'] or 0,
        'success_sent': SentRecord.objects.filter(campaign=campaign, sent_status='ACCEPTED').count(),
        'failed_sent': sent['failed_sent'] or 0,
        'delivered': delivered['delivered'] or 0,
        'success_delivery': delivered['delivered'] or 0,
        'failed_delivery': delivered['failed_delivery'] or 0,
        'pending': pending['pending'] or 0,
        'started_at': campaign.activated_at,
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
