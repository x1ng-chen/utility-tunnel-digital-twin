"""Initialize inventory only; never seed measurements or import demo fixtures."""
import json
import secrets
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection, transaction
from operations.hardware_live import INVENTORY, hardware_live_enabled
from operations.models import Asset, HardwareBinding, Profile


class Command(BaseCommand):
    help = 'Prepare the isolated, receive-only four-controller commissioning database without fake measurements.'

    def add_arguments(self, parser):
        parser.add_argument('--install-model', action='store_true', help='Validate and activate the existing V17 GLB; do not rebuild it.')

    def handle(self, *args, **options):
        from operations.twin_presentation import runtime_inventory
        inventory = runtime_inventory()
        root = Path(getattr(settings, 'HARDWARE_LIVE_ROOT', settings.BASE_DIR / 'invalid')).resolve()
        if (not hardware_live_enabled() or connection.vendor != 'sqlite'
                or Path(connection.settings_dict['NAME']).resolve() != root / 'db.sqlite3'):
            raise CommandError('Use config.hardware_live_settings and its dedicated database only.')
        root.mkdir(parents=True, exist_ok=True)
        access_path = root / 'access.json'
        if User.objects.filter(is_superuser=True).exists():
            raise CommandError('Unexpected superuser in the isolated hardware database; inspect it before proceeding.')
        access = json.loads(access_path.read_text(encoding='utf-8')) if access_path.exists() else {
            'account': 'hardware-operator', 'password': secrets.token_urlsafe(24)}
        with transaction.atomic():
            user, created = User.objects.get_or_create(username=access['account'],
                defaults={'email': access['account'], 'is_staff': False, 'is_superuser': False})
            if created:
                user.set_password(access['password']); user.save(update_fields=['password'])
            Profile.objects.get_or_create(user=user, defaults={'role': 'operator', 'display_name': '实物联调运维员'})
            records = [(b['assetCode'], b['physicalTag'], b['stationId'], b['targetNode'], b['controllerId'], 'sensor')
                for b in inventory['bindings']]
            records += [(code, code, '控制器', mesh, code, 'controller')
                for code, mesh in inventory['controllerLegacyMeshes'].items()]
            records += [(code, code, '排风设备', code, controller, 'fan')
                for code, controller in INVENTORY['fanControllers'].items()]
            expected_codes = {r[0] for r in records}
            if Asset.objects.exclude(code__in=expected_codes).exists():
                raise CommandError('Unexpected assets in hardware database; no data was removed.')
            for code, tag, station, mesh, controller, kind in records:
                asset, _ = Asset.objects.get_or_create(code=code, defaults={
                    'name': f'{tag} · {station}', 'zone': station, 'asset_type': kind,
                    'status': 'unknown', 'mesh': mesh, 'integration_status': 'pending_verification',
                    'installation_note': f'{INVENTORY["revision"]}; {controller}; 实物联调，逐路接线/触发/恢复及标定待验收。'})
                if asset.mesh != mesh or asset.zone != station:
                    raise CommandError(f'{code}: existing identity differs; refusing to overwrite.')
                binding, _ = HardwareBinding.objects.get_or_create(asset=asset, defaults={
                    'protocol': 'mqtt', 'device_identifier': f'physical:{controller}:{code}',
                    'endpoint': f'ut/v1/{controller}/telemetry', 'expected_interval_seconds': 2,
                    'status': 'reserved'})
                if binding.endpoint != f'ut/v1/{controller}/telemetry':
                    raise CommandError(f'{code}: existing endpoint differs; refusing to overwrite.')
            call_command('configure_ingest_principal', verbosity=0, stdout=self.stdout)
        access_path.write_text(json.dumps(access, ensure_ascii=False, indent=2), encoding='utf-8')
        if options['install_model']:
            from operations.models import TwinModelRelease
            if not TwinModelRelease.objects.filter(status='active').exists():
                from django.core.files.uploadedfile import SimpleUploadedFile
                from rest_framework.test import APIClient
                importer, _ = User.objects.get_or_create(username='hardware-model-import',
                    defaults={'is_active': False, 'is_staff': False, 'is_superuser': False})
                importer.set_unusable_password(); importer.save(update_fields=['password'])
                Profile.objects.get_or_create(user=importer,
                    defaults={'role': 'administrator', 'display_name': 'CLI模型初始化（非人工验收）'})
                path = settings.BASE_DIR.parent / 'model/square-five-station-v17-fan-ready/square-five-station-v17-fan-ready.glb'
                client = APIClient(HTTP_HOST='127.0.0.1'); client.force_authenticate(importer)
                response = client.post('/api/twin/models/', {'version': 'hardware-live-v17',
                    'file': SimpleUploadedFile(path.name, path.read_bytes(), content_type='model/gltf-binary')}, format='multipart')
                if response.status_code != 201:
                    raise CommandError(f'V17 model validation failed: {response.status_code}')
                response = client.post(f'/api/twin/models/{response.data["id"]}/activate/')
                if response.status_code != 200:
                    raise CommandError(f'V17 model activation failed: {response.status_code}')
        self.stdout.write(json.dumps({'profile': 'hardware-live', 'sensors': 31, 'controllers': 4,
            'fans': 2, 'assets': Asset.objects.count(), 'measurementsSeeded': 0,
            'credentialsFile': str(access_path), 'hardwareControl': 'disabled'}, ensure_ascii=False))
