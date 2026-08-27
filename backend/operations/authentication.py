from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    keyword = 'Bearer'

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        expires_at = token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS)
        if expires_at <= timezone.now():
            token.delete()
            raise AuthenticationFailed('Token has expired.')
        return user, token
