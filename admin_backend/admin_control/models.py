from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from .crypto import SharedEncryptedCharField


class SharedConfigModel(models.Model):
    """Base for campaign-manager tables: admin_backend never migrates them."""

    class Meta:
        abstract = True
        managed = False
        app_label = "admin_control"


class Channel(SharedConfigModel):
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_channel"

    def __str__(self):
        return f"{self.name} ({self.code})"


class SenderID(SharedConfigModel):
    sender_id = models.CharField(max_length=11)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_senderid"

    def __str__(self):
        return self.sender_id


class SenderIDDetails(models.Model):
    class SenderType(models.TextChoices):
        ALPHANUMERIC = "ALPHANUMERIC", "Alphanumeric"
        NUMERIC = "NUMERIC", "Numeric"
        SHORT_CODE = "SHORT_CODE", "Short code"

    sender_id = models.OneToOneField(
        SenderID, on_delete=models.CASCADE, related_name="admin_details"
    )
    sender_type = models.CharField(
        max_length=16, choices=SenderType.choices, default=SenderType.ALPHANUMERIC
    )
    country = models.CharField(max_length=100, blank=True, default="")
    tps_limit = models.PositiveIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        value = self.sender_id.sender_id
        if self.sender_type == self.SenderType.NUMERIC and not value.isdigit():
            raise ValidationError({"sender_type": "Numeric Sender IDs may contain only digits."})
        if self.sender_type == self.SenderType.ALPHANUMERIC and not value.isalnum():
            raise ValidationError(
                {"sender_type": "Alphanumeric Sender IDs may contain only letters and digits."}
            )
        if self.sender_type == self.SenderType.SHORT_CODE and (
            not value.isdigit() or not 3 <= len(value) <= 8
        ):
            raise ValidationError({"sender_type": "Short codes must contain 3 to 8 digits."})
        if self.tps_limit is not None and not 1 <= self.tps_limit <= 100000:
            raise ValidationError({"tps_limit": "Sender TPS must be from 1 to 100000."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class SMSCConfig(SharedConfigModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    base_url = models.URLField(max_length=500)
    send_endpoint = models.CharField(max_length=255, default="/api/send")
    http_method = models.CharField(max_length=10, default="POST")
    auth_type = models.CharField(max_length=20, default="api_key")
    api_key = SharedEncryptedCharField(max_length=500, blank=True, default="")
    api_secret = SharedEncryptedCharField(max_length=500, blank=True, default="")
    username = models.CharField(max_length=255, blank=True, default="")
    password = SharedEncryptedCharField(max_length=500, blank=True, default="")
    extra_headers = models.JSONField(default=dict, blank=True)
    extra_params = models.JSONField(default=dict, blank=True)
    rate_limit_per_second = models.PositiveIntegerField(default=100)
    rate_limit_per_minute = models.PositiveIntegerField(default=3000)
    max_retries = models.PositiveSmallIntegerField(default=3)
    retry_backoff_seconds = models.PositiveIntegerField(default=5)
    max_addresses_per_request = models.PositiveIntegerField(default=1000)
    request_timeout_seconds = models.PositiveIntegerField(default=30)
    connect_timeout_seconds = models.PositiveIntegerField(default=10)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, default="")
    last_test_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_smscconfig"

    def __str__(self):
        return self.name


class GlobalTPSConfig(SharedConfigModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    global_tps = models.PositiveIntegerField(default=4000)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_globaltpsconfig"


class NAddressesConfig(SharedConfigModel):
    """Existing global max-destinations-per-request config."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    max_addresses_per_request = models.PositiveIntegerField(default=1000)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_naddressesconfig"


class Campaign(SharedConfigModel):
    name = models.CharField(max_length=255)
    sender_id = models.CharField(max_length=11)
    owner_emails = models.JSONField(default=list, blank=True)
    channels_id = models.JSONField(default=list)
    status = models.CharField(max_length=20)
    is_ready_to_execute = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_column="created_by_id",
        related_name="admin_created_campaigns",
    )

    class Meta(SharedConfigModel.Meta):
        db_table = "sms_campaign_manager_campaign"


class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        CAMPAIGN_MANAGER = "CAMPAIGN_MANAGER", "Campaign Manager"

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="admin_profile"
    )
    role = models.CharField(
        max_length=24,
        choices=Role.choices,
        default=Role.CAMPAIGN_MANAGER,
        db_index=True,
    )
    department = models.CharField(max_length=150, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_locked = models.BooleanField(default=False)
    require_password_change = models.BooleanField(default=False)
    tps_limit = models.PositiveIntegerField(null=True, blank=True)
    sms_configs = models.ManyToManyField(SMSCConfig, blank=True, related_name="assigned_profiles")
    sender_ids = models.ManyToManyField(SenderID, blank=True, related_name="assigned_profiles")
    channels = models.ManyToManyField(Channel, blank=True, related_name="assigned_profiles")
    tps_configs = models.ManyToManyField(
        GlobalTPSConfig, blank=True, related_name="assigned_profiles"
    )
    n_address_configs = models.ManyToManyField(
        NAddressesConfig, blank=True, related_name="assigned_profiles"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"

    def clean(self):
        if self.tps_limit is not None and self.tps_limit < 1:
            raise ValidationError({"tps_limit": "TPS limit must be at least 1."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        expected_staff = self.role == self.Role.ADMIN
        if self.user.is_staff != expected_staff:
            self.user.is_staff = expected_staff
            self.user.save(update_fields=["is_staff"])


class SenderSMSCBinding(models.Model):
    sender_id = models.ForeignKey(SenderID, on_delete=models.CASCADE)
    smsc = models.ForeignKey(SMSCConfig, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("sender_id", "smsc"), name="admin_sender_smsc_unique"
            )
        ]


class ChannelSMSCBinding(models.Model):
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE)
    smsc = models.ForeignKey(SMSCConfig, on_delete=models.CASCADE)
    allowed_sender_ids = models.ManyToManyField(SenderID, blank=True)
    default_tps = models.PositiveIntegerField(default=100)
    priority = models.PositiveIntegerField(default=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("channel", "smsc"), name="admin_channel_smsc_unique"
            )
        ]

    def clean(self):
        if self.default_tps < 1:
            raise ValidationError({"default_tps": "Channel TPS must be at least 1."})


class NAddress(models.Model):
    class AddressType(models.TextChoices):
        MSISDN = "MSISDN", "MSISDN"
        ALPHANUMERIC = "ALPHANUMERIC", "Alphanumeric"
        POOL = "POOL", "Pool"

    value = models.CharField(max_length=255, unique=True)
    address_type = models.CharField(max_length=16, choices=AddressType.choices)
    smsc = models.ForeignKey(SMSCConfig, on_delete=models.PROTECT, related_name="n_addresses")
    channel = models.ForeignKey(
        Channel, null=True, blank=True, on_delete=models.PROTECT, related_name="n_addresses"
    )
    sender_id = models.ForeignKey(
        SenderID, null=True, blank=True, on_delete=models.PROTECT, related_name="n_addresses"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    tps_cap = models.PositiveIntegerField(null=True, blank=True)
    assigned_users = models.ManyToManyField(
        User, blank=True, related_name="assigned_n_addresses"
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("value",)

    def clean(self):
        if self.tps_cap is not None and self.tps_cap < 1:
            raise ValidationError({"tps_cap": "TPS cap must be at least 1."})


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="admin_audit_events"
    )
    action = models.CharField(max_length=40, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=100, blank=True, default="")
    summary = models.CharField(max_length=255)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)


class LoginAttempt(models.Model):
    username = models.CharField(max_length=254, db_index=True)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_attempts"
    )
    succeeded = models.BooleanField(default=False, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)


class AdminEmailConfig(models.Model):
    name = models.CharField(max_length=150, unique=True, default="Admin account email")
    host = models.CharField(max_length=255)
    port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255, blank=True, default="")
    password = SharedEncryptedCharField(max_length=1000, blank=True, default="")
    use_tls = models.BooleanField(default=True)
    use_ssl = models.BooleanField(default=False)
    from_email = models.EmailField()
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True, default="")
    last_test_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if not self.host.strip():
            raise ValidationError({"host": "SMTP host is required."})
        if not 1 <= self.port <= 65535:
            raise ValidationError({"port": "Port must be between 1 and 65535."})
        if not self.from_email:
            raise ValidationError({"from_email": "Sender email is required."})
        if self.use_tls and self.use_ssl:
            raise ValidationError({"use_ssl": "Choose TLS or SSL, not both."})

    def save(self, *args, **kwargs):
        if not self.is_active:
            self.is_default = False
        self.full_clean()
        if self.is_default:
            AdminEmailConfig.objects.filter(is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class PasswordResetChallenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="admin_password_challenges")
    pin_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
