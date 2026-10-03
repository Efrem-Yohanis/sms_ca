from .models import AdminAuditLog


SECRET_FIELDS = {"password", "api_key", "api_secret", "token", "authorization"}


def _safe_value(key, value):
    normalized_key = key.lower().replace("-", "_")
    if any(secret in normalized_key for secret in SECRET_FIELDS):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(child_key): _safe_value(str(child_key), child_value) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(key, child_value) for child_value in value]
    return value


def safe_values(values):
    return _safe_value("", values)


def snapshot(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name == "password":
            values[field.name] = "[redacted]"
        else:
            value = getattr(instance, field.attname)
            values[field.name] = value.isoformat() if hasattr(value, "isoformat") else value

    for field in instance._meta.many_to_many:
        values[field.name] = list(
            getattr(instance, field.name).values_list("pk", flat=True)
        )

    if hasattr(instance, "assigned_profiles"):
        values["assigned_user_ids"] = list(
            instance.assigned_profiles.values_list("user_id", flat=True)
        )
    if instance._meta.model_name == "userprofile":
        values["assigned_n_addresses"] = list(
            instance.user.assigned_n_addresses.values_list("pk", flat=True)
        )
    if instance._meta.model_name == "senderid":
        from .models import SenderSMSCBinding
        values["smsc_ids"] = list(
            SenderSMSCBinding.objects.filter(sender_id=instance).values_list("smsc_id", flat=True)
        )
    elif instance._meta.model_name == "channel":
        from .models import ChannelSMSCBinding
        values["smsc_bindings"] = [
            {
                "smsc_id": binding.smsc_id,
                "default_tps": binding.default_tps,
                "priority": binding.priority,
                "allowed_sender_ids": list(
                    binding.allowed_sender_ids.values_list("pk", flat=True)
                ),
            }
            for binding in ChannelSMSCBinding.objects.filter(channel=instance)
            .prefetch_related("allowed_sender_ids")
            .order_by("smsc_id")
        ]
    elif instance._meta.model_name == "smscconfig":
        from .models import ChannelSMSCBinding, SenderSMSCBinding
        values["sender_ids"] = list(
            SenderSMSCBinding.objects.filter(smsc=instance).values_list("sender_id_id", flat=True)
        )
        values["channels"] = list(
            ChannelSMSCBinding.objects.filter(smsc=instance).values_list("channel_id", flat=True)
        )
    return values


def audit(request, action, instance, summary, old_values=None, new_values=None):
    actor = request.user if request.user.is_authenticated else None
    AdminAuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=instance._meta.label,
        object_id=str(instance.pk),
        summary=summary,
        old_values=safe_values(old_values or {}),
        new_values=safe_values(new_values or {}),
    )
