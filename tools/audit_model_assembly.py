"""Read-only full-scene contact candidates; no claimed engineering clearance.

Run in isolated Blender: --python tools/audit_model_assembly.py -- input.glb output.json
Surface contact includes intentional joints; lack of it can include containment.
This report is a review queue, not a pass/fail collision certificate.
"""
import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args=sys.argv[sys.argv.index('--')+1:]
source,output=map(Path,args[:2])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
geometry={}
for obj in bpy.data.objects:
    if obj.type!='MESH':continue
    vertices=[obj.matrix_world@v.co for v in obj.data.vertices]
    geometry[obj.name]={
        'bounds':[[min(v[k] for v in vertices) for k in range(3)],
                  [max(v[k] for v in vertices) for k in range(3)]],
        'bvh':BVHTree.FromPolygons(vertices,[list(p.vertices) for p in obj.data.polygons]),
    }
names=sorted(geometry)
contacts={n:[] for n in names}
pairs=[]
for i,a in enumerate(names):
    amin,amax=geometry[a]['bounds']
    for b in names[i+1:]:
        bmin,bmax=geometry[b]['bounds']
        if any(min(amax[k],bmax[k])<max(amin[k],bmin[k])-1e-6 for k in range(3)):continue
        overlap=geometry[a]['bvh'].overlap(geometry[b]['bvh'])
        if overlap:
            contacts[a].append(b);contacts[b].append(a)
            pairs.append({'a':a,'b':b,'trianglePairs':len(overlap)})
annotations=('LABEL','CALLOUT','FLOW_INDICATOR','FLOW_ARROW')
result={
    'source':source.name,'status':'REVIEW_REQUIRED',
    'method':'world-space mesh BVH surface intersections; no solid containment or certified clearance',
    'meshCount':len(names),'surfaceContactPairs':pairs,
    'noSurfaceContacts':[{'name':n,'bounds':geometry[n]['bounds']} for n in names if not contacts[n]],
    'nonAnnotationPairs':[p for p in pairs if not any(s in p['a'] or s in p['b'] for s in annotations)],
    'limitations':['Contacts include intentional joints and decorative overlays.',
                   'No surface contact is not proof of floating: one part may be contained in another.',
                   'Hidden enclosure geometry is included; cutaway appearance alone does not prove missing mounts.'],
}
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('ASSEMBLY_REVIEW',len(pairs),'pairs;',len(result['noSurfaceContacts']),'objects without surface contacts',flush=True)
