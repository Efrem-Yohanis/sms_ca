from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives, get_connection

from .models import AdminEmailConfig


class AdminEmailNotConfigured(ImproperlyConfigured):
    pass


def get_admin_email_config():
    config = AdminEmailConfig.objects.filter(is_active=True, is_default=True).first()
    if config is None:
        raise AdminEmailNotConfigured("Configure admin email settings before sending account email.")
    return config


def send_admin_email(recipient, subject, text_body, html_body=None, *, config=None):
    config = config or get_admin_email_config()
    connection = get_connection(
        host=config.host,
        port=config.port,
        username=config.username or None,
        password=config.password or None,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
        fail_silently=False,
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=config.from_email,
        to=[recipient],
        connection=connection,
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
