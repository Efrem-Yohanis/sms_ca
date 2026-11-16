import admin_control.crypto
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_control", "0007_password_reset_token_hash"),
    ]

    operations = [
        migrations.CreateModel(
            name="AudioCallConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("base_url", models.URLField(max_length=500)),
                ("call_endpoint", models.CharField(default="/api/call", max_length=255)),
                ("http_method", models.CharField(default="POST", max_length=10)),
                ("auth_type", models.CharField(default="api_key", max_length=20)),
                ("api_key", admin_control.crypto.SharedEncryptedCharField(blank=True, default="", max_length=500)),
                ("api_secret", admin_control.crypto.SharedEncryptedCharField(blank=True, default="", max_length=500)),
                ("username", models.CharField(blank=True, default="", max_length=255)),
                ("password", admin_control.crypto.SharedEncryptedCharField(blank=True, default="", max_length=500)),
                ("calling_number", models.CharField(max_length=30)),
                ("request_field_mapping", models.JSONField(default=dict)),
                ("extra_headers", models.JSONField(blank=True, default=dict)),
                ("extra_params", models.JSONField(blank=True, default=dict)),
                ("rate_limit_per_second", models.PositiveIntegerField(default=10)),
                ("rate_limit_per_minute", models.PositiveIntegerField(default=600)),
                ("max_retries", models.PositiveSmallIntegerField(default=3)),
                ("retry_backoff_seconds", models.PositiveIntegerField(default=5)),
                ("request_timeout_seconds", models.PositiveIntegerField(default=30)),
                ("connect_timeout_seconds", models.PositiveIntegerField(default=10)),
                ("is_default", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_test_status", models.CharField(blank=True, default="", max_length=20)),
                ("last_test_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField()),
                ("updated_at", models.DateTimeField()),
            ],
            options={
                "db_table": "sms_campaign_manager_audiocallconfig",
                "abstract": False,
                "managed": False,
            },
        ),
        migrations.AddField(
            model_name="userprofile",
            name="audio_call_configs",
            field=models.ManyToManyField(blank=True, related_name="assigned_profiles", to="admin_control.audiocallconfig"),
        ),
    ]
