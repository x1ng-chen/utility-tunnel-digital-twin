"""Install the exact V20 model and its presentation mapping, preserving wire IDs."""
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
from operations.hardware_live import INVENTORY, hardware_live_enabled
from operations.models import Asset, AuditLog, HardwareBinding, Profile, TwinModelRelease
from operations.twin_presentation import V20


class Command(BaseCommand):
    help = 'Back up the hardware commissioning DB, then install V20 visual numbering without changing telemetry ownership.'

    def handle(self, *args, **options):
        root = Path(getattr(settings, 'HARDWARE_LIVE_ROOT', settings.BASE_DIR/'invalid')).resolve()
        db_path = Path(str(connection.settings_dict['NAME'])).resolve()
        if not hardware_live_enabled() or connection.vendor != 'sqlite' or db_path != root/'db.sqlite3':
            raise CommandError('Use the dedicated config.hardware_live_settings database only.')
        source = settings.BASE_DIR.parent / V20['modelPath']
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != V20['modelSha256']:
            raise CommandError('V20 GLB hash does not match the reviewed presentation descriptor.')
        backup = root / ('before-v20-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as original, sqlite3.connect(backup) as saved:
            original.backup(saved)
        actor = User.objects.get(username='hardware-model-import')
        if actor.has_usable_password() or actor.is_active or Profile.objects.get(user=actor).role != 'administrator':
            raise CommandError('Unexpected model importer account; inspect it before applying changes.')
        client = APIClient(HTTP_HOST='127.0.0.1'); client.force_authenticate(actor)
        with transaction.atomic():
            expected = {b['assetCode'] for b in INVENTORY['bindings']}
            assets = {a.code:a for a in Asset.objects.select_for_update().filter(code__in=expected | set(V20['controllerMeshes']))}
            if set(assets) != expected | set(V20['controllerMeshes']):
                raise CommandError('The current four-controller asset registry is incomplete.')
            binding_before = list(HardwareBinding.objects.values('id','asset_id','protocol','device_identifier','endpoint'))
            changes = []
            # Clear the old cyclic mesh aliases inside this transaction before
            # assigning canonical controller names; the unique constraint stays active.
            Asset.objects.filter(code__in=V20['controllerMeshes']).update(mesh='')
            for code, mesh in V20['controllerMeshes'].items():
                asset = assets[code]
                before = {'zone':asset.zone, 'mesh':asset.mesh, 'name':asset.name}
                asset.mesh = mesh
                asset.version += 1
                asset.save(update_fields=['mesh','version','updated_at'])
                changes.append({'assetCode':code, 'before':before, 'after':{'zone':asset.zone,'mesh':mesh,'name':asset.name}})
            for b in INVENTORY['bindings']:
                asset = assets[b['assetCode']]
                before = {'zone':asset.zone, 'mesh':asset.mesh, 'name':asset.name}
                if asset.mesh != b['targetNode']:
                    raise CommandError(f'{asset.code}: sensor identity mismatch; refusing to relabel another node.')
                asset.zone = V20['sensorStations'][asset.code]
                asset.name = f'{b["physicalTag"]} · {asset.zone}'
                asset.version += 1
                asset.save(update_fields=['zone','name','version','updated_at'])
                changes.append({'assetCode':asset.code, 'before':before, 'after':{'zone':asset.zone,'mesh':asset.mesh,'name':asset.name}})
            release = TwinModelRelease.objects.filter(sha256=V20['modelSha256']).first()
            if not release:
                response = client.post('/api/twin/models/', {'version':V20['modelVersion'],
                    'file':SimpleUploadedFile(source.name, data, content_type='model/gltf-binary')}, format='multipart')
                if response.status_code != 201:
                    raise CommandError(f'V20 model upload rejected: HTTP {response.status_code}')
                release = TwinModelRelease.objects.get(pk=response.data['id'])
            response = client.post(f'/api/twin/models/{release.pk}/activate/')
            if response.status_code != 200:
                raise CommandError(f'V20 model activation rejected: HTTP {response.status_code}')
            if binding_before != list(HardwareBinding.objects.values('id','asset_id','protocol','device_identifier','endpoint')):
                raise CommandError('Hardware bindings unexpectedly changed; rolling back the database transaction.')
            AuditLog.objects.create(actor=actor, action='twin.presentation.v20_installed', resource_type='twin_model_release',
                resource_id=str(release.pk), detail={'presentationRevision':V20['revision'],
                    'wireLayoutVersionUnchanged':INVENTORY['revision'], 'changes':changes,
                    'controllerOwnershipChanged':False, 'modelSha256':V20['modelSha256'], 'backupFile':backup.name})
        result = {'modelVersion':release.version, 'sha256':release.sha256, 'presentationRevision':V20['revision'],
            'wireLayoutVersion':INVENTORY['revision'], 'controllerOwnershipChanged':False,
            'sensors':31, 'backup':str(backup), 'hardwareCommands':0, 'modelCalls':0}
        (root/'v20-installation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(json.dumps(result,ensure_ascii=True))
