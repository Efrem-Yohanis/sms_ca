from datetime import datetime, time, timezone as datetime_timezone
from unittest.mock import patch

from django.core import mail
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from sms_campaign_manager.models import EmailConfig

from .airflow import AirflowError, connection_exists, list_connections, logs_for_run, render_dag, set_paused
from .models import Schedule
from .notifications import send_schedule_notification
from .views import _sync_one


class ScheduleApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="scheduler-test", email="scheduler@example.com", password="test-pass"
        )
        self.client.force_authenticate(user=self.user)
        self.payload = {
            "id": "s-example",
            "name": "Example task",
            "owner": "Example owner",
            "ownerEmail": "owner@example.com",
            "acceptNotifications": True,
            "scheduleType": "Manual",
            "cron": "0 2 * * *",
            "intervalValue": 15,
            "intervalUnit": "minutes",
            "timezone": "Africa/Addis_Ababa",
            "startDate": None,
            "endDate": None,
            "type": "Python",
            "code": "print('ok')",
            "connection": "",
            "retries": 2,
            "retryDelay": 30,
            "status": "Active",
        }

    @patch(
        "task_scheduler.views.airflow.next_run",
        return_value=datetime(2026, 10, 11, 5, 0, tzinfo=datetime_timezone.utc),
    )
    @patch("task_scheduler.views.airflow.set_paused")
    @patch("task_scheduler.views.airflow.write_dag")
    def test_create_schedule_persists_and_returns_ui_shape(
        self, write_dag, set_paused, next_run
    ):
        response = self.client.post("/api/v1/task-scheduler/schedules/", self.payload, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["ownerEmail"], "owner@example.com")
        schedule = Schedule.objects.get(name="Example task")
        self.assertEqual(response.data["id"], schedule.pk)
        self.assertEqual(schedule.owner_user, self.user)
        self.assertEqual(response.data["nextRun"], 1791694800000)
        set_paused.assert_called_once_with(schedule, False)
        write_dag.assert_called_once()

    @patch("task_scheduler.views.send_schedule_notification")
    @patch(
        "task_scheduler.views.airflow.set_paused",
        side_effect=AirflowError("DAG is not registered yet.", 404),
    )
    @patch("task_scheduler.views.airflow.write_dag")
    def test_create_returns_pending_while_airflow_parses_dag(
        self, write_dag, set_paused, send_notification
    ):
        response = self.client.post(
            "/api/v1/task-scheduler/schedules/", self.payload, format="json"
        )

        schedule = Schedule.objects.get(name="Example task")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(schedule.status, Schedule.Status.PENDING)
        self.assertIn("Waiting for Airflow", response.data["airflowSyncError"])
        self.assertEqual(response.data["id"], schedule.pk)
        write_dag.assert_called_once_with(schedule)
        set_paused.assert_called_once_with(schedule, False)
        send_notification.assert_called_once_with(schedule, "created")

    def test_task_scheduler_requires_authentication(self):
        client = APIClient()

        response = client.get("/api/v1/task-scheduler/schedules/")

        self.assertEqual(response.status_code, 401)

    @patch(
        "task_scheduler.views.airflow.list_connections",
        return_value=[{"id": "warehouse", "type": "postgres"}],
    )
    def test_connections_endpoint_returns_configured_airflow_connections(self, list_connections):
        response = self.client.get("/api/v1/task-scheduler/connections/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{"id": "warehouse", "type": "postgres"}])
        list_connections.assert_called_once_with()

    def test_users_only_list_their_own_schedules(self):
        other_user = get_user_model().objects.create_user(
            username="other-scheduler-test", email="other@example.com", password="test-pass"
        )
        Schedule.objects.create(
            id="s-owned-by-other",
            name="Private task",
            owner="Other user",
            owner_email=other_user.email,
            owner_user=other_user,
            task_type="Python",
            code="print('private')",
        )

        response = self.client.get("/api/v1/task-scheduler/schedules/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_sql_schedule_requires_connection(self):
        payload = {**self.payload, "type": "SQL", "connection": ""}

        response = self.client.post("/api/v1/task-scheduler/schedules/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("connection", response.data)

    @patch(
        "task_scheduler.airflow.airflow_request",
        return_value={
            "connections": [{
                "connection_id": "warehouse_pg",
                "conn_type": "postgres",
                "password": "must-not-leak",
            }],
            "total_entries": 1,
        },
    )
    def test_airflow_connection_listing_returns_ids_and_types_only(self, airflow_request):
        self.assertEqual(
            list_connections(),
            [{"id": "warehouse_pg", "type": "postgres"}],
        )
        airflow_request.assert_called_once_with(
            "GET", "connections", params={"limit": 100, "offset": 0}
        )

    @patch(
        "task_scheduler.airflow.airflow_request",
        side_effect=AirflowError("Connection not found.", 404),
    )
    def test_airflow_connection_exists_handles_unknown_connection(self, airflow_request):
        self.assertFalse(connection_exists("missing_connection"))
        airflow_request.assert_called_once_with(
            "GET", "connections/missing_connection"
        )

    @patch("task_scheduler.views.airflow.connection_exists", return_value=False)
    def test_sql_schedule_rejects_connection_not_configured_in_airflow(self, connection_exists_mock):
        payload = {**self.payload, "type": "SQL", "connection": "missing_connection"}

        response = self.client.post("/api/v1/task-scheduler/schedules/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("connection", response.data)
        self.assertFalse(Schedule.objects.filter(name="Example task").exists())
        connection_exists_mock.assert_called_once_with("missing_connection")

    def test_generated_dag_embeds_configuration_as_json_not_python_source(self):
        schedule = Schedule(
            **{
                "id": self.payload["id"],
                "name": self.payload["name"],
                "owner": self.payload["owner"],
                "owner_email": self.payload["ownerEmail"],
                "schedule_type": "Manual",
                "task_type": "Python",
                "code": "__import__('os').system('echo safe')",
                "airflow_dag_id": "ui_schedule_s_example",
            }
        )

        dag = render_dag(schedule)

        self.assertIn("json.loads(", dag)
        self.assertNotIn("__import__('os').system('echo safe')", dag)

    def test_generated_cron_dag_uses_trigger_timetable_in_schedule_timezone(self):
        schedule = Schedule(
            id="s-cron",
            name="Cron task",
            owner="Example owner",
            owner_email="owner@example.com",
            schedule_type=Schedule.ScheduleType.CRON,
            cron="35 13 * * *",
            timezone="Africa/Addis_Ababa",
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )

        dag = render_dag(schedule)

        self.assertIn(
            "schedule=CronTriggerTimetable('35 13 * * *', timezone='Africa/Addis_Ababa')",
            dag,
        )

    @patch("task_scheduler.views.airflow.set_paused")
    @patch("task_scheduler.views.airflow.write_dag")
    @patch("task_scheduler.views.airflow.next_run", return_value=None)
    def test_create_schedule_saves_run_constraints(
        self, next_run, write_dag, set_paused
    ):
        payload = {
            **self.payload,
            "scheduleType": "Cron",
            "cron": "35 13 * * *",
            "daysOfWeek": [0, 2, 2],
            "windowStart": "09:00",
            "windowEnd": "17:00",
            "excludedDates": ["2026-12-25", "2026-01-01", "2026-12-25"],
        }

        response = self.client.post("/api/v1/task-scheduler/schedules/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        schedule = Schedule.objects.get(name="Example task")
        self.assertEqual(schedule.days_of_week, [0, 2])
        self.assertEqual(schedule.window_start.isoformat(), "09:00:00")
        self.assertEqual(schedule.window_end.isoformat(), "17:00:00")
        self.assertEqual(
            schedule.excluded_dates, ["2026-01-01", "2026-12-25"]
        )
        self.assertEqual(response.data["effectiveCron"], "35 13 * * *")
        write_dag.assert_called_once()
        set_paused.assert_called_once()

    def test_non_cron_schedule_rejects_weekday_and_window_filters(self):
        payload = {
            **self.payload,
            "daysOfWeek": [0],
            "windowStart": "09:00",
            "windowEnd": "17:00",
        }

        response = self.client.post("/api/v1/task-scheduler/schedules/", payload, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("daysOfWeek", response.data)

    def test_cron_run_window_must_be_same_day_and_complete(self):
        incomplete = {
            **self.payload,
            "scheduleType": "Cron",
            "windowStart": "09:00",
        }
        overnight = {
            **self.payload,
            "scheduleType": "Cron",
            "windowStart": "22:00",
            "windowEnd": "06:00",
        }

        incomplete_response = self.client.post(
            "/api/v1/task-scheduler/schedules/", incomplete, format="json"
        )
        overnight_response = self.client.post(
            "/api/v1/task-scheduler/schedules/", overnight, format="json"
        )

        self.assertEqual(incomplete_response.status_code, 400)
        self.assertIn("windowStart", incomplete_response.data)
        self.assertEqual(overnight_response.status_code, 400)
        self.assertIn("windowEnd", overnight_response.data)

    def test_generated_dag_gates_runs_using_local_day_window_and_exclusions(self):
        schedule = Schedule(
            id="s-window",
            name="Window task",
            owner="Example owner",
            owner_email="owner@example.com",
            schedule_type=Schedule.ScheduleType.CRON,
            cron="35 13 * * *",
            timezone="Africa/Addis_Ababa",
            days_of_week=[0, 2],
            window_start=time(9, 0),
            window_end=time(17, 0),
            excluded_dates=["2026-12-25"],
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )

        dag = render_dag(schedule)
        compile(dag, "generated_dag.py", "exec")

        self.assertIn(
            "schedule=CronTriggerTimetable('35 13 * * *', timezone='Africa/Addis_Ababa')",
            dag,
        )
        self.assertIn("ALLOWED_DOWS = [0, 2]", dag)
        self.assertIn("WINDOW_START = time(9, 0)", dag)
        self.assertIn("WINDOW_END = time(17, 0)", dag)
        self.assertIn("EXCLUDED_DATES = ['2026-12-25']", dag)
        self.assertIn('local_run_time = context["logical_date"].in_timezone(TIMEZONE)', dag)
        self.assertIn("run_gate >> execute", dag)

    def test_generated_dag_notifies_task_start_completion_and_failure(self):
        schedule = Schedule(
            id="s-notify",
            name="Notification task",
            owner="Example owner",
            owner_email="owner@example.com",
            schedule_type=Schedule.ScheduleType.MANUAL,
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )

        dag = render_dag(schedule)

        compile(dag, "generated_notification_dag.py", "exec")
        self.assertIn('notify_schedule_event("started", context)', dag)
        self.assertIn('notify_schedule_event("completed", context)', dag)
        self.assertIn('notify_schedule_event("failed", context)', dag)

    @patch("task_scheduler.views.airflow.runs_for_schedule", return_value=[])
    @patch(
        "task_scheduler.views.airflow.get_dag",
        return_value={
            "next_dagrun": "2026-10-10T10:35:00+00:00",
            "next_dagrun_create_after": "2026-10-11T10:35:00+00:00",
            "is_paused": False,
        },
    )
    def test_sync_summary_uses_next_dagrun_create_after(self, get_dag, runs_for_schedule):
        schedule = Schedule.objects.create(
            id="s-next-run",
            name="Next run task",
            owner="Example owner",
            owner_email="owner@example.com",
            schedule_type=Schedule.ScheduleType.CRON,
            cron="35 13 * * *",
            timezone="Africa/Addis_Ababa",
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )

        _sync_one(schedule)

        self.assertEqual(
            schedule.next_run.isoformat(),
            "2026-10-11T10:35:00+00:00",
        )

    @patch("task_scheduler.views.airflow.set_paused", return_value={"is_paused": False})
    @patch("task_scheduler.views.airflow.runs_for_schedule", return_value=[])
    @patch(
        "task_scheduler.views.airflow.get_dag",
        return_value={
            "next_dagrun_create_after": "2026-10-11T10:35:00+00:00",
            "is_paused": True,
        },
    )
    def test_sync_activates_pending_schedule_after_airflow_registers_dag(
        self, get_dag, runs_for_schedule, set_paused
    ):
        schedule = Schedule.objects.create(
            id="s-pending-sync",
            name="Pending task",
            owner="Example owner",
            owner_email="owner@example.com",
            status=Schedule.Status.PENDING,
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )

        _sync_one(schedule)

        self.assertEqual(schedule.status, Schedule.Status.ACTIVE)
        self.assertEqual(schedule.airflow_sync_error, "")
        set_paused.assert_called_once_with(schedule, False)

    @patch(
        "task_scheduler.airflow.airflow_request",
        side_effect=AirflowError("DAG not found.", 404),
    )
    def test_set_paused_returns_immediately_when_airflow_has_not_parsed_dag(
        self, airflow_request
    ):
        schedule = Schedule(
            id="s-new-dag",
            name="New DAG",
            owner="Example owner",
            owner_email="owner@example.com",
            airflow_dag_id="ui_schedule_s_new_dag",
        )

        with self.assertRaises(AirflowError) as error:
            set_paused(schedule, False)

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(airflow_request.call_count, 1)

    @override_settings(TASK_SCHEDULER_CALLBACK_TOKEN="scheduler-callback-test")
    @patch("task_scheduler.views.send_schedule_notification")
    def test_internal_callback_requires_token_and_sends_valid_event(self, send_notification):
        schedule = Schedule.objects.create(
            id="s-callback",
            name="Callback task",
            owner="Example owner",
            owner_email="owner@example.com",
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )
        url = f"/api/v1/task-scheduler/schedules/{schedule.pk}/notifications/"

        denied = APIClient().post(url, {"event": "started"}, format="json")
        accepted = APIClient().post(
            url,
            {"event": "completed", "runId": "manual__test"},
            format="json",
            HTTP_X_TASK_SCHEDULER_TOKEN="scheduler-callback-test",
        )

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(accepted.status_code, 204)
        send_notification.assert_called_once_with(
            schedule, "completed", run_id="manual__test"
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_schedule_notification_uses_active_campaign_default_and_square_template(self):
        schedule = Schedule.objects.create(
            id="s-email",
            name="Task & report",
            owner="Example owner",
            owner_email="owner@example.com",
            task_type=Schedule.TaskType.PYTHON,
            code="print('ok')",
        )
        EmailConfig.objects.create(
            name="Default campaign mail",
            host="smtp.example.com",
            default_from_email="campaign@example.com",
            is_default=True,
            is_active=True,
        )

        result = send_schedule_notification(schedule, "created")

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "campaign@example.com")
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn("Task &amp; report", html)
        self.assertNotIn("border-radius", html)

    @patch(
        "task_scheduler.airflow.airflow_request",
        side_effect=[
            {
                "task_instances": [
                    {
                        "task_id": "execute_schedule",
                        "try_number": 1,
                        "state": "success",
                        "start_date": "2026-10-10T10:35:01+00:00",
                    }
                ]
            },
            "INFO - hello from task\nWARN - sample warning\n",
        ],
    )
    def test_logs_for_run_handles_airflow_plain_text_log_responses(self, airflow_request):
        schedule = Schedule(
            id="s-log",
            name="Log task",
            owner="Example owner",
            owner_email="owner@example.com",
            airflow_dag_id="ui_schedule_s_log",
        )

        logs = logs_for_run(schedule, "scheduled__2026-10-10T10:35:00+00:00")

        self.assertEqual([entry["msg"] for entry in logs], [
            "INFO - hello from task",
            "WARN - sample warning",
        ])
        self.assertEqual([entry["level"] for entry in logs], ["INFO", "WARN"])
        self.assertTrue(airflow_request.call_args.kwargs["raw_text"])
