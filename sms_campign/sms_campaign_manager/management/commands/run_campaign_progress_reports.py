from django.core.management.base import BaseCommand

from ...services.campaign_progress_reports import send_due_reports


class Command(BaseCommand):
    help = 'Send due scheduled campaign progress email reports.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Process due reports once and exit.')

    def handle(self, *args, **options):
        import time

        while True:
            results = send_due_reports()
            for result in results:
                if result.get('success', True):
                    self.stdout.write(self.style.SUCCESS(f"Report {result['report_id']} sent."))
                else:
                    self.stdout.write(self.style.ERROR(f"Report {result['report_id']} failed: {result['message']}"))
            if options['once']:
                return
            time.sleep(30)
