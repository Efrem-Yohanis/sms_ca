from django.db import migrations, models
from django.db.models import Q


def fail_duplicate_active_builds(apps, schema_editor):
    from datetime import datetime, timezone
    from django.db.models import Count

    BuildJob = apps.get_model('sms_campaign_manager', 'AudienceBuildJob')
    database = schema_editor.connection.alias
    duplicated_configs = BuildJob.objects.using(database).filter(
        status__in=['PENDING', 'RUNNING'],
    ).values('audience_config_id').annotate(job_count=Count('id')).filter(job_count__gt=1)
    completed_at = datetime.now(timezone.utc)

    for item in duplicated_configs:
        active_ids = list(BuildJob.objects.using(database).filter(
            audience_config_id=item['audience_config_id'],
            status__in=['PENDING', 'RUNNING'],
        ).order_by('created_at', 'id').values_list('id', flat=True))
        BuildJob.objects.using(database).filter(pk__in=active_ids[1:]).update(
            status='FAILED',
            error_message='Superseded while enforcing one active build per configuration.',
            completed_at=completed_at,
            heartbeat_at=completed_at,
        )


class Migration(migrations.Migration):
    dependencies = [
        ('sms_campaign_manager', '0019_reportdeliverylog_email_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='audience',
            name='build_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=64),
        ),
        migrations.AddIndex(
            model_name='audience',
            index=models.Index(fields=['campaign', 'round_number'], name='audience_campaign_round_idx'),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='rebuild_on_each_round',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='is_round_active',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_build_id',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='audienceconfig',
            name='round_number',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RunPython(fail_duplicate_active_builds, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='audiencebuildjob',
            constraint=models.UniqueConstraint(
                condition=Q(status__in=['PENDING', 'RUNNING']),
                fields=('audience_config',),
                name='unique_active_audience_build_per_config',
            ),
        ),
    ]