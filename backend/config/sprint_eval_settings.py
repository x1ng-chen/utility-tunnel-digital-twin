"""New evaluation recordings never reset the previous .agent-eval database."""
from .agent_eval_settings import *  # noqa: F403
AGENT_EVAL_ROOT = BASE_DIR.parent / '.agent-eval-sprint'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True, exist_ok=True)
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':AGENT_EVAL_ROOT/'db.sqlite3'}}
MEDIA_ROOT = AGENT_EVAL_ROOT/'media'
CONTROLLER_COMMAND_PROTOCOL = 'four-controller-v2'
