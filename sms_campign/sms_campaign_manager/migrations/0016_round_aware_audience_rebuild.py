from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('sms_campaign_manager', '0015_audience_build_progress'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='audience',
            name='unique_campaign_msisdn',
        ),
        migrations.AddConstraint(
            model_name='audience',
            constraint=models.UniqueConstraint(
                fields=('campaign', 'msisdn', 'round_number'),
                name='unique_campaign_msisdn',
            ),
        ),
        migrations.AddField(
            model_name='audienceconfig',
            name='last_rebuild_round',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='audience',
            name='language_source',
            field=models.CharField(
                choices=[
                    ('source', 'From Source'),
                    ('mapper', 'From Mapper'),
                    ('default', 'Default Language'),
                ],
                db_index=True,
                default='default',
                max_length=20,
            ),
        ),
    ]
