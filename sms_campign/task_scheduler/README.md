# Integrated Task Scheduler

Task schedules are stored by the `task_scheduler` Django app in the Campaign
Manager's configured database. The migration adds a separate
`task_scheduler_schedule` table; it does not change the Campaign Manager's
campaign schedule tables or Airflow metadata tables.

The API is available under `/api/v1/task-scheduler/` and uses the Campaign
Manager's JWT authentication. Schedules are scoped to their creator; superusers
can administer all schedules. Older rows without a creator remain visible to a
matching owner email or a superuser.

The Django service publishes generated task DAG files to
`AIRFLOW_DAGS_DIR`. Docker Compose mounts a dedicated `task_scheduler_dags`
volume at that path and at `/opt/airflow/dags/task-scheduler` in the existing
Airflow scheduler and webserver. Airflow API credentials come from
`AIRFLOW_ADMIN_USERNAME` and `AIRFLOW_ADMIN_PASSWORD`. The existing campaign
DAG folder, scheduler, webserver, and PostgreSQL service are reused.

Python and SQL task code executes in Airflow. The SQL connection picker reads
configured connection IDs and types through the authenticated Django API; the
backend verifies that a selected connection exists before saving the task.
Connection credentials are never sent to the browser. Only create or run task
code that has been reviewed and is trusted. Configure the selected Airflow
connection before running a SQL task.

When a schedule accepts notifications, task creation, start, completion, and
failure messages are sent to its owner using the active default Email
Configuration in Campaign Manager. Compose passes the
`TASK_SCHEDULER_CALLBACK_TOKEN` to Django and Airflow so task callbacks can
authenticate their internal notification requests. Set a unique secret value
for deployments; the Compose fallback is intended only for local development.
If Airflow has not parsed a new DAG yet, schedule creation returns promptly
with `Pending` status; a subsequent schedule read promotes it after Airflow
registers the DAG.

The repository contains the standalone application's schema and migrations,
but no database dump or Airflow metadata export. Applying the new migrations
creates the integrated tables; it cannot import schedule rows or historical
Airflow runs from a separate deployment without that deployment's data and a
planned migration.
