from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from operations.models import Alert, Asset, WorkOrder


class Command(BaseCommand):
    help = 'Retire the physically removed CTRL-02 SHT30 in the hardware-live database.'

    @transaction.atomic
    def handle(self, *args, **options):
        root = getattr(settings, 'HARDWARE_LIVE_ROOT', None)
        if (not getattr(settings, 'HARDWARE_LIVE_MODE', False) or root is None
                or connection.vendor != 'sqlite'
                or Path(connection.settings_dict['NAME']).resolve() != Path(root).resolve() / 'db.sqlite3'):
            raise CommandError('Use the isolated hardware-live database.')
        asset = Asset.objects.select_for_update().filter(
            code='ENV-04', hardware_binding__endpoint='ut/v1/CTRL-02/telemetry',
        ).first()
        if asset is None:
            raise CommandError('Expected CTRL-02 ENV-04 binding is missing.')
        if not asset.is_active:
            self.stdout.write('ENV-04 already inactive.')
            return
        open_alerts = asset.alerts.filter(status__in=[Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED])
        if (open_alerts.exclude(rule_key='connectivity.offline').exists()
                or asset.work_orders.exclude(status__in=[WorkOrder.Status.COMPLETED, WorkOrder.Status.CANCELLED]).exists()):
            raise CommandError('ENV-04 has an active non-connectivity incident or work order.')
        now = timezone.now()
        for alert in open_alerts:
            alert.status = Alert.Status.RESOLVED
            alert.resolved_at = now
            alert.detail += '\n设备于 2026-11-03 停用，关闭通信告警；未观察到采样恢复。'
            alert.save(update_fields=['status', 'resolved_at', 'detail'])
        asset.is_active = False
        asset.version += 1
        asset.save(update_fields=['is_active', 'version', 'updated_at'])
        self.stdout.write('ENV-04 inactive; identity, binding and historical readings retained.')
