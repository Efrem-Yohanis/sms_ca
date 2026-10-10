import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Max
from django.template.loader import render_to_string
from django.utils import timezone

from ..models import AudienceConfig, Language, MessageObject
from .email_delivery import get_active_email_config, get_email_connection

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    'manual': 'Manual',
    'file_import': 'File import',
    'database': 'Database',
}


def build_activation_email_context(campaign):
    schedule = getattr(campaign, 'schedule', None)
    content = getattr(campaign, 'message_content', None)
    audience = AudienceConfig.objects.filter(campaign=campaign).order_by('-round_number').first()

    channel_names = ', '.join(campaign.channels.order_by('name').values_list('name', flat=True)) or '—'
    processed = MessageObject.objects.filter(campaign=campaign, sent_status='SENT')
    last_processed_id = processed.aggregate(last_id=Max('id'))['last_id'] or 0

    def display_date(value):
        return timezone.localtime(value).strftime('%d/%m/%Y, %H:%M:%S') if value else '—'

    language_names = {
        language.code: language.name
        for language in Language.objects.filter(is_active=True)
    }
    language_content = []
    if content:
        for code, text in content.get_content_dict().items():
            if text.strip():
                language_content.append({
                    'code': code,
                    'name': language_names.get(code, code),
                    'text': text.strip(),
                    'is_default': code == content.default_language.code,
                })

    campaign_info_rows = [
        {'label': 'Campaign Name', 'value': campaign.name},
        {'label': 'Sender ID', 'value': campaign.sender_id},
        {'label': 'Owner Emails', 'value': ', '.join(campaign.owner_emails or []) or '—'},
        {'label': 'Status', 'value': campaign.status},
        {'label': 'Execution Status', 'value': campaign.execution_status.title()},
        {'label': 'Channels', 'value': channel_names},
        {'label': 'Created', 'value': display_date(campaign.created_at)},
        {'label': 'Activated At', 'value': display_date(campaign.activated_at)},
        {'label': 'Last Updated', 'value': display_date(campaign.updated_at)},
        {'label': 'Total Processed', 'value': str(processed.count())},
        {'label': 'Last Processed ID', 'value': str(last_processed_id)},
    ]

    schedule_rows = []
    if schedule:
        schedule_rows = [
            {'label': 'Schedule Type', 'value': schedule.get_schedule_type_display()},
            {'label': 'Description', 'value': schedule.get_schedule_summary()},
            {'label': 'Active', 'value': 'Yes' if schedule.is_active else 'No'},
            {'label': 'Start Date', 'value': str(schedule.start_date)},
        ]
        if schedule.end_date:
            schedule_rows.append({'label': 'End Date', 'value': str(schedule.end_date)})
        schedule_rows.extend([
            {'label': 'Timezone', 'value': schedule.timezone},
            {
                'label': 'Delivery Windows',
                'value': ', '.join(
                    f'{window["start"]} → {window["end"]}'
                    for window in schedule.time_windows
                ),
            },
        ])

    audience_total = audience.total_count or 0 if audience else 0
    audience_valid = audience.valid_count or 0 if audience else 0
    audience_invalid = audience.invalid_count or 0 if audience else 0

    return {
        'campaign_name': campaign.name,
        'notification_heading': f'{campaign.name} is active',
        'notification_message': 'The following campaign is now active and ready to send.',
        'campaign_info_rows': campaign_info_rows,
        'default_language': content.default_language.name if content else '—',
        'languages_available': ', '.join(item['name'] for item in language_content) or '—',
        'language_content': language_content,
        'schedule_rows': schedule_rows,
        'has_audience': audience is not None,
        'audience_total': audience_total,
        'audience_valid': audience_valid,
        'audience_invalid': audience_invalid,
        'audience_valid_rate': f'{audience_valid * 100 / audience_total:.1f}' if audience_total else '0.0',
        'audience_source': SOURCE_LABELS.get(audience.source_type, audience.source_type) if audience else '',
    }


