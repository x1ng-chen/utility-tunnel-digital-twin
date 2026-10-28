"""MCP export V24 and render synthetic powered lighting separately from the saved off state."""
import bpy,json,math,hashlib,struct,copy
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parent
s=bpy.context.scene;assert Path(bpy.data.filepath).parent.resolve()==ROOT.resolve()
report=json.loads((ROOT/'fan-mount-review.json').read_text(encoding='utf-8'))
for n in [1,2]:
    fan=bpy.data.objects[f'FAN-{n:02}'];frame=bpy.data.objects[f'FAN-{n:02}_FRAME']
    mesh=frame.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
    size=[max(v.co[i] for v in mesh.vertices)-min(v.co[i] for v in mesh.vertices) for i in range(3)]
    assert max(abs(a-b) for a,b in zip(size,[.120,.120,.025]))<.0001,(frame.name,size)
    frame.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
    assert len([o for o in fan.children if o.get('fanRgb')])==24
    assert len([o for o in bpy.data.objects[f'FAN-{n:02}_ROTOR'].children if 'BLADE' in o.name])==7
    wall=bpy.data.objects[fan['wallNode']]
    centre=Vector(wall['openingCentreWorld_m'])
    origin=centre+Vector((0,-.03,0))
    loc=wall.matrix_world.inverted()@origin
    direction=wall.matrix_world.inverted().to_3x3()@Vector((0,1,0))
    assert not wall.ray_cast(loc,direction,distance=.06)[0],'Acrylic still covers the centre aperture'

bpy.ops.object.select_all(action='DESELECT')
for o in s.objects:
    if o.type in {'MESH','CURVE','FONT','EMPTY'} and not any(c.name=='99_STUDIO' for c in o.users_collection):o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(ROOT/(ROOT.name+'.glb')),export_format='GLB',use_selection=True,export_extras=True,export_apply=True,export_cameras=False,export_lights=False,export_yup=True,export_animations=False)
raw=(ROOT/(ROOT.name+'.glb')).read_bytes();gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
assert len(gltf['nodes'])==len({node['name'] for node in gltf['nodes']})
assert sum(bool(n.get('extras',{}).get('assetCode')) for n in gltf['nodes'])==69
assert sum(n.get('extras',{}).get('category')=='external_sensor' for n in gltf['nodes'])==31
assert not gltf.get('animations')
report.update({'status':'PASS','glbNodes':len(gltf['nodes']),'glbSha256':hashlib.sha256(raw).hexdigest(),'nativeCentreRaysThroughBothApertures':True,'frameDimensionsMeasuredFromEvaluatedMeshMm':[120,120,25],'savedDefaultEmission':0})
settings=(s.camera,s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage,s.cycles.samples,s.render.filepath)
original_composite=s.use_nodes
def aim(cam,position,target):
    pos=Vector(position);cam.matrix_world=Matrix.Translation(pos)@(Vector(target)-pos).to_track_quat('-Z','Y').to_matrix().to_4x4()
def camera(name,position,target,scale):
    cam=bpy.data.objects.get(name)
    if not cam:cam=bpy.data.objects.new(name,bpy.data.cameras.new(name));bpy.data.collections['99_STUDIO'].objects.link(cam)
    cam.data.type='ORTHO';cam.data.ortho_scale=scale;aim(cam,position,target);return cam
cam=camera('VIEW_FAN_INSET_DETAIL',(.30,1.08,.30),(.35,.698,.22),.23)
led_materials=[m for m in bpy.data.materials if m.get('fanPowerOnly')]
try:
    # Powered preview is an explicit visual example, never written into the live model.
    for mat in led_materials:
        p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Emission Strength'].default_value=3
    s.render.resolution_percentage=100;s.cycles.samples=96
    s.camera=cam;s.render.resolution_x=1100;s.render.resolution_y=1000
    s.render.filepath=str(ROOT/'previews/fan-inset-powered-example.png');bpy.ops.render.render(write_still=True)
    s.camera=bpy.data.objects['VIEW_REFINED_HERO'];s.render.resolution_x=1700;s.render.resolution_y=1530
    s.render.filepath=str(ROOT/'previews/overall-powered-example.png');bpy.ops.render.render(write_still=True)
finally:
    for mat in led_materials:
        p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Emission Strength'].default_value=0
    s.camera,s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage,s.cycles.samples,s.render.filepath=settings
    s.use_nodes=original_composite
bpy.ops.object.select_all(action='DESELECT')
report['previewsAreSyntheticPowerExample']=True
assert report['protectedInputFiles']=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in report['protectedInputFiles']}
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/(ROOT.name+'.blend')),compress=True)
report['blendSha256']=hashlib.sha256((ROOT/(ROOT.name+'.blend')).read_bytes()).hexdigest()
(ROOT/'fan-mount-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','glbNodes','nativeCentreRaysThroughBothApertures','glbSha256','blendSha256']},ensure_ascii=False))
