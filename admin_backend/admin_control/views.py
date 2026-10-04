import logging
import os
import secrets
import smtplib
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import audit, snapshot
from .models import (
    AdminAuditLog,
    AdminEmailConfig,
    Campaign,
    Channel,
    ChannelSMSCBinding,
    GlobalTPSConfig,
    LoginAttempt,
    NAddress,
    NAddressesConfig,
    PasswordResetChallenge,
    SMSCConfig,
    SenderID,
    SenderSMSCBinding,
    UserProfile,
)
from .permissions import IsActivePlatformUser, IsPlatformAdmin
from .serializers import (
    AdminAuditLogSerializer,
    AdminEmailConfigSerializer,
    ChannelSerializer,
    ChannelSMSCBindingSerializer,
    GlobalTPSConfigSerializer,
    LoginAttemptSerializer,
    LoginSerializer,
    NAddressSerializer,
    NAddressesConfigSerializer,
    SMSCConfigSerializer,
    SMSCConfigWriteSerializer,
    SenderIDSerializer,
    SenderSMSCBindingSerializer,
    UserCampaignSerializer,
    UserProfileSerializer,
)
from .email_service import AdminEmailNotConfigured, send_admin_email

logger = logging.getLogger(__name__)


def _user_snapshot(profile):
    values = snapshot(profile)
    values.update(
        {
            "username": profile.user.username,
            "email": profile.user.email,
            "first_name": profile.user.first_name,
            "last_name": profile.user.last_name,
            "is_active": profile.user.is_active,
        }
    )
    return values


def _serialize_manager_configs(serializer_class, queryset):
    return [
        {key: value for key, value in config.items() if key != "assigned_user_ids"}
        for config in serializer_class(queryset, many=True).data
    ]


def _user_portal_url(profile):
    return (
        os.environ.get("ADMIN_PORTAL_URL", "http://localhost:4173")
        if profile.role == UserProfile.Role.ADMIN
        else os.environ.get("CAMPAIGN_MANAGER_URL", "http://localhost:3000")
    ).rstrip("/")


def _user_login_url(profile):
    return f"{_user_portal_url(profile)}/login"


def _user_password_reset_url(profile, challenge, token):
    fragment = urlencode({"challenge": challenge.pk, "token": token})
    return f"{_user_portal_url(profile)}/reset-password#{fragment}"


class AdminLoginView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.create(serializer.validated_data))


class AdminMeView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        return Response(UserProfileSerializer(request.user.admin_profile, context={"request": request}).data)


class UserListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = UserProfileSerializer

    def get_queryset(self):
        queryset = UserProfile.objects.select_related("user").prefetch_related(
            "sms_configs", "sender_ids", "channels", "tps_configs", "n_address_configs"
        )
        role = self.request.query_params.get("role")
        department = self.request.query_params.get("department")
        active = self.request.query_params.get("is_active")
        account_status = self.request.query_params.get("status")
        assigned = self.request.query_params.get("assigned")
        search = self.request.query_params.get("search")
        if role:
            queryset = queryset.filter(role=role)
        if department:
            queryset = queryset.filter(department__icontains=department)
        if active in {"true", "false"}:
            queryset = queryset.filter(user__is_active=(active == "true"))
        if account_status == "active":
            queryset = queryset.filter(user__is_active=True, is_locked=False)
        elif account_status == "inactive":
            queryset = queryset.filter(user__is_active=False)
        elif account_status == "locked":
            queryset = queryset.filter(is_locked=True)
        if assigned == "true":
            queryset = queryset.filter(
                Q(sms_configs__isnull=False)
                | Q(sender_ids__isnull=False)
                | Q(channels__isnull=False)
                | Q(tps_configs__isnull=False)
                | Q(n_address_configs__isnull=False)
                | Q(user__assigned_n_addresses__isnull=False)
            )
        elif assigned == "false":
            queryset = queryset.filter(
                sms_configs__isnull=True,
                sender_ids__isnull=True,
                channels__isnull=True,
                tps_configs__isnull=True,
                n_address_configs__isnull=True,
                user__assigned_n_addresses__isnull=True,
            )
        if search:
            queryset = queryset.filter(
                Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(department__icontains=search)
            )
        return queryset.distinct()

    @transaction.atomic
    def perform_create(self, serializer):
        profile = serializer.save()
        audit(
            self.request,
            "create",
            profile,
            f"Created user {profile.user.username}.",
            new_values=_user_snapshot(profile),
        )
        temporary_password = self.request.data.get("password")
        login_url = _user_login_url(profile)
        full_name = profile.user.get_full_name() or profile.user.username
        role_label = profile.get_role_display()
        text_body = (
            f"Hello {full_name},\n\n"
            f"Your {role_label} account has been created.\n"
            f"Username: {profile.user.username}\n"
            f"Temporary password: {temporary_password}\n\n"
            f"Sign in here: {login_url}\n"
            "You will be asked to change this password when you first sign in."
        )
        html_body = render_to_string(
            "admin_control/emails/account_created.html",
            {
                "full_name": full_name,
                "role_label": role_label,
                "username": profile.user.username,
                "temporary_password": temporary_password,
                "login_url": login_url,
            },
        )
        try:
            send_admin_email(
                profile.user.email,
                "Your SMS platform account",
                text_body,
                html_body,
            )
        except (AdminEmailNotConfigured, smtplib.SMTPException, OSError) as error:
            logger.exception("Could not send the new account email.")
            from rest_framework.exceptions import APIException

            failure = APIException("User account email could not be sent. Check admin email settings and try again.")
            failure.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            raise failure from error


