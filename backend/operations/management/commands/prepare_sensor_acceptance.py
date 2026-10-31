"""Idempotently install non-calibrated commissioning rules in the isolated DB."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import connection, transaction
from operations.hardware_live import hardware_live_enabled
from operations.hardware_alarm_config import RULES, policy
from operations.models import AuditLog, Threshold


def install_rules():
    """Fail atomically on unreviewed conflicting settings; never seed telemetry."""
    with transaction.atomic():
        for spec in RULES:
            existing = Threshold.objects.filter(key=spec['key']).first()
            if existing and (existing.warning,existing.alarm,existing.unit) != (spec['warning'],spec['alarm'],spec['unit']):
                raise CommandError(f'{spec["key"]}: existing settings differ; no rules were overwritten.')
        created = []
        for spec in RULES:
            key = spec['key']
            _, added = Threshold.objects.get_or_create(key=key, defaults={k:v for k,v in spec.items() if k!='key'})
            if added:
                created.append(key)
                AuditLog.objects.create(action='hardware.sensor_acceptance_rule_configured', resource_type='threshold',
                    resource_id=key, detail={**spec, 'policyRevision':policy()['revision'],
                        'reason':'User requested remaining physical sensor alarm rules; provisional commissioning limits.',
                        'observationsSeeded':0, 'hardwareCommands':0, 'modelCalls':0})
        return created


class Command(BaseCommand):
    help = 'Configure digital, environment and raw-ADC acceptance rules; oxygen remains blocked pending calibration.'

    def handle(self, *args, **options):
        root = Path(getattr(settings, 'HARDWARE_LIVE_ROOT', settings.BASE_DIR/'invalid')).resolve()
        db = Path(connection.settings_dict['NAME']).resolve()
        if not hardware_live_enabled() or connection.vendor!='sqlite' or db!=root/'db.sqlite3':
            raise CommandError('Use config.hardware_live_settings and its dedicated database only.')
        backup = root/('before-sensor-rules-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        with sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True) as original, sqlite3.connect(backup) as saved:
            original.backup(saved)
        created = install_rules()
        report = {**policy(), 'createdRuleKeys':created, 'backup':str(backup),
            'configuredAt':datetime.now(timezone.utc).isoformat(), 'observationsSeeded':0,
            'hardwareCommands':0, 'modelCalls':0}
        (root/'sensor-alarm-rules.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps({k:v for k,v in report.items() if k not in {'sensors','rules'}},ensure_ascii=True))
