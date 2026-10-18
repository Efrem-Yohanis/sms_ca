from rest_framework.permissions import BasePermission
from django.conf import settings
from django.db.models import Q
import secrets

from .platform_accounts import get_platform_profile
from .models import (
    Audience, AudienceBuildJob, AudienceConfig, Campaign,
    CampaignProgressReport, CustomerProfileConfig, DatabaseConfig,
    DeliveryRecord, EmailConfig, GlobalTPSConfig, MessageContent,
    NAddressesConfig, ReportDeliveryLog, ReportSubscription, Schedule,
    SenderID, SentRecord, SMSCConfig, TestMessage,
)


class IsCampaignManager(BasePermission):
    """Allow only active, unlocked Campaign Manager accounts into this API."""

    message = "Only Campaign Manager accounts can access this application."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or user.is_superuser:
            return False
        profile = get_platform_profile(user.pk)
        if not (profile and profile[0] == "CAMPAIGN_MANAGER" and not profile[1]):
            return False

        # Detail endpoints must resolve only objects owned by the signed-in
        # campaign manager, even when a view uses a hand-written APIView.
        parts = [part for part in request.path_info.strip("/").split("/") if part]
        if len(parts) < 3 or parts[0] != "api" or parts[1] != "v1":
            return True
        resource = parts[2]
        key = parts[3] if len(parts) > 3 else ""
        if resource == "databases" and len(parts) > 4 and parts[3] == "customer-profiles":
            key = parts[4]
            if key.isdigit():
                return CustomerProfileConfig.objects.filter(
                    pk=int(key), created_by=user,
                ).exists()
        if not key.isdigit():
            return True
        object_id = int(key)
        owned = {
            "campaigns": Campaign.objects.filter(pk=object_id, created_by=user, is_deleted=False),
            "schedules": Schedule.objects.filter(pk=object_id, campaign__created_by=user),
            "audiences": Audience.objects.filter(pk=object_id, campaign__created_by=user),
            "audience-configs": AudienceConfig.objects.filter(pk=object_id, campaign__created_by=user),
            "audience-build-jobs": AudienceBuildJob.objects.filter(pk=object_id, audience_config__campaign__created_by=user),
            "message-content": MessageContent.objects.filter(pk=object_id, campaign__created_by=user),
            "test-sms": TestMessage.objects.filter(pk=object_id, created_by=user),
            "sender-ids": SenderID.objects.filter(pk=object_id, created_by=user),
            "smsc-configs": SMSCConfig.objects.filter(pk=object_id, created_by=user),
            "global-tps-config": GlobalTPSConfig.objects.filter(pk=object_id, created_by=user),
            "n-addresses-config": NAddressesConfig.objects.filter(pk=object_id, created_by=user),
            "email-config": EmailConfig.objects.filter(pk=object_id, created_by=user),
            "email-reports": CampaignProgressReport.objects.filter(pk=object_id, created_by=user),
            "report-subscriptions": ReportSubscription.objects.filter(pk=object_id, created_by=user),
            "databases": DatabaseConfig.objects.filter(pk=object_id, created_by=user),
        }.get(resource)
        if owned is not None:
            return owned.exists()
        if resource == "report-delivery-logs":
            return ReportDeliveryLog.objects.filter(pk=object_id).filter(
                Q(campaign__created_by=user) | Q(subscription__created_by=user),
            ).exists()
        if resource == "sent-records":
            return SentRecord.objects.filter(pk=object_id, campaign__created_by=user).exists()
        if resource == "delivery-records":
            return DeliveryRecord.objects.filter(pk=object_id, campaign__created_by=user).exists()
        return True


def has_valid_internal_service_token(request):
    configured = getattr(settings, "INTERNAL_SERVICE_API_TOKEN", "")
    supplied = request.headers.get("X-Internal-Service-Token", "")
    return bool(configured and secrets.compare_digest(supplied, configured))


class IsCampaignManagerOrInternalService(IsCampaignManager):
    """Permission for the small set of routes called by Airflow and sender."""

    def has_permission(self, request, view):
        if has_valid_internal_service_token(request):
            return True
        return super().has_permission(request, view)
