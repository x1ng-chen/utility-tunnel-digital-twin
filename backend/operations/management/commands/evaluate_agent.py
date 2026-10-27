"""Opt-in paid acceptance run. No model call without --live."""
import json
import hashlib
from datetime import datetime, timezone
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from operations.agent_context import require_evaluation_database
from operations.agent_evaluation import entries, evaluate_entry


class Command(BaseCommand):
    help = 'List or explicitly run real-model Agent cases in the isolated database.'

    def add_arguments(self, parser):
        parser.add_argument('--suite', choices=['smoke', 'composite', 'regression'], default='smoke')
        parser.add_argument('--case')
        parser.add_argument('--live', action='store_true')
        parser.add_argument('--confirm-test-proposals', action='store_true')
        parser.add_argument('--key-env-file', help='Read only DEEPSEEK_API_KEY from this local dotenv file, never echo it.')

    def handle(self, *args, **options):
        root = require_evaluation_database()
        cases = [e for e in entries(options['suite']) if not options['case'] or e['id'] in options['case'].split(',')]
        if not cases:
            raise CommandError('No matching case.')
        if not options['live']:
            self.stdout.write(json.dumps({'mode': 'DRY_RUN_NO_MODEL_CALLS', 'cases': cases}, ensure_ascii=False))
            return
        if options['key_env_file']:
            from dotenv import dotenv_values
            settings.DEEPSEEK_API_KEY = (dotenv_values(options['key_env_file']).get('DEEPSEEK_API_KEY') or '').strip()
        if not settings.DEEPSEEK_API_KEY:
            raise CommandError('No server model key configured.')
        output = root / 'runs' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.jsonl')
        output.parent.mkdir(parents=True, exist_ok=True)
        sources = sorted((settings.BASE_DIR / 'operations').glob('agent*.py')) + [settings.BASE_DIR / 'operations/ai_assistant.py'] + sorted((settings.BASE_DIR / 'operations/agent_catalog').glob('*.json'))
        fingerprint = hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sources)).hexdigest()
        with output.open('x', encoding='utf-8') as f:
            for case in cases:
                result = evaluate_entry(case, options['confirm_test_proposals'])
                result['buildFingerprint'] = fingerprint
                result['suite'] = options['suite']
                f.write(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False) + '\n'); f.flush()
                self.stdout.write(json.dumps({'caseId': case['id'], 'status': result['status'],
                    'httpStatus': result['httpStatus'], 'checks': result['automatedChecks']}, ensure_ascii=False))
                if result['httpStatus'] in (401, 402, 429, 503) or result['response'].get('error') == 'assistant_not_configured':
                    self.stdout.write('Model access unavailable; stopping paid run. Remaining cases are NOT_RUN.')
                    break
        self.stdout.write(f'Records: {output}; facts require explicit review; cost is unknown until billing reconciliation.')
