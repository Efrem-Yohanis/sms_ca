from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('sms_campaign_manager', '0029_schedule_ethiopian_timezone')]

    operations = [
        migrations.AddField(
            model_name='audienceconfig',
            name='source_sql',
            field=models.TextField(blank=True, default='', help_text='Read-only SELECT query for SQL audience source'),
        ),
        migrations.AlterField(
            model_name='audienceconfig',
            name='source_type',
            field=models.CharField(choices=[('manual', 'Manual Entry'), ('file_import', 'File Import'), ('database', 'Database Source'), ('sql', 'SQL Query')], db_index=True, default='manual', max_length=20),
        ),
    ]
