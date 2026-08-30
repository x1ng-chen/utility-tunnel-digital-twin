from rest_framework.throttling import SimpleRateThrottle
from django.conf import settings
import hashlib


def client_address(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '') if settings.TRUST_PROXY_HEADERS else ''
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', 'unknown')


class LoginRateThrottle(SimpleRateThrottle):
    """Limit attempts per client and account without exposing account data in cache keys."""

    scope = 'login'

    def get_cache_key(self, request, view):
        payload = request.data if isinstance(request.data, dict) else {}
        account = str(payload.get('email') or payload.get('account') or '').strip().casefold()
        identity = f'{client_address(request)}:{account}' if account else client_address(request)
        digest = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        return self.cache_format % {'scope': self.scope, 'ident': digest}


class LoginBurstRateThrottle(SimpleRateThrottle):
    """Retain an IP-wide ceiling so rotating account names cannot bypass protection."""

    scope = 'login_burst'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': client_address(request)}


class PasswordChangeRateThrottle(SimpleRateThrottle):
    """Limit a signed-in user's password changes independently of login attempts."""

    scope = 'password_change'

    def get_cache_key(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': request.user.pk}
