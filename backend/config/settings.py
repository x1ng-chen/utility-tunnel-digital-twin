from pathlib import Path
import os
from urllib.parse import parse_qs, unquote, urlparse
from dotenv import load_dotenv
from corsheaders.defaults import default_headers


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').lower()
IS_PRODUCTION = DJANGO_ENV == 'production'
# Fail closed for deployments that do not explicitly provide a debug flag.
# Local development can opt in through backend/.env.example.
DEBUG = DJANGO_ENV != 'production' and os.getenv('DJANGO_DEBUG', 'false').lower() in {'1', 'true', 'yes'}
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if DJANGO_ENV == 'production' and len(SECRET_KEY) < 32:
    raise RuntimeError('DJANGO_SECRET_KEY must contain at least 32 characters in production.')
if not SECRET_KEY:
    SECRET_KEY = 'local-development-only-change-me'
ALLOWED_HOSTS = [host.strip() for host in os.getenv('DJANGO_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'operations',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'operations.middleware.RequestIdMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


def database_config() -> dict:
    database_url = os.getenv('DATABASE_URL', '').strip()
    if not database_url:
        if IS_PRODUCTION:
            raise RuntimeError('DATABASE_URL is required in production; SQLite fallback is development-only.')
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('DATABASE_URL must use postgresql:// or postgres://')
    query = parse_qs(parsed.query)
    sslmode = os.getenv('DB_SSLMODE', '').strip() or query.get('sslmode', ['prefer'])[-1]
    if IS_PRODUCTION and sslmode not in {'require', 'verify-ca', 'verify-full'}:
        raise RuntimeError('Production DATABASE_URL must use sslmode=require, verify-ca, or verify-full.')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '127.0.0.1',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        'OPTIONS': {'sslmode': sslmode},
    }


DATABASES = {'default': database_config()}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173').split(',') if origin.strip()]
CORS_ALLOW_CREDENTIALS = os.getenv('CORS_ALLOW_CREDENTIALS', 'false').lower() in {'1', 'true', 'yes'}
CORS_ALLOW_HEADERS = [*default_headers, 'x-request-id']
API_TOKEN_TTL_SECONDS = int(os.getenv('API_TOKEN_TTL_SECONDS', '900'))
if API_TOKEN_TTL_SECONDS <= 0:
    raise ValueError('API_TOKEN_TTL_SECONDS must be greater than zero.')
TRUST_PROXY_HEADERS = os.getenv('DJANGO_TRUST_PROXY_HEADERS', 'false').lower() in {'1', 'true', 'yes'}
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['operations.authentication.BearerTokenAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'EXCEPTION_HANDLER': 'config.api.api_exception_handler',
    'DEFAULT_THROTTLE_RATES': {'login': os.getenv('LOGIN_RATE_LIMIT', '10/min')},
}
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_RESOURCE_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'no-referrer'
SECURE_SSL_REDIRECT = IS_PRODUCTION and os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'true').lower() in {'1', 'true', 'yes'}
SECURE_HSTS_SECONDS = 31536000 if IS_PRODUCTION and os.getenv('DJANGO_ENABLE_HSTS', 'true').lower() in {'1', 'true', 'yes'} else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') if os.getenv('DJANGO_TRUST_PROXY_SSL', 'false').lower() in {'1', 'true', 'yes'} else None
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'json': {'()': 'config.logging.JsonFormatter'}},
    'handlers': {'console_json': {'class': 'logging.StreamHandler', 'formatter': 'json'}},
    'loggers': {
        'operations.request': {'handlers': ['console_json'], 'level': 'INFO', 'propagate': False},
        'django.request': {'handlers': ['console_json'], 'level': 'WARNING', 'propagate': False},
    },
}
