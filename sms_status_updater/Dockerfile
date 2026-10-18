FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY sms_status_updater/requirements.txt /tmp/status-requirements.txt
RUN pip install --no-cache-dir -r /tmp/status-requirements.txt

COPY sms_campign/requirements.txt /tmp/campaign-requirements.txt
RUN pip install --no-cache-dir -r /tmp/campaign-requirements.txt

COPY sms_campign/ /app/sms_campign/
COPY sms_status_updater/ /app/sms_status_updater/

EXPOSE 8010

CMD ["uvicorn", "sms_status_updater.app:app", "--host", "0.0.0.0", "--port", "8010"]
