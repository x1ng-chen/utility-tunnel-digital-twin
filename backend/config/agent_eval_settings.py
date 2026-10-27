"""Explicit, local-only Agent acceptance sandbox. Never selects the business DB."""
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

if IS_PRODUCTION:  # noqa: F405
    raise ImproperlyConfigured('Agent evaluation settings cannot run in production.')
AGENT_EVALUATION_MODE = True
AGENT_EVAL_ROOT = BASE_DIR.parent / '.agent-eval'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': AGENT_EVAL_ROOT / 'db.sqlite3'}}
MEDIA_ROOT = AGENT_EVAL_ROOT / 'media'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'agent-eval'}}
# The sandbox never connects an MQTT publisher, even if an authenticated user
# attempts to use the existing controller endpoint.
MQTT_COMMAND_BROKER_HOST = '127.0.0.1'
MQTT_COMMAND_BROKER_PORT = 1

CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, 'http://127.0.0.1:5186']
WEBSOCKET_ALLOWED_ORIGINS = [*WEBSOCKET_ALLOWED_ORIGINS, 'http://127.0.0.1:5186']

REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {**REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'], 'ai_assistant': '200/hour'}}
