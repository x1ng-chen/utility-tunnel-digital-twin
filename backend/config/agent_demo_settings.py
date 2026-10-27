"""Local demonstration only. Never imports or selects the business database."""
from .agent_eval_settings import *  # noqa: F403

AGENT_DEMO_MODE = True
AGENT_EVAL_ROOT = BASE_DIR.parent / '.agent-demo'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3',
    'NAME': AGENT_EVAL_ROOT / 'db.sqlite3', 'OPTIONS': {'timeout': 20,'transaction_mode':'IMMEDIATE'}}}
MEDIA_ROOT = AGENT_EVAL_ROOT / 'media'
CONTROLLER_COMMAND_PROTOCOL = 'four-controller-v2'
CORS_ALLOWED_ORIGINS = [*CORS_ALLOWED_ORIGINS, 'http://127.0.0.1:5187']  # noqa: F405
WEBSOCKET_ALLOWED_ORIGINS = [*WEBSOCKET_ALLOWED_ORIGINS, 'http://127.0.0.1:5187']  # noqa: F405
