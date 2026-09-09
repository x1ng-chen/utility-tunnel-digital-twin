"""Correct reversed optical ends; local geometry trial, not fabrication approval."""
import bpy,json,sys,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260909/level-optics';out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds,audit
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260909/air-pump-trial.blend'))
original={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
scene=bpy.context.scene;camera=scene.camera;camera.data.type='ORTHO'
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=900;scene.render.resolution_y=650;scene.render.resolution_percentage=100
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
directions=[('front',(0,-1,0)),('back',(0,1,0)),('left',(-1,0,0)),('right',(1,0,0)),('top',(0,0,1)),('hero',(1,-2,1.2))]
centers={}
for i in range(1,6):
    n=f'MESH_V12-FSIR02_L{i:02}_PROBE';lo,hi=original[n];centers[i]=(Vector(lo)+Vector(hi))/2
def render(prefix):
    for i,c in centers.items():
        selected={f'MESH_V12-FSIR02_L{i:02}_PROBE',f'GEO-V12-FSIR02_L{i:02}_OPTIC',f'GEO-V09-L{i:02}-SERVICE-BOSS',f'GEO-V14-FSIR02_L{i:02}_PIPE_CLAMP'}
        # Isolated assembly evidence intentionally omits opaque pipes; not proof of a wetted bore.
        for o in bpy.data.objects:
            if o.type=='MESH':o.hide_render=o.name not in selected
        for label,d in directions:
            focus=c+Vector((0,.004,0));camera.location=focus+Vector(d);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=.044
            scene.render.filepath=str(out/f'{prefix}-L{i:02}-{label}.png');bpy.ops.render.render(write_still=True)
render('before')
records=[]
for i,c in centers.items():
    name=f'GEO-V12-FSIR02_L{i:02}_OPTIC';o=bpy.data.objects[name]
    end=c+Vector((0,.011,0))
    # Cone base overlaps existing service boss; apex faces +Y toward the pipe axis.
    vertices=[];segments=48;base=end-Vector((0,.004,0));tip=end+Vector((0,.0008,0))
    for j in range(segments):
        a=2*math.pi*j/segments;vertices.append(tuple(base+Vector((.0027*math.cos(a),0,.0027*math.sin(a)))))
    vertices.append(tuple(tip));faces=[tuple(reversed(range(segments)))]+[(j,(j+1)%segments,segments) for j in range(segments)]
    mesh=bpy.data.meshes.new(name+' corrected optical tip');mesh.from_pydata(vertices,[],faces);mesh.update()
    for m in o.data.materials:mesh.materials.append(m)
    o.data=mesh;o.matrix_world=Matrix.Identity(4)
    for p in mesh.polygons:p.use_smooth=len(p.vertices)==3
    o['review_status']='Optical direction corrected; bore and seal not approved'
    records.append({'station':f'L{i:02}','beforeBounds':original[name],'tip':list(tip),'pipeAxisTarget':list(end),'direction':'+Y','boreAndSeal':'UNVERIFIED'})
bpy.context.view_layer.update()
changed={f'GEO-V12-FSIR02_L{i:02}_OPTIC' for i in range(1,6)}
for n,bs in original.items():
    if n not in changed:
        now=bounds(bpy.data.objects[n]);assert max(abs(now[a][k]-bs[a][k]) for a in (0,1) for k in range(3))<1e-6,n
floor=audit(bpy.data.objects);assert floor['status']=='PASS'
render('after')
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_render=any(t in o.name for t in ('ACRYLIC','ROOF-FULL'));o.hide_set(False)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'level-optics-trial.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'level-optics-trial.blend'),compress=True)
import numpy as np
sheet=np.ones((1300,4500,4),dtype=np.float32)
for row,prefix in enumerate(('before','after')):
    for i in range(1,6):
        im=bpy.data.images.load(str(out/f'{prefix}-L{i:02}-hero.png'));pixels=np.empty(900*650*4,dtype=np.float32);im.pixels.foreach_get(pixels)
        sheet[(1-row)*650:(2-row)*650,(i-1)*900:i*900]=pixels.reshape(650,900,4)
im=bpy.data.images.new('Before above After below',width=4500,height=1300);im.pixels.foreach_set(sheet.ravel());im.filepath_raw=str(out/'contact-sheet.png');im.file_format='PNG';im.save()
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(out/'level-optics-trial.glb'))
assert sum(o.type=='MESH' for o in bpy.data.objects)==len(original)
for r in records:
    o=bpy.data.objects[f"GEO-V12-FSIR02_{r['station']}_OPTIC"]
    assert min((o.matrix_world@v.co-Vector(r['tip'])).length for v in o.data.vertices)<1e-6
fresh=audit(bpy.data.objects);assert fresh['status']=='PASS'
(out/'review.json').write_text(json.dumps({'status':'PARTIAL_REPAIR_NOT_RELEASE_READY','records':records,'unchangedMeshes':len(original)-5,'floor':floor,'freshFloor':fresh,'freshMeshCount':len(original),'limitations':['Opaque original pipes are solid visual meshes; a tip inside their envelope is NOT proof of a fluid-connected lumen.','Seal, bore, installation dimensions and remaining unsupported sensors require further work.'],'evidence':'contact-sheet.png: before above, after below, L01 to L05'},ensure_ascii=False,indent=2),encoding='utf-8')
print('LEVEL_OPTIC_TRIAL_COMPLETE',flush=True)
