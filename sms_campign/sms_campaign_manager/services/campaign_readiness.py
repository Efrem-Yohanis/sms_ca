"""Readiness checks for Campaign lifecycle actions."""


class CampaignReadinessService:
    def __init__(self, campaign):
        self.campaign = campaign

    def check(self):
        errors = []
        warnings = []
        stats = {}
        campaign = self.campaign

        if campaign.is_deleted:
            errors.append('Campaign is deleted.')
        if campaign.status != 'draft':
            errors.append(f"Campaign must be in 'draft' status to be activated (current: '{campaign.status}').")
        if not campaign.name.strip():
            errors.append('Campaign name is empty.')
        if not campaign.sender_id.strip():
            errors.append('Sender ID is empty.')
        if not campaign.channels:
            errors.append('At least one channel is required.')

        try:
            content = campaign.message_content
        except AttributeError:
            content = None
        if content is None:
            errors.append('Message content is missing.')
        elif not content.has_any_content():
            errors.append('Message content is empty for all languages.')
        elif not content.has_language(content.default_language):
            errors.append(f"Default language '{content.default_language}' has no content.")
        else:
            stats['available_languages'] = content.languages_with_content()

        audience = campaign.audience_members.filter(is_valid=True)
        if not audience.exists():
            errors.append('Audience is missing.')
            stats['has_audience'] = False
        else:
            stats['has_audience'] = True

        warnings.append('No schedule configured. Campaign will not run automatically.')
        stats['has_schedule'] = hasattr(campaign, 'schedule')
        if stats['has_schedule']:
            stats['schedule_type'] = campaign.schedule.schedule_type

        return {'is_ready': not errors, 'errors': errors, 'warnings': warnings, 'stats': stats}
