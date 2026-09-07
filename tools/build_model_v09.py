"""Isolated, reproducible V09 visual candidate; never load/save the live scene.

Run: blender -b --python tools/build_model_v09.py -- <repository-root>
Dimensions are inherited scene units, NOT approved fabrication dimensions.
"""
import bpy
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from mathutils import Vector

root = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
out = root / 'model'
preview = out / 'previews'
preview.mkdir(exist_ok=True)

def glb_json(path):
    data = path.read_bytes()
    return json.loads(data[20:20 + struct.unpack_from('<I', data, 12)[0]])

baseline = glb_json(out / 'utility-tunnel-annular-v07-final.glb')
source = out / 'utility-tunnel-annular-v08-final.glb'
allowed = {n['name'] for n in baseline['nodes'] if n.get('name')}
bt_names = {n['name'] for n in glb_json(source)['nodes'] if n.get('name', '').startswith('GEO-V08-BT01-') or n.get('name') == 'MESH_BT_01'}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
# Bake world transforms before removing historical parents, preserving placement.
for obj in list(bpy.data.objects):
    matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = matrix
excluded = sorted(o.name for o in bpy.data.objects if o.name not in allowed | bt_names)
for obj in list(bpy.data.objects):
    if obj.name in excluded:
        bpy.data.objects.remove(obj, do_unlink=True)

def bounds(obj):
    pts = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
    return [[min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]]

