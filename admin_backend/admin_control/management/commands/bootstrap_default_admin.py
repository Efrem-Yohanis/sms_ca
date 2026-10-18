import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from admin_control.models import UserProfile


class Command(BaseCommand):
    help = "Create or promote the default platform administrator account."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME", "admin").strip()
        password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "admin")
        email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "admin@example.com").strip()

        if not username or not password:
            raise CommandError("Bootstrap admin username and password must be set.")
        if not settings.DEBUG and password == "admin":
            raise CommandError(
                "Set ADMIN_BOOTSTRAP_PASSWORD to a non-default value outside local development."
            )

        User = get_user_model()
        user = User.objects.filter(username=username).first()
        created = user is None
        if created:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
        else:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            fields = ["is_staff", "is_superuser", "is_active"]
            if email and not user.email:
                user.email = email
                fields.append("email")
            user.save(update_fields=fields)

        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role": UserProfile.Role.ADMIN,
                "department": "Administration",
            },
        )
        if profile.role != UserProfile.Role.ADMIN:
            profile.role = UserProfile.Role.ADMIN
            profile.save(update_fields=["role", "updated_at"])

        action = "Created" if created else "Ensured"
        self.stdout.write(self.style.SUCCESS(f"{action} administrator account '{username}'."))
