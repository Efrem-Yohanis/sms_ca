import csv
import io
from datetime import datetime, timedelta, timezone as datetime_timezone
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, F, Max, Min, Q
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe

from ..models import (
    Audience,
    Campaign,
    DeliveryRecord,
    FailedDelivery,
    FailedSent,
    MessageObject,
    ReportDeliveryLog,
    SentRecord,
    SuccessDelivery,
    SuccessSent,
)
from .email_delivery import get_active_email_config, get_email_connection


def collect_campaign_report_data(
    campaign,
    include_sent_stats=True,
    include_delivery_stats=True,
    include_message_stats=True,
):
    data = {
        'campaign_id': campaign.pk,
        'campaign_name': campaign.name,
        'campaign_status': campaign.status,
        'generated_at': timezone.now().isoformat(),
        'include_sent_stats': include_sent_stats,
        'include_delivery_stats': include_delivery_stats,
        'include_message_stats': include_message_stats,
    }

    if include_sent_stats:
        success_sent = SuccessSent.objects.filter(campaign=campaign)
        failed_sent = FailedSent.objects.filter(campaign=campaign)
        if success_sent.exists() or failed_sent.exists():
            rejected = failed_sent.filter(provider_status__iexact='REJECTED').count()
            failed = failed_sent.count() - rejected
            data['sent'] = {
                'total': success_sent.count() + failed_sent.count(),
                'accepted': success_sent.count(),
                'rejected': rejected,
                'failed': failed,
                'rejection_reasons': list(
                    failed_sent.exclude(last_error='')
                    .values(error_message=F('last_error'))
                    .annotate(count=Count('id'))
                    .order_by('-count', 'error_message')[:5]
                ),
            }
        else:
            sent_records = SentRecord.objects.filter(campaign=campaign)
            sent_counts = sent_records.aggregate(
                total=Count('id'),
                accepted=Count('id', filter=Q(sent_status__in=['SUBMITTED', 'ACCEPTED'])),
                rejected=Count('id', filter=Q(sent_status='REJECTED')),
                failed=Count('id', filter=Q(sent_status='FAILED')),
            )
            data['sent'] = {key: value or 0 for key, value in sent_counts.items()}
            data['sent']['rejection_reasons'] = list(
                sent_records.filter(sent_status='REJECTED').exclude(error_message='')
                .values('error_message').annotate(count=Count('id'))
                .order_by('-count', 'error_message')[:5]
            )

    if include_delivery_stats:
        success_delivery = SuccessDelivery.objects.filter(campaign=campaign)
        failed_delivery = FailedDelivery.objects.filter(campaign=campaign)
        if success_delivery.exists() or failed_delivery.exists():
            delivery_counts = {
                'total': success_delivery.count() + failed_delivery.count(),
                'delivered': success_delivery.count(),
                'failed': failed_delivery.count(),
            }
            failure_by_status = list(
                failed_delivery.values('delivery_status')
                .annotate(count=Count('id'))
                .order_by('delivery_status')
            )
        else:
            delivery_records = DeliveryRecord.objects.filter(campaign=campaign)
            delivery_counts = delivery_records.aggregate(
                total=Count('id'),
                delivered=Count('id', filter=Q(delivery_status='DELIVERED')),
                failed=Count('id', filter=Q(delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'])),
            )
            failure_by_status = list(
                delivery_records.filter(
                    delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'],
                ).values('delivery_status').annotate(count=Count('id')).order_by('delivery_status')
            )
        accepted = (data.get('sent') or {}).get('accepted', 0)
        data['delivery'] = {
            **{key: value or 0 for key, value in delivery_counts.items()},
            'failure_by_status': failure_by_status,
            'delivery_rate': (delivery_counts['delivered'] or 0) / accepted if accepted else 0,
        }

    if include_message_stats:
        messages = MessageObject.objects.filter(campaign=campaign)
        message_counts = messages.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(sent_status='PENDING', sending_started_at__isnull=True)),
            processing=Count('id', filter=(Q(sent_status='SUBMITTED') | Q(sent_status='PENDING', sending_started_at__isnull=False))),
            sent=Count('id', filter=Q(sent_status='ACCEPTED')),
        )
        data['messages'] = {key: value or 0 for key, value in message_counts.items()}

    return data


