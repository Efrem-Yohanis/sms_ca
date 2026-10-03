from rest_framework.permissions import BasePermission

from .models import UserProfile


class IsPlatformAdmin(BasePermission):
    message = "Only platform administrators can perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        try:
            profile = user.admin_profile
        except UserProfile.DoesNotExist:
            return False
        return profile.role == UserProfile.Role.ADMIN and not profile.is_locked


class IsActivePlatformUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated or not user.is_active:
            return False
        try:
            return not user.admin_profile.is_locked
        except UserProfile.DoesNotExist:
            return False
