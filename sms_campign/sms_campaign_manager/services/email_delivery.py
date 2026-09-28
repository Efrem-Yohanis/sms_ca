from django.core.mail import get_connection

from ..models import EmailConfig


def get_email_connection(config=None):
    config = config or EmailConfig.objects.filter(
        is_active=True,
    ).order_by('-is_default', 'id').first()
    if config is None:
        return get_connection()
    return get_connection(
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
        fail_silently=False,
    )


def get_active_email_config():
    return EmailConfig.objects.filter(
        is_active=True,
    ).order_by('-is_default', 'id').first()