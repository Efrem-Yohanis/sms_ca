FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY sms_smsc_sender/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
        --trusted-host pypi.org \
        --trusted-host pypi.python.org \
        --trusted-host files.pythonhosted.org \
        --retries 5 --timeout 120 \
        -r /tmp/requirements.txt

COPY sms_smsc_sender /app/sms_smsc_sender

ENV PYTHONPATH=/app
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "sms_smsc_sender.app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
