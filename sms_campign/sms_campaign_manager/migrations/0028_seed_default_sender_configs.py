from django.db import migrations


def seed_default_sender_configs(apps, schema_editor):
    database = schema_editor.connection.alias
    GlobalTPSConfig = apps.get_model('sms_campaign_manager', 'GlobalTPSConfig')
    NAddressesConfig = apps.get_model('sms_campaign_manager', 'NAddressesConfig')

    if not GlobalTPSConfig.objects.using(database).exists():
        GlobalTPSConfig.objects.using(database).create(
            name='Default global TPS',
            description='Baseline sender throughput configuration.',
            global_tps=4000,
            is_default=True,
            is_active=True,
        )

    if not NAddressesConfig.objects.using(database).exists():
        NAddressesConfig.objects.using(database).create(
            name='Default N-addresses',
            description='Baseline maximum destinations per SMSC request.',
            max_addresses_per_request=1000,
            is_default=True,
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sms_campaign_manager', '0027_alter_reportsubscription_frequency'),
    ]

    operations = [
        migrations.RunPython(seed_default_sender_configs, migrations.RunPython.noop),
    ]
