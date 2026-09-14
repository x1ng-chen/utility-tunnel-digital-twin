import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
args=sys.argv[sys.argv.index('--')+1:];R=Path(args[0]);O=R/(args[1] if len(args)>1 else '_qa_rebuild_20260910/distributed')
inv=json.loads((O/'inventory.json').read_text(encoding='utf-8'))
def authored_bounds(o):
    v=[o.matrix_world@v.co for v in o.data.vertices];return [[min(p[i] for p in v) for i in range(3)],[max(p[i] for p in v) for i in range(3)]]
bpy.ops.wm.open_mainfile(filepath=str(O/'planned-rebuild.blend'))
authored={o.name:authored_bounds(o) for o in bpy.data.objects if o.type=='MESH'}
authored_triangles=sum(len(p.vertices)-2 for o in bpy.data.objects if o.type=='MESH' for p in o.data.polygons)
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
result['authoredImportedNamesMatch']=set(authored)==set(bs)
result['authoredMeshCount']=len(authored)
result['authoredTriangleCount']=authored_triangles
result['maximumBoundsDelta']=max(abs(a-b) for n in authored if n in bs for aa,bb in zip(authored[n],bs[n]) for a,b in zip(aa,bb))
pumpNames=[n for n in bs if n=='PUMP24' or n.startswith('PUMP24-') and '断电线' not in n]
result['waterPumpEnvelope']=[max(bs[n][1][i] for n in pumpNames)-min(bs[n][0][i] for n in pumpNames) for i in range(3)]
result['pumpThreadMajorDiameter']={axis:max(bs[n][1][dim]-bs[n][0][dim] for n in bs if n.startswith(prefix)) for axis,prefix,dim in [('horizontal','PUMP24-水平螺纹',1),('vertical','PUMP24-竖直螺纹',0)]}
result['levelProbeCenters']={n:[(bs[n][0][i]+bs[n][1][i])/2 for i in range(3)] for n in bs if n.startswith('LEVEL-L') and n.endswith('-光学端')}
route=bpy.data.objects.get('WATER-连续泵出口')
if route:
 import bmesh
 bm=bmesh.new();bm.from_mesh(route.data);result['outletBoundaryEdges']=sum(e.is_boundary for e in bm.edges);result['outletNonmanifoldEdges']=sum(not e.is_manifold for e in bm.edges);bm.free()
offsets=[]
for n in bs:
 if n.endswith('-中文'):
  pn=n[:-3]+'-铭牌'
  if pn in bs:
   a=(Vector(bs[n][0])+Vector(bs[n][1]))/2;b=(Vector(bs[pn][0])+Vector(bs[pn][1]))/2
   if (a-b).length>.006:offsets.append({'label':n,'centerOffset':(a-b).length})
result['labelCenterOffsetsOver6mm']=offsets
result['degenerateFacesByObject']={o.name:sum(p.area<1e-14 for p in o.data.polygons) for o in meshes if any(p.area<1e-14 for p in o.data.polygons)}
shell=[o for o in meshes if o.name.startswith('围护-')]
shell_hits=[];saddle_hits=[]
for a in shell+[o for o in meshes if o.name.startswith('管托')]:
 for b in meshes:
  if a==b or b.name.startswith('围护-') or b.name.startswith('门框') or b.name in ['环形承重底座','内沿护边','门脚','门铰','检修门','门磁','门磁对磁']:continue
  if a.name.startswith('管托') and not b.name.startswith('WATER-'):continue
  if overlap(bs[a.name],bs[b.name]):
   for o in [a,b]:
    if o.name not in tree:tree[o.name]=bvh(o)
   if tree[a.name].overlap(tree[b.name]):
    (shell_hits if a in shell else saddle_hits).append([a.name,b.name])
result['enclosureMeshCount']=len(shell)
result['enclosureHardwareSurfaceCandidates']=shell_hits
result['saddlePipeSurfaceCandidates']=saddle_hits
accessory_hits=[]
targets=[o for o in meshes if o.name.startswith(('PIPE-G01','WATER-','气泵管路-','气管取样支路-','接口占位-','卡箍-','GAS-主供气支路','GAS-泵','GAS-泄漏支管','GAS-泄漏排气口'))]
for a in targets:
 for b in meshes:
  if a==b or b in shell or b.name.startswith(('WATER-','气泵管路-','气管取样支路-','接口占位-','卡箍-')):continue
  if overlap(bs[a.name],bs[b.name]):
   for o in [a,b]:
    if o.name not in tree:tree[o.name]=bvh(o)
   if tree[a.name].overlap(tree[b.name]):accessory_hits.append([a.name,b.name])
