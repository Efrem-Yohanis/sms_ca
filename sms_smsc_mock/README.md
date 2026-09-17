# Local SMSC Mock

Simulates a real SMPP-style SMSC, not just a "always succeeds" stub:

1. Client calls `/api/send` (or `/api/send/batch`).
2. The mock first checks a **TPS (throughput) limiter** — real SMSCs enforce a negotiated max submit rate per bind/system_id, and reject bursts over it with `ESME_RTHROTTLED`. Exceeding `SMSC_MAX_TPS` here returns `429`.
3. If accepted, it returns `200 ACCEPTED` immediately with a `provider_message_id` and `segment_count` (long messages get split into concatenated-SMS segments, same as a real SMSC would).
4. A background task waits a **randomized transit delay** (`SMSC_MIN_DELIVERY_DELAY_SECONDS`–`SMSC_MAX_DELIVERY_DELAY_SECONDS`, slightly longer for multi-segment messages), then resolves to one of four **final statuses**, weighted like real network traffic:

| Status | Default weight | Meaning |
|---|---|---|
| `DELIVRD` | 92% | Delivered to handset |
| `UNDELIV` | 4% | Absent subscriber / handset full / network error / unknown subscriber |
| `EXPIRED` | 2% | Validity period expired before delivery |
| `REJECTD` | 2% | Rejected by network / destination blocked |

Each status carries an SMPP-style `err_code` and human-readable reason (see `REASON_CODES` in `app.py`).

5. If the request included a `callback_url`, the mock POSTs a delivery report (DLR) to it — with retries on failure/timeout — including both structured JSON fields and a standard SMPP `deliver_sm` DLR text string (`id:... stat:DELIVRD err:000 ...`).

All writes still go through one queue drained by a single SQLite writer task, so there's no lock contention regardless of throughput.

## Install

```powershell
pip install fastapi uvicorn httpx
```

## Start

```powershell
python -m uvicorn sms_smsc_mock.app:app --host 127.0.0.1 --port 8090 --workers 1
```

One worker only — the TPS bucket, queue, and SQLite writer all live in-process.

## Send one message

```powershell
curl -X POST http://127.0.0.1:8090/api/send `
  -H "Content-Type: application/json" `
  -d '{"campaign_id":13,"sender_id":"SMSINFO","receiver":"+251911000001","message_content":"Hello from the SMSC test service","callback_url":"http://127.0.0.1:9000/dlr"}'
```

Response:

```json
{
  "success": true,
  "status": "ACCEPTED",
  "provider_message_id": "smsc_<id>",
  "message_id": "msg_<id>",
  "segment_count": 1
}
```

If you're over the TPS limit:

```json
{"detail": "ESME_RTHROTTLED: submit throughput exceeded, retry shortly"}
```
with HTTP `429`.

## Delivery report (DLR)

POSTed to `callback_url` once the simulated transit delay elapses:

```json
{
  "message_id": "msg_<id>",
  "provider_message_id": "smsc_<id>",
  "campaign_id": 13,
  "receiver": "+251911000001",
  "status": "UNDELIV",
  "err_code": "008",
  "error_reason": "Absent Subscriber",
  "segment_count": 1,
  "delivered_at": "2026-09-16T10:15:32.123456+00:00",
  "dlr_text": "id:msg_<id> sub:001 dlvrd:000 submit date:2609161015 done date:2609161018 stat:UNDELIV err:008 text:Hello from the SMSC "
}
```

Your callback endpoint should return any 2xx status; non-2xx or timeouts (`SMSC_DLR_TIMEOUT_SECONDS`) trigger a retry, up to `SMSC_DLR_MAX_ATTEMPTS`.

## Check message status directly

```powershell
curl http://127.0.0.1:8090/api/messages/msg_<id>
```

Same fields as the DLR payload, plus `received_at`, `dlr_sent`, `dlr_attempts`, `dlr_last_error`.

## Config (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `SMSC_MOCK_DATABASE` | `sms_smsc_mock/smsc_mock.sqlite3` | SQLite file path |
| `SMSC_QUEUE_MAX_SIZE` | `50000` | Bounded write queue; full queue returns `503` |
| `SMSC_BATCH_SIZE` | `1000` | Max rows per SQLite write batch |
| `SMSC_FLUSH_INTERVAL_SECONDS` | `0.01` | How often the writer flushes |
| `SMSC_MIN_DELIVERY_DELAY_SECONDS` | `1.0` | Fastest simulated transit time |
| `SMSC_MAX_DELIVERY_DELAY_SECONDS` | `5.0` | Slowest simulated transit time |
| `SMSC_DELIVRD_WEIGHT` | `0.92` | Relative weight for a delivered outcome |
| `SMSC_UNDELIV_WEIGHT` | `0.04` | Relative weight for undelivered |
| `SMSC_EXPIRED_WEIGHT` | `0.02` | Relative weight for expired |
| `SMSC_REJECTD_WEIGHT` | `0.02` | Relative weight for rejected |
| `SMSC_MAX_TPS` | `200` | Sustained submit rate before `429 ESME_RTHROTTLED` |
| `SMSC_TPS_BURST_CAPACITY` | same as `SMSC_MAX_TPS` | Token-bucket burst size above the sustained rate |
| `SMSC_DLR_TIMEOUT_SECONDS` | `5.0` | Timeout per webhook POST attempt |
| `SMSC_DLR_MAX_ATTEMPTS` | `3` | Retries on webhook failure |
| `SMSC_DLR_RETRY_BACKOFF_SECONDS` | `2.0` | Backoff multiplier between retries |

To make everything always succeed (like before), set:
```powershell
$env:SMSC_DELIVRD_WEIGHT="1"; $env:SMSC_UNDELIV_WEIGHT="0"; $env:SMSC_EXPIRED_WEIGHT="0"; $env:SMSC_REJECTD_WEIGHT="0"
```

`message_id` is optional and generated when omitted. The legacy field name `recipient` is still accepted as an alias for `receiver`.