def _rows(report_data):
    sections = []
    for key, label in (('sent', 'Sent summary'), ('delivery', 'Delivery summary'), ('messages', 'Message queue')):
        section = report_data.get(key)
        if not section:
            continue
        rows = [(name.replace('_', ' ').title(), value) for name, value in section.items()]
        sections.append((label, rows))
    return sections


def render_report(report_data, report_format):
    title = f"Campaign report: {report_data.get('campaign_name', 'Campaign')}"
    sections = _rows(report_data)
    if report_format == 'text':
        lines = [title, f"Status: {report_data.get('campaign_status', 'Unknown')}"]
        for name, rows in sections:
            lines.extend(['', name])
            lines.extend(f'{label}: {value}' for label, value in rows)
        return '\n'.join(lines), []

    if report_format == 'html':
        content = [f'<h1>{escape(title)}</h1>', f'<p>Status: {escape(str(report_data.get("campaign_status", "Unknown")))}</p>']
        for name, rows in sections:
            row_html = ''.join(
                f'<tr><th scope="row">{escape(label)}</th><td>{escape(str(value))}</td></tr>'
                for label, value in rows
            )
            content.append(f'<h2>{escape(name)}</h2><table><tbody>{row_html}</tbody></table>')
        return '<html><body>' + ''.join(content) + '</body></html>', []

    if report_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Section', 'Metric', 'Value'])
        for name, rows in sections:
            for label, value in rows:
                writer.writerow([name, label, value])
        return f'Report attached: {title}', [('campaign-report.csv', output.getvalue(), 'text/csv')]

    if report_format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        flow = [Paragraph(escape(title), styles['Title']), Paragraph(
            f"Status: {escape(str(report_data.get('campaign_status', 'Unknown')))}",
            styles['Normal'],
        ), Spacer(1, 14)]
        for name, rows in sections:
            flow.append(Paragraph(escape(name), styles['Heading2']))
            table = Table([['Metric', 'Value'], *[[label, str(value)] for label, value in rows]])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef2')),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#aab4bc')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]))
            flow.extend([table, Spacer(1, 12)])
        document.build(flow)
        return f'Report attached: {title}', [('campaign-report.pdf', buffer.getvalue(), 'application/pdf')]

    raise ValueError(f'Unsupported report format: {report_format}')


def send_campaign_report(
    campaign,
    recipients,
    report_format='html',
    subject=None,
    include_sent_stats=True,
    include_delivery_stats=True,
    include_message_stats=True,
    email_config=None,
    subscription=None,
    log=None,
):
    config = email_config or (log.email_config if log and log.email_config_id else None)
    config = config or get_active_email_config()
    log = log or ReportDeliveryLog.objects.create(
        campaign=campaign,
        subscription=subscription,
        email_config=config,
        recipients=recipients,
        format=report_format,
        subject=subject or f'Campaign report: {campaign.name}',
        include_sent_stats=include_sent_stats,
        include_delivery_stats=include_delivery_stats,
        include_message_stats=include_message_stats,
    )
    log.status = 'failed'
    log.error_message = ''
    log.sent_at = None
    log.recipients = recipients
    log.format = report_format
    log.subject = subject or log.subject or f'Campaign report: {campaign.name}'
    log.email_config = config
    log.include_sent_stats = include_sent_stats
    log.include_delivery_stats = include_delivery_stats
    log.include_message_stats = include_message_stats

    try:
        report_data = collect_campaign_report_data(
            campaign,
            include_sent_stats=include_sent_stats,
            include_delivery_stats=include_delivery_stats,
            include_message_stats=include_message_stats,
        )
        if report_format == 'html':
            from .campaign_progress_reports import build_campaigns_report_content
            body, _ = build_campaigns_report_content([campaign], subject or f'{campaign.name} - Reports')
            attachments = []
        else:
            body, attachments = render_report(report_data, report_format)
        log.report_data = report_data
        log.content = body
        log.attachment_names = [filename for filename, _, _ in attachments]
        log.save()

        message = EmailMultiAlternatives(
            subject=log.subject,
            body=body,
            from_email=config.default_from_email if config else settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            connection=get_email_connection(config),
        )
        if report_format == 'html':
            message.attach_alternative(body, 'text/html')
        for filename, content, mimetype in attachments:
            message.attach(filename, content, mimetype)
        sent_count = message.send(fail_silently=False)
        if sent_count < 1:
            raise RuntimeError('Email backend did not send the report to any recipients.')
        log.status = 'sent'
        log.sent_at = timezone.now()
    except Exception as exc:
        log.error_message = str(exc)

    log.save()
    return log


