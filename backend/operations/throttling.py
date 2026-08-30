from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class ClientAddressRateThrottle(SimpleRateThrottle):
    """Build an IP-keyed throttle without trusting spoofable proxy headers."""

    def get_cache_key(self, request, view):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '') if settings.TRUST_PROXY_HEADERS else ''
        client = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', 'unknown')
        return self.cache_format % {'scope': self.scope, 'ident': client}


class LoginRateThrottle(ClientAddressRateThrottle):
    """Limit password login attempts per client address."""

    scope = 'login'


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
