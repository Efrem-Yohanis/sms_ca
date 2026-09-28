# campaign_manager/models.py

"""
Database models for Campaign Manager.

All tables, relations, and constraints.
"""

import base64
import uuid
from datetime import datetime, date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .constants import (
    CAMPAIGN_STATUS_CHOICES,
    SCHEDULE_TYPE_CHOICES,
    DATABASE_TYPE_CHOICES,
    SENT_STATUS_CHOICES,
    SENT_TERMINAL_STATUSES,
    DELIVERY_STATUS_CHOICES,
    DELIVERY_TERMINAL_STATUSES,
    SOURCE_TYPE_CHOICES,
    LANGUAGE_SOURCE_CHOICES,
)
from .fields import EncryptedCharField


# ============================================================================
# REFERENCE TABLES
# ============================================================================

class Channel(models.Model):
    """A delivery channel (SMS, Flash SMS, App Notification)."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Channel'
        verbose_name_plural = 'Channels'

    def __str__(self):
        return f'{self.name} ({self.code})'

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().lower()
        self.name = (self.name or '').strip()
        super().save(*args, **kwargs)
        cache.delete('active_channel_ids')


class Language(models.Model):
    """A language supported for campaign content."""

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Language'
        verbose_name_plural = 'Languages'

    def __str__(self):
        return f'{self.name} ({self.code})'

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().lower()
        self.name = (self.name or '').strip()
        super().save(*args, **kwargs)
        cache.delete('active_language_ids')


class SenderID(models.Model):
    """
    Sender ID available for use in campaigns.
    Selected at campaign creation time.

    Independent of Channel. Campaign.sender_id is validated against this
    table's active rows in Campaign.clean() — see fix note there.
    """

    id = models.BigAutoField(primary_key=True)
    sender_id = models.CharField(
        max_length=11,
        unique=True,
        db_index=True,
        help_text="The actual sender ID shown to end users (e.g., SMSINFO)",
    )
    name = models.CharField(
        max_length=100,
        help_text="Friendly name (e.g., 'Marketing Sender')",
    )
    description = models.TextField(blank=True, default='')

    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_sender_ids',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'sender_id']
        verbose_name = 'Sender ID'
        verbose_name_plural = 'Sender IDs'
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_default']),
        ]

    def __str__(self):
        return self.sender_id

    def clean(self):
        errors = {}

        if not self.sender_id or not self.sender_id.strip():
            errors['sender_id'] = 'Sender ID is required.'
        else:
            sid = self.sender_id.strip()
            if not (3 <= len(sid) <= 11):
                errors['sender_id'] = 'Sender ID must be 3–11 characters.'
            elif not sid.replace('_', '').isalnum():
                errors['sender_id'] = (
                    'Sender ID can only contain letters, numbers, and underscores.'
                )

        if not self.name or not self.name.strip():
            errors['name'] = 'Name is required.'

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.sender_id = (self.sender_id or '').strip()
        self.name = (self.name or '').strip()

        if self.is_default:
            SenderID.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False,
            )

        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)


class SMSCConfig(models.Model):
    """
    SMSC API configuration — connection, credentials,
    rate limits, and sending behavior.
    """

    AUTH_TYPE_CHOICES = [
        ('none', 'None'),
        ('api_key', 'API Key'),
        ('bearer', 'Bearer Token'),
        ('basic', 'Basic Auth'),
    ]

    HTTP_METHOD_CHOICES = [
        ('POST', 'POST'),
        ('GET', 'GET'),
        ('PUT', 'PUT'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default='')

    # ==================== CONNECTION ====================
    base_url = models.URLField(
        max_length=500,
        help_text="SMSC API base URL (e.g., https://smsc.example.com)",
    )
    send_endpoint = models.CharField(
        max_length=255,
        default='/api/send',
        help_text="Path for sending SMS",
    )
    http_method = models.CharField(
        max_length=10,
        choices=HTTP_METHOD_CHOICES,
        default='POST',
    )

    # ==================== AUTHENTICATION ====================
    auth_type = models.CharField(
        max_length=20,
        choices=AUTH_TYPE_CHOICES,
        default='api_key',
    )
    api_key = EncryptedCharField(max_length=500, blank=True, default='')
    api_secret = EncryptedCharField(max_length=500, blank=True, default='')
    username = models.CharField(max_length=255, blank=True, default='')
    password = EncryptedCharField(max_length=500, blank=True, default='')

    # ==================== EXTRA ====================
    extra_headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional HTTP headers",
    )
    extra_params = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional body/query params",
    )

    # ==================== RATE LIMITS ====================
    rate_limit_per_second = models.PositiveIntegerField(
        default=100,
        help_text="Max requests per second",
    )
    rate_limit_per_minute = models.PositiveIntegerField(
        default=3000,
        help_text="Max requests per minute",
    )
    max_retries = models.PositiveSmallIntegerField(
        default=3,
        help_text="Max retry attempts per message",
    )
    retry_backoff_seconds = models.PositiveIntegerField(
        default=5,
        help_text="Seconds between retries",
    )

    # ==================== TIMEOUTS ====================
    request_timeout_seconds = models.PositiveIntegerField(default=30)
    connect_timeout_seconds = models.PositiveIntegerField(default=10)

    # ==================== STATUS ====================
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # ==================== HEALTH ====================
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, default='')
    last_test_message = models.TextField(blank=True, default='')

    # ==================== AUDIT ====================
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_smsc_configs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'SMSC Configuration'
        verbose_name_plural = 'SMSC Configurations'
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['is_default']),
        ]

    def __str__(self):
        return f'{self.name} ({self.base_url})'

    def get_full_send_url(self) -> str:
        base = (self.base_url or '').rstrip('/')
        endpoint = (self.send_endpoint or '').strip()
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        return f'{base}{endpoint}'

    def get_auth_headers(self) -> dict:
        headers = {}

        if self.auth_type == 'api_key' and self.api_key:
            headers['X-API-Key'] = self.api_key
        elif self.auth_type == 'bearer' and self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'
        elif self.auth_type == 'basic':
            credentials = f'{self.username}:{self.password}'
            encoded = base64.b64encode(credentials.encode()).decode()
            headers['Authorization'] = f'Basic {encoded}'

        return headers

    def get_headers(self) -> dict:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        headers.update(self.get_auth_headers())
        headers.update(self.extra_headers or {})
        return headers

    def clean(self):
        errors = {}

        if not self.name or not self.name.strip():
            errors['name'] = 'Name is required.'

        if not self.base_url or not self.base_url.strip():
            errors['base_url'] = 'Base URL is required.'

        if self.rate_limit_per_second <= 0:
            errors['rate_limit_per_second'] = 'Must be greater than 0.'

        if self.rate_limit_per_minute <= 0:
            errors['rate_limit_per_minute'] = 'Must be greater than 0.'

        if self.request_timeout_seconds <= 0:
            errors['request_timeout_seconds'] = 'Must be greater than 0.'

        # FIX: previously auth_type could be 'api_key'/'bearer'/'basic' with
        # no actual credentials set, which passed validation and then
        # silently produced broken auth headers (e.g. "Basic <base64 of ':'>")
        # at send time. Validate credentials match the chosen auth_type.
        if self.auth_type in ('api_key', 'bearer') and not (self.api_key or '').strip():
            errors['api_key'] = (
                f"API key is required when auth_type is '{self.auth_type}'."
            )
        elif self.auth_type == 'basic':
            if not (self.username or '').strip():
                errors['username'] = "Username is required when auth_type is 'basic'."
            if not (self.password or '').strip():
                errors['password'] = "Password is required when auth_type is 'basic'."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        self.base_url = (self.base_url or '').strip()

        if self.is_default:
            SMSCConfig.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False,
            )

        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)


class EmailConfig(models.Model):
    """SMTP connection settings used for campaign notification emails."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default='')
    host = models.CharField(max_length=255, default='smtp.example.com')
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, blank=True, default='')
    password = EncryptedCharField(max_length=500, blank=True, default='')
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    default_from_email = models.EmailField(default='no-reply@example.com')
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, default='')
    last_test_message = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='email_configs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'Email Configuration'
        verbose_name_plural = 'Email Configurations'

    def __str__(self):
        return f'{self.name} ({self.host}:{self.port})'

    def clean(self):
        errors = {}
        if not self.name or not self.name.strip():
            errors['name'] = 'Name is required.'
        if not self.host or not self.host.strip():
            errors['host'] = 'Host is required.'
        if not 1 <= self.port <= 65535:
            errors['port'] = 'Port must be between 1 and 65535.'
        if not self.default_from_email:
            errors['default_from_email'] = 'Default sender email is required.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        self.host = (self.host or '').strip()
        self.default_from_email = (self.default_from_email or '').strip()
        if self.is_default:
            EmailConfig.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False,
            )
        if not self.use_tls and self.use_ssl:
            self.use_tls = False
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)


