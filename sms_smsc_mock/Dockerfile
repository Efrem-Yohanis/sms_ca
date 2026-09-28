FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY sms_smsc_mock/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sms_smsc_mock/ ./sms_smsc_mock/

EXPOSE 8090

CMD ["python", "-m", "uvicorn", "sms_smsc_mock.app:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]