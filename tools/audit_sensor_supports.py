"""Read-only sensor mounting evidence; no engineering certification."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260909/sensors';out.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root/'_qa_iteration_20260909/air-pump-trial.blend'))
meshes={o.name:o for o in bpy.data.objects if o.type=='MESH'}
verts={n:[o.matrix_world@v.co for v in o.data.vertices] for n,o in meshes.items()}
trees={n:BVHTree.FromPolygons(verts[n],[list(p.vertices) for p in o.data.polygons]) for n,o in meshes.items()}
annotations=('LABEL','CALLOUT','HARNESS','ARROW','OPTIC','LENS','STATUS','WIRE','CABLE')
targets=[n for n in meshes if any(k in n for k in ('FSIR02','MESH_GAS_','SENSOR_STAND','MESH_MOUNT_','MESH_SHT','MESH_SMOKE','MESH_TEMP_')) and not any(k in n for k in annotations)]
records=[]
for n in targets:
    contacts=[];near=[]
    for m in meshes:
        if m==n or any(k in m for k in annotations):continue
        if trees[n].overlap(trees[m]):contacts.append(m)
        else:
            distance=min(trees[m].find_nearest(v)[3] for v in verts[n])
            near.append((distance,m))
    records.append({'name':n,'surfaceContacts':contacts,'nearestNonContact':sorted(near)[:4]})
(out/'support-audit.json').write_text(json.dumps({'status':'REVIEW_REQUIRED','records':records,'limitations':'Surface contacts include unintended pipe penetration; vertex-to-surface distances are candidates, not certified clearances.'},ensure_ascii=False,indent=2),encoding='utf-8')
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=900;scene.render.resolution_y=700;scene.render.resolution_percentage=100
scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_cavity=True
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
camera=scene.camera;camera.data.type='ORTHO'
views=[]
for i in range(1,6):
    token=f'FSIR02_L0{i}';objects=[o for n,o in meshes.items() if token in n]
    vs=[v for o in objects for v in verts[o.name]];focus=sum(vs,Vector())/len(vs)
    views.append((f'L0{i}',focus,.14,token))
views.extend([('gas',Vector((.48,.15,.38)),.95,'GAS'),('environment',Vector((-.44,.10,.33)),.18,'ENV')])
for label,focus,scale,token in views:
    for n,o in meshes.items():
        o.hide_render=any(k in n for k in ('LABEL','CALLOUT','ACRYLIC','ROOF','RENDER_GROUND'))
        if token.startswith('FSIR'):
            o.hide_render=o.hide_render or (token not in n and any(f'FSIR02_L0{j}' in n for j in range(1,6)))
    for view,direction in [('front',(0,-1,0)),('top',(0,0,1)),('hero',(1,-2,1.2))]:
        camera.location=focus+Vector(direction);camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=scale
        scene.render.filepath=str(out/f'{label}-{view}.png');bpy.ops.render.render(write_still=True)
print('SENSOR_SUPPORT_AUDIT_COMPLETE',len(records),flush=True)
