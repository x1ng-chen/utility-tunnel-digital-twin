import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910/control-labels'
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds
bpy.ops.wm.open_mainfile(filepath=str(out/'control-labels-trial.blend'))
expected={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
for o in list(bpy.data.objects):
    if o.type=='MESH':bpy.data.objects.remove(o,do_unlink=True)
bpy.ops.import_scene.gltf(filepath=str(out/'control-labels-trial.glb'))
actual={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
assert set(expected)==set(actual),'Mesh names changed'
error=max(abs(a-b) for n in expected for aa,bb in zip(expected[n],actual[n]) for a,b in zip(aa,bb))
assert error<1e-5,error
assert all(math.isfinite(c) for o in bpy.data.objects if o.type=='MESH' for v in o.data.vertices for c in v.co)
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_render=any(k in o.name for k in ['ACRYLIC','ROOF-FULL'])
scene=bpy.context.scene;focus=Vector((-.45,-.32,.407));camera=scene.camera
camera.location=focus+Vector((0,-1,0));camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler()
scene.render.filepath=str(out/'fresh-glb-front.png');bpy.ops.render.render(write_still=True)
r=json.loads((out/'review.json').read_text(encoding='utf-8'));r.update(freshImport={'meshCount':len(actual),'namesMatch':True,'maxBoundsError':error,'finiteCoordinates':True},status='LOCAL_FIX_VERIFIED_WITH_REMAINING_ANNOTATION_DEFECTS')
(out/'review.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print('FRESH_IMPORT_PASS',flush=True)
