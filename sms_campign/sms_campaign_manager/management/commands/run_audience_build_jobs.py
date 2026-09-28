from django.core.management.base import BaseCommand
import time

from ...models import AudienceBuildJob
from ...services.audience_service import AudienceBuildService


class Command(BaseCommand):
    help = 'Process pending audience rebuild jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            job = AudienceBuildJob.objects.filter(status='PENDING').order_by('created_at').first()
            if job is None:
                if options['once']:
                    return
                time.sleep(1)
                continue
            job = AudienceBuildService.run_job(job.id)
            self.stdout.write(self.style.SUCCESS(
                f'Job {job.id}: {job.status} ({job.processed_rows} rows)'
            ))
            if options['once']:
                return