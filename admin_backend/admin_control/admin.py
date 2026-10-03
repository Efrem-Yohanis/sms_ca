from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .admin_site import admin_site
from .audit import audit, snapshot
from .models import (
    AdminAuditLog,
    Channel,
    ChannelSMSCBinding,
    GlobalTPSConfig,
    LoginAttempt,
    NAddress,
    NAddressesConfig,
    SMSCConfig,
    SenderID,
    SenderIDDetails,
    SenderSMSCBinding,
    UserProfile,
)


class AuditedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        old = snapshot(type(obj).objects.get(pk=obj.pk)) if change else {}
        self._old_relation_values = {
            key: value for key, value in old.items() if key in _RELATION_KEYS
        }
        if change:
            old = {key: value for key, value in old.items() if key not in _RELATION_KEYS}
        super().save_model(request, obj, form, change)
        new = snapshot(obj)
        new = {key: value for key, value in new.items() if key not in _RELATION_KEYS}
        audit(request, "update" if change else "create", obj, f"Saved {obj}.", old, new)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        new = snapshot(form.instance)
        new_relation_values = {
            key: value for key, value in new.items() if key in _RELATION_KEYS
        }
        if self._old_relation_values != new_relation_values:
            audit(
                request,
                "assign",
                form.instance,
                f"Updated assignments for {form.instance}.",
                self._old_relation_values,
                new_relation_values,
            )

    def delete_model(self, request, obj):
        _validate_config_delete(obj)
        audit(request, "delete", obj, f"Deleted {obj}.")
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            _validate_config_delete(obj)
        for obj in queryset:
            self.delete_model(request, obj)


_RELATION_KEYS = {
    "assigned_user_ids",
    "sms_configs",
    "sender_ids",
    "channels",
    "tps_configs",
    "n_address_configs",
    "smsc_ids",
    "smsc_bindings",
    "allowed_sender_ids",
    "assigned_users",
}


def _validate_config_delete(obj):
    from django.core.exceptions import ValidationError
    from .models import Campaign, ChannelSMSCBinding, NAddress, SenderSMSCBinding

    if isinstance(obj, SMSCConfig) and (
        SenderSMSCBinding.objects.filter(smsc_id=obj.pk).exists()
        or ChannelSMSCBinding.objects.filter(smsc_id=obj.pk).exists()
        or NAddress.objects.filter(smsc_id=obj.pk).exists()
    ):
        raise ValidationError("Remove the SMSC's sender, channel, and N-address bindings before deleting it.")
    if isinstance(obj, SenderSMSCBinding) and NAddress.objects.filter(
        sender_id_id=obj.sender_id_id, smsc_id=obj.smsc_id
    ).exists():
        raise ValidationError("Reassign dependent N-addresses before removing this Sender ID binding.")
    if isinstance(obj, ChannelSMSCBinding) and (
        ChannelSMSCBinding.objects.filter(channel_id=obj.channel_id).count() <= 1
        or NAddress.objects.filter(channel_id=obj.channel_id, smsc_id=obj.smsc_id).exists()
    ):
        raise ValidationError("A channel must retain an SMSC binding; reassign dependent N-addresses first.")
    if isinstance(obj, SenderID) and Campaign.objects.filter(
        sender_id=obj.sender_id,
        is_deleted=False,
        status__in=("active", "in_progress", "paused"),
    ).exists():
        raise ValidationError("Cannot delete a Sender ID used by an active campaign; disable it instead.")
    if isinstance(obj, Channel) and any(
        str(obj.pk) in {str(channel_id) for channel_id in (campaign.channels_id or [])}
        for campaign in Campaign.objects.filter(is_deleted=False).only("channels_id")
    ):
        raise ValidationError("Cannot delete a Channel referenced by a campaign; disable it instead.")


class UserProfileAdmin(AuditedAdmin):
    list_display = ("username", "email", "department", "role", "active", "is_locked", "tps_limit")
    list_filter = ("role", "department", "is_locked", "user__is_active")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "department")
    filter_horizontal = ("sms_configs", "sender_ids", "channels", "tps_configs", "n_address_configs")
    raw_id_fields = ("user",)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(ordering="user__username")
    def username(self, obj):
        return obj.user.username

    @admin.display(ordering="user__email")
    def email(self, obj):
        return obj.user.email

    @admin.display(boolean=True, ordering="user__is_active")
    def active(self, obj):
        return obj.user.is_active

    def save_model(self, request, obj, form, change):
        if change and obj.user_id == request.user.id and "role" in form.changed_data:
            from django.core.exceptions import ValidationError
            raise ValidationError("You cannot change your own role.")
        if change:
            current = UserProfile.objects.get(pk=obj.pk)
            removing_last = (
                current.role == UserProfile.Role.ADMIN
                and current.user.is_active
                and not current.is_locked
                and (
                    obj.role != current.role
                    or not obj.user.is_active
                    or obj.is_locked
                )
            )
            if removing_last and UserProfile.objects.filter(
                role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False
            ).count() <= 1:
                from django.core.exceptions import ValidationError
                raise ValidationError("Cannot remove or disable the last active Admin.")
        super().save_model(request, obj, form, change)

class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("username", "email", "password1", "password2")}),
    )
    list_display = ("username", "email", "first_name", "last_name", "is_active")
    readonly_fields = ("last_login", "date_joined")

    def delete_model(self, request, obj):
        from django.core.exceptions import ValidationError
        profile = getattr(obj, "admin_profile", None)
        if obj.pk == request.user.pk:
            raise ValidationError("You cannot delete your own account.")
        if profile and profile.role == UserProfile.Role.ADMIN and obj.is_active and not profile.is_locked:
            if UserProfile.objects.filter(
                role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False
            ).count() <= 1:
                raise ValidationError("Cannot delete the last active Admin.")
        audit(request, "delete", profile or obj, f"Deleted user {obj.username}.")
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from django.core.exceptions import ValidationError

        if queryset.filter(pk=request.user.pk).exists():
            raise ValidationError("You cannot delete your own account.")
        selected_active_admins = UserProfile.objects.filter(
            user__in=queryset,
            role=UserProfile.Role.ADMIN,
            user__is_active=True,
            is_locked=False,
        ).count()
        total_active_admins = UserProfile.objects.filter(
            role=UserProfile.Role.ADMIN, user__is_active=True, is_locked=False
        ).count()
        if selected_active_admins and total_active_admins - selected_active_admins < 1:
            raise ValidationError("Cannot delete the last active Admin.")
        for user in queryset:
            self.delete_model(request, user)

    def has_module_permission(self, request):
        return super().has_module_permission(request)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return False



admin_site.register(User, UserAdmin)
admin_site.register(UserProfile, UserProfileAdmin)
admin_site.register(SMSCConfig, AuditedAdmin)
admin_site.register(SenderID, AuditedAdmin)
admin_site.register(SenderIDDetails, AuditedAdmin)
admin_site.register(Channel, AuditedAdmin)
admin_site.register(GlobalTPSConfig, AuditedAdmin)
admin_site.register(NAddressesConfig, AuditedAdmin)
admin_site.register(NAddress, AuditedAdmin)
admin_site.register(SenderSMSCBinding, AuditedAdmin)
admin_site.register(ChannelSMSCBinding, AuditedAdmin)
admin_site.register(AdminAuditLog, ReadOnlyAdmin)
admin_site.register(LoginAttempt, ReadOnlyAdmin)
