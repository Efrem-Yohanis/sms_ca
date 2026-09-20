# Kafka integration

Set `KAFKA_ENABLED=true` and `KAFKA_BOOTSTRAP_SERVERS` to enable asynchronous
delivery reports. Message builds, sender outcomes, and callback reports are
written transactionally to `KafkaOutboxEvent`. Run:

```sh
python manage.py migrate
python manage.py publish_outbox
python manage.py consume_dlr_events
```

Failed publishes are retried with exponential backoff and moved to
`KAFKA_DLQ_TOPIC` after `KAFKA_MAX_RETRIES`. With Kafka disabled, callbacks
retain their direct synchronous behavior. `docker compose up --build` starts
Postgres, Redpanda, the web process, publisher, sender, and DLR consumer.
