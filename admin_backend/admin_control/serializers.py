from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    AdminAuditLog,
    Campaign,
    Channel,
    ChannelSMSCBinding,
    GlobalTPSConfig,
    LoginAttempt,
    NAddress,
    NAddressesConfig,
    SMSCConfig,
    SenderID,
    SenderIDDetails,
    SenderSMSCBinding,
    UserProfile,
)


class AssignedUserIdField(serializers.PrimaryKeyRelatedField):
    def to_representation(self, value):
        return value.user_id

    def to_internal_value(self, data):
        profile = UserProfile.objects.filter(
            user_id=data, role=UserProfile.Role.CAMPAIGN_MANAGER
        ).first()
        if profile is None:
            self.fail("does_not_exist", pk_value=data)
        return profile


class SMSCConfigSerializer(serializers.ModelSerializer):
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles",
        many=True,
        queryset=UserProfile.objects.all(),
        required=False,
    )
    has_api_key = serializers.SerializerMethodField()
    has_api_secret = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = SMSCConfig
        exclude = ("created_at", "updated_at", "api_key", "api_secret", "password")
        read_only_fields = ("id", "last_tested_at", "last_test_status", "last_test_message")

    def get_has_api_key(self, obj):
        return bool(obj.api_key)

    def get_has_api_secret(self, obj):
        return bool(obj.api_secret)

    def get_has_password(self, obj):
        return bool(obj.password)


class SMSCConfigWriteSerializer(serializers.ModelSerializer):
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles",
        many=True,
        queryset=UserProfile.objects.all(),
        required=False,
    )

    AUTH_TYPES = {"none", "api_key", "bearer", "basic"}
    HTTP_METHODS = {"GET", "POST", "PUT"}

    class Meta:
        model = SMSCConfig
        exclude = ("created_at", "updated_at", "last_tested_at", "last_test_status", "last_test_message")
        read_only_fields = ("id",)
        extra_kwargs = {
            "api_key": {"write_only": True, "required": False, "allow_blank": True},
            "api_secret": {"write_only": True, "required": False, "allow_blank": True},
            "password": {"write_only": True, "required": False, "allow_blank": True},
        }

    def update(self, instance, validated_data):
        for field in ("api_key", "api_secret", "password"):
            if validated_data.get(field) == "":
                validated_data.pop(field)
        return super().update(instance, validated_data)

    def validate(self, attrs):
        auth_type = attrs.get("auth_type", getattr(self.instance, "auth_type", "api_key"))
        api_key = attrs.get("api_key", getattr(self.instance, "api_key", ""))
        if self.instance and api_key == "":
            api_key = self.instance.api_key
        username = attrs.get("username", getattr(self.instance, "username", ""))
        password = attrs.get("password", getattr(self.instance, "password", ""))
        if self.instance and password == "":
            password = self.instance.password
        if auth_type not in self.AUTH_TYPES:
            raise serializers.ValidationError({"auth_type": "Choose none, api_key, bearer, or basic."})
        if auth_type in {"api_key", "bearer"} and not api_key:
            raise serializers.ValidationError({"api_key": "This authentication type requires an API key."})
        if auth_type == "basic" and (not username or not password):
            raise serializers.ValidationError({"username": "Basic authentication requires a username and password."})
        if attrs.get("http_method", getattr(self.instance, "http_method", "POST")) not in self.HTTP_METHODS:
            raise serializers.ValidationError({"http_method": "Choose GET, POST, or PUT."})
        for field in ("rate_limit_per_second", "rate_limit_per_minute"):
            if attrs.get(field, getattr(self.instance, field, 1)) < 1:
                raise serializers.ValidationError({field: "Must be at least 1."})
        for field in ("request_timeout_seconds", "connect_timeout_seconds"):
            if attrs.get(field, getattr(self.instance, field, 1)) < 1:
                raise serializers.ValidationError({field: "Must be at least 1."})
        for field in ("extra_headers", "extra_params"):
            value = attrs.get(field)
            if value is not None and not isinstance(value, dict):
                raise serializers.ValidationError({field: "Must be a JSON object."})
        return attrs


