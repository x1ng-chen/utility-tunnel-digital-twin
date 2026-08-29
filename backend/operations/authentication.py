from datetime import timedelta
from secrets import compare_digest

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import BaseAuthentication, TokenAuthentication

from .models import Profile


class IngestApiKeyAuthentication(BaseAuthentication):
    """Authenticate the telemetry gateway without a reusable human password."""

    header = 'X-Ingest-Key'

    def authenticate_header(self, request):
        # Keep unauthenticated API responses at HTTP 401 even though this
        # machine scheme is evaluated before bearer-token authentication.
        return 'IngestKey'

    def authenticate(self, request):
        supplied = request.headers.get(self.header, '')
        if not supplied:
            return None
        expected = settings.INGEST_API_KEY
        if not expected or not compare_digest(supplied, expected):
            raise AuthenticationFailed('Invalid ingest API key.')
        try:
            user = User.objects.select_related('profile').get(
                username=settings.INGEST_PRINCIPAL_USERNAME,
                is_active=True,
                profile__role=Profile.Role.INGEST,
            )
        except User.DoesNotExist as exc:
            raise AuthenticationFailed('Ingest principal is not provisioned.') from exc
        return user, 'ingest-api-key'


class BearerTokenAuthentication(TokenAuthentication):
    keyword = 'Bearer'

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        expires_at = token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS)
        if expires_at <= timezone.now():
            token.delete()
            raise AuthenticationFailed('Token has expired.')
        return user, token
