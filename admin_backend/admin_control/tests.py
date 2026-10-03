from django.utils import timezone
from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import (
    Campaign,
    Channel,
    GlobalTPSConfig,
    NAddress,
    NAddressesConfig,
    SenderID,
    SMSCConfig,
    UserProfile,
)


class AdminBackendApiTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.created_shared_tables = []
        with connection.schema_editor() as editor:
            for model in (
                SMSCConfig, SenderID, Channel, GlobalTPSConfig, NAddressesConfig, Campaign
            ):
                editor.create_model(model)
                cls.created_shared_tables.append(model)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            for model in reversed(cls.created_shared_tables):
                editor.delete_model(model)
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="platform-admin",
            email="platform-admin@example.test",
            password="Strong-pass-934!",
            is_staff=True,
        )
        self.admin.admin_profile.role = UserProfile.Role.ADMIN
        self.admin.admin_profile.department = "IT"
        self.admin.admin_profile.save()
        self.manager = User.objects.create_user(
            username="campaign-manager",
            email="manager@example.test",
            password="Strong-pass-934!",
        )
        self.manager.admin_profile.department = "Marketing"
        self.manager.admin_profile.save()

    def test_login_issues_tokens_only_for_admins_and_records_attempt(self):
        response = self.client.post(
            "/api/v1/admin/auth/login/",
            {"username": self.admin.email, "password": "Strong-pass-934!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

        denied = self.client.post(
            "/api/v1/admin/auth/login/",
            {"username": self.manager.username, "password": "Strong-pass-934!"},
        )
        self.assertEqual(denied.status_code, 400)
        from .models import LoginAttempt
        self.assertEqual(LoginAttempt.objects.count(), 2)
        self.assertEqual(LoginAttempt.objects.filter(succeeded=True).count(), 1)

    def test_admin_can_create_manager_but_manager_cannot_manage_users(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/admin/users/",
            {
                "username": "new-manager",
                "email": "new-manager@example.test",
                "password": "S7!qM4#vP9@kD2",
                "department": "Sales",
                "role": UserProfile.Role.CAMPAIGN_MANAGER,
                "assigned_n_addresses": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(User.objects.get(username="new-manager").is_staff)
        self.assertEqual(response.data["assigned_config_counts"]["channels"], 0)

        self.client.force_authenticate(self.manager)
        denied = self.client.get("/api/v1/admin/users/")
        self.assertEqual(denied.status_code, 403)

    def test_user_creation_rejects_duplicate_identity_and_weak_password(self):
        self.client.force_authenticate(self.admin)
        payload = {
            "username": "new-user",
            "email": self.manager.email,
            "password": "S7!qM4#vP9@kD2",
            "department": "Sales",
            "role": UserProfile.Role.CAMPAIGN_MANAGER,
        }
        duplicate_email = self.client.post(
            "/api/v1/admin/users/", payload, format="json"
        )
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertIn("email", duplicate_email.data)

        payload["email"] = "new-user@example.test"
        payload["password"] = "new-user"
        weak_password = self.client.post(
            "/api/v1/admin/users/", payload, format="json"
        )
        self.assertEqual(weak_password.status_code, 400)
        self.assertIn("password", weak_password.data)

    def test_admin_cannot_demote_themselves(self):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/admin/users/{self.admin.admin_profile.pk}/",
            {"role": UserProfile.Role.CAMPAIGN_MANAGER},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_configuration_assignments_are_exposed_for_manager(self):
        now = timezone.now()
        channel = Channel.objects.create(
            code="sms", name="SMS", is_active=True, created_at=now, updated_at=now
        )
        sender_id = SenderID.objects.create(
            sender_id="TESTSMS",
            name="Test sender",
            description="",
            is_default=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.manager.admin_profile.channels.add(channel)
        self.manager.admin_profile.sender_ids.add(sender_id)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/v1/configurations/assigned/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["channels"]], [channel.pk])
        self.assertEqual([row["id"] for row in response.data["sender_ids"]], [sender_id.pk])
        self.assertNotIn("assigned_user_ids", response.data["channels"][0])
        self.assertNotIn("assigned_user_ids", response.data["sender_ids"][0])

    def test_admin_created_manager_can_login_and_only_sees_assigned_config(self):
        now = timezone.now()
        assigned_channel = Channel.objects.create(
            code="assigned", name="Assigned", is_active=True, created_at=now, updated_at=now
        )
        unassigned_channel = Channel.objects.create(
            code="private", name="Unassigned", is_active=True, created_at=now, updated_at=now
        )
        sender_id = SenderID.objects.create(
            sender_id="E2ETEST",
            name="E2E sender",
            description="",
            is_default=False,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/v1/admin/users/",
            {
                "username": "e2e-manager",
                "email": "e2e-manager@example.test",
                "password": "S7!qM4#vP9@kD2",
                "department": "Operations",
                "role": UserProfile.Role.CAMPAIGN_MANAGER,
                "assigned_channels": [assigned_channel.pk],
                "assigned_sender_ids": [sender_id.pk],
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        login = TokenObtainPairSerializer(
            data={"username": "e2e-manager", "password": "S7!qM4#vP9@kD2"}
        )
        self.assertTrue(login.is_valid(), login.errors)

        campaign_client = APIClient()
        campaign_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {login.validated_data['access']}"
        )
        assigned = campaign_client.get("/api/v1/configurations/assigned/")
        self.assertEqual(assigned.status_code, 200, assigned.data)
        self.assertEqual(
            [row["id"] for row in assigned.data["channels"]], [assigned_channel.pk]
        )
        self.assertNotIn(
            unassigned_channel.pk, [row["id"] for row in assigned.data["channels"]]
        )
        self.assertEqual([row["id"] for row in assigned.data["sender_ids"]], [sender_id.pk])

        admin_only = campaign_client.get("/api/v1/admin/users/")
        self.assertEqual(admin_only.status_code, 403)

    def test_admin_can_assign_n_addresses_from_user_profile(self):
        now = timezone.now()
        smsc = SMSCConfig.objects.create(
            name="Address SMSC",
            base_url="https://smsc.example.test",
            created_at=now,
            updated_at=now,
        )
        address = NAddress.objects.create(
            value="+12025550123",
            address_type=NAddress.AddressType.MSISDN,
            smsc=smsc,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f"/api/v1/admin/users/{self.manager.admin_profile.pk}/",
            {"assigned_n_addresses": [address.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["assigned_n_addresses"], [address.pk])

        self.client.force_authenticate(self.manager)
        assigned = self.client.get("/api/v1/configurations/assigned/")
        self.assertEqual(assigned.status_code, 200)
        self.assertEqual([item["id"] for item in assigned.data["n_addresses"]], [address.pk])

    def test_channel_creation_requires_and_saves_smsc_binding(self):
        now = timezone.now()
        smsc = SMSCConfig.objects.create(
            name="Channel SMSC",
            base_url="https://smsc.example.test",
            created_at=now,
            updated_at=now,
        )
        self.client.force_authenticate(self.admin)
        sender_response = self.client.post(
            "/api/v1/admin/sender-ids/",
            {
                "sender_id": "CHANNELTEST",
                "name": "Channel Test Sender",
                "sender_type": "ALPHANUMERIC",
                "country": "ET",
                "tps_limit": 100,
                "smsc_ids": [smsc.pk],
                "assigned_user_ids": [self.manager.pk],
            },
            format="json",
        )
        self.assertEqual(sender_response.status_code, 201, sender_response.data)
        self.assertEqual(sender_response.data["bound_smsc_ids"], [smsc.pk])
        self.assertEqual(sender_response.data["assigned_user_ids"], [self.manager.pk])
        self.assertEqual(sender_response.data["sender_type"], "ALPHANUMERIC")
        self.assertEqual(sender_response.data["tps_limit"], 100)

        payload = {"code": "transactional", "name": "Transactional"}
        missing_binding = self.client.post(
            "/api/v1/admin/channels/", payload, format="json"
        )
        self.assertEqual(missing_binding.status_code, 400)

        payload["smsc_bindings"] = [
            {"smsc": smsc.pk, "allowed_sender_ids": [sender_response.data["id"]]}
        ]
        response = self.client.post(
            "/api/v1/admin/channels/", payload, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["bound_smsc_bindings"]), 1)

    def test_admin_audit_log_redacts_smsc_credentials(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/v1/admin/smsc-configs/",
            {
                "name": "Test SMSC",
                "base_url": "https://smsc.example.test",
                "send_endpoint": "/send",
                "http_method": "POST",
                "auth_type": "none",
                "api_key": "must-not-be-logged",
                "rate_limit_per_second": 30,
                "rate_limit_per_minute": 1800,
                "max_retries": 3,
                "retry_backoff_seconds": 5,
                "max_addresses_per_request": 100,
                "request_timeout_seconds": 30,
                "connect_timeout_seconds": 10,
                "is_default": False,
                "is_active": True,
                "extra_headers": {},
                "extra_params": {},
                "assigned_user_ids": [self.manager.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["assigned_user_ids"], [self.manager.pk])
        from .models import AdminAuditLog
        event = AdminAuditLog.objects.get(action="create", object_type="admin_control.SMSCConfig")
        self.assertEqual(event.new_values["api_key"], "[redacted]")
        self.assertNotIn("api_key", response.data)
