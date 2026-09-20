"""Kafka topic, event and transactional outbox helpers."""
import json
from django.conf import settings
from django.utils import timezone
from .models import KafkaOutboxEvent

TOPIC_MESSAGE_CREATED = getattr(settings, "KAFKA_MESSAGE_CREATED_TOPIC", "message.created")
TOPIC_DLR = getattr(settings, "KAFKA_DLR_TOPIC", "delivery.report.received")
TOPIC_SENT = getattr(settings, "KAFKA_SENT_TOPIC", "sent.report.received")
TOPIC_DLQ = getattr(settings, "KAFKA_DLQ_TOPIC", "sms.dlq")

def enqueue_event(event_type, payload, *, key="", topic=None):
    return KafkaOutboxEvent.objects.create(
        event_type=event_type, topic=topic or event_type, key=str(key or ""),
        payload=payload, available_at=timezone.now(),
    )

def event_payload(event):
    return json.dumps({"event_id": event.id, "event_type": event.event_type,
                       "payload": event.payload}, separators=(",", ":")).encode()

def produce_message(producer, event):
    producer.produce(event.topic, key=event.key or None, value=event_payload(event))
    producer.flush()

def kafka_producer():
    from confluent_kafka import Producer
    return Producer({
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "enable.idempotence": True,
        "acks": "all",
        "retries": 10,
        "max.in.flight.requests.per.connection": 5,
    })
