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
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, 'profile', None)
        return not profile or profile.role != 'ingest'


class TelemetryPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        profile = getattr(request.user, 'profile', None)
        if profile and profile.role == 'ingest':
            return request.method == 'POST'
        return True
