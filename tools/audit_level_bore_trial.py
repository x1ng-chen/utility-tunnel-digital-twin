"""Whole-scene optical interference and welded topology review, read-only."""
import bpy,bmesh,json,sys
from pathlib import Path
from mathutils.bvhtree import BVHTree
root=Path(sys.argv[sys.argv.index('--')+1]);out=root/'_qa_iteration_20260909/level-bores'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(out/'level-bores-trial.glb'))
meshes={o.name:o for o in bpy.data.objects if o.type=='MESH'}
trees={n:BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons]) for n,o in meshes.items()}
report={'status':'REVIEW_REQUIRED','optics':[],'topology':[],'limits':['Surface intersections do not detect complete containment.','Welded manifoldness does not prove fluid connectivity or minimum wall thickness.']}
for i in range(1,6):
    name=f'GEO-V12-FSIR02_L{i:02}_OPTIC'
    contacts=[n for n in meshes if n!=name and trees[name].overlap(trees[n])]
    expected=f'MESH_V12-FSIR02_L{i:02}_PROBE'
    report['optics'].append({'station':f'L{i:02}','allContacts':contacts,'unexpectedNonAnnotation':[n for n in contacts if n!=expected and not any(k in n for k in ('LABEL','CALLOUT','HARNESS','WIRE'))]})
targets=json.loads((out/'review.json').read_text(encoding='utf-8'))['changedMeshes']
for name in targets:
    o=meshes[name];bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1e-7)
    report['topology'].append({'name':name,'vertices':len(bm.verts),'boundaryEdges':sum(e.is_boundary for e in bm.edges),'nonManifoldEdges':sum(not e.is_manifold for e in bm.edges),'zeroAreaFaces':sum(f.calc_area()<1e-12 for f in bm.faces)})
    bm.free()
(out/'whole-scene-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
