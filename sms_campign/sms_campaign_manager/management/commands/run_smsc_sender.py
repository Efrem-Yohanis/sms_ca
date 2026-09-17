from django.core.management.base import BaseCommand, CommandError

from ...models import SMSCConfig
from ...services.smsc_sender import SmsSenderService


class Command(BaseCommand):
    help = 'Send pending MessageObject rows to the configured SMSC.'

    def add_arguments(self, parser):
        parser.add_argument('--smsc-id', type=int, help='SMSCConfig id; defaults to the active default config.')
        parser.add_argument('--once', action='store_true', help='Process one rate-limited window and exit.')
        parser.add_argument('--workers', type=int, default=None, help='Maximum concurrent HTTP submissions.')

    def handle(self, *args, **options):
        smsc_id = options.get('smsc_id')
        if smsc_id:
            config = SMSCConfig.objects.filter(pk=smsc_id, is_active=True).first()
        else:
            config = SMSCConfig.objects.filter(is_active=True, is_default=True).first()
            if config is None:
                config = SMSCConfig.objects.filter(is_active=True).first()

        if config is None:
            raise CommandError('No active SMSCConfig found.')

        service = SmsSenderService(config, workers=options.get('workers'))
        self.stdout.write(
            f'SMSC sender started: {config.name} -> {config.get_full_send_url()} '
            f'at {config.rate_limit_per_second} TPS'
        )

        if options['once']:
            self.stdout.write(str(service.run_once()))
            return

        try:
            service.run_forever()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('SMSC sender stopped.'))
