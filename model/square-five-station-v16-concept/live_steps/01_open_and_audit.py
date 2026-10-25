import bpy,json
from pathlib import Path
from collections import Counter
path='D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v16-concept/square-five-station-v16-concept.blend'
assert bpy.data.filepath.endswith('mcp-live-ready.blend') or bpy.data.filepath==path or bpy.context.scene.name=='MCP_CONNECTION_TEST_ONLY', 'Unexpected user scene: stop before loading'
bpy.ops.wm.open_mainfile(filepath=path)
bpy.context.view_layer.update()
roots=[o for o in bpy.context.scene.objects if o.get('category')]
sensors=[o for o in roots if o['category']=='external_sensor']
print(json.dumps({'file':bpy.data.filepath,'blender':bpy.app.version_string,'rootCounts':dict(Counter(o['category'] for o in roots)),
    'ownership':dict(Counter(o['controllerId'] for o in sensors)),
    'stationParents':{f'P{n}':[o['physicalTag'] for o in sensors if o.get('physicalMember') and o.get('stationId')==f'P{n}'] for n in range(1,6)},
    'labelPositions':{f'P{n}':list(bpy.data.objects[f'STATION_LABEL_P{n}'].matrix_world.translation) for n in range(1,6)}},ensure_ascii=False))
