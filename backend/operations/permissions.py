from rest_framework.permissions import BasePermission


class RolePermission(BasePermission):
    required_roles: set[str] = set()

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        profile = getattr(request.user, 'profile', None)
        return bool(profile and profile.role in getattr(view, 'required_roles', set()))


class AuthenticatedRead(RolePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)
