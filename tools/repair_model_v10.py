"""Scoped V09 -> V10 floor repair. Run in an ISOLATED Blender process.

blender -b --python tools/repair_model_v10.py -- <root> [source.blend]
Default source is the preserved published V09; optional live checkpoint allows
retaining unsaved user geometry. Does not modify V09 or production V07.
"""
import bpy
import hashlib
import json
import struct
import sys
from pathlib import Path
from mathutils import Vector

root = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
args = sys.argv[sys.argv.index('--') + 2:]
source = Path(args[0]) if args else root / 'model/utility-tunnel-annular-v09-candidate.blend'
sys.path.insert(0, str(root / 'tools'))
from model_floor_audit import audit, bounds

out = root / 'model'
preview = out / 'previews'
qa = root / '_qa_v10'
qa.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
for obj in bpy.data.objects:
    matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = matrix
bpy.context.view_layer.update()
before = audit(bpy.data.objects)
(qa / 'floor-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
original = {o.name: bounds(o) for o in bpy.data.objects if o.type == 'MESH'}
floor_top = before['floorTop']
changes = []
steel = bpy.data.materials['V09 安装件 · 银灰']


def move(names, delta, reason):
    names = sorted(names)
    for name in names:
        bpy.data.objects[name].location += Vector(delta)
    changes.append({'action': 'translate-assembly', 'nodes': names, 'delta': delta, 'reason': reason})
    bpy.context.view_layer.update()


def resize_bottom(name, new_bottom):
    obj = bpy.data.objects[name]
    lo, hi = bounds(obj)
    inv = obj.matrix_world.inverted()
    for vertex in obj.data.vertices:
        p = obj.matrix_world @ vertex.co
        p.z = new_bottom + (p.z-lo[2]) * (hi[2]-new_bottom)/(hi[2]-lo[2])
        vertex.co = inv @ p
    obj.data.update()
    changes.append({'action': 'shorten-bottom-keep-top', 'nodes': [name], 'oldBottom': lo[2], 'newBottom': new_bottom})
    bpy.context.view_layer.update()


def fit_height(name, bottom, top):
    obj=bpy.data.objects[name]
    lo,hi=bounds(obj)
    inv=obj.matrix_world.inverted()
    for v in obj.data.vertices:
        p=obj.matrix_world@v.co
        p.z=bottom+(p.z-lo[2])*(top-bottom)/(hi[2]-lo[2])
        v.co=inv@p
    obj.data.update()
    bpy.context.view_layer.update()
    changes.append({'action':'fit-mount-height','nodes':[name],'bottom':bottom,'top':top})


def support(name, xy, size_xy, top):
    bottom = floor_top
    assert top > bottom
    bpy.ops.mesh.primitive_cube_add(size=1, location=(*xy, (top+bottom)/2))
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = (*size_xy, top-bottom)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(steel)
    obj['中文名称'] = name.split('__')[-1]
    changes.append({'action': 'add-floor-support', 'nodes': [name], 'bottom': bottom, 'top': top})
    return obj


# Classify water components so the drain station can move as a complete unit
# while the four other stations and main circuit retain their coordinates.
water_exact = {'P-01', 'V-01', 'WATER-TANK-01', 'WATER-TRAY-01', 'LEAK-W01',
               'MESH_HILEVEL_01', 'GEO_HILEVEL_FLOAT_01', 'MESH_LEAK_W01',
               'MESH_SEEP_W01', 'GEO_MESH_SEEP_W01_LENS', 'MESH_PIPE_W01', 'MESH_DRIP_W01'}
water_prefixes = ('GEO-V09-WATER-', 'GEO-V09-P01-', 'GEO-V09-L0',
                  'GEO-V09-RETURN-LABEL', 'MESH_WATER_', 'GEO_WATER_', 'GEO_WET_DRY_PARTITION_')
water_names = {o.name for o in bpy.data.objects if o.type == 'MESH' and
               (o.name in water_exact or o.name.startswith(water_prefixes) or 'FSIR02_L' in o.name or
                ('CALLOUT-' in o.name and any(o.name.endswith(f'_L{i:02}') for i in range(1,6))) or
                o.name.startswith(tuple('GEO-V13-LABEL-'+s for s in ('LVL','LINE-LVL','PUMP','LINE-PUMP','VALVE','LINE-VALVE','TRAY','LINE-TRAY','SEEP','LINE-SEEP','FLOAT','LINE-FLOAT'))))}
# Historical lens had an unrelated stale transform inside the foundation.
lens = bpy.data.objects['GEO_MESH_SEEP_W01_LENS']
lo, hi = bounds(bpy.data.objects['MESH_SEEP_W01'])
lc = sum((Vector(p) for p in bounds(lens)), Vector())/2
move([lens.name], [((lo[0]+hi[0])/2-lc.x), lo[1]-.005-lc.y, (lo[2]+hi[2])/2-lc.z], 'Restore indicator to seepage sensor front; do not intersect adjacent drip pipe')
drain_names={n for n in water_names if 'FSIR02_L01' in n or n.endswith('_L01') or
             n.startswith('GEO-V09-L01-') or 'WATER_DRAIN_' in n or 'WATER_MANUAL_DRAIN_' in n or
             n in {'GEO-V13-LABEL-LVL1','GEO-V13-LABEL-LINE-LVL1'}}
move(drain_names, [0,0,.04], 'Raise drain valve/hose/probe station together; main water routes stay fixed')
# Main water stations stay at their existing pipe coordinates. Correct only
# mounting interfaces, not the established routing envelope near the fan.
fit_height('P-01',floor_top,floor_top+.001)
fit_height('GEO-V09-P01-FEET',floor_top+.001,floor_top+.003)
resize_bottom('GEO-V09-P01-PUMP-BODY',floor_top+.003)
move(['GEO-V13-LABEL-PUMP','GEO-V13-LABEL-LINE-PUMP'],[0,0,.03],'Lift pump annotation and its leader clear of floor')
for name in ('MESH_WATER_TRAY_INNER_PAN','MESH_HILEVEL_01','MESH_WATER_BARRIER_01','MESH_WATER_BARRIER_02',
             'GEO-V14-FSIR02_L02_BRACKET','GEO-V14-FSIR02_L03_BRACKET'):
    resize_bottom(name,floor_top)
resize_bottom('GEO-V14-FSIR02_L03_BRACKET',floor_top+.001)
move(['MESH_LEAK_W01'],[0,0,floor_top-original['MESH_LEAK_W01'][0][2]],'Resolve tiny leak sensor penetration')
fit_height('GEO_WET_DRY_PARTITION_GASKET',floor_top,original['GEO_WET_DRY_PARTITION_GASKET'][1][2])

# Display is a separate status board, not the five distributed pipe probes.
status_names = {o.name for o in bpy.data.objects if o.name.startswith('GEO-V11-LEVEL-') or
                ('GEO-V14-CALLOUT-' in o.name and o.name.endswith('-STATUS'))}
for side in ('L','R'):
    foot='GEO-V11-LEVEL-STATUS-FOOT-'+side
    fit_height(foot,floor_top,floor_top+.003)
    resize_bottom('GEO-V11-LEVEL-STATUS-STAND-'+side,floor_top+.003)
move(status_names,[-.15,0,0],'Place status display between simulation box and drain station with separate access')
# Retain the max-fill marker on the tray lip, clear of the relocated valve.
marker=bpy.data.objects['GEO_WATER_MAX_FILL_MARK']
lo,hi=bounds(marker)
inv=marker.matrix_world.inverted()
for v in marker.data.vertices:
    p=marker.matrix_world@v.co
    p.x=-.074+(p.x-lo[0])*.049/(hi[0]-lo[0])
    v.co=inv@p
marker.data.update()
changes.append({'action':'shorten-fill-marker','nodes':[marker.name],'xInterval':[-.074,-.025]})

# Trunking and removable cover move together; no buried duct is left hidden.
fit_height('MESH_CABLE_DUCT_01',floor_top,floor_top+.005)
fit_height('GEO_CABLE_DUCT_COVER',floor_top+.005,floor_top+.007)

# Second-pass image review: the original straight duct occupies the newly
# exposed drain outlet lane. Detour its middle section toward the outer edge,
# keeping both ends, vertical profile, node IDs, cover, and materials.
def detour_duct(name):
    obj = bpy.data.objects[name]
    lo, hi = bounds(obj)
    cy = (lo[1]+hi[1])/2
    half = (hi[1]-lo[1])/2
    sections = [(lo[0],cy,half),(-.16,cy,half),(-.115,-.313,.011),
                (.10,-.313,.011),(.15,cy,half),(hi[0],cy,half)]
    vertices = []
    for x,y,w in sections:
        vertices.extend([(x,y-w,lo[2]),(x,y+w,lo[2]),(x,y+w,hi[2]),(x,y-w,hi[2])])
    faces = [(3,2,1,0)]
    for i in range(len(sections)-1):
        a,b = 4*i,4*(i+1)
        for j in range(4):
            k=(j+1)%4
            faces.append((a+j,a+k,b+k,b+j))
    faces.append(tuple(range(len(vertices)-4,len(vertices))))
    mesh = bpy.data.meshes.new(name+' V10 drain bypass')
    inv = obj.matrix_world.inverted()
    mesh.from_pydata([inv@Vector(v) for v in vertices],[],faces)
    for material in obj.data.materials:
        mesh.materials.append(material)
    obj.data = mesh
    changes.append({'action':'drain-lane-detour','nodes':[name],
                    'sections':sections,'reason':'Keep raised cable duct clear of drain hose'})
for name in ('MESH_CABLE_DUCT_01','GEO_CABLE_DUCT_COVER'):
    detour_duct(name)
bpy.context.view_layer.update()

# Keep manifold elevation fixed: lift feet and shorten only the lower posts.
for i in range(1,4):
    foot = f'GEO_G01_STANCHION_FOOT_{i:02}'
    fit_height(foot,floor_top,floor_top+.001)
    resize_bottom(f'GEO_G01_STANCHION_{i:02}', bounds(bpy.data.objects[foot])[1][2])
move(['GEO_G01_STANCHION_FOOT_01','GEO_G01_STANCHION_01'],[-.12,0,0],
     'Move front manifold support left of tray while retaining manifold elevation')
for name in original:
    if name.startswith('GEO_ACRYLIC_SERVICE_SEAM_') or (name.startswith('GEO_ZONE_') and name.endswith('_RIB')):
        resize_bottom(name, floor_top)
move(['GEO_ZONE_B_FLOOR_KEY'], [0,0,floor_top-original['GEO_ZONE_B_FLOOR_KEY'][0][2]], 'Expose buried B-zone floor marker')

# All repaired supports now terminate directly on the unchanged floor.

# A legacy pipe label was under the foundation; relocate label and its leader
# as a pair to the utility-pipe front (without changing the pipe).
for name in ('GEO-V13-LABEL-PIPE','GEO-V13-LABEL-LINE-PIPE'):
    move([name], [-.22,-.165,.205], 'Bring buried utility pipe annotation above the slab')
from mathutils.bvhtree import BVHTree
pipe=bpy.data.objects['PIPE-G01']
bvh=BVHTree.FromPolygons([pipe.matrix_world@v.co for v in pipe.data.vertices],
                         [list(p.vertices) for p in pipe.data.polygons])
label_center=sum((Vector(p) for p in bounds(bpy.data.objects['GEO-V13-LABEL-PIPE'])),Vector())/2
endpoint=bvh.find_nearest(label_center)[0]
leader=bpy.data.objects['GEO-V13-LABEL-LINE-PIPE']
curve=bpy.data.curves.new('V10 gas label leader','CURVE')
curve.dimensions='3D';curve.bevel_depth=.00035;curve.bevel_resolution=1
spline=curve.splines.new('POLY');spline.points.add(1)
for p,co in zip(spline.points,(label_center,endpoint)):p.co=(*co,1)
temp=bpy.data.objects.new('Temporary label connector',curve)
bpy.context.collection.objects.link(temp)
bpy.ops.object.select_all(action='DESELECT');temp.select_set(True)
bpy.context.view_layer.objects.active=temp;bpy.ops.object.convert(target='MESH')
mesh=temp.data.copy()
for m in leader.data.materials:mesh.materials.append(m)
leader.data=mesh;leader.matrix_world.identity()
bpy.data.objects.remove(temp,do_unlink=True)

bpy.context.view_layer.update()
after = audit(bpy.data.objects)
report = {'version': 'V10-CANDIDATE', 'date': '2026-09-08', 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'source': source.name, 'before': before, 'after': after, 'changes': changes,
          'drainAssembly': sorted(drain_names), 'drainRigidDelta': [0,0,.04],
          'scope': 'Visual floor-clearance repair only; not global clash or fabrication certification'}
(out / 'v10-floor-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
assert after['status'] == 'PASS', 'Remaining floor intersections: '+str([r['name'] for r in after['findings']])

# Existing water connections must retain their relative displacement exactly.
for name in drain_names:
    now = bounds(bpy.data.objects[name])
    assert max(abs(now[a][k]-original[name][a][k]-(.04 if k==2 else 0)) for a in (0,1) for k in range(3)) < 1e-6, name

candidate = out / 'utility-tunnel-annular-v10-candidate.glb'
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        obj.hide_set(False)
        obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(candidate), export_format='GLB', use_selection=True,
                          export_yup=True, export_apply=True, export_animations=False)
data = candidate.read_bytes()
doc = json.loads(data[20:20+struct.unpack_from('<I',data,12)[0]])
asset_map = json.loads((out/'asset-map-v09-candidate.json').read_text(encoding='utf-8'))
asset_map.update(version='V10-CANDIDATE',date='2026-09-08',sourceVersion='V09 floor-clearance repair',
                 model=candidate.name,sha256=hashlib.sha256(data).hexdigest(),
                 runtimeValidation={'glbNodes':len(doc['nodes']),'status':'PENDING_FRESH_IMPORT'})
(out/'asset-map-v10-candidate.json').write_text(json.dumps(asset_map,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')

scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'MATERIAL'
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.render.resolution_x = 1600
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
camera = scene.camera
assert camera is not None
camera.data.type = 'ORTHO'
for obj in bpy.data.objects:
    obj.hide_render = any(s in obj.name for s in ('ACRYLIC','ROOF-FULL','ROOF-RETAINER'))
views = [('overview',(1.5,-2.8,2.2),(0,0,.25),2.2),
         ('front',(0,-3,.32),(0,0,.32),2.1),
         ('side',(2,-.14,.32),(.25,-.14,.32),.85),
         ('water',(.30,-1.3,.85),(.22,-.18,.31),1.2),
         ('drain',(.1,-1,.52),(-.055,-.21,.25),.62),
         ('floor',(.1,-2,.205),(.1,-.17,.205),1.25),
         ('bottom',(0,0,-3),(0,0,.2),2.2)]
for name, position, target, scale in views:
    camera.location = position
    camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale = scale
    scene.render.filepath = str(preview/f'v10-{name}.png')
    if name=='bottom':
        bpy.data.objects['MESH_BASE_01'].hide_render=True
        bpy.data.objects['GEO_UT_RING_RENDER_GROUND'].hide_render=True
    bpy.ops.render.render(write_still=True)
    if name=='bottom':
        bpy.data.objects['MESH_BASE_01'].hide_render=False
        bpy.data.objects['GEO_UT_RING_RENDER_GROUND'].hide_render=False

# Open the saved file in a useful cutaway view. Hidden enclosure geometry is
# retained in Blender and in the exported GLB, not deleted to pass the gate.
for obj in bpy.data.objects:
    if obj.hide_render:
        obj.hide_set(True)
bpy.ops.object.select_all(action='DESELECT')
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.overlay.show_extras = False
            area.spaces.active.region_3d.view_location = (0,-.05,.29)
            area.spaces.active.region_3d.view_distance = 1.9
            area.spaces.active.region_3d.view_rotation = (Vector((0,0,.29))-Vector((1,-2,1.1))).to_track_quat('-Z','Y')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'utility-tunnel-annular-v10-candidate.blend'),compress=True)
print('V10_BUILD_PASS',len(doc['nodes']),flush=True)
