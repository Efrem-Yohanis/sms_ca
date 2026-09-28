"""Readiness checks for Campaign lifecycle actions."""

from django.core.exceptions import ValidationError


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

        try:
            schedule = campaign.schedule
        except AttributeError:
            schedule = None
        stats['has_schedule'] = schedule is not None
        if schedule is None:
            errors.append('Schedule is missing.')
        else:
            stats['schedule_type'] = schedule.schedule_type
            try:
                schedule.full_clean()
            except ValidationError as exc:
                messages = exc.message_dict.values() if hasattr(exc, 'message_dict') else [exc.messages]
                errors.extend(
                    f'Schedule configuration is invalid: {message}'
                    for field_messages in messages
                    for message in (field_messages if isinstance(field_messages, list) else [field_messages])
                )

        return {'is_ready': not errors, 'errors': errors, 'warnings': warnings, 'stats': stats}