class SenderTypeField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(choices=SenderIDDetails.SenderType.choices, **kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        try:
            return instance.admin_details.sender_type
        except SenderIDDetails.DoesNotExist:
            return (
                SenderIDDetails.SenderType.NUMERIC
                if instance.sender_id.isdigit()
                else SenderIDDetails.SenderType.ALPHANUMERIC
            )


class SenderCountryField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(required=False, allow_blank=True, **kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        try:
            return instance.admin_details.country
        except SenderIDDetails.DoesNotExist:
            return ""


class SenderTPSField(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(
            required=False, allow_null=True, min_value=1, max_value=100000, **kwargs
        )

    def get_attribute(self, instance):
        return instance

    def to_representation(self, instance):
        try:
            return instance.admin_details.tps_limit
        except SenderIDDetails.DoesNotExist:
            return None


class SenderIDSerializer(serializers.ModelSerializer):
    sender_type = SenderTypeField(required=False)
    country = SenderCountryField()
    tps_limit = SenderTPSField()
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles", many=True, queryset=UserProfile.objects.all(), required=False
    )
    smsc_ids = serializers.PrimaryKeyRelatedField(
        queryset=SMSCConfig.objects.all(), many=True, required=False, write_only=True
    )
    bound_smsc_ids = serializers.SerializerMethodField()

    class Meta:
        model = SenderID
        fields = (
            "id", "sender_id", "name", "description", "sender_type", "country",
            "tps_limit", "is_default", "is_active",
            "assigned_user_ids", "smsc_ids", "bound_smsc_ids", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_bound_smsc_ids(self, obj):
        return list(
            SenderSMSCBinding.objects.filter(sender_id=obj).values_list("smsc_id", flat=True)
        )

    def validate_sender_id(self, value):
        value = value.strip()
        senders = SenderID.objects.filter(sender_id__iexact=value)
        if self.instance:
            senders = senders.exclude(pk=self.instance.pk)
        if senders.exists():
            raise serializers.ValidationError("This Sender ID already exists.")
        if not value:
            raise serializers.ValidationError("Sender ID is required.")
        return value

    def validate(self, attrs):
        smscs = attrs.get("smsc_ids")
        if self.instance is None and not smscs:
            raise serializers.ValidationError(
                {"smsc_ids": "A Sender ID must be bound to at least one SMSC."}
            )
        if self.instance:
            existing_ids = set(
                SenderSMSCBinding.objects.filter(sender_id=self.instance).values_list(
                    "smsc_id", flat=True
                )
            )
            if smscs is None and not existing_ids:
                raise serializers.ValidationError(
                    {"smsc_ids": "A Sender ID must be bound to at least one SMSC."}
                )
            if smscs is not None:
                new_ids = {smsc.pk for smsc in smscs}
                if not new_ids:
                    raise serializers.ValidationError(
                        {"smsc_ids": "A Sender ID must remain bound to at least one SMSC."}
                    )
                removed_ids = existing_ids - new_ids
                if NAddress.objects.filter(
                    sender_id=self.instance, smsc_id__in=removed_ids
                ).exists():
                    raise serializers.ValidationError(
                        {"smsc_ids": "Reassign dependent N-addresses before removing an SMSC binding."}
                    )
        sender_value = attrs.get(
            "sender_id", self.instance.sender_id if self.instance else ""
        )
        details = getattr(self.instance, "admin_details", None) if self.instance else None
        sender_type = attrs.get(
            "sender_type",
            details.sender_type if details else (
                SenderIDDetails.SenderType.NUMERIC
                if sender_value.isdigit()
                else SenderIDDetails.SenderType.ALPHANUMERIC
            ),
        )
        tps_limit = attrs.get("tps_limit", details.tps_limit if details else None)
        if sender_type == SenderIDDetails.SenderType.NUMERIC and not sender_value.isdigit():
            raise serializers.ValidationError(
                {"sender_type": "Numeric Sender IDs may contain only digits."}
            )
        if sender_type == SenderIDDetails.SenderType.ALPHANUMERIC and not sender_value.isalnum():
            raise serializers.ValidationError(
                {"sender_type": "Alphanumeric Sender IDs may contain only letters and digits."}
            )
        if sender_type == SenderIDDetails.SenderType.SHORT_CODE and (
            not sender_value.isdigit() or not 3 <= len(sender_value) <= 8
        ):
            raise serializers.ValidationError(
                {"sender_type": "Short codes must contain 3 to 8 digits."}
            )
        if tps_limit is not None and not 1 <= tps_limit <= 100000:
            raise serializers.ValidationError(
                {"tps_limit": "Sender TPS must be from 1 to 100000."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        smscs = validated_data.pop("smsc_ids")
        assigned_profiles = validated_data.pop("assigned_profiles", [])
        sender_type = validated_data.pop("sender_type", None)
        country = validated_data.pop("country", "")
        tps_limit = validated_data.pop("tps_limit", None)
        sender_id = SenderID.objects.create(**validated_data)
        sender_id.assigned_profiles.set(assigned_profiles)
        SenderSMSCBinding.objects.bulk_create(
            [SenderSMSCBinding(sender_id=sender_id, smsc=smsc) for smsc in smscs]
        )
        if sender_type is None:
            sender_type = (
                SenderIDDetails.SenderType.NUMERIC
                if sender_id.sender_id.isdigit()
                else SenderIDDetails.SenderType.ALPHANUMERIC
            )
        SenderIDDetails.objects.create(
            sender_id=sender_id,
            sender_type=sender_type,
            country=country,
            tps_limit=tps_limit,
        )
        return sender_id

    @transaction.atomic
    def update(self, instance, validated_data):
        smscs = validated_data.pop("smsc_ids", None)
        assigned_profiles = validated_data.pop("assigned_profiles", None)
        details_data = {
            key: validated_data.pop(key)
            for key in ("sender_type", "country", "tps_limit")
            if key in validated_data
        }
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        details = getattr(instance, "admin_details", None)
        if details_data or details:
            if details:
                for field, value in details_data.items():
                    setattr(details, field, value)
                details.save()
            else:
                details_data.setdefault(
                    "sender_type",
                    SenderIDDetails.SenderType.NUMERIC
                    if instance.sender_id.isdigit()
                    else SenderIDDetails.SenderType.ALPHANUMERIC,
                )
                SenderIDDetails.objects.create(sender_id=instance, **details_data)
        if assigned_profiles is not None:
            instance.assigned_profiles.set(assigned_profiles)
        if smscs is not None:
            new_ids = {smsc.pk for smsc in smscs}
            SenderSMSCBinding.objects.filter(sender_id=instance).exclude(
                smsc_id__in=new_ids
            ).delete()
            existing_ids = set(
                SenderSMSCBinding.objects.filter(sender_id=instance).values_list(
                    "smsc_id", flat=True
                )
            )
            SenderSMSCBinding.objects.bulk_create(
                [
                    SenderSMSCBinding(sender_id=instance, smsc=smsc)
                    for smsc in smscs
                    if smsc.pk not in existing_ids
                ]
            )
        return instance


class ChannelBindingInputSerializer(serializers.Serializer):
    smsc = serializers.PrimaryKeyRelatedField(queryset=SMSCConfig.objects.all())
    allowed_sender_ids = serializers.PrimaryKeyRelatedField(
        queryset=SenderID.objects.all(), many=True, required=False
    )
    default_tps = serializers.IntegerField(min_value=1, max_value=100000, default=100)
    priority = serializers.IntegerField(min_value=0, default=100)


class ChannelSerializer(serializers.ModelSerializer):
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles", many=True, queryset=UserProfile.objects.all(), required=False
    )
    smsc_bindings = ChannelBindingInputSerializer(many=True, required=False, write_only=True)
    bound_smsc_bindings = serializers.SerializerMethodField()

    class Meta:
        model = Channel
        fields = (
            "id", "code", "name", "is_active", "assigned_user_ids",
            "smsc_bindings", "bound_smsc_bindings", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_bound_smsc_bindings(self, obj):
        return ChannelSMSCBindingSerializer(
            ChannelSMSCBinding.objects.filter(channel=obj).select_related("smsc").prefetch_related(
                "allowed_sender_ids"
            ),
            many=True,
        ).data

    def validate_code(self, value):
        value = value.strip().lower()
        channels = Channel.objects.filter(code__iexact=value)
        if self.instance:
            channels = channels.exclude(pk=self.instance.pk)
        if channels.exists():
            raise serializers.ValidationError("This channel code already exists.")
        if not value:
            raise serializers.ValidationError("Channel code is required.")
        return value

    def validate_name(self, value):
        value = value.strip()
        channels = Channel.objects.filter(name__iexact=value)
        if self.instance:
            channels = channels.exclude(pk=self.instance.pk)
        if channels.exists():
            raise serializers.ValidationError("This channel name already exists.")
        if not value:
            raise serializers.ValidationError("Channel name is required.")
        return value

    def validate(self, attrs):
        bindings = attrs.get("smsc_bindings")
        if self.instance is None and not bindings:
            raise serializers.ValidationError(
                {"smsc_bindings": "A channel must be created with at least one SMSC binding."}
            )
        if bindings is not None:
            if not bindings:
                raise serializers.ValidationError(
                    {"smsc_bindings": "A channel must remain bound to at least one SMSC."}
                )
            smsc_ids = [binding["smsc"].pk for binding in bindings]
            if len(smsc_ids) != len(set(smsc_ids)):
                raise serializers.ValidationError(
                    {"smsc_bindings": "An SMSC can only be bound to a channel once."}
                )
            for binding in bindings:
                if any(
                    not SenderSMSCBinding.objects.filter(
                        sender_id=sender, smsc=binding["smsc"]
                    ).exists()
                    for sender in binding.get("allowed_sender_ids", [])
                ):
                    raise serializers.ValidationError(
                        {"smsc_bindings": "Each allowed Sender ID must be bound to the selected SMSC."}
                    )
            if self.instance:
                new_smsc_ids = set(smsc_ids)
                removed_bindings = ChannelSMSCBinding.objects.filter(
                    channel=self.instance
                ).exclude(smsc_id__in=new_smsc_ids)
                if any(
                    NAddress.objects.filter(
                        channel=self.instance, smsc_id=binding.smsc_id
                    ).exists()
                    for binding in removed_bindings
                ):
                    raise serializers.ValidationError(
                        {"smsc_bindings": "Reassign dependent N-addresses before removing an SMSC binding."}
                    )
        elif self.instance and not ChannelSMSCBinding.objects.filter(channel=self.instance).exists():
            raise serializers.ValidationError(
                {"smsc_bindings": "A channel must be bound to at least one SMSC."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        bindings = validated_data.pop("smsc_bindings")
        assigned_profiles = validated_data.pop("assigned_profiles", [])
        channel = Channel.objects.create(**validated_data)
        channel.assigned_profiles.set(assigned_profiles)
        self._save_bindings(channel, bindings)
        return channel

    @transaction.atomic
    def update(self, instance, validated_data):
        bindings = validated_data.pop("smsc_bindings", None)
        assigned_profiles = validated_data.pop("assigned_profiles", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if assigned_profiles is not None:
            instance.assigned_profiles.set(assigned_profiles)
        if bindings is not None:
            self._save_bindings(instance, bindings)
        return instance

    @staticmethod
    def _save_bindings(channel, bindings):
        incoming_smsc_ids = {binding["smsc"].pk for binding in bindings}
        existing = {
            binding.smsc_id: binding
            for binding in ChannelSMSCBinding.objects.filter(channel=channel)
        }
        for smsc_id, binding in existing.items():
            if smsc_id not in incoming_smsc_ids:
                binding.delete()
        for binding_data in bindings:
            allowed_sender_ids = binding_data.pop("allowed_sender_ids", [])
            smsc = binding_data.pop("smsc")
            binding, _ = ChannelSMSCBinding.objects.update_or_create(
                channel=channel,
                smsc=smsc,
                defaults=binding_data,
            )
            binding.allowed_sender_ids.set(allowed_sender_ids)


class GlobalTPSConfigSerializer(serializers.ModelSerializer):
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles", many=True, queryset=UserProfile.objects.all(), required=False
    )

    class Meta:
        model = GlobalTPSConfig
        fields = ("id", "name", "description", "global_tps", "is_default", "is_active", "assigned_user_ids", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_global_tps(self, value):
        if not 1 <= value <= 100000:
            raise serializers.ValidationError("Global TPS must be from 1 to 100000.")
        return value


class NAddressesConfigSerializer(serializers.ModelSerializer):
    assigned_user_ids = AssignedUserIdField(
        source="assigned_profiles", many=True, queryset=UserProfile.objects.all(), required=False
    )

    class Meta:
        model = NAddressesConfig
        fields = ("id", "name", "description", "max_addresses_per_request", "is_default", "is_active", "assigned_user_ids", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_max_addresses_per_request(self, value):
        if value < 1:
            raise serializers.ValidationError("Maximum addresses per request must be at least 1.")
        return value


class NAddressSerializer(serializers.ModelSerializer):
    assigned_user_ids = serializers.PrimaryKeyRelatedField(
        source="assigned_users", many=True, queryset=User.objects.all(), required=False
    )

    class Meta:
        model = NAddress
        fields = (
            "id", "value", "address_type", "smsc", "channel", "sender_id",
            "is_active", "tps_cap", "assigned_user_ids", "notes", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_tps_cap(self, value):
        if value is not None and not 1 <= value <= 100000:
            raise serializers.ValidationError("N-address TPS cap must be from 1 to 100000.")
        return value

    def validate_assigned_user_ids(self, users):
        valid_ids = set(
            UserProfile.objects.filter(
                user__in=users, role=UserProfile.Role.CAMPAIGN_MANAGER
            ).values_list("user_id", flat=True)
        )
        if valid_ids != {user.pk for user in users}:
            raise serializers.ValidationError("N-addresses can only be assigned to Campaign Managers.")
        return users

    def validate(self, attrs):
        smsc = attrs.get("smsc", self.instance.smsc if self.instance else None)
        channel = attrs.get("channel", self.instance.channel if self.instance else None)
        sender_id = attrs.get("sender_id", self.instance.sender_id if self.instance else None)
        value = attrs.get("value", self.instance.value if self.instance else "")
        address_type = attrs.get(
            "address_type", self.instance.address_type if self.instance else None
        )
        if address_type == NAddress.AddressType.MSISDN:
            digits = value[1:] if value.startswith("+") else value
            if not digits.isdigit() or not 1 <= len(digits) <= 20:
                raise serializers.ValidationError(
                    {"value": "MSISDN values must contain 1-20 digits, optionally prefixed by +."}
                )
        if channel and smsc and not ChannelSMSCBinding.objects.filter(
            channel=channel, smsc=smsc
        ).exists():
            raise serializers.ValidationError(
                {"channel": "The selected channel is not bound to this SMSC."}
            )
        if sender_id and smsc and not SenderSMSCBinding.objects.filter(
            sender_id=sender_id, smsc=smsc
        ).exists():
            raise serializers.ValidationError(
                {"sender_id": "The selected Sender ID is not bound to this SMSC."}
            )
        if channel and sender_id and smsc:
            binding = ChannelSMSCBinding.objects.filter(channel=channel, smsc=smsc).first()
            if binding and binding.allowed_sender_ids.exists() and not binding.allowed_sender_ids.filter(
                pk=sender_id.pk
            ).exists():
                raise serializers.ValidationError(
                    {"sender_id": "The Sender ID is not allowed on the selected channel."}
                )
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    department = serializers.CharField(required=False, allow_blank=False)
    role = serializers.ChoiceField(choices=UserProfile.Role.choices, required=False)
    username = serializers.CharField(source="user.username")
    email = serializers.EmailField(source="user.email")
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)
    is_active = serializers.BooleanField(source="user.is_active", required=False)
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    user_id = serializers.IntegerField(source="user.pk", read_only=True)
    full_name = serializers.SerializerMethodField()
    assigned_config_counts = serializers.SerializerMethodField()
    assigned_smscs = serializers.PrimaryKeyRelatedField(
        source="sms_configs", many=True, queryset=SMSCConfig.objects.all(), required=False
    )
    assigned_sender_ids = serializers.PrimaryKeyRelatedField(
        source="sender_ids", many=True, queryset=SenderID.objects.all(), required=False
    )
    assigned_channels = serializers.PrimaryKeyRelatedField(
        source="channels", many=True, queryset=Channel.objects.all(), required=False
    )
    assigned_tps_configs = serializers.PrimaryKeyRelatedField(
        source="tps_configs", many=True, queryset=GlobalTPSConfig.objects.all(), required=False
    )
    assigned_n_address_configs = serializers.PrimaryKeyRelatedField(
        source="n_address_configs", many=True, queryset=NAddressesConfig.objects.all(), required=False
    )
    assigned_n_addresses = serializers.PrimaryKeyRelatedField(
        source="user.assigned_n_addresses",
        many=True,
        queryset=NAddress.objects.all(),
        required=False,
    )
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = UserProfile
        fields = (
            "id", "user_id", "username", "email", "first_name", "last_name", "full_name",
            "department", "role", "is_active", "is_locked", "last_login", "notes",
            "tps_limit", "assigned_smscs", "assigned_sender_ids", "assigned_channels",
            "assigned_tps_configs", "assigned_n_address_configs", "assigned_n_addresses",
            "assigned_config_counts",
            "password", "created_at", "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_full_name(self, profile):
        return profile.user.get_full_name()

    def get_assigned_config_counts(self, profile):
        return {
            "smsc": profile.sms_configs.count(),
            "sender_ids": profile.sender_ids.count(),
            "channels": profile.channels.count(),
            "tps": profile.tps_configs.count(),
            "n_address_configs": profile.n_address_configs.count(),
            "n_addresses": profile.user.assigned_n_addresses.count(),
        }

    def validate_tps_limit(self, value):
        if value is not None and not 1 <= value <= 100000:
            raise serializers.ValidationError("User TPS must be from 1 to 100000.")
        return value

    def validate_username(self, value):
        users = User.objects.filter(username__iexact=value)
        if self.instance:
            users = users.exclude(pk=self.instance.user_id)
        if users.exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_email(self, value):
        users = User.objects.filter(email__iexact=value)
        if self.instance:
            users = users.exclude(pk=self.instance.user_id)
        if users.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.strip()

    def validate(self, attrs):
        request = self.context.get("request")
        target = self.instance.user if self.instance else None
        if self.instance is None:
            if not attrs.get("department"):
                raise serializers.ValidationError({"department": "Department is required."})
            if not attrs.get("role"):
                raise serializers.ValidationError({"role": "Role is required."})
        if target and request and target.pk == request.user.pk and attrs.get("role", self.instance.role) != self.instance.role:
            raise serializers.ValidationError({"role": "You cannot change your own role."})
        password = attrs.get("password")
        if password:
            user_data = attrs.get("user", {})
            user = target or User(
                username=user_data.get("username", ""),
                email=user_data.get("email", ""),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
            )
            for field, value in attrs.get("user", {}).items():
                if field in {"username", "email", "first_name", "last_name"}:
                    setattr(user, field, value)
            try:
                validate_password(password, user=user)
            except DjangoValidationError as error:
                raise serializers.ValidationError({"password": error.messages}) from error
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user_data = validated_data.pop("user")
        assigned_n_addresses = user_data.pop("assigned_n_addresses", [])
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required when creating a user."})
        user = User.objects.create_user(password=password, **user_data)
        profile_data = {
            key: validated_data.pop(key)
            for key in list(validated_data)
            if key in {"sms_configs", "sender_ids", "channels", "tps_configs", "n_address_configs"}
        }
        profile = UserProfile.objects.get(user=user)
        for key, value in validated_data.items():
            setattr(profile, key, value)
        profile.save()
        self._save_assignments(profile, profile_data)
        user.assigned_n_addresses.set(assigned_n_addresses)
        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        assigned_n_addresses = user_data.pop("assigned_n_addresses", None)
        password = validated_data.pop("password", None)
        for key, value in user_data.items():
            setattr(instance.user, key, value)
        if password:
            validate_password(password, user=instance.user)
            instance.user.set_password(password)
        instance.user.save()
        assignment_fields = {"sms_configs", "sender_ids", "channels", "tps_configs", "n_address_configs"}
        assignment_data = {key: validated_data.pop(key) for key in list(validated_data) if key in assignment_fields}
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        self._save_assignments(instance, assignment_data)
        if assigned_n_addresses is not None:
            instance.user.assigned_n_addresses.set(assigned_n_addresses)
        return instance

    @staticmethod
    def _save_assignments(profile, assignment_data):
        for field, values in assignment_data.items():
            getattr(profile, field).set(values)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        identifier = attrs["username"].strip()
        user_model = User
        try:
            user = user_model.objects.get(email__iexact=identifier)
            username = user.username
        except User.DoesNotExist:
            username = identifier
            user = None
        authenticated = authenticate(
            request=self.context.get("request"),
            username=username,
            password=attrs["password"],
        )
        profile = getattr(authenticated, "admin_profile", None)
        from .models import LoginAttempt
        request = self.context.get("request")
        LoginAttempt.objects.create(
            username=identifier[:254],
            user=authenticated or user,
            succeeded=bool(
                authenticated
                and authenticated.is_active
                and profile
                and profile.role == UserProfile.Role.ADMIN
                and not profile.is_locked
            ),
            ip_address=request.META.get("REMOTE_ADDR") if request else None,
        )
        if not (
            authenticated
            and authenticated.is_active
            and profile
            and profile.role == UserProfile.Role.ADMIN
            and not profile.is_locked
        ):
            raise serializers.ValidationError("Invalid admin credentials or account is not an active Admin.")
        attrs["user"] = authenticated
        return attrs

    def create(self, validated_data):
        refresh = RefreshToken.for_user(validated_data["user"])
        return {"refresh": str(refresh), "access": str(refresh.access_token)}


class AdminAuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = AdminAuditLog
        fields = ("id", "actor", "actor_username", "action", "object_type", "object_id", "summary", "old_values", "new_values", "created_at")
        read_only_fields = fields


class LoginAttemptSerializer(serializers.ModelSerializer):
    username_display = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = LoginAttempt
        fields = ("id", "username", "username_display", "user", "succeeded", "ip_address", "created_at")
        read_only_fields = fields


class SenderSMSCBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SenderSMSCBinding
        fields = ("id", "sender_id", "smsc")

    def validate(self, attrs):
        sender = attrs.get("sender_id", self.instance.sender_id if self.instance else None)
        smsc = attrs.get("smsc", self.instance.smsc if self.instance else None)
        bindings = SenderSMSCBinding.objects.filter(sender_id=sender, smsc=smsc)
        if self.instance:
            bindings = bindings.exclude(pk=self.instance.pk)
            if (
                (sender.pk != self.instance.sender_id_id or smsc.pk != self.instance.smsc_id)
                and NAddress.objects.filter(
                    sender_id=self.instance.sender_id, smsc_id=self.instance.smsc_id
                ).exists()
            ):
                raise serializers.ValidationError(
                    "Reassign dependent N-addresses before changing this binding."
                )
        if bindings.exists():
            raise serializers.ValidationError("This Sender ID is already bound to that SMSC.")
        return attrs


class ChannelSMSCBindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelSMSCBinding
        fields = ("id", "channel", "smsc", "allowed_sender_ids", "default_tps", "priority")

    def validate_default_tps(self, value):
        if not 1 <= value <= 100000:
            raise serializers.ValidationError("Channel TPS must be from 1 to 100000.")
        return value

    def validate(self, attrs):
        channel = attrs.get("channel", self.instance.channel if self.instance else None)
        smsc = attrs.get("smsc", self.instance.smsc if self.instance else None)
        bindings = ChannelSMSCBinding.objects.filter(channel=channel, smsc=smsc)
        if self.instance:
            bindings = bindings.exclude(pk=self.instance.pk)
            changing_binding = (
                channel.pk != self.instance.channel_id or smsc.pk != self.instance.smsc_id
            )
            if changing_binding and NAddress.objects.filter(
                channel_id=self.instance.channel_id, smsc_id=self.instance.smsc_id
            ).exists():
                raise serializers.ValidationError(
                    "Reassign dependent N-addresses before changing this binding."
                )
            if (
                channel.pk != self.instance.channel_id
                and ChannelSMSCBinding.objects.filter(channel_id=self.instance.channel_id).count() <= 1
            ):
                raise serializers.ValidationError(
                    "A channel must remain bound to at least one SMSC."
                )
        if bindings.exists():
            raise serializers.ValidationError("This channel is already bound to that SMSC.")
        allowed_sender_ids = attrs.get(
            "allowed_sender_ids",
            list(self.instance.allowed_sender_ids.all()) if self.instance else [],
        )
        unbound_senders = [
            sender.pk
            for sender in allowed_sender_ids
            if not SenderSMSCBinding.objects.filter(sender_id=sender, smsc=smsc).exists()
        ]
        if unbound_senders:
            raise serializers.ValidationError(
                {"allowed_sender_ids": "Every allowed Sender ID must be bound to this SMSC."}
            )
        return attrs
