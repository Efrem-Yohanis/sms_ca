from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sms_campaign_manager', '0014_audience_rebuild_lifecycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_phase',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_processed',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_total',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_percent',
            field=models.FloatField(default=0),
        ),
    ]
