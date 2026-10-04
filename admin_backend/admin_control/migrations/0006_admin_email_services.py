from django.db import migrations, models
import django.utils.timezone


def mark_existing_default(apps, schema_editor):
    AdminEmailConfig = apps.get_model("admin_control", "AdminEmailConfig")
    existing = AdminEmailConfig.objects.order_by("id").first()
    if existing:
        AdminEmailConfig.objects.filter(pk=existing.pk).update(is_default=True)


class Migration(migrations.Migration):
    dependencies = [
        ("admin_control", "0005_account_email_and_password_flows"),
    ]

    operations = [
        migrations.AlterField(
            model_name="adminemailconfig",
            name="name",
            field=models.CharField(default="Admin account email", max_length=150, unique=True),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="is_default",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="last_tested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="last_test_status",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="last_test_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="adminemailconfig",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(mark_existing_default, migrations.RunPython.noop),
    ]
