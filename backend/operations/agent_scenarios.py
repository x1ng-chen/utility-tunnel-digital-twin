"""Reproducible acceptance fixtures, strictly restricted to the local sandbox."""
import json
import secrets
from datetime import timedelta
from pathlib import Path
from django.contrib.auth.models import User
from django.core.management import call_command, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient
from .agent_context import require_evaluation_database
from .agent_operations import BINDINGS, INVENTORY, SENSOR_METRICS
from .models import Alert, Asset, AuditLog, HardwareBinding, Profile, Telemetry, WorkOrder

CASES = ('INS-01', 'INS-02', 'INS-03', 'INS-04', 'DIA-01', 'DIA-02', 'DIA-03', 'DIA-04',
         'ORD-01', 'ORD-02', 'ORD-03', 'ORD-04')
UNITS = {'temperature': '°C', 'humidity': '%RH', 'smoke.alarm': 'bool', 'flame.alarm': 'bool',
         'level.detected': 'bool', 'rotational.speed': 'rpm', 'motor.current': 'A', 'supply.voltage': 'V'}


def seed_scenario(case_id, reset=False, with_model=True):
    root = require_evaluation_database()
    if case_id not in CASES:
        raise CommandError('Unknown acceptance case.')
    if Asset.objects.exists() or User.objects.exists():
        if not reset:
            raise CommandError('Sandbox already contains data. Use --reset explicitly.')
        call_command('flush', interactive=False, verbosity=0)
    credential_path = root / 'users.json'
    passwords = json.loads(credential_path.read_text(encoding='utf-8')) if credential_path.exists() else {
        role: secrets.token_urlsafe(24) for role in ('administrator', 'operator', 'viewer', 'ingest')}
    root.mkdir(parents=True, exist_ok=True)
    credential_path.write_text(json.dumps(passwords, indent=2), encoding='utf-8')
    now = timezone.now()
    with transaction.atomic():
        users = {}
        for role, password in passwords.items():
            user = User.objects.create_user(username=f'agent-eval-{role}', email=f'agent-eval-{role}', password=password)
            Profile.objects.update_or_create(user=user, defaults={'role': role, 'display_name': f'模拟测试 {role}'})
            users[role] = user
        for b in BINDINGS:
            asset = Asset.objects.create(code=b['assetCode'], name=f"模拟测试 {b['physicalTag']}", zone=b['stationId'],
                asset_type='sensor', mesh=b['targetNode'], integration_status='pending_verification')
            bind(asset, b['controllerId'], now)
            for group in SENSOR_METRICS[b['physicalTag'].split('-')[0]]:
                key = group[0]
                value = 24 if key == 'temperature' else 55 if key == 'humidity' else 150 if key.endswith('.raw') else 0
                reading(asset, key, value, now - timedelta(seconds=60))
                reading(asset, key, value, now - timedelta(seconds=1))
        for code, mesh in INVENTORY['controllerLegacyMeshes'].items():
            asset = Asset.objects.create(code=code, name=f'模拟测试 {code}（模型文字旧编号）', zone='控制器',
                asset_type='controller', mesh=mesh)
            bind(asset, code, now)
        for code, controller in INVENTORY['fanControllers'].items():
            asset = Asset.objects.create(code=code, name=f'模拟测试 {code}', zone='排风设备', asset_type='fan', mesh=code)
            bind(asset, controller, now)
            for key, value in [('rotational.speed', 1200), ('motor.current', .3), ('supply.voltage', 12)]:
                reading(asset, key, value, now - timedelta(seconds=1))
            AuditLog.objects.create(actor=users['operator'], action='controller.command.sent', resource_type='asset',
                resource_id=controller, detail={'action': 'fan.start', 'assetCode': code,
                    'outcome': 'simulated_requested', 'protocolVersion': 'four-controller-eval-v1',
                    'ackReason': 'SIMULATED_TEST: not sent to hardware'})
        target = Asset.objects.get(code='MQ4-05')
        if case_id != 'INS-01':
            reading(target, 'methane.raw', 450, now)
            Alert.objects.create(code='SIM-P5-001', asset=target, severity='warning', category='模拟测试',
                title='模拟测试：P5单测点原始量变化', detail='SIMULATED_TEST；非已标定浓度，不证明实际危险工况。', opened_at=now)
        if case_id == 'INS-02':
            offline_controller('CTRL-03', now)
        elif case_id == 'INS-03':
            Telemetry.objects.filter(asset=target).update(quality='bad')
            Telemetry.objects.filter(asset__code='CO-05').update(recorded_at=now + timedelta(minutes=1))
        elif case_id == 'INS-04':
            pass  # Invalidate only after a legitimate model activation below.
        elif case_id == 'DIA-01':
            Telemetry.objects.filter(asset__code='FAN-01').delete()
            for key in ('rotational.speed', 'motor.current', 'supply.voltage'):
                reading(Asset.objects.get(code='FAN-01'), key, 0, now)
        elif case_id == 'DIA-02':
            Telemetry.objects.filter(asset__code='FAN-01', metric_key='rotational.speed').delete()
        elif case_id == 'DIA-04':
            offline_controller('CTRL-03', now)
            Telemetry.objects.filter(asset__code='FAN-01').update(recorded_at=now-timedelta(hours=1))
        elif case_id in ('ORD-02', 'ORD-04'):
            WorkOrder.objects.create(code='WO-SIM-001', asset=target, title='模拟测试：P5待复核工单',
                status='pending_review', created_by=users['operator'])
            if case_id == 'ORD-04':
                WorkOrder.objects.filter(code='WO-SIM-001').update(updated_at=now-timedelta(minutes=2))
    if with_model:
        install_model(users['administrator'])
    if case_id == 'INS-04':
        Asset.objects.filter(code='MQ4-05').update(mesh='')
    state = {'caseId': case_id, 'seededAt': now.isoformat(), 'layoutVersion': INVENTORY['revision'],
             'source': 'SIMULATED_TEST', 'modelInstalled': with_model}
    (root / 'scenario.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    return state


def bind(asset, controller, now):
    HardwareBinding.objects.create(asset=asset, protocol='manual', device_identifier=f'sim:{asset.code}',
        endpoint=f'SIMULATED_TEST:{controller}', status='connected', last_heartbeat_at=now,
        expected_interval_seconds=60)


def reading(asset, key, value, sampled_at):
    return Telemetry.objects.create(asset=asset, event_id=f'simulation:{secrets.token_hex(12)}', metric_key=key,
        metric=key, value=value, unit=UNITS.get(key, 'adc'), recorded_at=sampled_at)


def offline_controller(code, now):
    members = [b['assetCode'] for b in BINDINGS if b['controllerId'] == code] + [code]
    HardwareBinding.objects.filter(asset__code__in=members).update(last_heartbeat_at=now-timedelta(hours=1))
    Telemetry.objects.filter(asset__code__in=members).update(recorded_at=now-timedelta(hours=1))


def install_model(admin):
    """Exercise the actual administrator upload/activation gates; no forged inventory."""
    path = Path(__file__).resolve().parents[2] / 'model/square-five-station-v17-fan-ready/square-five-station-v17-fan-ready.glb'
    if not path.exists() or path.read_bytes()[:4] != b'glTF':
        raise CommandError('V17 GLB is not available; fetch its LFS object or use --without-model explicitly.')
    client = APIClient(HTTP_HOST='127.0.0.1'); client.force_authenticate(admin)
    response = client.post('/api/twin/models/', {'version': 'agent-eval-v17',
        'file': SimpleUploadedFile(path.name, path.read_bytes(), content_type='model/gltf-binary')}, format='multipart')
    if response.status_code != 201:
        raise CommandError(f'Model upload validation failed ({response.status_code}): {response.data}')
    response = client.post(f"/api/twin/models/{response.data['id']}/activate/")
    if response.status_code != 200:
        raise CommandError(f'Model activation rejected ({response.status_code}): {response.data}')
