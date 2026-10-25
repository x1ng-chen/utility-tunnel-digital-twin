"""Read-only evidence tools for the four-controller competition workflow.

The inventory is a versioned design, not proof of hardware commissioning.
All observations come from the database at query time. No device writes here.
"""
import json
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db.models import Count, F, OuterRef, Q, Subquery, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .connectivity import binding_is_online
from .models import Alert, Asset, AuditLog, HardwareBinding, Telemetry, TwinModelRelease, WorkOrder

INVENTORY = json.loads((Path(__file__).parent / 'agent_catalog/station-inventory.json').read_text(encoding='utf-8'))
BINDINGS = INVENTORY['bindings']
STATIONS = ('P1', 'P2', 'P3', 'P4', 'P5')
SENSOR_METRICS = {
    'MQ2': [('smoke.alarm',)], 'MQ4': [('methane.raw',)], 'CO': [('co.raw',)],
    'FLAME': [('flame.alarm',)], 'LEVEL': [('level.detected', 'water.raw')],
    'SHT': [('temperature',), ('humidity',)], 'O2': [('oxygen.raw', 'oxygen.voltage')],
}
METRIC_UNITS = {
    'smoke.alarm': {'bool'}, 'flame.alarm': {'bool'}, 'level.detected': {'bool'},
    'water.raw': {'adc'}, 'methane.raw': {'adc'}, 'co.raw': {'adc'}, 'oxygen.raw': {'adc'},
    'oxygen.voltage': {'mv'}, 'temperature': {'°c', 'c', 'degc'}, 'humidity': {'%rh', '%'},
}
assert len(BINDINGS) == len({b['assetCode'] for b in BINDINGS}) == len({b['physicalTag'] for b in BINDINGS}) == 31
assert Counter(b['controllerId'] for b in BINDINGS) == {'CTRL-01': 7, 'CTRL-02': 6, 'CTRL-03': 11, 'CTRL-04': 7}


def connection(asset, now):
    binding = getattr(asset, 'hardware_binding', None)
    state = 'unbound'
    if binding:
        if binding.status in {HardwareBinding.Status.ERROR, HardwareBinding.Status.INACTIVE}:
            state = binding.status
        elif binding.status == HardwareBinding.Status.RESERVED or not binding.last_heartbeat_at:
            state = 'awaiting_data'
        elif binding.last_heartbeat_at > now:
            state = 'future_timestamp'
        else:
            state = 'online' if binding_is_online(binding, now) else 'offline'
    return {
        'state': state,
        'heartbeat_at': binding.last_heartbeat_at.isoformat() if binding and binding.last_heartbeat_at else None,
        'heartbeat_age_seconds': round((now - binding.last_heartbeat_at).total_seconds(), 1) if binding and binding.last_heartbeat_at else None,
        'freshness_limit_seconds': max(settings.DEVICE_OFFLINE_MIN_GRACE_SECONDS,
            binding.expected_interval_seconds * settings.DEVICE_OFFLINE_GRACE_MULTIPLIER) if binding else None,
    }


def snapshots(codes, now=None):
    """Batch latest-per-metric queries, bounded to 20 metrics for each asset."""
    now = now or timezone.now()
    assets = list(Asset.objects.filter(code__in=codes, is_active=True).select_related('hardware_binding'))
    results = {}
    for asset in assets:
        results[asset.code] = {
            'asset_code': asset.code, 'name': asset.name, 'integration_status': asset.integration_status,
            'connection': connection(asset, now), 'metric_count': 0, 'limit': 20, 'readings': [],
        }
    rows = Telemetry.objects.filter(asset__in=assets)
    latest = rows.filter(asset_id=OuterRef('asset_id'), metric_key=OuterRef('metric_key')).filter(
        ~Q(metric_key='') | Q(metric=OuterRef('metric'))).order_by('-recorded_at', '-id')
    rows = rows.filter(id=Subquery(latest.values('id')[:1]))
    code_by_id = {a.pk: a.code for a in assets}
    for row in rows.values('asset_id').annotate(total=Count('id')).order_by():
        results[code_by_id[row['asset_id']]]['metric_count'] = row['total']
    bounded = rows.annotate(metric_ordinal=Window(RowNumber(), partition_by=[F('asset_id')],
        order_by=[F('metric_key').asc(), F('metric').asc(), F('id').desc()])).filter(metric_ordinal__lte=20)
    for row in bounded.order_by('asset_id', 'metric_key', 'metric'):
        result = results[code_by_id[row.asset_id]]
        age = (now - row.recorded_at).total_seconds()
        limit = result['connection']['freshness_limit_seconds']
        freshness = 'future_timestamp' if age < 0 else ('unknown' if limit is None else 'fresh' if age <= limit else 'stale')
        demo = bool(row.event_id and row.event_id.lower().startswith(('demo:', 'simulation:', 'fixture:')))
        value = row.value if math.isfinite(row.value) else None
        result['readings'].append({
            'id': row.id, 'metric_key': row.metric_key, 'metric': row.metric, 'value': value,
            'unit': row.unit, 'quality': row.quality, 'sampled_at': row.recorded_at.isoformat(),
            'ingested_at': row.ingested_at.isoformat(), 'sample_age_seconds': round(age, 1),
            'freshness': freshness, 'provenance': 'demo' if demo else 'database_observation',
            'usable': bool(value is not None and row.quality == 'good' and freshness == 'fresh'
                and row.ingested_at <= now and not demo and result['connection']['state'] == 'online'),
        })
    return results


