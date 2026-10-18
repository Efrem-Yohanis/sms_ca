from django.db import migrations, models


def set_addis_ababa_timezone(apps, schema_editor):
    Schedule = apps.get_model("task_scheduler", "Schedule")
    Schedule.objects.exclude(timezone="Africa/Addis_Ababa").update(
        timezone="Africa/Addis_Ababa"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("task_scheduler", "0004_schedule_owner_user"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schedule",
            name="timezone",
            field=models.CharField(default="Africa/Addis_Ababa", max_length=64),
        ),
        migrations.RunPython(set_addis_ababa_timezone, migrations.RunPython.noop),
    ]
