import csv
import io
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Count, Q
from django.utils import timezone

from ..models import DeliveryRecord, MessageObject, ReportDeliveryLog, SentRecord
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
        delivery_records = DeliveryRecord.objects.filter(campaign=campaign)
        delivery_counts = delivery_records.aggregate(
            total=Count('id'),
            delivered=Count('id', filter=Q(delivery_status='DELIVERED')),
            failed=Count('id', filter=Q(delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'])),
        )
        accepted = (data.get('sent') or {}).get('accepted', 0)
        data['delivery'] = {
            **{key: value or 0 for key, value in delivery_counts.items()},
            'failure_by_status': list(
                delivery_records.filter(
                    delivery_status__in=['UNDELIVERABLE', 'EXPIRED', 'REJECTED'],
                ).values('delivery_status').annotate(count=Count('id')).order_by('delivery_status')
            ),
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
        message.send(fail_silently=False)
        log.status = 'sent'
        log.sent_at = timezone.now()
    except Exception as exc:
        log.error_message = str(exc)

    log.save()
    return log