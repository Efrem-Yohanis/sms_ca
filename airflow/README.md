# Airflow Scheduler

The Airflow deployment runs two DAGs:

- `dispatch_campaigns` polls Django every minute, builds any required audience and messages, activates due campaigns, starts the sender, and stops campaigns whose schedule window has closed.
- `dispatch_reports` polls every five minutes and asks Django to render and deliver due report subscriptions.

## Run locally

Start the stack from the repository root:

```powershell
docker compose up --build -d
```

Open the Airflow UI at `http://localhost:8080`. The local default login is `admin` / `change-this-local-password`; set `AIRFLOW_ADMIN_USERNAME`, `AIRFLOW_ADMIN_PASSWORD`, `AIRFLOW_FERNET_KEY`, and `AIRFLOW_WEBSERVER_SECRET_KEY` in `.env` before starting the stack anywhere shared or production-like. `AIRFLOW_WEBSERVER_PORT` changes the host port.

The DAGs call Django at `http://django:8000/api/v1` and the FastAPI SMS sender at `http://sms-sender:8001` over the Compose network. The sender service uses the shared campaign PostgreSQL database and Kafka broker.

The local Compose configuration stores Airflow metadata in the same PostgreSQL database as Django. Use a dedicated database and stronger secret management for production deployments.