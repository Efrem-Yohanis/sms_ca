import logging
import uuid

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.shortcuts import get_object_or_404

from ..models import (
    Campaign,
    MessageObject,
    Audience,
    Channel,
    Language,
)
from ..kafka import enqueue_event, TOPIC_MESSAGE_CREATED

logger = logging.getLogger(__name__)


class MessageBuilder:
    """
    Build MessageObject rows from the campaign audience metadata.

    This implementation mirrors the request in the project note while
    adapting it to the current model schema in this repository:
    - MessageObject carries channel and language foreign keys
    - sent_status and delivery_status hold lifecycle state
    - the audience child table is Audience/AudienceMember under the
      campaign, via `campaign` relation and `msisdn + language` rows.
    """

    def __init__(self, campaign, round_number=1, batch_id=None):
        self.campaign = campaign
        self.round_number = round_number
        self.batch_id = batch_id or f'batch_{uuid.uuid4().hex[:8]}'

    def build(self):
        """Build all MessageObject rows for this campaign's audience."""
        started = timezone.now()

        self._validate_prerequisites()

        with transaction.atomic():
            return self._build_transaction(started)

    def _build_transaction(self, started):
        # Clear any existing queue rows for this campaign.
        cleared = MessageObject.objects.filter(campaign=self.campaign).delete()[0]

        audience_query = (
            Audience.objects.filter(
                campaign=self.campaign,
                is_valid=True,
            ).select_related('language').values(
                'id', 'msisdn', 'language__code', 'custom_fields',
            )
        )
        total_audience = audience_query.count()

        content = self.campaign.message_content
        channel = self._get_channel()

        stats = self._build_and_insert(
            audience_rows=audience_query.iterator(chunk_size=5000),
            content=content,
            channel=channel,
        )

        return {
            'campaign_id': self.campaign.id,
            'round_number': self.round_number,
            'batch_id': self.batch_id,
            'cleared': cleared,
            'total_audience': total_audience,
            **stats,
            'duration_seconds': (timezone.now() - started).total_seconds(),
        }

    def _validate_prerequisites(self):
        errors = []

        if not self.campaign.sender_id:
            errors.append('Campaign has no sender_id.')

        # message_content is OneToOne FK; use hasattr for safety
        if not hasattr(self.campaign, 'message_content'):
            errors.append('Campaign has no message content.')

        if not Audience.objects.filter(campaign=self.campaign, is_valid=True).exists():
            errors.append('Campaign has no valid audience.')

        if not self.campaign.channels_id:
            errors.append('Campaign has no channels.')

        if errors:
            raise ValueError('Cannot build messages: ' + '; '.join(errors))

    def _get_channel(self):
        ids = self.campaign.channels_id or []
        channel = Channel.objects.filter(id__in=ids, is_active=True).first()
        if not channel:
            raise ValueError('No active channel found for campaign.')
        return channel

    def _build_and_insert(self, audience_rows, content, channel):
        built = 0
        skipped = 0
        errors = []
        failed = 0
        rows = []
        chunk_size = 5000
        languages = {
            language.code: language
            for language in Language.objects.filter(
                code__in=['en', 'am', 'ti', 'om', 'so']
            )
        }

        for member in audience_rows:
            try:
                lang_code = (member.get('language__code') or '').strip().lower() or content.default_language.code
                template = content.get_message(lang_code)
                if not template or not template.strip():
                    template = content.get_message(content.default_language.code)

                if not template or not template.strip():
                    skipped += 1
                    continue

                personalized = self._personalize(template, member.get('custom_fields') or {})
                parts = self._calculate_parts(personalized)

                language = languages.get(lang_code) or content.default_language

                rows.append(MessageObject(
                    message_id=f'msg_{self.campaign.id}_{uuid.uuid4().hex}',
                    campaign=self.campaign,
                    recipient=member['msisdn'],
                    sender_id=self.campaign.sender_id,
                    message_content=personalized,
                    channel=channel,
                    language=language,
                    message_parts=parts,
                    sent_status='PENDING',
                    delivery_status='PENDING',
                    batch_id=self.batch_id,
                    personalized_fields=member.get('custom_fields') or {},
                ))
                built += 1

                if len(rows) >= chunk_size:
                    MessageObject.objects.bulk_create(rows, batch_size=chunk_size)
                    self._enqueue_messages(rows)
                    rows = []

            except Exception as exc:
                failed += 1
                if len(errors) < 20:
                    errors.append({
                        'msisdn': member.get('msisdn'),
                        'error': str(exc),
                    })

        if rows:
            MessageObject.objects.bulk_create(rows, batch_size=chunk_size)
            self._enqueue_messages(rows)

        return {
            'built': built,
            'skipped': skipped,
            'failed': failed,
            'errors': errors,
        }

    def _enqueue_messages(self, rows):
        if not settings.KAFKA_ENABLED:
            return
        for message in rows:
            enqueue_event('message.created', {
                'message_id': message.message_id, 'campaign_id': message.campaign_id,
                'recipient': message.recipient, 'sender_id': message.sender_id,
                'message_content': message.message_content, 'batch_id': message.batch_id,
            }, key=message.message_id, topic=TOPIC_MESSAGE_CREATED)

    @staticmethod
    def _personalize(template, fields):
        result = template
        for key, value in (fields or {}).items():
            result = result.replace(f'{{{{{key}}}}}', str(value))
        return result

    @staticmethod
    def _calculate_parts(message):
        if not message:
            return 1

        # Mirror the design note: GSM-7 versus Unicode estimates.
        is_unicode = any(ord(ch) > 127 for ch in message)
        if is_unicode:
            single, multi = 70, 67
        else:
            single, multi = 160, 153

        if len(message) <= single:
            return 1

        return (len(message) + multi - 1) // multi
