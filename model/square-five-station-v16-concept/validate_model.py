"""Fresh .blend and GLB checks. No frontend, registry, firmware or live alarm claims."""
import bpy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parent
REV='square-five-station-v16-concept'
inventory=json.loads((ROOT/'asset-map.json').read_text(encoding='utf-8'))
bindings=json.loads((ROOT/'sensor-bindings.json').read_text(encoding='utf-8'))['bindings']
stations=json.loads((ROOT/'station-focus.json').read_text(encoding='utf-8'))['stations']
fixtures=json.loads((ROOT/'alarm-location-fixtures.json').read_text(encoding='utf-8'))['fixtures']
baseline=json.loads((ROOT/'identity-baseline-v15.json').read_text(encoding='utf-8'))
old={a['physicalTag']:a for a in baseline['assets'] if a['category']=='external_sensor'}
assert len(bindings)==31 and len({b['assetCode'] for b in bindings})==31
assert len({b['targetNode'] for b in bindings})==31 and len(stations)==5
report={}
def bounds(o):
    points=[o.matrix_world @ Vector(v) for v in o.bound_box]
    return [[min(p[j] for p in points)*1000 for j in range(3)],[max(p[j] for p in points)*1000 for j in range(3)]]
def ancestors(o):
    result=[]
    while o.parent:
        o=o.parent; result.append(o.name)
    return result
def distance_xy(p,a,b):
    ab=Vector((b[0]-a[0],b[1]-a[1])); ap=Vector((p[0]-a[0],p[1]-a[1]))
    t=max(0,min(1,ap.dot(ab)/ab.length_squared))
    return (ap-ab*t).length