def station_snapshot(station_id='all'):
    if station_id not in (*STATIONS, 'all'):
        raise ValueError('检测点仅允许 P1～P5 或 all。')
    now = timezone.now()
    bindings = [b for b in BINDINGS if station_id == 'all' or b['stationId'] == station_id]
    sensor_codes = [b['assetCode'] for b in bindings]
    controller_codes = sorted({b['controllerId'] for b in bindings})
    observed = snapshots([*sensor_codes, *controller_codes], now)
    assets = {a.code: a for a in Asset.objects.filter(code__in=observed)}
    release = TwinModelRelease.objects.filter(status='active').first()
    node_counts = Counter(release.node_names) if release and release.node_inventory_available else Counter()
    alerts = list(Alert.objects.filter(asset__code__in=observed, status__in=['open', 'acknowledged'])
        .values('code', 'asset__code', 'severity', 'title').order_by('asset__code', 'code')[:100])
    items = []
    for binding in bindings:
        code = binding['assetCode']
        asset = assets.get(code)
        snapshot = observed.get(code)
        mesh = asset.mesh.strip() if asset else ''
        if not asset:
            mapping = 'asset_missing'
        elif mesh != binding['targetNode']:
            mapping = 'mesh_mismatch' if mesh else 'mesh_missing'
        elif not release or not release.node_inventory_available:
            mapping = 'active_model_unverified'
        elif node_counts[mesh] != 1:
            mapping = 'node_missing_or_ambiguous'
        else:
            mapping = 'active_model_node_verified'
        readings = snapshot['readings'] if snapshot else []
        expected_groups = SENSOR_METRICS[binding['physicalTag'].split('-')[0]]
        missing_metrics = [list(group) for group in expected_groups if not any(r['metric_key'] in group for r in readings)]
        relevant_readings = [r for r in readings if any(r['metric_key'] in g for g in expected_groups)]
        unit_issues = [r['metric_key'] for r in relevant_readings
            if r['unit'].strip().lower() not in METRIC_UNITS[r['metric_key']]]
        # A physical sensor can produce multiple metrics. Count devices, never metric rows.
        usable = bool(relevant_readings and not missing_metrics and not unit_issues and all(r['usable'] for r in relevant_readings)
            and snapshot['metric_count'] <= snapshot['limit'])
        items.append({**binding, 'identity_status': 'planned_hardware_binding_unverified',
            'registry_present': asset is not None, 'mapping_status': mapping,
            'missing_metric_groups': missing_metrics,
            'unit_issues': unit_issues,
            'current_mesh': mesh or None, 'observation_state': 'usable_observations' if usable else 'needs_verification',
            'snapshot': snapshot, 'active_alerts': [
                {'code': a['code'], 'severity': a['severity'], 'title': a['title'][:160]}
                for a in alerts if a['asset__code'] == code],
        })
    return {'revision': INVENTORY['revision'], 'queried_at': now.isoformat(), 'station_id': station_id,
        'expected_sensor_count': len(bindings), 'registered_sensor_count': sum(code in observed for code in sensor_codes),
        'usable_observation_sensor_count': sum(i['observation_state'] == 'usable_observations' for i in items),
        'controller_allocation': dict(Counter(b['controllerId'] for b in bindings)),
        'controllers': {code: observed.get(code) for code in controller_codes},
        'stations': {s: [b['physicalTag'] for b in bindings if b['stationId'] == s] for s in STATIONS
            if any(b['stationId'] == s for b in bindings)},
        'active_model_version': release.version if release else None, 'items': items,
        'boundary': '31路身份来自已确认布局；台账、模型和硬件绑定分别核验。可用观测不代表传感器已标定或环境安全。'}