def mat(name, color, metal=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = .42
    return m

water = mat('V09 水路 · 蓝', (.035, .42, .68))
steel = mat('V09 安装件 · 银灰', (.52, .57, .61), .6)
dark = mat('V09 泵体 · 深灰', (.09, .13, .17), .4)
ink = mat('V09 铭牌文字 · 黑', (.015,.02,.025))
paper = mat('V09 铭牌底 · 白', (.88,.90,.92))

def cube(name, center, size, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj

def tube(name, points, radius=.005, material=water):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.use_fill_caps = True
    spline = curve.splines.new('POLY')
    spline.points.add(len(points)-1)
    for p, value in zip(spline.points, points):
        p.co = (*value, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    obj.select_set(False)
    return obj

bt_before = bounds(bpy.data.objects['MESH_BT_01'])
bt_delta = Vector((-.147, -.063, .076))
for name in bt_names:
    bpy.data.objects[name].location += bt_delta
# Underside z=.298; PCB upper z=.297: visible supporting strip fills the gap.
cube('GEO-V09-BT01-SUPPORT', (-.452, -.310, .2975), (.039, .018, .001), steel)

# V07 exported no connected suction/pump-return circuit. Add explicit visual
# routes and pump body rather than attaching probes to unrelated utility pipes.
for obj in list(bpy.data.objects):
    if 'FSIR02_L04' in obj.name or ('CALLOUT-' in obj.name and obj.name.endswith('_L04')):
        obj.location.x += .043
    if 'FSIR02_L05' in obj.name or ('CALLOUT-' in obj.name and obj.name.endswith('_L05')):
        obj.location.z += .08

routes = {
 'GEO-V09-WATER-SUCTION': [[.46,-.11,.207],[.44,-.13,.207],[.44,-.154,.207],[.48,-.154,.207],[.506,-.144,.207],[.529,-.144,.207]],
 'GEO-V09-WATER-DISCHARGE': [[.548,-.144,.219],[.566,-.144,.219],[.566,-.144,.277],[.5967,-.147,.277]],
 'GEO-V09-WATER-RETURN': [[.5967,-.147,.277],[.640,-.144,.277],[.672,-.144,.277],[.672,-.245,.277],[.672,-.245,.382],[.113,-.245,.382],[.113,-.201,.382],[.081,-.201,.382],[.081,-.177,.382],[.081,-.177,.24]],
}
for name, points in routes.items():
    tube(name, points)
cube('GEO-V09-P01-PUMP-BODY', (.534,-.144,.209), (.038,.031,.06), dark)
# Mount feet touch the existing P-01 base at z=.17955.
cube('GEO-V09-P01-FEET', (.534,-.144,.180), (.048,.04,.002), steel)

stations = ['排水段','吸水段','泵入口','阀后段','回水段']
targets = ['MESH_WATER_DRAIN_VALVE_01','GEO-V09-WATER-SUCTION','GEO-V09-WATER-SUCTION','GEO-V09-WATER-RETURN','GEO-V09-WATER-RETURN']
bpy.context.view_layer.update()
checks = []
for i, (station, target) in enumerate(zip(stations, targets), 1):
    probe = bpy.data.objects[f'MESH_V12-FSIR02_L{i:02}_PROBE']
    # Short service boss visibly joins probe tip to the dedicated pipe.
    center = sum((Vector(p) for p in bounds(probe)), Vector()) / 2
    end = center + Vector((0,.011,0))
    tube(f'GEO-V09-L{i:02}-SERVICE-BOSS', [list(center), list(end)], .004, steel)
    board_bounds = bounds(bpy.data.objects[f'MESH_V12-FSIR02_L{i:02}_BOARD'])
    bracket_bounds = bounds(bpy.data.objects[f'GEO-V14-FSIR02_L{i:02}_BRACKET'])
    board_back = [(board_bounds[0][0]+board_bounds[1][0])/2, board_bounds[1][1], (board_bounds[0][2]+board_bounds[1][2])/2]
    bracket_top = [(bracket_bounds[0][0]+bracket_bounds[1][0])/2, (bracket_bounds[0][1]+bracket_bounds[1][1])/2, board_back[2]]
    tube(f'GEO-V09-L{i:02}-BOARD-SUPPORT', [board_back,bracket_top], .0025, steel)
    if target in routes:
        distances = []
        for start, finish in zip(routes[target], routes[target][1:]):
            a,b = Vector(start),Vector(finish)
            ab = b-a
            t = max(0,min(1,(end-a).dot(ab)/ab.length_squared))
            distances.append((end-(a+t*ab)).length)
        distance = min(distances)
        assert distance <= .005, f'{station}: service boss misses its pipe centerline'
    else:
        low, high = bounds(bpy.data.objects[target])
        distance = math.sqrt(sum(max(0,low[j]-end[j],end[j]-high[j])**2 for j in range(3)))
        assert distance <= .001, f'{station}: service boss misses drain valve bounds'
    checks.append({'asset':f'LEVEL-L{i:02}', 'station':station, 'target':target, 'probeBounds':bounds(probe), 'bossEndpointDistance':distance, 'method':'point-to-route-centerline' if target in routes else 'point-to-valve-AABB', 'status':'VISUAL_ONLY', 'note':'Visual boss and route; not a pressure seal or calibration approval.'})

# Repair low-contrast nameplates and crowded control callouts identified in
# the first render. Keep node IDs stable while replacing text geometry.
font_path = Path('C:/Windows/Fonts/msyh.ttc')
font = bpy.data.fonts.load(str(font_path)) if font_path.exists() else None
if font is None:
    raise RuntimeError('Chinese font unavailable: supply Microsoft YaHei before building')

def label(name, text, center, width):
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    data = bpy.data.curves.new(name, 'FONT')
    data.body = text
    data.font = font
    data.align_x = 'CENTER'
    data.align_y = 'CENTER'
    data.size = .01
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = center
    obj.rotation_euler = (math.pi/2,0,0)
    obj.data.materials.append(ink)
    bpy.context.view_layer.update()
    obj.scale *= min(1, width/max(obj.dimensions.x, .001))
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    cube(name+'-BACKPLATE', (center[0],center[1]+.0015,center[2]), (width+.005,.002,.013), paper)

for obj in bpy.data.objects:
    if obj.name.startswith('GEO-V14-CALLOUT-TEXT'):
        obj.data.materials.clear()
        obj.data.materials.append(ink)
    elif obj.name.startswith('GEO-V14-CALLOUT-PLATE'):
        obj.data.materials.clear()
        obj.data.materials.append(paper)
control_labels = [
 ('CTRL','主控板',(-.54,-.34,.43)),
 ('ESTOP','急停',(-.45,-.34,.43)),
 ('PSU','12V电源',(-.36,-.34,.43)),
 ('TFT','显示屏',(-.54,-.34,.405)),
 ('ESP','无线通信',(-.45,-.34,.405)),
 ('IF01','接口板',(-.36,-.34,.405)),
 ('FUSE','保险座',(-.45,-.34,.215)),
]
for code, text, position in control_labels:
    name = 'GEO-V13-LABEL-'+code
    if bpy.data.objects.get(name):
        label(name, text, position, .065)
    leader = bpy.data.objects.get('GEO-V13-LABEL-LINE-'+code)
    if leader:
        # Old lines referred to old text positions; exclude misleading lines.
        bpy.data.objects.remove(leader, do_unlink=True)
    target_name = {'CTRL':'CTRL-01','ESTOP':'MESH_ESTOP_01','PSU':'MESH_PSU_12V_01','TFT':'MESH_DISP_01','ESP':'MESH_ESP01S_01','IF01':'MESH_V12-IF01-BOARD','FUSE':'MESH_FUSE_HOLDER_01'}[code]
    target_bounds = bounds(bpy.data.objects[target_name])
    anchor = [(target_bounds[0][j]+target_bounds[1][j])/2 for j in range(3)]
    tube('GEO-V13-LABEL-LINE-'+code, [list(position),anchor], .00035, steel)
label('GEO-V08-BT01-LABEL','蓝牙（可选）',(-.455,-.334,.325),.061)
label('GEO-V09-RETURN-LABEL','回水管（示意）',(.34,-.253,.399),.11)

bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        obj.select_set(True)
candidate = out / 'utility-tunnel-annular-v09-candidate.glb'
bpy.ops.export_scene.gltf(filepath=str(candidate), export_format='GLB', use_selection=True, export_yup=True, export_apply=True)
doc = glb_json(candidate)
asset_map = json.loads((out / 'asset-map-v07-final.json').read_text(encoding='utf-8'))
asset_map.update(version='V09-CANDIDATE', date='2026-09-07', sourceVersion='V08 published GLB filtered by V07 node inventory; isolated V09 visual repair', model=candidate.name, sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
asset_map.pop('layout', None)  # Historical group bounds are not V09 measurements.
asset_map['assets'].append({'asset_id':'BT-01','meshNames':['MESH_BT_01','GEO-V09-BT01-SUPPORT'],'status':'OPTIONAL_VISUAL_ONLY','label':'蓝牙模块（可选，非主链路）'})
for asset in asset_map['assets']:
    if asset['asset_id'] == 'GAS-01':
        asset['meshNames'] = ['MESH_GAS_SAMPLE_MANIFOLD_01']
asset_map['runtimeValidation'] = {'glbNodes':len(doc['nodes']), 'status':'PENDING_GATE'}
(out / 'asset-map-v09-candidate.json').write_text(json.dumps(asset_map, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(out / 'v09-structural-audit.json').write_text(json.dumps({'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'excludedLegacyNodes':excluded,'btBefore':bt_before,'btAfter':bounds(bpy.data.objects['MESH_BT_01']),'levelStations':checks,'routes':routes,'scope':'visual candidate only; no physical commissioning approval'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Diagnostic cutaways, not a fabricated beauty shot. Export includes the shell;
# only render views hide enclosure and lid for inspection.
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'MATERIAL'
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.background_type = 'WORLD'
scene.world = bpy.data.worlds.new('V09 Inspection World')
scene.world.color = (.12,.12,.12)
scene.render.resolution_x = 1600
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
for obj in bpy.data.objects:
    if any(key in obj.name for key in ('ACRYLIC','ROOF-FULL','ROOF-RETAINER')):
        obj.hide_render = True
camdata = bpy.data.cameras.new('V09 Inspection')
camera = bpy.data.objects.new('V09 Inspection', camdata)
scene.collection.objects.link(camera)
scene.camera = camera
camdata.type = 'ORTHO'
views = [
 ('overview', (1.5,-2.8,2.2), (0,0,.25), 2.2),
 ('front', (0,-3,.55), (0,0,.30), 2.2),
 ('top', (0,0,3), (0,0,.2), 2.2),
 ('water', (.42,-1.3,.9), (.33,-.18,.29), .95),
 ('control', (-.45,-1,.62), (-.45,-.28,.33), .52),
]
for name, position, target, scale in views:
    camera.location = position
    camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camdata.ortho_scale = scale
    scene.render.filepath = str(preview / f'v09-{name}.png')
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'utility-tunnel-annular-v09-candidate.blend'), compress=True)
print('V09 candidate exported with',len(doc['nodes']),'nodes; excluded',len(excluded))
