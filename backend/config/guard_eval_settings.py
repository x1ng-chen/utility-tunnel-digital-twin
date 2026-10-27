"""Dedicated guardrail evaluation database; no business/demo/old evaluation reset."""
from .sprint_eval_settings import *  # noqa: F403
AGENT_EVAL_ROOT=BASE_DIR.parent/'.agent-eval-guards'  # noqa: F405
AGENT_EVAL_ROOT.mkdir(parents=True,exist_ok=True)
DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':AGENT_EVAL_ROOT/'db.sqlite3'}}
MEDIA_ROOT=AGENT_EVAL_ROOT/'media'
AGENT_EXPERIENCE_ENABLED=False
