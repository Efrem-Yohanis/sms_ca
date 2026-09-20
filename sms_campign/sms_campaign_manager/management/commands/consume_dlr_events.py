import json
from django.conf import settings
from django.core.management.base import BaseCommand
from ...services.delivery_report_service import DeliveryReportService

class Command(BaseCommand):
    help = 'Consume delivery.report.received Kafka events.'
    def add_arguments(self, parser): parser.add_argument('--once', action='store_true')
    def handle(self, *args, **opts):
        if not settings.KAFKA_ENABLED: return
        from confluent_kafka import Consumer
        consumer = Consumer({'bootstrap.servers': settings.KAFKA_BOOTSTRAP_SERVERS,
            'group.id': settings.KAFKA_DLR_GROUP_ID, 'enable.auto.commit': False,
            'auto.offset.reset': 'earliest'})
        consumer.subscribe([settings.KAFKA_DLR_TOPIC])
        try:
            while True:
                msg = consumer.poll(settings.KAFKA_CONSUMER_POLL_TIMEOUT)
                if msg is None: 
                    if opts['once']: break
                    continue
                if msg.error(): continue
                body = json.loads(msg.value())
                DeliveryReportService.process(body.get('payload', body))
                consumer.commit(message=msg, asynchronous=False)
                if opts['once']: break
        finally: consumer.close()
