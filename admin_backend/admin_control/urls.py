from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from .views import (
    AdminLoginView,
    AdminEmailConfigView,
    AdminEmailServiceListCreateView,
    AdminEmailServiceDetailView,
    AdminEmailServiceTestView,
    AdminMeView,
    AssignedConfigurationsView,
    AuditLogListView,
    ChannelDetailView,
    ChannelListCreateView,
    ChannelSMSCBindingListCreateView,
    ChannelSMSCBindingDetailView,
    GlobalTPSDetailView,
    GlobalTPSListCreateView,
    LoginAttemptListView,
    InitialPasswordChangeView,
    NAddressDetailView,
    NAddressListCreateView,
    NAddressesConfigDetailView,
    NAddressesConfigListCreateView,
    SMSCConfigDetailView,
    SMSCConfigListCreateView,
    SenderIDDetailView,
    SenderIDListCreateView,
    SenderSMSCBindingListCreateView,
    SenderSMSCBindingDetailView,
    UserDetailView,
    UserCampaignListView,
    UserListCreateView,
    UserPasswordResetView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"status": "ok"})


urlpatterns = [
    path("health/", HealthView.as_view(), name="admin-backend-health"),
    path("admin/auth/login/", AdminLoginView.as_view(), name="admin-api-login"),
    path("admin/auth/initial-password/", InitialPasswordChangeView.as_view(), name="admin-initial-password"),
    path("admin/auth/password-reset/request/", PasswordResetRequestView.as_view(), name="admin-password-reset-request"),
    path("admin/auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="admin-password-reset-confirm"),
    path("admin/email-config/", AdminEmailConfigView.as_view(), name="admin-email-config"),
    path("admin/email-services/", AdminEmailServiceListCreateView.as_view(), name="admin-email-services"),
    path("admin/email-services/<int:pk>/", AdminEmailServiceDetailView.as_view(), name="admin-email-service-detail"),
    path("admin/email-services/<int:pk>/test/", AdminEmailServiceTestView.as_view(), name="admin-email-service-test"),
    path("admin/me/", AdminMeView.as_view(), name="admin-api-me"),
    path("admin/users/", UserListCreateView.as_view(), name="admin-users"),
    path("admin/users/<int:pk>/campaigns/", UserCampaignListView.as_view(), name="admin-user-campaigns"),
    path("admin/users/<int:pk>/", UserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<int:pk>/password-reset/", UserPasswordResetView.as_view(), name="admin-user-password-reset"),
    path("admin/smsc-configs/", SMSCConfigListCreateView.as_view(), name="admin-smsc-configs"),
    path("admin/smsc-configs/<int:pk>/", SMSCConfigDetailView.as_view(), name="admin-smsc-config-detail"),
    path("admin/sender-ids/", SenderIDListCreateView.as_view(), name="admin-sender-ids"),
    path("admin/sender-ids/<int:pk>/", SenderIDDetailView.as_view(), name="admin-sender-id-detail"),
    path("admin/channels/", ChannelListCreateView.as_view(), name="admin-channels"),
    path("admin/channels/<int:pk>/", ChannelDetailView.as_view(), name="admin-channel-detail"),
    path("admin/tps-configs/", GlobalTPSListCreateView.as_view(), name="admin-tps-configs"),
    path("admin/tps-configs/<int:pk>/", GlobalTPSDetailView.as_view(), name="admin-tps-config-detail"),
    path("admin/n-address-configs/", NAddressesConfigListCreateView.as_view(), name="admin-n-address-configs"),
    path("admin/n-address-configs/<int:pk>/", NAddressesConfigDetailView.as_view(), name="admin-n-address-config-detail"),
    path("admin/n-addresses/", NAddressListCreateView.as_view(), name="admin-n-addresses"),
    path("admin/n-addresses/<int:pk>/", NAddressDetailView.as_view(), name="admin-n-address-detail"),
    path("admin/sender-smsc-bindings/", SenderSMSCBindingListCreateView.as_view(), name="admin-sender-smsc-bindings"),
    path("admin/sender-smsc-bindings/<int:pk>/", SenderSMSCBindingDetailView.as_view(), name="admin-sender-smsc-binding-detail"),
    path("admin/channel-smsc-bindings/", ChannelSMSCBindingListCreateView.as_view(), name="admin-channel-smsc-bindings"),
    path("admin/channel-smsc-bindings/<int:pk>/", ChannelSMSCBindingDetailView.as_view(), name="admin-channel-smsc-binding-detail"),
    path("configurations/assigned/", AssignedConfigurationsView.as_view(), name="assigned-configurations"),
    path("admin/audit-log/", AuditLogListView.as_view(), name="admin-audit-log"),
    path("admin/login-attempts/", LoginAttemptListView.as_view(), name="admin-login-attempts"),
]