REPORT_COLUMNS = [
    ('campaign_name', 'Campaign Name'),
    ('campaign_id', 'Campaign ID'),
    ('campaign_status', 'Campaign Status'),
    ('owner_email', 'Owner Email'),
    ('total_audience', 'Total Audience'),
    ('pending', 'Pending'),
    ('sent_started_at', 'Sent Started At'),
    ('sent_completed_at', 'Sent Completed At'),
    ('sent_success', 'Sent Success'),
    ('sent_failed', 'Sent Failed'),
    ('delivery_success', 'Delivery Success'),
    ('delivery_failed', 'Delivery Failed'),
    ('delivery_started_at', 'Delivery Started At'),
    ('last_delivery_at', 'Last Delivery At'),
]
TOTAL_KEYS = ('total_audience', 'pending', 'sent_success', 'sent_failed', 'delivery_success', 'delivery_failed')


def _format_datetime(value):
    if value is None:
        return '—'
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M:%S %Z')


def _campaign_report_row(campaign, owner_email):
    schedule = getattr(campaign, 'schedule', None)
    current_round = schedule.current_round if schedule and schedule.current_round else None
    audience_rows = Audience.objects.filter(campaign=campaign)
    if current_round is None:
        current_round = audience_rows.aggregate(round_number=Max('round_number'))['round_number'] or 1

    sent_stats = SuccessSent.objects.filter(campaign=campaign, round_number=current_round).aggregate(
        started=Min('sent_at'),
        completed=Max('sent_at'),
        count=Count('id'),
    )
    sent_failed = FailedSent.objects.filter(campaign=campaign, round_number=current_round).count()
    delivery_success = SuccessDelivery.objects.filter(campaign=campaign, round_number=current_round)
    delivery_failed = FailedDelivery.objects.filter(campaign=campaign, round_number=current_round)
    delivery_started_values = [
        value for value in (
            delivery_success.aggregate(value=Min('delivered_at'))['value'],
            delivery_failed.aggregate(value=Min('failed_at'))['value'],
        ) if value is not None
    ]
    delivery_last_values = [
        value for value in (
            delivery_success.aggregate(value=Max('delivered_at'))['value'],
            delivery_failed.aggregate(value=Max('failed_at'))['value'],
        ) if value is not None
    ]
    return {
        'campaign_name': campaign.name,
        'campaign_id': campaign.id,
        'campaign_status': campaign.status,
        'owner_email': owner_email,
        'total_audience': audience_rows.filter(round_number=current_round).count(),
        'pending': MessageObject.objects.filter(
            campaign=campaign,
            round_number=current_round,
            sent_status__in=['PENDING', 'SUBMITTED', 'ACCEPTED'],
        ).count(),
        'sent_started_at': _format_datetime(sent_stats['started']),
        'sent_completed_at': _format_datetime(sent_stats['completed']),
        'sent_success': sent_stats['count'] or 0,
        'sent_failed': sent_failed,
        'delivery_success': delivery_success.count(),
        'delivery_failed': delivery_failed.count(),
        'delivery_started_at': _format_datetime(min(delivery_started_values) if delivery_started_values else None),
        'last_delivery_at': _format_datetime(max(delivery_last_values) if delivery_last_values else None),
    }


def build_subscription_report_data(subscription, campaigns, recipient):
    rows = [_campaign_report_row(campaign, recipient) for campaign in campaigns]
    totals = {key: sum(row[key] for row in rows) for key in TOTAL_KEYS}
    sent_total = totals['sent_success'] + totals['sent_failed']
    delivered_total = totals['delivery_success']
    failed_total = totals['sent_failed'] + totals['delivery_failed']
    return {
        'report_name': subscription.name,
        'generated_at': timezone.now().isoformat(),
        'generated_at_display': timezone.localtime().strftime('%Y-%m-%d %H:%M:%S %Z'),
        'summary_total_campaigns': len(rows),
        'summary_total_sent': sent_total,
        'summary_total_delivered': delivered_total,
        'summary_total_failed': failed_total,
        'summary_total_pending': totals['pending'],
        'campaigns': rows,
        'totals': totals,
    }


