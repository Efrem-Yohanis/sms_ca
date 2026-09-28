"""DRF serializers for Campaign resources."""

from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from .constants import (
    DELIVERY_STATUS_CHOICES,
    DELIVERY_TERMINAL_STATUSES,
    SUPPORTED_LANGUAGE_CODES,
    SUPPORTED_LANGUAGES,
    SOURCE_TYPE_CHOICES,
    VALID_CHANNELS,
)
from .models import (
    AudienceConfig,
    AudienceMember,
    Campaign,
    Channel,
    CustomerProfileConfig,
    DatabaseConfig,
    DeliveryRecord,
    EmailConfig,
    EmailReport,
    CampaignProgressReport,
    ReportSubscription,
    ReportDeliveryLog,
    Language,
    MessageContent,
    Schedule,
    SentRecord,
    SenderID,
    SMSCConfig,
)


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'email', 'password']
        read_only_fields = ['id']

    def validate(self, attrs):
        user = self.Meta.model(
            username=attrs['username'],
            email=attrs.get('email', ''),
        )
        password_validation.validate_password(attrs['password'], user=user)
        return attrs

    def create(self, validated_data):
        return self.Meta.model.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'date_joined', 'last_login']
        read_only_fields = ['id', 'username', 'is_staff', 'date_joined', 'last_login']


class UserAdminUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser']
        read_only_fields = ['username']


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        password_validation.validate_password(value, user=self.context['request'].user)
        return value


class SentRecordSerializer(serializers.ModelSerializer):
    is_terminal = serializers.SerializerMethodField()
    class Meta:
        model = SentRecord
        fields = ['id', 'campaign_id', 'batch_id', 'msisdn', 'submitted_at', 'sent_status', 'is_terminal', 'created_at', 'updated_at']
        read_only_fields = fields
    def get_is_terminal(self, obj) -> bool:
        return obj.is_terminal()


class SentRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SentRecord
        fields = ['campaign_id', 'batch_id', 'msisdn', 'submitted_at', 'sent_status']

    def validate_campaign_id(self, value):
        if not Campaign.objects.filter(id=value, is_deleted=False).exists():
            raise serializers.ValidationError(f'Campaign with id={value} does not exist.')
        return value

    def validate_batch_id(self, value):
        value = value.strip()
        if not value or len(value) > 50:
            raise serializers.ValidationError('batch_id is required and must be at most 50 characters.')
        return value

    def validate_msisdn(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('msisdn is required.')
        return value


class SentRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SentRecord
        fields = ['sent_status', 'submitted_at']

    def validate(self, attrs):
        if self.instance and self.instance.is_terminal():
            raise serializers.ValidationError(f"Cannot modify record with terminal status '{self.instance.sent_status}'.")
        return attrs


class SentRecordBulkCreateSerializer(serializers.Serializer):
    records = SentRecordCreateSerializer(many=True)
    def validate_records(self, value):
        if not value or len(value) > 10000:
            raise serializers.ValidationError('Provide between 1 and 10,000 records.')
        return value


class SentRecordBulkUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sent_status = serializers.ChoiceField(choices=['PENDING', 'SUBMITTED', 'ACCEPTED', 'REJECTED', 'FAILED'])
    submitted_at = serializers.DateTimeField(required=False, allow_null=True)


class SentRecordBulkUpdateSerializer(serializers.Serializer):
    updates = SentRecordBulkUpdateItemSerializer(many=True)


class CustomerProfileConfigSerializer(serializers.ModelSerializer):
    database_name = serializers.CharField(source='database_config.name', read_only=True)
    class Meta:
        model = CustomerProfileConfig
        fields = ['id', 'name', 'description', 'database_config', 'database_name', 'table_name', 'msisdn_column', 'language_column', 'default_language', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'database_name', 'created_at', 'updated_at']


class AudienceConfigSerializer(serializers.ModelSerializer):
    manual_msisdns = serializers.ListField(
        child=serializers.CharField(max_length=30),
        required=False,
        default=list,
    )
    manual_languages = serializers.ListField(
        child=serializers.CharField(max_length=10, allow_blank=True),
        required=False,
        default=list,
    )
    source_database_id = serializers.PrimaryKeyRelatedField(
        source='source_database',
        queryset=DatabaseConfig.objects.all(),
        required=False,
        allow_null=True,
    )
    mapper_database_id = serializers.PrimaryKeyRelatedField(
        source='mapper_database',
        queryset=DatabaseConfig.objects.all(),
        required=False,
        allow_null=True,
    )
    default_language_id = serializers.PrimaryKeyRelatedField(
        source='default_language',
        queryset=Language.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = AudienceConfig
        fields = [
            'id', 'campaign', 'source_type', 'source_database', 'source_database_id',
            'source_table', 'source_msisdn_column', 'source_language_column',
            'source_filter_clause', 'manual_msisdns', 'manual_languages',
            'source_file_path', 'source_file_msisdn_column', 'source_file_language_column',
            'mapper_enabled', 'mapper_database', 'mapper_database_id', 'mapper_table',
            'mapper_msisdn_column', 'mapper_language_column', 'mapper_join_type',
            'rebuild_before_each_run', 'rebuild_on_each_round', 'rebuild_minutes_before',
            'rebuild_timeout_minutes',
            'default_language', 'default_language_id', 'total_count', 'valid_count',
            'invalid_count', 'language_from_source', 'language_from_mapper',
            'language_from_default', 'total_rows_fetched', 'round_number', 'is_processed',
            'last_built_at', 'last_rebuild_round',
            'is_round_active', 'last_build_id', 'last_rebuild_status', 'last_rebuild_phase',
            'last_rebuild_processed', 'last_rebuild_total', 'last_rebuild_percent',
            'last_rebuild_started_at', 'last_rebuild_completed_at', 'last_rebuild_error',
            'last_rebuild_duration_seconds', 'avg_rebuild_duration_seconds',
            'rebuild_history_seconds', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'campaign', 'total_count', 'valid_count', 'invalid_count',
            'language_from_source', 'language_from_mapper', 'language_from_default',
            'round_number', 'is_processed', 'last_built_at', 'last_rebuild_round',
            'is_round_active', 'last_build_id',
            'last_rebuild_status', 'last_rebuild_phase', 'last_rebuild_processed',
            'last_rebuild_total', 'last_rebuild_percent', 'last_rebuild_started_at',
            'last_rebuild_completed_at', 'last_rebuild_error', 'last_rebuild_duration_seconds',
            'total_rows_fetched', 'avg_rebuild_duration_seconds', 'rebuild_history_seconds',
            'created_at', 'updated_at',
        ]

    def validate_rebuild_minutes_before(self, value):
        if value < 1 or value > 1440:
            raise serializers.ValidationError('Must be between 1 and 1,440 minutes.')
        return value

    def validate_rebuild_timeout_minutes(self, value):
        if value < 1 or value > 1440:
            raise serializers.ValidationError('Must be between 1 and 1,440 minutes.')
        return value

    def validate(self, attrs):
        if 'rebuild_on_each_round' in attrs and 'rebuild_before_each_run' not in attrs:
            attrs['rebuild_before_each_run'] = attrs['rebuild_on_each_round']
        elif 'rebuild_before_each_run' in attrs and 'rebuild_on_each_round' not in attrs:
            attrs['rebuild_on_each_round'] = attrs['rebuild_before_each_run']
        source_type = attrs.get('source_type', getattr(self.instance, 'source_type', 'manual'))
        if source_type != 'manual':
            attrs['manual_msisdns'] = []
            attrs['manual_languages'] = []
        if (
            attrs.get('rebuild_before_each_run', getattr(self.instance, 'rebuild_before_each_run', False))
            and attrs.get('rebuild_timeout_minutes', getattr(self.instance, 'rebuild_timeout_minutes', 30))
            < attrs.get('rebuild_minutes_before', getattr(self.instance, 'rebuild_minutes_before', 10))
        ):
            raise serializers.ValidationError({
                'rebuild_timeout_minutes': 'Timeout must be at least the rebuild lead time.',
            })
        return attrs


class AudienceMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudienceMember
        fields = ['id', 'campaign_id', 'msisdn', 'language', 'language_source', 'source_type', 'is_valid', 'validation_error', 'custom_fields', 'sequence_number', 'round_number', 'build_id', 'rebuilt_at', 'created_at']
        read_only_fields = fields


class MapperConfigMixin(serializers.Serializer):
    """Reusable mapper fields for all audience source serializers."""

    mapper_enabled = serializers.BooleanField(default=False)
    mapper_database_id = serializers.IntegerField(required=False, allow_null=True)
    mapper_table = serializers.CharField(required=False, allow_blank=True, default='')
    mapper_msisdn_column = serializers.CharField(required=False, allow_blank=True, default='')
    mapper_language_column = serializers.CharField(required=False, allow_blank=True, default='')
    mapper_join_type = serializers.ChoiceField(choices=['LEFT', 'INNER'], default='LEFT')
    rebuild_before_each_run = serializers.BooleanField(default=False)
    rebuild_on_each_round = serializers.BooleanField(required=False)
    rebuild_minutes_before = serializers.IntegerField(default=10, min_value=1, max_value=1440)
    rebuild_timeout_minutes = serializers.IntegerField(default=30, min_value=1, max_value=1440)
    default_language_id = serializers.IntegerField(required=True)

    def validate_default_language_id(self, value):
        if not Language.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(f'Language with id={value} does not exist or is inactive.')
        return value

    def validate(self, attrs):
        if attrs.get('rebuild_timeout_minutes', 30) < attrs.get('rebuild_minutes_before', 10):
            raise serializers.ValidationError({
                'rebuild_timeout_minutes': 'Timeout must be at least the rebuild lead time.',
            })
        if attrs.get('mapper_enabled'):
            missing = []
            for field in ['mapper_database_id', 'mapper_table', 'mapper_msisdn_column', 'mapper_language_column']:
                if not attrs.get(field):
                    missing.append(field)
            if missing:
                raise serializers.ValidationError({'mapper_enabled': f'Mapper enabled but missing fields: {missing}'})
            if not DatabaseConfig.objects.filter(id=attrs['mapper_database_id'], is_active=True).exists():
                raise serializers.ValidationError(f'Mapper database id={attrs["mapper_database_id"]} not found or inactive.')
        return attrs


class ManualAudienceSerializer(MapperConfigMixin):
    """POST /api/v1/campaigns/<id>/audience/manual/"""

    manual_msisdns = serializers.ListField(child=serializers.CharField(max_length=20), allow_empty=False)
    manual_languages = serializers.ListField(
        child=serializers.CharField(max_length=10, allow_blank=True),
        required=False,
        allow_empty=True,
        default=list,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        msisdns = attrs.get('manual_msisdns', [])
        languages = attrs.get('manual_languages', [])
        if len(msisdns) > 100000:
            raise serializers.ValidationError({'manual_msisdns': 'Maximum 100,000 MSISDNs per request.'})
        if languages and len(languages) != len(msisdns):
            raise serializers.ValidationError({'manual_languages': f'Length ({len(languages)}) must match manual_msisdns ({len(msisdns)}).'})
        return attrs


class FileAudienceSerializer(MapperConfigMixin):
    """POST /api/v1/campaigns/<id>/audience/file/ (multipart)"""

    file = serializers.FileField(required=True)
    source_file_msisdn_column = serializers.CharField(max_length=100)
    source_file_language_column = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_file(self, value):
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError('File must be ≤ 100 MB.')
        ext = value.name.rsplit('.', 1)[-1].lower() if '.' in value.name else ''
        if ext not in ('csv', 'xlsx', 'xls'):
            raise serializers.ValidationError(f'Unsupported file type: .{ext}. Use CSV, XLSX, or XLS.')
        return value


class DatabaseAudienceSerializer(MapperConfigMixin):
    """POST /api/v1/campaigns/<id>/audience/database/"""

    source_database_id = serializers.IntegerField()
    source_table = serializers.CharField(max_length=200)
    source_msisdn_column = serializers.CharField(max_length=100, default='msisdn')
    source_language_column = serializers.CharField(required=False, allow_blank=True, default='')
    source_filter_clause = serializers.CharField(required=False, allow_blank=True, default='')

    def validate_source_database_id(self, value):
        if not DatabaseConfig.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError(f'Database id={value} not found or inactive.')
        return value


class ManualAudienceInputSerializer(serializers.Serializer):
    msisdns = serializers.ListField(child=serializers.CharField(max_length=30), allow_empty=False)
    languages = serializers.ListField(child=serializers.CharField(max_length=10, allow_blank=True), required=False, default=list)
    default_language = serializers.ChoiceField(choices=['en', 'am', 'ti', 'om', 'so'], default='en')
    customer_profile_id = serializers.IntegerField(required=False, allow_null=True)
    source_type = serializers.ChoiceField(choices=SOURCE_TYPE_CHOICES, default='manual')

    def validate(self, attrs):
        if attrs.get('languages') and len(attrs['languages']) != len(attrs['msisdns']):
            raise serializers.ValidationError({'languages': 'Languages must match the number of MSISDNs.'})
        return attrs


class CustomerProfilePreviewSerializer(serializers.Serializer):
	"""Preview language mapping for a batch of MSISDNs using a profile."""
	msisdns = serializers.ListField(child=serializers.CharField(max_length=30), allow_empty=False)

class CampaignReadinessSerializer(serializers.Serializer):
    is_ready = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    stats = serializers.DictField()


class DeliveryRecordSerializer(serializers.ModelSerializer):
    is_terminal = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryRecord
        fields = [
            'id', 'campaign_id', 'batch_id', 'msisdn', 'delivered_at',
            'delivery_status', 'is_terminal', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_is_terminal(self, obj) -> bool:
        return obj.is_terminal()


class DeliveryRecordCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = ['campaign_id', 'batch_id', 'msisdn', 'delivered_at', 'delivery_status']

    def validate_campaign_id(self, value):
        if not Campaign.objects.filter(id=value, is_deleted=False).exists():
            raise serializers.ValidationError(f'Campaign with id={value} does not exist.')
        return value

    def validate_batch_id(self, value):
        value = value.strip()
        if not value or len(value) > 50:
            raise serializers.ValidationError('batch_id is required and must be at most 50 characters.')
        return value

    def validate_msisdn(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('msisdn is required.')
        return value

    def validate_delivery_status(self, value):
        valid = [code for code, _ in DELIVERY_STATUS_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(f'Invalid delivery_status. Valid: {valid}')
        return value


class DeliveryRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryRecord
        fields = ['delivery_status', 'delivered_at']

    def validate(self, attrs):
        if self.instance and self.instance.is_terminal():
            raise serializers.ValidationError(
                f"Cannot modify record with terminal status '{self.instance.delivery_status}'."
            )
        return attrs


class DeliveryRecordBulkCreateSerializer(serializers.Serializer):
    records = DeliveryRecordCreateSerializer(many=True)

    def validate_records(self, value):
        if not value or len(value) > 10000:
            raise serializers.ValidationError('Provide between 1 and 10,000 records.')
        return value


class DeliveryRecordBulkUpdateItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    delivery_status = serializers.ChoiceField(choices=[code for code, _ in DELIVERY_STATUS_CHOICES])
    delivered_at = serializers.DateTimeField(required=False, allow_null=True)


class DeliveryRecordBulkUpdateSerializer(serializers.Serializer):
    updates = DeliveryRecordBulkUpdateItemSerializer(many=True)

    def validate_updates(self, value):
        if not value or len(value) > 10000:
            raise serializers.ValidationError('Provide between 1 and 10,000 updates.')
        return value


class DatabaseConfigTestResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    details = serializers.DictField(required=False, default=dict)


class DatabaseConfigSerializer(serializers.ModelSerializer):
    connection_string = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = DatabaseConfig
        fields = [
            'id', 'name', 'description', 'database_type', 'host', 'port',
            'database_name', 'username', 'ssl_required', 'extra_options',
            'is_active', 'last_tested_at', 'last_test_status',
            'last_test_message', 'connection_string', 'created_by',
            'created_by_username', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_connection_string(self, obj) -> str:
        return obj.get_connection_string()


class DatabaseConfigCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseConfig
        fields = [
            'name', 'description', 'database_type', 'host', 'port',
            'database_name', 'username', 'password', 'ssl_required',
            'extra_options', 'is_active',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def validate_port(self, value):
        if not 1 <= value <= 65535:
            raise serializers.ValidationError('Port must be between 1 and 65535.')
        return value


class DatabaseConfigTestParamsSerializer(serializers.Serializer):
    database_type = serializers.ChoiceField(choices=['postgresql', 'mysql', 'mssql', 'oracle', 'sqlite'])
    host = serializers.CharField(max_length=255, required=False, default='localhost')
    port = serializers.IntegerField(min_value=1, max_value=65535, required=False, default=1)
    database_name = serializers.CharField(max_length=255)
    username = serializers.CharField(max_length=255, required=False, default='')
    password = serializers.CharField(max_length=500, required=False, default='', write_only=True)
    ssl_required = serializers.BooleanField(required=False, default=False)


class SenderIDSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = SenderID
        fields = [
            'id', 'sender_id', 'name', 'description',
            'is_default', 'is_active', 'created_by',
            'created_by_username', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_username']


class SenderIDCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SenderID
        fields = ['sender_id', 'name', 'description', 'is_default', 'is_active']

    def validate_sender_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Sender ID is required.')
        if not (3 <= len(value) <= 11):
            raise serializers.ValidationError('Sender ID must be between 3 and 11 characters.')
        if not value.replace('_', '').isalnum():
            raise serializers.ValidationError('Sender ID can only contain letters, numbers, and underscores.')
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name is required.')
        return value


class SMSCConfigSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = SMSCConfig
        fields = [
            'id', 'name', 'description', 'base_url', 'send_endpoint',
            'http_method', 'auth_type', 'api_key', 'api_secret',
            'username', 'password', 'extra_headers', 'extra_params',
            'rate_limit_per_second', 'rate_limit_per_minute',
            'max_retries', 'retry_backoff_seconds',
            'request_timeout_seconds', 'connect_timeout_seconds',
            'is_default', 'is_active', 'last_tested_at',
            'last_test_status', 'last_test_message', 'created_by',
            'created_by_username', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_username']
        extra_kwargs = {
            'api_key': {'write_only': True, 'required': False, 'allow_blank': True},
            'api_secret': {'write_only': True, 'required': False, 'allow_blank': True},
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
        }


class SMSCConfigCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSCConfig
        fields = [
            'name', 'description', 'base_url', 'send_endpoint',
            'http_method', 'auth_type', 'api_key', 'api_secret',
            'username', 'password', 'extra_headers', 'extra_params',
            'rate_limit_per_second', 'rate_limit_per_minute',
            'max_retries', 'retry_backoff_seconds',
            'request_timeout_seconds', 'connect_timeout_seconds',
            'is_default', 'is_active',
        ]
        extra_kwargs = {
            'api_key': {'write_only': True, 'required': False, 'allow_blank': True},
            'api_secret': {'write_only': True, 'required': False, 'allow_blank': True},
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Name is required.')
        return value

    def validate_base_url(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Base URL is required.')
        return value

    def validate(self, attrs):
        if attrs.get('rate_limit_per_second', 100) <= 0:
            raise serializers.ValidationError({'rate_limit_per_second': 'Must be greater than 0.'})
        if attrs.get('rate_limit_per_minute', 3000) <= 0:
            raise serializers.ValidationError({'rate_limit_per_minute': 'Must be greater than 0.'})
        if attrs.get('request_timeout_seconds', 30) <= 0:
            raise serializers.ValidationError({'request_timeout_seconds': 'Must be greater than 0.'})
        return attrs


class EmailConfigSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = EmailConfig
        fields = [
            'id', 'name', 'description', 'host', 'port', 'username', 'password',
            'use_tls', 'use_ssl', 'default_from_email', 'is_default', 'is_active',
            'last_tested_at', 'last_test_status', 'last_test_message',
            'created_by', 'created_by_username', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'last_tested_at', 'last_test_status', 'last_test_message',
            'created_at', 'updated_at', 'created_by_username',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
        }


class EmailConfigCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailConfig
        fields = [
            'name', 'description', 'host', 'port', 'username', 'password',
            'use_tls', 'use_ssl', 'default_from_email', 'is_default', 'is_active',
        ]
        extra_kwargs = {
            'password': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def validate_name(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Name is required.')
        return value

    def validate_host(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Host is required.')
        return value

    def validate_port(self, value):
        if not 1 <= value <= 65535:
            raise serializers.ValidationError('Port must be between 1 and 65535.')
        return value


class EmailConfigTestParamsSerializer(serializers.Serializer):
    host = serializers.CharField(max_length=255)
    port = serializers.IntegerField(min_value=1, max_value=65535, default=587)
    username = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    password = serializers.CharField(max_length=500, required=False, allow_blank=True, default='', write_only=True)
    use_tls = serializers.BooleanField(default=True)
    use_ssl = serializers.BooleanField(default=False)
    default_from_email = serializers.EmailField(required=False, allow_blank=True, default='no-reply@example.com')
    test_email = serializers.EmailField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        if attrs.get('use_ssl') and attrs.get('use_tls'):
            raise serializers.ValidationError({'use_tls': 'Choose either TLS or SSL, not both.'})
        return attrs


class EmailReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailReport
        fields = [
            'id', 'campaign', 'report_type', 'subject', 'recipients', 'content',
            'status', 'sent_at', 'error_message', 'metadata', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class CampaignEmailReportCreateSerializer(serializers.Serializer):
    recipients = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    email_config_id = serializers.PrimaryKeyRelatedField(
        source='email_config',
        queryset=EmailConfig.objects.filter(is_active=True),
        required=False,
        allow_null=True,
    )
    report_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default='campaign_summary')
    format = serializers.ChoiceField(choices=ReportSubscription.FORMAT_CHOICES, default='html')
    include_sent_stats = serializers.BooleanField(default=True)
    include_delivery_stats = serializers.BooleanField(default=True)
    include_message_stats = serializers.BooleanField(default=True)

    def validate_recipients(self, value):
        normalized = []
        for email in value:
            email = email.strip().lower()
            if email and email not in normalized:
                normalized.append(email)
        return normalized


class ReportSubscriptionSerializer(serializers.ModelSerializer):
    recipients = serializers.ListField(
        child=serializers.EmailField(), required=False, default=list,
    )
    campaign_name = serializers.CharField(source='campaign.name', read_only=True, default=None)

    class Meta:
        model = ReportSubscription
        fields = [
            'id', 'campaign', 'campaign_name', 'recipients', 'frequency', 'format',
            'include_sent_stats', 'include_delivery_stats', 'include_message_stats',
            'is_active', 'next_run_at', 'last_sent_at', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'campaign_name', 'last_sent_at', 'created_by', 'created_at', 'updated_at']

    def validate_recipients(self, value):
        normalized = list(dict.fromkeys(email.strip().lower() for email in value if email.strip()))
        if not normalized:
            raise serializers.ValidationError('Select or add at least one recipient.')
        if len(normalized) > 50:
            raise serializers.ValidationError('A report can have at most 50 recipients.')
        return normalized


class ReportDeliveryLogSerializer(serializers.ModelSerializer):
    email_config_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReportDeliveryLog
        fields = [
            'id', 'subscription', 'campaign', 'email_config_id', 'recipients', 'format', 'sent_at', 'status',
            'error_message', 'attachment_names', 'report_data', 'subject', 'content',
            'include_sent_stats', 'include_delivery_stats', 'include_message_stats', 'created_at',
        ]
        read_only_fields = fields


class CampaignProgressReportSerializer(serializers.ModelSerializer):
    recipients = serializers.ListField(
        child=serializers.EmailField(), required=False, default=list,
    )
    campaigns = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Campaign.objects.filter(is_deleted=False),
    )
    campaign_names = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = CampaignProgressReport
        fields = [
            'id', 'name', 'campaigns', 'campaign_names', 'recipients',
            'include_campaign_owners', 'frequency', 'is_active',
            'next_run_at', 'last_run_at', 'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'campaign_names', 'created_by', 'created_at', 'updated_at', 'last_run_at']

    def get_campaign_names(self, obj) -> list[str]:
        return list(obj.campaigns.values_list('name', flat=True))

    def validate_recipients(self, value):
        normalized = []
        for email in value or []:
            email = email.strip().lower()
            if email and email not in normalized:
                normalized.append(email)
        if not normalized and not self.initial_data.get('include_campaign_owners', False):
            raise serializers.ValidationError('Add at least one recipient or enable include_campaign_owners.')
        return normalized

    def validate_campaigns(self, value):
        if not value:
            raise serializers.ValidationError('Select at least one campaign.')
        return value


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ['id', 'code', 'name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError('Channel code is required.')
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Channel name is required.')
        return value


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ['id', 'code', 'name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_code(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError('Language code is required.')
        if value not in SUPPORTED_LANGUAGE_CODES:
            raise serializers.ValidationError(
                f'Unsupported language code. Valid options: {SUPPORTED_LANGUAGE_CODES}'
            )
        return value

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Language name is required.')
        return value

    def validate_is_active(self, value):
        if not value and self.instance:
            content_filter = {self.instance.code + '__gt': ''}
            if MessageContent.objects.filter(**content_filter).exists():
                raise serializers.ValidationError(
                    'Cannot deactivate a language that is used by message content.'
                )
        return value


class SupportedLanguageSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class MessageContentSerializer(serializers.ModelSerializer):
    languages_with_content = serializers.ReadOnlyField()
    has_any_content = serializers.ReadOnlyField()
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)

    class Meta:
        model = MessageContent
        fields = [
            'id', 'campaign', 'campaign_name', 'en', 'am', 'ti', 'om', 'so',
            'default_language', 'languages_with_content', 'has_any_content',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'campaign', 'campaign_name', 'languages_with_content',
            'has_any_content', 'created_at', 'updated_at',
        ]


class MessageContentApiSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    default_language = serializers.CharField(source='default_language.code', read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    languages_available = serializers.ReadOnlyField(source='languages_with_content')
    preview = serializers.SerializerMethodField()

    class Meta:
        model = MessageContent
        fields = [
            'id', 'campaign', 'campaign_name', 'content', 'default_language',
            'languages_available', 'preview', 'created_at', 'updated_at',
        ]

    def get_content(self, obj):
        return obj.get_content_dict()

    def get_preview(self, obj):
        language = obj.default_language.code
        return {'language': language, 'preview': obj.get_message(language)}


class MessageContentApiInputSerializer(serializers.Serializer):
    campaign = serializers.PrimaryKeyRelatedField(
        queryset=Campaign.objects.filter(is_deleted=False), required=True,
    )
    content = serializers.DictField(child=serializers.CharField(allow_blank=True))
    default_language = serializers.SlugRelatedField(
        slug_field='code', queryset=Language.objects.filter(is_active=True),
    )

    def validate_content(self, value):
        active_codes = set(Language.objects.filter(is_active=True).values_list('code', flat=True))
        unknown = set(value) - active_codes
        if unknown:
            raise serializers.ValidationError(f'Unsupported or inactive languages: {sorted(unknown)}')
        return value


class LanguagePrimaryKeyOrCodeField(serializers.PrimaryKeyRelatedField):
    def to_internal_value(self, data):
        if isinstance(data, str) and not data.isdigit():
            language = self.get_queryset().filter(code=data).first()
            if language is not None:
                return language
        return super().to_internal_value(data)


class MessageContentCreateUpdateSerializer(serializers.ModelSerializer):
    default_language = LanguagePrimaryKeyOrCodeField(
        queryset=Language.objects.filter(is_active=True),
        required=True,
    )

    class Meta:
        model = MessageContent
        fields = ['en', 'am', 'ti', 'om', 'so', 'default_language']

    def validate_default_language(self, value):
        if not getattr(value, 'is_active', False):
            raise serializers.ValidationError(
                'Default language must be an active language in Language Manager.'
            )
        return value

    def validate(self, attrs):
        language_codes = list(
            Language.objects.filter(is_active=True).values_list('code', flat=True)
        )
        merged = {
            code: getattr(self.instance, code, '') if self.instance else ''
            for code in language_codes
        }
        merged.update({code: attrs[code] for code in language_codes if code in attrs})

        default_language = attrs.get(
            'default_language',
            self.instance.default_language if self.instance else None,
        )
        default_language_code = default_language.code if isinstance(default_language, Language) else str(default_language)

        if not any((merged[code] or '').strip() for code in language_codes):
            raise serializers.ValidationError(
                {'non_field_errors': 'At least one language must have content.'}
            )
        if not (merged.get(default_language_code, '') or '').strip():
            raise serializers.ValidationError({
                'default_language': (
                    f"Default language '{default_language}' must have content."
                ),
            })
        return attrs

class CampaignListSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    execution_status = serializers.CharField(read_only=True)
    execution_status_display = serializers.SerializerMethodField()
    channels = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    total_messages = serializers.IntegerField(read_only=True)
    total_processed = serializers.IntegerField(read_only=True)
    next_run = serializers.SerializerMethodField()
    has_schedule = serializers.SerializerMethodField()
    has_audience = serializers.SerializerMethodField()
    has_content = serializers.SerializerMethodField()
    audience_id = serializers.IntegerField(read_only=True, allow_null=True)
    message_content_id = serializers.IntegerField(read_only=True, allow_null=True)
    schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    schedule = serializers.SerializerMethodField()
    audience_rebuild = serializers.SerializerMethodField()

    def get_execution_status_display(self, obj):
        return {
            'PENDING': 'Pending',
            'PROCESSING': 'Processing',
            'PAUSED': 'Paused',
            'STOPPED': 'Stopped',
            'COMPLETED': 'Completed',
            'FAILED': 'Failed',
        }.get(obj.execution_status, obj.execution_status.title())

    def get_channels(self, obj):
        return list(obj.channels.order_by('name').values_list('name', flat=True))

    def get_progress_percent(self, obj):
        if not obj.total_messages:
            return 0
        return round(obj.total_processed * 100 / obj.total_messages, 1)

    def get_next_run(self, obj):
        schedule = getattr(obj, 'schedule', None)
        return schedule.next_run_date if schedule else None

    def get_has_schedule(self, obj):
        return obj.schedule_id is not None

    def get_has_audience(self, obj):
        return obj.has_audience

    def get_has_content(self, obj):
        return obj.message_content_id is not None

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_schedule(self, obj):
        schedule = getattr(obj, 'schedule', None)
        if schedule is None:
            return None
        return {
            'schedule_type': schedule.schedule_type,
            'start_date': schedule.start_date,
            'end_date': schedule.end_date,
            'run_days': schedule.run_days,
            'time_windows': schedule.time_windows,
            'timezone': schedule.timezone,
            'is_active': schedule.is_active,
            'schedule_status': schedule.schedule_status,
        }

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_audience_rebuild(self, obj):
        config = getattr(obj, 'audience_config', None)
        if config is None:
            return None
        return {
            'id': config.id,
            'enabled': config.rebuild_on_each_round or config.rebuild_before_each_run,
            'minutes_before': config.rebuild_minutes_before,
            'timeout_minutes': config.rebuild_timeout_minutes,
            'last_built_at': config.last_built_at,
        }

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'sender_id', 'owner_emails', 'channels_id', 'channels',
            'status', 'status_display', 'execution_status', 'execution_status_display',
            'progress_percent', 'total_messages', 'total_processed', 'next_run',
            'has_schedule', 'has_audience', 'has_content', 'is_ready_to_execute',
            'audience_id', 'message_content_id', 'schedule_id', 'schedule',
            'audience_rebuild', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class CampaignDetailSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source='created_by.username', read_only=True,
    )
    audience_id = serializers.IntegerField(read_only=True, allow_null=True)
    message_content_id = serializers.IntegerField(read_only=True, allow_null=True)
    schedule_id = serializers.IntegerField(read_only=True, allow_null=True)
    audience = serializers.SerializerMethodField()
    message_content = serializers.SerializerMethodField()
    schedule = serializers.SerializerMethodField()
    execution_status_display = serializers.SerializerMethodField()

    def get_execution_status_display(self, obj):
        return {
            'PENDING': 'Pending',
            'PROCESSING': 'Processing',
            'PAUSED': 'Paused',
            'STOPPED': 'Stopped',
            'COMPLETED': 'Completed',
            'FAILED': 'Failed',
        }.get(obj.execution_status, obj.execution_status.title())

    def get_message_content(self, obj):
        try:
            content = obj.message_content
        except MessageContent.DoesNotExist:
            return None
        return MessageContentApiSerializer(content).data

    def get_schedule(self, obj):
        schedule = getattr(obj, 'schedule', None)
        if schedule is None:
            return None
        return {
            'id': schedule.id,
            'campaign_name': obj.name,
            'schedule_type': schedule.schedule_type,
            'schedule_type_display': schedule.get_schedule_type_display(),
            'campaign_status': obj.status,
            'campaign_status_display': obj.get_status_display(),
            'current_window_status_display': schedule.get_schedule_status_display(),
            'schedule_summary': schedule.get_schedule_summary(),
            'start_date': schedule.start_date,
            'end_date': schedule.end_date,
            'run_days': schedule.run_days,
            'time_windows': schedule.time_windows,
            'timezone': schedule.timezone,
            'current_round': schedule.current_round,
            'current_window_date': schedule.next_run_date,
            'current_window_index': 0,
            'current_window_status': schedule.schedule_status,
            'next_run_date': schedule.next_run_date,
            'next_run_window': 0,
            'completed_windows': schedule.completed_windows,
            'total_windows_completed': schedule.total_windows_completed,
            'is_active': schedule.is_active,
            'auto_reset': schedule.auto_reset,
            'created_at': schedule.created_at,
            'updated_at': schedule.updated_at,
            'last_processed_at': schedule.last_processed_at,
        }

    def get_audience(self, obj):
        config = AudienceConfig.objects.filter(campaign=obj).first()
        members = AudienceMember.objects.filter(campaign=obj)
        member_total = members.count()
        if config is None and member_total == 0:
            return None
        total = config.total_count if config and config.is_processed else member_total
        valid = config.valid_count if config and config.is_processed else members.filter(is_valid=True).count()
        invalid = config.invalid_count if config and config.is_processed else members.filter(is_valid=False).count()
        return {
            'id': config.id if config else obj.pk,
            'source_type': config.source_type if config else 'manual',
            'summary': {'total': total, 'valid': valid, 'invalid': invalid},
            'total_count': total,
            'valid_count': valid,
            'invalid_count': invalid,
            'valid_percentage': valid * 100 / total if total else 0,
            'database_table': config.source_table if config else '',
            'id_field': config.source_msisdn_column if config else '',
            'filter_condition': config.source_filter_clause if config else '',
            'created_at': config.created_at if config else obj.created_at,
            'updated_at': config.updated_at if config else obj.updated_at,
        }

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'sender_id', 'owner_emails', 'channels_id', 'status',
            'execution_status', 'execution_status_display', 'is_ready_to_execute',
            'audience_id', 'audience', 'message_content_id', 'message_content',
            'schedule_id', 'schedule', 'created_at', 'updated_at',
            'activated_at', 'paused_at', 'resumed_at', 'completed_at',
            'stopped_at', 'created_by', 'created_by_username',
            'activated_by', 'is_deleted', 'deleted_at',
        ]
        read_only_fields = [
            'id', 'status', 'is_ready_to_execute', 'audience_id',
            'message_content_id', 'schedule_id', 'created_at',
            'updated_at', 'activated_at', 'paused_at', 'resumed_at',
            'completed_at', 'stopped_at', 'created_by', 'activated_by',
            'is_deleted', 'deleted_at',
        ]


class CampaignCreateUpdateSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=True, allow_blank=False)
    sender_id = serializers.CharField(required=True, allow_blank=False)
    owner_emails = serializers.ListField(
        child=serializers.EmailField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    channels = serializers.ListField(
        child=serializers.CharField(max_length=100, allow_blank=False),
        allow_empty=False,
        required=True,
    )

    class Meta:
        model = Campaign
        fields = ['name', 'sender_id', 'owner_emails', 'channels']

    @staticmethod
    def _active_channel_ids_by_name():
        channel_ids = {}
        for channel in Channel.objects.filter(is_active=True):
            channel_ids[channel.name.strip().lower()] = channel.id
            channel_ids[channel.code.strip().lower()] = channel.id
        return channel_ids

    def validate_owner_emails(self, value):
        normalized = []
        for email in value:
            email = email.strip().lower()
            if email not in normalized:
                normalized.append(email)
        if len(normalized) > 50:
            raise serializers.ValidationError('A campaign can have at most 50 owners.')
        return normalized

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Campaign name is required.')
        if len(value) < 3:
            raise serializers.ValidationError(
                'Campaign name must be at least 3 characters.'
            )
        if len(value) > 255:
            raise serializers.ValidationError(
                'Campaign name must not exceed 255 characters.'
            )
        return value

    def validate_sender_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Sender ID is required.')
        if len(value) < 3 or len(value) > 11:
            raise serializers.ValidationError(
                'Sender ID must be between 3 and 11 characters.'
            )
        if not value.replace('_', '').isalnum():
            raise serializers.ValidationError(
                'Sender ID can only contain letters, numbers, and underscores.'
            )
        if not SenderID.objects.filter(sender_id=value, is_active=True).exists():
            raise serializers.ValidationError(
                f"Sender ID '{value}' must exist as an active row in the SenderID model."
            )
        return value

    def validate_channels(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('Channels must be a list of Channel names.')
        if not value:
            raise serializers.ValidationError(
                'At least one channel must be selected.'
            )

        normalized = []
        for raw in value:
            if not isinstance(raw, str):
                raise serializers.ValidationError('Channel entries must be strings.')
            name = raw.strip()
            if not name:
                raise serializers.ValidationError('Channel name is required.')
            normalized.append(name)

        available = set(self._active_channel_ids_by_name())
        invalid = [name for name in normalized if name.lower() not in available]
        if invalid:
            raise serializers.ValidationError(
                f'Invalid or inactive channel(s): {invalid}. '
                f'Available channels: {sorted(available)}'
            )
        return normalized

    def create(self, validated_data):
        channels = validated_data.pop('channels')
        channel_map = self._active_channel_ids_by_name()
        channel_ids = [channel_map[name.strip().lower()] for name in channels]

        campaign = Campaign.objects.create(
            name=validated_data['name'],
            sender_id=validated_data['sender_id'],
            owner_emails=validated_data.pop('owner_emails', []),
            channels_id=channel_ids,
            status=validated_data.pop('status', 'draft'),
            is_ready_to_execute=False,
            created_by=validated_data.pop('created_by', None),
            activated_by=validated_data.pop('activated_by', None),
        )
        return campaign

    def update(self, instance, validated_data):
        channels = validated_data.pop('channels', None)
        owner_emails = validated_data.pop('owner_emails', None)
        if channels is not None:
            channel_map = self._active_channel_ids_by_name()
            instance.channels_id = [channel_map[name.strip().lower()] for name in channels]

        if 'name' in validated_data:
            instance.name = validated_data['name']
        if 'sender_id' in validated_data:
            instance.sender_id = validated_data['sender_id']
        if owner_emails is not None:
            instance.owner_emails = owner_emails

        instance.save()
        return instance


class ScheduleSerializer(serializers.ModelSerializer):
    schedule_summary = serializers.SerializerMethodField()
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    schedule_type_display = serializers.CharField(source='get_schedule_type_display', read_only=True)
    campaign_status = serializers.CharField(source='campaign.status', read_only=True)
    campaign_status_display = serializers.SerializerMethodField()
    campaign_info = serializers.SerializerMethodField()
    current_window_status = serializers.CharField(source='schedule_status', read_only=True)
    current_window_status_display = serializers.SerializerMethodField()
    current_window_date = serializers.DateField(source='next_run_date', read_only=True)
    current_window_index = serializers.SerializerMethodField()
    next_run_window = serializers.SerializerMethodField()
    upcoming_windows = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = [
            'id', 'campaign', 'campaign_name', 'campaign_info', 'schedule_type',
            'schedule_type_display', 'campaign_status', 'campaign_status_display',
            'current_window_status', 'current_window_status_display',
            'current_window_date', 'current_window_index', 'next_run_window',
            'upcoming_windows', 'start_date',
            'end_date', 'run_days', 'time_windows', 'timezone', 'is_active',
            'auto_reset', 'schedule_status', 'current_round', 'next_run_date',
            'last_processed_at', 'total_windows_completed', 'schedule_summary',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_schedule_summary(self, obj) -> str:
        return obj.get_schedule_summary()

    def get_campaign_status_display(self, obj) -> str:
        return obj.campaign.get_status_display()

    def get_campaign_info(self, obj) -> dict:
        return {
            'id': obj.campaign_id,
            'name': obj.campaign.name,
            'status': obj.campaign.status,
            'execution_status': obj.campaign.status,
        }

    def get_current_window_status_display(self, obj) -> str:
        return obj.get_schedule_status_display()

    def get_current_window_index(self, obj) -> int:
        return 0

    def get_next_run_window(self, obj) -> int:
        return 0

    def get_upcoming_windows(self, obj) -> list:
        return []


class ScheduleCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Schedule
        fields = [
            'schedule_type', 'start_date', 'end_date', 'run_days',
            'time_windows', 'timezone', 'auto_reset',
        ]

    def validate_run_days(self, value):
        if value is None:
            return []
        if not isinstance(value, list) or any(day not in range(7) for day in value):
            raise serializers.ValidationError('run_days must contain values from 0 to 6.')
        return sorted(set(value))

    def validate_time_windows(self, value):
        from datetime import datetime
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError('At least one time window is required.')
        parsed = []
        for index, window in enumerate(value):
            if not isinstance(window, dict) or 'start' not in window or 'end' not in window:
                raise serializers.ValidationError(f'Window {index} must contain start and end.')
            try:
                start = datetime.strptime(window['start'], '%H:%M').time()
                end = datetime.strptime(window['end'], '%H:%M').time()
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'Window {index} must use HH:MM format.')
            if start >= end or any(start < old_end and end > old_start for old_start, old_end in parsed):
                raise serializers.ValidationError(f'Window {index} is invalid or overlaps another window.')
            parsed.append((start, end))
        return value

    def validate(self, attrs):
        from datetime import date
        get = lambda key, default=None: attrs.get(key, getattr(self.instance, key, default) if self.instance else default)
        start_date = get('start_date')
        end_date = get('end_date')
        schedule_type = get('schedule_type', 'once')
        run_days = get('run_days', [])
        time_windows = get('time_windows', [])
        if not start_date:
            raise serializers.ValidationError({'start_date': 'Start date is required.'})
        if end_date and start_date > end_date:
            raise serializers.ValidationError({'end_date': 'End date must be on or after start date.'})
        if schedule_type == 'once' and start_date < date.today():
            raise serializers.ValidationError({'start_date': 'Start date cannot be in the past.'})
        if schedule_type == 'weekly' and not run_days:
            raise serializers.ValidationError({'run_days': 'Weekly schedules require at least one run day.'})
        if not time_windows:
            raise serializers.ValidationError({'time_windows': 'At least one time window is required.'})
        return attrs

