# SMS Campaign Manager Design

## 1. Purpose

The application manages large SMS campaigns from campaign setup through delivery:

1. Configure a campaign.
2. Build an audience from a database, file, or manual list.
3. Generate one message object per valid recipient.
4. Submit messages to an SMSC with rate limiting and retries.
5. Store send attempts and provider IDs.
6. Receive delivery reports and update delivery status.

The system is designed for large audiences, including the validated 500,000-recipient PostgreSQL flow, and is being prepared for Kafka-based streaming at high throughput.

## 2. Current components

```text
Client/UI
   |
   v
Django REST API
   |
   +--> PostgreSQL
   |       +--> Campaign
   |       +--> Audience
   |       +--> MessageObject
   |       +--> SentRecord
   |       +--> DeliveryRecord
   |       +--> KafkaOutboxEvent
   |
   +--> Audience builder
   +--> Message builder
   +--> Campaign scheduler
   |
   v
SMS sender service
   |
   v
SMSC API / local SMSC mock
   |
   v
Delivery report callback
```

Main backend:

- [sms_campign/sms_campaign_manager/models.py](./sms_campign/sms_campaign_manager/models.py)
- [sms_campign/sms_campaign_manager/views.py](./sms_campign/sms_campaign_manager/views.py)
- [sms_campign/sms_campaign_manager/serializers.py](./sms_campign/sms_campaign_manager/serializers.py)
- [sms_campign/sms_campaign_manager/urls.py](./sms_campign/sms_campaign_manager/urls.py)

Supporting services:

- [sms_smsc_sender/app.py](./sms_smsc_sender/app.py)
- [sms_smsc_mock/app.py](./sms_smsc_mock/app.py)

## 3. Domain model

### Campaign

Stores campaign identity, sender ID, channels, lifecycle status, ownership, and soft-delete state.

Typical states:

```text
draft -> active -> paused -> active -> completed
draft -> cancelled
active -> cancelled
```

### Audience

One normalized recipient per row:

- Campaign
- MSISDN
- Language
- Source type
- Validation status
- Sequence number
- Optional custom fields

The database audience builder reads source records in batches and inserts normalized audience rows in batches.

### MessageObject

One outbound SMS payload per recipient:

- Unique message ID
- Campaign
- Recipient
- Sender ID
- Message content
- Language
- Batch ID
- Send status
- Delivery status
- Retry counters

Message objects are queue records and can be deleted after accepted submission because `SentRecord` retains send history.

### SentRecord

Append-only submission history:

- Campaign and channel
- Message object reference
- Recipient
- Provider message ID
- Provider response
- Accepted or failed status
- Error information

The sender persists a window using `bulk_create`, `bulk_update`, and bulk deletion.

### DeliveryRecord

Append-only or idempotently updated provider delivery history:

- Provider message ID through `sent_record`
- Provider status
- Application delivery status
- Delivery timestamp
- Provider response

Provider statuses are mapped as follows:

```text
DELIVRD -> DELIVERED
UNDELIV -> UNDELIVERABLE
EXPIRED -> EXPIRED
REJECTD -> REJECTED
```

## 4. Current message flow

### Campaign setup

```text
POST /campaigns/
POST /campaigns/{id}/audience/database/
POST /audience-configs/{id}/build/
POST /campaigns/{id}/content/
POST /campaigns/{id}/schedule/
POST /campaigns/{id}/validate/
POST /campaigns/{id}/activate/
```

### Audience build

The database audience path:

1. Opens the configured source database.
2. Executes the configured source query.
3. Reads rows using bounded fetches.
4. Normalizes MSISDN values.
5. Resolves language from source, mapper, or default.
6. Bulk inserts `Audience` rows.
7. Updates aggregate build statistics.

The implementation avoids materializing the entire external source in Python memory.

### Message build

The message builder:

1. Deletes the existing queue rows for the campaign.
2. Streams valid audience rows using a Django iterator.
3. Personalizes message templates.
4. Calculates SMS segment count.
5. Inserts message objects in chunks.
6. Returns build statistics.

The current rebuild is synchronous. For very large campaigns, the HTTP request should eventually become an asynchronous job.

### SMS submission

The sender:

1. Finds pending/failed messages.
2. Allocates SMSC capacity fairly among campaigns.
3. Sends messages concurrently to the SMSC.
4. Collects outcomes.
5. Persists the complete window in one database transaction.

The persistence transaction:

```text
bulk_create SentRecord rows
bulk_update retryable MessageObject rows
bulk_delete accepted/exhausted MessageObject rows
```

### Delivery reports

When Kafka is disabled, the callback processes the report synchronously.

When asynchronous database inbox mode is enabled, the callback places the payload in `DeliveryReportInbox`, and `process_delivery_reports` drains it.

The callback path is:

```text
SMSC -> POST /api/v1/delivery-reports/callback/
     -> map provider status
     -> create/update DeliveryRecord
     -> update MessageObject delivery status when linked
```

## 5. Current scale characteristics

Validated:

- PostgreSQL audience build and message rebuild for 500,000 recipients.
- Full campaign setup flow.
- SMS submission window.
- Sent report creation.
- Delivery report processing.
- Batched sender persistence.

The 500,000-recipient test completed successfully in approximately 17 minutes 38 seconds in the local PostgreSQL environment.

This validates functional throughput and bounded-memory processing for the tested workload. It does not yet validate sustained 5,000 TPS for 30–60 minutes.

Current scale risks:

- Message rebuild is synchronous.
- Direct sender HTTP submission is process-local.
- DLR processing is not yet a full Kafka streaming path.
- SQLite is unsuitable for production throughput.
- PostgreSQL indexes and table retention need production sizing.
- Authentication and API permissions still require hardening.

## 6. Kafka target architecture

Kafka should be the streaming transport, not the system of record. PostgreSQL remains authoritative.

```text
Message builder
   |
   v
KafkaOutboxEvent
   |
   v
Outbox publisher
   |
   v
Kafka: message.created
   |
   v
SMS sender consumer
   |
   +--> SMSC
   |
   v
Kafka: sent.report.received
   |
   v
Sent-report consumer
   |
   v
PostgreSQL bulk persistence

SMSC DLR webhook
   |
   v
KafkaOutboxEvent
   |
   v
Kafka: delivery.report.received
   |
   v
DLR consumer
   |
   v
PostgreSQL bulk persistence
```

Current Kafka-related code:

- [sms_campign/sms_campaign_manager/kafka.py](./sms_campign/sms_campaign_manager/kafka.py)
- [sms_campign/sms_campaign_manager/management/commands/publish_outbox.py](./sms_campign/sms_campaign_manager/management/commands/publish_outbox.py)
- [sms_campign/sms_campaign_manager/management/commands/consume_dlr_events.py](./sms_campign/sms_campaign_manager/management/commands/consume_dlr_events.py)
- [docker-compose.yml](./docker-compose.yml)
- [KAFKA.md](./KAFKA.md)

Configured topics include:

```text
message.created
delivery.report.received
sent.report.received
sms.dlq
```

## 7. Kafka work remaining

The following work is still required before calling the Kafka path production-ready:

1. Run the real producer and consumer against Redpanda/Kafka.
2. Add automated topic creation with production partition counts.
3. Replace per-event producer flushes with true batch publishing.
4. Add `select_for_update(skip_locked=True)` to outbox publishing.
5. Add producer delivery callbacks and durable failure handling.
6. Add a complete sent-report Kafka consumer.
7. Process DLR events in batches rather than one event per transaction.
8. Commit Kafka offsets only after PostgreSQL transactions succeed.
9. Add event IDs and database uniqueness constraints for replay safety.
10. Add retry topics with delayed retry policy.
11. Add dead-letter event payloads containing original topic, partition, offset, and error.
12. Add distributed SMSC rate limiting for multiple sender workers.
13. Add consumer lag, producer errors, retry counts, and DLQ metrics.
14. Run sustained 5,000 TPS load tests.
15. Add failure-recovery tests for broker, database, and SMSC outages.

## 8. Work that can be completed before Kafka is available

### A. Harden the database path

- Run PostgreSQL migrations and verify indexes.
- Measure query plans for audience, message, sent, and delivery tables.
- Add database constraints for provider message IDs and event idempotency.
- Configure connection pooling.
- Add retention and archival policies.
- Test PostgreSQL backup and restore.

### B. Complete functional testing

- Test duplicate callbacks.
- Test out-of-order delivery statuses.
- Test SMSC timeouts and HTTP 429 throttling.
- Test retry exhaustion.
- Test partial sender-window failures.
- Test message rebuild while a campaign is active.
- Test campaign pause/resume during sending.

### C. Benchmark the direct path

Run progressively:

```text
10,000 messages
100,000 messages
500,000 messages
1,000,000 messages
5,000 submissions/second for 5 minutes
5,000 submissions/second for 30 minutes
```

Collect:

- Submission TPS
- SMSC latency p50/p95/p99
- PostgreSQL transaction latency
- CPU and memory
- Failed and retried messages
- Delivery-report delay
- Remaining queue depth

### D. Prepare operational tooling

- Add structured JSON logging.
- Add health/readiness endpoints.
- Add Prometheus metrics.
- Add dashboards and alerts.
- Add correlation IDs to campaign, batch, message, and provider events.
- Add graceful shutdown for sender and consumer processes.

### E. Harden security

Before production:

- Set `DEBUG=False`.
- Move `SECRET_KEY` to a secret manager.
- Configure `ALLOWED_HOSTS`.
- Replace `AllowAny` with authenticated permissions.
- Authenticate DLR callbacks with HMAC or provider credentials.
- Rotate SMSC and database credentials.
- Use TLS for API, database, and Kafka connections.

### F. Validate Docker locally

The current Compose setup contains PostgreSQL, Redpanda, Django, the outbox publisher, sender, and DLR consumer.

Before using it as production deployment:

- Add health checks.
- Make migrations an explicit startup job.
- Separate development and production Compose files.
- Use secrets instead of inline passwords.
- Configure persistent Kafka storage.
- Configure Kafka partitions and retention.
- Add restart policies.
- Add resource limits.

## 9. Environment modes

### Direct mode

```text
KAFKA_ENABLED=false
```

Use this mode for current functional tests and direct SMSC integration.

### Kafka mode

```text
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

Use this only after the broker is running and migrations have been applied.

## 10. Definition of production readiness

The application should not be considered enterprise-ready until it can demonstrate:

- 5,000 TPS sustained submission under realistic SMSC latency.
- No message loss during process, database, or broker restarts.
- Replay-safe sent and delivery report processing.
- Bounded Kafka consumer lag.
- Zero uncontrolled DLQ growth.
- Horizontal sender scaling with a shared rate limiter.
- PostgreSQL bulk persistence without lock contention.
- Monitoring and alerting for all critical queues.
- Authenticated APIs and DLR callbacks.
- Successful backup, restore, and disaster-recovery tests.