def _build_activation_email_text(
    context,
    owner_email=None,
    notification_message='The following campaign is now active and ready to send.',
):
    lines = [
        f'Hello {owner_email},' if owner_email else 'Hello,',
        '',
        notification_message,
        '',
        '═' * 67,
        ' 1. CAMPAIGN INFO',
        '═' * 67,
        '',
    ]
    for row in context['campaign_info_rows']:
        lines.append(f'{row["label"]:<20} {row["value"]}')

    lines.extend([
        '',
        '═' * 67,
        ' 2. MESSAGE CONTENT',
        '═' * 67,
        '',
    ])

    if context['language_content']:
        lines.extend([
            f'Default Language     {context["default_language"]}',
            'Languages Available  ' + context['languages_available'],
            '',
            'Content per language:',
            '─' * 49,
        ])
        for item in context['language_content']:
            language_label = f'{item["name"]} (default)' if item['is_default'] else item['name']
            lines.append(f' {language_label:<20} {" ".join(item["text"].splitlines())}')
    else:
        lines.append('No message content configured.')

    lines.extend(['', '═' * 67, ' 3. SCHEDULE', '═' * 67, ''])
    if context['schedule_rows']:
        lines.extend(
            f'{row["label"]:<20} {row["value"]}'
            for row in context['schedule_rows']
        )
    else:
        lines.append('No schedule configured.')

    lines.extend(['', '═' * 67, ' 4. AUDIENCE', '═' * 67, ''])
    if context['has_audience']:
        lines.extend([
            f'Recipients           {context["audience_total"]}',
            f'Valid                {context["audience_valid"]}',
            f'Invalid              {context["audience_invalid"]}',
            f'Valid rate           {context["audience_valid_rate"]}%',
            f'Source               {context["audience_source"]}',
        ])
    else:
        lines.append('No audience configuration found.')

    lines.extend([
        '',
        '─' * 67,
        '',
        'You are receiving this email because you are listed as an owner of',
        'this campaign. You will receive status updates and reports at this',
        'email address.',
        '',
        '— Campaign Manager',
        'This is an automated message. Do not reply.',
    ])
    return '\n'.join(lines)


def build_activation_email(campaign, owner_email=None):
    context = build_activation_email_context(campaign)
    return _build_activation_email_text(context, owner_email)


def build_activation_email_html(campaign, owner_email=None):
    context = build_activation_email_context(campaign)
    return render_to_string(
        'sms_campaign_manager/emails/campaign_activation.html',
        {**context, 'owner_email': owner_email or ''},
    )


def send_campaign_activation_email(campaign):
    return _send_campaign_owner_email(
        campaign,
        subject=f'Campaign activated: {campaign.name}',
        notification_heading=f'{campaign.name} is active',
        notification_message='The following campaign is now active and ready to send.',
        notification_type='activation',
    )


def send_campaign_started_email(campaign):
    return _send_campaign_owner_email(
        campaign,
        subject=f'Campaign started: {campaign.name}',
        notification_heading=f'{campaign.name} is now sending',
        notification_message='The following campaign has started sending messages.',
        notification_type='started',
    )


def _send_campaign_owner_email(campaign, subject, notification_heading, notification_message, notification_type):
    recipients = list(dict.fromkeys(
        email.strip().lower()
        for email in (campaign.owner_emails or [])
        if email and email.strip()
    ))
    if not recipients:
        return None

    context = {
        **build_activation_email_context(campaign),
        'notification_heading': notification_heading,
        'notification_message': notification_message,
    }
    config = get_active_email_config()
    sent_to_all = True
    for recipient in recipients:
        try:
            message = EmailMultiAlternatives(
                subject=subject,
                body=_build_activation_email_text(context, recipient, notification_message),
                from_email=config.default_from_email if config else settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                connection=get_email_connection(config),
            )
            message.attach_alternative(
                render_to_string(
                    'sms_campaign_manager/emails/campaign_activation.html',
                    {**context, 'owner_email': recipient},
                ),
                'text/html',
            )
            if message.send(fail_silently=False) != 1:
                sent_to_all = False
        except Exception:
            logger.exception('Failed to send %s notification for campaign %s', notification_type, campaign.pk)
            sent_to_all = False
    return sent_to_all
