import logging
import uuid

from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from ..models import (
    Campaign,
    MessageBuildJob,
    MessageObject,
    Audience,
    Channel,
    Language,
)

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
        self.audience_round_number = round_number
        self.batch_id = batch_id or f'batch_{uuid.uuid4().hex[:8]}'

    def build(self):
        """Build all MessageObject rows for this campaign's audience."""
        started = timezone.now()
        job = MessageBuildJob.objects.create(
            campaign=self.campaign,
            batch_id=self.batch_id,
            round_number=self.round_number,
            phase='validating',
        )
        try:
            self._resolve_audience_round()
            self._validate_prerequisites()
            job.phase = 'clearing'
            job.save(update_fields=['phase', 'updated_at'])

            cleared = MessageObject.objects.filter(
                campaign=self.campaign,
                batch_id=self.batch_id,
            ).delete()[0]
            audience_queryset = Audience.objects.filter(
                campaign=self.campaign,
                round_number=self.audience_round_number,
                is_valid=True,
            ).select_related('language').values(
                'id', 'msisdn', 'language__code', 'custom_fields',
            )
            total_audience = audience_queryset.count()
            job.phase = 'building'
            job.total_rows = total_audience
            job.save(update_fields=['phase', 'total_rows', 'updated_at'])

            content = self.campaign.message_content
            channel = self._get_channel()
            languages_by_code = Language.objects.in_bulk(field_name='code')
            stats = self._build_and_insert(
                audience_rows=audience_queryset.iterator(chunk_size=5000),
                content=content,
                channel=channel,
                job=job,
                languages_by_code=languages_by_code,
            )
            inserted_rows = MessageObject.objects.filter(
                campaign=self.campaign,
                batch_id=self.batch_id,
            ).count()
            job.status = 'SUCCEEDED'
            job.phase = 'complete'
            job.processed_rows = total_audience
            job.built_rows = inserted_rows
            job.skipped_rows = stats['skipped']
            job.failed_rows = stats['failed']
            job.percent = 100
            job.completed_at = timezone.now()
            job.save(update_fields=[
                'status', 'phase', 'processed_rows', 'built_rows', 'skipped_rows',
                'failed_rows', 'percent',
                'completed_at', 'updated_at',
            ])

            return {
                'campaign_id': self.campaign.id,
                'round_number': self.round_number,
                'audience_round_number': self.audience_round_number,
                'batch_id': self.batch_id,
                'build_job_id': job.pk,
                'cleared': cleared,
                'total_audience': total_audience,
                **stats,
                'built': inserted_rows,
                'duration_seconds': (timezone.now() - started).total_seconds(),
            }
        except Exception as exc:
            MessageObject.objects.filter(campaign=self.campaign, batch_id=self.batch_id).delete()
            job.status = 'FAILED'
            job.phase = 'failed'
            job.error_message = str(exc)
            job.completed_at = timezone.now()
            job.save(update_fields=['status', 'phase', 'error_message', 'completed_at', 'updated_at'])
            logger.exception(
                'Message build failed campaign_id=%s job_id=%s batch_id=%s',
                self.campaign.pk, job.pk, self.batch_id,
            )
            raise

    def _validate_prerequisites(self):
        errors = []

        if not self.campaign.sender_id:
            errors.append('Campaign has no sender_id.')

        # message_content is OneToOne FK; use hasattr for safety
        if not hasattr(self.campaign, 'message_content'):
            errors.append('Campaign has no message content.')

        if not Audience.objects.filter(
            campaign=self.campaign,
            round_number=self.audience_round_number,
            is_valid=True,
        ).exists():
            errors.append(f'Campaign has no valid audience for round {self.round_number}.')

        if not self.campaign.channels_id:
            errors.append('Campaign has no channels.')

        if errors:
            raise ValueError('Cannot build messages: ' + '; '.join(errors))

    def _resolve_audience_round(self):
        if Audience.objects.filter(
            campaign=self.campaign,
            round_number=self.round_number,
            is_valid=True,
        ).exists():
            return
        previous_round = Audience.objects.filter(
            campaign=self.campaign,
            round_number__lt=self.round_number,
            is_valid=True,
        ).order_by('-round_number').values_list('round_number', flat=True).first()
        if previous_round is not None:
            self.audience_round_number = previous_round

    def _get_channel(self):
        ids = self.campaign.channels_id or []
        channel = Channel.objects.filter(id__in=ids, is_active=True).first()
        if not channel:
            raise ValueError('No active channel found for campaign.')
        return channel

    def _build_and_insert(self, audience_rows, content, channel, job, languages_by_code):
        built = 0
        skipped = 0
        errors = []
        rows = []
        chunk_size = 5000
        processed = 0

        for member in audience_rows:
            processed += 1
            try:
                lang_code = (member.get('language__code') or '').strip().lower() or content.default_language.code
                template = content.get_message(lang_code)
                if not template or not template.strip():
                    template = content.get_message(content.default_language.code)

                if not template or not template.strip():
                    skipped += 1
                    continue

                personalized = self._personalize(template, member.get('custom_fields') or {})

                language = languages_by_code.get(lang_code)
                if not language:
                    language = content.default_language

                rows.append(MessageObject(
                    message_id=f'msg_{self.campaign.id}_{uuid.uuid4().hex}',
                    campaign=self.campaign,
                    recipient=member['msisdn'],
                    sender_id=self.campaign.sender_id,
                    message_content=personalized,
                    channel=channel,
                    language=language,
                    round_number=self.round_number,
                    sent_status='PENDING',
                    batch_id=self.batch_id,
                ))
                if processed % chunk_size == 0:
                    if rows:
                        MessageObject.objects.bulk_create(rows, batch_size=chunk_size)
                        built += len(rows)
                        rows = []
                    self._update_job_progress(job, processed, built, skipped, len(errors))
            except Exception as exc:
                errors.append({
                    'msisdn': member.get('msisdn'),
                    'error': str(exc),
                })
                if processed % chunk_size == 0:
                    if rows:
                        MessageObject.objects.bulk_create(rows, batch_size=chunk_size)
                        built += len(rows)
                        rows = []
                    self._update_job_progress(job, processed, built, skipped, len(errors))

        if rows:
            MessageObject.objects.bulk_create(rows, batch_size=chunk_size)
            built += len(rows)
        self._update_job_progress(job, processed, built, skipped, len(errors))

        return {
            'built': built,
            'skipped': skipped,
            'failed': len(errors),
            'errors': errors[:20],
        }

    @staticmethod
    def _update_job_progress(job, processed, built, skipped, failed):
        total = job.total_rows
        percent = round(processed / total * 100, 2) if total else 100
        MessageBuildJob.objects.filter(pk=job.pk, status='RUNNING').update(
            phase='inserting',
            processed_rows=processed,
            built_rows=built,
            skipped_rows=skipped,
            failed_rows=failed,
            percent=percent,
            updated_at=timezone.now(),
        )
        logger.info(
            'Message build progress campaign_id=%s job_id=%s batch_id=%s phase=inserting processed=%s total=%s committed=%s skipped=%s failed=%s percent=%s',
            job.campaign_id, job.pk, job.batch_id, processed, total,
            built, skipped, failed, percent,
        )

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
