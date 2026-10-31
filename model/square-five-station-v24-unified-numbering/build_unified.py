"""Create a separate V24 numbering revision; never overwrite the original."""
import copy
import hashlib
import json
import struct
from pathlib import Path
import bpy

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CATALOG = ROOT / 'backend/operations/agent_catalog'
old = json.loads((CATALOG / 'model-v24-presentation.json').read_text(encoding='utf-8'))
inventory = json.loads((CATALOG / 'station-inventory.json').read_text(encoding='utf-8'))
source = Path(bpy.data.filepath)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
source_glb = source.with_suffix('.glb')
assert hashlib.sha256(source_glb.read_bytes()).hexdigest() == old['modelSha256']
OUT.mkdir(exist_ok=True)
before = {o.name: [list(row) for row in o.matrix_world] for o in bpy.data.objects}

# The centre oxygen probe is the third physical channel, not channel five.
for ob in list(bpy.data.objects):
    if 'O2-05' in ob.name:
        ob.name = ob.name.replace('O2-05', 'O2-03')
    if ob.type == 'FONT' and ob.data.body == 'O2-05':
        ob.data = ob.data.copy()
        ob.data.body = 'O2-03'
oxygen = bpy.data.objects['GAS-O2-03']
oxygen['physicalTag'] = 'O2-03'
oxygen['assetCode'] = 'GAS-O2-03'

nodes = [o for o in bpy.data.objects if o.get('category') == 'external_sensor']
assert len(nodes) == 31
by_tag = {o['physicalTag']: o for o in nodes}
assert len(by_tag) == 31
descriptor = copy.deepcopy(old)
descriptor.update(revision='v24-unified-numbering-20261029.1',
    modelVersion='hardware-live-v24-unified',
    modelPath='model/square-five-station-v24-unified-numbering/utility-tunnel-v24-unified.glb')
bindings = []
for binding in inventory['bindings']:
    code, tag = binding['assetCode'], binding['physicalTag']
    node = by_tag[tag]
    node['assetCode'] = code
    node['controllerId'] = binding['controllerId']
    node['identityStatus'] = 'WIRE_AND_MODEL_NUMBER_ALIGNED_PHYSICAL_ACCEPTANCE_SEPARATE'
    descriptor['sensorMeshes'][code] = node.name
    descriptor['sensorModelTags'][code] = tag
    descriptor['sensorStations'][code] = node['stationId']
    p = node.matrix_world.translation
    descriptor['sensorPositionsGltfM'][code] = [p.x, p.z, -p.y]
    bindings.append({**binding, 'targetNode': node.name, 'stationId': node['stationId'],
                     'positionGltfM': [p.x, p.z, -p.y]})
assert len(set(descriptor['sensorMeshes'].values())) == 31
assert all(descriptor['sensorModelTags'][b['assetCode']] == b['physicalTag'] for b in inventory['bindings'])
for ob in bpy.data.objects:
    old_name = ob.name.replace('O2-03', 'O2-05') if 'O2-03' in ob.name else ob.name
    assert before[old_name] == [list(row) for row in ob.matrix_world], ob.name

bpy.ops.object.select_all(action='DESELECT')
for ob in bpy.context.scene.objects:
    if ob.type in {'MESH', 'CURVE', 'FONT', 'EMPTY'} and not any(c.name == '99_STUDIO' for c in ob.users_collection):
        ob.select_set(True)
glb = OUT / 'utility-tunnel-v24-unified.glb'
bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=True,
    export_extras=True, export_apply=True, export_cameras=False, export_lights=False,
    export_yup=True, export_animations=False)
raw = glb.read_bytes()
data = json.loads(raw[20:20+struct.unpack_from('<I', raw, 12)[0]])
assert len(data['nodes']) == len({n['name'] for n in data['nodes']}) == 755
assert len([n for n in data['nodes'] if n.get('extras', {}).get('category') == 'external_sensor']) == 31
descriptor['modelSha256'] = hashlib.sha256(raw).hexdigest()
descriptor['notice'] = ('全部31路按采集物理编号对应同编号模型模块；烟雾、甲烷、一氧化碳和火焰01～05分别对应P1～P5。'
    '温湿度和液位保留现有同编号模块的位置。氧气01在P1、02在P2、03在中央P5，中央旧O2-05已更名O2-03。'
    '业务资产别名SMOKE-01/GAS-CH4-01/GAS-CO-01仍代表MQ2-01/MQ4-01/CO-01；固件编号和11/7/6/7主控归属未改。'
    '模型映射核验不代替逐路实物验收；风机仍分别依赖有效RPM和电压反馈。')
(CATALOG / 'model-v24-unified-presentation.json').write_text(json.dumps(descriptor, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(OUT / 'sensor-bindings.json').write_text(json.dumps({'revision': descriptor['revision'], 'bindings': bindings}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'utility-tunnel-v24-unified.blend'), compress=True)
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
report = {'revision': descriptor['revision'], 'modelSha256': descriptor['modelSha256'],
          'sensors': 31, 'uniqueTargets': 31, 'gltfNodes': 755,
          'originalBlendSha256': source_hash, 'originalModelUnchanged': True,
          'allObjectTransformsUnchanged': True, 'physicalAcceptance': 'separate_user_tests'}
(OUT / 'verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
print('UNIFIED_NUMBERING', json.dumps(report))
