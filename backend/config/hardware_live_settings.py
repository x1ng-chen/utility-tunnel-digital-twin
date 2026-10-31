"""Local, receive-only commissioning profile; never selects a business/demo DB."""
import os
from pathlib import Path
from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[2] / '.hardware-live'
load_dotenv(_root / '.env', override=False)
from .settings import *  # noqa: E402,F403
from django.core.exceptions import ImproperlyConfigured

if IS_PRODUCTION:  # noqa: F405
    raise ImproperlyConfigured('The hardware commissioning profile is local-only.')
HARDWARE_LIVE_MODE = True
AGENT_EVALUATION_MODE = False
AGENT_DEMO_MODE = False
HARDWARE_LIVE_ROOT = _root
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
    'NAME': _root / 'db.sqlite3', 'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
MEDIA_ROOT = _root / 'media'
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'hardware-live'}}
CONTROLLER_COMMAND_PROTOCOL = 'four-controller-v2'
# This sprint receives telemetry only. Neither an operator nor an administrator
# may bypass this profile's command block. Paid model calls stay postponed.
DEEPSEEK_API_KEY = ''
MQTT_COMMAND_BROKER_PORT = 1
CONNECTIVITY_MONITOR_URL = 'http://127.0.0.1:8000/api/internal/connectivity/reconcile/'
CONNECTIVITY_RECONCILE_INTERVAL_SECONDS = 5
DEVICE_OFFLINE_MIN_GRACE_SECONDS = 15
DEVICE_OFFLINE_GRACE_MULTIPLIER = 3
