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

Python and SQL task code executes in Airflow. Only create or run task code that
has been reviewed and is trusted. Configure the selected Airflow connection
before running a SQL task. Email notification delivery is not implemented by
the source scheduler UI; the preference is retained as schedule data.

The repository contains the standalone application's schema and migrations,
but no database dump or Airflow metadata export. Applying the new migrations
creates the integrated tables; it cannot import schedule rows or historical
Airflow runs from a separate deployment without that deployment's data and a
planned migration.
