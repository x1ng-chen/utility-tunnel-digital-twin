import json

from django.core.management.base import BaseCommand

from operations.connectivity import reconcile_connectivity


class Command(BaseCommand):
    help = 'Reconcile device heartbeats into online/offline asset state and communication alerts.'

    def handle(self, *args, **options):
        result = reconcile_connectivity()
        self.stdout.write(json.dumps({
            'online': result.online,
            'offline': result.offline,
            'alertsCreated': result.alerts_created,
            'alertsResolved': result.alerts_resolved,
        }, ensure_ascii=False))
