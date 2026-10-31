"""Exact V24 installation for isolated software sandboxes, never hardware DBs."""
import hashlib
from pathlib import Path
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.db import transaction
from rest_framework.test import APIClient
from .agent_context import require_evaluation_database
from .models import Asset, HardwareBinding, TwinModelRelease
from .sprint_models import AgentRun
from .twin_presentation import BASE_INVENTORY, V24


def sandbox_root():
    root = require_evaluation_database()
    if (getattr(settings, 'HARDWARE_LIVE_MODE', False) or root.name not in {
            '.agent-demo', '.agent-capabilities', '.agent-eval', '.agent-eval-sprint', '.agent-eval-guards'}):
        raise CommandError('V24 software installation requires a dedicated demo/evaluation database.')
    return root


def v24_model_file(model_file=None):
    path = Path(model_file) if model_file else settings.BASE_DIR.parent / 'frontend/public/models/utility-tunnel-v24.glb'
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CommandError('V24 GLB unavailable; fetch frontend/public/models/utility-tunnel-v24.glb with Git LFS.') from exc
    if data[:4] != b'glTF' or hashlib.sha256(data).hexdigest() != V24['modelSha256']:
        raise CommandError('V24 GLB hash mismatch or Git LFS pointer; no sandbox data changed.')
    return path, data


def install_v24_demo_model(administrator, model_file=None):
    """Upgrade presentation only; keep IDs, observations, cases and run history.

    Model metadata owners are deliberately ignored.  All identity and controller
    relationships are from the frozen wire catalog and reviewed V24 adapter.
    """
    sandbox_root()
    path, data = v24_model_file(model_file)
    expected = {b['assetCode'] for b in BASE_INVENTORY['bindings']} | set(V24['controllerMeshes'])
    assets = {a.code: a for a in Asset.objects.filter(code__in=expected)}
    if set(assets) != expected:
        raise CommandError('The sandbox must contain all 31 sensors and four controllers before V24 installation.')
    allowed_blank = set()
    from .agent_context import data_context
    if data_context().get('scenarioId') == 'INS-04':
        allowed_blank.add('MQ4-05')
    for b in BASE_INVENTORY['bindings']:
        code = b['assetCode']
        known = {b['targetNode'], V24['sensorMeshes'][code]}
        if code in allowed_blank:
            known.add('')
        if assets[code].mesh not in known:
            raise CommandError(f'{code}: unknown sandbox mapping; refusing an implicit identity migration.')
    for code, mesh in V24['controllerMeshes'].items():
        if assets[code].mesh not in {mesh, BASE_INVENTORY['controllerLegacyMeshes'][code]}:
            raise CommandError(f'{code}: unknown controller geometry mapping.')
    desired = {}
    for b in BASE_INVENTORY['bindings']:
        code = b['assetCode']; tag = V24['sensorModelTags'][code]
        label = tag if tag == b['physicalTag'] else f'{tag}（采集 {b["physicalTag"]}）'
        desired[code] = {'mesh': '' if code in allowed_blank and assets[code].mesh == '' else V24['sensorMeshes'][code],
            'zone': V24['sensorStations'][code], 'name': f'模拟测试 {label} · {V24["sensorStations"][code]}'}
    for code, mesh in V24['controllerMeshes'].items():
        desired[code] = {'mesh': mesh, 'zone': '控制器', 'name': f'模拟测试 {code}'}
    active = TwinModelRelease.objects.filter(status='active').first()
    changed = [code for code, fields in desired.items() if any(getattr(assets[code], key) != value for key, value in fields.items())]
    upgrading = bool(changed or not active or active.sha256 != V24['modelSha256'])
    if upgrading and AgentRun.objects.filter(status__in=['queued', 'running']).exists():
        raise CommandError('Finish or cancel active Agent jobs before changing their model presentation.')
    release = TwinModelRelease.objects.filter(sha256=V24['modelSha256']).first()
    if release:
        try:
            with release.model_file.open('rb') as stored:
                intact = hashlib.sha256(stored.read()).hexdigest() == V24['modelSha256']
        except OSError:
            intact = False
        if not intact:
            raise CommandError('Existing V24 storage differs from its recorded hash; inspect before replacing it.')
        if not upgrading:
            return {'modelVersion': release.version, 'modelSha256': V24['modelSha256'],
                'presentationRevision': V24['revision'], 'changedAssets': 0,
                'sensors': 31, 'hardwareCommands': 0, 'modelCalls': 0}
    client = APIClient(HTTP_HOST='127.0.0.1'); client.force_authenticate(administrator)
    created_file = None
    try:
        with transaction.atomic():
            if upgrading and AgentRun.objects.filter(status__in=['queued', 'running']).exists():
                raise CommandError('Finish or cancel active Agent jobs before changing their model presentation.')
            # Clear the cyclic sensor/controller aliases in one operation.
            # Do not feed prior renamed values back through a permutation.
            before_bindings = list(HardwareBinding.objects.order_by('id').values())
            Asset.objects.filter(code__in=expected).update(mesh='')
            for code, fields in desired.items():
                asset = assets[code]
                for key, value in fields.items(): setattr(asset, key, value)
                if code in changed: asset.version += 1
                asset.save(update_fields=['mesh', 'zone', 'name', 'version', 'updated_at'])
            if not release:
                response = client.post('/api/twin/models/', {'version': 'agent-demo-v24',
                    'file': SimpleUploadedFile(path.name, data, content_type='model/gltf-binary')}, format='multipart')
                if response.status_code != 201:
                    raise CommandError(f'V24 sandbox upload rejected: HTTP {response.status_code}.')
                release = TwinModelRelease.objects.get(pk=response.data['id'])
                created_file = (release.model_file.storage, release.model_file.name)
            # Missing-binding scenarios are invalidated after the real upload and
            # activation gates pass, never replaced with forged node metadata.
            for code in allowed_blank:
                Asset.objects.filter(code=code).update(mesh=V24['sensorMeshes'][code])
            response = client.post(f'/api/twin/models/{release.pk}/activate/')
            if response.status_code != 200:
                raise CommandError(f'V24 sandbox activation rejected: HTTP {response.status_code}.')
            for code in allowed_blank:
                Asset.objects.filter(code=code).update(mesh=desired[code]['mesh'])
            if before_bindings != list(HardwareBinding.objects.order_by('id').values()):
                raise CommandError('Hardware bindings changed during software presentation installation.')
    except Exception:
        if created_file:
            created_file[0].delete(created_file[1])
        raise
    return {'modelVersion': release.version, 'modelSha256': V24['modelSha256'],
        'presentationRevision': V24['revision'], 'changedAssets': len(changed),
        'sensors': 31, 'hardwareCommands': 0, 'modelCalls': 0}
