"""Activate exact V24 geometry with a bijective wire-to-model presentation map."""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from rest_framework.test import APIClient
from operations.hardware_live import hardware_live_enabled
from operations.models import Asset, AuditLog, HardwareBinding, Profile, TwinModelRelease
from operations.twin_presentation import BASE_INVENTORY, V24, V24_UNIFIED

# Exact mappings from presentation 20261029.1, before the user corrected these
# three flame locations. Permit this known predecessor for deliberate upgrades.
PREVIOUS_V24_FLAME_MESHES = {'FLAME-01': 'FLAME-04', 'FLAME-02': 'FLAME-01', 'FLAME-04': 'FLAME-02'}

def validate_registry(assets):
    expected = {b['assetCode'] for b in BASE_INVENTORY['bindings']} | set(V24['controllerMeshes'])
    if set(assets) != expected:
        raise CommandError('The current four-controller sensor registry is incomplete.')
    for binding in BASE_INVENTORY['bindings']:
        code = binding['assetCode']
        # A previously verified release or original wire mapping is allowed.
        # Unknown manual mappings must be inspected instead of silently replaced.
        if assets[code].mesh not in {binding['targetNode'], V24['sensorMeshes'][code],
                                    V24_UNIFIED['sensorMeshes'][code],
                                    PREVIOUS_V24_FLAME_MESHES.get(code)}:
            raise CommandError(f'{code}: unknown prior sensor mapping; no replacement applied.')
    for code, target in V24['controllerMeshes'].items():
        if assets[code].mesh != target:
            raise CommandError(f'{code}: controller geometry identity differs; inspect before replacement.')


class Command(BaseCommand):
    help = 'Back up the isolated hardware DB and activate exact V24; preserve asset IDs and MQTT bindings.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=Path, help='Optional exact V24 GLB; its SHA256 must match the descriptor.')
        parser.add_argument('--unified-numbering', action='store_true', help='Use same-number physical sensor/model labels, including central O2-03.')

    def handle(self, *args, **options):
        descriptor = V24_UNIFIED if options.get('unified_numbering') else V24
        root = Path(getattr(settings, 'HARDWARE_LIVE_ROOT', settings.BASE_DIR / 'invalid')).resolve()
        db_path = Path(str(connection.settings_dict['NAME'])).resolve()
        if not hardware_live_enabled() or connection.vendor != 'sqlite' or db_path != root / 'db.sqlite3':
            raise CommandError('Use the dedicated config.hardware_live_settings database only.')
        source = options.get('file') or settings.BASE_DIR.parent / descriptor['modelPath']
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != descriptor['modelSha256']:
            raise CommandError('V24 GLB hash mismatch (or Git LFS pointer); no replacement applied.')
        expected = {b['assetCode'] for b in BASE_INVENTORY['bindings']} | set(V24['controllerMeshes'])
        validate_registry({a.code: a for a in Asset.objects.filter(code__in=expected)})
        actor = User.objects.get(username='hardware-model-import')
        if actor.has_usable_password() or actor.is_active or Profile.objects.get(user=actor).role != 'administrator':
            raise CommandError('Unexpected model importer account; inspect before applying changes.')
        backup = root / ('before-v24-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
        with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as original, sqlite3.connect(backup) as saved:
            original.backup(saved)
        client = APIClient(HTTP_HOST='127.0.0.1')
        client.force_authenticate(actor)
        changes = []
        with transaction.atomic():
            assets = {a.code: a for a in Asset.objects.select_for_update().filter(code__in=expected)}
            validate_registry(assets)
            before_bindings = list(HardwareBinding.objects.order_by('id').values())
            # Simultaneous cyclic renumbering: release unique mesh aliases first.
            Asset.objects.filter(code__in=descriptor['sensorMeshes']).update(mesh='')
            for binding in BASE_INVENTORY['bindings']:
                asset = assets[binding['assetCode']]
                before = {'mesh': asset.mesh, 'zone': asset.zone, 'name': asset.name}
                model_tag = descriptor['sensorModelTags'][asset.code]
                asset.mesh = descriptor['sensorMeshes'][asset.code]
                asset.zone = descriptor['sensorStations'][asset.code]
                label = model_tag if model_tag == binding['physicalTag'] else f'{model_tag}（采集 {binding["physicalTag"]}）'
                asset.name = f'{label} · {asset.zone}'
                if before != {'mesh': asset.mesh, 'zone': asset.zone, 'name': asset.name}:
                    asset.version += 1
                    changes.append({'assetCode': asset.code, 'before': before,
                        'after': {'mesh': asset.mesh, 'zone': asset.zone, 'name': asset.name}})
                asset.save(update_fields=['mesh', 'zone', 'name', 'version', 'updated_at'])
            release = TwinModelRelease.objects.filter(sha256=descriptor['modelSha256']).first()
            if not release:
                response = client.post('/api/twin/models/', {'version': descriptor['modelVersion'],
                    'file': SimpleUploadedFile(source.name, data, content_type='model/gltf-binary')}, format='multipart')
                if response.status_code != 201:
                    raise CommandError(f'V24 upload rejected: HTTP {response.status_code}')
                release = TwinModelRelease.objects.get(pk=response.data['id'])
            response = client.post(f'/api/twin/models/{release.pk}/activate/')
            if response.status_code != 200:
                raise CommandError(f'V24 activation rejected: HTTP {response.status_code}')
            if before_bindings != list(HardwareBinding.objects.order_by('id').values()):
                raise CommandError('Hardware bindings changed unexpectedly; rolling back.')
            AuditLog.objects.create(actor=actor, action='twin.presentation.v24_installed', resource_type='twin_model_release',
                resource_id=str(release.pk), detail={'presentationRevision': descriptor['revision'], 'changes': changes,
                    'wireLayoutVersionUnchanged': BASE_INVENTORY['revision'], 'controllerOwnershipChanged': False,
                    'assetCodesChanged': False, 'modelSha256': descriptor['modelSha256'], 'backupFile': backup.name})
        result = {'modelVersion': release.version, 'sha256': release.sha256, 'sensors': 31,
            'presentationRevision': descriptor['revision'], 'changedAssets': len(changes), 'backup': str(backup),
            'assetCodesChanged': False, 'controllerOwnershipChanged': False, 'hardwareCommands': 0, 'modelCalls': 0}
        (root / 'v24-installation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps(result, ensure_ascii=True))
