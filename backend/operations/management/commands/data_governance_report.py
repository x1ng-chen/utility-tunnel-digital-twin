import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max, Min
from django.utils import timezone

from operations.models import AuditLog, ReportExport, Telemetry


class Command(BaseCommand):
    help = 'Report data-retention candidates without modifying business records.'

    def add_arguments(self, parser):
        parser.add_argument('--telemetry-days', type=int, default=90, help='Telemetry retention review period in days.')
        parser.add_argument('--audit-days', type=int, default=365, help='Audit retention review period in days.')
        parser.add_argument('--export-days', type=int, default=365, help='Export-record retention review period in days.')
        parser.add_argument('--format', choices=('text', 'json'), default='text', help='Output format.')

    def handle(self, *args, **options):
        periods = {
            'telemetry': options['telemetry_days'],
            'audit': options['audit_days'],
            'exports': options['export_days'],
        }
        invalid = [name for name, days in periods.items() if days < 1]
        if invalid:
            raise CommandError(f"Retention periods must be positive: {', '.join(invalid)}")

        now = timezone.now()
        report = {
            'generatedAt': now.isoformat(),
            'mode': 'read-only',
            'collections': {
                'telemetry': self.collection(Telemetry, 'recorded_at', periods['telemetry'], now),
                'audit': self.collection(AuditLog, 'occurred_at', periods['audit'], now),
                'reportExports': self.collection(ReportExport, 'created_at', periods['exports'], now),
            },
        }
        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
            return

        self.stdout.write(self.style.SUCCESS('Data governance report (read-only)'))
        for name, item in report['collections'].items():
            self.stdout.write(
                f"- {name}: total={item['total']}, retentionDays={item['retentionDays']}, "
                f"reviewCandidates={item['reviewCandidates']}, oldest={item['oldestAt'] or '-'}, newest={item['newestAt'] or '-'}"
            )
        self.stdout.write('No records were deleted. Review candidates before approving a separate, audited retention release.')

    @staticmethod
    def collection(model, field: str, retention_days: int, now):
        cutoff = now - timedelta(days=retention_days)
        aggregation = model.objects.aggregate(oldest=Min(field), newest=Max(field))
        return {
            'total': model.objects.count(),
            'retentionDays': retention_days,
            'cutoffAt': cutoff.isoformat(),
            'reviewCandidates': model.objects.filter(**{f'{field}__lt': cutoff}).count(),
            'oldestAt': aggregation['oldest'].isoformat() if aggregation['oldest'] else None,
            'newestAt': aggregation['newest'].isoformat() if aggregation['newest'] else None,
        }
