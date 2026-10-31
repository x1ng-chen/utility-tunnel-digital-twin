"""Versioned, read-only equipment relationships, never acquired measurements.

The graph is built once by the server and queried from the frozen run snapshot.
Expected mappings and configured transport paths do not establish continuity,
online status, or physical commissioning.  No spatial edge is guessed from 3D
coordinates, and a telemetry path is not a local safety-control dependency.
"""
from collections import Counter, deque
from copy import deepcopy
import hashlib
import json
from pathlib import Path


VERSION = 'equipment-topology-20261029.1'
SOURCE = 'CONFIGURED_RELATIONSHIP'
STATIONS = tuple(f'P{i}' for i in range(1, 6))
CONTROLLERS = tuple(f'CTRL-{i:02}' for i in range(1, 5))
BUS_ID = 'RS485-BUS'
GATEWAY_ID = 'ESP32-S3-GATEWAY'
DEPENDENCIES = {'owned_by', 'telemetry_via', 'has_feedback'}
BOUNDARY = ('设备关系来自配置，非采集事实或接线实测；中心遥测路径不表示STM32本地保护依赖网关。'
            '共同依赖只能支持排查候选，不能证明根因；缺失绑定不能显示定位成功。')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def build_topology(inventory=None, presentation=None, bindings=None):
    """Build a detached graph from trusted server configuration.

    ``inventory`` is the run's runtime_inventory; ``presentation`` is an optional
    already verified server adapter. ``bindings`` is inspection['items'], not
    client input. Actual mesh edges are created only for explicitly verified
    inspection items. All remaining mesh edges are labelled expected_mapping.
    """
    if inventory is None:
        inventory = json.loads((Path(__file__).parent / 'agent_catalog' /
                                'station-inventory.json').read_text(encoding='utf-8'))
    inventory = deepcopy(inventory)
    if not isinstance(inventory, dict) or not isinstance(inventory.get('bindings'), list):
        raise ValueError('设备拓扑需要服务器身份清单。')
    if len(inventory['bindings']) > 128:
        raise ValueError('设备拓扑超过128路身份限制。')
    presentation = deepcopy(presentation or inventory.get('presentation') or {})
    if presentation and presentation.get('wireLayoutVersion') not in (None, inventory.get('revision')):
        raise ValueError('展示适配与接线布局版本不匹配。')
    if presentation:
        inventory['presentationRevision'] = presentation.get('revision')
        for item in inventory['bindings']:
            station = presentation.get('sensorStations', {}).get(item.get('assetCode'))
            if station:
                item['stationId'] = station
    if bindings is not None and not isinstance(bindings, list):
        raise ValueError('实际绑定必须为冻结巡检条目数组。')
    actual = {}
    for item in bindings or []:
        if not isinstance(item, dict) or not isinstance(item.get('assetCode'), str):
            raise ValueError('实际绑定条目需要assetCode。')
        if item['assetCode'] in actual:
            raise ValueError('重复的实际绑定条目。')
        actual[item['assetCode']] = item
    nodes, edges, missing = {}, [], []

    def node(identity, kind, **fields):
        if identity not in nodes:
            nodes[identity] = {'id': identity, 'kind': kind, **fields}

    def edge(start, end, kind, **fields):
        edges.append({'from': start, 'to': end, 'kind': kind,
                      'source': SOURCE, **fields})

    for station in STATIONS:
        node(station, 'station')
    for controller in CONTROLLERS:
        node(controller, 'controller')
        edge(controller, BUS_ID, 'telemetry_via', verified=False)
    node(BUS_ID, 'bus', protocol='RS-485', logical=True)
    node(GATEWAY_ID, 'gateway', model='ESP32-S3', logical=True)
    edge(BUS_ID, GATEWAY_ID, 'telemetry_via', verified=False)
    seen_tags = set()
    for item in inventory['bindings']:
        code = item.get('assetCode')
        tag = item.get('physicalTag')
        if not isinstance(code, str) or not code or code in nodes or not isinstance(tag, str) or tag in seen_tags:
            raise ValueError('身份清单包含缺失或重复的设备/实体编号。')
        seen_tags.add(tag)
        controller, station = item.get('controllerId'), item.get('stationId')
        node(code, 'sensor', physicalTag=tag, stationId=station,
             controllerId=controller)
        if controller in CONTROLLERS:
            edge(code, controller, 'owned_by', verified=False)
        else:
            missing.append({'target': code, 'reason': 'controller_not_configured'})
        if station in STATIONS:
            edge(code, station, 'located_at', verified=False)
        else:
            missing.append({'target': code, 'reason': 'station_not_configured'})
        mesh = item.get('targetNode')
        observed = actual.get(code)
        verified = bool(observed and observed.get('registry_present') is True
                        and observed.get('mapping_status') == 'active_model_node_verified'
                        and observed.get('current_mesh') == mesh and mesh
                        and observed.get('controllerId') == controller
                        and observed.get('stationId') == station)
        if mesh:
            node('mesh:' + mesh, 'model_object', objectName=mesh)
            edge(code, 'mesh:' + mesh, 'mapped_to' if verified else 'expected_mapping',
                 verified=verified)
        if not verified:
            missing.append({'target': code, 'reason': (observed or {}).get(
                'mapping_status', 'actual_model_binding_not_verified')})
        if observed and (observed.get('controllerId') != controller or observed.get('stationId') != station):
            missing.append({'target': code, 'reason': 'binding_identity_conflict'})
    fan_controllers = inventory.get('fanControllers', {})
    for fan in ('FAN-01', 'FAN-02'):
        controller = fan_controllers.get(fan)
        node(fan, 'fan', controllerId=controller)
        if controller in CONTROLLERS:
            edge(fan, controller, 'owned_by', verified=False)
        else:
            missing.append({'target': fan, 'reason': 'fan_controller_not_configured'})
        for metric, label in (('supply.voltage', '供电反馈'), ('motor.current', 'INA电流反馈'),
                              ('rotational.speed', '独立RPM反馈')):
            identity = f'feedback:{fan}:{metric}'
            node(identity, 'feedback_channel', assetCode=fan, metricKey=metric,
                 label=label, observationVerified=False)
            edge(fan, identity, 'has_feedback', verified=False)
    controller_meshes = presentation.get('controllerMeshes') or inventory.get('controllerLegacyMeshes', {})
    for controller, mesh in sorted(controller_meshes.items()):
        if controller in CONTROLLERS and isinstance(mesh, str) and mesh:
            node('mesh:' + mesh, 'model_object', objectName=mesh)
            edge(controller, 'mesh:' + mesh, 'expected_mapping', verified=False)
    allocation = dict(sorted(Counter(x.get('controllerId') for x in inventory['bindings']).items(),
                             key=lambda item: str(item[0])))
    if len(inventory['bindings']) != 31:
        missing.append({'target': 'inventory', 'reason': 'expected_31_sensor_identities'})
    result = {'version': VERSION, 'source': SOURCE, 'layoutVersion': inventory.get('revision'),
              'presentationVersion': inventory.get('presentationRevision'),
              'modelVersion': presentation.get('modelVersion'),
              'nodes': sorted(nodes.values(), key=lambda value: value['id']),
              'edges': sorted(edges, key=lambda value: (value['from'], value['kind'], value['to'])),
              'missing': missing, 'counts': {'sensors': len(inventory['bindings']),
                  'controllers': 4, 'stations': 5, 'fans': 2, 'allocation': allocation},
              'boundary': BOUNDARY}
    result['sha256'] = _hash(result)
    return result


