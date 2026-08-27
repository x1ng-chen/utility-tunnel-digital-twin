from typing import Optional
from django.utils import timezone
from .models import AuditLog


def actor_name(user) -> str:
    profile = getattr(user, 'profile', None)
    return (profile.display_name if profile else '') or user.get_full_name() or user.email or user.username


def audit(user, action: str, resource_type: str, resource_id: str = '', detail: Optional[dict] = None, request_id: str = '') -> AuditLog:
    return AuditLog.objects.create(
        actor=user,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id or ''),
        detail=detail or {},
        request_id=request_id,
        occurred_at=timezone.now(),
    )
