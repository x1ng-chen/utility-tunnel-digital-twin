import hashlib

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle


def client_address(request):
    """Resolve the client address without trusting proxy headers by default."""

    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '') if settings.TRUST_PROXY_HEADERS else ''
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', 'unknown')


class ClientAddressRateThrottle(SimpleRateThrottle):
    """Build an IP-keyed throttle for public endpoints."""

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': client_address(request)}


class LoginRateThrottle(SimpleRateThrottle):
    """Limit attempts per client and account without exposing account data in cache keys."""

    scope = 'login'

    def get_cache_key(self, request, view):
        payload = request.data if isinstance(request.data, dict) else {}
        account = str(payload.get('email') or payload.get('account') or '').strip().casefold()
        identity = f'{client_address(request)}:{account}' if account else client_address(request)
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': digest}

    @classmethod
    def clear_after_success(cls, request):
        """A valid login proves credential ownership; retain only failed-attempt history."""
        throttle = cls()
        key = throttle.get_cache_key(request, None)
        if key:
            cache.delete(key)


class LoginBurstRateThrottle(ClientAddressRateThrottle):
    """Retain an IP-wide ceiling so rotating account names cannot bypass protection."""

    scope = 'login_burst'


class RegistrationRateThrottle(ClientAddressRateThrottle):
    """Keep public account applications from consuming the login budget."""

    scope = 'registration'


class PasswordSetupRateThrottle(ClientAddressRateThrottle):
    """Limit one-time password setup attempts independently of login."""

    scope = 'password_setup'


class PasswordChangeRateThrottle(SimpleRateThrottle):
    """Limit a signed-in user's password changes independently of login attempts."""

    scope = 'password_change'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}
