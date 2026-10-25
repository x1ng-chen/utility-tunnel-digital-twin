"""Run in a separate MCP call after prepare; file-open invalidates the old UI context."""
import bpy, json, hashlib, struct
from pathlib import Path
ROOT = Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v17-fan-ready')
REV = ROOT.name
assert Path(bpy.data.filepath).resolve() == (ROOT / (REV + '.blend')).resolve()
contract = json.loads((ROOT / 'fan-animation-contract.json').read_text(encoding='utf-8'))
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    if obj.type in {'MESH', 'CURVE', 'FONT', 'EMPTY'} and not any(c.name == '99_STUDIO' for c in obj.users_collection):
        obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(ROOT / (REV + '.glb')), export_format='GLB', use_selection=True,
    export_extras=True, export_apply=True, export_cameras=False, export_lights=False,
    export_yup=True, export_animations=False)
raw = (ROOT / (REV + '.glb')).read_bytes()
gltf = json.loads(raw[20:20 + struct.unpack_from('<I', raw, 12)[0]])
names = [o.get('name') for o in gltf['nodes']]
assert len(names) == len(set(names))
assert not gltf.get('animations')
for fan in contract['fans']:
    rotor_index = names.index(fan['rotorNode'])
    rotor_node = gltf['nodes'][rotor_index]
    assert sorted(names[i] for i in rotor_node['children']) == sorted(fan['movingNodes'])
    housing = gltf['nodes'][names.index(fan['housingNode'])]
    assert rotor_index in housing['children']
    assert all(names.index(n) in housing['children'] for n in fan['fixedNodes'] if n != fan['housingNode'])
report = json.loads((ROOT / 'model-readiness-report.json').read_text(encoding='utf-8'))
report.update(glbExport='PASS', glbNodeCount=len(names), glbAnimations=0, glbSha256=hashlib.sha256(raw).hexdigest())
report['protectedFilesAfter'] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in report['protectedFilesBefore']}
assert report['protectedFilesBefore'] == report['protectedFilesAfter']
(ROOT / 'model-readiness-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
