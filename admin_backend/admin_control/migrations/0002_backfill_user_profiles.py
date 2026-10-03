from django.conf import settings
from django.db import migrations


def create_profiles_for_existing_users(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserProfile = apps.get_model("admin_control", "UserProfile")
    for user in User.objects.all().iterator():
        UserProfile.objects.get_or_create(
            user_id=user.pk,
            defaults={
                "role": "ADMIN" if user.is_staff or user.is_superuser else "CAMPAIGN_MANAGER",
                "department": "Unassigned",
                "is_locked": False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("admin_control", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_profiles_for_existing_users, migrations.RunPython.noop),
    ]
