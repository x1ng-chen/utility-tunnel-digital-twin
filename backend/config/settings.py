from pathlib import Path
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from corsheaders.defaults import default_headers


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
DJANGO_ENV = os.getenv('DJANGO_ENV', 'development').lower()
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
        return {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}
    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('DATABASE_URL must use postgresql:// or postgres://')
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': parsed.path.lstrip('/'),
        'USER': parsed.username or '',
        'PASSWORD': parsed.password or '',
        'HOST': parsed.hostname or '127.0.0.1',
        'PORT': str(parsed.port or 5432),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
        'OPTIONS': {'sslmode': os.getenv('DB_SSLMODE', 'prefer')},
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
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [*default_headers, 'x-request-id']
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['operations.authentication.BearerTokenAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticated'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
}
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'no-referrer'
