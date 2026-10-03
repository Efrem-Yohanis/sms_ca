# Campaign Scheduler

Standalone FastAPI service that checks campaign schedules and changes campaign state.

## Compose profile

The optional Compose service uses the `standalone-scheduler` profile:

```powershell
docker compose --profile standalone-scheduler up --build -d standalone_scheduler_api
```

The profile starts the API on port `8093`. Its background worker is disabled by default because the main stack uses the Airflow `scduler_app` for automatic dispatch. Do not enable `SMSC_SCHEDULER_RUN_WORKER` while Airflow is dispatching campaigns.

## Start

From `C:\Users\efrem\Desktop\sms`:

```powershell
$env:SMSC_SCHEDULER_DJANGO_API = 'http://127.0.0.1:8000/api/v1'
$env:SMSC_SCHEDULER_INTERVAL = '60'
$env:SMSC_SCHEDULER_RUN_WORKER = 'true'
python -m uvicorn sms_campaign_scheduler.app:app --host 127.0.0.1 --port 8093 --workers 1
```

Every interval, the service gets all campaigns and checks their schedule window. It activates and starts a campaign when its window opens, pauses sending between windows, and resumes at the next window. It does not permanently cancel campaigns at a window boundary.

## Endpoints

- `GET /health`
- `POST /run-once`
- `POST /worker/start`
- `POST /worker/stop`