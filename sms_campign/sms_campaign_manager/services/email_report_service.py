"""Aggregation and SMTP delivery for scheduled campaign reports."""

from email.message import EmailMessage
import smtplib

from django.db.models import Count, Min, Q
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import DeliveryRecord, SentRecord


def aggregate_campaigns(campaigns):
    campaign_ids = campaigns.values_list('id', flat=True)
    sent = SentRecord.objects.filter(campaign_id__in=campaign_ids).aggregate(
        sent_start=Min('submitted_at'),
        created_start=Min('created_at'),
        sent_count=Count('id'),
        failed_sent=Count('id', filter=Q(sent_status='FAILED')),
    )
    delivery = DeliveryRecord.objects.filter(campaign_id__in=campaign_ids).aggregate(
        delivered_count=Count('id', filter=Q(delivery_status='DELIVERED')),
        failed_delivery=Count(
            'id', filter=Q(delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED']),
        ),
    )
    stats = {key: value or 0 for key, value in {**sent, **delivery}.items()}
    stats['sent_start'] = sent['sent_start'] or sent['created_start']
    del stats['created_start']
    return stats


def render_report(report):
    stats = aggregate_campaigns(report.campaigns.all())
    lines = [
        f'Campaign report: {report.name}',
        f"Campaign sent start: {stats['sent_start'] or 'N/A'}",
        f"Sent count: {stats['sent_count']}",
        f"Failed sent: {stats['failed_sent']}",
        f"Delivered count: {stats['delivered_count']}",
        f"Failed delivery: {stats['failed_delivery']}",
    ]
    return '\n'.join(lines), stats


def render_html_report(report):
    stats = aggregate_campaigns(report.campaigns.all())
    return render_to_string(
        'sms_campaign_manager/email_campaign_report.html',
        {'report': report, 'stats': stats},
    )


def send_report(report):
    body, stats = render_report(report)
    html_body = render_html_report(report)
    recipients = list(report.recipients.values_list('email', flat=True))
    if report.include_owner:
        campaign_owner_emails = report.campaigns.filter(
            created_by__isnull=False,
        ).exclude(
            created_by__email='',
        ).values_list('created_by__email', flat=True)
        recipients.extend(campaign_owner_emails)
    recipients = list(dict.fromkeys(recipients))
    if not recipients:
        return stats
    server = report.email_server
    message = EmailMessage()
    message['Subject'] = f'Campaign report: {report.name}'
    message['From'] = server.from_email
    message['To'] = ', '.join(recipients)
    message.set_content(body)
    message.add_alternative(html_body, subtype='html')
    with smtplib.SMTP_SSL(server.host, server.port) if server.use_ssl else smtplib.SMTP(server.host, server.port) as smtp:
        if server.use_tls:
            smtp.starttls()
        if server.username:
            smtp.login(server.username, server.password)
        smtp.send_message(message)
    report.last_sent_at = timezone.now()
    report.save(update_fields=['last_sent_at', 'updated_at'])
    return stats
