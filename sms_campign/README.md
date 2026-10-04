# SMS Campaign Manager Backend

The `sms_campign` application is the Django REST API and data-management
service for the SMS Campaign Manager. It serves the campaign UI, validates and
stores campaign setup, builds audiences and outbound message records, manages
schedules and reports, and exposes delivery progress and status APIs.

This service is not the SMSC itself. Message submission, delivery-receipt
processing, and schedule orchestration are connected services in the wider
platform.

## Technology

- Python 3.12 in the Docker image
- Django 4.2 and Django REST Framework
- SimpleJWT for JWT authentication
- drf-spectacular for OpenAPI, Swagger UI, and ReDoc
- PostgreSQL in Docker Compose; SQLite for local development by default
- pandas and openpyxl for data import and processing
- requests for outbound HTTP integrations

## Main responsibilities

- **Campaigns:** CRUD, readiness checks, validation, lifecycle actions, and
  dashboard summaries.
- **Audiences:** manual recipient entry, CSV/Excel import, or database-backed
  sources; MSISDN validation, duplicate handling, language mapping, build
  progress, and audience statistics.
- **Messages:** localized campaign content and generation of queued message
  records from valid audience members.
- **Schedules:** one-time and recurring schedules, time windows, upcoming
  windows, and activation controls.
- **Delivery visibility:** campaign progress, message batches, send records,
  delivery records, and aggregate send/delivery statistics.
- **Configuration:** channels, languages, Sender IDs, SMSC settings, database
  connections, customer profiles, global TPS, N-address limits, and email
  services/reports.
- **Test SMS:** submit test messages through the SMSC integration and review
  their recorded provider responses.

## Request and processing flow

1. The campaign UI submits requests to this API under `/api/v1/`.
2. Campaign and setup data are persisted in the shared platform database.
3. Audience builds can run as background jobs. The `audience-worker` Compose
   service runs `run_audience_build_jobs` and processes pending build jobs.
4. On activation, the backend checks campaign readiness and builds message
   records for the eligible audience.
5. The separate SMS sender service submits queued messages to the configured
   SMSC. The backend also contains a `run_smsc_sender` management command for
   deployments or operations that use the in-process sender worker.
6. Sent responses and delivery reports are processed by the separate status
   updater and DLR services, which update the shared database and campaign
   progress.
7. Airflow handles orchestration in the standard Compose stack. A standalone
   scheduler API is available under the `standalone-scheduler` Compose profile.

The backend exposes APIs for campaign start, pause, resume, stop/cancel,
activation, and send-now operations. Valid state transitions and readiness
requirements are enforced by the backend; a successful UI request alone does
not guarantee that a campaign is ready to send.

## Delivery receipt (DLR) flow

In the standard Docker Compose deployment, delivery receipts use a separate
receiver and Kafka consumer rather than being posted to the campaign API:

1. After accepting a submitted SMS, the SMSC sends a JSON callback to the DLR
   Receiver at `POST http://<receiver-host>:8003/api/v1/delivery-reports/callback/`.
   In the Compose network, the service hostname is `dlr_app`.
2. The receiver validates the callback and puts it in a bounded in-memory
   queue. It batches events and publishes them to Kafka topic
   `delivery-report`, keyed by the SMSC's message ID.
3. The `status_updater_app` consumes that topic using consumer group
   `status-updater-delivery`, matches the provider message ID against
   `SuccessSent` or `FailedSent`, and records each matched report as
   `SuccessDelivery` or `FailedDelivery` in the shared campaign database.
4. Campaign progress and reporting use those persisted delivery records. The
   original callback body and provider response are retained for investigation.

### Callback contract

The receiver expects a JSON object using the SMSC callback field names below.
`messageId`, `status`, and `msisdn` are required non-empty strings; `doneDate`
and `event` are optional.

```json
{
  "messageId": "11779274578648910",
  "msisdn": "251799120001",
  "status": "DELIVRD",
  "doneDate": "260928080404",
  "event": "Delivery receipt received"
}
```

The response acknowledges queue acceptance, not completion of database
processing:

```json
{
  "success": true,
  "accepted": true,
  "received_at": "2026-09-28T08:04:04.123Z"
}
```

| HTTP result | Meaning |
| --- | --- |
| `200` | Valid report accepted into the receiver's queue. |
| `400` | Invalid JSON, missing required fields, or invalid callback body. |
| `503` | Kafka is disconnected or the receiver queue is full; the SMSC should retry. |

