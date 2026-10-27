from django.core.management.base import BaseCommand
from operations.agent_scenarios import CASES, seed_scenario


class Command(BaseCommand):
    help = 'Seed/reset ONLY the explicitly selected local Agent evaluation database.'

    def add_arguments(self, parser):
        parser.add_argument('--case', choices=CASES, default='INS-01')
        parser.add_argument('--reset', action='store_true')
        parser.add_argument('--without-model', action='store_true')

    def handle(self, *args, **options):
        import json
        state = seed_scenario(options['case'], options['reset'], not options['without_model'])
        self.stdout.write(json.dumps(state, ensure_ascii=False))
