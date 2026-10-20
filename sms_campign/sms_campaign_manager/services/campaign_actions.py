"""Campaign lifecycle actions."""

from django.db import transaction
from django.conf import settings
import logging
import requests
from django.utils import timezone

from .campaign_readiness import CampaignReadinessService
from .campaign_activation_email import send_campaign_activation_email
from .message_builder import MessageBuilder

logger = logging.getLogger(__name__)


class CampaignActionsService:
    def __init__(self, campaign):
        self.campaign = campaign

    def validate_campaign(self):
        return CampaignReadinessService(self.campaign).check()

    def _stop_sender(self):
        sender_api = getattr(settings, 'SMSC_SENDER_API', '').rstrip('/')
        if not sender_api:
            logger.error('SMSC_SENDER_API is not configured; cannot stop campaign_id=%s', self.campaign.pk)
            return False
        try:
            status_response = requests.get(
                f'{sender_api}/sender/status/{self.campaign.pk}',
                timeout=5,
            )
            if status_response.status_code == 404:
                return True
            status_response.raise_for_status()
            status_body = status_response.json()
        except requests.RequestException:
            logger.exception('Could not read sender status for campaign_id=%s', self.campaign.pk)
            return False
        except ValueError:
            logger.error(
                'Sender status returned invalid JSON for campaign_id=%s: %s',
                self.campaign.pk, status_response.text[:300],
            )
            return False

        if not isinstance(status_body, dict):
            logger.error('Sender status returned an invalid body for campaign_id=%s', self.campaign.pk)
            return False
        sender_data = status_body.get('data')
        if not isinstance(sender_data, dict):
            logger.error('Sender status response missing data for campaign_id=%s', self.campaign.pk)
            return False
        if not sender_data.get('active'):
            return True
        try:
            round_number = int(sender_data['round_number'])
        except (KeyError, TypeError, ValueError):
            logger.error('Sender status missing active round for campaign_id=%s', self.campaign.pk)
            return False
        if round_number < 1:
            logger.error('Sender status returned invalid round for campaign_id=%s', self.campaign.pk)
            return False

        try:
            response = requests.post(
                f'{sender_api}/sender/stop',
                json={'campaign_id': self.campaign.pk, 'round_number': round_number},
                timeout=5,
            )
        except requests.RequestException:
            logger.exception('Could not stop sender for campaign_id=%s', self.campaign.pk)
            return False
        if response.status_code not in (200, 404):
            logger.error(
                'Sender stop returned HTTP %s for campaign_id=%s: %s',
                response.status_code, self.campaign.pk, response.text[:300],
            )
            return False
        return True

    def activate_campaign(self, build_messages=True):
        if self.campaign.status != 'draft':
            return {
                'success': False,
                'message': f"Cannot activate campaign in '{self.campaign.status}' status.",
                'errors': [f"Activation requires draft status; current status is '{self.campaign.status}'."],
            }
        report = self.validate_campaign()
        if not report['is_ready']:
            return {
                'success': False,
                'message': 'Campaign is not ready for activation.',
                **{key: report[key] for key in ('errors', 'warnings', 'stats')},
            }
        build_result = None
        try:
            queued_messages_exist = self.campaign.messages.filter(sent_status__in=['PENDING', 'FAILED']).exists()
            if build_messages and not queued_messages_exist:
                build_result = MessageBuilder(campaign=self.campaign).build()
                if build_result['built'] < 1:
                    raise ValueError('No messages were built for this campaign.')

            with transaction.atomic():
                if not build_messages and not self.campaign.messages.exists():
                    raise ValueError('No queued messages exist; build messages before activating.')
                self.campaign.status = 'active'
                self.campaign.is_ready_to_execute = True
                self.campaign.activated_at = timezone.now()
                self.campaign.save(update_fields=['status', 'is_ready_to_execute', 'activated_at', 'updated_at'])
                schedule = getattr(self.campaign, 'schedule', None)
                if schedule:
                    schedule.is_active = True
                    schedule.schedule_status = 'active'
                    schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        except ValueError as exc:
            return {
                'success': False,
                'message': 'Campaign could not be activated because messages could not be built.',
                'errors': [str(exc)],
                'warnings': report['warnings'],
                'stats': report['stats'],
            }
        owner_notification_sent = send_campaign_activation_email(self.campaign)
        return {
            'success': True,
            'message': 'Campaign activated successfully.',
            'data': {
                'campaign_id': self.campaign.id,
                'status': self.campaign.status,
                'messages_built': build_result['built'] if build_result else 0,
                'owner_notification_sent': owner_notification_sent,
            },
            'warnings': report['warnings'],
        }

    def deactivate_campaign(self):
        if self.campaign.status not in {'active', 'stopped'}:
            return {'success': False, 'message': f"Cannot deactivate campaign in '{self.campaign.status}' status."}
        if self.campaign.status == 'active' and not self._stop_sender():
            return {'success': False, 'message': 'Could not stop the campaign sender; campaign was not deactivated.'}
        self.campaign.status = 'draft'
        self.campaign.save(update_fields=['status', 'updated_at'])
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule:
            schedule.is_active = False
            schedule.schedule_status = 'paused'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {'success': True, 'message': 'Campaign deactivated successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def restart_campaign(self):
        if self.campaign.status != 'stopped':
            return {'success': False, 'message': f"Cannot restart campaign in '{self.campaign.status}' status."}
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule is None:
            return {'success': False, 'message': 'Cannot restart campaign without a schedule.'}
        if not self.campaign.refresh_readiness_flag():
            return {'success': False, 'message': 'Campaign is not ready to execute; deactivate it and activate it again.'}

        # Rebuild this scheduled round before reactivating so the sender has a
        # fresh PENDING queue. Reuse a stable batch ID so retrying a restart
        # replaces the previous restart build for this round.
        round_number = max(schedule.current_round, 1)
        batch_id = f'campaign-{self.campaign.pk}-round-{round_number}'
        try:
            build_result = MessageBuilder(
                campaign=self.campaign,
                round_number=round_number,
                batch_id=batch_id,
            ).build()
            if build_result['built'] < 1:
                raise ValueError('No messages were built for this campaign.')
        except Exception as exc:
            logger.exception('Could not rebuild messages for restarted campaign_id=%s', self.campaign.pk)
            return {
                'success': False,
                'message': 'Campaign could not be restarted because messages could not be rebuilt.',
                'errors': [str(exc)],
            }

        with transaction.atomic():
            self.campaign.status = 'active'
            self.campaign.save(update_fields=['status', 'updated_at'])
            schedule.is_active = True
            schedule.schedule_status = 'active'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {
            'success': True,
            'message': 'Campaign messages rebuilt as pending and its schedule reactivated.',
            'data': {
                'campaign_id': self.campaign.id,
                'status': self.campaign.status,
                'round_number': round_number,
                'messages_built': build_result['built'],
            },
        }

    def pause_campaign(self):
        if self.campaign.status != 'in_progress':
            return {'success': False, 'message': f"Cannot pause campaign in '{self.campaign.status}' status."}
        if not self._stop_sender():
            return {'success': False, 'message': 'Could not stop the campaign sender; campaign remains in progress.'}
        self.campaign.status = 'paused'
        self.campaign.paused_at = timezone.now()
        self.campaign.save(update_fields=['status', 'paused_at', 'updated_at'])
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule:
            schedule.is_active = False
            schedule.schedule_status = 'paused'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {'success': True, 'message': 'Campaign paused successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def resume_campaign(self):
        if self.campaign.status != 'paused':
            return {'success': False, 'message': f"Cannot resume campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'active'
        self.campaign.resumed_at = timezone.now()
        self.campaign.save(update_fields=['status', 'resumed_at', 'updated_at'])
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule:
            schedule.is_active = True
            schedule.schedule_status = 'active'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {'success': True, 'message': 'Campaign resumed and will run in its next scheduled window.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def complete_campaign(self):
        if self.campaign.status not in {'active', 'in_progress', 'paused'}:
            return {'success': False, 'message': f"Cannot complete campaign in '{self.campaign.status}' status."}
        if not self._stop_sender():
            return {'success': False, 'message': 'Could not stop the campaign sender; campaign was not completed.'}
        self.campaign.status = 'completed'
        self.campaign.completed_at = timezone.now()
        self.campaign.save(update_fields=['status', 'completed_at', 'updated_at'])
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule:
            schedule.is_active = False
            schedule.schedule_status = 'completed'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {'success': True, 'message': 'Campaign completed successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def cancel_campaign(self):
        if self.campaign.status not in ('active', 'in_progress', 'paused'):
            return {'success': False, 'message': f"Cannot cancel campaign in '{self.campaign.status}' status."}
        if self.campaign.status in {'active', 'in_progress'} and not self._stop_sender():
            return {'success': False, 'message': 'Could not stop the campaign sender; campaign was not stopped.'}
        self.campaign.status = 'stopped'
        self.campaign.stopped_at = timezone.now()
        self.campaign.save(update_fields=['status', 'stopped_at', 'updated_at'])
        schedule = getattr(self.campaign, 'schedule', None)
        if schedule:
            schedule.is_active = False
            schedule.schedule_status = 'stopped'
            schedule.save(update_fields=['is_active', 'schedule_status', 'updated_at'])
        return {'success': True, 'message': 'Campaign stopped successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def archive_campaign(self):
        if self.campaign.status != 'completed':
            return {'success': False, 'message': f"Cannot archive campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'archived'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign archived successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}
