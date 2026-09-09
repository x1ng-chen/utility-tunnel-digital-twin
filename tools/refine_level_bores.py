"""Bored sensor interface trial. Inherited dimensions are NOT machining dimensions."""
import bpy,bmesh,json,sys,ast,math
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260909/level-bores';out.mkdir(exist_ok=True)
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import bounds,audit
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260909/level-optics/level-optics-trial.blend'))
original={o.name:bounds(o) for o in bpy.data.objects if o.type=='MESH'}
for o in bpy.data.objects:
    if o.type=='MESH':
        o.data=o.data.copy();o.data.transform(o.matrix_world);o.matrix_world=Matrix.Identity(4)
        if ('SERVICE-BOSS' in o.name or 'PIPE_CLAMP' in o.name and 'FSIR02' in o.name or o.name.startswith('GEO-V09-WATER-')):
            bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
bpy.context.view_layer.update()
def cutter(points,radius):
    c=bpy.data.curves.new('QA bore cutter','CURVE');c.dimensions='3D';c.bevel_depth=radius;c.bevel_resolution=5;c.use_fill_caps=True
    s=c.splines.new('POLY');s.points.add(len(points)-1)
    for p,v in zip(s.points,points):p.co=(*v,1)
    o=bpy.data.objects.new('QA bore cutter',c);bpy.context.collection.objects.link(o)
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.convert(target='MESH');return bpy.context.object
changes=[]
def subtract(name,tool):
    o=bpy.data.objects[name];bpy.context.view_layer.objects.active=o
    m=o.modifiers.new('Open fluid passage','BOOLEAN');m.operation='DIFFERENCE';m.solver='EXACT';m.object=tool
    bpy.ops.object.modifier_apply(modifier=m.name)
    assert len(o.data.polygons)>0,name
    changes.append(name)
# Read the authoritative V09 centerlines, without executing that build.
tree=ast.parse((root/'tools/build_model_v09.py').read_text(encoding='utf-8'))
routes=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='routes' for t in n.targets))
for name,points in routes.items():
    p=[Vector(v) for v in points];segments=48;verts=[];faces=[];old_tangent=None;normal=None
    for j,point in enumerate(p):
        incoming=(p[j]-p[j-1]).normalized() if j else (p[1]-p[0]).normalized()
        outgoing=(p[j+1]-p[j]).normalized() if j<len(p)-1 else incoming
        tangent=(incoming+outgoing).normalized()
        if normal is None:
            reference=Vector((0,0,1)) if abs(tangent.z)<.9 else Vector((0,1,0));normal=tangent.cross(reference).normalized()
        else:normal=old_tangent.rotation_difference(tangent)@normal
        binormal=tangent.cross(normal).normalized();old_tangent=tangent
        for radius in (.005,.0035):
            for k in range(segments):
                a=2*math.pi*k/segments;verts.append(tuple(point+radius*(math.cos(a)*normal+math.sin(a)*binormal)))
    for j in range(len(p)-1):
        a=j*segments*2;b=(j+1)*segments*2
        for k in range(segments):
            q=(k+1)%segments
            faces.append((a+k,a+q,b+q,b+k));faces.append((a+segments+q,a+segments+k,b+segments+k,b+segments+q))
    for j in (0,len(p)-1):
        a=j*segments*2
        for k in range(segments):
            q=(k+1)%segments;faces.append((a+k,a+segments+k,a+segments+q,a+q))
    o=bpy.data.objects[name];mesh=bpy.data.meshes.new(name+' explicit hollow wall');mesh.from_pydata(verts,[],faces);mesh.update()
    for m in o.data.materials:mesh.materials.append(m)
    o.data=mesh
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free()
    for poly in mesh.polygons:poly.use_smooth=True
    changes.append(name)
records=[]
for i in range(1,6):
    n=f'MESH_V12-FSIR02_L{i:02}_PROBE';lo,hi=original[n];center=(Vector(lo)+Vector(hi))/2;axis=center+Vector((0,.011,0))
    optic=bpy.data.objects[f'GEO-V12-FSIR02_L{i:02}_OPTIC']
    bm=bmesh.new();bm.from_mesh(optic.data)
    caps=[f for f in bm.faces if len(f.verts)>3]
    assert len(caps)==1
    result=bmesh.ops.extrude_face_region(bm,geom=caps)
    extruded=[v for v in result['geom'] if isinstance(v,bmesh.types.BMVert)]
    for v in extruded:v.co.y=center.y+.003
    bmesh.ops.delete(bm,geom=caps,context='FACES_ONLY')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(optic.data);bm.free()
    # A real through-bore in the sleeve and clamp, from housing to wet-side cavity.
    tool=cutter([center-Vector((0,.001,0)),axis+Vector((0,.005,0))],.003)
    for name in [f'GEO-V09-L{i:02}-SERVICE-BOSS',f'GEO-V14-FSIR02_L{i:02}_PIPE_CLAMP']:
        subtract(name,tool)
    if i>1:subtract('GEO-V09-WATER-SUCTION' if i<4 else 'GEO-V09-WATER-RETURN',tool)
    bpy.data.objects.remove(tool,do_unlink=True)
    records.append({'station':f'L{i:02}','axis':list(axis),'probeCenter':list(center),'drainValveLumen':'UNVERIFIED' if i==1 else 'not applicable'})
