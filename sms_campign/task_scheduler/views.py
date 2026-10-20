import logging
import secrets
from datetime import datetime, timezone as datetime_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from . import airflow
from .airflow import AirflowError
from .models import Schedule
from .notifications import NotificationDeliveryError, send_schedule_notification
from .serializers import ScheduleSerializer
from sms_campaign_manager.permissions import IsCampaignManager

logger = logging.getLogger(__name__)


def visible_schedules(request):
    queryset = Schedule.objects.all()
    if request.user.is_superuser:
        return queryset
    user_email = (request.user.email or "").strip()
    owned = Q(owner_user=request.user)
    if user_email:
        # Claim legacy schedules only when their saved owner email matches the
        # authenticated account; new schedules are always linked by owner_user.
        owned |= Q(owner_user__isnull=True, owner_email__iexact=user_email)
    return queryset.filter(owned)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def airflow_error_response(exc: AirflowError, context: str = ""):
    logger.warning("Airflow error%s: %s", f" [{context}]" if context else "", exc)
    # Map upstream errors so our service doesn't look unhealthy.
    upstream = getattr(exc, "status_code", 502) or 502
    response_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if upstream >= 500
        else status.HTTP_502_BAD_GATEWAY
    )
    return Response(
        {"detail": "Airflow is unavailable or rejected the scheduler request."},
        status=response_status,
    )


def _apply_airflow_summary(schedule, dag, latest_run):
    """Pure function: mutate schedule fields from Airflow data. No I/O."""
    if dag:
        schedule.next_run = airflow.parse_time(
            dag.get("next_dagrun_create_after") or dag.get("next_dagrun")
        )
        schedule.status = (
            Schedule.Status.PAUSED
            if dag.get("is_paused")
            else Schedule.Status.ACTIVE
        )
    if latest_run:
        schedule.last_run = datetime.fromtimestamp(
            latest_run["start"] / 1000, tz=datetime_timezone.utc
        )
        schedule.last_status = latest_run.get("status", "")
    schedule.airflow_synced_at = timezone.now()
    schedule.airflow_sync_error = ""


def _send_schedule_notification(schedule, event, run_id=""):
    try:
        send_schedule_notification(schedule, event, run_id=run_id)
    except NotificationDeliveryError:
        logger.exception(
            "Unable to send %s notification for schedule %s",
            event,
            schedule.pk,
        )


