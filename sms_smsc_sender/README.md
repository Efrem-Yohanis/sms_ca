# Standalone SMS Sender

This FastAPI process reads pending Django `MessageObject` rows from SQLite and sends them to the configured SMSC API. Campaign scheduling runs in the separate `sms_campaign_scheduler` service.

## Start

From `c:\Users\efrem\Desktop\sms`:

```powershell
$env:SMSC_SENDER_DATABASE = 'c:\Users\efrem\Desktop\sms\sms_campign\db.sqlite3'
$env:SMSC_SENDER_CONFIG_ID = '1'
$env:SMSC_SENDER_DLR_CALLBACK_URL = 'http://127.0.0.1:8092/api/v1/delivery-reports/callback/'
$env:SMSC_SENDER_RUN_WORKER = 'true'
python -m uvicorn sms_smsc_sender.app:app --host 127.0.0.1 --port 8091 --workers 1
```

Use one Uvicorn worker because the sender coordinates rate allocation in process memory.

## Run one rate-limited window

```powershell
Invoke-RestMethod http://127.0.0.1:8091/run-once -Method Post
```

For continuous delivery, start the worker:

```powershell
Invoke-RestMethod http://127.0.0.1:8091/worker/start -Method Post
```

Or start it automatically with `SMSC_SENDER_RUN_WORKER=true`.

The internal worker processes the sender queue continuously. An external scheduler can instead call `POST /run-once` when needed.

## Fair allocation

If the SMSC config allows `4000` TPS and four campaigns have pending messages, one window allocates up to `1000` rows to each campaign. The sender then builds each request as:

```json
{
  "message_id": "msg_13_...",
  "campaign_id": 13,
  "sender_id": "SMSINFO",
  "receiver": "+251911000001",
  "message_content": "Full message content",
  "callback_url": "http://127.0.0.1:8000/api/v1/delivery-reports/callback/"
}
```

Successful SMSC responses create a `SentRecord` and remove the queue row. The callback URL lets the SMSC post the final delivery report to the standalone FastAPI delivery receiver, which maps it to a `DeliveryRecord` in the shared database. Failed responses create a failed `SentRecord`; the queue row remains for retry until `max_retries` is reached, then it is removed.

## Endpoints

- `GET /health`
- `POST /run-once`
- `POST /worker/start`
- `POST /worker/stop`

Set `SMSC_SENDER_DLR_CALLBACK_URL` to a URL reachable by the SMSC process. The FastAPI receiver accepts `DELIVRD`, `UNDELIV`, `EXPIRED`, and `REJECTD`, maps them to the application delivery statuses, and safely handles duplicate reports.

## Delivery receiver

Start the receiver separately from Django and the sender:

```powershell
$env:SMSC_DELIVERY_DATABASE = 'c:\Users\efrem\Desktop\sms\sms_campign\db.sqlite3'
python -m uvicorn sms_delivery_receiver.app:app --host 127.0.0.1 --port 8092 --workers 1
```

Use `POST /api/v1/delivery-reports/callback/` for the SMSC webhook and `GET /health` for a readiness check. The service updates both `SentRecord` and `DeliveryRecord` in one SQLite transaction.
