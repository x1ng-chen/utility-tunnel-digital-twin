"""2026-09-09 isolated air-pump assembly refinement; never overwrite V10.

Stages: preserved candidate -> fixed evidence -> structural repair -> export
and fresh import -> same evidence. The whole-model iteration remains ongoing.
"""
import bpy
import json
import hashlib
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

root=Path(sys.argv[sys.argv.index('--')+1]).resolve()
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import audit,bounds
out=root/'_qa_iteration_20260909'
out.mkdir(exist_ok=True)
source=root/'_qa_iteration_20260908/live-before-iteration.blend'
if not source.exists():source=root/'model/sources/2026-09-08-iteration-input.blend'
bpy.ops.wm.open_mainfile(filepath=str(source))
for o in bpy.data.objects:
    matrix=o.matrix_world.copy();o.parent=None;o.matrix_world=matrix
bpy.context.view_layer.update()
members=sorted(o.name for o in bpy.data.objects if o.name.startswith('GEO_AIR_PUMP_01_'))
assert len(members)==7,members
body='MESH_AIR_PUMP_01'
route='MESH_AIR_IN_01_SAFE_ROUTE'
original={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}


def bvh(obj):
    return BVHTree.FromPolygons([obj.matrix_world@v.co for v in obj.data.vertices],
                               [list(p.vertices) for p in obj.data.polygons])


def pair_contacts(names):
    cache={o.name:bvh(o) for o in bpy.data.objects if o.type=='MESH'}
    bs={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
    result={}
    for a in names:
        result[a]=[]
        for n in cache:
            if n==a:continue
            lo,hi=bs[a];l,h=bs[n]
            if any(min(hi[k],h[k])-max(lo[k],l[k])<-1e-6 for k in range(3)):continue
            if cache[a].overlap(cache[n]):result[a].append(n)
    return result


views=[('front',(0,-1,0)),('back',(0,1,0)),('left',(-1,0,0)),
       ('right',(1,0,0)),('top',(0,0,1)),('hero',(1,-2,1.2))]
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=1000;scene.render.resolution_y=700
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL'
scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.display.shading.background_type='WORLD'
scene.world.color=(.18,.18,.18)
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None';scene.view_settings.exposure=0;scene.view_settings.gamma=1
camera=scene.camera
assert camera is not None
camera.data.type='ORTHO'
focus=Vector((.52,-.02,.37))


def evidence(prefix,full=False):
    for o in bpy.data.objects:
        if o.type=='MESH':
            o.hide_render=(any(s in o.name for s in ('ACRYLIC','ROOF-FULL')) if full else
                           o.name not in set(members+[body,route,'MESH_AIR_CHECK_VALVE_01','MESH_AIR_FLOW_METER_01']))
    for name,direction in views:
        camera.location=focus+Vector(direction)
        camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.ortho_scale=.43
        if full:
            if name!='hero':continue
            camera.location=(1.5,-2.8,2.2)
            camera.rotation_euler=(Vector((0,0,.25))-camera.location).to_track_quat('-Z','Y').to_euler()
            camera.data.ortho_scale=2.2
        scene.render.filepath=str(out/f'{prefix}-{name}.png')
        bpy.ops.render.render(write_still=True)


before=pair_contacts(members)
evidence('before')
evidence('before-context',True)
delta=Vector((-.135,-.10125,0))
for name in members:bpy.data.objects[name].location+=delta
bpy.context.view_layer.update()
for name in members:
    if 'SCREW_' in name:
        bpy.data.objects[name].location.y+=bounds(bpy.data.objects[body])[0][1]+.001-bounds(bpy.data.objects[name])[1][1]
bpy.context.view_layer.update()
after=pair_contacts(members)
assert all(body in after[n] for n in members),'Detached pump attachment'
assert all(route in after[n] for n in members if n.endswith(('INLET','OUTLET'))),'Detached air port'
floor=audit(bpy.data.objects)
assert floor['status']=='PASS',floor
preserved=[]
for name,bs in original.items():
    if name in members:continue
    now=bounds(bpy.data.objects[name])
    assert max(abs(now[a][k]-bs[a][k]) for a in (0,1) for k in range(3))<1e-6,name
    preserved.append(name)
report={'date':'2026-09-09','stage':'structural_refinement','status':'AWAITING_VISUAL_AND_CONNECTION_REVIEW',
        'source':str(source.relative_to(root)),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'members':members,'delta':list(delta),'beforeContacts':before,'afterContacts':after,
        'unchangedMeshes':len(preserved),'floor':floor,
        'newContacts':{n:sorted(set(after[n])-set(before[n])) for n in members},
        'scope':'Air pump accessories only; contact sets include intended joints and require review'}
(out/'air-pump-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
evidence('after')
evidence('after-context',True)
# Export every mesh, not just the isolated inspection subjects.
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_set(False);o.select_set(True)
glb=out/'air-pump-trial.glb'
bpy.ops.export_scene.gltf(filepath=str(glb),export_format='GLB',use_selection=True,
                          export_apply=True,export_yup=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'air-pump-trial.blend'),compress=True)
# Fresh import checks the actual export, not only the authored scene.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(glb))
fresh=pair_contacts(members)
assert all(set(fresh[n])==set(after[n]) for n in members),'Export changed accessory contacts'
report['freshImportFloor']=audit(bpy.data.objects)
assert report['freshImportFloor']['status']=='PASS'
report['exportSha256']=hashlib.sha256(glb.read_bytes()).hexdigest()
report['freshImportContacts']=fresh
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_x=1000;scene.render.resolution_y=700
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL'
scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.display.shading.background_type='WORLD'
scene.world=bpy.data.worlds.new('QA World');scene.world.color=(.18,.18,.18)
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
camera=bpy.data.objects.new('QA Camera',bpy.data.cameras.new('QA Camera'))
scene.collection.objects.link(camera);scene.camera=camera;camera.data.type='ORTHO'
evidence('fresh')
import numpy as np
sheet=np.ones((1400,3000,4),dtype=np.float32)
for row,prefix in enumerate(('before','after')):
    for col,view in enumerate(('front','top','hero')):
        im=bpy.data.images.load(str(out/f'{prefix}-{view}.png'),check_existing=False)
        pixels=np.empty(1000*700*4,dtype=np.float32);im.pixels.foreach_get(pixels)
        sheet[(1-row)*700:(2-row)*700,col*1000:(col+1)*1000,:]=pixels.reshape(700,1000,4)
image=bpy.data.images.new('Before above - after below',width=3000,height=1400)
image.pixels.foreach_set(sheet.ravel());image.filepath_raw=str(out/'paired-contact-sheet.png');image.file_format='PNG';image.save()
report['connectionChecks']='PASS: all seven attachments contact body; both ports contact air route'
report['contactSheet']='paired-contact-sheet.png: before above, after below; front/top/hero'
(out/'air-pump-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('AIR_PUMP_TRIAL_EXPORTED',json.dumps(report['newContacts']),flush=True)
