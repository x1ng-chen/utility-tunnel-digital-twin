import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from operations.agent_operations import STATIONS, station_snapshot


class Command(BaseCommand):
    help = 'Read-only 31-sensor design vs current registry/telemetry/model audit. Never seeds or migrates data.'

    def add_arguments(self, parser):
        parser.add_argument('--station', choices=[*STATIONS, 'all'], default='all')
        parser.add_argument('--output', help='Optional JSON file; existing files are not overwritten.')
        parser.add_argument('--strict', action='store_true', help='Fail if any expected sensor lacks usable observations or a verified active-model node.')

    def handle(self, *args, **options):
        result = station_snapshot(options['station'])
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False, default=str)+'\n'
        if options['output']:
            path = Path(options['output'])
            try:
                with path.open('x', encoding='utf-8') as file:
                    file.write(rendered)
            except OSError as exc:
                raise CommandError('Cannot create report; check path or choose a new filename.') from exc
            self.stdout.write(f'Wrote read-only inspection report: {path}')
        else:
            self.stdout.write(rendered)
        if options['strict'] and any(i['observation_state'] != 'usable_observations'
                or i['mapping_status'] != 'active_model_node_verified' for i in result['items']):
            raise CommandError('Inspection has missing, unusable or unmapped sensors; see report. This is not hardware acceptance.')