def diagnose_station(station_id):
    """Collect comparable evidence; candidate causes are deliberately non-exclusive."""
    inspection = station_snapshot(station_id)
    all_primary_codes = [b['assetCode'] for b in BINDINGS if b['stationLinkKind'] == 'DIRECT_FOUR_SENSOR_MEMBER']
    now = timezone.now()
    nearby = snapshots(all_primary_codes, now)
    fans = snapshots(['FAN-01', 'FAN-02'], now)
    candidates = []
    for code in ('FAN-01', 'FAN-02'):
        readings = (fans.get(code) or {}).get('readings', [])
        rpm = next((r for r in readings if r['metric_key'] == 'rotational.speed'), None)
        current = next((r for r in readings if r['metric_key'] == 'motor.current'), None)
        valid_rpm = rpm and rpm['usable'] and rpm['unit'].strip().lower() == 'rpm' and rpm['value'] >= 0
        valid_current = current and current['usable'] and current['unit'] in {'mA', 'A'} and current['value'] >= 0
        if not valid_rpm:
            candidates.append({'asset_code': code, 'candidate': '转速反馈缺失或不可用',
                'reason': '缺少新鲜、良好且单位为 rpm 的独立反馈，不能判断实际转动。',
                'alternatives': ['转速采集链路异常', '节点通信或时钟异常', '实际机械状态仍未知']})
        elif rpm['value'] == 0:
            candidates.append({'asset_code': code, 'candidate': '观测到零转速，原因待核实',
                'reason': '零转速不能单独证明电机损坏；需结合控制意图、供电和反馈链路。',
                'alternatives': ['正常停机', '供电或驱动未使能', '机械卡滞', 'TACH 输入异常']})
        if not valid_current:
            candidates.append({'asset_code': code, 'candidate': '电流证据不足',
                'reason': '无新鲜良好且单位明确的 INA226 电流，不能据此区分无供电与采集异常。',
                'alternatives': ['电流采集缺失', '通信或质量问题']})
    alerts = list(Alert.objects.filter(asset__code__in=all_primary_codes, status__in=['open', 'acknowledged'])
        .values('code', 'asset__code', 'rule_key', 'severity', 'opened_at').order_by('-opened_at')[:30])
    commands = list(AuditLog.objects.filter(action__in=['controller.command.sent', 'controller.command.failed'],
        resource_type='asset', resource_id__in=['CTRL-01', 'CTRL-04'], occurred_at__gte=now-timedelta(minutes=10))
        .order_by('-occurred_at')[:6])
    # Only expose established audit fields. Never pass tokens, arbitrary request bodies, or hidden endpoints.
    command_evidence = [{'controller': c.resource_id, 'recorded_at': c.occurred_at.isoformat(),
        'action': c.action, 'command_action': c.detail.get('action'), 'outcome': c.detail.get('outcome'),
        'ack_reason': str(c.detail.get('ackReason', ''))[:200]} for c in commands]
    return {'station': inspection, 'neighbor_latest_observations': nearby, 'fans': fans,
        'neighbor_trends': primary_trends(all_primary_codes, now),
        'active_alerts': alerts, 'recent_command_audit': command_evidence, 'candidate_causes': candidates,
        'limits': ['近5分钟趋势按同资产、同指标、同单位比较；相关变化不能证明扩散方向或预测事故。',
            'MQ-4/MQ-7 原始值未标定不能横向比较为 ppm；AO-02 裸探头读数不能证明氧气安全。',
            '现有控制审计可能来自旧版 CTRL-01 双风机协议，不能视作新四节点执行证明。',
            '命令已发布或已回执均不等于风机在转；候选原因不等于根因。']}


