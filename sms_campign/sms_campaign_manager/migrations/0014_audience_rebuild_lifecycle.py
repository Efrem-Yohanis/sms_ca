from django.db import migrations, models
from django.db.models import F


def backfill_rebuilt_at(apps, schema_editor):
    Audience = apps.get_model('sms_campaign_manager', 'Audience')
    Audience.objects.using(schema_editor.connection.alias).filter(
        rebuilt_at__isnull=True,
    ).update(rebuilt_at=F('created_at'))


class Migration(migrations.Migration):

    dependencies = [
        ('sms_campaign_manager', '0013_messageobject_locked_until_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='audience',
            name='round_number',
            field=models.PositiveIntegerField(db_index=True, default=1),
        ),
        migrations.AddField(
            model_name='audience',
            name='rebuilt_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(
            backfill_rebuilt_at,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='audience',
            name='rebuilt_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='round_number',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='total_rows_fetched',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_completed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_status',
            field=models.CharField(choices=[('idle', 'Idle'), ('running', 'Running'), ('success', 'Success'), ('failed', 'Failed')], db_index=True, default='idle', max_length=20),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_error',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_duration_seconds',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='avg_rebuild_duration_seconds',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='rebuild_history_seconds',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='audiencebuildjob',
            name='round_number',
            field=models.PositiveIntegerField(default=1),
        ),
    ]