class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = UserProfileSerializer
    queryset = UserProfile.objects.select_related("user")

    def _admin_count(self):
        return UserProfile.objects.filter(role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False).count()

    def perform_update(self, serializer):
        instance = self.get_object()
        old_values = _user_snapshot(instance)
        old_role, old_active, old_locked = instance.role, instance.user.is_active, instance.is_locked
        role = serializer.validated_data.get("role", old_role)
        user_data = serializer.validated_data.get("user", {})
        next_active = user_data.get("is_active", old_active)
        next_locked = serializer.validated_data.get("is_locked", old_locked)
        removes_admin = (
            old_role == UserProfile.Role.ADMIN
            and old_active
            and not old_locked
            and (role != old_role or not next_active or next_locked)
        )
        with transaction.atomic():
            if instance.user_id == self.request.user.id and role != old_role:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"role": "You cannot change your own role."})
            if removes_admin and len(
                list(
                    UserProfile.objects.select_for_update()
                    .filter(role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False)
                    .values_list("pk", flat=True)
                )
            ) <= 1:
                from rest_framework.exceptions import ValidationError
                raise ValidationError("Cannot remove or disable the last active Admin.")
            profile = serializer.save()
            audit(
                self.request, "update", profile, f"Updated user {profile.user.username}.",
                old_values=old_values,
                new_values=_user_snapshot(profile),
            )

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError

        with transaction.atomic():
            instance = UserProfile.objects.select_for_update().select_related("user").get(
                pk=instance.pk
            )
            if instance.user_id == self.request.user.id:
                raise ValidationError("You cannot delete your own account.")
            active_admin_ids = list(
                UserProfile.objects.select_for_update()
                .filter(role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False)
                .values_list("pk", flat=True)
            )
            if (
                instance.role == UserProfile.Role.ADMIN
                and instance.user.is_active
                and not instance.is_locked
                and len(active_admin_ids) <= 1
            ):
                raise ValidationError("Cannot delete the last active Admin.")
            username = instance.user.username
            audit(
                self.request,
                "delete",
                instance,
                f"Deleted user {username}.",
                old_values=_user_snapshot(instance),
            )
            instance.user.delete()


class UserCampaignListView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = UserCampaignSerializer

    def get_queryset(self):
        profile = get_object_or_404(UserProfile, pk=self.kwargs["pk"])
        return Campaign.objects.filter(created_by_id=profile.user_id).order_by(
            "-created_at", "-id"
        )

    def list(self, request, *args, **kwargs):
        campaigns = list(self.get_queryset())
        channel_ids = {
            channel_id
            for campaign in campaigns
            for channel_id in (campaign.channels_id or [])
        }
        channel_names_by_id = dict(
            Channel.objects.filter(pk__in=channel_ids).values_list("pk", "name")
        )
        serializer = self.get_serializer(
            campaigns,
            many=True,
            context={**self.get_serializer_context(), "channel_names_by_id": channel_names_by_id},
        )
        return Response(serializer.data)


