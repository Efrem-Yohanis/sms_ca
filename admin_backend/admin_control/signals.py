from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        role = (
            UserProfile.Role.ADMIN
            if instance.is_superuser or instance.is_staff
            else UserProfile.Role.CAMPAIGN_MANAGER
        )
        UserProfile.objects.create(
            user=instance,
            role=role,
            department="Administration" if role == UserProfile.Role.ADMIN else "Unassigned",
        )
    else:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                "role": (
                    UserProfile.Role.ADMIN
                    if instance.is_superuser or instance.is_staff
                    else UserProfile.Role.CAMPAIGN_MANAGER
                ),
                "department": "Unassigned",
            },
        )
