# SMS Sender Service

The `sms_smsc_sender` application is the platform's asynchronous SMS delivery
service. It is a FastAPI application that claims queued campaign messages from
the shared PostgreSQL database, applies the configured TPS and request-size
limits, submits requests to the configured SMSC, updates message state, and
publishes send-result events to Kafka.

The sender is separate from the Django campaign backend, the Airflow
orchestrator, the Kafka status updater, and the DLR receiver. It does not
decide when a campaign schedule is due.

## Technology

- Python 3.11
- FastAPI and Uvicorn
- `psycopg` async connection pool for PostgreSQL access
- `httpx` async HTTP client for SMSC and campaign API requests
- `aiokafka` producer for send-result events
- `cryptography` Fernet for decrypting encrypted SMSC credentials
- Pydantic request validation

## How message delivery works

1. The sender service connects to PostgreSQL, the campaign API, and Kafka at
   application startup.
2. When the sender worker is enabled, it runs a delivery tick at the configured
   interval.
3. Each tick loads the active global TPS configuration, maximum addresses per
   request, active SMSC configuration, and channel codes.
4. For each campaign currently registered as active in this sender process,
   the service allocates the global TPS across active campaign IDs, capped by
   the SMSC's configured per-second rate limit.
5. It claims pending or retryable failed messages for that campaign's current
   round using PostgreSQL row locks (`FOR UPDATE SKIP LOCKED`) and a lock
   expiry. Messages are grouped by language and identical message content,
   then split into requests that do not exceed the configured maximum number
   of addresses per request.
6. The sender builds the SMSC payload, applies the configured authentication
   method and request headers, and submits the request asynchronously.
7. An accepted SMSC response marks the message `SENT` and releases its lock.
   Failed submissions are marked `FAILED`, their attempt count is incremented,
   and they remain retryable until the SMSC's configured `max_retries` is
   reached.
8. Accepted sends and terminal failures are published to the Kafka
   `sent-response` topic. The status updater consumes these events and writes
   send records and campaign status information to the shared database.
   Delivery receipts are handled separately by the DLR receiver and
   `delivery-report` Kafka topic.

TPS distribution is deterministic by sorted campaign ID. For example, a
global limit of 4,000 TPS shared by three active campaigns is allocated as
1,334, 1,333, and 1,333 TPS, then capped at the active SMSC's own rate limit.
The sender also limits each HTTP request to the configured maximum addresses.

## API

The service listens on port `8001` in Docker Compose. FastAPI's interactive
API documentation is at `http://localhost:8001/docs`, with the OpenAPI schema
at `http://localhost:8001/openapi.json`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Checks database/config availability and reports worker state, active campaign IDs, active TPS/request-size/SMSC configuration, Kafka connectivity, and the last tick result. Returns `503` when required DB/config loading fails. |
| `POST` | `/sender/start` | Activates and starts a campaign round in this sender process. JSON body: `{"campaign_id": 123, "round_number": 1}`. Returns `202` on start and `409` if already running. |
| `POST` | `/sender/stop` | Stops a running campaign by pausing it through the campaign API and unregistering it from this process. Body accepts `campaign_id`, `round_number`, and optional `reason`. |
| `GET` | `/sender/status` | Returns active campaigns, current rounds, pending counts, and TPS allocations. |
| `GET` | `/sender/status/{campaign_id}` | Returns a campaign's active state, pending count, and allocation if active. |
| `POST` | `/run-once` | Runs one delivery tick and returns its per-campaign reports. |

`/sender/start` and `/sender/stop` are used by the Airflow campaign dispatcher.
The service currently does not expose `/worker/start` or `/worker/stop`
endpoints; the background worker is controlled by `SMSC_SENDER_RUN_WORKER` and
starts automatically by default.

These endpoints do not implement application-level authentication in this
service. Keep the API on a trusted private network and do not expose it
directly to untrusted clients.

## Configuration

Environment variables read by the application:

| Variable | Application default | Purpose |
| --- | --- | --- |
| `DB_HOST` | `main_db` | PostgreSQL host. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `DB_NAME` | `campaign_db` | Shared campaign database name. |
| `DB_USER` | `postgres` | PostgreSQL user. |
| `DB_PASSWORD` | Empty | PostgreSQL password. |
| `SMSC_SENDER_DJANGO_API` | `http://camaping-manager-backend-app:8000/api/v1` | Campaign API base URL used for active TPS/N-address configuration and campaign state actions. |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Kafka bootstrap server. |
| `KAFKA_SENT_TOPIC` | `sent-response` | Topic for accepted sends and terminal send failures. |
| `SMSC_SENDER_SCHEDULER_INTERVAL` | `1` second | Delivery worker tick interval. |
| `SMSC_SENDER_WORKERS` | `100` | Maximum concurrent outbound SMSC HTTP requests. |
| `LOCK_TIMEOUT_SECONDS` | `300` | Duration for which claimed messages are locked before they may be reclaimed. |
| `SMSC_SENDER_RUN_WORKER` | `true` | Start the continuous background worker automatically at application startup. |
| `FIELD_ENCRYPTION_KEY` | Empty | Fernet key used to decrypt encrypted SMSC credentials read from the campaign database. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

The active global TPS, N-address request limit, and SMSC settings are loaded
from the campaign backend/database configuration rather than configured
separately in this service. The SMSC encryption key must match the key used to
encrypt those credentials in the campaign and admin backends.

In the standard Compose configuration, database credentials come from
`POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`; the sender connects to
`main_db`, `kafka:9092`, and the campaign API. Compose enables the continuous
worker with `SMSC_SENDER_RUN_WORKER=true`.

## Local development

The sender requires a PostgreSQL database with the campaign manager schema,
the campaign API, and a Kafka broker. SQLite is not supported by this current
sender implementation.

From the repository root, start the platform dependencies and sender:

```powershell
docker compose up --build -d main_db kafka kafka-init camaping_manager_backend_app sms_sender_app
```

Check the service health endpoint:

```powershell
Invoke-RestMethod http://localhost:8001/health
```

To run the service directly instead of using Compose, install dependencies
from this directory, set the database, campaign API, Kafka, and encryption
environment variables, then run one Uvicorn worker:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn sms_smsc_sender.app:app --host 127.0.0.1 --port 8001 --workers 1
```

Use one Uvicorn worker per sender instance. Active campaigns are tracked in
process memory, so multiple web workers do not share the same active-campaign
registry. PostgreSQL message locks protect message claims, but they do not
replicate that in-memory registry between API worker processes.

## Compose and related services

The root Compose service is named `sms_sender_app`. It builds this directory's
Dockerfile, publishes host port `8001` by default, waits for PostgreSQL, the
campaign backend, and Kafka topic initialization, and restarts unless stopped.
The Docker image health check calls `GET /health`.

Related services:

- **Campaign backend:** owns campaigns, message rows, and active SMSC/TPS/
  request-size configuration.
- **Airflow:** calls `/sender/start`, `/sender/stop`, and `/sender/status` to
  coordinate due campaign rounds.
- **Status updater:** consumes the sender's `sent-response` events and records
  send outcomes.
- **DLR receiver:** accepts provider delivery callbacks and publishes delivery
  events for the status updater.

## Tests

Run the sender's unit and API tests from the repository root:

```powershell
python -m unittest sms_smsc_sender.test_app
```

The tests cover TPS allocation, message chunking, SMSC request formatting and
authentication, sender endpoints, and empty active-campaign status.