def render_subscription_report(report_data, report_format):
    rows = report_data['campaigns']
    totals = report_data['totals']
    if report_format == 'html':
        campaign_rows = []
        for row in rows:
            cells = ''.join(
                f'<td style="padding:8px;border-bottom:1px solid #e1e5ea">{escape(str(row[key]))}</td>'
                for key, _ in REPORT_COLUMNS
            )
            campaign_rows.append(f'<tr>{cells}</tr>')
        total_cells = []
        for key, _ in REPORT_COLUMNS:
            value = totals[key] if key in totals else '—'
            total_cells.append(f'<td style="padding:8px;font-weight:bold">{escape(str(value))}</td>')
        return render_to_string('sms_campaign_manager/emails/report_subscription.html', {
            **report_data,
            'campaign_rows': mark_safe(''.join(campaign_rows)),
            'total_cells': mark_safe(''.join(total_cells)),
        }), []

    if report_format == 'text':
        lines = [
            report_data['report_name'],
            f"Generated {report_data['generated_at_display']}",
            f"Campaigns: {report_data['summary_total_campaigns']} | Sent: {report_data['summary_total_sent']} | Delivered: {report_data['summary_total_delivered']} | Failed: {report_data['summary_total_failed']} | Pending: {report_data['summary_total_pending']}",
            '',
            ' | '.join(label for _, label in REPORT_COLUMNS),
        ]
        lines.extend(' | '.join(str(row[key]) for key, _ in REPORT_COLUMNS) for row in rows)
        lines.append(' | '.join(str(totals.get(key, '—')) if key in TOTAL_KEYS else '—' for key, _ in REPORT_COLUMNS))
        report_text = '\n'.join(lines)
        return report_text, [('campaign-report.txt', report_text, 'text/plain')]

    if report_format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([label for _, label in REPORT_COLUMNS])
        writer.writerows([[row[key] for key, _ in REPORT_COLUMNS] for row in rows])
        writer.writerow([totals.get(key, '') if key in TOTAL_KEYS else '' for key, _ in REPORT_COLUMNS])
        return 'Campaign report is attached as CSV.', [('campaign-report.csv', output.getvalue(), 'text/csv')]

    raise ValueError(f'Unsupported report format: {report_format}')


def send_subscription_report(subscription, campaigns, recipients):
    config = subscription.email_config
    if not config or not config.is_active:
        config = get_active_email_config()
    subject = f'Campaign Report: {subscription.name}'
    logs = []
    for recipient in recipients:
        report_data = None
        body = ''
        attachments = []
        render_error = ''
        try:
            recipient_campaigns = (
                campaigns.get(recipient, [])
                if isinstance(campaigns, dict)
                else campaigns
            )
            report_data = build_subscription_report_data(subscription, recipient_campaigns, recipient)
            body, attachments = render_subscription_report(report_data, subscription.format)
        except Exception as exc:
            render_error = str(exc)
        log = ReportDeliveryLog.objects.create(
            subscription=subscription,
            campaign=recipient_campaigns[0] if len(recipient_campaigns) == 1 else None,
            email_config=config,
            recipients=[recipient],
            format=subscription.format,
            subject=subject,
            report_data=report_data or {},
            content=body,
            attachment_names=[filename for filename, _, _ in attachments],
        )
        try:
            if render_error:
                raise RuntimeError(render_error)
            message = EmailMultiAlternatives(
                subject=subject,
                body=body,
                from_email=config.default_from_email if config else settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                connection=get_email_connection(config),
            )
            if subscription.format == 'html':
                message.attach_alternative(body, 'text/html')
            for filename, content, mimetype in attachments:
                message.attach(filename, content, mimetype)
            if message.send(fail_silently=False) < 1:
                raise RuntimeError('Email backend did not send the report.')
            log.status = 'sent'
            log.sent_at = timezone.now()
        except Exception as exc:
            log.status = 'failed'
            log.error_message = str(exc)
        log.save(update_fields=['status', 'sent_at', 'error_message'])
        logs.append(log)
    return logs


def next_subscription_run_at(frequency, now):
    now = now.astimezone(datetime_timezone.utc)
    if frequency == '10min':
        boundary = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)
        return boundary + timedelta(minutes=10)
    if frequency == '1hr':
        boundary = now.replace(minute=0, second=0, microsecond=0)
        return boundary + timedelta(hours=1)
    if frequency == '1day':
        return now + timedelta(days=1)
    return None
