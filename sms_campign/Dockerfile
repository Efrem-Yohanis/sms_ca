FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sms_campign/ ./sms_campign/
COPY sms_campaign_scheduler/ ./sms_campign/sms_campaign_scheduler/
WORKDIR /app/sms_campign

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]