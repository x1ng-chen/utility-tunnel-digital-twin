"""Restore fan geometry around surviving top rails; collisions remain explicit gates."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260910/fan-clearance';out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds,audit
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260909/manifold-mount/manifold-mount-trial.blend'))
added=[];groups={}
def cube(n,p,s,mat):
    bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=bpy.context.object;o.name=n;o.dimensions=s;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
    m=o.modifiers.new('edge','BEVEL');m.width=.001;m.segments=3;bpy.ops.object.modifier_apply(modifier=m.name);added.append(n);return o
for key in ['FAN-01','FAN-02']:
    if key=='FAN-02':
        o=bpy.data.objects[key]
        roof_bottom=bounds(bpy.data.objects['MESH_RING_ACRYLIC_ROOF'])[0][2]
        o.location.z+=roof_bottom-.01-bounds(o)[1][2]
        bpy.context.view_layer.update()
    start=len(added);anchor=bpy.data.objects[key];lo,hi=bounds(anchor);x=(lo[0]+hi[0])/2;y=(lo[1]+hi[1])/2;top=(lo[2]+hi[2])/2;z=top-.0729;mat=anchor.data.materials[0]
    cube(key+'_左边框',(x-.0729,y,z),(.0162,.0243,.1458),mat)
    cube(key+'_右边框',(x+.0729,y,z),(.0162,.0243,.1458),mat)
    cube(key+'_下边框',(x,y,z-.0729),(.162,.0243,.0162),mat)
    bpy.ops.mesh.primitive_torus_add(major_segments=64,minor_segments=12,location=(x,y,z),rotation=(math.pi/2,0,0),major_radius=.063,minor_radius=.006)
    o=bpy.context.object;o.name=key+'_风圈';o.data.materials.append(mat);added.append(o.name)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=.014,depth=.018,location=(x,y,z),rotation=(math.pi/2,0,0))
    o=bpy.context.object;o.name=key+'_轮毂';o.data.materials.append(mat);added.append(o.name)
    for i in range(5):
        a=2*math.pi*i/5
        o=cube(key+f'_叶片{i+1}',(x+math.sin(a)*.031,y,z+math.cos(a)*.031),(.021,.009,.043),mat);o.rotation_euler.y=a
    cube(key+'_后侧横支撑',(x,y+.007,z),(.134,.003,.005),mat)
    cube(key+'_后侧竖支撑',(x,y+.007,z),(.005,.003,.134),mat)
    groups[key]={'names':[key]+added[start:],'center':(x,y,z)}
    if key=='FAN-01':
        floor_top=.19589924812316895
        low=floor_top+.003;high=z-.0729
        for side,xx in [('左',x-.0729),('右',x+.0729)]:
            for n,p,s in [(key+'_'+side+'底脚',(xx,y,floor_top+.0024995),(.028,.033,.005)),(key+'_'+side+'立脚',(xx,y,(low+high)/2),(.010,.016,high-low))]:
                o=cube(n,p,s,mat);groups[key]['names'].append(o.name)
    if key=='FAN-02':
        roof=bpy.data.objects['MESH_RING_ACRYLIC_ROOF']
        roof_tree=BVHTree.FromPolygons([roof.matrix_world@v.co for v in roof.data.vertices],[list(p.vertices) for p in roof.data.polygons])
        for side,xx in [('左',x-.065),('右',x+.065)]:
            hit=roof_tree.ray_cast(Vector((xx,y,top+.009)),Vector((0,0,1)))
            assert hit[0] is not None,'Roof anchorage ray missed'
            low=top+.006;high=hit[0].z+.001
            o=cube(key+'_'+side+'顶盖连接柱',(xx,y,(low+high)/2),(.008,.012,high-low),mat)
            groups[key]['names'].append(o.name)
bpy.context.view_layer.update()
trees={o.name:BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons]) for o in bpy.data.objects if o.type=='MESH'}
collisions={}
for key,g in groups.items():
    collisions[key]={n:[m for m in trees if m not in g['names'] and not any(t in m for t in ('LABEL','CALLOUT')) and trees[n].overlap(trees[m])] for n in g['names']}
scene=bpy.context.scene;camera=scene.camera;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True;scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
for key,g in groups.items():
    for o in bpy.data.objects:
        if o.type=='MESH':o.hide_render=o.name not in g['names']
    for tag,d in [('front',(0,-1,0)),('back',(0,1,0)),('left',(-1,0,0)),('right',(1,0,0)),('top',(0,0,1)),('hero',(1,-2,1))]:
        focus=Vector(g['center'])+Vector((0,0,-.04 if key=='FAN-01' else 0));camera.data.type='ORTHO';camera.data.ortho_scale=.40 if key=='FAN-01' else .28;camera.location=focus+Vector(d);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(out/f'{key}-{tag}.png');bpy.ops.render.render(write_still=True)
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_render=any(k in o.name for k in ['ACRYLIC','ROOF-FULL']);o.hide_set(False)
camera.location=(1.5,-2.8,2.2);camera.rotation_euler=(Vector((0,0,.30))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=2.1;scene.render.filepath=str(out/'context-cutaway.png');bpy.ops.render.render(write_still=True)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'fan-restoration-trial.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'fan-restoration-trial.blend'),compress=True)
floor=audit(bpy.data.objects)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(out/'fan-restoration-trial.glb'))
assert all(n in bpy.data.objects for n in added)
fresh_trees={o.name:BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons]) for o in bpy.data.objects if o.type=='MESH'}
fresh_collisions={key:{n:[m for m in fresh_trees if m not in g['names'] and not any(t in m for t in ('LABEL','CALLOUT')) and fresh_trees[n].overlap(fresh_trees[m])] for n in g['names']} for key,g in groups.items()}
assert fresh_collisions==collisions
connections={}
for key in groups:
    for part in ['后侧横支撑','后侧竖支撑']:
        n=key+'_'+part;connections[n]={end:bool(fresh_trees[n].overlap(fresh_trees[key+'_'+end])) for end in ['轮毂','风圈']}
for side in ['左','右']:
    n='FAN-02_'+side+'顶盖连接柱';connections[n]={end:bool(fresh_trees[n].overlap(fresh_trees[end])) for end in ['FAN-02','MESH_RING_ACRYLIC_ROOF']}
    n='FAN-01_'+side+'底脚';connections[n]={end:bool(fresh_trees[n].overlap(fresh_trees[end])) for end in ['MESH_RING_FLOOR','FAN-01_'+side+'立脚']}
    n='FAN-01_'+side+'立脚';connections[n]={'frame':bool(fresh_trees[n].overlap(fresh_trees['FAN-01_下边框']))}
(out/'review.json').write_text(json.dumps({'status':'CLEARANCE_AND_SUPPORT_REVIEW_REQUIRED','added':added,'collisions':collisions,'freshCollisionMatch':True,'connections':connections,'floor':floor,'freshFloor':audit(bpy.data.objects),'limitations':['FAN02 ceiling connectors are layout concepts; fasteners and roof load capacity unverified','FAN01 frame mounting, guards and clear airflow path require completion','Original FAN nodes were top rails only; name-only inventory was inadequate']},ensure_ascii=False,indent=2),encoding='utf-8')
print('FAN_RESTORATION_DONE',flush=True)
