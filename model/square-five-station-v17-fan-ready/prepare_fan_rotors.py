"""Execute via Blender MCP in the already open V16 scene. Does not alter V16 files."""
import bpy
import hashlib
import json
import math
import struct
from pathlib import Path
from mathutils import Matrix, Vector

ROOT = Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v17-fan-ready')
BASE = ROOT.parent / 'square-five-station-v16-concept'
REV = ROOT.name
ROOT.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
assert Path(bpy.data.filepath).resolve() in {
    (BASE / 'square-five-station-v16-concept.blend').resolve(),
    (ROOT / (REV + '.blend')).resolve(),
}, 'Unexpected live Blender document; refusing to change another project.'
# This reproducible operation starts from the saved base in this task's controlled instance.
bpy.ops.wm.open_mainfile(filepath=str(BASE / 'square-five-station-v16-concept.blend'))
scene = bpy.context.scene
protected_paths = [
    BASE / 'square-five-station-v16-concept.blend',
    BASE / 'square-five-station-v16-concept.glb',
    ROOT.parents[1] / 'frontend/public/models/utility-tunnel.glb',
]
protected = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_paths}
before = {o.name: o.matrix_world.copy() for o in scene.objects if o.type != 'EMPTY'}
counts_before = {'objects': len(scene.objects), 'meshes': sum(o.type == 'MESH' for o in scene.objects)}
fans = []
checks = {}
for n in (1, 2):
    code = f'FAN-{n:02}'
    housing = bpy.data.objects[code]
    moving = [bpy.data.objects[f'FAN_{n}_HUB']] + [bpy.data.objects[f'FAN_{n}_BLADE_{a}'] for a in range(0, 360, 72)]
    fixed = [housing] + [o for o in housing.children if '_MOUNT_' in o.name or '_GUARD_' in o.name]
    assert len(fixed) == 10
    rotor_name = code + '_ROTOR'
    rotor = bpy.data.objects.get(rotor_name)
    if rotor is None:
        rotor = bpy.data.objects.new(rotor_name, None)
        housing.users_collection[0].objects.link(rotor)
        rotor.parent = housing
        bpy.context.view_layer.update()
        rotor.matrix_world = Matrix.Translation(housing.matrix_world.translation)
        rotor.empty_display_type = 'CIRCLE'
        rotor.empty_display_size = .025
        bpy.context.view_layer.update()
        for obj in moving:
            world = obj.matrix_world.copy()
            obj.parent = rotor
            obj.matrix_parent_inverse = Matrix.Identity(4)
            obj.matrix_world = world
        bpy.context.view_layer.update()
    assert rotor.parent == housing
    assert set(o.name for o in rotor.children) == set(o.name for o in moving)
    rotor['role'] = 'FAN_ROTOR_ONLY'
    rotor['animationAssetCode'] = code
    rotor['telemetryMetricKey'] = 'rotational.speed'
    rotor['animationAutoplay'] = False
    rotor['physicalRotationDirection'] = 'UNVERIFIED'
    housing['rotorNode'] = rotor_name
    rest = rotor.matrix_world.copy()
    assert (rest.translation - housing.matrix_world.translation).length < 1e-9
    axis_native_local = Vector((0, 1, 0))
    axis_native_world = rest.to_quaternion() @ axis_native_local
    fixed_before = {o.name: o.matrix_world.copy() for o in fixed}
    moving_before = {o.name: o.matrix_world.copy() for o in moving}
    rotor.matrix_world = rest @ Matrix.Rotation(.37, 4, 'Y')
    bpy.context.view_layer.update()
    assert all(max(abs(o.matrix_world[r][c] - fixed_before[o.name][r][c]) for r in range(4) for c in range(4)) < 1e-8 for o in fixed)
    moved = sum((o.matrix_world.translation - moving_before[o.name].translation).length > .001 for o in moving)
    assert moved == 5, f'{code}: all five blades must move about the centre'
    assert (moving[0].matrix_world.translation - rest.translation).length < 1e-8
    rotor.matrix_world = rest
    bpy.context.view_layer.update()
    # Deterministic start / stop / restart simulation; never driven by a real relay.
    angle = 0.0
    phases = []
    for label, rpm in [('initial_stop', 0), ('start', 720), ('stop', 0), ('restart', 960)]:
        start = angle
        for _ in range(30):
            angle = (angle + min(max(rpm, 0), 90) * 2 * math.pi / 60 / 30) % (2 * math.pi)
        changed = abs(angle - start) > 1e-8
        assert changed == (rpm > 0)
        phases.append({'state': label, 'fixtureRpm': rpm, 'angleBefore': start, 'angleAfter': angle, 'moved': changed})
    fans.append({
        'assetCode': code, 'housingNode': code, 'rotorNode': rotor_name,
        'movingNodes': [o.name for o in moving], 'fixedNodes': [o.name for o in fixed],
        'pivotBlender_m': list(rest.translation),
        'pivotGltf_m': [rest.translation.x, rest.translation.z, -rest.translation.y],
        'axisBlenderLocal': list(axis_native_local),
        'axisBlenderWorld': list(axis_native_world),
        'axisGltfLocal': [0, 0, -1],
        'axisGltfWorld': [axis_native_world.x, axis_native_world.z, -axis_native_world.y],
        'physicalRotationDirection': 'UNVERIFIED',
        'positiveVisualDirection': 'ILLUSTRATIVE_ONLY',
        'simulation': phases,
    })
    checks[code] = {'movingMeshes': len(moving), 'fixedObjects': len(fixed), 'bladeOrbit': 'PASS', 'housingGuardsMountsStatic': 'PASS', 'startStopRestart': 'PASS'}

