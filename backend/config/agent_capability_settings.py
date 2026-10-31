"""New capability sandbox; never selects business or older acceptance databases."""
from .agent_demo_settings import *  # noqa: F403
AGENT_EVAL_ROOT = BASE_DIR.parent / '.agent-capabilities'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': AGENT_EVAL_ROOT / 'db.sqlite3',
    'OPTIONS': {'timeout': 20, 'transaction_mode': 'IMMEDIATE'}}}
MEDIA_ROOT = AGENT_EVAL_ROOT / 'media'
# Keep existing paid-task guards and keys unchanged. This setting does not turn them on.
