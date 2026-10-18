from smtplib import SMTPException

from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils import timezone

from sms_campaign_manager.models import EmailConfig


class NotificationDeliveryError(Exception):
    pass


EVENTS = {
    "created": ("Task created", "Your scheduled task has been created."),
    "started": ("Task started", "Your scheduled task has started running."),
    "completed": ("Task completed", "Your scheduled task completed successfully."),
    "failed": ("Task failed", "Your scheduled task failed."),
}


def send_schedule_notification(schedule, event, run_id=""):
    if not schedule.accept_notifications:
        return False
    if event not in EVENTS:
        raise ValueError(f"Unsupported task scheduler notification event: {event}")

    try:
        config = EmailConfig.objects.filter(is_active=True, is_default=True).first()
        password = config.password if config else ""
    except (ImproperlyConfigured, ValueError) as exc:
        raise NotificationDeliveryError(
            "The campaign manager email configuration could not be read."
        ) from exc
    if config is None:
        raise NotificationDeliveryError(
            "No active default campaign manager email configuration is available."
        )

    label, message = EVENTS[event]
    context = {
        "event_label": label,
        "message": message,
        "schedule": schedule,
        "run_id": run_id,
        "sent_at": timezone.localtime(),
    }
    subject_name = " ".join(schedule.name.splitlines()).strip()
    email = EmailMultiAlternatives(
        subject=f"[Task Scheduler] {label}: {subject_name}",
        body=(
            f"{message}\n\nTask: {schedule.name}\n"
            f"Owner: {schedule.owner}\n"
            + (f"Run: {run_id}\n" if run_id else "")
        ),
        from_email=config.default_from_email,
        to=[schedule.owner_email],
        connection=get_connection(
            host=config.host,
            port=config.port,
            username=config.username,
            password=password,
            use_tls=config.use_tls,
            use_ssl=config.use_ssl,
            timeout=5,
            fail_silently=False,
        ),
    )
    email.attach_alternative(
        render_to_string("task_scheduler/emails/schedule_notification.html", context),
        "text/html",
    )
    try:
        sent = email.send(fail_silently=False)
    except (OSError, SMTPException, ValueError) as exc:
        raise NotificationDeliveryError("Campaign email delivery failed.") from exc
    if sent != 1:
        raise NotificationDeliveryError("Campaign email backend did not send the message.")
    return True
