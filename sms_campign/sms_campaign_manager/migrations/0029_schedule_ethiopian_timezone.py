from django.db import migrations, models


def use_ethiopian_timezone(apps, schema_editor):
    Schedule = apps.get_model('sms_campaign_manager', 'Schedule')
    Schedule.objects.using(schema_editor.connection.alias).update(timezone='Africa/Addis_Ababa')


class Migration(migrations.Migration):

    dependencies = [
        ('sms_campaign_manager', '0028_seed_default_sender_configs'),
    ]

    operations = [
        migrations.RunPython(use_ethiopian_timezone, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='schedule',
            name='timezone',
            field=models.CharField(default='Africa/Addis_Ababa', max_length=50),
        ),
    ]
