"""Release smoke recordings stay separate from all previous paid evaluations."""
from .sprint_eval_settings import *  # noqa: F403

AGENT_EVAL_ROOT = BASE_DIR.parent / '.agent-eval-sprint/release-20261029/.agent-eval-sprint'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': AGENT_EVAL_ROOT / 'db.sqlite3'}}
MEDIA_ROOT = AGENT_EVAL_ROOT / 'media'
# First validate the existing three-agent workflow without an experimental router.
ANYJEV_ENABLED = False
