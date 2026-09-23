"""Attach four existing Chinese mesh labels to their identified housing faces."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector,Matrix
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910/surface-labels-v2';out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260910/surface-labels-input.blend'))
original={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
spec=[('LEDA','MESH_WS2812B_STRIP_ZA',.038,.007),('LEDB','MESH_WS2812B_STRIP_ZB',.038,.007),('LEDC','MESH_WS2812B_STRIP_ZC',.038,.007),('CONTACT','MESH_DOOR_CONTACT_01',.027,.008)]
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=1000;scene.render.resolution_y=700;scene.render.resolution_percentage=100;scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True;scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
camera=scene.camera;camera.data.type='ORTHO'
def render(prefix):
    for o in bpy.data.objects:
        if o.type=='MESH':o.hide_render=any(k in o.name for k in ['ACRYLIC','ROOF-FULL'])
    for tag,target,w,h in spec:
        lo,hi=map(Vector,bounds(bpy.data.objects[target]));focus=(lo+hi)/2
        for view,d in [('front',(0,-1,0)),('angle',(.22,-1,.16))]:
            camera.location=focus+Vector(d);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.24 if tag.startswith('LED') else .13
            scene.render.filepath=str(out/f'{prefix}-{tag}-{view}.png');bpy.ops.render.render(write_still=True)
render('before')
changed=[];removed=[];contacts=[]
for tag,target,w,h in spec:
    n='GEO-V13-LABEL-'+tag;o=bpy.data.objects[n];lo,hi=map(Vector,bounds(bpy.data.objects[target]));center=(lo+hi)/2
    if tag=='LEDB':center.x-=.065
    z=center.z if tag.startswith('LED') else hi.z-.006
    destination=Vector((center.x,lo.y-.00065,z));a,b=map(Vector,bounds(o));c=(a+b)/2;scale=min((w-.004)/(b.x-a.x),(h-.002)/(b.z-a.z))
    o.data=o.data.copy()
    for v in o.data.vertices:
        p=(o.matrix_world@v.co-c)*scale+destination;p.y=destination.y;v.co=p
    o.matrix_world=Matrix.Identity(4);o.data.materials.clear()
    for m in bpy.data.objects['GEO-V13-LABEL-CTRL'].data.materials:o.data.materials.append(m)
    bpy.ops.mesh.primitive_cube_add(size=1,location=(center.x,lo.y-.0003,z));plate=bpy.context.object;plate.name=n+'-BACKPLATE';plate.dimensions=(w,.0006,h);bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    for m in bpy.data.objects['GEO-V13-LABEL-CTRL-BACKPLATE'].data.materials:plate.data.materials.append(m)
    plate['annotation_mount']='housing-front-face; visual nameplate, adhesive specification unverified'
    line=bpy.data.objects['GEO-V13-LABEL-LINE-'+tag];removed.append(line.name);bpy.data.objects.remove(line,do_unlink=True);changed.append(n)
    bpy.context.view_layer.update();pmin,pmax=bounds(plate)
    gap=abs(pmax[1]-lo.y);assert gap<1e-6
    assert pmin[0]>=lo.x and pmax[0]<=hi.x and pmin[2]>=lo.z and pmax[2]<=hi.z
    contacts.append({'tag':tag,'housing':target,'surfaceGap':gap,'insideFaceBounds':True})
assert all(bounds(bpy.data.objects[n])==bs for n,bs in original.items() if n not in changed+removed)
render('after')
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_set(False);o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'surface-labels-trial.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'surface-labels-trial.blend'),compress=True)
expected={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
(out/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
(out/'iteration_review.json').write_text(json.dumps({'stage':'presentation_polish_and_export','contract':'Four housing-mounted Chinese labels; preserve all hardware geometry and scale','beforeLedger':{'bareLabels':'fail','hardwareIdentity':'pass for selected four; DOOR label excluded pending identity review'},'changed':changed,'removedAnnotationLeaders':removed,'contacts':contacts,'hardwareBoundsUnchanged':True,'decision':'pending_visual_review'},ensure_ascii=False,indent=2),encoding='utf-8')
print('SURFACE_LABELS_DONE',flush=True)