for form in ['blend','glb']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if form=='blend': bpy.ops.wm.open_mainfile(filepath=str(ROOT/(REV+'.blend')))
    else: bpy.ops.import_scene.gltf(filepath=str(ROOT/(REV+'.glb')))
    bpy.context.view_layer.update()
    objects=list(bpy.context.scene.objects)
    assert not any(o.name.startswith('DEMO_ONLY_') for o in objects)
    assert not any(m and m.name.startswith('DEMO_ONLY_') for o in objects if o.type=='MESH' for m in o.data.materials)
    roots=[o for o in objects if o.get('category')]
    sensors=[o for o in roots if o['category']=='external_sensor']
    assert len(sensors)==31
    families=Counter(o['family'] for o in sensors)
    assert families=={'MQ2':5,'MQ4':5,'CO':5,'FLAME':5,'SHT':4,'LEVEL':4,'O2':3}
    ownership=Counter(o['controllerId'] for o in sensors)
    assert [ownership[f'CTRL-{n:02}'] for n in range(1,5)]==[7,6,11,7]
    categories=Counter(o['category'] for o in roots)
    assert categories==inventory['category_counts']
    assert categories['controller']==4 and categories['rs485_module']==5
    assert categories['gateway']==categories['voice_controller']==1
    assert categories['business_display']==2 and categories['voice_display']==1
    assert categories['fan']==categories['relay']==categories['power_monitor']==2
    assert categories['wet_tray']==4 and categories['utility_pipe']==2
    assert len({o['assetCode'] for o in roots})==len(roots)
    for a in inventory['assets']:
        for name in a['meshNames']: assert name in bpy.data.objects,name
        o=bpy.data.objects[a['meshNames'][0]]
        assert o['assetCode']==a['assetCode']
        assert max(abs(o.matrix_world.translation[j]*1000-a['position_mm'][j]) for j in range(3))<.025,(o.name,tuple(o.matrix_world.translation),a['position_mm'])
    for n,(x,y) in {1:(110,590),2:(590,590),3:(110,110),4:(590,110)}.items():
        p=bpy.data.objects[f'CTRL-{n:02}'].matrix_world.translation*1000
        assert abs(p.x-x)<.025 and abs(p.y-y)<.025
    for s in stations:
        p=int(s['stationId'][1:])
        owner='CTRL-'+('03' if p in [3,5] else f'{p:02}')
        assert s['controllerId']==owner
        members=[o for o in sensors if o.get('physicalMember') and o.get('stationId')==s['stationId']]
        assert len(members)==4 and {o['family'] for o in members}=={'MQ2','MQ4','CO','FLAME'}
        assert {o['physicalTag'] for o in members}=={f'{f}-{p:02}' for f in ['MQ2','MQ4','CO','FLAME']}
        assert all(o['controllerId']==owner and s['groupNode'] in ancestors(o) for o in members)
        assert set(s['memberAssetCodes'])=={o['assetCode'] for o in members}
    fixture_results=[]
    for b in bindings:
        o=bpy.data.objects[b['targetNode']]
        assert o['physicalTag']==b['physicalTag'] and o['assetCode']==b['assetCode']
        assert b['assetCode']==old[b['physicalTag']]['assetCode']
        assert b['targetNode']==old[b['physicalTag']]['meshNames'][0]
        assert b['identityStatus']
        p=o.matrix_world.translation
        assert max(abs(p[j]-b['positionBlender_m'][j]) for j in range(3))<.000025
        assert max(abs([p.x,p.z,-p.y][j]-b['positionGltf_m'][j]) for j in range(3))<.000025
        assert b['stationGroupNode'] in bpy.data.objects
        # Exact target-subtree highlighting must never contain a second sensor.
        descendant_sensor_ids={c['assetCode'] for c in o.children_recursive if c.get('category')=='external_sensor'}
        assert not descendant_sensor_ids
    for fixture in fixtures:
        b=next(b for b in bindings if b['assetCode']==fixture['assetCode'])
        assert b['targetNode']==fixture['expectedTargetNode'] and b['stationId']==fixture['expectedStationId'] and b['controllerId']==fixture['expectedControllerId']
        fixture_results.append({'fixture':fixture['fixtureId'],'status':'MODEL_RESOLUTION_PASS_NOT_PLATFORM_ALARM_TEST'})
    assert not any('PUMP' in o.name.upper() or 'TANK' in o.name.upper() or 'MQ5' in o.name.upper() or 'MQ-5' in o.name.upper() for o in objects)
    assert all(o['physicalTag']!='LEVEL-05' for o in sensors)
    mods=[o for o in roots if o['category']=='rs485_module']
    assert {o['assetCode'] for o in mods if o.get('termination')=='ON_END'}=={'RS485-05','RS485-04'}
    for o in roots:
        if o['category']=='fan': assert o['airflow']=='CHAMBER_TO_EXTERIOR' and o['connectedToProcessPipe']==False
        if o['category']=='utility_pipe': assert o['role']=='BUSINESS_PIPE_NOT_AIR_DUCT'
    lid=bpy.data.objects['REMOVABLE_TRANSPARENT_LID']
    assert lid['removable'] and not lid.hide_render
    assert 'STATION_LABELS' in bpy.data.objects
    # Primary independent module bodies; large routed pipe AABBs excluded.
    physical=[o for o in roots if o['category'] not in {'utility_pipe','led_strip'}]
    clashes=[]
    for i,a in enumerate(physical):
        aa=bounds(a)
        for b in physical[i+1:]:
            bb=bounds(b)
            overlap=[min(aa[1][j],bb[1][j])-max(aa[0][j],bb[0][j]) for j in range(3)]
            if min(overlap)>.15: clashes.append([a.name,b.name,[round(x,2) for x in overlap]])
    assert not clashes,clashes
    pipe_routes=[json.loads(o['route_mm']) for o in roots if o['category']=='utility_pipe']
    # Check dry support posts against process-pipe centrelines at pipe elevation.
    post_checks=0
    for o in objects:
        if o.type!='MESH' or not ('_LEG_' in o.name or '_SUPPORT' in o.name or '_STAND_' in o.name): continue
        if o.name.startswith('PIPE_') or o.name.startswith('STUDIO_'): continue
        b=bounds(o)
        if not b[0][2]<85<b[1][2]: continue
        p=o.matrix_world.translation*1000
        r=max(b[1][0]-b[0][0],b[1][1]-b[0][1])/2
        for route in pipe_routes:
            distance=min(distance_xy(p,a,c) for a,c in zip(route,route[1:]))
            assert distance>11+r-.1,('support_pipe_collision',o.name,round(distance,2),r)
        post_checks+=1
    # Correct text transforms: parented labels should sit on their own carrier.
    for p in range(1,6):
        lab=bpy.data.objects[f'STATION_LABEL_P{p}']
        group=bpy.data.objects[f'STATION_P{p}']
        assert (lab.matrix_world.translation-group.matrix_world.translation).length<.07
    envelope=None
    if form=='blend':
        solids=[o for o in objects if o.type in {'MESH','CURVE'} and not o.name.startswith('STUDIO_')]
        bb=[bounds(o) for o in solids]
        envelope=[[round(min(b[0][j] for b in bb),3) for j in range(3)],[round(max(b[1][j] for b in bb),3) for j in range(3)]]
        assert all(envelope[0][j]>=-.1 for j in range(3)),envelope
        assert all(envelope[1][j]<=v+.1 for j,v in enumerate([700,700,300])),envelope
    report[form]={'status':'PASS','sensor_count':31,'station_count':5,'ownership':dict(ownership),
        'category_counts':dict(categories),'identity_continuity_from_v15':True,'all_31_targets_unique_and_resolvable':True,
        'station_parentage_correct':True,'no_baked_simulated_alarm_materials':True,'primary_body_clashes':clashes,'dry_support_pipe_clearance_checks':post_checks,
        'bounds_mm':envelope,'fixtures':fixture_results,'platformAlarmIntegration':'NOT_EXECUTED'}
for item in json.loads((ROOT/'protected-input-hashes.json').read_text(encoding='utf-8-sig')):
    assert hashlib.sha256(Path(item['Path']).read_bytes()).hexdigest().upper()==item['Hash']
report['protected_inputs_unchanged']=True
report['limitations']='Concept proxies; no measured installation, electrical, airflow, acoustic, splash or frontend alarm integration approval.'
(ROOT/'validation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('FRESH_MODEL_BINDING_CHECK_PASS',json.dumps(report,ensure_ascii=False),flush=True)
