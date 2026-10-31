"""Apply the user's three flame corrections to the isolated hardware DB only."""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.hardware_live_settings'
import django
django.setup()
from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection, transaction
from operations.models import Asset, AuditLog, HardwareBinding, TwinModelRelease
from operations.twin_presentation import V24, runtime_inventory

runtime = ROOT / '.hardware-live'
db_path = Path(connection.settings_dict['NAME']).resolve()
assert settings.HARDWARE_LIVE_MODE and db_path == (runtime / 'db.sqlite3').resolve()
targets = {'FLAME-01': ('FLAME-04', 'P1'), 'FLAME-02': ('FLAME-01', 'P2'),
           'FLAME-04': ('FLAME-02', 'P4')}
release = TwinModelRelease.objects.get(status='active')
assert release.sha256 == V24['modelSha256']
assert all(code in release.node_names for code in targets)
backup = runtime / ('before-flame-rebind-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
with sqlite3.connect(f'file:{db_path.as_posix()}?mode=ro', uri=True) as original, sqlite3.connect(backup) as saved:
    original.backup(saved)

with transaction.atomic():
    rows = {a.code: a for a in Asset.objects.select_for_update().filter(code__in=targets)}
    assert set(rows) == set(targets)
    bindings_before = list(HardwareBinding.objects.order_by('id').values())
    others_before = list(Asset.objects.exclude(code__in=targets).order_by('id').values('id', 'code', 'name', 'mesh', 'zone', 'version'))
    changes = []
    for code, (previous_mesh, station) in targets.items():
        assert rows[code].mesh in {previous_mesh, code}, f'{code}: unexpected existing mesh'
        assert V24['sensorMeshes'][code] == code and V24['sensorStations'][code] == station
    Asset.objects.filter(code__in=targets).update(mesh='')
    for code, (_, station) in targets.items():
        asset = rows[code]
        before = {'mesh': asset.mesh, 'zone': asset.zone, 'name': asset.name}
        after = {'mesh': code, 'zone': station, 'name': f'{code} · {station}'}
        asset.mesh, asset.zone, asset.name = after['mesh'], after['zone'], after['name']
        if before != after:
            asset.version += 1
            changes.append({'assetCode': code, 'before': before, 'after': after})
        asset.save(update_fields=['mesh', 'zone', 'name', 'version', 'updated_at'])
    assert bindings_before == list(HardwareBinding.objects.order_by('id').values())
    assert others_before == list(Asset.objects.exclude(code__in=targets).order_by('id').values('id', 'code', 'name', 'mesh', 'zone', 'version'))
    inventory = runtime_inventory(release)
    assert len(inventory['bindings']) == len({b['targetNode'] for b in inventory['bindings']}) == 31
    AuditLog.objects.create(actor=User.objects.get(username='hardware-model-import'),
        action='twin.presentation.flame_rebound', resource_type='twin_model_release', resource_id=str(release.pk),
        detail={'presentationRevision': V24['revision'], 'changes': changes, 'backupFile': backup.name,
                'authorization': 'User confirmed FLAME-01/02/04 bind to identically numbered model probes.',
                'hardwareBindingsChanged': False, 'hardwareCommands': 0})
report = {'presentationRevision': V24['revision'], 'changes': changes, 'backup': str(backup),
          'otherAssetsChanged': False, 'hardwareBindingsChanged': False, 'hardwareCommands': 0}
(runtime / 'flame-rebinding.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
