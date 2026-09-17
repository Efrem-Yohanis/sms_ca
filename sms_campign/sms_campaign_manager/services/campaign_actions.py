"""Campaign lifecycle actions."""

from django.db import transaction
from django.utils import timezone

from .campaign_readiness import CampaignReadinessService


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
        built = 0
        with transaction.atomic():
            self.campaign.status = 'active'
            self.campaign.activated_at = timezone.now()
            self.campaign.save(update_fields=['status', 'activated_at', 'updated_at'])
        return {
            'success': True,
            'message': 'Campaign activated successfully.',
            'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status, 'messages_built': built},
            'warnings': report['warnings'],
        }

    def pause_campaign(self):
        if self.campaign.status != 'active':
            return {'success': False, 'message': f"Cannot pause campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'paused'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign paused successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def resume_campaign(self):
        if self.campaign.status != 'paused':
            return {'success': False, 'message': f"Cannot resume campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'active'
        self.campaign.save(update_fields=['status', 'updated_at'])
        return {'success': True, 'message': 'Campaign resumed successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def complete_campaign(self):
        if self.campaign.status not in ('active', 'paused'):
            return {'success': False, 'message': f"Cannot complete campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'completed'
        self.campaign.completed_at = timezone.now()
        self.campaign.save(update_fields=['status', 'completed_at', 'updated_at'])
        return {'success': True, 'message': 'Campaign completed successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}

    def cancel_campaign(self):
        if self.campaign.status in ('completed', 'stopped'):
            return {'success': False, 'message': f"Cannot cancel campaign in '{self.campaign.status}' status."}
        self.campaign.status = 'stopped'
        self.campaign.stopped_at = timezone.now()
        self.campaign.save(update_fields=['status', 'stopped_at', 'updated_at'])
        return {'success': True, 'message': 'Campaign cancelled successfully.', 'data': {'campaign_id': self.campaign.id, 'status': self.campaign.status}}
