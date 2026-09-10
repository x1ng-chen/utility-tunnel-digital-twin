import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
R=Path(sys.argv[sys.argv.index('--')+1]);O=R/'_qa_rebuild_20260910/distributed'
inv=json.loads((O/'inventory.json').read_text(encoding='utf-8'))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(O/'planned-rebuild.glb'))
def bounds(o):
 v=[o.matrix_world@v.co for v in o.data.vertices];return [[min(p[i] for p in v) for i in range(3)],[max(p[i] for p in v) for i in range(3)]]
def bvh(o):return BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices) for p in o.data.polygons],all_triangles=False)
def overlap(a,b):return all(min(a[1][i],b[1][i])-max(a[0][i],b[0][i])>1e-6 for i in range(3))
meshes=[o for o in bpy.data.objects if o.type=='MESH'];bs={o.name:bounds(o) for o in meshes};tree={}
cores=[bpy.data.objects[a['object']] for a in inv['assets']]
collisions=[]
for i,a in enumerate(cores):
 for b in cores[i+1:]:
  if overlap(bs[a.name],bs[b.name]):
   for o in [a,b]:
    if o.name not in tree:tree[o.name]=bvh(o)
   if tree[a.name].overlap(tree[b.name]):collisions.append([a.name,b.name])
env=[a for a in inv['assets'] if a['kind'] in ['MQ4','MQ7','ME2O2','MQ2','FLAME','SHT30']]
positions=[bpy.data.objects[a['object']].matrix_world.translation for a in env]
separation=min((a-b).length for i,a in enumerate(positions) for b in positions[i+1:])
finite=all(math.isfinite(c) for o in meshes for v in o.data.vertices for c in o.matrix_world@v.co)
degenerate=sum(p.area<1e-14 for o in meshes for p in o.data.polygons)
triangles=sum(len(p.vertices)-2 for o in meshes for p in o.data.polygons)
below=[n for n,b in bs.items() if b[0][2]<-1e-5]
result={'freshGLBImport':True,'registeredAssets':len(cores),'meshCount':len(meshes),'triangles':triangles,'nonFiniteVertices':not finite,'zeroAreaLocalFaces':degenerate,'belowGround':below,'distinctHardwareSurfaceCollisions':collisions,'environmentalSensorCount':len(env),'environmentalSensorMinCenterDistance':separation,'scope':'Core-to-core surface intersection and Z checks only; containment, all supports, wiring topology and fabrication clearances require further review','status':'CANDIDATE_REVIEW_NOT_MANUFACTURING_PASS'}
(O/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
S=bpy.context.scene;S.world=bpy.data.worlds.new('检验环境');S.world.color=(.82,.82,.82);S.render.engine='BLENDER_WORKBENCH';S.display.shading.color_type='MATERIAL';S.display.shading.show_cavity=True;S.display.shading.cavity_type='BOTH';S.view_settings.view_transform='Standard';S.render.resolution_x=1600;S.render.resolution_y=1100;S.render.resolution_percentage=100
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';S.camera=cam
for tag in ['hero','top','water']:
 p,target,scale=inv['views'][tag];cam.location=p;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;S.render.filepath=str(O/f'fresh-{tag}.png');bpy.ops.render.render(write_still=True)
print(json.dumps(result,ensure_ascii=False),flush=True)
