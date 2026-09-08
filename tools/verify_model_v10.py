"""Fresh GLB import, floor-regression fixtures and changed-neighbor review."""
import bpy
import hashlib
import json
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

root = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
sys.path.insert(0,str(root/'tools'))
from model_floor_audit import audit, bounds


def box(name, center, size):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    o=bpy.context.object
    o.name=name
    o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return o


def fixture_tests():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Four bars form a real hole, not a filled floor AABB.
    parts=[box('part',(x,y,.1),size) for x,y,size in
           [(0,-.8,(2,.4,.2)),(0,.8,(2,.4,.2)),(-.8,0,(.4,1.2,.2)),(.8,0,(.4,1.2,.2))]]
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:p.select_set(True)
    bpy.context.view_layer.objects.active=parts[0]
    bpy.ops.object.join()
    parts[0].name='MESH_RING_FLOOR'
    box('in-hole',(0,0,.1),(.2,.2,.1))
    box('seated',(0,-.8,.25),(.2,.2,.1))
    box('embedded',(0,.8,.15),(.2,.2,.1))
    box('fully-below',(.8,0,-.3),(.1,.1,.1))
    box('spanning-no-vertices-over-floor',(0,0,.1),(3,.05,.02))
    bpy.context.view_layer.update()
    names={r['name'] for r in audit(bpy.data.objects)['findings']}
    expected={'embedded','fully-below','spanning-no-vertices-over-floor'}
    assert names==expected,(names,expected)
    return {'status':'PASS','cases':5,'caught':sorted(expected),
            'accepted':['in-hole','seated']}


def mesh_snapshot():
    result={}
    for o in bpy.data.objects:
        if o.type!='MESH':continue
        vs=[o.matrix_world@v.co for v in o.data.vertices]
        result[o.name]={'bounds':bounds(o),
                        'bvh':BVHTree.FromPolygons(vs,[list(p.vertices) for p in o.data.polygons])}
    return result


def collisions(snapshot, changed):
    # Candidate surfaces only. Internal water connections and diagnostic
    # annotation geometry are excluded from *neighbor regression*, not floor.
    ignored=('LABEL','CALLOUT','ACRYLIC','ROOF','RENDER_GROUND')
    names=[n for n in snapshot if not any(x in n for x in ignored)
           and n not in {'MESH_RING_FLOOR','MESH_BASE_01'}]
    pairs=set()
    for i,a in enumerate(names):
        for b in names[i+1:]:
            if a not in changed and b not in changed:continue
            la,ha=snapshot[a]['bounds'];lb,hb=snapshot[b]['bounds']
            if any(min(ha[k],hb[k])-max(la[k],lb[k])<1e-5 for k in range(3)):continue
            if snapshot[a]['bvh'].overlap(snapshot[b]['bvh']):pairs.add(tuple(sorted((a,b))))
    return pairs


fixtures=fixture_tests()
out=root/'model'
report=json.loads((out/'v10-floor-audit.json').read_text(encoding='utf-8'))
changed={n for change in report['changes'] for n in change['nodes']}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root/'model/utility-tunnel-annular-v09-candidate.glb'))
old=mesh_snapshot()
old_pairs=collisions(old,changed)
bpy.ops.wm.read_factory_settings(use_empty=True)
candidate=out/'utility-tunnel-annular-v10-candidate.glb'
bpy.ops.import_scene.gltf(filepath=str(candidate))
fresh=audit(bpy.data.objects)
current=mesh_snapshot()
new_pairs=collisions(current,changed)-old_pairs
accepted_pairs={tuple(sorted(('GEO_MESH_SEEP_W01_LENS','MESH_SEEP_W01'))):
                'Indicator lens seated into its own sensor housing'}
unexpected=new_pairs-accepted_pairs.keys()
stable=[]
for name in old.keys()-changed:
    assert name in current,name
    error=max(abs(current[name]['bounds'][a][k]-old[name]['bounds'][a][k]) for a in (0,1) for k in range(3))
    assert error<2e-6,(name,error)
    stable.append(name)
assert not old.keys()-current.keys(),'Existing node lost'
assert fresh['status']=='PASS',fresh
# Direct duct/drain check, both of which moved and are intentionally outside
# the changed/unchanged-neighbor comparison above.
duct_clear=[]
for duct in ('MESH_CABLE_DUCT_01','GEO_CABLE_DUCT_COVER'):
    for drain in ('MESH_WATER_DRAIN_TUBE_01','MESH_WATER_DRAIN_VALVE_01','GEO_WATER_DRAIN_UNION_01'):
        assert not current[duct]['bvh'].overlap(current[drain]['bvh']),(duct,drain)
        duct_clear.append([duct,drain])
result={'status':'PASS' if not unexpected else 'NEEDS_REVIEW','sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'freshImportFloor':fresh,'floorRegressionFixtures':fixtures,
        'preservedOriginalNodes':len(old),'unchangedBoundsVerified':len(stable),
        'meshCount':len(current),'ductDrainSurfaceChecks':duct_clear,
        'newUnexpectedSurfacePairs':sorted(unexpected),
        'acceptedNewContacts':[{'pair':list(p),'reason':accepted_pairs[p]} for p in new_pairs & accepted_pairs.keys()],
        'neighborMethod':'BVH surface overlap regression, excludes annotations/enclosure; not an exhaustive solid-volume clearance certificate'}
(out/'v10-export-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
assert not unexpected,'New neighbor collisions: '+str(sorted(unexpected))
asset_map=json.loads((out/'asset-map-v10-candidate.json').read_text(encoding='utf-8'))
for asset in asset_map['assets']:
    for name in asset['meshNames']:assert name in current,name
asset_map['runtimeValidation']={'glbNodes':len(current),'status':'FRESH_IMPORT_AND_BINDINGS_PASS','productionRuntime':'V07 unchanged'}
(out/'asset-map-v10-candidate.json').write_text(json.dumps(asset_map,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(result,ensure_ascii=False),flush=True)
