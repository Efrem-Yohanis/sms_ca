from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from ...models import KafkaOutboxEvent
from ...kafka import kafka_producer, produce_message, TOPIC_DLQ

class Command(BaseCommand):
    help = 'Publish pending transactional Kafka outbox events.'
    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--batch-size', type=int, default=100)
    def handle(self, *args, **opts):
        if not settings.KAFKA_ENABLED: return
        producer = kafka_producer()
        while True:
            rows = list(KafkaOutboxEvent.objects.filter(status='pending',
                available_at__lte=timezone.now()).order_by('id')[:opts['batch_size']])
            if not rows: break
            for event in rows:
                try:
                    event.attempts += 1
                    produce_message(producer, event)
                    event.status, event.published_at, event.last_error = 'published', timezone.now(), ''
                except Exception as exc:
                    event.last_error = str(exc)
                    if event.attempts >= settings.KAFKA_MAX_RETRIES:
                        event.status, event.topic = 'failed', TOPIC_DLQ
                    else:
                        event.available_at = timezone.now() + timedelta(seconds=2 ** min(event.attempts, 8))
                event.save(update_fields=['status','published_at','last_error','attempts','available_at','topic','updated_at'])
            if opts['once']: break