for name in sorted(set(changes)):
    o=bpy.data.objects[name];bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
    bmesh.ops.dissolve_degenerate(bm,dist=1e-7,edges=list(bm.edges))
    bmesh.ops.triangulate(bm,faces=list(bm.faces),quad_method='BEAUTY',ngon_method='BEAUTY')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(o.data);bm.free()
floor=audit(bpy.data.objects);assert floor['status']=='PASS'
# Before accepting, ensure the exposed cone does not intersect its sleeve or pipe wall.
def tree_for(n):
    o=bpy.data.objects[n];return BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons])
for r in records:
    tag=r['station'];opt=tree_for(f'GEO-V12-FSIR02_{tag}_OPTIC')
    test=[f'GEO-V09-{tag}-SERVICE-BOSS',f'GEO-V14-FSIR02_{tag}_PIPE_CLAMP']
    if tag!='L01':test+=['GEO-V09-WATER-SUCTION' if tag in ('L02','L03') else 'GEO-V09-WATER-RETURN']
    r['opticWallIntersections']=[n for n in test if opt.overlap(tree_for(n))]
    r['opticConnectedToHousing']=bool(opt.overlap(tree_for(f'MESH_V12-FSIR02_{tag}_PROBE')))
for o in bpy.data.objects:
    if o.type=='MESH':o.hide_render=any(s in o.name for s in ('ACRYLIC','ROOF-FULL'));o.hide_set(False)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
    if o.type=='MESH':o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(out/'level-bores-trial.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'level-bores-trial.blend'),compress=True)
scene=bpy.context.scene;camera=scene.camera;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=1000;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
for r in records:
    tag=r['station'];focus=Vector(r['axis']);visible={f'MESH_V12-FSIR02_{tag}_PROBE',f'GEO-V12-FSIR02_{tag}_OPTIC',f'GEO-V09-{tag}-SERVICE-BOSS',f'GEO-V14-FSIR02_{tag}_PIPE_CLAMP'}
    visible.add('MESH_WATER_DRAIN_VALVE_01' if tag=='L01' else 'GEO-V09-WATER-SUCTION' if tag in ('L02','L03') else 'GEO-V09-WATER-RETURN')
    restore={}
    for o in bpy.data.objects:
        if o.type!='MESH':continue
        o.hide_render=o.name not in visible
        if o.name in visible and not o.name.endswith('_OPTIC'):
            restore[o.name]=o.data;o.data=o.data.copy();bm=bmesh.new();bm.from_mesh(o.data)
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-7,plane_co=focus,plane_no=Vector((0,0,1)),clear_outer=True,clear_inner=False)
            bm.to_mesh(o.data);bm.free()
    camera.data.type='ORTHO';camera.data.ortho_scale=.046;camera.location=focus+Vector((0,0,1));camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(out/f'{tag}-section.png');bpy.ops.render.render(write_still=True)
    for n,mesh in restore.items():bpy.data.objects[n].data=mesh
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(out/'level-bores-trial.glb'))
fresh=audit(bpy.data.objects);assert fresh['status']=='PASS'
for r in records:
    tag=r['station'];opt=tree_for(f'GEO-V12-FSIR02_{tag}_OPTIC')
    r['freshOpticConnectedToHousing']=bool(opt.overlap(tree_for(f'MESH_V12-FSIR02_{tag}_PROBE')))
    assert r['freshOpticConnectedToHousing']
(out/'review.json').write_text(json.dumps({'status':'AWAITING_SECTION_REVIEW','changedMeshes':sorted(set(changes)),'stations':records,'floor':floor,'freshFloor':fresh,'limitations':['L01 valve lumen unresolved','Watertightness and bore continuity need checking; Boolean completion alone is not proof','All dimensions inherited and not approved for fabrication']},ensure_ascii=False,indent=2),encoding='utf-8')
print('BORE_TRIAL_COMPLETE',records,flush=True)
