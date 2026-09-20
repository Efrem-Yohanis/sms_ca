FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
WORKDIR /app/sms_campign
CMD ["gunicorn", "sms_campign.wsgi:application", "--bind", "0.0.0.0:8000"]
