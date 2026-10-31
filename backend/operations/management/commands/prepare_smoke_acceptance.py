"""Enable the digital MQ-2 smoke alarm in the isolated commissioning DB."""
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from operations.hardware_live import hardware_live_enabled
from operations.models import AuditLog, Threshold


class Command(BaseCommand):
    help = 'Enable smoke.alarm=1 for physical MQ-2/highlight acceptance only.'

    @transaction.atomic
    def handle(self, *args, **options):
        root = Path(getattr(settings, 'HARDWARE_LIVE_ROOT', settings.BASE_DIR/'invalid')).resolve()
        if not hardware_live_enabled() or connection.vendor != 'sqlite' or Path(connection.settings_dict['NAME']).resolve() != root/'db.sqlite3':
            raise CommandError('Use config.hardware_live_settings and its dedicated database only.')
        rule, created = Threshold.objects.get_or_create(key='smoke.alarm', defaults={
            'label': '烟雾数字输入', 'warning': .5, 'alarm': 1, 'unit': 'bool'})
        if (rule.warning, rule.alarm, rule.unit) != (.5, 1, 'bool'):
            raise CommandError('An existing smoke rule differs; it was not overwritten.')
        if created:
            AuditLog.objects.create(action='hardware.smoke_acceptance_rule_configured', resource_type='threshold',
                resource_id='smoke.alarm', detail={'warning': .5, 'alarm': 1, 'unit': 'bool',
                    'reason': 'User-requested physical smoke/highlight acceptance',
                    'observationsSeeded': 0, 'hardwareCommands': 0, 'modelCalls': 0})
        self.stdout.write(json.dumps({'key': rule.key, 'warning': rule.warning, 'alarm': rule.alarm,
            'unit': rule.unit, 'created': created, 'observationsSeeded': 0, 'hardwareCommands': 0}))