class CampaignProgressReport(models.Model):
    """Reusable scheduled HTML progress report for one or more campaigns."""

    FREQUENCY_CHOICES = [
        ('10_minutes', 'Every 10 minutes'),
        ('hourly', 'Every hour'),
        ('daily', 'Daily'),
    ]

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=150, unique=True)
    campaigns = models.ManyToManyField(
        'Campaign', related_name='progress_reports', blank=False,
    )
    recipients = models.JSONField(default=list)
    include_campaign_owners = models.BooleanField(default=False)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    is_active = models.BooleanField(default=True, db_index=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='campaign_progress_reports',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class EmailReport(models.Model):
    """Log of email reports sent for a campaign."""

    REPORT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='email_reports',
        db_index=True,
    )
    report_type = models.CharField(max_length=50, default='campaign_summary')
    subject = models.CharField(max_length=255)
    recipients = models.JSONField(default=list, blank=True)
    content = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=REPORT_STATUS_CHOICES, default='pending')
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Report'
        verbose_name_plural = 'Email Reports'

    def __str__(self):
        return f'{self.subject} ({self.status})'


class ReportSubscription(models.Model):
    """Campaign report recipients and delivery preferences."""

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('on_completion', 'On completion'),
        ('manual', 'Manual'),
    ]
    FORMAT_CHOICES = [
        ('text', 'Plain text'),
        ('html', 'HTML'),
        ('csv', 'CSV'),
        ('pdf', 'PDF'),
    ]

    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.CASCADE,
        related_name='report_subscriptions',
        null=True,
        blank=True,
    )
    recipients = models.JSONField(default=list)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='manual')
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default='html')
    include_sent_stats = models.BooleanField(default=True)
    include_delivery_stats = models.BooleanField(default=True)
    include_message_stats = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='report_subscriptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Report subscription #{self.pk} ({self.frequency})'


class ReportDeliveryLog(models.Model):
    """Snapshot of a campaign report delivery attempt."""

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    id = models.BigAutoField(primary_key=True)
    subscription = models.ForeignKey(
        ReportSubscription,
        on_delete=models.SET_NULL,
        related_name='delivery_logs',
        null=True,
        blank=True,
    )
    campaign = models.ForeignKey(
        'Campaign',
        on_delete=models.SET_NULL,
        related_name='report_delivery_logs',
        null=True,
        blank=True,
    )
    email_config = models.ForeignKey(
        EmailConfig,
        on_delete=models.SET_NULL,
        related_name='report_delivery_logs',
        null=True,
        blank=True,
    )
    recipients = models.JSONField(default=list)
    format = models.CharField(max_length=10, choices=ReportSubscription.FORMAT_CHOICES)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='failed')
    error_message = models.TextField(blank=True, default='')
    attachment_names = models.JSONField(default=list, blank=True)
    report_data = models.JSONField(default=dict, blank=True)
    subject = models.CharField(max_length=255, blank=True, default='')
    content = models.TextField(blank=True, default='')
    include_sent_stats = models.BooleanField(default=True)
    include_delivery_stats = models.BooleanField(default=True)
    include_message_stats = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['campaign', '-created_at'], name='sms_campaig_campaig_3687b0_idx')]

    def __str__(self):
        return f'Report delivery #{self.pk} ({self.status})'


