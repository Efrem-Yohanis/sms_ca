# Standalone SMS Sender

This FastAPI process is called by a scheduler every minute. It checks scheduled campaigns, calls the Django activate/cancel APIs, reads pending Django `MessageObject` rows from SQLite, and sends them to the configured SMSC API.

## Start

From `c:\Users\efrem\Desktop\sms`:

```powershell
$env:SMSC_SENDER_DATABASE = 'c:\Users\efrem\Desktop\sms\sms_campign\db.sqlite3'
$env:SMSC_SENDER_CONFIG_ID = '1'
$env:SMSC_SENDER_DJANGO_API = 'http://127.0.0.1:8000/api/v1'
$env:SMSC_SENDER_DLR_CALLBACK_URL = 'http://127.0.0.1:8000/api/v1/delivery-reports/callback/'
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

The internal worker runs the scheduler and sender once every 60 seconds. An external scheduler can instead call `POST /run-once` every minute.

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

Successful SMSC responses create a `SentRecord` and remove the queue row. The callback URL lets the SMSC post the final delivery report back to Django, where it is mapped to a `DeliveryRecord`. Failed responses create a failed `SentRecord`; the queue row remains for retry until `max_retries` is reached, then it is removed.

Campaigns are eligible only when their schedule date, recurrence, time window, and `schedule_status` are active. A draft campaign is started through `POST /campaigns/{campaign_id}/activate/`; an active campaign outside its schedule is stopped through `POST /campaigns/{campaign_id}/cancel/`.

## Endpoints

- `GET /health`
- `POST /run-once`
- `POST /scheduler/run-once`
- `POST /worker/start`
- `POST /worker/stop`

Set `SMSC_SENDER_DLR_CALLBACK_URL` to a URL reachable by the SMSC process. The Django callback accepts `DELIVRD`, `UNDELIV`, `EXPIRED`, and `REJECTD`, maps them to the application delivery statuses, and safely handles duplicate reports.