def query_topology(snapshot, target, relation='dependencies'):
    """Query a frozen graph only; never silently replace it with current config."""
    if relation not in {'dependencies', 'impact', 'neighbors'}:
        raise ValueError('拓扑查询仅支持dependencies、impact或neighbors。')
    if not isinstance(target, str) or not 1 <= len(target) <= 100:
        raise ValueError('需要明确的设备或检测站编号。')
    graph = snapshot.get('topologyContext')
    if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list):
        return {'status': 'unknown', 'source': SOURCE, 'target': target, 'relation': relation,
                'nodes': [], 'edges': [], 'missing': [{'target': target, 'reason': 'frozen_topology_missing'}],
                'boundary': BOUNDARY}
    nodes = {item['id']: item for item in graph['nodes']}
    if target not in nodes:
        aliases = [item['id'] for item in graph['nodes'] if item.get('physicalTag') == target]
        if len(aliases) == 1:
            target = aliases[0]
    result = {'status': 'ok' if target in nodes else 'unknown', 'source': SOURCE,
              'version': graph.get('version'), 'topologyHash': graph.get('sha256'),
              'snapshotHash': snapshot.get('sha256'), 'layoutVersion': graph.get('layoutVersion'),
              'presentationVersion': graph.get('presentationVersion'), 'target': target,
              'relation': relation, 'nodes': [], 'edges': [], 'modelBindings': [],
              'missing': [], 'boundary': BOUNDARY}
    if target not in nodes:
        result['missing'] = [{'target': target, 'reason': 'identity_not_in_frozen_graph'}]
        return result
    edges = graph.get('edges', [])
    selected = {target}
    if relation == 'neighbors':
        here = nodes[target]
        stations = {target} if here['kind'] == 'station' else {here.get('stationId')}
        controllers = {target} if here['kind'] == 'controller' else {here.get('controllerId')}
        selected.update(item['id'] for item in nodes.values()
                        if item['kind'] in {'sensor', 'fan'} and
                        ((item.get('stationId') is not None and item.get('stationId') in stations)
                         or (item.get('controllerId') is not None and item.get('controllerId') in controllers)))
        selected.update(item['id'] for item in nodes.values() if item['kind'] == 'controller'
                        and any(nodes[s].get('controllerId') == item['id'] for s in selected))
        result['neighborMeaning'] = '同站或共享主控的配置邻居；不表示物理距离、管道连通或气体传播方向。'
    else:
        starts = {target}
        if nodes[target]['kind'] == 'station':
            starts.update(item['id'] for item in nodes.values() if item.get('stationId') == target)
            selected.update(starts)
        queue = deque((identity, 0) for identity in sorted(starts))
        while queue:
            identity, depth = queue.popleft()
            if depth >= 4:
                continue
            for edge in edges:
                if edge['kind'] not in DEPENDENCIES:
                    continue
                start, end = (edge['to'], edge['from']) if relation == 'impact' else (edge['from'], edge['to'])
                if start == identity and end not in selected:
                    selected.add(end)
                    queue.append((end, depth + 1))
    result['nodes'] = [deepcopy(nodes[identity]) for identity in sorted(selected)]
    result['edges'] = [deepcopy(edge) for edge in edges
                       if edge['from'] in selected and edge['to'] in selected]
    result['modelBindings'] = [deepcopy(edge) for edge in edges
                               if edge['from'] in selected and edge['kind'] in {'mapped_to', 'expected_mapping'}]
    result['missing'] = [deepcopy(item) for item in graph.get('missing', [])
                         if item.get('target') in selected or item.get('target') == 'inventory']
    return result
