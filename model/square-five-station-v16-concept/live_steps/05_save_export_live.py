import bpy,json,csv,struct,hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v16-concept')
REV='square-five-station-v16-concept'
scene=bpy.context.scene
graph=bpy.context.evaluated_depsgraph_get()
checks={}
for name,origin,direction,expect in [
    ('lid_mic_clear',(.565,.390,.5),(0,0,-1),False),
    ('lid_speaker_clear',(.635,.350,.5),(0,0,-1),False),
    ('lid_solid_elsewhere',(.350,.350,.5),(0,0,-1),True),
    ('wall_button_clear',(1,.305,.160),(-1,0,0),False),
    ('wall_solid_elsewhere',(1,.330,.160),(-1,0,0),True)]:
    obj=bpy.data.objects['REMOVABLE_TRANSPARENT_LID' if name.startswith('lid_') else 'CLEAR_WALL_RIGHT'].evaluated_get(graph)
    inverse=obj.matrix_world.inverted()
    hit,*_=obj.ray_cast(inverse@Vector(origin),inverse.to_3x3()@Vector(direction))
    assert hit==expect,(name,hit,expect)
    checks[name]='PASS'
(ROOT/'voice-opening-check.json').write_text(json.dumps({'method':'Evaluated Blender mesh ray tests on lid/wall, grille and button separate','checks':checks,'acousticPerformance':'NOT_TESTED'},indent=2)+'\n',encoding='utf-8')
scene.camera=bpy.data.objects['VIEW_OVERALL']
scene['modelEditRoute']='LIVE_MCP_execute_blender_code'
scene['physicalEnvelope_mm']='700x700x300'
scene['platformAlarmIntegration']='NOT_EXECUTED'
for a in bpy.context.screen.areas:
    if a.type=='VIEW_3D':
        a.spaces.active.region_3d.view_perspective='CAMERA'
        a.spaces.active.shading.type='MATERIAL'
        a.spaces.active.overlay.show_overlays=False
bpy.context.preferences.filepaths.save_version=0
bpy.data.objects['REMOVABLE_TRANSPARENT_LID'].hide_render=False
bpy.data.objects['CLEAR_WALL_BOTTOM'].hide_render=False
inventory=json.loads((ROOT/'asset-map.json').read_text(encoding='utf-8'))
with (ROOT/'asset-map.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for a in inventory['assets'] for k in a))
    w=csv.DictWriter(f,fields); w.writeheader()
    for a in inventory['assets']: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in a.items()})
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/(REV+'.blend')),compress=True)
bpy.ops.object.select_all(action='DESELECT')
export=[]
for obj in scene.objects:
    if obj.type in {'MESH','CURVE','FONT','EMPTY'} and not any(c.name=='99_STUDIO' for c in obj.users_collection):
        obj.select_set(True); export.append(obj)
bpy.ops.export_scene.gltf(filepath=str(ROOT/(REV+'.glb')),export_format='GLB',use_selection=True,
    export_extras=True,export_apply=True,export_cameras=False,export_lights=False,export_yup=True)
raw=(ROOT/(REV+'.glb')).read_bytes()
data=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
names=[n.get('name') for n in data['nodes']]
assert len(names)==len(set(names))
assert all(n in names for a in inventory['assets'] for n in a['meshNames'])
report={'revision':REV,'blender':bpy.app.version_string,'glb_bytes':len(raw),'glb_nodes':len(names),
    'sha256':hashlib.sha256(raw).hexdigest(),'assets':len(inventory['assets']),'sensors':31,'stations':5,
    'modelEditRoute':'LIVE_MCP_execute_blender_code','baselineCommit':'12c1feebe811329c6370f8927dcb14bc733b40f7',
    'liveFrontendIntegration':'NOT_EXECUTED','voiceOpeningsRayCheck':'PASS'}
(ROOT/'export-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
