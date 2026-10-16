from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Schedule",
            fields=[
                ("id", models.CharField(max_length=80, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("owner", models.CharField(max_length=120)),
                ("owner_email", models.EmailField(max_length=254)),
                ("accept_notifications", models.BooleanField(default=True)),
                ("schedule_type", models.CharField(choices=[("Cron", "Cron"), ("Interval", "Interval"), ("Manual", "Manual")], default="Cron", max_length=12)),
                ("cron", models.CharField(default="0 2 * * *", max_length=120)),
                ("interval_value", models.PositiveIntegerField(default=15)),
                ("interval_unit", models.CharField(choices=[("minutes", "Minutes"), ("hours", "Hours")], default="minutes", max_length=12)),
                ("timezone", models.CharField(default="Africa/Nairobi", max_length=64)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("task_type", models.CharField(choices=[("Python", "Python"), ("SQL", "SQL")], default="Python", max_length=8)),
                ("code", models.TextField(blank=True)),
                ("connection", models.CharField(blank=True, max_length=120)),
                ("retries", models.PositiveIntegerField(default=2)),
                ("retry_delay", models.PositiveIntegerField(default=300)),
                ("status", models.CharField(choices=[("Active", "Active"), ("Paused", "Paused"), ("Failed", "Failed")], default="Active", max_length=8)),
                ("last_run", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(blank=True, max_length=16)),
                ("next_run", models.DateTimeField(blank=True, null=True)),
                ("airflow_dag_id", models.CharField(editable=False, max_length=250, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
