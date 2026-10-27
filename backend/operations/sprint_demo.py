"""No MQTT, sockets, hardware publisher or model calls belong in this module."""
import uuid
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIClient
from .agent_context import require_evaluation_database
from .agent_scenarios import CASES, seed_scenario
from .agent_operations import BINDINGS, INVENTORY, SENSOR_METRICS
from .models import Alert, Asset, HardwareBinding, Telemetry, Threshold, WorkOrder
from .sprint_models import AgentRun, DemoSession, SimulatedAction


def guard():
    root = require_evaluation_database()
    if not getattr(settings, 'AGENT_DEMO_MODE', False) or root.resolve() != (settings.BASE_DIR.parent / '.agent-demo').resolve():
        raise CommandError('Only the dedicated .agent-demo database supports demonstration control.')
    return root


def session_state():
    guard()
    s, _ = DemoSession.objects.get_or_create(pk=1)
    return {'generation': str(s.generation), 'caseId': s.case_id, 'running': s.running, 'phase': s.phase,
        'tick': s.tick, 'lastTickAt': s.last_tick_at, 'source': 'SIMULATED_TEST', 'outputs': s.outputs}


def initialize(with_model=True):
    guard()
    if not Asset.objects.exists():
        seed_scenario('INS-01', with_model=with_model)
    Threshold.objects.update_or_create(key='methane.raw', defaults={'label': '模拟原始量变化规则，非浓度阈值',
        'unit': 'adc', 'warning': 400, 'alarm': 700})
    return session_state()


@transaction.atomic
def control(action, case_id=None):
    guard()
    if not isinstance(action,str) or action not in {'start', 'pause', 'advance', 'reset'} or (case_id is not None and (not isinstance(case_id,str) or case_id not in CASES)):
        raise ValueError('未知场景或操作。')
    s = DemoSession.objects.select_for_update().get(pk=1)
    if action == 'reset':
        if AgentRun.objects.filter(status__in=['running', 'queued']).exists():
            raise ValueError('请先完成或取消当前Agent任务，再重置场景。')
        # Keep users, immutable run snapshots, action histories and evaluation records.
        WorkOrder.objects.all().delete()
        Alert.objects.all().delete()
        Telemetry.objects.all().delete()
        s.generation, s.case_id, s.phase, s.tick, s.outputs = uuid.uuid4(), case_id or 'INS-01', 0, 0, {}
        SimulatedAction.objects.filter(state='proposed').update(state='expired')
        s.running = False
        # INS-04 can intentionally remove just this test binding.
        for b in BINDINGS:
            Asset.objects.filter(code=b['assetCode']).update(mesh=b['targetNode'])
        if s.case_id == 'INS-04':
            Asset.objects.filter(code='MQ4-05').update(mesh='')
        if s.case_id in {'ORD-02','ORD-04'}:
            WorkOrder.objects.create(code='WO-SIM-001',asset=Asset.objects.get(code='MQ4-05'),
                title='模拟测试：P5待复核工单',status='pending_review',
                created_by=User.objects.get(username='agent-eval-operator'))
    elif action == 'advance':
        s.phase = min(s.phase + 1, 3)
    else:
        s.running = action == 'start'
    s.save()
    return session_state()


@transaction.atomic
def tick():
    guard()
    s = DemoSession.objects.select_for_update().get(pk=1)
    if not s.running:
        return False
    now = timezone.now()
    if s.last_tick_at and (now - s.last_tick_at).total_seconds() < 1.8:
        return False
    s.tick += 1
    changed = s.case_id != 'INS-01' or s.phase in {1, 2}
    recovered = s.phase == 3
    readings = []
    offline = s.case_id in {'INS-02', 'DIA-04'} and not recovered
    for b in BINDINGS:
        if offline and b['controllerId'] == 'CTRL-03':
            continue
        for group in SENSOR_METRICS[b['physicalTag'].split('-')[0]]:
            key = group[0]
            value = 24 if key == 'temperature' else 55 if key == 'humidity' else 150 if key.endswith('.raw') else 0
            if b['assetCode'] == 'MQ4-05' and changed and not recovered:
                value = 450
            quality, at = 'good', now
            if s.case_id == 'INS-03' and not recovered:
                if b['assetCode'] == 'MQ4-05': quality = 'bad'
                if b['assetCode'] == 'CO-05': at += timedelta(minutes=1)
            readings.append(row(s, b['assetCode'], key, value, at, quality))
    for fan, controller in INVENTORY['fanControllers'].items():
        output = s.outputs.get(fan, {'power': True, 'pwm': 50})
        rpm = 1200 * output['pwm'] / 50 if output['power'] else 0
        values = {'rotational.speed': rpm, 'motor.current': .3 if rpm else 0,
                  'supply.voltage': 12 if output['power'] else 0, 'power': 3.6 if rpm else 0}
        if fan == 'FAN-01' and s.case_id == 'DIA-01' and not recovered:
            values = {k: 0 for k in values}
        for key, value in values.items():
            if fan == 'FAN-01' and s.case_id == 'DIA-02' and key == 'rotational.speed' and not recovered:
                continue
            if fan == 'FAN-01' and s.case_id == 'DIA-04' and not recovered:
                continue
            readings.append(row(s, fan, key, value, now))
    client = APIClient(HTTP_HOST='127.0.0.1')
    client.force_authenticate(User.objects.get(username='agent-eval-ingest'))
    response = client.post('/api/telemetry/', {'readings': readings}, format='json')
    if response.status_code not in {200, 201}:
        raise ValueError(f'Simulation ingestion rejected: {response.status_code} {response.data}')
    controllers = ['CTRL-01', 'CTRL-02', 'CTRL-03', 'CTRL-04']
    HardwareBinding.objects.filter(asset__code__in=controllers).exclude(
        asset__code='CTRL-03' if offline else '').update(last_heartbeat_at=now)
    if offline:
        members = [b['assetCode'] for b in BINDINGS if b['controllerId'] == 'CTRL-03'] + ['CTRL-03']
        HardwareBinding.objects.filter(asset__code__in=members).update(last_heartbeat_at=now-timedelta(hours=1))
    s.last_tick_at = now
    s.save()
    return True


def row(s, code, metric, value, at, quality='good'):
    units = {'temperature': '°C', 'humidity': '%RH', 'smoke.alarm': 'bool', 'flame.alarm': 'bool',
             'level.detected': 'bool', 'rotational.speed': 'rpm', 'motor.current': 'A', 'supply.voltage': 'V', 'power': 'W'}
    return {'eventId': f'simulation:{s.generation}:{s.tick}:{code}:{metric}', 'assetCode': code,
        'metricKey': metric, 'metric': metric, 'value': value, 'unit': units.get(metric, 'adc'),
        'quality': quality, 'recordedAt': at.isoformat()}
