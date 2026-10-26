"""Export equal-source packets and blank human/LLM comparison records."""
import csv
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from operations.agent_context import require_evaluation_database


def raw_evidence(value):
    if isinstance(value, dict):
        # Do not leak the Agent's derived hypotheses or a fixture's answer key
        # into a plain-model/manual baseline.
        return {k: raw_evidence(v) for k, v in value.items()
                if k not in {'diagnosis', 'candidate_causes', 'scenarioId', 'caseId'}}
    if isinstance(value, list):
        return [raw_evidence(v) for v in value]
    return value


class Command(BaseCommand):
    help = 'Export M/L/A comparison packets without inventing human timing or accuracy.'

    def add_arguments(self, parser):
        parser.add_argument('records', help='A JSONL file produced by evaluate_agent --live')

    def handle(self, *args, **options):
        root = require_evaluation_database()
        source = Path(options['records']).resolve()
        if not source.is_relative_to(root.resolve()) or source.suffix != '.jsonl':
            raise CommandError('Only a local sandbox JSONL recording may be exported.')
        destination = source.with_suffix('.comparison')
        destination.mkdir(exist_ok=False)
        records = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
        fields = ['case', 'group', 'buildFingerprint', 'preparationSeconds', 'taskSeconds', 'passed',
            'factErrors', 'locationAttempts', 'locationCorrect', 'tokenUsage', 'cost', 'reviewer', 'status']
        with (destination / 'results.csv').open('x', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
            for index, record in enumerate(records):
                response = record['response']
                packet = {'id': f'TASK-{index+1:02}', 'question': record['prompt'],
                    'source': 'SIMULATED_TEST', 'evidence': raw_evidence(response.get('evidence', [])),
                    'preparationMode': 'automatic_export_not_human_preparation',
                    'fairness': 'Use this exact frozen evidence and the same referenced runbooks for M and L. Do not provide expected outcomes.'}
                (destination / f'TASK-{index+1:02}.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding='utf-8')
                for group in ('M', 'L', 'A'):
                    writer.writerow({'case': record['caseId'], 'group': group,
                        'buildFingerprint': record.get('buildFingerprint', 'unrecorded'),
                        'status': record['status'] if group == 'A' else 'NOT_RUN',
                        'tokenUsage': json.dumps(response.get('runtime', {}).get('tokens')) if group == 'A' else ''})
        self.stdout.write(str(destination))
