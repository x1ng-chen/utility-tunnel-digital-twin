"""Server-owned provenance and acceptance context; never accepts a client flag."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection


def evaluation_enabled():
    return bool(getattr(settings, 'AGENT_EVALUATION_MODE', False) and not settings.IS_PRODUCTION)


def require_evaluation_database():
    root = Path(getattr(settings, 'AGENT_EVAL_ROOT', settings.BASE_DIR / 'invalid')).resolve()
    db = connection.settings_dict
    if (not evaluation_enabled() or db['ENGINE'] != 'django.db.backends.sqlite3'
            or Path(str(db['NAME'])).resolve() != root / 'db.sqlite3'):
        raise CommandError('Only config.agent_eval_settings and its dedicated evaluation database may be reset.')
    return root


def data_context():
    if not evaluation_enabled():
        return {'mode': 'database_observation', 'label': '数据库观测；现场状态需核验', 'scenarioId': None}
    scenario = {}
    try:
        path = Path(settings.AGENT_EVAL_ROOT) / 'scenario.json'
        if path.stat().st_size < 4096:
            scenario = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, AttributeError):
        pass
    generation=None
    if getattr(settings,'AGENT_DEMO_MODE',False):
        from .sprint_models import DemoSession
        session=DemoSession.objects.filter(pk=1).first()
        if session:
            scenario={'caseId':session.case_id,'seededAt':None}
            generation=str(session.generation)
    return {'mode': 'simulated_test', 'label': '模拟测试 · 隔离验收库，非现场实时',
            'scenarioId': scenario.get('caseId'), 'seededAt': scenario.get('seededAt'),'generation':generation}


def observation_valid(reading):
    return reading.get('scenario_usable', False) if evaluation_enabled() else reading.get('usable', False)