max_rest_delta = 0.0
for name, matrix in before.items():
    actual = bpy.data.objects[name].matrix_world
    delta = max(abs(actual[r][c] - matrix[r][c]) for r in range(4) for c in range(4))
    max_rest_delta = max(max_rest_delta, delta)
    assert delta < 1e-6, ('Rest pose changed beyond float transform tolerance', name, delta)
assert not any(o.animation_data for fan in fans for o in [bpy.data.objects[fan['rotorNode']]])
scene['revision'] = REV
scene['fanAnimationReadiness'] = 'INDEPENDENT_ROTORS_READY_LIVE_TELEMETRY_NOT_CONNECTED'
scene['fanMotionPolicy'] = 'Use fresh measured rotational.speed, never command acknowledgement or asset health.'
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / (REV + '.blend')), compress=True)
contract = {
    'revision': REV, 'status': 'MODEL_READY_REAL_DEVICE_INTEGRATION_PENDING',
    'baselineRevision': 'square-five-station-v16-concept', 'units': 'metres',
    'fans': fans,
    'telemetryContract': {
        'assetCode': ['FAN-01', 'FAN-02'], 'metricKey': 'rotational.speed', 'unit': 'rpm',
        'qualityRequired': 'good', 'sourceRequired': 'api', 'requiredTimestamp': 'recordedAt',
        'freshness': 'Configure from real sampling period, transport jitter and clock sync. No hardcoded production timeout.',
        'running': 'fresh good rpm > 0: animate only this rotor',
        'stopped': 'fresh good rpm == 0: stop at current phase',
        'unknown': 'missing, bad, suspect, stale, future, offline or demo data: freeze and label unknown',
        'commandAck': 'Never use relay_on, relay_off, PWM setting or normal/warning asset status as measured motion.',
        'visualRpmCap': 90,
        'visualRpmCapEvidence': 'Illustrative preview choice, not measured shaft speed. Keep measured rpm visible separately.',
        'coasting': 'Continue while tach reports rpm > 0 after relay-off; a stop command alone is insufficient.',
    },
    'integrationEvidence': {
        'existingTelemetryUi': 'frontend/src/views/DashboardView.vue uses rotational.speed independently for FAN-01 and FAN-02',
        'currentTwinScene': 'frontend/src/components/TwinScene.vue currently receives assets and alerts, not fan telemetry',
        'liveHardwareVerifiedThisSession': False, 'frontendModified': False,
    },
}
(ROOT / 'fan-animation-contract.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
report = {
    'revision': REV, 'editRoute': 'LIVE_BLENDER_MCP_execute_blender_code', 'blenderVersion': bpy.app.version_string,
    'modelChecks': checks, 'existingGeometryRestTransformsUnchanged': True,
    'maxRestMatrixElementDelta': max_rest_delta, 'restMatrixTolerance': 1e-6,
    'countsBefore': counts_before, 'countsAfter': {'objects': len(scene.objects), 'meshes': sum(o.type == 'MESH' for o in scene.objects)},
    'glbExport': 'PENDING_SEPARATE_MCP_CALL', 'protectedFilesBefore': protected,
    'protectedFilesAfter': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected_paths},
    'realDeviceTelemetryTest': 'NOT_EXECUTED', 'frontendIntegration': 'NOT_EXECUTED',
}
assert report['protectedFilesBefore'] == report['protectedFilesAfter']
(ROOT / 'model-readiness-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