def primary_trends(codes, now):
    """At most 60 observations per physical primary sensor; never mix units."""
    rows = Telemetry.objects.filter(asset__code__in=codes, asset__is_active=True,
        metric_key__in=['smoke.alarm', 'methane.raw', 'co.raw', 'flame.alarm'],
        unit__in=['adc', 'ADC', 'bool'], quality='good',
        recorded_at__gte=now-timedelta(minutes=5), recorded_at__lte=now, ingested_at__lte=now)
    for prefix in ('demo:', 'simulation:', 'fixture:'):
        rows = rows.exclude(event_id__istartswith=prefix)
    rows = rows.annotate(sample_ordinal=Window(RowNumber(), partition_by=[F('asset_id')],
        order_by=[F('recorded_at').desc(), F('id').desc()])).filter(sample_ordinal__lte=60).select_related('asset')
    groups = {}
    for row in rows.order_by('recorded_at', 'id'):
        if not math.isfinite(row.value):
            continue
        group = groups.setdefault((row.asset.code, row.metric_key, row.unit), [])
        group.append(row)
    return {'window_minutes': 5, 'sample_limit_per_asset': 60, 'scope': 'bounded_good_non_demo_observations',
        'items': [{'asset_code': code, 'metric_key': metric, 'unit': unit, 'count': len(values),
            'from': values[0].recorded_at.isoformat(), 'to': values[-1].recorded_at.isoformat(),
            'first': values[0].value, 'last': values[-1].value,
            'minimum': min(v.value for v in values), 'maximum': max(v.value for v in values),
            'delta': finite_delta(values[-1].value, values[0].value) if len(values) >= 2 else None,
            'interpretation': 'within_same_asset_raw_change_only_no_calibrated_concentration'}
            for (code, metric, unit), values in sorted(groups.items())]}


def finite_delta(last, first):
    delta = last - first
    return delta if math.isfinite(delta) else None


def review_work_order(code):
    order = WorkOrder.objects.filter(code=code, asset__is_active=True).select_related('asset').first()
    if not order:
        raise ValueError('未找到该工单或关联资产已停用。')
    now = timezone.now()
    snapshot = snapshots([order.asset.code], now)[order.asset.code]
    readings = snapshot['readings']
    post_review = [r for r in readings if r['usable'] and parse_datetime(r['sampled_at']) > order.updated_at]
    alerts = Alert.objects.filter(asset=order.asset, status__in=['open', 'acknowledged'])
    return {'work_order_code': order.code, 'asset_code': order.asset.code, 'status': order.status,
        'work_order_updated_at': order.updated_at.isoformat(), 'queried_at': now.isoformat(),
        'communication': snapshot['connection'], 'latest_measurements': snapshot,
        'measurement_review': 'new_usable_observations' if readings and len(post_review) == len(readings)
            and snapshot['metric_count'] <= snapshot['limit'] else 'insufficient_new_evidence',
        'active_alert_count': alerts.count(),
        'active_alert_codes': list(alerts.order_by('code').values_list('code', flat=True)[:15]),
        'human_review_required': True, 'work_order_changed': False,
        'boundary': '新观测仅证明数据更新；不自动判定测量恢复正常，不关闭告警或工单。仍需核对标定、阈值、故障工况和持续稳定性。'}


def location_cards(evidence):
    """Cards are server-derived; LLM/user text never supplies a mesh or route."""
    cards = {}
    by_code = {b['assetCode']: b for b in BINDINGS}
    for item in evidence:
        if item['status'] != 'ok':
            continue
        data = item['data']
        inspection = data.get('station', data)
        if item['tool'] in {'station_snapshot', 'diagnose_station'}:
            for sensor in inspection.get('items', []):
                if sensor['registry_present']:
                    cards[sensor['assetCode']] = {'assetCode': sensor['assetCode'], 'stationId': sensor['stationId'],
                        'controllerId': sensor['controllerId'], 'physicalTag': sensor['physicalTag'],
                        'mappingStatus': sensor['mapping_status'], 'evidenceId': item['id']}
        elif item['tool'] in {'asset_snapshot', 'review_work_order'}:
            code = data.get('asset_code')
            if code in by_code and code not in cards:
                b = by_code[code]
                cards[code] = {'assetCode': code, 'stationId': b['stationId'], 'controllerId': b['controllerId'],
                    'physicalTag': b['physicalTag'], 'mappingStatus': 'not_checked', 'evidenceId': item['id']}
    return list(cards.values())


def inspection_summary(evidence):
    for entry in reversed(evidence):
        if entry['status'] != 'ok' or entry['tool'] not in {'station_snapshot', 'diagnose_station'}:
            continue
        report = entry['data'].get('station', entry['data'])
        return {'evidenceId': entry['id'], 'expected': report['expected_sensor_count'],
            'registered': report['registered_sensor_count'], 'usable': report['usable_observation_sensor_count'],
            'missingAssetCodes': [i['assetCode'] for i in report['items'] if not i['registry_present']],
            'stations': [{'stationId': station, 'expected': len(items),
                'registered': sum(i['registry_present'] for i in items),
                'usable': sum(i['observation_state'] == 'usable_observations' for i in items),
                'alertCount': sum(len(i['active_alerts']) for i in items)}
                for station in STATIONS if (items := [i for i in report['items'] if i['stationId'] == station])]}
    return None
