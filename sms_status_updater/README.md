# SMS Status Updater

The `sms_status_updater` service consumes SMS submission responses and delivery
reports from Kafka and writes the resulting message history to the campaign
backend's database. It keeps the campaign message queue and permanent send and
delivery history in sync. It is a background consumer and health API, not an
SMSC callback receiver or a user-facing campaign API.

## Technology

- Python 3.12
- FastAPI and Uvicorn for the health endpoints and asynchronous service
  lifecycle
- aiokafka for Kafka consumers
- Django ORM for campaign database models and transactions
- PostgreSQL in Docker Compose; the campaign backend's configured SQLite
  database can be used for local development

## Processing flow

The service starts two Kafka consumers at startup. Both use manual offset
commits, so a Kafka batch is acknowledged only after its database handler
completes successfully.

### SMS send responses

The send consumer reads `SENT_RESPONSE` events from `sent-response` using the
`status-updater-send` consumer group. Each event identifies the message,
campaign, channel, recipient, sender, and the sender's accepted/failed result.
The updater:

1. Validates and groups events by message ID.
2. Writes accepted messages to `SuccessSent` and rejected/failed messages to
   `FailedSent`, including provider response and attempt details.
3. Removes the matching queued `MessageObject` rows in the same database
   transaction.

Existing history rows are not duplicated when a message event is replayed.
Invalid event fields and references are logged and skipped.

### Delivery receipts (DLRs)

The delivery consumer reads `DELIVERY_REPORT` events from `delivery-report`
using the `status-updater-delivery` consumer group. The HTTP callback is handled
by the separate [`dlr_receiver`](../dlr_receiver/) service; the normal DLR path
is:

`SMSC callback -> DLR Receiver -> Kafka delivery-report -> Status Updater -> campaign database`

The updater matches `provider_message_id` against `SuccessSent` or
`FailedSent`, then stores successful `DELIVRD` reports in `SuccessDelivery` and
all other statuses in `FailedDelivery`. It retains the event and original
callback payload for troubleshooting. Existing message/provider ID pairs are
deduplicated.

| SMSC status | Stored delivery status | Code | Description |
| --- | --- | --- | --- |
| `DELIVRD` | `DELIVERED` | `000` | Delivered |
| `UNDELIV` | `UNDELIVERABLE` | `008` | Undeliverable |
| `EXPIRED` | `EXPIRED` | `001` | Validity period expired |
| `REJECTD` | `REJECTED` | `002` | Rejected |
| Any other status | `UNKNOWN` | `999` | Unknown |

`doneDate` is interpreted as UTC in `YYMMDDhhmmss` format. Missing or invalid
dates do not prevent the report from being saved, but leave its delivery or
failure timestamp empty. Reports without a matching send-history provider ID
are logged and counted as orphans; they are not saved as campaign deliveries.
The consumer commits the batch after this handler completes, so an orphan is
not automatically retried.

## API and access points

The service exposes monitoring endpoints only:

| Method and path | Purpose |
| --- | --- |
| `GET /` | Service name and health endpoint path. |
| `GET /health` | Database, Kafka-consumer, processing-count, and orphan-report status. |

With Docker Compose, the service is reachable at
`http://localhost:8010/health`. A healthy response includes database and Kafka
connectivity, pending and persisted message counts, each consumer's topic,
group, running state, totals, last processed batch time, and the number of
orphan DLRs. The endpoint reports a degraded state if the database is
unavailable or either consumer has an error.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_ENGINE` | `sqlite` in the campaign Django settings; Compose sets `postgresql` | Database engine used by the Django ORM. |
| `DB_NAME` | `campaign_manager` | PostgreSQL database name. |
| `DB_USER` | `campaign_manager` | PostgreSQL username. |
| `DB_PASSWORD` | Empty in Django settings | PostgreSQL password. |
| `DB_HOST` | `localhost` | PostgreSQL hostname. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `DJANGO_SECRET_KEY` | Campaign backend development fallback | Django setting required to initialize campaign models. Set securely in deployed environments. |
| `KAFKA_BOOTSTRAP` | `kafka:9092` | Kafka broker address. |
| `KAFKA_SENT_TOPIC` | `sent-response` | Topic containing SMS submission outcomes. |
| `KAFKA_DELIVERY_TOPIC` | `delivery-report` | Topic containing SMS delivery reports. |
| `KAFKA_SEND_GROUP` | `status-updater-send` | Consumer group for SMS submission outcomes. |
| `KAFKA_DELIVERY_GROUP` | `status-updater-delivery` | Consumer group for delivery reports. |
| `KAFKA_BATCH_SIZE` | `1000` | Maximum records polled per consumer batch. |
| `KAFKA_POLL_INTERVAL_MS` | `1000` | Maximum wait for Kafka records per poll. |
| `KAFKA_STARTUP_TIMEOUT_SECONDS` | `300` | Time allowed to connect both consumers during startup. |

Configure the updater to use the same database as the campaign backend. In the
standard Compose deployment, the service receives its PostgreSQL connection
details and Kafka topics from the root `docker-compose.yml`.

## Run and operate

From the repository root, start the service with its Compose dependencies:

```powershell
docker compose up --build -d status_updater_app
```

Inspect its health and logs with:

```powershell
Invoke-RestMethod http://localhost:8010/health
docker compose logs -f status_updater_app
```

On a database-batch failure, the consumer does not commit the offsets; it seeks
back to the batch and retries after a short delay. Database writes run in
transactions and are designed to tolerate replay. The consumer startup fails
if it cannot initialize the database or connect to Kafka within the configured
startup timeout.

The DLR receiver acknowledges a callback when it enters its own in-memory
queue, before Kafka publication and database persistence. For the end-to-end
callback contract, queue limits, and receiver retry behavior, see the
campaign backend's [DLR documentation](../sms_campign/README.md#delivery-receipt-dlr-flow).
