from django.urls import path

from . import views

app_name = "task_scheduler"

urlpatterns = [
    # Probes
    path("health/", views.health, name="health"),
    path("ready/", views.ready, name="ready"),

    # Collections
    path("schedules/", views.schedules, name="schedules"),
    path("runs/", views.all_runs, name="all-runs"),

    # Run-related routes must be registered BEFORE the generic detail route,
    # otherwise "runs" and "pause" could be swallowed by <schedule_id>/.
    path(
        "schedules/<str:schedule_id>/runs/trigger/",
        views.run_now,
        name="run-now",
    ),
    path(
        "schedules/<str:schedule_id>/runs/<str:run_id>/logs/",
        views.run_logs,
        name="run-logs",
    ),
    path(
        "schedules/<str:schedule_id>/runs/",
        views.schedule_runs,
        name="schedule-runs",
    ),
    path(
        "schedules/<str:schedule_id>/pause/",
        views.pause_schedule,
        name="schedule-pause",
    ),
    path(
        "schedules/<str:schedule_id>/",
        views.schedule_detail,
        name="schedule-detail",
    ),
]
