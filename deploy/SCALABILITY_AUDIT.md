# SMS platform reliability and scale audit

## Scope

This is a code and deployment-template review for the stated workload of up to
100 million messages and 2,000–4,000 SMS per second. It is not a load-test
result: recipient batching, SMSC latency, peak duration, delivery-receipt rate,
retention, recovery objectives, and provider idempotency still need to be
measured or agreed before sizing production infrastructure.

## Current application findings

| Application or area | Current design | Main scale or availability gap |
| --- | --- | --- |
| Campaign backend | Django API; owns campaigns, recipients, queue rows, configuration, and schedules. | Compose runs Django `runserver`; the API shares one PostgreSQL database and credentials with several services. |
| Admin backend | Separate Django API and UI for platform administration. | Uses the same database and credentials as the campaign backend. Shared tables make migration ownership and failure isolation unclear. |
| Campaign and admin UIs | Separate web applications. | The Kubernetes templates can run two replicas, but public routing, CDN, TLS, rollout policy, and final API origins depend on deployment configuration. |
| Audience worker | Builds recipient audiences from uploaded data. | Compose and the starter Kubernetes template use one worker. Uploads require shared durable storage before multiple replicas can safely consume them. |
| SMS sender | Claims rows with PostgreSQL `FOR UPDATE SKIP LOCKED`, sends HTTP batches to the SMSC, then publishes Kafka events. | Active campaigns are process-local, so a restart loses their registrations and multiple replicas can disagree. It updates message rows before Kafka publication; a Kafka outage between those operations can lose the corresponding status event. TPS allocation is process-local rather than a cluster-wide rate limit. |
| DLR receiver | Accepts provider callbacks and publishes DLR events to Kafka. | Previously it returned success after placing a callback only in a process-local queue. A process exit could therefore lose an acknowledged callback. This turn changes callback success to wait for a Kafka broker acknowledgement. |
| Status updater | Kafka consumers persist send and DLR events in database transactions, then commit offsets. | This gives replay on a database failure, but the current database write path and connection limits need load testing at target event rates. It depends on Kafka topic durability and enough partitions/consumer replicas. |
| Kafka | Compose runs a single combined broker/controller. Topics have 20 partitions but replication factor 1. | It has no broker redundancy; a broker or host failure takes out the event bus. Partition count alone does not provide availability. |
| PostgreSQL | One PostgreSQL 16 container, one shared application database, one shared user, local volume. | It is a single failure point and all applications compete for the same connection and write capacity. The project has already observed `too many clients`. |
| Airflow | Webserver and one scheduler using `LocalExecutor`; Airflow metadata is in the shared application database. | A single scheduler and shared metadata database are not an HA deployment. Airflow should schedule/coordinate campaigns, not carry per-message send traffic. |
| Mock SMSC | Local FastAPI mock with SQLite and a persistent local volume. | Development/testing only; do not use as a production dependency. |
| Kubernetes templates | Starter manifests cover the two APIs, two UIs, and one audience worker. | They explicitly omit PostgreSQL, Kafka, sender, DLR, status updater, Airflow, and their services/health checks. They are not yet a complete production release. |

## Work order

### 1. Delivery correctness before increasing replicas

- Add a transactional outbox for sender results so a sent message state and its
  Kafka event cannot be separated by a crash. A background publisher should
  retry unsent outbox rows and mark them delivered only after Kafka confirms.
- Move campaign execution leases and global/per-SMSC TPS coordination out of
  sender process memory. Use database leases or a durable dispatch queue with
  fencing so restart and horizontal scaling cannot start duplicate work.
- Define behavior for an SMSC timeout after it may have accepted a request.
  Use provider idempotency keys if supported; otherwise retain an explicit
  uncertain state and reconcile instead of blindly resending.
- Keep DLR callback success tied to durable Kafka acknowledgement, as updated
  in this change. Add provider authentication/signature validation or an
  approved network allowlist before exposing the callback publicly.

### 2. Separate application ownership and protect the data path

- Use separate database users with least-privilege grants immediately. Keep
  Airflow metadata in its own database. Keep campaign tables owned by the
  campaign service; admin and worker services should use explicit API/event
  contracts or restricted table grants.
- Move PostgreSQL to a managed HA deployment (or a deliberately operated
  primary/standby setup) with automated failover, connection pooling, backups,
  point-in-time recovery, and tested restore procedures.
- Benchmark recipient queue claims, message-state updates, status history, and
  reports at the target rate. Add appropriate indexes and time-based
  partitioning for high-volume message/history tables based on measured query
  patterns; define retention and archival first.
- Use a replicated Kafka cluster across failure zones. For critical topics,
  configure replication factor 3, `min.insync.replicas=2`, and producers with
  `acks=all`; monitor under-replicated partitions and consumer lag.

### 3. Deploy every component as a managed workload

- Use a multi-zone Kubernetes or equivalent orchestrator for stateless APIs,
  sender workers, DLR receiver, status consumers, audience workers, UIs, and
  Airflow components. Set readiness/liveness probes, disruption budgets,
  resource requests/limits, autoscaling rules, and rolling deployment policy.
- Keep UI delivery behind TLS ingress and a CDN or equivalent. Keep internal
  sender, database, Kafka, and Airflow endpoints private; store secrets in the
  platform secret manager.
- Add metrics, dashboards, alerts, centralized logs, trace/correlation IDs,
  queue-age and Kafka-lag alerts, DB saturation alarms, and a documented
  failover/restore exercise.
- Use Airflow for schedule orchestration and campaign-level coordination. A
  durable queue and horizontally scaled workers should handle message-level
  delivery.

## Release gates

Do not call the service production-ready for the stated rate until a staging
environment demonstrates the target send and DLR rates with realistic SMSC
latency, verifies no lost or duplicated status events under process/broker/DB
failures, and records recovery time, data-loss bounds, database headroom, and
consumer lag. Exact replica counts and database sizing must come from those
measurements and the selected hosting platform.
