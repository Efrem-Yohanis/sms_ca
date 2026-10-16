from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("task_scheduler", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="schedule",
            name="airflow_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="schedule",
            name="airflow_sync_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="schedule",
            name="days_of_week",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="schedule",
            name="window_start",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="schedule",
            name="window_end",
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="schedule",
            name="excluded_dates",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
