import bpy,json,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v16-concept')
assert bpy.data.filepath.replace('\\','/').endswith('square-five-station-v16-concept/square-five-station-v16-concept.blend')
def place(obj,name,collection,parent=None):
    obj.name=name
    for c in list(obj.users_collection): c.objects.unlink(obj)
    bpy.data.collections[collection].objects.link(obj)
    if parent:
        bpy.context.view_layer.update()
        world=obj.matrix_world.copy(); obj.parent=parent; obj.matrix_world=world
    return obj
def box(name,xyz,dims,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=Vector(xyz)/1000)
    obj=place(bpy.context.object,name,'08_REMOVABLE_COVER' if parent else '05_VOICE',parent)
    obj.dimensions=Vector(dims)/1000
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(bpy.data.materials['05 Stainless / visual proxy'])
    return obj
def cut(obj,name,xyz,radius,axis):
    bpy.ops.mesh.primitive_cylinder_add(vertices=40,radius=radius/1000,depth=.03,location=Vector(xyz)/1000)
    cutter=bpy.context.object
    if axis=='X': cutter.rotation_euler[1]=math.pi/2
    mod=obj.modifiers.new(name,'BOOLEAN'); mod.operation='DIFFERENCE'; mod.object=cutter
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
def ring(name,xyz,r,parent):
    bpy.ops.mesh.primitive_torus_add(major_segments=40,minor_segments=8,location=Vector(xyz)/1000,major_radius=r/1000,minor_radius=.001)
    obj=place(bpy.context.object,name,'08_REMOVABLE_COVER',parent)
    obj.data.materials.append(bpy.data.materials['05 Stainless / visual proxy'])

lid=bpy.data.objects['REMOVABLE_TRANSPARENT_LID']
if not lid.get('voiceAperturesAdded'):
    for tag,xy,r in [('MIC',(565,390),5),('SPEAKER',(635,350),25)]:
        cut(lid,tag+'_LID_CUT',(*xy,296),r,'Z')
        ring(tag+'_LID_RIM',(*xy,298),r,lid)
    for dx in [-18,-12,-6,0,6,12,18]: box(f'SPEAKER_LID_GRILLE_{dx}',(635+dx,350,299),(1.3,2*math.sqrt(23**2-dx**2),1),lid)
    lid['voiceAperturesAdded']=True
button=bpy.data.objects['VOICE-BUTTON-01']
button.location=(.6975,.305,.160)
button.rotation_euler=(0,math.pi/2,0)
if not button.get('externalWallAccess'):
    cut(bpy.data.objects['CLEAR_WALL_RIGHT'],'VOICE_BUTTON_WALL_CUT',(698,305,160),6,'X')
    box('VOICE_BUTTON_BRACKET',(688,305,152),(20,16,3))
    for obj in list(bpy.data.objects):
        if obj.name.startswith('VOICE-BUTTON-01_GENERIC_MOUNT_'): bpy.data.objects.remove(obj,do_unlink=True)
    c=bpy.data.curves.new('VOICE_BUTTON_TO_BOARD','CURVE'); c.dimensions='3D'; c.bevel_depth=.0006; c.bevel_resolution=1
    s=c.splines.new('POLY'); s.points.add(2)
    for p,xyz in zip(s.points,[(.695,.305,.160),(.675,.305,.160),(.585,.305,.154)]): p.co=(*xyz,1)
    o=bpy.data.objects.new('VOICE_BUTTON_TO_BOARD',c); bpy.data.collections['05_VOICE'].objects.link(o)
    o.data.materials.append(bpy.data.materials['09 RS485 B ivory'])
    button['externalWallAccess']=True
for n,cy in [(1,590),(2,590),(3,110),(4,110)]:
    bpy.data.objects[f'CTRL-{n:02}_LABEL'].location.y=(cy+65 if n<3 else cy-61)/1000
bpy.context.view_layer.update()
inventory=json.loads((ROOT/'asset-map.json').read_text(encoding='utf-8'))
for a in inventory['assets']:
    obj=bpy.data.objects[a['meshNames'][0]]
    a['position_mm']=[round(v*1000,3) for v in obj.matrix_world.translation]
(ROOT/'asset-map.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
bpy.context.scene['modelEditRoute']='LIVE_MCP_execute_blender_code'
bpy.context.scene['revision']='square-five-station-v16-concept'
bpy.context.scene['baseline_commit']='12c1feebe811329c6370f8927dcb14bc733b40f7'
print(json.dumps({'liveMCPRefinement':'DONE','lidOpenings':['microphone','speaker'],'voiceButton_mm':list(button.location*1000),'controllerLabels':'All four moved clear of business displays'}))
