import sms_campaign_manager.fields
import django.conf
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("sms_campaign_manager", "0029_schedule_ethiopian_timezone"),
    ]

    operations = [
        migrations.CreateModel(
            name="AudioCallConfig",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=150, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("base_url", models.URLField(max_length=500)),
                ("call_endpoint", models.CharField(default="/api/call", max_length=255)),
                ("http_method", models.CharField(choices=[("GET", "GET"), ("POST", "POST"), ("PUT", "PUT")], default="POST", max_length=10)),
                ("auth_type", models.CharField(choices=[("none", "None"), ("api_key", "API Key"), ("bearer", "Bearer"), ("basic", "Basic Auth")], default="api_key", max_length=20)),
                ("api_key", sms_campaign_manager.fields.EncryptedCharField(blank=True, default="", max_length=500)),
                ("api_secret", sms_campaign_manager.fields.EncryptedCharField(blank=True, default="", max_length=500)),
                ("username", models.CharField(blank=True, default="", max_length=255)),
                ("password", sms_campaign_manager.fields.EncryptedCharField(blank=True, default="", max_length=500)),
                ("calling_number", models.CharField(max_length=30)),
                ("request_field_mapping", models.JSONField(default=dict, help_text="Maps msisdn, audio_recording, calling_number, language, and call_id to provider field names.")),
                ("extra_headers", models.JSONField(blank=True, default=dict)),
                ("extra_params", models.JSONField(blank=True, default=dict)),
                ("rate_limit_per_second", models.PositiveIntegerField(default=10)),
                ("rate_limit_per_minute", models.PositiveIntegerField(default=600)),
                ("max_retries", models.PositiveSmallIntegerField(default=3)),
                ("retry_backoff_seconds", models.PositiveIntegerField(default=5)),
                ("request_timeout_seconds", models.PositiveIntegerField(default=30)),
                ("connect_timeout_seconds", models.PositiveIntegerField(default=10)),
                ("is_default", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_test_status", models.CharField(blank=True, default="", max_length=20)),
                ("last_test_message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_audio_call_configs", to=django.conf.settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-is_default", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="audiocallconfig",
            index=models.Index(fields=["is_active"], name="sms_campaign_audio_active_idx"),
        ),
        migrations.AddIndex(
            model_name="audiocallconfig",
            index=models.Index(fields=["is_default"], name="sms_campaign_audio_default_idx"),
        ),
    ]
