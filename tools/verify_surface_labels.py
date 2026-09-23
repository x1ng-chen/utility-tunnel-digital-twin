import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910/surface-labels-v2'
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds
bpy.ops.wm.open_mainfile(filepath=str(out/'surface-labels-trial.blend'))
for o in list(bpy.data.objects):
    if o.type=='MESH':bpy.data.objects.remove(o,do_unlink=True)
bpy.ops.import_scene.gltf(filepath=str(out/'surface-labels-trial.glb'))
expected=json.loads((out/'expected.json').read_text(encoding='utf-8'));actual={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
assert set(expected)==set(actual)
error=max(abs(a-b) for n in expected for aa,bb in zip(expected[n],actual[n]) for a,b in zip(aa,bb));assert error<1e-5
assert all(math.isfinite(c) for o in bpy.data.objects if o.type=='MESH' for v in o.data.vertices for c in v.co)
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_render=any(k in o.name for k in ['ACRYLIC','ROOF-FULL'])
scene=bpy.context.scene;camera=scene.camera
for tag,target in [('LEDA','MESH_WS2812B_STRIP_ZA'),('LEDB','MESH_WS2812B_STRIP_ZB'),('CONTACT','MESH_DOOR_CONTACT_01')]:
    lo,hi=map(Vector,bounds(bpy.data.objects[target]));focus=(lo+hi)/2;camera.location=focus+Vector((.22,-1,.16));camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.24 if tag.startswith('LED') else .13
    scene.render.filepath=str(out/f'fresh-{tag}.png');bpy.ops.render.render(write_still=True)
r=json.loads((out/'iteration_review.json').read_text(encoding='utf-8'));r['freshImport']={'meshes':len(actual),'namesMatch':True,'maximumBoundsError':error,'finiteVertices':True}
(out/'iteration_review.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print('FRESH_SURFACE_PASS',flush=True)
