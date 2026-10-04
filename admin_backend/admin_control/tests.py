from django.utils import timezone
from django.contrib.auth.models import User
from django.db import connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from unittest.mock import patch

from .models import (
    Campaign,
    Channel,
    GlobalTPSConfig,
    AdminEmailConfig,
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
        self.email_sender = patch("admin_control.views.send_admin_email")
        self.email_sender.start()
        self.addCleanup(self.email_sender.stop)
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
        self.assertTrue(User.objects.get(username="new-manager").admin_profile.require_password_change)
        self.assertEqual(response.data["assigned_config_counts"]["channels"], 0)
        self.email_sender.assert_called_once()
        self.assertEqual(self.email_sender.call_args.args[0], "new-manager@example.test")
        self.assertIn("http://localhost:3000/login", self.email_sender.call_args.args[2])
        self.assertIn('href="http://localhost:3000/login"', self.email_sender.call_args.args[3])
        self.assertIn("Temporary password:", self.email_sender.call_args.args[3])

        self.client.force_authenticate(self.manager)
        denied = self.client.get("/api/v1/admin/users/")
        self.assertEqual(denied.status_code, 403)

    def test_new_admin_must_change_temporary_password_before_getting_tokens(self):
        self.client.force_authenticate(self.admin)
        created = self.client.post(
            "/api/v1/admin/users/",
            {
                "username": "new-platform-admin",
                "email": "new-platform-admin@example.test",
                "password": "Temp-admin-2891!",
                "department": "IT",
                "role": UserProfile.Role.ADMIN,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.data)

        login = self.client.post(
            "/api/v1/admin/auth/login/",
            {"username": "new-platform-admin", "password": "Temp-admin-2891!"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.data, {"must_change_password": True})

        changed = self.client.post(
            "/api/v1/admin/auth/initial-password/",
            {
                "username": "new-platform-admin",
                "current_password": "Temp-admin-2891!",
                "new_password": "Changed-admin-5781!",
            },
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertFalse(
            User.objects.get(username="new-platform-admin").admin_profile.require_password_change
        )

        login = self.client.post(
            "/api/v1/admin/auth/login/",
            {"username": "new-platform-admin", "password": "Changed-admin-5781!"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertIn("access", login.data)

    def test_password_reset_pin_is_emailed_and_can_reset_a_manager_password(self):
        requested = self.client.post(
            "/api/v1/admin/auth/password-reset/request/",
            {"email": self.manager.email},
        )
        self.assertEqual(requested.status_code, 200)
        self.assertEqual(self.email_sender.call_args.args[0], self.manager.email)
        pin = self.email_sender.call_args.args[2].split(" is ")[1].split(".")[0]
        self.assertIn(pin, self.email_sender.call_args.args[3])
        self.assertIn('href="http://localhost:3000/login"', self.email_sender.call_args.args[3])

        confirmed = self.client.post(
            "/api/v1/admin/auth/password-reset/confirm/",
            {
                "email": self.manager.email,
                "pin": pin,
                "new_password": "Manager-reset-4912!",
            },
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertTrue(User.objects.get(pk=self.manager.pk).check_password("Manager-reset-4912!"))

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

    def test_admin_can_view_campaigns_created_by_user(self):
        now = timezone.now()
        channel = Channel.objects.create(
            code="campaigns", name="Campaign SMS", is_active=True,
            created_at=now, updated_at=now,
        )
        user_campaign = Campaign.objects.create(
            name="Manager campaign",
            sender_id="TESTSENDER",
            owner_emails=["owner@example.test"],
            channels_id=[channel.pk],
            status="draft",
            is_ready_to_execute=False,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            created_by=self.manager,
        )
        Campaign.objects.create(
            name="Admin campaign",
            sender_id="TESTSENDER",
            owner_emails=[],
            channels_id=[],
            status="active",
            is_ready_to_execute=True,
            is_deleted=False,
            created_at=now,
            updated_at=now,
            created_by=self.admin,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f"/api/v1/admin/users/{self.manager.admin_profile.pk}/campaigns/"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [campaign["id"] for campaign in response.data], [user_campaign.pk]
        )
        self.assertEqual(response.data[0]["name"], "Manager campaign")
        self.assertEqual(response.data[0]["sender_id"], "TESTSENDER")
        self.assertEqual(response.data[0]["channel_names"], ["Campaign SMS"])

        self.client.force_authenticate(self.manager)
        denied = self.client.get(
            f"/api/v1/admin/users/{self.manager.admin_profile.pk}/campaigns/"
        )
        self.assertEqual(denied.status_code, 403)

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

    def test_admin_email_services_support_default_and_test_delivery(self):
        self.client.force_authenticate(self.admin)
        first = self.client.post(
            "/api/v1/admin/email-services/",
            {
                "name": "Primary account mail",
                "host": "smtp.primary.example.test",
                "port": 587,
                "username": "admin-mail",
                "default_from_email": "accounts@example.test",
                "use_tls": True,
                "use_ssl": False,
                "is_active": True,
                "is_default": False,
            },
            format="json",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["is_default"])
        first_config = AdminEmailConfig.objects.get(pk=first.data["id"])

        backup = self.client.post(
            "/api/v1/admin/email-services/",
            {
                "name": "Backup account mail",
                "host": "smtp.backup.example.test",
                "port": 465,
                "default_from_email": "backup@example.test",
                "use_tls": False,
                "use_ssl": True,
                "is_active": True,
                "is_default": False,
            },
            format="json",
        )
        self.assertEqual(backup.status_code, 201, backup.data)
        self.assertFalse(backup.data["is_default"])

        changed = self.client.patch(
            f"/api/v1/admin/email-services/{backup.data['id']}/",
            {"is_default": True},
            format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.data)
        first_config.refresh_from_db()
        self.assertFalse(first_config.is_default)

        tested = self.client.post(
            f"/api/v1/admin/email-services/{backup.data['id']}/test/",
            {"test_email": "test-recipient@example.test"},
            format="json",
        )
        self.assertEqual(tested.status_code, 200, tested.data)
        self.email_sender.assert_called_once()
        self.assertEqual(
            self.email_sender.call_args.kwargs["config"].pk,
            backup.data["id"],
        )

        disabled = self.client.patch(
            f"/api/v1/admin/email-services/{backup.data['id']}/",
            {"is_active": False, "is_default": False},
            format="json",
        )
        self.assertEqual(disabled.status_code, 200, disabled.data)
        first_config.refresh_from_db()
        self.assertTrue(first_config.is_default)