Configure the SMSC callback destination to the receiver route above. For the
mock SMSC in Compose, `SMSC_MOCK_DLR_CALLBACK_URL` defaults to
`http://dlr_app:8003/api/v1/delivery-reports/callback/`. A real SMSC must be
able to reach the receiver through the deployment network or an appropriately
secured ingress. Do not expose the callback to untrusted networks without
network-level access controls; the receiver endpoint itself does not implement
callback authentication.

### DLR status mapping and persistence

Provider statuses are uppercased before mapping:

| SMSC status | Campaign status | Delivery code | Description |
| --- | --- | --- | --- |
| `DELIVRD` | `DELIVERED` | `000` | Delivered; persisted in `SuccessDelivery`. |
| `UNDELIV` | `UNDELIVERABLE` | `008` | Undeliverable; persisted in `FailedDelivery`. |
| `EXPIRED` | `EXPIRED` | `001` | Validity period expired; persisted in `FailedDelivery`. |
| `REJECTD` | `REJECTED` | `002` | Rejected; persisted in `FailedDelivery`. |
| Any other value | `UNKNOWN` | `999` | Unknown provider result; persisted in `FailedDelivery`. |

The receiver uses `messageId` to find the matching send record. Repeated
reports are deduplicated by message ID and provider message ID. If there is no
matching sent record, the status updater logs an orphan report and increments
its `orphan_delivery_reports` health counter; that unmatched report is not
persisted as a campaign delivery record. `doneDate` is parsed as a UTC
timestamp in `YYMMDDhhmmss` format; if it is absent or invalid, the report is
still recorded without a provider delivery timestamp.

### DLR configuration and operations

| Variable | Compose default | Service | Purpose |
| --- | --- | --- | --- |
| `DLR_RECEIVER_PORT` | `8003` | DLR Receiver | HTTP callback listener port. |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Receiver and status updater | Kafka broker address. |
| `KAFKA_DELIVERY_TOPIC` | `delivery-report` | Receiver and status updater | Topic used for DLR events. |
| `DLR_QUEUE_MAX` | `100000` | DLR Receiver | Maximum callback events held in memory before Kafka publish. |
| `DLR_BATCH_SIZE` | `100` | DLR Receiver | Maximum events in a Kafka publish batch. |
| `DLR_FLUSH_INTERVAL` | `0.05` seconds | DLR Receiver | Maximum batch-collection wait. |
| `DLR_MAX_RETRIES` | `5` | DLR Receiver | Kafka publish attempts per batch. |
| `DLR_RETRY_BACKOFF` | `2.0` seconds | DLR Receiver | Base exponential retry delay. |
| `DLR_KAFKA_STARTUP_TIMEOUT` | `300` seconds | DLR Receiver | Time allowed to establish the initial Kafka connection. |
| `KAFKA_DELIVERY_GROUP` | `status-updater-delivery` | Status updater | Consumer group that persists DLR events. |
| `KAFKA_BATCH_SIZE` | `1000` | Status updater | Maximum Kafka records handled in a consumer batch. |

Check `GET http://localhost:8003/health` for receiver Kafka connectivity, queue
depth, and received/published/failed/retrying counters. Check
`GET http://localhost:8010/health` for database and consumer status, the latest
delivery-consumer batch time, and the orphan DLR count. Investigate receiver
`failed_total`, a degraded status updater, or increasing orphan counts in the
service logs and metrics. The receiver queue is in memory: callback events
already acknowledged to the SMSC but not yet published to Kafka can be lost if
the receiver process terminates. Once a Kafka batch reaches the status updater,
database transaction errors are retried by seeking the batch for redelivery.

## API and documentation

With the local Compose defaults, the API base URL is
`http://localhost:8000/api/v1/`.

The schema and interactive API references are:

- `GET /api/v1/schema/` — OpenAPI schema
- `GET /api/v1/docs/` — Swagger UI
- `GET /api/v1/redoc/` — ReDoc UI

The API is grouped broadly into:

| API area | Example routes |
| --- | --- |
| Authentication and user management | `/auth/login/`, `/auth/refresh/`, `/auth/me/`, `/auth/password/`, `/auth/users/` |
| Dashboard and campaigns | `/dashboard/`, `/campaigns/`, `/campaigns/<id>/readiness/`, `/campaigns/<id>/start/` |
| Audiences | `/audiences/`, `/campaigns/<id>/audience/`, `/campaigns/<id>/audience/manual/`, `/campaigns/<id>/audience/file/`, `/campaigns/<id>/audience/database/` |
| Message content and schedules | `/message-content/`, `/campaigns/<id>/content/`, `/schedules/`, `/campaigns/<id>/schedule/` |
| Message and delivery status | `/campaigns/<id>/messages/`, `/campaigns/<id>/progress/`, `/campaigns/<id>/report-history/` |
| Platform configuration | `/databases/`, `/channels/`, `/sender-ids/`, `/smsc-configs/`, `/global-tps-config/`, `/n-addresses-config/` |
| Reporting and email | `/email-reports/`, `/report-subscriptions/`, `/report-delivery-logs/` |
| Test SMS | `/test-sms/`, `/test-sms/<id>/resend/` |

For exact methods, request/response schemas, and operation details, use the
generated schema or Swagger UI rather than relying on this high-level list.

## Authentication and endpoint permissions

JWT authentication is configured for the REST API. The login endpoint issues
an access and refresh token; send the access token on authenticated requests
as `Authorization: Bearer <token>`. The API also provides token refresh,
current-user, password-change, and initial-password-change endpoints.

Access is determined by each view. The project-wide DRF default permission is
`AllowAny`, while some views explicitly require an authenticated user or a
Django staff user. Do not assume every endpoint is protected merely because
JWT is configured; verify the specific endpoint's permission behavior in the
OpenAPI schema and implementation before exposing the service to untrusted
networks. The Admin Backend is a separate service with its own role and
configuration-assignment model.

## Access points

The default Docker Compose endpoints are:

- Campaign API: `http://localhost:8000/api/v1/`
- Swagger UI: `http://localhost:8000/api/v1/docs/`
- Django admin: `http://localhost:8000/admin/`
- PostgreSQL: internal Compose service `main_db`

The campaign UI is served separately at `http://localhost:3000`. It sends
campaign API requests to the same browser origin by default (proxied by
Nginx), while its Admin Backend configuration requests go to the admin
backend.

## Configuration

The backend reads these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Local development fallback | Django signing and cryptographic operations; provide a secret value in deployed environments. |
| `DJANGO_DEBUG` | `true` | Django debug mode. Disable in deployed environments. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated Django allowed host names. |
| `DB_ENGINE` | `sqlite` | Database engine; supported values are `sqlite` and `postgresql`. |
| `DB_NAME` | `campaign_manager` for PostgreSQL | Database name. |
| `DB_USER` | `campaign_manager` | PostgreSQL username. |
| `DB_PASSWORD` | Empty outside Compose | PostgreSQL password. |
| `DB_HOST` | `localhost` | PostgreSQL host. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `SMSC_SENDER_API` | `http://sms_sender_app:8001` | Base URL for the separate SMS sender service. |
| `FIELD_ENCRYPTION_KEY` | Local development fallback | Fernet key used for encrypted SMSC credentials. Keep consistent with the Admin Backend and store securely. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Django SMTP defaults | SMTP transport settings for notification/report email. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL` | TLS enabled, SSL disabled, example sender | SMTP security and sender settings. |
| `DJANGO_CAMPAIGN_LOG_LEVEL` | `INFO` | Log level for the `sms_campaign_manager` logger. |

When `DB_ENGINE=postgresql`, set the database connection variables and use the
same database for the campaign and admin backends. The SQLite development
database is `sms_campign/db.sqlite3`.

## Local development

From this directory, set a secure `DJANGO_SECRET_KEY` and
`FIELD_ENCRYPTION_KEY`, then run:

```powershell
python -m venv ..\venv
..\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 8000
```

Run the tests and checks with:

```powershell
python manage.py check
python manage.py test sms_campaign_manager
```

To build audiences using the background worker locally, run in a second
terminal:

```powershell
python manage.py run_audience_build_jobs
```

To run the built-in SMSC sender worker instead of the separate sender service:

```powershell
python manage.py run_smsc_sender
```

## Docker Compose

The Compose campaign backend applies migrations at startup and listens on
port `8000`. It waits for PostgreSQL to become healthy. The Compose
`audience-worker` is a separate process built from this same backend image.

Start the relevant services with:

```powershell
docker compose up --build -d main_db camaping_manager_backend_app admin_backend_app audience-worker
```

Use the root Compose file to start the full platform, including the sender,
status updater, DLR receiver, Kafka, and Airflow services. Configure all
deployment passwords, signing keys, encryption keys, hostnames, and SMTP
settings securely; Compose example defaults are for local development only.