# ============================================================================
# DATABASE CONFIG (external DB connections)
# ============================================================================

class DatabaseConfig(models.Model):
    """Configuration for an external database."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default='')
    database_type = models.CharField(
        max_length=20, choices=DATABASE_TYPE_CHOICES, default='postgresql',
    )
    host = models.CharField(max_length=255, default='localhost')
    port = models.PositiveIntegerField(default=5432)
    database_name = models.CharField(max_length=255)
    username = models.CharField(max_length=255, blank=True, default='')

    password = EncryptedCharField(max_length=500, blank=True, default='')

    ssl_required = models.BooleanField(default=False)
    extra_options = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, default='')
    last_test_message = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='database_configs',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Database Configuration'
        verbose_name_plural = 'Database Configurations'

    def __str__(self):
        return f'{self.name} ({self.database_type}://{self.host}:{self.port}/{self.database_name})'

    def get_connection_string(self) -> str:
        return (
            f'{self.database_type}://{self.username}@'
            f'{self.host}:{self.port}/{self.database_name}'
        )

    def clean(self):
        errors = {}
        if not self.name or not self.name.strip():
            errors['name'] = 'Name is required.'
        if not self.database_name or not self.database_name.strip():
            errors['database_name'] = 'Database name is required.'
        if not (1 <= self.port <= 65535):
            errors['port'] = 'Port must be between 1 and 65535.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.name = (self.name or '').strip()
        self.host = (self.host or '').strip()
        self.database_name = (self.database_name or '').strip()
        self.username = (self.username or '').strip()
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)


# ============================================================================
# CAMPAIGN (MASTER)
# ============================================================================

class Campaign(models.Model):
    """
    Master campaign table — configuration.

    No FK to children. Children reference Campaign via their own FK.
    """

    # ==================== IDENTITY ====================
    id = models.BigAutoField(primary_key=True)

    name = models.CharField(
        max_length=255,
        help_text="Campaign name (e.g., 'New Year Promotion 2025')",
    )
    sender_id = models.CharField(
        max_length=11,
        help_text="Sender ID (e.g., SMSINFO, MPESA)",
    )
    owner_emails = models.JSONField(
        default=list,
        blank=True,
        help_text='Email addresses that receive campaign notifications',
    )

    # ==================== CHANNELS ====================
    # NOTE ON DESIGN: this is a denormalized JSONField list of Channel IDs,
    # not a ForeignKey/ManyToMany. That's a deliberate tradeoff (preserves
    # explicit ordering, avoids an M2M through-table) but it means there is
    # NO database-level referential integrity: if a Channel row is hard
    # deleted, any campaign referencing its ID silently loses that channel
    # from `channels` (the property just filters it out) rather than
    # erroring or cascading. clean() below only checks IDs at save time —
    # it can't protect against a Channel being deleted afterward. If that
    # silent-drop behavior isn't acceptable, switch to a ManyToManyField
    # instead.
    channels_id = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Channel IDs: [1, 2]",
    )

    # ==================== STATUS ====================
    status = models.CharField(
        max_length=20,
        choices=CAMPAIGN_STATUS_CHOICES,
        default='draft',
        db_index=True,
        help_text="draft / active / paused / stopped / completed / cancelled",
    )

    is_ready_to_execute = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True when campaign has channels, audience, schedule, and content",
    )

    # ==================== TIMING ====================
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)

    # ==================== AUDIT ====================
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns',
    )
    activated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activated_campaigns',
    )

    # ==================== SOFT DELETE ====================
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['is_ready_to_execute']),
            models.Index(fields=['status', 'is_ready_to_execute']),
            models.Index(fields=['is_deleted']),
            models.Index(fields=['created_by']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'{self.name} (#{self.id}) — {self.status}'

    # ==================== PROPERTIES ====================

    @property
    def channels(self):
        ids = self.channels_id or []
        if not ids:
            return Channel.objects.none()
        return Channel.objects.filter(id__in=ids)

    @property
    def channel_codes(self):
        return list(self.channels.values_list('code', flat=True))

    @property
    def has_audience(self) -> bool:
        return self.audience_members.filter(is_valid=True).exists()

    @property
    def has_schedule(self) -> bool:
        return hasattr(self, 'schedule')

    @property
    def has_message_content(self) -> bool:
        return hasattr(self, 'message_content')

    @property
    def has_messages(self) -> bool:
        return self.messages.exists()

    @property
    def execution_status(self) -> str:
        return {
            'draft': 'PENDING',
            'active': 'PENDING',
            'in_progress': 'PROCESSING',
            'paused': 'PAUSED',
            'stopped': 'STOPPED',
            'completed': 'COMPLETED',
            'invalid_schedule': 'FAILED',
            'archived': 'COMPLETED',
        }.get(self.status, 'PENDING')

    @property
    def is_ready_for_activation(self) -> bool:
        return (
            self.status == 'draft'
            and bool(self.channels_id)
            and self.has_audience
            and self.has_schedule
            and self.has_message_content
        )

    def refresh_readiness_flag(self, save: bool = True):
        new_value = self.is_ready_for_activation
        if self.is_ready_to_execute != new_value:
            self.is_ready_to_execute = new_value
            if save:
                self.save(update_fields=['is_ready_to_execute', 'updated_at'])
        return new_value

    # ==================== VALIDATION ====================

    def clean(self):
        errors = {}

        if not self.name or not self.name.strip():
            errors['name'] = 'Campaign name is required.'
        elif len(self.name.strip()) > 255:
            errors['name'] = 'Campaign name must be ≤ 255 characters.'

        if not self.sender_id or not self.sender_id.strip():
            errors['sender_id'] = 'Sender ID is required.'
        else:
            sid = self.sender_id.strip()
            if not (3 <= len(sid) <= 11):
                errors['sender_id'] = 'Sender ID must be 3–11 characters.'
            elif not sid.replace('_', '').isalnum():
                errors['sender_id'] = (
                    'Sender ID can only contain letters, numbers, and underscores.'
                )
            # FIX: SenderID table existed but nothing checked Campaign.sender_id
            # against it, so a campaign could use a sender ID that was never
            # registered, or was deactivated. Enforce the link here.
            elif not SenderID.objects.filter(sender_id=sid, is_active=True).exists():
                errors['sender_id'] = (
                    f"'{sid}' is not a registered, active Sender ID. "
                    "Add or activate it under Sender ID management first."
                )

        if not self.channels_id:
            errors['channels_id'] = 'At least one channel is required.'
        elif not isinstance(self.channels_id, list):
            errors['channels_id'] = 'channels_id must be a list of Channel IDs.'
        else:
            active_ids = cache.get('active_channel_ids')
            if active_ids is None:
                active_ids = set(
                    Channel.objects.filter(is_active=True).values_list('id', flat=True)
                )
                cache.set('active_channel_ids', active_ids, 300)
            invalid = [cid for cid in self.channels_id if cid not in active_ids]
            if invalid:
                errors['channels_id'] = (
                    f'Invalid or inactive channel IDs: {invalid}. '
                    f'Active IDs: {sorted(active_ids)}'
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, update_fields=None, **kwargs):
        self.name = (self.name or '').strip()
        self.sender_id = (self.sender_id or '').strip()

        # FIX: previously this normalized channels_id unconditionally, even
        # on a save(update_fields=[...]) call that didn't include
        # 'channels_id'. That meant the in-memory instance would show a
        # cleaned/sorted value that was never actually written to the row —
        # any code inspecting `campaign.channels_id` right after such a
        # partial save would see a value that disagrees with the database.
        # Only normalize when channels_id is actually part of what's being
        # persisted.
        if isinstance(self.channels_id, list) and (
            update_fields is None or 'channels_id' in update_fields
        ):
            try:
                self.channels_id = sorted(set(int(x) for x in self.channels_id if x))
            except (TypeError, ValueError):
                pass

        if update_fields is None:
            self.full_clean(validate_unique=False)

        super().save(*args, update_fields=update_fields, **kwargs)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])


# ============================================================================
# MESSAGE CONTENT (1:1 with Campaign)
# ============================================================================

class MessageContent(models.Model):
    """Multi-language message content template for one campaign."""

    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name='message_content',
    )
    en = models.TextField(blank=True, default='')
    am = models.TextField(blank=True, default='')
    ti = models.TextField(blank=True, default='')
    om = models.TextField(blank=True, default='')
    so = models.TextField(blank=True, default='')

    default_language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name='default_for_message_contents',
        help_text="Fallback language when recipient's language has no content",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Message Content'
        verbose_name_plural = 'Message Contents'

    def __str__(self):
        return f'Content for {self.campaign.name}'

    def get_content_dict(self):
        return {
            'en': self.en, 'am': self.am, 'ti': self.ti,
            'om': self.om, 'so': self.so,
        }

    def get_message(self, language_code=None):
        if not language_code:
            language_code = self.default_language.code
        content = (self.get_content_dict().get(language_code) or '').strip()
        if not content:
            content = (
                self.get_content_dict().get(self.default_language.code) or ''
            ).strip()
        return content

    def has_any_content(self) -> bool:
        return any((c or '').strip() for c in self.get_content_dict().values())

    def languages_with_content(self) -> list:
        return [
            code for code, text in self.get_content_dict().items()
            if (text or '').strip()
        ]

    def has_language(self, language) -> bool:
        language_code = getattr(language, 'code', language)
        return bool((self.get_content_dict().get(language_code) or '').strip())


# ============================================================================
# SCHEDULE (1:1 with Campaign)
# ============================================================================

class Schedule(models.Model):
    """One-time or recurring schedule for a campaign."""

    SCHEDULE_STATE_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('stopped', 'Stopped'),
        ('completed', 'Completed'),
    ]

    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name='schedule',
    )
    schedule_type = models.CharField(
        max_length=20, choices=SCHEDULE_TYPE_CHOICES, default='once',
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    run_days = models.JSONField(default=list, blank=True)
    time_windows = models.JSONField(default=list)
    timezone = models.CharField(max_length=50, default='UTC')
    auto_reset = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    schedule_status = models.CharField(
        max_length=20, choices=SCHEDULE_STATE_CHOICES, default='active',
    )
    current_round = models.PositiveIntegerField(default=0)
    next_run_date = models.DateField(null=True, blank=True, db_index=True)
    last_processed_at = models.DateTimeField(null=True, blank=True)
    completed_windows = models.JSONField(default=list, blank=True)
    total_windows_completed = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_date', 'created_at']
        verbose_name = 'Schedule'
        verbose_name_plural = 'Schedules'
        indexes = [
            models.Index(fields=['schedule_type', 'next_run_date']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'Schedule for {self.campaign.name} — {self.schedule_type}'

    def get_schedule_summary(self) -> str:
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday', 'Sunday']
        if self.schedule_type == 'once':
            start = self.time_windows[0]['start'] if self.time_windows else '-'
            return f'One-time on {self.start_date} at {start}'
        if self.schedule_type == 'daily':
            label = 'Every day'
        elif self.schedule_type == 'weekly':
            label = 'Every ' + ', '.join(days[i] for i in sorted(self.run_days))
        else:
            label = f'Monthly on day {self.start_date.day}'
        windows = ', '.join(
            f"{w['start']}-{w['end']}" for w in self.time_windows
        ) or '-'
        date_range = f'from {self.start_date}' + (
            f' to {self.end_date}' if self.end_date else ''
        )
        return f'{label} at {windows} {date_range}'

    @staticmethod
    def _windows_overlap(a_start, a_end, b_start, b_end) -> bool:
        return a_start < b_end and b_start < a_end

    def clean(self):
        errors = {}
        valid_types = [c for c, _ in SCHEDULE_TYPE_CHOICES]
        if self.schedule_type not in valid_types:
            errors['schedule_type'] = f'Invalid schedule type. Valid: {valid_types}'
        if self.end_date and self.start_date and self.start_date > self.end_date:
            errors['end_date'] = 'End date must be on or after start date.'
        if (self.schedule_type == 'once' and self.start_date
                and self.start_date < date.today()):
            errors['start_date'] = 'Start date cannot be in the past for one-time.'

        if not isinstance(self.time_windows, list) or not self.time_windows:
            errors['time_windows'] = 'At least one time window is required.'
        else:
            parsed = []
            for i, w in enumerate(self.time_windows):
                if not isinstance(w, dict) or 'start' not in w or 'end' not in w:
                    errors['time_windows'] = f'Window {i} must contain start and end.'
                    break
                try:
                    s = datetime.strptime(w['start'], '%H:%M').time()
                    e = datetime.strptime(w['end'], '%H:%M').time()
                except (TypeError, ValueError):
                    errors['time_windows'] = f'Window {i} must use HH:MM.'
                    break
                if s >= e:
                    errors['time_windows'] = f'Window {i} has start >= end.'
                    break
                if any(self._windows_overlap(s, e, ps, pe) for ps, pe in parsed):
                    errors['time_windows'] = f'Window {i} overlaps another.'
                    break
                parsed.append((s, e))

        if self.schedule_type == 'weekly':
            if not isinstance(self.run_days, list) or not self.run_days:
                errors['run_days'] = 'Weekly schedules require at least one run day.'
            elif any(day not in range(7) for day in self.run_days):
                errors['run_days'] = 'Run days must contain values 0–6.'

        if errors:
            raise ValidationError(errors)

    def sync_campaign_status(self, save: bool = True):
        """Mirror this schedule's run state onto the parent Campaign.

        FIX: schedule_status and Campaign.status were two independent
        fields with no code path keeping them aligned — a schedule could be
        'paused' while its campaign row still said 'active'. Call this
        explicitly whenever schedule_status changes (pause/resume/stop
        actions) rather than setting both fields separately at each call
        site.
        """
        mapping = {
            'active': 'active',
            'paused': 'paused',
            'stopped': 'stopped',
            'completed': 'completed',
        }
        new_status = mapping.get(self.schedule_status)
        if new_status and self.campaign.status != new_status:
            self.campaign.status = new_status
            if save:
                self.campaign.save(update_fields=['status', 'updated_at'])

    def save(self, *args, update_fields=None, **kwargs):
        if self.schedule_type != 'weekly':
            self.run_days = []
        if update_fields is None:
            self.full_clean(validate_unique=False)
        super().save(*args, update_fields=update_fields, **kwargs)


# ============================================================================
# AUDIENCE (1:N with Campaign)
# ============================================================================

class Audience(models.Model):
    """One row per recipient in a campaign.

    NOTE: at 100k+ rows per campaign, audience uploads use bulk_create(),
    which bypasses save()/clean() and Django's post_save signal entirely.
    Validate rows before bulk insertion, and call
    campaign.refresh_readiness_flag() explicitly once a bulk upload
    finishes — the post_save receiver below only fires for individual
    .save() calls.
    """

    id = models.BigAutoField(primary_key=True)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='audience_members',
        db_index=True,
    )
    msisdn = models.CharField(max_length=20, db_index=True)
    language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name='audience',
    )
    language_source = models.CharField(
        max_length=20,
        choices=LANGUAGE_SOURCE_CHOICES,
        default='default',
        db_index=True,
    )

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default='manual',
    )

    is_valid = models.BooleanField(default=True, db_index=True)
    validation_error = models.TextField(blank=True, default='')

    custom_fields = models.JSONField(default=dict, blank=True)
    sequence_number = models.PositiveIntegerField(db_index=True)
    round_number = models.PositiveIntegerField(default=1, db_index=True)
    build_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    rebuilt_at = models.DateTimeField(auto_now_add=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sequence_number']
        verbose_name = 'Audience'
        verbose_name_plural = 'Audience'
        indexes = [
            models.Index(fields=['campaign', 'round_number'], name='audience_campaign_round_idx'),
            models.Index(fields=['campaign', 'is_valid']),
            models.Index(fields=['campaign', 'language']),
            models.Index(fields=['msisdn', 'campaign']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['campaign', 'msisdn', 'round_number'],
                name='unique_campaign_msisdn',
            ),
        ]

    def __str__(self):
        return f'{self.msisdn} — {self.language.code}'


# Canonical backwards-compatible surface for the current app code and
# imported serializer/admin/service references, which expect AudienceMember
# to be present in the model namespace as the child audience entity.
AudienceMember = Audience


# ============================================================================
# MESSAGE OBJECT (1:N with Campaign) — SMSC payload
# ============================================================================

class MessageObject(models.Model):
    """
    Message object — payload sent to SMSC API.
    Built at activation time. One row per recipient.

    AUTHORITATIVE STATUS: sent_status/delivery_status on this model reflect
    the message's *current* state. SentRecord/DeliveryRecord are append-only
    attempt history — each one's save() pushes its status onto the parent
    MessageObject (see below) so the two never disagree. Don't update
    sent_status/delivery_status here directly from application code; write
    a SentRecord/DeliveryRecord instead and let that propagate.

    NOTE: like Audience, this is bulk_create()'d at scale and bypasses
    save()/clean().
    """

    id = models.BigAutoField(primary_key=True)
    message_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Globally unique message ID (msg_<campaign>_<uuid32>)",
    )

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='messages',
        db_index=True,
    )

    recipient = models.CharField(
        max_length=20,
        db_index=True,
        help_text="Recipient MSISDN",
    )
    sender_id = models.CharField(
        max_length=11,
        help_text="Sender ID shown to end users",
    )
    message_content = models.TextField(
        help_text="Fully personalized message content",
    )

    channel = models.ForeignKey(
        Channel,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='messages',
    )
    language = models.ForeignKey(
        Language,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='messages',
    )

    message_parts = models.PositiveSmallIntegerField(default=1)

    sent_status = models.CharField(
        max_length=20,
        choices=SENT_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )

    batch_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    worker_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)
    sending_started_at = models.DateTimeField(null=True, blank=True, db_index=True)

    built_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    personalized_fields = models.JSONField(default=dict, blank=True)
    send_attempts = models.PositiveSmallIntegerField(default=0)
    delivery_attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Message Object'
        verbose_name_plural = 'Message Objects'
        indexes = [
            models.Index(fields=['campaign', 'sent_status']),
            models.Index(fields=['campaign', 'delivery_status']),
            models.Index(fields=['campaign', 'batch_id']),
            models.Index(fields=['recipient', 'campaign']),
            models.Index(fields=['sent_status']),
            models.Index(fields=['delivery_status']),
            models.Index(fields=['channel']),
            models.Index(fields=['language']),
        ]

    def __str__(self):
        return f'{self.message_id} → {self.recipient} ({self.sent_status})'

    @staticmethod
    def generate_message_id(campaign_id):
        # FIX: previously used only the first 12 hex chars (48 bits) of a
        # uuid4, which is fine at moderate volume but starts to carry real
        # collision risk at very high message counts under a unique
        # constraint. Use the full 32-char hex (122 bits of randomness).
        return f'msg_{campaign_id}_{uuid.uuid4().hex}'

    def to_smsc_payload(self) -> dict:
        return {
            'campaign_id': self.campaign_id,
            'sender_id': self.sender_id,
            'recipient': self.recipient,
            'message_content': self.message_content,
        }


class MessageBuildJob(models.Model):
    STATUS_CHOICES = [
        ('RUNNING', 'Running'),
        ('SUCCEEDED', 'Succeeded'),
        ('FAILED', 'Failed'),
    ]

    id = models.BigAutoField(primary_key=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='message_build_jobs')
    batch_id = models.CharField(max_length=50, blank=True, default='')
    round_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RUNNING', db_index=True)
    phase = models.CharField(max_length=30, blank=True, default='starting')
    processed_rows = models.PositiveBigIntegerField(default=0)
    total_rows = models.PositiveBigIntegerField(default=0)
    built_rows = models.PositiveBigIntegerField(default=0)
    skipped_rows = models.PositiveBigIntegerField(default=0)
    failed_rows = models.PositiveBigIntegerField(default=0)
    percent = models.FloatField(default=0)
    error_message = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['campaign', '-created_at'], name='msgbuild_campaign_ct_idx')]
        constraints = [
            models.UniqueConstraint(
                fields=['campaign'],
                condition=models.Q(status='RUNNING'),
                name='unique_running_message_build_per_campaign',
            ),
        ]


# ============================================================================
# SENT RECORD (1:N with Campaign)
# ============================================================================

class SentRecord(models.Model):
    """One row per send attempt to SMSC (append-only history).

    FIX: save() now propagates sent_status onto the linked MessageObject so
    the two can't drift apart — see MessageObject's docstring.
    """

    id = models.BigAutoField(primary_key=True)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name='sent_records',
        db_index=True,
    )
    channel = models.ForeignKey(
        Channel,
        on_delete=models.PROTECT,
        related_name='sent_records',
        db_index=True,
    )
    message_object = models.ForeignKey(
        MessageObject,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_records',
    )

    msisdn = models.CharField(max_length=20, db_index=True)
    batch_id = models.CharField(max_length=50, blank=True, default='', db_index=True)

    submitted_at = models.DateTimeField(null=True, blank=True)

    sent_status = models.CharField(
        max_length=20,
        choices=SENT_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )

    provider_message_id = models.CharField(
        max_length=100, blank=True, default='', db_index=True,
    )
    provider_status = models.CharField(max_length=50, blank=True, default='')
    provider_response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Sent Record'
        verbose_name_plural = 'Sent Records'
        indexes = [
            models.Index(fields=['campaign', 'sent_status']),
            models.Index(fields=['batch_id', 'sent_status']),
            models.Index(fields=['provider_message_id']),
            models.Index(fields=['msisdn', 'campaign']),
            models.Index(fields=['channel']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'SentRecord #{self.id} — campaign={self.campaign_id} — {self.msisdn}'

    def is_terminal(self) -> bool:
        return self.sent_status in SENT_TERMINAL_STATUSES

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Push this attempt's status onto the parent MessageObject so it
        # stays the single source of truth for "what's this message's
        # status right now" without callers needing to update both places.
        if self.message_object_id:
            MessageObject.objects.filter(pk=self.message_object_id).update(
                sent_status=self.sent_status,
                updated_at=timezone.now(),
            )


# ============================================================================
# DELIVERY RECORD (1:N with Campaign)
# ============================================================================

class DeliveryRecord(models.Model):
    """One row per delivery report from SMSC (append-only history).

    FIX: save() now propagates delivery_status onto the linked
    MessageObject — see MessageObject's docstring and SentRecord above.
    """

    id = models.BigAutoField(primary_key=True)

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.PROTECT,
        related_name='delivery_records',
        db_index=True,
    )
    channel = models.ForeignKey(
        Channel,
        on_delete=models.PROTECT,
        related_name='delivery_records',
        db_index=True,
    )
    message_object = models.ForeignKey(
        MessageObject,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='delivery_records',
    )
    sent_record = models.ForeignKey(
        SentRecord,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='delivery_records',
    )

    msisdn = models.CharField(max_length=20, db_index=True)
    batch_id = models.CharField(max_length=50, blank=True, default='', db_index=True)

    delivered_at = models.DateTimeField(null=True, blank=True)

    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default='PENDING',
        db_index=True,
    )

    provider_status = models.CharField(max_length=50, blank=True, default='')
    provider_response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Delivery Record'
        verbose_name_plural = 'Delivery Records'
        indexes = [
            models.Index(fields=['campaign', 'delivery_status']),
            models.Index(fields=['batch_id', 'delivery_status']),
            models.Index(fields=['msisdn', 'campaign']),
            models.Index(fields=['channel']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f'DeliveryRecord #{self.id} — campaign={self.campaign_id} — {self.msisdn}'

    def is_terminal(self) -> bool:
        return self.delivery_status in DELIVERY_TERMINAL_STATUSES

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.message_object_id:
            MessageObject.objects.filter(pk=self.message_object_id).update(
                delivery_status=self.delivery_status,
                updated_at=timezone.now(),
            )


class _SendHistoryBase(models.Model):
    """Shared immutable fields for accepted and rejected SMS submissions."""

    id = models.BigAutoField(primary_key=True)
    message_id = models.CharField(max_length=100, unique=True, db_index=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, db_index=True)
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, db_index=True)
    recipient = models.CharField(max_length=20, db_index=True)
    sender_id = models.CharField(max_length=11)
    batch_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    total_attempts = models.PositiveSmallIntegerField(default=1)
    provider_message_id = models.CharField(max_length=100, blank=True, default='', db_index=True)
    provider_status = models.CharField(max_length=50, blank=True, default='')
    provider_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['campaign', '-created_at']),
            models.Index(fields=['recipient', 'campaign']),
        ]


class SuccessSent(_SendHistoryBase):
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'sms_campaign_manager_successsent'
        ordering = ['-created_at']


class FailedSent(_SendHistoryBase):
    last_error = models.TextField(blank=True, default='')
    error_code = models.CharField(max_length=50, blank=True, default='')
    first_attempt_at = models.DateTimeField(null=True, blank=True)
    final_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sms_campaign_manager_failedsent'
        ordering = ['-created_at']


class _DeliveryHistoryBase(models.Model):
    """Shared immutable fields for terminal delivery reports."""

    id = models.BigAutoField(primary_key=True)
    message_id = models.CharField(max_length=100, db_index=True)
    provider_message_id = models.CharField(max_length=100, db_index=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, db_index=True)
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, db_index=True)
    recipient = models.CharField(max_length=20, db_index=True)
    sender_id = models.CharField(max_length=11)
    delivery_status = models.CharField(max_length=20, db_index=True)
    delivery_code = models.CharField(max_length=20, blank=True, default='')
    delivery_description = models.TextField(blank=True, default='')
    provider_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['campaign', 'delivery_status']),
            models.Index(fields=['recipient', 'campaign']),
        ]


class SuccessDelivery(_DeliveryHistoryBase):
    delivered_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'sms_campaign_manager_successdelivery'
        ordering = ['-created_at']


class FailedDelivery(_DeliveryHistoryBase):
    failed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'sms_campaign_manager_faileddelivery'
        ordering = ['-created_at']


# ============================================================================
# CUSTOMER PROFILE CONFIG (language mapping)
# ============================================================================

class CustomerProfileConfig(models.Model):
    """Reusable language-mapping profile."""

    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(blank=True, default='')
    database_config = models.ForeignKey(
        DatabaseConfig,
        on_delete=models.CASCADE,
        related_name='customer_profiles',
    )
    table_name = models.CharField(max_length=200)
    msisdn_column = models.CharField(max_length=100, default='msisdn')
    language_column = models.CharField(max_length=100, default='language')

    join_source_column = models.CharField(max_length=100, blank=True, default='')
    join_profile_column = models.CharField(max_length=100, blank=True, default='')

    default_language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name='default_for_profiles',
    )
    is_active = models.BooleanField(default=True, db_index=True)

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='customer_profiles',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'

    def __str__(self):
        return f'{self.name} → {self.table_name}.{self.language_column}'


# ============================================================================
# AUDIENCE CONFIG (metadata-first model)
# ============================================================================

class AudienceConfig(models.Model):
    """Metadata-first audience configuration for one campaign.

    Stores source, file, manual, and mapper metadata once. The real
    audience records are built later by a SQL join or equivalent lookup
    service, while this model remains the canonical persisted contract.
    """

    SOURCE_TYPE_CHOICES = SOURCE_TYPE_CHOICES
    JOIN_TYPE_CHOICES = [
        ('LEFT', 'LEFT JOIN'),
        ('INNER', 'INNER JOIN'),
    ]
    REBUILD_STATUS_CHOICES = [
        ('idle', 'Idle'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    id = models.BigAutoField(primary_key=True)

    campaign = models.OneToOneField(
        Campaign,
        on_delete=models.CASCADE,
        related_name='audience_config',
    )

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default='manual',
        db_index=True,
    )

    source_database = models.ForeignKey(
        DatabaseConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_audience_configs',
        help_text='For database source',
    )
    source_table = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Table name (for database source)',
    )
    source_msisdn_column = models.CharField(
        max_length=100,
        blank=True,
        default='msisdn',
        help_text='MSISDN column in source table',
    )
    source_language_column = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Language column in source table (optional)',
    )
    source_filter_clause = models.TextField(
        blank=True,
        default='',
        help_text='Optional SQL WHERE clause without the word WHERE',
    )

    manual_msisdns = models.JSONField(
        default=list,
        blank=True,
        help_text='List of MSISDNs (for manual source)',
    )
    manual_languages = models.JSONField(
        default=list,
        blank=True,
        help_text='Optional matching list of languages (for manual source)',
    )

    source_file_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='Path to uploaded file',
    )
    source_file_msisdn_column = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='MSISDN column in file',
    )
    source_file_language_column = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Language column in file (optional)',
    )

    mapper_enabled = models.BooleanField(
        default=False,
        help_text='Whether to join with a language mapper table',
    )
    mapper_database = models.ForeignKey(
        DatabaseConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mapper_audience_configs',
        help_text='Database containing mapper table',
    )
    mapper_table = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text='Mapper table name',
    )
    mapper_msisdn_column = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='MSISDN column in mapper table (JOIN key)',
    )
    mapper_language_column = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='Language column in mapper table',
    )
    mapper_join_type = models.CharField(
        max_length=10,
        choices=JOIN_TYPE_CHOICES,
        default='LEFT',
        help_text='JOIN type between source and mapper',
    )

    rebuild_before_each_run = models.BooleanField(
        default=False,
        help_text='Rebuild the audience from its source before each scheduled run',
    )
    rebuild_on_each_round = models.BooleanField(default=False)
    rebuild_minutes_before = models.PositiveSmallIntegerField(
        default=10,
        help_text='Minutes before the scheduled start to begin rebuilding',
    )
    rebuild_timeout_minutes = models.PositiveSmallIntegerField(
        default=30,
        help_text='Maximum allowed audience rebuild duration in minutes',
    )
    round_number = models.PositiveIntegerField(default=1)
    last_rebuild_round = models.PositiveIntegerField(default=0)
    is_round_active = models.BooleanField(default=False)
    last_build_id = models.CharField(max_length=64, blank=True, default='')

    default_language = models.ForeignKey(
        Language,
        on_delete=models.PROTECT,
        related_name='audience_configs',
        help_text='Fallback when no source/mapper provides language',
    )

    total_count = models.PositiveIntegerField(default=0)
    total_rows_fetched = models.PositiveBigIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    invalid_count = models.PositiveIntegerField(default=0)
    language_from_source = models.PositiveIntegerField(default=0)
    language_from_mapper = models.PositiveIntegerField(default=0)
    language_from_default = models.PositiveIntegerField(default=0)

    is_processed = models.BooleanField(default=False, db_index=True)
    last_built_at = models.DateTimeField(null=True, blank=True)
    last_rebuild_started_at = models.DateTimeField(null=True, blank=True)
    last_rebuild_completed_at = models.DateTimeField(null=True, blank=True)
    last_rebuild_status = models.CharField(
        max_length=20,
        choices=REBUILD_STATUS_CHOICES,
        default='idle',
        db_index=True,
    )
    last_rebuild_phase = models.CharField(max_length=30, blank=True, default='')
    last_rebuild_processed = models.PositiveBigIntegerField(default=0)
    last_rebuild_total = models.PositiveBigIntegerField(default=0)
    last_rebuild_percent = models.FloatField(default=0)
    last_rebuild_error = models.TextField(blank=True, default='')
    last_rebuild_duration_seconds = models.FloatField(null=True, blank=True)
    avg_rebuild_duration_seconds = models.FloatField(default=0)
    rebuild_history_seconds = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Audience Configuration'
        verbose_name_plural = 'Audience Configurations'

    def __str__(self):
        return f'AudienceConfig for {self.campaign.name} ({self.source_type})'


class AudienceBuildJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCEEDED', 'Succeeded'),
        ('FAILED', 'Failed'),
    ]

    id = models.BigAutoField(primary_key=True)
    audience_config = models.ForeignKey(AudienceConfig, on_delete=models.CASCADE, related_name='build_jobs')
    round_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    processed_rows = models.PositiveBigIntegerField(default=0)
    valid_rows = models.PositiveBigIntegerField(default=0)
    invalid_rows = models.PositiveBigIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['audience_config', 'status'])]
        constraints = [
            models.UniqueConstraint(
                fields=['audience_config'],
                condition=models.Q(status__in=['PENDING', 'RUNNING']),
                name='unique_active_audience_build_per_config',
            ),
        ]


# ============================================================================
# SIGNALS — keep Campaign.is_ready_to_execute from going stale
# ============================================================================
#
# FIX: previously nothing recomputed is_ready_to_execute when Schedule,
# MessageContent, or Audience rows changed, so the flag could silently
# drift from reality (e.g. a campaign marked ready that later lost its
# schedule). These receivers refresh it whenever those related rows are
# saved individually.
#
# IMPORTANT CAVEAT: post_save does NOT fire for bulk_create()/bulk_update().
# Audience uploads at 100k+ rows use bulk_create() and will NOT trigger the
# receiver below — call campaign.refresh_readiness_flag() explicitly once a
# bulk audience upload finishes.

@receiver(post_save, sender=Schedule)
def _schedule_saved_refresh_campaign_readiness(sender, instance, **kwargs):
    instance.campaign.refresh_readiness_flag()


@receiver(post_save, sender=MessageContent)
def _message_content_saved_refresh_campaign_readiness(sender, instance, **kwargs):
    instance.campaign.refresh_readiness_flag()


@receiver(post_save, sender=Audience)
def _audience_saved_refresh_campaign_readiness(sender, instance, **kwargs):
    instance.campaign.refresh_readiness_flag()