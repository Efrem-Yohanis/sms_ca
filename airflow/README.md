# Airflow Orchestration Scheduler

The `airflow` directory contains the Apache Airflow deployment and DAGs that
orchestrate campaign dispatch and scheduled report delivery. Airflow polls the
campaign backend for work and coordinates with the separate SMS sender API.
It is not the campaign scheduling data store: campaign schedules and their
due-window decisions are managed by the Django campaign backend.

## What it does

The Compose deployment includes two DAGs. Both are configured to run once per
minute in Ethiopian time (`Africa/Addis_Ababa`), with catchup disabled and at
most one active run of each DAG.

### `dispatch_campaigns`

The campaign dispatcher performs these operations:

1. Reads due campaign windows from
   `GET /api/v1/schedules/due-now/`.
2. Reads currently active sends from `GET /sender/status` on the SMS sender.
3. For each due campaign:
   - If its audience needs a rebuild, requests the build from Django and polls
     build progress until success, failure, or timeout.
   - Builds campaign message records when required or after an audience
     rebuild.
   - Activates the campaign through the campaign API.
   - Starts that campaign round through the campaign API, which records the
     campaign as in progress and emails its owner when sending begins.
   - Stops a previously running round if the due schedule has advanced to a
     different round.
4. Stops sender campaigns that are running but are no longer due.
5. Logs the dispatch result and writes started, stopped, and error details to
   the Airflow task's XCom values.

The campaign API handles schedule calculation and persists campaign and
message data. The sender service performs SMSC submission; Airflow coordinates
when it should run.

### `dispatch_reports`

The report dispatcher:

1. Reads due subscriptions from
   `GET /api/v1/report-subscriptions/due-now/`.
2. Requests each due subscription to be sent through
   `POST /api/v1/report-subscriptions/<id>/send-now/` with `scheduled: true`.
3. Sends only when at least one selected campaign has started and is still in
   progress or paused, or has completed since its final status was last reported
   to that recipient. Campaigns that complete between rounds are included once
   with their final status and delivery statistics.
4. Advances the schedule without sending email when there are no running
   campaigns or unreported final results.
5. Logs successful, skipped, and failed sends and publishes the results to task
   XCom.

The campaign backend generates and delivers the reports; this DAG periodically
asks it to process subscriptions that are due.

Each DAG is configured with one retry and a 30-second retry delay for task
failures. Per-campaign dispatch errors and per-subscription report failures are
collected and logged in the task result; consult the task logs and XCom to
diagnose them.

## Components and access points

The root `docker-compose.yml` defines these Airflow services:

- **`airflow-init`** — runs Airflow metadata database migrations and creates
  the configured Airflow admin user if it does not exist.
- **`scduler_app`** — runs the Airflow scheduler process that discovers DAGs
  and launches due tasks. The service name is spelled `scduler_app` in Compose.
- **`airflow-webserver`** — serves the Airflow browser UI and API.

Open the Airflow UI at `http://localhost:8080` by default. Set
`AIRFLOW_WEBSERVER_PORT` to change its host port. The scheduler itself is an
internal Compose service and does not publish an HTTP port.

The campaign dispatcher reaches these services over the Compose network:

- Campaign backend: `http://camaping-manager-backend-app:8000/api/v1`
- SMS sender: `http://sms_sender_app:8001`

The DAG files are mounted read-only from `airflow/dags/` into the Airflow
containers. Airflow task logs are stored in the `airflow_logs` Docker volume.

## Technology

- Apache Airflow 2.10.5
- Python 3.11
- `LocalExecutor`
- `requests` for HTTP calls to the campaign backend and SMS sender
- PostgreSQL for Airflow metadata in the local Compose deployment

The Compose environment disables example DAGs, starts newly discovered DAGs
unpaused, and uses the existing PostgreSQL Compose service for Airflow
metadata. For production, use a dedicated metadata database and appropriate
Airflow executor and secrets management for the expected workload.

## Configuration

These environment variables are configured for the Airflow services:

| Variable | Compose default | Purpose |
| --- | --- | --- |
| `AIRFLOW__CORE__DEFAULT_TIMEZONE` | `Africa/Addis_Ababa` | Default timezone used by the Airflow scheduler. |
| `AIRFLOW__WEBSERVER__DEFAULT_UI_TIMEZONE` | `Africa/Addis_Ababa` | Timezone used to display Airflow dates and times in the web UI. |
| `AIRFLOW_DJANGO_API` | `http://camaping-manager-backend-app:8000/api/v1` | Campaign API base URL used by the DAGs. |
| `AIRFLOW_SENDER_API` | `http://sms_sender_app:8001` | SMS sender API base URL used by the campaign dispatcher. |
| `AIRFLOW_AUDIENCE_BUILD_TIMEOUT` | `1800` seconds | Maximum time the campaign DAG polls an audience build before failing that campaign dispatch. |
| `AIRFLOW_AUDIENCE_POLL_INTERVAL` | `5` seconds | Delay between audience build progress checks. |
| `AIRFLOW_ADMIN_USERNAME` | `admin` | Airflow UI administrator username created by `airflow-init`. |
| `AIRFLOW_ADMIN_PASSWORD` | `change-this-local-password` | Airflow UI administrator password. Replace it before deployment. |
| `AIRFLOW_ADMIN_EMAIL` | `admin@example.com` | Email for the Airflow administrator account. |
| `AIRFLOW_WEBSERVER_PORT` | `8080` | Host port mapped to the Airflow webserver's port 8080. |
| `AIRFLOW_FERNET_KEY` | Empty | Fernet key used by Airflow to encrypt sensitive connection/variable values. Set a stable key before storing secrets. |
| `AIRFLOW_WEBSERVER_SECRET_KEY` | Local development value | Webserver signing key, including for session and webserver operation. Replace it before deployment. |
| `AIRFLOW_UID` | `50000` | Linux user ID used to run Airflow containers. |

Airflow's metadata connection is assembled from the shared PostgreSQL Compose
variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`. The default
values in Compose are local-development values; do not use them in a shared or
production environment.

## Run and inspect

From the repository root, build and start the Airflow services along with
their dependencies:

```powershell
docker compose up --build -d airflow-init scduler_app airflow-webserver
```

To start the complete platform instead:

```powershell
docker compose up --build -d
```

Then open `http://localhost:8080`, sign in with the configured Airflow admin
account, and inspect the `dispatch_campaigns` and `dispatch_reports` DAGs.
For an unsuccessful or incomplete dispatch, inspect the DAG run, task logs,
and task XCom values. Also verify that the campaign backend and SMS sender are
healthy and reachable from the Compose network.

## Relationship to the campaign scheduler

This Airflow deployment uses the campaign schedule API to decide which
campaign rounds are due, then coordinates the SMS sender. It is separate from
the optional `standalone_scheduler_api` service in Compose, which is defined
under the `standalone-scheduler` profile and runs from the
`sms_campaign_scheduler` directory. The standalone scheduler is not the
Airflow webserver or scheduler, and it is not started by the standard Compose
stack.
