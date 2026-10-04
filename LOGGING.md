# SMS Platform Logging

This document describes application logging as implemented in the repository.
It distinguishes operational logs from database audit/history records and
identifies where each application sends its output.

## Summary

Backend and worker services write logs to standard output and standard error;
Docker Compose users can read container output with `docker compose logs`.
Airflow writes DAG messages to its task logs. Browser-side UI errors are sent to
the browser developer console, not automatically forwarded to the backend.

Logging is implemented across the server applications, but event coverage is
not uniform. Some services log key failures and lifecycle events rather than
every request or message. There is no repository-wide log collector, shared
structured log schema, or automatic frontend-to-backend log forwarding.

## Primary services

The following are the six services requested for this combined guide.

| Application | Logging implementation | Output and coverage |
| --- | --- | --- |
| Admin Backend (`admin_backend`) | Django `LOGGING` config with timestamp, severity, logger name, and message. `admin_control` level is controlled by `ADMIN_BACKEND_LOG_LEVEL` (default `INFO`); Django request/security warnings are enabled. | Console output. Current application-level logs primarily cover email delivery and SMTP test failures; this is not a complete user-action or API audit trail. |
| Campaign Backend (`sms_campign`) | Django `LOGGING` config with timestamp, severity, logger name, and message; level controlled by `DJANGO_CAMPAIGN_LOG_LEVEL` (default `INFO`). | Console output. Campaign, audience-build, message-build, notification, and schedule paths emit selected lifecycle and error logs. |
| Airflow (`airflow`) | DAG modules use Python loggers; Airflow configures task logging. | Airflow task logs. Dispatch outcomes and campaign/report failures are logged with task context. |
| SMS Sender (`sms_smsc_sender`) | Named Python logger, configured with `LOG_LEVEL` (default `INFO`). | Container console. Current explicit messages focus on sender worker exceptions and Kafka send-response publication errors. |
| DLR Receiver (`dlr_receiver`) | Named Python logger, configured with `LOG_LEVEL` (default `INFO`). | Container console. Logs Kafka connection, retry, and publish failures. Health output separately exposes queue and publish counters. |
| Status Updater (`sms_status_updater`) | Named Python logger; Uvicorn configures the process logging pipeline. | Container console. Logs malformed events, orphan DLRs, Kafka connection/poll/batch errors, and database health errors. |

## Other application logging

These components also have logging or error output, but are not part of the
six-service documentation scope above.

| Application | Logging implementation | Output and coverage |
| --- | --- | --- |
| SMSC Mock (`sms_smsc_mock`) | Named Python logger, configured with `SMSC_MOCK_LOG_LEVEL` (default `INFO`). | Container console. Logs DLR callback failures and exhausted retries, and write-batch failures. |
| Campaign Scheduler (`sms_campaign_scheduler`) | Named Python logger. Uvicorn provides the console logging pipeline. | Console/container output. Logs worker lifecycle, per-campaign schedule errors, worker exceptions, and cycle summaries. |
| Admin UI (`admin-ui`) | Server-side errors are expanded and written with `console.error`; global errors and unhandled rejections are captured for SSR error reporting. | Server process console for server-side errors; browser console for client-side errors. Its “System Logs” page currently displays static sample activity rows; it is not connected to the Admin Backend audit-log endpoint. It does not forward general browser logs to a central service. |
| Campaign UI (`sms_ui`) | Selected UI failures use `console.error`; user-facing notifications are also shown in the interface. | Browser developer console only. Logging is selective and there is no shared frontend logging/telemetry endpoint. |

“Logging implemented” means an application has a path for writing operational
messages. It does not mean every request, business decision, or success event
is logged.

## Configuration and access

| Variable | Application | Default |
| --- | --- | --- |
| `DJANGO_CAMPAIGN_LOG_LEVEL` | Campaign Backend | `INFO` |
| `ADMIN_BACKEND_LOG_LEVEL` | Admin Backend | `INFO` |
| `LOG_LEVEL` | SMS Sender and DLR Receiver | `INFO` |
| `SMSC_MOCK_LOG_LEVEL` | SMSC Mock | `INFO` |

The Status Updater and standalone Campaign Scheduler use Uvicorn's process
logging configuration and do not currently define a separate application log
level variable. Airflow task-log behavior is controlled by Airflow deployment
configuration.

For container logs:

```powershell
docker compose logs --follow camaping_manager_backend_app admin_backend_app
docker compose logs --follow sms_sender_app dlr_app status_updater_app
docker compose logs --follow mock_app
docker compose --profile standalone-scheduler logs --follow standalone_scheduler_api
```

Use Airflow's task-log interface for DAG output. Use browser developer tools
for UI console messages. Container logs are not persisted by this repository
configuration; persistence, retention, alerting, and cross-service search must
be configured in the deployment's container logging driver or external
observability platform.

## Logging versus audit and message history

Application logs are diagnostic text streams. They are not substitutes for:

- Admin Backend login-attempt records and `AdminAuditLog` database entries.
- SMS sender/provider submission history.
- Campaign `SuccessSent` / `FailedSent` and `SuccessDelivery` /
  `FailedDelivery` records.
- Airflow task state and run history.

The Admin Backend exposes persisted audit records at
`GET /api/v1/admin/audit-log/` and login-attempt records at
`GET /api/v1/admin/login-attempts/` to platform administrators. These endpoints
are separate from the static sample rows currently shown in the Admin UI's
“System Logs” page. Use the relevant application database or Airflow metadata
UI when a durable, queryable activity record is required.

## Operational and privacy guidance

- Keep logs access-controlled and configure an explicit retention policy.
- Do not log passwords, access/refresh tokens, encryption keys, SMTP
  credentials, or full authorization headers.
- Treat phone numbers, provider message IDs, campaign IDs, and exception
  details as potentially sensitive operational data.
- Prefer stable IDs, status codes, and counts over full message bodies or raw
  provider payloads. Review any event-level exception logging before sending
  logs to a third-party observability service.
- Configure centralized collection and alerting for repeated worker failures,
  Kafka disconnections, DLR publish failures/orphans, and elevated API errors;
  these integrations are deployment responsibilities and are not configured
  centrally in this repository.
