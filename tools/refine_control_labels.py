"""Unify remaining bare control labels with the existing plaque layout."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector,Matrix
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910/control-labels';out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260910/labels-input.blend'))
original={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=1400;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True;scene.view_settings.view_transform='Standard';scene.view_settings.look='None';camera=scene.camera;camera.data.type='ORTHO'
focus=Vector((-.45,-.32,.407))
def render(prefix):
    for o in bpy.data.objects:
        if o.type=='MESH':o.hide_render=any(k in o.name for k in ['ACRYLIC','ROOF-FULL'])
    for tag,d in [('front',(0,-1,0)),('angle',(.25,-1,.12))]:
        camera.location=focus+Vector(d);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.31;scene.render.filepath=str(out/f'{prefix}-{tag}.png');bpy.ops.render.render(write_still=True)
render('before')
changed=[]
for tag,x,target in [('BUZZ',-.54,'MESH_BUZZ_01'),('RELAY',-.45,'MESH_RELAY_01'),('FANDRV',-.36,'MESH_V12-FAN-DRV-01')]:
    n='GEO-V13-LABEL-'+tag;o=bpy.data.objects[n];lo,hi=bounds(o);center=(Vector(lo)+Vector(hi))/2
    destination=Vector((x,-.340,.380));o.data=o.data.copy()
    for v in o.data.vertices:v.co=(o.matrix_world@v.co-center)*.42+destination
    o.matrix_world=Matrix.Identity(4);o.data.materials.clear()
    for m in bpy.data.objects['GEO-V13-LABEL-CTRL'].data.materials:o.data.materials.append(m)
    changed.append(n)
    template=bpy.data.objects['GEO-V13-LABEL-CTRL-BACKPLATE'];plate=template.copy();plate.data=template.data.copy();plate.name=n+'-BACKPLATE';bpy.context.collection.objects.link(plate)
    lo,hi=bounds(plate);plate.location+=Vector((x,-.3385,.380))-(Vector(lo)+Vector(hi))/2
    leader=bpy.data.objects['GEO-V13-LABEL-LINE-'+tag];lo,hi=bounds(bpy.data.objects[target]);endpoint=(Vector(lo)+Vector(hi))/2
    curve=bpy.data.curves.new(leader.name+' rerouted','CURVE');curve.dimensions='3D';curve.bevel_depth=.00035;curve.bevel_resolution=2;curve.use_fill_caps=True;s=curve.splines.new('POLY');s.points.add(1)
    s.points[0].co=(*destination,1);s.points[1].co=(*endpoint,1)
    temp=bpy.data.objects.new('QA leader',curve);bpy.context.collection.objects.link(temp)
    for m in leader.data.materials:curve.materials.append(m)
    bpy.ops.object.select_all(action='DESELECT');temp.select_set(True);bpy.context.view_layer.objects.active=temp;bpy.ops.object.convert(target='MESH')
    leader.data=temp.data.copy();leader.matrix_world=Matrix.Identity(4);bpy.data.objects.remove(temp,do_unlink=True);changed.append(leader.name)
bpy.context.view_layer.update()
assert all(bounds(bpy.data.objects[n])==bs for n,bs in original.items() if n not in changed),'Unrelated geometry moved'
render('after')
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_set(False);o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'control-labels-trial.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'control-labels-trial.blend'),compress=True)
(out/'review.json').write_text(json.dumps({'changed':changed,'newPlaques':3,'existingHardwareBoundsUnchanged':True,'status':'AWAITING_SCREENSHOT_REVIEW','scope':'Buzzer relay fan-driver bare labels unified into third plaque row; annotation layout, not physical signs'},ensure_ascii=False,indent=2),encoding='utf-8')
print('LABEL_LAYOUT_DONE',flush=True)
