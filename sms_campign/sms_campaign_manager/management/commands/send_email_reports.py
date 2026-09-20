from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import EmailCampaignReport
from ...services.email_report_service import send_report


class Command(BaseCommand):
    help = 'Send due scheduled campaign reports via SMTP.'

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0
        for report in EmailCampaignReport.objects.filter(
            is_active=True, email_server__is_active=True,
        ).select_related('owner', 'email_server').prefetch_related('recipients', 'campaigns'):
            interval = {'10m': timedelta(minutes=10), '1h': timedelta(hours=1), 'daily': timedelta(days=1)}[report.frequency]
            if report.last_sent_at and report.last_sent_at > now - interval:
                continue
            try:
                send_report(report)
                sent += 1
            except Exception as exc:
                self.stderr.write(f'Report {report.pk} failed: {exc}')
        self.stdout.write(self.style.SUCCESS(f'Sent {sent} report(s).'))