class UserPasswordResetView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        profile = get_object_or_404(UserProfile, pk=pk)
        password = request.data.get("password", "")
        if not isinstance(password, str) or not password:
            return Response({"password": ["A new password is required."]}, status=status.HTTP_400_BAD_REQUEST)
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        try:
            validate_password(password, user=profile.user)
        except ValidationError as error:
            return Response({"password": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        profile.user.set_password(password)
        profile.user.save(update_fields=["password"])
        profile.require_password_change = True
        profile.save(update_fields=["require_password_change", "updated_at"])
        audit(request, "password_reset", profile, f"Reset password for {profile.user.username}.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class InitialPasswordChangeView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        identifier = request.data.get("username", "")
        current_password = request.data.get("current_password", "")
        new_password = request.data.get("new_password", "")
        if not all(isinstance(value, str) and value for value in (identifier, current_password, new_password)):
            return Response(
                {"detail": "Username, current password, and new password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        profile = getattr(user, "admin_profile", None) if user else None
        if not (
            user
            and user.is_active
            and user.check_password(current_password)
            and profile
            and profile.role == UserProfile.Role.ADMIN
            and not profile.is_locked
            and profile.require_password_change
        ):
            return Response({"detail": "The temporary sign-in could not be verified."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as error:
            return Response({"new_password": error.messages}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password"])
            profile.require_password_change = False
            profile.save(update_fields=["require_password_change", "updated_at"])
        return Response({"success": True})


class PasswordResetRequestView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "")
        if not isinstance(email, str) or not email.strip():
            return Response({"email": ["Enter your email address."]}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
        profile = getattr(user, "admin_profile", None) if user else None
        if profile and not profile.is_locked:
            recent = PasswordResetChallenge.objects.filter(
                user=user, created_at__gte=timezone.now() - timedelta(minutes=1)
            ).exists()
            if not recent:
                token = secrets.token_urlsafe(32)
                PasswordResetChallenge.objects.filter(
                    user=user, consumed_at__isnull=True
                ).delete()
                challenge = PasswordResetChallenge.objects.create(
                    user=user,
                    token_hash=make_password(token),
                    expires_at=timezone.now() + timedelta(minutes=10),
                )
                reset_url = _user_password_reset_url(profile, challenge, token)
                try:
                    send_admin_email(
                        user.email,
                        "Reset your SMS platform password",
                        (
                            f"Hello {user.get_full_name() or user.username},\n\n"
                            "We received a request to reset your SMS platform password.\n"
                            "Use the secure link below within 10 minutes to choose a new password:\n\n"
                            f"{reset_url}\n\n"
                            "If you did not request this reset, you can ignore this email."
                        ),
                        render_to_string(
                            "admin_control/emails/password_reset_link.html",
                            {
                                "full_name": user.get_full_name() or user.username,
                                "reset_url": reset_url,
                            },
                        ),
                    )
                except (AdminEmailNotConfigured, smtplib.SMTPException, OSError) as error:
                    challenge.delete()
                    logger.exception("Could not send the password reset link.")
                    return Response(
                        {"detail": "Password reset email could not be sent. Check admin email settings."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
        return Response(
            {"detail": "If an active account matches that email, a password reset link has been sent."}
        )


class PasswordResetConfirmView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        challenge_id = request.data.get("challenge")
        token = request.data.get("token", "")
        new_password = request.data.get("new_password", "")
        try:
            challenge_id = int(challenge_id)
        except (TypeError, ValueError):
            challenge_id = 0
        if not challenge_id or not all(
            isinstance(value, str) and value for value in (token, new_password)
        ):
            return Response(
                {"detail": "A valid reset link and new password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            challenge = (
                PasswordResetChallenge.objects.select_for_update()
                .select_related("user")
                .filter(
                    pk=challenge_id,
                    consumed_at__isnull=True,
                    expires_at__gt=timezone.now(),
                    attempts__lt=5,
                )
                .first()
            )
            user = challenge.user if challenge else None
            profile = getattr(user, "admin_profile", None) if user else None
            if (
                not challenge
                or not user.is_active
                or not profile
                or profile.is_locked
                or not check_password(token, challenge.token_hash)
            ):
                if challenge:
                    challenge.attempts += 1
                    challenge.save(update_fields=["attempts"])
                return Response(
                    {"token": ["This password reset link is invalid or expired."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                validate_password(new_password, user=user)
            except DjangoValidationError as error:
                return Response({"new_password": error.messages}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(new_password)
            user.save(update_fields=["password"])
            profile.require_password_change = False
            profile.save(update_fields=["require_password_change", "updated_at"])
            challenge.consumed_at = timezone.now()
            challenge.save(update_fields=["consumed_at"])
        return Response({"success": True})


class AdminEmailConfigView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        config = AdminEmailConfig.objects.filter(is_active=True, is_default=True).first()
        if config is None:
            return Response({"configured": False})
        return Response({"configured": True, **AdminEmailConfigSerializer(config).data})

    def patch(self, request):
        config = AdminEmailConfig.objects.filter(is_active=True, is_default=True).first()
        serializer = AdminEmailConfigSerializer(
            config,
            data=request.data,
            partial=config is not None,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(is_default=True, is_active=True)
        return Response({"configured": True, **serializer.data})

    def post(self, request):
        recipient = request.data.get("recipient", "")
        if not isinstance(recipient, str) or not recipient.strip():
            return Response({"recipient": ["Enter a test recipient email."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            send_admin_email(
                recipient.strip(),
                "Admin email configuration test",
                "This is a test message from the SMS platform admin console.",
            )
        except (AdminEmailNotConfigured, smtplib.SMTPException, OSError) as error:
            logger.exception("Admin SMTP test failed.")
            return Response({"detail": f"Could not send the test email: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"success": True})


class AdminEmailServiceListCreateView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        configs = AdminEmailConfig.objects.all().order_by("-is_default", "name")
        return Response({"results": AdminEmailConfigSerializer(configs, many=True).data})

    @transaction.atomic
    def post(self, request):
        serializer = AdminEmailConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_default = serializer.validated_data.get("is_default", False)
        if not AdminEmailConfig.objects.filter(is_active=True, is_default=True).exists():
            is_default = True
        config = serializer.save(is_default=is_default)
        return Response(AdminEmailConfigSerializer(config).data, status=status.HTTP_201_CREATED)


class AdminEmailServiceDetailView(APIView):
    permission_classes = [IsPlatformAdmin]

    @transaction.atomic
    def patch(self, request, pk):
        config = get_object_or_404(AdminEmailConfig, pk=pk)
        was_default = config.is_default
        serializer = AdminEmailConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        config = serializer.save()
        if was_default and not config.is_default:
            replacement = AdminEmailConfig.objects.filter(is_active=True).order_by("name").first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default", "updated_at"])
        return Response(AdminEmailConfigSerializer(config).data)

    @transaction.atomic
    def delete(self, request, pk):
        config = get_object_or_404(AdminEmailConfig, pk=pk)
        was_default = config.is_default
        config.delete()
        if was_default:
            replacement = AdminEmailConfig.objects.filter(is_active=True).order_by("name").first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminEmailServiceTestView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, pk):
        config = get_object_or_404(AdminEmailConfig, pk=pk)
        if not config.is_active:
            return Response(
                {"detail": "Activate this email service before testing it."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        recipient = request.data.get("test_email", "")
        if not isinstance(recipient, str) or not recipient.strip():
            return Response({"test_email": ["Enter a test recipient email."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            send_admin_email(
                recipient.strip(),
                "Admin email configuration test",
                "This is a test message from the SMS platform admin console.",
                config=config,
            )
        except (AdminEmailNotConfigured, smtplib.SMTPException, OSError) as error:
            logger.exception("Admin SMTP test failed.")
            config.last_tested_at = timezone.now()
            config.last_test_status = "failed"
            config.last_test_message = str(error)
            config.save(update_fields=["last_tested_at", "last_test_status", "last_test_message", "updated_at"])
            return Response({"success": False, "message": f"Could not send the test email: {error}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        config.last_tested_at = timezone.now()
        config.last_test_status = "success"
        config.last_test_message = f"Test email sent to {recipient.strip()}."
        config.save(update_fields=["last_tested_at", "last_test_status", "last_test_message", "updated_at"])
        return Response({"success": True, "message": "Test email sent."})


class AdminConfigViewSet:
    permission_classes = [IsPlatformAdmin]
    lookup_field = "pk"


class SMSCConfigListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = SMSCConfig.objects.all()
    serializer_class = SMSCConfigSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = SMSCConfigWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()
        item = serializer.save(created_at=now, updated_at=now)
        self._apply_default(item)
        audit(request, "create", item, f"Created SMSC configuration {item.name}.", new_values=snapshot(item))
        return Response(SMSCConfigSerializer(item).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _apply_default(item):
        if item.is_default:
            SMSCConfig.objects.exclude(pk=item.pk).filter(is_default=True).update(is_default=False)


class SMSCConfigDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = SMSCConfig.objects.all()
    serializer_class = SMSCConfigSerializer

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        old_values = snapshot(instance)
        serializer = SMSCConfigWriteSerializer(instance, data=request.data, partial=kwargs.pop("partial", False))
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(updated_at=timezone.now())
        self._apply_default(updated)
        audit(
            request,
            "update",
            updated,
            f"Updated SMSC configuration {updated.name}.",
            old_values=old_values,
            new_values=snapshot(updated),
        )
        return Response(SMSCConfigSerializer(updated).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if SenderSMSCBinding.objects.filter(smsc_id=instance.pk).exists() or ChannelSMSCBinding.objects.filter(smsc_id=instance.pk).exists() or NAddress.objects.filter(smsc_id=instance.pk).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("This SMSC is bound to a sender, channel, or N-address. Remove bindings before deleting it.")
        audit(self.request, "delete", instance, f"Deleted SMSC configuration {instance.name}.")
        instance.delete()


class ConfigCRUDMixin:
    permission_classes = [IsPlatformAdmin]

    @transaction.atomic
    def perform_create(self, serializer):
        now = timezone.now()
        item = serializer.save(created_at=now, updated_at=now)
        self.apply_invariants(item)
        audit(self.request, "create", item, f"Created {item}.", new_values=snapshot(item))

    @transaction.atomic
    def perform_update(self, serializer):
        old_values = snapshot(serializer.instance)
        item = serializer.save(updated_at=timezone.now())
        self.apply_invariants(item)
        audit(
            self.request, "update", item, f"Updated {item}.",
            old_values=old_values, new_values=snapshot(item),
        )

    def apply_invariants(self, item):
        if isinstance(item, SenderID) and item.is_default:
            SenderID.objects.exclude(pk=item.pk).filter(is_default=True).update(is_default=False)
        elif isinstance(item, GlobalTPSConfig):
            if item.is_default:
                GlobalTPSConfig.objects.exclude(pk=item.pk).filter(is_default=True).update(is_default=False)
            if item.is_active:
                GlobalTPSConfig.objects.exclude(pk=item.pk).filter(is_active=True).update(is_active=False)
        elif isinstance(item, NAddressesConfig):
            if item.is_default:
                NAddressesConfig.objects.exclude(pk=item.pk).filter(is_default=True).update(is_default=False)
            if item.is_active:
                NAddressesConfig.objects.exclude(pk=item.pk).filter(is_active=True).update(is_active=False)

    @transaction.atomic
    def perform_destroy(self, instance):
        audit(self.request, "delete", instance, f"Deleted {instance}.")
        instance.delete()


class SenderIDListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = SenderID.objects.all()
    serializer_class = SenderIDSerializer


class SenderIDDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = SenderID.objects.all()
    serializer_class = SenderIDSerializer

    def perform_destroy(self, instance):
        if Campaign.objects.filter(sender_id=instance.sender_id, is_deleted=False, status__in=("active", "in_progress", "paused")).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete a Sender ID used by an active campaign; disable it instead.")
        super().perform_destroy(instance)


class ChannelListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer


class ChannelDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer

    def perform_destroy(self, instance):
        if any(
            str(instance.pk) in {str(channel_id) for channel_id in (campaign.channels_id or [])}
            for campaign in Campaign.objects.filter(is_deleted=False).only("channels_id")
        ):
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Cannot delete a Channel referenced by a campaign; disable it instead.")
        super().perform_destroy(instance)


class GlobalTPSListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = GlobalTPSConfig.objects.all()
    serializer_class = GlobalTPSConfigSerializer


class GlobalTPSDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = GlobalTPSConfig.objects.all()
    serializer_class = GlobalTPSConfigSerializer


class NAddressesConfigListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = NAddressesConfig.objects.all()
    serializer_class = NAddressesConfigSerializer


class NAddressesConfigDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = NAddressesConfig.objects.all()
    serializer_class = NAddressesConfigSerializer


class NAddressListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = NAddress.objects.select_related("smsc", "channel", "sender_id").prefetch_related("assigned_users")
    serializer_class = NAddressSerializer


class NAddressDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = NAddress.objects.all()
    serializer_class = NAddressSerializer


class SenderSMSCBindingDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = SenderSMSCBinding.objects.select_related("sender_id", "smsc")
    serializer_class = SenderSMSCBindingSerializer

    def perform_destroy(self, instance):
        if NAddress.objects.filter(sender_id=instance.sender_id, smsc_id=instance.smsc).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Reassign dependent N-addresses before removing this Sender ID binding.")
        super().perform_destroy(instance)


class SenderSMSCBindingListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = SenderSMSCBinding.objects.select_related("sender_id", "smsc")
    serializer_class = SenderSMSCBindingSerializer


class ChannelSMSCBindingListCreateView(ConfigCRUDMixin, generics.ListCreateAPIView):
    queryset = ChannelSMSCBinding.objects.select_related("channel", "smsc").prefetch_related("allowed_sender_ids")
    serializer_class = ChannelSMSCBindingSerializer


class ChannelSMSCBindingDetailView(ConfigCRUDMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = ChannelSMSCBinding.objects.select_related("channel", "smsc").prefetch_related("allowed_sender_ids")
    serializer_class = ChannelSMSCBindingSerializer

    def perform_destroy(self, instance):
        if ChannelSMSCBinding.objects.filter(channel_id=instance.channel_id).count() <= 1:
            from rest_framework.exceptions import ValidationError
            raise ValidationError("A channel must remain bound to at least one SMSC.")
        if NAddress.objects.filter(channel_id=instance.channel_id, smsc_id=instance.smsc_id).exists():
            from rest_framework.exceptions import ValidationError
            raise ValidationError("Reassign dependent N-addresses before removing this channel binding.")
        super().perform_destroy(instance)


class AssignedConfigurationsView(APIView):
    permission_classes = [IsActivePlatformUser]

    def get(self, request):
        try:
            profile = request.user.admin_profile
        except UserProfile.DoesNotExist:
            return Response({"detail": "User profile is not configured."}, status=status.HTTP_403_FORBIDDEN)
        if profile.role == UserProfile.Role.ADMIN:
            return Response({
                "smsc": SMSCConfigSerializer(SMSCConfig.objects.filter(is_active=True), many=True).data,
                "sender_ids": SenderIDSerializer(SenderID.objects.filter(is_active=True), many=True).data,
                "channels": ChannelSerializer(Channel.objects.filter(is_active=True), many=True).data,
                "tps_configs": GlobalTPSConfigSerializer(GlobalTPSConfig.objects.filter(is_active=True), many=True).data,
                "n_address_configs": NAddressesConfigSerializer(NAddressesConfig.objects.filter(is_active=True), many=True).data,
                "n_addresses": NAddressSerializer(NAddress.objects.filter(is_active=True), many=True, context={"request": request}).data,
                "tps_limit": profile.tps_limit,
            })
        return Response({
            "smsc": _serialize_manager_configs(
                SMSCConfigSerializer, profile.sms_configs.filter(is_active=True)
            ),
            "sender_ids": _serialize_manager_configs(
                SenderIDSerializer, profile.sender_ids.filter(is_active=True)
            ),
            "channels": _serialize_manager_configs(
                ChannelSerializer, profile.channels.filter(is_active=True)
            ),
            "tps_configs": _serialize_manager_configs(
                GlobalTPSConfigSerializer, profile.tps_configs.filter(is_active=True)
            ),
            "n_address_configs": _serialize_manager_configs(
                NAddressesConfigSerializer,
                profile.n_address_configs.filter(is_active=True),
            ),
            "n_addresses": _serialize_manager_configs(
                NAddressSerializer,
                request.user.assigned_n_addresses.filter(is_active=True),
            ),
            "tps_limit": profile.tps_limit,
        })


class AuditLogListView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminAuditLogSerializer
    queryset = AdminAuditLog.objects.select_related("actor")

    def get_queryset(self):
        queryset = super().get_queryset()
        actor = self.request.query_params.get("actor")
        object_type = self.request.query_params.get("object_type")
        since = self.request.query_params.get("from")
        until = self.request.query_params.get("to")
        if actor:
            queryset = queryset.filter(actor_id=actor)
        if object_type:
            queryset = queryset.filter(object_type=object_type)
        if since:
            queryset = queryset.filter(created_at__date__gte=since)
        if until:
            queryset = queryset.filter(created_at__date__lte=until)
        return queryset


class LoginAttemptListView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = LoginAttemptSerializer
    queryset = LoginAttempt.objects.select_related("user")

    def get_queryset(self):
        queryset = super().get_queryset()
        username = self.request.query_params.get("username")
        if username:
            queryset = queryset.filter(Q(username__icontains=username) | Q(user__username__icontains=username))
        return queryset
