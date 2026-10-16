from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from rest_framework import serializers

from .models import Schedule


class ScheduleSerializer(serializers.ModelSerializer):
    # --- camelCase API surface ---------------------------------------------
    ownerEmail = serializers.EmailField(source="owner_email")
    acceptNotifications = serializers.BooleanField(
        source="accept_notifications", required=False
    )
    scheduleType = serializers.ChoiceField(
        source="schedule_type", choices=Schedule.ScheduleType.choices
    )
    intervalValue = serializers.IntegerField(
        source="interval_value", min_value=1, required=False
    )
    intervalUnit = serializers.ChoiceField(
        source="interval_unit", choices=Schedule.IntervalUnit.choices, required=False
    )
    daysOfWeek = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        source="days_of_week",
        required=False,
        allow_empty=True,
    )
    windowStart = serializers.TimeField(
        source="window_start", allow_null=True, required=False
    )
    windowEnd = serializers.TimeField(
        source="window_end", allow_null=True, required=False
    )
    excludedDates = serializers.ListField(
        child=serializers.DateField(),
        source="excluded_dates",
        required=False,
        allow_empty=True,
    )
    startDate = serializers.DateField(
        source="start_date", allow_null=True, required=False
    )
    endDate = serializers.DateField(
        source="end_date", allow_null=True, required=False
    )
    type = serializers.ChoiceField(source="task_type", choices=Schedule.TaskType.choices)
    retryDelay = serializers.IntegerField(
        source="retry_delay", min_value=0, required=False
    )
    lastRun = serializers.SerializerMethodField()
    lastStatus = serializers.CharField(source="last_status", read_only=True)
    nextRun = serializers.SerializerMethodField()
    effectiveCron = serializers.SerializerMethodField()
    airflowSyncedAt = serializers.DateTimeField(
        source="airflow_synced_at", read_only=True
    )
    airflowSyncError = serializers.CharField(
        source="airflow_sync_error", read_only=True
    )
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "name",
            "owner",
            "ownerEmail",
            "acceptNotifications",
            "scheduleType",
            "cron",
            "intervalValue",
            "intervalUnit",
            "timezone",
            "daysOfWeek",
            "windowStart",
            "windowEnd",
            "excludedDates",
            "startDate",
            "endDate",
            "type",
            "code",
            "connection",
            "retries",
            "retryDelay",
            "status",
            "lastRun",
            "lastStatus",
            "nextRun",
            "effectiveCron",
            "airflowSyncedAt",
            "airflowSyncError",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["status"]

    # --- representation helpers -------------------------------------------
    def get_lastRun(self, schedule):
        return (
            int(schedule.last_run.timestamp() * 1000) if schedule.last_run else None
        )

    def get_nextRun(self, schedule):
        return (
            int(schedule.next_run.timestamp() * 1000) if schedule.next_run else None
        )

    def get_effectiveCron(self, schedule):
        return schedule.effective_cron()

    # --- field-level validation -------------------------------------------
    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise serializers.ValidationError(f"Unknown timezone: {value}")
        return value

    def validate_daysOfWeek(self, value):
        return sorted(set(value))

    def validate_excludedDates(self, value):
        return sorted({day.isoformat() for day in value})

    # --- object-level validation ------------------------------------------
    def _current(self, attrs, field, default=None):
        """Return attrs value if present, else instance value, else default."""
        if field in attrs:
            return attrs[field]
        if self.instance is not None:
            return getattr(self.instance, field, default)
        return default

    def validate(self, attrs):
        schedule_type = self._current(
            attrs, "schedule_type", Schedule.ScheduleType.CRON
        )
        task_type = self._current(attrs, "task_type", Schedule.TaskType.PYTHON)
        code = (self._current(attrs, "code", "") or "").strip()
        connection = (self._current(attrs, "connection", "") or "").strip()
        cron = (self._current(attrs, "cron", "") or "").strip()
        days = self._current(attrs, "days_of_week", []) or []
        window_start = self._current(attrs, "window_start")
        window_end = self._current(attrs, "window_end")

        # task_type dependent rules
        if not code:
            raise serializers.ValidationError(
                {"code": "Script code is required."}
            )
        if task_type == Schedule.TaskType.SQL and not connection:
            raise serializers.ValidationError(
                {"connection": "Select an Airflow connection for SQL tasks."}
            )

        # schedule_type dependent rules
        if schedule_type == Schedule.ScheduleType.CRON:
            if not cron:
                raise serializers.ValidationError(
                    {"cron": "Cron expression is required for cron schedules."}
                )
            if len(cron.split()) != 5 or not croniter.is_valid(cron):
                raise serializers.ValidationError(
                    {"cron": f"Expected a valid five-field cron expression, got {cron!r}."}
                )
        elif schedule_type == Schedule.ScheduleType.INTERVAL:
            if not self._current(attrs, "interval_value"):
                raise serializers.ValidationError(
                    {"intervalValue": "Interval value is required."}
                )
        if schedule_type != Schedule.ScheduleType.CRON and (
            days or window_start is not None or window_end is not None
        ):
            raise serializers.ValidationError(
                {
                    "daysOfWeek": (
                        "Weekday and time-window filters are only supported for Cron schedules."
                    )
                }
            )

        if (window_start is None) != (window_end is None):
            raise serializers.ValidationError(
                {
                    "windowStart": (
                        "Provide both windowStart and windowEnd, or neither."
                    )
                }
            )
        if window_start is not None and window_end is not None and window_end <= window_start:
            raise serializers.ValidationError(
                {"windowEnd": "windowEnd must be later than windowStart."}
            )

        # date sanity
        start = self._current(attrs, "start_date")
        end = self._current(attrs, "end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"endDate": "End date must be on or after the start date."}
            )

        return attrs


class ScheduleWriteResponseSerializer(ScheduleSerializer):
    """Optional: use for write responses if you want to hide certain fields."""

    pass