def _sync_one(schedule, *, save=True):
    """Fetch Airflow state for a single schedule and persist it."""
    try:
        airflow.ensure_dag_file_current(schedule)
        dag = airflow.get_dag(schedule)
        if not dag:
            schedule.status = Schedule.Status.PENDING
            schedule.airflow_sync_error = "Waiting for Airflow to register the generated DAG."
            schedule.airflow_synced_at = timezone.now()
            if save:
                schedule.save(
                    update_fields=[
                        "status",
                        "airflow_synced_at",
                        "airflow_sync_error",
                        "updated_at",
                    ]
                )
            return schedule
        if schedule.status == Schedule.Status.PENDING:
            dag = airflow.set_paused(schedule, False)
        runs = airflow.runs_for_schedule(schedule, limit=1) if dag else []
        _apply_airflow_summary(schedule, dag, runs[0] if runs else None)
    except AirflowError as exc:
        schedule.airflow_sync_error = str(exc)
        if save:
            schedule.save(
                update_fields=[
                    "airflow_synced_at",
                    "airflow_sync_error",
                    "updated_at",
                ]
            )
        raise
    if save:
        schedule.save(
            update_fields=[
                "last_run",
                "last_status",
                "next_run",
                "status",
                "airflow_synced_at",
                "airflow_sync_error",
                "updated_at",
            ]
        )
    return schedule


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def health(request):
    """Liveness probe. Cheap, no dependencies."""
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsCampaignManager])
def ready(request):
    """Readiness probe. Hits DB and Airflow."""
    from django.db import connection

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover
        logger.exception("DB readiness check failed")
        return Response(
            {"status": "unavailable", "detail": f"db: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        airflow.ping()
    except AirflowError as exc:
        logger.warning("Airflow readiness check failed: %s", exc)
        return Response(
            {"status": "unavailable", "detail": f"airflow: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([IsCampaignManager])
def connections(request):
    """Expose Airflow connection IDs for SQL task configuration, never secrets."""
    try:
        return Response(airflow.list_connections())
    except AirflowError as exc:
        return airflow_error_response(exc, context="connections")


def validate_airflow_connection(serializer):
    task_type = serializer.validated_data.get(
        "task_type", getattr(serializer.instance, "task_type", None)
    )
    if task_type != Schedule.TaskType.SQL:
        return None
    connection_id = serializer.validated_data.get(
        "connection", getattr(serializer.instance, "connection", "")
    )
    try:
        exists = airflow.connection_exists(connection_id)
    except AirflowError as exc:
        return airflow_error_response(exc, context="validate-sql-connection")
    if not exists:
        raise ValidationError({"connection": "Select a connection that exists in Airflow."})
    return None


# ---------------------------------------------------------------------------
# Schedule collection
# ---------------------------------------------------------------------------
@api_view(["GET", "POST"])
@permission_classes([IsCampaignManager])
def schedules(request):
    if request.method == "GET":
        queryset = visible_schedules(request).order_by("name")
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(owner__icontains=search)
                | Q(owner_email__icontains=search)
            )
        paginator = LimitOffsetPagination()
        paginator.default_limit = 50
        paginator.max_limit = 200
        page = paginator.paginate_queryset(queryset, request, view=schedules)

        # Best-effort sync; failures don't fail the whole request.
        for item in page:
            try:
                _sync_one(item)
            except AirflowError:
                continue

        serializer = ScheduleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    # POST
    serializer = ScheduleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    connection_error = validate_airflow_connection(serializer)
    if connection_error:
        return connection_error

    # Persist first (in a transaction), then push to Airflow outside it.
    with transaction.atomic():
        item = serializer.save(
            owner_user=request.user,
            status=Schedule.Status.PENDING,
        )

    _send_schedule_notification(item, "created")
    try:
        airflow.write_dag(item)
        airflow.set_paused(item, False)
        item.next_run = airflow.next_run(item)
        item.status = Schedule.Status.ACTIVE
        item.airflow_sync_error = ""
        item.airflow_synced_at = timezone.now()
        item.save(
            update_fields=[
                "next_run",
                "status",
                "airflow_sync_error",
                "airflow_synced_at",
                "updated_at",
            ]
        )
    except AirflowError as exc:
        logger.warning("DAG write failed for %s: %s", item.pk, exc)
        waiting_for_dag = exc.status_code == 404
        item.airflow_sync_error = (
            "Waiting for Airflow to register the generated DAG."
            if waiting_for_dag
            else str(exc)
        )
        item.status = (
            Schedule.Status.PENDING if waiting_for_dag else Schedule.Status.FAILED
        )
        item.save(update_fields=["airflow_sync_error", "status", "updated_at"])
        return Response(
            {
                "detail": (
                    "Schedule saved and is waiting for Airflow to register it."
                    if waiting_for_dag
                    else "Schedule saved but Airflow sync failed."
                ),
                "airflowSyncError": item.airflow_sync_error,
                "id": item.pk,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    return Response(ScheduleSerializer(item).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Schedule detail
# ---------------------------------------------------------------------------
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsCampaignManager])
def schedule_detail(request, schedule_id):
    item = get_object_or_404(visible_schedules(request), pk=schedule_id)

    if request.method == "GET":
        try:
            _sync_one(item)
        except AirflowError as exc:
            # Return local state + sync error rather than 5xx-ing the whole read.
            data = ScheduleSerializer(item).data
            data["airflowSyncError"] = str(exc)
            return Response(data)
        return Response(ScheduleSerializer(item).data)

    if request.method == "PATCH":
        serializer = ScheduleSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        connection_error = validate_airflow_connection(serializer)
        if connection_error:
            return connection_error

        with transaction.atomic():
            # Lock the row so concurrent PATCHes serialize.
            item = Schedule.objects.select_for_update().get(pk=item.pk)
            serializer = ScheduleSerializer(item, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            item = serializer.save()

        try:
            airflow.write_dag(item)
            airflow.set_paused(item, item.status == Schedule.Status.PAUSED)
            item.next_run = (
                None
                if item.status == Schedule.Status.PAUSED
                else airflow.next_run(item)
            )
            item.airflow_sync_error = ""
            item.airflow_synced_at = timezone.now()
            item.save(
                update_fields=[
                    "next_run",
                    "airflow_sync_error",
                    "airflow_synced_at",
                    "updated_at",
                ]
            )
        except AirflowError as exc:
            logger.warning("DAG update failed for %s: %s", item.pk, exc)
            item.airflow_sync_error = str(exc)
            item.save(update_fields=["airflow_sync_error", "updated_at"])
            return Response(
                {
                    "detail": "Saved locally but Airflow sync failed.",
                    "airflowSyncError": str(exc),
                    "schedule": ScheduleSerializer(item).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        return Response(ScheduleSerializer(item).data)

    # Keep the row until both Airflow and the generated source file are cleaned
    # up so a failed deletion remains visible and can be retried.
    dag_id = item.airflow_dag_id
    schedule_id_value = item.pk
    try:
        airflow.delete_dag_by_id(dag_id)
        airflow.remove_dag_file_by_id(dag_id)
    except AirflowError as exc:
        logger.warning(
            "Airflow cleanup failed while deleting schedule %s: %s",
            schedule_id_value,
            exc,
        )
        return airflow_error_response(exc, context="delete")
    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsCampaignManager])
def pause_schedule(request, schedule_id):
    item = get_object_or_404(visible_schedules(request), pk=schedule_id)
    paused = request.data.get("paused")
    if not isinstance(paused, bool):
        return Response(
            {"paused": "Expected a boolean."}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        airflow.set_paused(item, paused)
    except AirflowError as exc:
        return airflow_error_response(exc, context="pause")

    item.status = (
        Schedule.Status.PAUSED if paused else Schedule.Status.ACTIVE
    )
    item.next_run = None if paused else airflow.next_run(item)
    item.save(update_fields=["status", "next_run", "updated_at"])
    return Response(ScheduleSerializer(item).data)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsCampaignManager])
def run_now(request, schedule_id):
    item = get_object_or_404(visible_schedules(request), pk=schedule_id)
    try:
        run = airflow.trigger_run(item)
    except AirflowError as exc:
        return airflow_error_response(exc, context="trigger")

    item.last_run = timezone.now()
    item.last_status = "queued"
    item.save(update_fields=["last_run", "last_status", "updated_at"])
    return Response(run, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
@permission_classes([IsCampaignManager])
def schedule_runs(request, schedule_id):
    item = get_object_or_404(visible_schedules(request), pk=schedule_id)
    try:
        return Response(airflow.runs_for_schedule(item))
    except AirflowError as exc:
        return airflow_error_response(exc, context="runs")


@api_view(["GET"])
@permission_classes([IsCampaignManager])
def all_runs(request):
    """Single Airflow call for all DAG runs; annotate with schedule metadata."""
    try:
        runs = airflow.all_dag_runs(limit=200)
    except AirflowError as exc:
        return airflow_error_response(exc, context="all-runs")

    schedules_by_dag = {
        schedule.airflow_dag_id: schedule
        for schedule in visible_schedules(request)
    }
    visible_runs = []
    for run in runs:
        schedule = schedules_by_dag.get(run.get("dag_id"))
        if schedule is None:
            continue
        serialized = airflow.serialize_run(schedule, run)
        serialized["scheduleName"] = schedule.name
        visible_runs.append(serialized)
    return Response(visible_runs)


@api_view(["GET"])
@permission_classes([IsCampaignManager])
def run_logs(request, schedule_id, run_id):
    item = get_object_or_404(visible_schedules(request), pk=schedule_id)
    try:
        return Response(airflow.logs_for_run(item, run_id))
    except AirflowError as exc:
        return airflow_error_response(exc, context="logs")


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def schedule_notification_callback(request, schedule_id):
    configured_token = settings.TASK_SCHEDULER_CALLBACK_TOKEN
    supplied_token = request.headers.get("X-Task-Scheduler-Token", "")
    if not configured_token or not secrets.compare_digest(
        supplied_token, configured_token
    ):
        return Response(
            {"detail": "Invalid scheduler callback credentials."},
            status=status.HTTP_403_FORBIDDEN,
        )

    event = request.data.get("event")
    if not isinstance(event, str) or event not in {"started", "completed", "failed"}:
        return Response(
            {"event": "Expected started, completed, or failed."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    item = get_object_or_404(Schedule, pk=schedule_id)
    run_id = str(request.data.get("runId", ""))[:250]
    try:
        send_schedule_notification(item, event, run_id=run_id)
    except NotificationDeliveryError:
        logger.exception(
            "Unable to send %s notification for schedule %s",
            event,
            item.pk,
        )
        return Response(
            {"detail": "Task notification could not be delivered."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response(status=status.HTTP_204_NO_CONTENT)