result['pipeAccessorySurfaceCandidates']=accessory_hits
result['scope']='Core pairs, enclosure versus hardware, pipe versus support/accessories; excludes enclosure/frame seating and does not certify containment or manufacturing clearance'
result['fullSystemFunctionalConnectivity']='NOT_VERIFIED: pump internal paths, gas circuit and seals not certified'
result['inspectionHiddenShell']='Roof, inner wall and front outer wall are hidden only in cutaway evidence'
if (O/'demo-topology.json').exists():
 demo=json.loads((O/'demo-topology.json').read_text(encoding='utf-8'))
 probe_checks=[]
 for p in [p for p in demo['points'] if p['kind']=='FSIR02']:
  name=p['id']+'-光学端';bb=bs[name];x=(bb[0][0]+bb[1][0])/2;z=(bb[0][2]+bb[1][2])/2
  center_z=.185+.075*(x+.4);distal_y=bb[1][1]
  probe_checks.append({'id':p['id'],'distalFaceInsidePipe':math.hypot(distal_y+.395,z-center_z)+.004<.017,
                       'heightDeltaFromPlan_m':abs(z-p['z_m'])})
 result['demoProbeChecks']=probe_checks
 result['demoNormalGasExitOpen']='气管封帽0' not in bs
 result['obsoleteGasRecirculationBranchRemoved']='气管取样支路-进气过滤' not in bs
 feed=bpy.data.objects['WATER-连续泵出口']
 distal=[feed.matrix_world@v.co for v in feed.data.vertices if (feed.matrix_world@v.co).x>.445]
 rim=max(bb[1][2] for name,bb in bs.items() if name.startswith('敞口供水盒-'))
 result['demoFeedAirGap_m']=min(v.z for v in distal)-rim
 support_hits=[]
 demo_supports=[o for o in meshes if o.name.startswith(('管托-重力','供水管支柱','供水管悬臂','供水盒支脚'))]
 hardware_parts=[o for o in meshes if o.name.startswith(('PUMP24','AIR-PUMP','LEVEL-L','FAN-','CTRL-'))]
 for a in demo_supports:
  for b in hardware_parts:
   if overlap(bs[a.name],bs[b.name]):
    for obj in [a,b]:
     if obj.name not in tree:tree[obj.name]=bvh(obj)
    if tree[a.name].overlap(tree[b.name]):support_hits.append([a.name,b.name])
 result['demoSupportHardwareSurfaceCandidates']=support_hits
 result['demoStatus']='GEOMETRY_AND_DESIGN_ONLY_NOT_COMMISSIONED'
(O/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
S=bpy.context.scene;S.world=bpy.data.worlds.new('检验环境');S.world.color=(.82,.82,.82);S.render.engine='BLENDER_WORKBENCH';S.display.shading.color_type='MATERIAL';S.display.shading.show_cavity=True;S.display.shading.cavity_type='BOTH';S.view_settings.view_transform='Standard';S.render.resolution_x=1600;S.render.resolution_y=1100;S.render.resolution_percentage=100
bpy.ops.object.camera_add();cam=bpy.context.object;cam.data.type='ORTHO';S.camera=cam
sys.path.insert(0,str(R/'tools'))
from enclosure_geometry import set_inspection_view
set_inspection_view(True)
for tag in ['hero','top','water']+([k for k in ['water-pump','air-pump'] if k in inv['views']]):
 p,target,scale=inv['views'][tag];cam.location=p;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;S.render.filepath=str(O/f'fresh-{tag}.png');bpy.ops.render.render(write_still=True)
if shell:
 set_inspection_view(False)
 p,target,scale=inv['views']['hero'];cam.location=p;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;S.render.filepath=str(O/'fresh-enclosure-full.png');bpy.ops.render.render(write_still=True)
print(json.dumps(result,ensure_ascii=False),flush=True)
