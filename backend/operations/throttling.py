from rest_framework.throttling import SimpleRateThrottle
from django.conf import settings


class LoginRateThrottle(SimpleRateThrottle):
    """Limit password attempts per client address without adding a dependency."""

    scope = 'login'

    def get_cache_key(self, request, view):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '') if settings.TRUST_PROXY_HEADERS else ''
        client = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', 'unknown')
        return self.cache_format % {'scope': self.scope, 'ident': client}


class PasswordChangeRateThrottle(SimpleRateThrottle):
    """Limit a signed-in user's password changes independently of login attempts."""

    scope = 'password_change'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}
