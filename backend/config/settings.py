from pathlib import Path
import os
from urllib.parse import parse_qs, unquote, urlparse
from dotenv import load_dotenv
from corsheaders.defaults import default_headers


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').strip().lower()
if DJANGO_ENV not in {'development', 'test', 'production'}:
    raise ValueError('DJANGO_ENV must be development, test, or production.')
IS_PRODUCTION = DJANGO_ENV == 'production'
# Fail closed for deployments that do not explicitly provide a debug flag.
# Local development can opt in through backend/.env.example.
DEBUG = DJANGO_ENV != 'production' and os.getenv('DJANGO_DEBUG', 'false').lower() in {'1', 'true', 'yes'}
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if DJANGO_ENV == 'production' and len(SECRET_KEY) < 32:
    raise RuntimeError('DJANGO_SECRET_KEY must contain at least 32 characters in production.')
if not SECRET_KEY:
    SECRET_KEY = 'local-development-only-change-me'
raw_allowed_hosts = os.getenv('DJANGO_ALLOWED_HOSTS', '').strip()
if IS_PRODUCTION and not raw_allowed_hosts:
    raise RuntimeError('DJANGO_ALLOWED_HOSTS is required in production.')
ALLOWED_HOSTS = [host.strip() for host in (raw_allowed_hosts or '127.0.0.1,localhost').split(',') if host.strip()]
if IS_PRODUCTION and '*' in ALLOWED_HOSTS:
    raise RuntimeError('DJANGO_ALLOWED_HOSTS must not contain a wildcard in production.')

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
    try:
        hostname = parsed.hostname
        port = parsed.port or 5432
    except ValueError as exc:
        raise ValueError('DATABASE_URL contains an invalid host or port.') from exc
    database_name = unquote(parsed.path.lstrip('/')).strip()
    username = unquote(parsed.username or '').strip()
    if not hostname or not username or not database_name:
        raise ValueError('DATABASE_URL must include a database name, username, and host.')
    query = parse_qs(parsed.query)
    sslmode = os.getenv('DB_SSLMODE', '').strip() or query.get('sslmode', ['prefer'])[-1]
    if IS_PRODUCTION and sslmode not in {'require', 'verify-ca', 'verify-full'}:
        raise RuntimeError('Production DATABASE_URL must use sslmode=require, verify-ca, or verify-full.')
    try:
        conn_max_age = int(os.getenv('DB_CONN_MAX_AGE', '60'))
    except ValueError as exc:
        raise ValueError('DB_CONN_MAX_AGE must be a non-negative integer.') from exc
    if conn_max_age < 0:
        raise ValueError('DB_CONN_MAX_AGE must be a non-negative integer.')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': database_name,
        'USER': username,
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': hostname,
        'PORT': str(port),
        'CONN_MAX_AGE': conn_max_age,
        'OPTIONS': {'sslmode': sslmode},
    }


DATABASES = {'default': database_config()}


def parse_origins(raw: str, default: str, setting_name: str) -> list[str]:
    origins = [origin.strip() for origin in (raw or default).split(',') if origin.strip()]
    for origin in origins:
        parsed = urlparse(origin)
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError(f'{setting_name} contains an invalid port.') from exc
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.params or parsed.query or parsed.fragment:
            raise ValueError(f'{setting_name} must contain origins such as https://ops.example.com without a path.')
    return origins

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

raw_cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '').strip()
if IS_PRODUCTION and not raw_cors_origins:
    raise RuntimeError('CORS_ALLOWED_ORIGINS is required in production.')
CORS_ALLOWED_ORIGINS = parse_origins(raw_cors_origins, 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173', 'CORS_ALLOWED_ORIGINS')
if IS_PRODUCTION and any(not origin.lower().startswith('https://') for origin in CORS_ALLOWED_ORIGINS):
    raise RuntimeError('Production CORS_ALLOWED_ORIGINS must use HTTPS origins.')
raw_csrf_origins = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '').strip()
if IS_PRODUCTION and not raw_csrf_origins:
    raise RuntimeError('DJANGO_CSRF_TRUSTED_ORIGINS is required in production.')
CSRF_TRUSTED_ORIGINS = parse_origins(raw_csrf_origins, '', 'DJANGO_CSRF_TRUSTED_ORIGINS')
if IS_PRODUCTION and any(not origin.lower().startswith('https://') for origin in CSRF_TRUSTED_ORIGINS):
    raise RuntimeError('Production DJANGO_CSRF_TRUSTED_ORIGINS must use HTTPS origins.')
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
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DJANGO_MAX_REQUEST_BYTES', str(2 * 1024 * 1024)))
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(os.getenv('DJANGO_MAX_REQUEST_FIELDS', '1000'))
if DATA_UPLOAD_MAX_MEMORY_SIZE <= 0 or DATA_UPLOAD_MAX_NUMBER_FIELDS <= 0:
    raise ValueError('Django request limits must be greater than zero.')
CACHE_BACKEND = os.getenv('DJANGO_CACHE_BACKEND', 'django.core.cache.backends.locmem.LocMemCache').strip()
CACHE_LOCATION = os.getenv('DJANGO_CACHE_LOCATION', 'utility-tunnel-default-cache').strip()
if IS_PRODUCTION and (not CACHE_BACKEND or CACHE_BACKEND.endswith('LocMemCache')):
    raise RuntimeError('Production requires a shared Django cache backend; configure DJANGO_CACHE_BACKEND.')
if not CACHE_LOCATION:
    raise ValueError('DJANGO_CACHE_LOCATION must not be empty.')
CACHES = {'default': {'BACKEND': CACHE_BACKEND, 'LOCATION': CACHE_LOCATION}}
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
