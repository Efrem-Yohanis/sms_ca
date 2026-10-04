from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("admin_control", "0006_admin_email_services"),
    ]

    operations = [
        migrations.RenameField(
            model_name="passwordresetchallenge",
            old_name="pin_hash",
            new_name="token_hash",
        ),
    ]
