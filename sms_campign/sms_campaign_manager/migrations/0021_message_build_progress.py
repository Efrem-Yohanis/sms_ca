from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('sms_campaign_manager', '0020_audience_round_build_contract'),
    ]

    operations = [
        migrations.CreateModel(
            name='MessageBuildJob',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('batch_id', models.CharField(blank=True, default='', max_length=50)),
                ('round_number', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('RUNNING', 'Running'), ('SUCCEEDED', 'Succeeded'), ('FAILED', 'Failed')], db_index=True, default='RUNNING', max_length=20)),
                ('phase', models.CharField(blank=True, default='starting', max_length=30)),
                ('processed_rows', models.PositiveBigIntegerField(default=0)),
                ('total_rows', models.PositiveBigIntegerField(default=0)),
                ('built_rows', models.PositiveBigIntegerField(default=0)),
                ('skipped_rows', models.PositiveBigIntegerField(default=0)),
                ('failed_rows', models.PositiveBigIntegerField(default=0)),
                ('percent', models.FloatField(default=0)),
                ('error_message', models.TextField(blank=True, default='')),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='message_build_jobs', to='sms_campaign_manager.campaign')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='messagebuildjob',
            index=models.Index(fields=['campaign', '-created_at'], name='msgbuild_campaign_ct_idx'),
        ),
        migrations.AddConstraint(
            model_name='messagebuildjob',
            constraint=models.UniqueConstraint(condition=Q(status='RUNNING'), fields=('campaign',), name='unique_running_message_build_per_campaign'),
        ),
    ]