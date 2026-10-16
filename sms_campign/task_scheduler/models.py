import uuid

from django.core.validators import RegexValidator
from django.db import models
from django.conf import settings


def new_schedule_id():
    return uuid.uuid4().hex


class Schedule(models.Model):
    class ScheduleType(models.TextChoices):
        CRON = "Cron", "Cron"
        INTERVAL = "Interval", "Interval"
        MANUAL = "Manual", "Manual"

    class IntervalUnit(models.TextChoices):
        MINUTES = "minutes", "Minutes"
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"

    class TaskType(models.TextChoices):
        PYTHON = "Python", "Python"
        SQL = "SQL", "SQL"

    class Status(models.TextChoices):
        ACTIVE = "Active", "Active"
        PAUSED = "Paused", "Paused"
        FAILED = "Failed", "Failed"
        PENDING = "Pending", "Pending"  # awaiting Airflow sync

    id = models.CharField(
        primary_key=True,
        max_length=80,
        default=new_schedule_id,
        editable=False,
        validators=[
            RegexValidator(
                r"^[a-zA-Z0-9_-]+$",
                "ID may only contain letters, digits, dashes, and underscores.",
            )
        ],
    )
    name = models.CharField(max_length=120, unique=True)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="task_schedules",
    )
    owner = models.CharField(max_length=120)
    owner_email = models.EmailField()
    accept_notifications = models.BooleanField(default=True)

    schedule_type = models.CharField(
        max_length=12, choices=ScheduleType.choices, default=ScheduleType.CRON
    )
    cron = models.CharField(max_length=120, default="0 2 * * *", blank=True)
    interval_value = models.PositiveIntegerField(default=15)
    interval_unit = models.CharField(
        max_length=12, choices=IntervalUnit.choices, default=IntervalUnit.MINUTES
    )
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    days_of_week = models.JSONField(default=list, blank=True)
    window_start = models.TimeField(null=True, blank=True)
    window_end = models.TimeField(null=True, blank=True)
    excluded_dates = models.JSONField(default=list, blank=True)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    task_type = models.CharField(
        max_length=8, choices=TaskType.choices, default=TaskType.PYTHON
    )
    code = models.TextField(blank=True)
    connection = models.CharField(max_length=120, blank=True)

    retries = models.PositiveIntegerField(default=2)
    retry_delay = models.PositiveIntegerField(default=300)

    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING
    )
    last_run = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=32, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)

    airflow_dag_id = models.CharField(max_length=250, unique=True, editable=False, blank=True)

    # Track Airflow sync state so we can retry / show warnings in the UI.
    airflow_synced_at = models.DateTimeField(null=True, blank=True)
    airflow_sync_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["status"], name="task_sched_status_idx"),
            models.Index(fields=["next_run"], name="task_sched_next_run_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.airflow_dag_id:
            # Deterministic, filesystem- and DAG-id-safe.
            safe = "".join(
                ch.lower() if ch.isalnum() else "_" for ch in self.pk
            )
            # Append a short hash so sanitization collisions don't violate unique=True.
            suffix = uuid.uuid5(uuid.NAMESPACE_URL, self.pk).hex[:8]
            self.airflow_dag_id = f"ui_schedule_{safe}_{suffix}"[:250]
        super().save(*args, **kwargs)

    def effective_cron(self):
        return self.cron

    def __str__(self):
        return self.name
