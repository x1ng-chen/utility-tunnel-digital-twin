"""Idempotent current software demo bootstrap without resetting histories."""
import json
from django.core.management.base import BaseCommand
from operations.sprint_demo import initialize
from operations.twin_presentation import runtime_inventory


class Command(BaseCommand):
    help = 'Initialize or upgrade the dedicated software demo to V24, preserving cases and old tasks.'

    def handle(self, *args, **options):
        session = initialize(with_model=True)
        inventory = runtime_inventory()
        self.stdout.write(json.dumps({'source': 'SIMULATED_TEST',
            'presentationRevision': inventory.get('presentationRevision'),
            'layoutVersion': inventory['revision'], 'session': session,
            'hardwareCommands': 0, 'modelCalls': 0}, default=str))
