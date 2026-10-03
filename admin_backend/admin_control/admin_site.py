from django.contrib.admin import AdminSite

from .models import UserProfile


class AdminBackendSite(AdminSite):
    site_header = "SMS Platform Administration"
    site_title = "SMS Administration"
    index_title = "Platform control plane"

    def has_permission(self, request):
        user = request.user
        if not user.is_active or not user.is_staff:
            return False
        try:
            return user.admin_profile.role == UserProfile.Role.ADMIN
        except UserProfile.DoesNotExist:
            return user.is_superuser


admin_site = AdminBackendSite(name="admin_backend")
