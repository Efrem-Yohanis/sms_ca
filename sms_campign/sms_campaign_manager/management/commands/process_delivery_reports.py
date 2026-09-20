import os
from types import SimpleNamespace

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import DeliveryReportInbox, SentRecord
from ...views import DeliveryReportCallbackView


class Command(BaseCommand):
    help = 'Process queued provider delivery reports in bounded batches.'

    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=1000)
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        batch_size = max(1, min(options['batch_size'], 10000))
        processed = failed = 0
        previous = os.environ.pop('DLR_ASYNC_PROCESSING', None)
        try:
            while True:
                inbox_rows = list(
                    DeliveryReportInbox.objects.filter(
                        status='pending',
                        available_at__lte=timezone.now(),
                    ).order_by('id')[:batch_size]
                )
                if not inbox_rows:
                    break

                for inbox in inbox_rows:
                    inbox.attempts += 1
                    try:
                        if not SentRecord.objects.filter(
                            provider_message_id=inbox.provider_message_id,
                        ).exists():
                            raise RuntimeError(
                                f'Unknown provider_message_id in inbox: '
                                f'{inbox.provider_message_id!r}'
                            )
                        callback_view = DeliveryReportCallbackView()
                        payload = dict(inbox.payload)
                        payload['provider_message_id'] = inbox.provider_message_id
                        response = callback_view.post(SimpleNamespace(data=payload))
                        if response.status_code >= 400:
                            response_data = getattr(response, 'data', None)
                            raise RuntimeError(
                                f'DLR callback returned HTTP {response.status_code}: '
                                f'{response_data}'
                            )
                        inbox.status = 'processed'
                        inbox.processed_at = timezone.now()
                        inbox.last_error = ''
                        processed += 1
                    except Exception as exc:
                        inbox.status = 'failed'
                        inbox.last_error = str(exc)
                        failed += 1
                    inbox.save(update_fields=[
                        'status', 'attempts', 'processed_at', 'last_error', 'updated_at',
                    ])

                if options['once']:
                    break
        finally:
            if previous is not None:
                os.environ['DLR_ASYNC_PROCESSING'] = previous

        self.stdout.write(self.style.SUCCESS(
            f'Processed {processed} delivery reports; failed {failed}.'
        ))
