"""September 10 read-only fan visibility/inventory review; independent process."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910';out.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260909/manifold-mount/manifold-mount-trial.blend'))
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds
mapping=json.loads((root/'model/asset-map-v11-candidate.json').read_text(encoding='utf-8'))
inventory=[]
for asset in mapping['assets']:
    names=asset['meshNames'];inventory.append({'asset':asset['asset_id'],'missing':[n for n in names if n not in bpy.data.objects],'empty':[n for n in names if n in bpy.data.objects and bpy.data.objects[n].type=='MESH' and not bpy.data.objects[n].data.vertices]})
fans=[]
for o in bpy.data.objects:
    if o.type=='MESH' and ('FAN' in o.name or 'BLADE' in o.name):fans.append({'name':o.name,'vertices':len(o.data.vertices),'bounds':bounds(o),'hideRender':o.hide_render,'hideViewport':o.hide_viewport,'hidden':o.hide_get()})
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True;scene.view_settings.view_transform='Standard';scene.view_settings.look='None';camera=scene.camera;camera.data.type='ORTHO'
for n in ['FAN-01','FAN-02']:
    lo,hi=bounds(bpy.data.objects[n]);focus=(Vector(lo)+Vector(hi))/2
    for o in bpy.data.objects:
        if o.type=='MESH':o.hide_render=any(t in o.name for t in ['ACRYLIC','ROOF-FULL','LABEL','CALLOUT'])
    for tag,d in [('front',(0,-1,0)),('hero',(1,-2,1.2))]:
        camera.location=focus+Vector(d);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=max(hi[i]-lo[i] for i in range(3))*2.5
        scene.render.filepath=str(out/f'{n}-{tag}.png');bpy.ops.render.render(write_still=True)
(out/'fan-inventory-review.json').write_text(json.dumps({'source':'local manifold-mount trial; rejected oxygen trial excluded','assets':inventory,'fans':fans,'limits':'Inventory presence is not mounting or function approval'},ensure_ascii=False,indent=2),encoding='utf-8')
print('FAN_INVENTORY_COMPLETE',flush=True)
