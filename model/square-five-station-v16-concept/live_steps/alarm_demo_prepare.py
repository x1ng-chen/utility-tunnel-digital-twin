"""P=1..5; temporary Blender-only simulated alarm view, never platform telemetry."""
import bpy,json
from mathutils import Vector
from pathlib import Path
ROOT=Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v16-concept')
scene=bpy.context.scene
bindings=json.loads((ROOT/'sensor-bindings.json').read_text(encoding='utf-8'))['bindings']
states_key='MCP_SIMULATED_ALARM_STATE'
if states_key not in scene:
    names=set()
    for b in bindings:
        root=bpy.data.objects[b['targetNode']]
        names.update(o.name for o in [root,*root.children_recursive] if o.type=='MESH')
    names.update(f'P{n}_CARRIER' for n in range(1,6))
    cover=bpy.data.objects['REMOVABLE_TRANSPARENT_LID']
    hidden=[o.name for o in [cover,*cover.children_recursive]]+[f'CLEAR_WALL_{s}' for s in ['TOP','BOTTOM','LEFT','RIGHT']]
    state={'camera':scene.camera.name,'materials':{name:[m.name for m in bpy.data.objects[name].data.materials] for name in names},
        'hidden':{name:bpy.data.objects[name].hide_get() for name in hidden}}
    scene[states_key]=json.dumps(state)
else: state=json.loads(scene[states_key])
for name,materials in state['materials'].items():
    obj=bpy.data.objects[name]; obj.data.materials.clear()
    for material in materials: obj.data.materials.append(bpy.data.materials[material])
for name in state['hidden']: bpy.data.objects[name].hide_set(True)
def material(name,color,emission=0):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color=(*color,1); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*color,1)
    p.inputs['Emission Color'].default_value=(*color,1); p.inputs['Emission Strength'].default_value=emission
    return m
red=material('DEMO_ONLY_ALARM_RED',(1,.025,.01),.35)
amber=material('DEMO_ONLY_STATION_AMBER',(1,.56,.015),.1)
ink=material('DEMO_ONLY_INK',(.015,.03,.045),0)
paper=material('DEMO_ONLY_PAPER',(.9,.95,.98),.2)
b=next(b for b in bindings if b['physicalTag']==f'MQ2-{P:02}')
root=bpy.data.objects[b['targetNode']]
for obj in [root,*root.children_recursive]:
    if obj.type=='MESH': obj.data.materials.clear(); obj.data.materials.append(red)
carrier=bpy.data.objects[f'P{P}_CARRIER']; carrier.data.materials.clear(); carrier.data.materials.append(amber)
cam=bpy.data.objects.get('DEMO_ONLY_ALARM_CAMERA')
if cam is None:
    d=bpy.data.cameras.new('DEMO_ONLY_ALARM_CAMERA'); d.type='ORTHO'; d.ortho_scale=.24; d.clip_start=.001
    cam=bpy.data.objects.new('DEMO_ONLY_ALARM_CAMERA',d); bpy.data.collections['99_STUDIO'].objects.link(cam)
target=root.matrix_world.translation+Vector((0,0,.008))
cam.location=target+Vector((.13,-.16,.25))
cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
caption=bpy.data.objects.get('DEMO_ONLY_CAPTION')
if caption is None:
    d=bpy.data.curves.new('DEMO_ONLY_CAPTION','FONT'); d.size=.008; d.align_y='TOP'
    caption=bpy.data.objects.new('DEMO_ONLY_CAPTION',d); bpy.data.collections['90_ANNOTATIONS'].objects.link(caption)
    caption.parent=cam; caption.location=(-.108,.089,-.069); caption.data.materials.append(ink)
    bpy.ops.mesh.primitive_plane_add(size=1)
    plate=bpy.context.object; plate.name='DEMO_ONLY_CAPTION_PLATE'
    for c in list(plate.users_collection): c.objects.unlink(plate)
    bpy.data.collections['90_ANNOTATIONS'].objects.link(plate)
    plate.parent=cam; plate.location=(0,.077,-.070); plate.rotation_euler=(0,0,0); plate.scale=(.226,.039,1)
    plate.data.materials.append(paper)
caption.data.body=f'SIMULATED  P{P} / {b["controllerId"]}\n{b["physicalTag"]}  |  {b["assetCode"]}'
scene.camera=cam
bpy.context.view_layer.update()
bad=[]
for other in bindings:
    obj=bpy.data.objects[other['targetNode']]
    if other['assetCode']!=b['assetCode'] and any(m and m.name==red.name for m in obj.data.materials): bad.append(other['assetCode'])
assert not bad
print(json.dumps({'dataSource':'SIMULATED_BLENDER_ONLY','assetCode':b['assetCode'],'physicalTag':b['physicalTag'],
    'stationId':b['stationId'],'controllerId':b['controllerId'],'targetNode':b['targetNode'],
    'cameraTargetBlender_m':list(target),'otherSensorRootsTinted':bad,'platformAlarmIntegration':'NOT_EXECUTED'}))
