from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sms_campaign_manager', '0018_emailconfig_last_test_message_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportdeliverylog',
            name='email_config',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='report_delivery_logs',
                to='sms_campaign_manager.emailconfig',
            ),
        ),
    ]
