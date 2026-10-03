# Mock Onion SMSC

The mock implements the real SMSC's HTTP contract for local development. It accepts authenticated batches, returns one result per destination, and sends an asynchronous HTTP delivery receipt for each message. It does not publish to Kafka.

## Service

| Property | Value |
|---|---|
| Compose service | `mock_app` |
| Container | `mock_app` |
| Port | `8090` |
| Internal URL | `http://mock_app:8090` |
| Network | `sms-network` |
| Runtime | Python 3.11, FastAPI, Uvicorn (4 workers) |

## Submit Messages

`POST /onion/swift/duos` requires HTTP Basic authentication and `Content-Type: application/json`.

```json
{
  "shortMessage": "Hello Alice, our offer is live!",
  "messageType": "TEXT",
  "destAddr": [
    { "id": "251799120001" },
    { "id": "251799120002" }
  ],
  "sourceAddr": { "name": "SMSINFO" },
  "servicetag": { "name": "camp-5" },
  "servicetype": { "name": "normal" }
}
```

`shortMessage` and `sourceAddr.name` are required. `messageType` is `TEXT` or `BIN`, defaulting to `TEXT`. `destAddr` contains 1–10,000 objects; every `id` must contain 7–20 digits without a plus sign. `servicetag` and `servicetype` are optional objects with a `name` value. Unicode message text is accepted.

Success returns HTTP 200 and an array in request order:

```json
[
  { "messageId": "11779274578648910", "msisdn": "251799120001", "status": "submitted" },
  { "messageId": "11779274578648911", "msisdn": "251799120002", "status": "submitted" }
]
```

Message IDs are numeric strings composed of the current millisecond timestamp and a six-digit random suffix. Invalid JSON or request fields return 400. Missing, malformed, or incorrect Basic credentials return 401. A depleted global token bucket returns 503 with `{"error":"Service Unavailable","message":"Rate limit exceeded. Retry shortly."}`.

Set both `SMSC_MOCK_USERNAME` and `SMSC_MOCK_PASSWORD` to enforce exact credentials. If either is empty, any syntactically valid Basic header with non-empty credentials is accepted. Bearer authentication is not supported.

## Delivery Receipts

After a random delay, each destination independently receives a weighted outcome: `DELIVRD` (0.92), `UNDELIV` (0.04), `EXPIRED` (0.02), or `REJECTD` (0.02). The mock POSTs this JSON to the fixed `SMSC_MOCK_DLR_CALLBACK_URL`:

```json
{
  "event": "Delivery receipt received",
  "msisdn": "251799120001",
  "messageId": "11779274578648910",
  "status": "DELIVRD",
  "doneDate": "260928080404"
}
```

`doneDate` is a UTC `YYMMDDhhmmss` timestamp. Only HTTP 200 is considered successful. Other responses and network errors are retried up to `SMSC_MOCK_DLR_RETRIES` times, waiting `SMSC_MOCK_DLR_RETRY_BACKOFF × attempt_number` seconds between attempts. Exhausted failures are logged and recorded.

## Inspect State

`GET /api/messages/{messageId}` returns 404 for unknown IDs, or the stored message and DLR state. `GET /health` returns service status, write queue depth, accepted and delivered totals, pending DLR tasks, available TPS tokens, and the configured callback URL.

## Storage and Throughput

SQLite stores message rows in `/data/smsc_mock.sqlite3` in Compose, using WAL mode and `synchronous=NORMAL`. A bounded asyncio queue batches writes; defaults are 50,000 queued records, 1,000 rows per write batch, and a 0.01-second flush interval. A file-locked token bucket state is shared between Uvicorn workers so the 5,000 TPS limit and 5,000-message burst capacity are global across workers.

## Environment

| Variable | Default | Purpose |
|---|---:|---|
| `SMSC_MOCK_DATABASE` | `sms_smsc_mock/smsc_mock.sqlite3` | SQLite file path |
| `SMSC_MOCK_DLR_CALLBACK_URL` | empty | Fixed DLR destination; configure for a running receiver |
| `SMSC_MOCK_USERNAME` | empty | Basic-auth username |
| `SMSC_MOCK_PASSWORD` | empty | Basic-auth password |
| `SMSC_MOCK_MAX_TPS` | `5000` | Global token refill rate per second |
| `SMSC_MOCK_TPS_BURST` | `5000` | Global token capacity |
| `SMSC_MOCK_MIN_DELAY_SECONDS` | `1.0` | Minimum DLR delay |
| `SMSC_MOCK_MAX_DELAY_SECONDS` | `5.0` | Maximum DLR delay |
| `SMSC_MOCK_DELIVRD_WEIGHT` | `0.92` | `DELIVRD` outcome weight |
| `SMSC_MOCK_UNDELIV_WEIGHT` | `0.04` | `UNDELIV` outcome weight |
| `SMSC_MOCK_EXPIRED_WEIGHT` | `0.02` | `EXPIRED` outcome weight |
| `SMSC_MOCK_REJECTD_WEIGHT` | `0.02` | `REJECTD` outcome weight |
| `SMSC_MOCK_DLR_RETRIES` | `3` | Callback attempts |
| `SMSC_MOCK_DLR_RETRY_BACKOFF` | `2.0` | Retry backoff multiplier in seconds |
| `SMSC_MOCK_QUEUE_MAX` | `50000` | Bounded write queue size |
| `SMSC_MOCK_BATCH_SIZE` | `1000` | Maximum records per SQLite transaction |
| `SMSC_MOCK_FLUSH_INTERVAL` | `0.01` | Partial-batch flush interval in seconds |
| `SMSC_MOCK_LOG_LEVEL` | `INFO` | Logging level |

Configure the sender's SMSC entry with `base_url=http://mock_app:8090`, `send_endpoint=/onion/swift/duos`, `auth_type=basic`, and the same username and password. The callback service must be reachable at the configured callback URL; Compose defaults it to `http://dlr_app:8003/api/v1/delivery-reports/callback/`.