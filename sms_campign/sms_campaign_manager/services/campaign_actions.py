"""Campaign lifecycle actions."""

from django.db import transaction
from django.utils import timezone

from .campaign_readiness import CampaignReadinessService
from .campaign_activation_email import send_campaign_activation_email
from .message_builder import MessageBuilder


class CampaignActionsService:
    def __init__(self, campaign):
        self.campaign = campaign

    def validate_campaign(self):
        return CampaignReadinessService(self.campaign).check()

    def activate_campaign(self, build_messages=True):
        report = self.validate_campaign()
        if not report['is_ready']:
            return {
                'success': False,
                'message': 'Campaign is not ready for activation.',
                **{key: report[key] for key in ('errors', 'warnings', 'stats')},
            }
        build_result = None
        try:
            if build_messages:
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

    def pause_campaign(self):
        if self.campaign.status != 'in_progress':
            return {'success': False, 'message': f"Cannot pause campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'paused'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign paused successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def start_campaign(self):
        if self.campaign.status != 'active':
            return {'success': False, 'message': f"Cannot start campaign in '{self.campaign.status}' status."}
        if not self.campaign.is_ready_to_execute:
            return {'success': False, 'message': 'Campaign is not ready to execute.'}
        if not self.campaign.messages.filter(sent_status__in=['PENDING', 'FAILED']).exists():
            return {'success': False, 'message': 'Campaign has no queued messages to send.'}
        self.campaign.status = 'in_progress'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign sending started.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def resume_campaign(self):
        if self.campaign.status != 'paused':
            return {'success': False, 'message': f"Cannot resume campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'in_progress'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign resumed successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def complete_campaign(self):
        if self.campaign.status != 'in_progress':
            return {'success': False, 'message': f"Cannot complete campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'completed'
        self.campaign.completed_at = timezone.now()
        self.campaign.save(update_fields=['status', 'completed_at', 'updated_at'])
        return {'success': True, 'message': 'Campaign completed successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def cancel_campaign(self):
        if self.campaign.status not in ('active', 'in_progress', 'paused'):
            return {'success': False, 'message': f"Cannot cancel campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'stopped'
        self.campaign.stopped_at = timezone.now()
        self.campaign.save(update_fields=['status', 'stopped_at', 'updated_at'])
        return {'success': True, 'message': 'Campaign cancelled successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}
