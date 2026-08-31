import json

from django.core.management.base import BaseCommand, CommandError

from operations.models import Asset, TwinModelRelease
from operations.release_hygiene import clean_release_test_data, release_test_data_summary


class Command(BaseCommand):
    help = 'Check that automated-test records are absent and the active twin model is deliverable.'

    def add_arguments(self, parser):
        parser.add_argument('--clean-test-data', action='store_true', help='Remove only reserved E2E namespaces before checking.')
        parser.add_argument('--require-model', action='store_true', help='Fail unless a compatible active twin model exists.')
        parser.add_argument('--format', choices=('text', 'json'), default='text')

    def handle(self, *args, **options):
        if options['clean_test_data']:
            clean_release_test_data()
        test_data = release_test_data_summary()
        active_release = TwinModelRelease.objects.filter(status=TwinModelRelease.Status.ACTIVE).first()
        missing_mesh_codes = list(Asset.objects.filter(is_active=True, mesh='').order_by('code').values_list('code', flat=True))
        report = {
            'clean': not any(test_data.values()),
            'testData': test_data,
            'model': {
                'required': options['require_model'],
                'activeVersion': active_release.version if active_release else None,
                'compatible': bool(active_release and active_release.is_compatible),
                'missingMeshCodes': missing_mesh_codes,
            },
        }
        if options['format'] == 'json':
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write(f"测试数据：{'干净' if report['clean'] else '存在残留'}")
            self.stdout.write(f"三维模型：{report['model']['activeVersion'] or '未启用'}")
        blockers = []
        if not report['clean']:
            blockers.append('检测到浏览器测试数据残留')
        if missing_mesh_codes:
            blockers.append('存在未配置三维节点名称的设备')
        if options['require_model'] and not report['model']['compatible']:
            blockers.append('没有兼容且已启用的三维模型')
        if blockers:
            raise CommandError('；'.join(blockers))
        self.stdout.write(self.style.SUCCESS('发布数据检查通过。'))
