"""Independent editable concept. Run: D:/blender/blender.exe -b --python build_model.py
All coordinates passed to primitives are mm; Blender/glTF coordinates are metres.
No input model, runtime file, database or firmware is modified.
"""
import bpy
import csv
import hashlib
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
PREVIEW = ROOT / 'previews'
PREVIEW.mkdir(exist_ok=True)
REV = 'square-five-station-v16-concept'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.length_unit = 'MILLIMETERS'
scene['revision'] = REV
scene['status'] = 'CONCEPT_NOT_FABRICATION_APPROVED'
scene['baseline_commit'] = '12c1feebe811329c6370f8927dcb14bc733b40f7'
scene['authorization'] = '2026-10-24: user authorized 700x700x300, corner controllers, five stations, process piping and separate exhaust fans.'
scene['coordinates'] = 'x=0 left, y=0 bottom/front, top view +y up; z=base underside; metres'
scene.render.engine = 'CYCLES'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.render.resolution_x = 1600
scene.render.resolution_y = 1300
scene.render.resolution_percentage = 100
scene.world = bpy.data.worlds.new('Studio world')
scene.world.color = (.24, .24, .24)
scene.view_settings.view_transform = 'AgX'
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

def mat(name, color, metal=0, rough=.48):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    return m

M = {
    'frame': mat('01 Graphite aluminium / concept', (.055,.085,.12), .6),
    'floor': mat('02 Warm light grey deck', (.64,.69,.71)),
    'pcb': mat('03 Controller soldermask', (.025,.23,.14)),
    'black': mat('04 Semiconductor and grilles', (.018,.025,.035)),
    'metal': mat('05 Stainless / visual proxy', (.58,.64,.69), .72),
    'white': mat('06 Light typography', (.94,.97,.99)),
    'ink': mat('07 Dark typography', (.035,.065,.09)),
    'signal': mat('08 RS485 A amber', (1,.51,.025)),
    'signalB': mat('09 RS485 B ivory', (.93,.88,.6)),
    'ground': mat('10 Reference ground', (.12,.14,.16)),
    'power': mat('11 LV supply, voltage TBD', (.73,.055,.035)),
    'water': mat('12 Dry tray / turquoise', (.045,.34,.43), .3),
    'screen': mat('13 Display blue', (.025,.15,.23), .15),
    'MQ2': mat('14 MQ-2 module', (.12,.34,.66)),
    'MQ4': mat('15 MQ-4 module', (.66,.19,.14)),
    'CO': mat('16 MQ-7 module', (.46,.22,.6)),
    'FLAME': mat('17 Flame module', (.86,.37,.035)),
    'SHT': mat('18 Temperature humidity module', (.025,.49,.43)),
    'O2': mat('19 Oxygen module', (.48,.58,.13)),
    'LEVEL': mat('20 Level module', (.07,.41,.64)),
    'blue': mat('21 Illustrative utility pipe', (.045,.25,.55), .3),
    'yellow': mat('22 Illustrative gas pipe', (.87,.55,.07), .3),
}
ZONE = [mat('Zone '+str(i+1), c) for i,c in enumerate([
    (.065,.38,.51),(.25,.46,.29),(.46,.28,.56),(.65,.34,.13)])]
COL = {}
for name in ['00_STRUCTURE','01_CONTROLLERS','02_SENSORS_31','03_BUS_POWER','04_ACTUATION_UI','05_VOICE','06_PIPES','90_ANNOTATIONS','99_STUDIO']:
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    COL[name] = c
EXPORT = []
ASSETS = []
ACTIVE = '00_STRUCTURE'
font_path = Path('C:/Windows/Fonts/msyh.ttc')
FONT = bpy.data.fonts.load(str(font_path)) if font_path.exists() else None

def finish(o, name, material=None, parent=None, export=True):
    o.name = name
    for c in list(o.users_collection):
        c.objects.unlink(o)
    COL[ACTIVE].objects.link(o)
    if material:
        o.data.materials.append(material)
    if parent:
        bpy.context.view_layer.update()
        world = o.matrix_world.copy()
        o.parent = parent
        o.matrix_world = world
    if export:
        EXPORT.append(o)
    return o

def box(name, xyz, dims, material, parent=None, bevel=.7, export=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=Vector(xyz)/1000)
    o = finish(bpy.context.object, name, material, parent, export)
    o.dimensions = Vector(dims)/1000
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b = o.modifiers.new('Concept edge radius', 'BEVEL')
        b.width = bevel/1000
        b.segments = 2
        o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o

def cyl(name, xyz, radius, depth, material, axis='Y', parent=None, vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius/1000, depth=depth/1000, location=Vector(xyz)/1000)
    o = finish(bpy.context.object, name, material, parent)
    if axis == 'Y': o.rotation_euler[0] = math.pi/2
    if axis == 'X': o.rotation_euler[1] = math.pi/2
    return o

def ring(name, xyz, major, minor, material, axis='Y', parent=None):
    bpy.ops.mesh.primitive_torus_add(major_segments=32, minor_segments=8, location=Vector(xyz)/1000, major_radius=major/1000, minor_radius=minor/1000)
    o = finish(bpy.context.object, name, material, parent)
    if axis == 'Y': o.rotation_euler[0] = math.pi/2
    if axis == 'X': o.rotation_euler[1] = math.pi/2
    return o

def wire(name, points, material, radius=.7, parent=None):
    c = bpy.data.curves.new(name, 'CURVE')
    c.dimensions = '3D'
    c.bevel_depth = radius/1000
    c.bevel_resolution = 1
    c.use_fill_caps = True
    s = c.splines.new('POLY')
    s.points.add(len(points)-1)
    for p,xyz in zip(s.points, points): p.co = (*[v/1000 for v in xyz],1)
    o = bpy.data.objects.new(name,c)
    return finish(o,name,material,parent)

def label(name, body, xyz, size=7, material=None, rotation=(math.pi/2,0,0), parent=None, export=True):
    c = bpy.data.curves.new(name,'FONT')
    c.body = body
    c.size = size/1000
    c.align_x = 'CENTER'
    c.align_y = 'CENTER'
    if FONT: c.font = FONT
    o = bpy.data.objects.new(name,c)
    COL[ACTIVE].objects.link(o)
    o.location = Vector(xyz)/1000
    o.rotation_euler = rotation
    return finish(o,name,material or M['white'],parent,export)

def record(o, code, physical, category, family, controller='', point='', status='PROPOSED_NEW_ID', dimensions='UNMEASURED_PROXY'):
    o['assetCode'] = code
    o['physicalTag'] = physical
    o['category'] = category
    o['family'] = family
    o['controllerId'] = controller
    o['detectionPoint'] = point
    o['dimensionEvidence'] = dimensions
    o['commissioned'] = False
    o['identityStatus'] = status
    ASSETS.append({'assetCode':code,'physicalTag':physical,'meshNames':[o.name],
        'category':category,'family':family,'controllerId':controller,'detectionPoint':point,
        'identityStatus':status,'position_mm':[round(v*1000,3) for v in o.location],
        'dimensionEvidence':dimensions,'pin':'TBD_NOT_A_WIRING_INSTRUCTION'})
    bpy.context.view_layer.update()
    ASSETS[-1]['position_mm']=[round(v*1000,3) for v in o.matrix_world.translation]
    return o

for name in ['07_STATIONS','08_REMOVABLE_COVER','90_STATION_LABELS']:
    c=bpy.data.collections.new(name)
    scene.collection.children.link(c)
    COL[name]=c
BASELINE=json.loads((ROOT/'identity-baseline-v15.json').read_text(encoding='utf-8'))
IDENTITIES={a['physicalTag']:a for a in BASELINE['assets'] if a['category']=='external_sensor'}
CTRL={1:(110,590),2:(590,590),3:(110,110),4:(590,110)}
POINTS={1:(260,540,1),2:(440,540,2),3:(260,160,3),4:(440,160,4),5:(350,350,3)}
STATIONS=[]

def empty(name, xyz=(0,0,0), parent=None):
    o=bpy.data.objects.new(name,None)
    o.location=Vector(xyz)/1000
    COL[ACTIVE].objects.link(o)
    bpy.context.view_layer.update()
    return finish(o,name,parent=parent)

def toptext(name,body,xyz,size=6,material=None,parent=None):
    return label(name,body,xyz,size,material or M['ink'],rotation=(0,0,0),parent=parent)

def cut(obj,name,xyz,dims=None,radius=None,axis='Y'):
    cutter=box(name,xyz,dims,M['black'],bevel=0,export=False) if dims else cyl(name,xyz,radius,30,M['black'],axis)
    if cutter in EXPORT: EXPORT.remove(cutter)
    bpy.context.view_layer.objects.active=obj
    obj.select_set(True)
    mod=obj.modifiers.new(name,'BOOLEAN')
    mod.operation='DIFFERENCE'
    mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)

glass=mat('Clear removable acrylic / conceptual',(.64,.82,.9),0,.12)
glass.diffuse_color=(.64,.82,.9,.045)
bsdf=glass.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Alpha'].default_value=.045
bsdf.inputs['Transmission Weight'].default_value=0
if hasattr(glass,'surface_render_method'): glass.surface_render_method='DITHERED'

ACTIVE='00_STRUCTURE'
box('STRUCTURE_BASE',(350,350,5),(700,700,10),M['floor'])
for n,(cx,cy) in CTRL.items():
    x=175 if cx<350 else 525
    y=525 if cy>350 else 175
    box(f'ZONE_{n}_FLOOR',(x,y,11),(334,334,2),ZONE[n-1],bevel=.3)
for x in [6,694]:
    for y in [6,694]: box(f'FRAME_POST_{x}_{y}',(x,y,155),(12,12,290),M['frame'])
for z in [16,294]:
    for y in [6,694]: box(f'FRAME_X_{y}_{z}',(350,y,z),(688,12,12),M['frame'])
    for x in [6,694]: box(f'FRAME_Y_{x}_{z}',(x,350,z),(12,688,12),M['frame'])
walls={}
for tag,xyz,dims in [('TOP',(350,698,152),(676,4,276)),('BOTTOM',(350,2,152),(676,4,276)),('LEFT',(2,350,152),(4,676,276)),('RIGHT',(698,350,152),(4,676,276))]:
    walls[tag]=box('CLEAR_WALL_'+tag,xyz,dims,glass,bevel=0)
for y in [435,385,325,275]: cut(walls['LEFT'],'PIPE_PORT_CUT_'+str(y),(2,y,85),radius=19,axis='X')
for wall,x,y in [('TOP',530,698),('BOTTOM',160,2)]: cut(walls[wall],'FAN_CUT_'+wall,(x,y,200),radius=33,axis='Y')
for y in [175,525]: cut(walls['RIGHT'],'MAKEUP_CUT_'+str(y),(698,y,70),(25,70,44))
for y in [175,525]:
    for dy in [-31,31]: box(f'MAKEUP_FRAME_{y}_{dy}',(693,y+dy,70),(10,6,44),M['frame'])
    for z in [51,89]: box(f'MAKEUP_FRAME_{y}_{z}',(693,y,z),(10,60,6),M['frame'])
    for dz in [-12,-4,4,12]: box(f'MAKEUP_LOUVER_{y}_{dz}',(693,y,70+dz),(10,58,2),M['metal'])
ACTIVE='08_REMOVABLE_COVER'
cover=box('REMOVABLE_TRANSPARENT_LID',(350,350,296),(674,674,4),glass)
cover['removable']=True
cover['uiVisibilityGroup']='REMOVABLE_COVER'
for x in [285,415]: wire(f'LID_LIFT_TAB_{x}',[(x-10,350,298),(x-10,340,299),(x+10,340,299),(x+10,350,298)],M['metal'],1,parent=cover)

ACTIVE='06_PIPES'
routes={
    'PIPE-G01':[(0,435,85),(60,435,85),(60,640,85),(640,640,85),(640,385,85),(0,385,85)],
    'PIPE-W01':[(0,275,85),(60,275,85),(60,60,85),(640,60,85),(640,325,85),(0,325,85)],
}
for n,(code,route) in enumerate(routes.items(),1):
    o=wire(code,route,M['yellow'] if n==1 else M['blue'],11)
    record(o,code,'','utility_pipe','PROCESS_LINE_MEDIUM_UNSPECIFIED',status='LEGACY_ID_PRESERVED' if n==1 else 'PROPOSED_NEW_ID')
    o['role']='BUSINESS_PIPE_NOT_AIR_DUCT'
    o['ports']=f'PROCESS_INLET_{n:02},PROCESS_OUTLET_{n:02}'
    o['route_mm']=json.dumps(route)
    for port,y in [('INLET',route[0][1]),('OUTLET',route[-1][1])]:
        ring(f'PROCESS_{port}_{n:02}',(5,y,85),17,2.5,M['metal'],'X',o)
        toptext(f'PROCESS_{port}_{n}_LABEL',('进' if port=='INLET' else '出')+str(n),(34,y+21,105),6,parent=o)
    supports=[(60,570,'Y'),(350,640,'X'),(640,570,'Y'),(350,385,'X')] if n==1 else [(60,130,'Y'),(350,60,'X'),(640,130,'Y'),(350,325,'X')]
    for j,(x,y,axis) in enumerate(supports):
        box(f'PIPE_{n}_SUPPORT_{j}',(x,y,43),(22,22,64),M['frame'],o)
        ring(f'PIPE_{n}_CLAMP_{j}',(x,y,85),12,1.8,M['metal'],axis,o)

ACTIVE='01_CONTROLLERS'
for n,(x,y) in CTRL.items():
    code=f'CTRL-{n:02}'
    box(code+'_PLATFORM',(x,y,123),(160,130,5),M['frame'])
    for dx in [-70,70]:
        for dy in [-30,30]: cyl(code+f'_LEG_{dx}_{dy}',(x+dx,y+dy,66),3,110,M['metal'],'Z')
    o=box(code,(x,y,135),(68,65,3),M['pcb'])
    record(o,code,code,'controller','STM32F103RCT6',code,status='LEGACY_ID_PRESERVED' if n<3 else 'PROPOSED_NEW_ID')
    box(code+'_MCU',(x,y,140),(18,18,6),M['black'],o)
    for dx in [-29,29]:
        for j in range(9): box(code+f'_HEADER_{dx}_{j}',(x+dx,y-25+j*6,140),(3,3,6),M['metal'],o,bevel=.2)
    for dx in [-22,22]: cyl(code+f'_STANDOFF_{dx}',(x+dx,y,130),2,9,M['metal'],'Z')
    toptext(code+'_LABEL',code+f' / {[7,6,11,7][n-1]}路',(x,y+65 if n<3 else y-61,127),9,M['white'])
    xm=x+55
    mod=box(f'RS485-{n:02}',(xm,y,135),(33,17,3),M['black'])
    record(mod,f'RS485-{n:02}','','rs485_module','JSM485_NONISOLATED',code,dimensions='APPROX_33x17_MM_IMAGE_NOT_MEASURED')
    mod['termination']='ON_END' if n==4 else 'OFF_INTERMEDIATE'
    box(f'RS485_{n}_SW1',(xm-9,y,139),(6,4,3),M['white'],mod)
    box(f'RS485_{n}_TERMINAL',(xm+9,y,141),(9,12,8),ZONE[n-1],mod)
    toptext(f'RS485_{n}_TEXT','485 '+('ON' if n==4 else 'OFF'),(xm,y-17,143),4)
    reg=box(f'REG-{n:02}',(x-55,y,135),(30,22,3),M['pcb'])
    record(reg,f'REG-{n:02}','','regulator','ZONE_REGULATOR_TBD',code)
    cyl(f'REG_{n}_INDUCTOR',(x-55,y,142),6,10,M['black'],'Z',reg)
    bank=box(code+'_TERMINALS',(x,y-50,134),(90,12,12),ZONE[n-1])
    for j in range(8): cyl(code+f'_TERMINAL_SCREW_{j}',(x-35+j*10,y-50,141),1.6,1,M['metal'],'Z',bank,vertices=12)

ACTIVE='03_BUS_POWER'
bus=[(120,350,150),(120,350,245),(70,350,245),(70,670,245),(665,670,245),(665,460,245),(40,460,245),(40,110,245),(645,110,245),(645,110,140)]
for tag,offset,material in [('A',0,M['signal']),('B',-4,M['signalB']),('REF',-8,M['ground'])]:
    wire('RS485_TRUNK_'+tag,[(x,y,z+offset) for x,y,z in bus],material,.8)
for n,(start,x,y) in enumerate([((165,670),165,590),((665,590),645,590),((165,110),165,110)],1):
    for tag,offset,material in [('A',0,M['signal']),('B',-4,M['signalB']),('REF',-8,M['ground'])]:
        wire(f'RS485_DROP_{n}_{tag}',[(start[0],start[1],245+offset),(x,y,245+offset),(x,y,140+offset)],material,.55)
# Thin open cable channels and cross-members reserve overhead routing space.
for j,(a,b) in enumerate(zip(bus[2:-2],bus[3:-1])):
    if a[2]!=b[2]: continue
    mid=tuple((aa+bb)/2 for aa,bb in zip(a,b))
    dims=(max(5,abs(a[0]-b[0])),max(5,abs(a[1]-b[1])),4)
    box(f'BUS_CABLE_CHANNEL_{j}',(mid[0],mid[1],252),dims,M['frame'])
entry=box('LV_POWER_ENTRY',(350,676,145),(34,24,25),M['black'])
record(entry,'POWER-ENTRY-01','','power_entry','LOW_VOLTAGE_RATING_TBD')
power=[(350,676,145),(350,676,226),(25,676,226),(25,25,226),(675,25,226),(675,676,226)]
wire('LV_POWER_TRUNK',power,M['power'],1)
wire('LV_RETURN_TRUNK',[(x,y,z-4) for x,y,z in power],M['ground'],1)
for n,(x,y) in CTRL.items():
    side=25 if x<350 else 675
    wire(f'ZONE_{n}_POWER_BRANCH',[(side,y,226),(x-55,y,226),(x-55,y,143)],M['power'],.8)
    wire(f'ZONE_{n}_RETURN_BRANCH',[(side,y+4,222),(x-51,y+4,222),(x-51,y,143)],M['ground'],.8)

ACTIVE='04_ACTUATION_UI'
gate=box('MESH_ESP01S_01',(80,350,150),(25,54,3),M['pcb'])
record(gate,'NET-01','ESP32-S3-GATEWAY','gateway','ESP32-S3_RS485_MQTT',status='LEGACY_ID_HARDWARE_MIGRATION_PENDING')
box('GATEWAY_RF',(80,365,155),(20,15,5),M['metal'],gate)
box('GATEWAY_PLATFORM',(95,350,143),(95,80,4),M['frame'])
for x in [60,130]: cyl('GATEWAY_SUPPORT_'+str(x),(x,350,78),3,126,M['metal'],'Z')
gmod=box('RS485-05',(120,350,150),(33,17,3),M['black'])
record(gmod,'RS485-05','','rs485_module','JSM485_NONISOLATED','NET-01',dimensions='APPROX_33x17_MM_IMAGE_NOT_MEASURED')
gmod['termination']='ON_END'
box('GATEWAY_SW1',(111,350,154),(6,4,3),M['white'],gmod)
toptext('GATEWAY_TEXT','NET-01 / MQTT  |  485 ON',(95,381,147),5,M['white'])

ACTIVE='07_STATIONS'
labelroot=empty('STATION_LABELS')
labelroot['uiToggle']='stationLabelsVisible'
for p,(x,y,owner) in POINTS.items():
    group=empty(f'STATION_P{p}',(x,y,151))
    group['stationId']=f'P{p}'
    group['controllerId']=f'CTRL-{owner:02}'
    group['notAnMCU']=True
    group['alarmScope']='Four independent member sensors, never merge their alarms'
    box(f'P{p}_CARRIER',(x,y,145),(110,105,4),M['white'],group)
    for dx in [-44,44]: cyl(f'P{p}_SUPPORT_{dx}',(x+dx,y,78),3,130,M['metal'],'Z',group)
    STATIONS.append({'stationId':f'P{p}','groupNode':group.name,'controllerId':f'CTRL-{owner:02}',
        'topViewPosition':['UPPER_LEFT','UPPER_RIGHT','LOWER_LEFT','LOWER_RIGHT','CENTRE'][p-1],
        'focusPositionBlender_m':[x/1000,y/1000,.16],
        'focusPositionGltf_m':[x/1000,.16,-y/1000],'memberAssetCodes':[],'memberPhysicalTags':[]})
    ACTIVE='90_STATION_LABELS'
    toptext(f'STATION_LABEL_P{p}',f'P{p}  /  CTRL-0{owner}',(x,y+45,149),7,M['ink'],labelroot)
    ACTIVE='07_STATIONS'

ACTIVE='02_SENSORS_31'
def sensor(tag,family,xyz,owner,station,parent=None,member=False):
    old=IDENTITIES[tag]
    x,y,z=xyz
    o=box(old['meshNames'][0],xyz,(34,26,3),M[family],parent)
    record(o,old['assetCode'],tag,'external_sensor',family,owner,station if member else '',old['identityStatus'])
    a=ASSETS[-1]
    a['stationId']=station
    a['stationLinkKind']='DIRECT_FOUR_SENSOR_MEMBER' if member else 'SPATIAL_CONTEXT_NOT_GAS_STATION_MEMBER'
    a['alarmTargetNode']=o.name
    a['stationGroupNode']='STATION_'+station
    o['stationId']=station
    o['physicalMember']=member
    if family in ['MQ2','MQ4','CO']:
        cyl(tag+'_CAN',(x,y,z+11),9.5,18,M['metal'],'Z',o)
        for dx in [-4,0,4]: box(tag+f'_MESH_{dx}',(x+dx,y,z+20.2),(1,11,.8),M['black'],o,bevel=.1)
    elif family=='FLAME': cyl(tag+'_OPTIC',(x,y,z+9),4,15,M['black'],'Z',o)
    elif family=='SHT': box(tag+'_CHIP',(x,y,z+4),(8,8,5),M['metal'],o)
    elif family=='O2': cyl(tag+'_CELL',(x,y,z+10),10,17,M['metal'],'Z',o)
    if member:
        for dx in [-11,11]: cyl(tag+f'_MOUNT_{dx}',(x+dx,y,148.5),1.5,3,M['metal'],'Z',o)
    else:
        # Environmental and level conditioning modules remain above the wet area.
        cyl(tag+'_SUPPORT',(x,y,(z+10)/2),2.5,z-13,M['metal'],'Z',o)
    toptext(tag+'_TEXT',tag,(x,y-20,z+2),5,parent=o)
    cx,cy=CTRL[int(owner[-2:])]
    # Local tails are not children of the alarm target: highlighting a sensor must
    # never paint a long shared harness or another station as the same alarm.
    if member:
        sx,sy,_=POINTS[int(station[1:])]
        route=[(x+15,y,z),(x+19,y,z),(x+19,sy+35,z+3),(sx,sy+35,z+3)]
    else:
        route=[(x+15,y,z),(x+19,y,z),(x+19,y,z+20),(cx,cy-40,z+20),(cx,cy-50,140)]
    wire(tag+'_LOCAL_HARNESS',route,ZONE[int(owner[-2:])-1],.45)
    if family=='LEVEL':
        tray=TRAYS[int(tag[-2:])]
        probe=cyl(old['meshNames'][1],(tray[0],tray[1],35),6,20,M['metal'],'X',o)
        a['meshNames'].append(probe.name)
        wire(tag+'_PROBE_CABLE',[(x,y,z),(x,y,70),(tray[0],tray[1],70),(tray[0],tray[1],35)],ZONE[int(owner[-2:])-1],.8,o)
    if member:
        STATIONS[int(station[1:])-1]['memberAssetCodes'].append(a['assetCode'])
        STATIONS[int(station[1:])-1]['memberPhysicalTags'].append(tag)

TRAYS={1:(115,440),2:(585,440),3:(115,260),4:(585,260)}
for p,(x,y,owner) in POINTS.items():
    group=bpy.data.objects[f'STATION_P{p}']
    for family,dx,dy in [('MQ2',-25,22),('MQ4',25,22),('CO',-25,-22),('FLAME',25,-22)]:
        sensor(f'{family}-{p:02}',family,(x+dx,y+dy,151),f'CTRL-{owner:02}',f'P{p}',group,True)
    cx,cy=CTRL[owner]
    wire(f'P{p}_ZONE_HARNESS',[(x,y+35,155),(x,y+35,211),(cx,cy-40,211),(cx,cy-50,140)],ZONE[owner-1],1.1)
for n,(x,y) in TRAYS.items():
    tray=box(f'WET_TRAY_{n:02}',(x,y,17),(140,85,6),M['water'])
    record(tray,f'WET-TRAY-{n:02}','','wet_tray','INDEPENDENT_CATCH_POSITION',f'CTRL-{n:02}')
    for dx in [-67,67]: box(f'TRAY_{n}_END_{dx}',(x+dx,y,32),(6,85,24),M['water'],tray)
    for dy in [-39.5,39.5]: box(f'TRAY_{n}_SIDE_{dy}',(x,y+dy,32),(134,6,24),M['water'],tray)
    toptext(f'TRAY_{n}_LABEL',f'W{n} / 独立接水',(x,y-27,21),7,M['white'])
    sy=500 if n<3 else 200
    sensor(f'LEVEL-{n:02}','LEVEL',(x,sy,105),f'CTRL-{n:02}',f'P{n}')
    ty=520 if n<3 else 180
    sensor(f'SHT-{n:02}','SHT',(110 if n%2 else 590,ty,180),f'CTRL-{n:02}',f'P{n}')
for tag,x,y,owner,p in [('O2-01',215,455,1,1),('O2-02',435,350,3,5),('O2-03',460,245,4,4)]:
    sensor(tag,'O2',(x,y,180),f'CTRL-{owner:02}',f'P{p}')

ACTIVE='04_ACTUATION_UI'
for n,code,title in [(1,'DISP-02','STATUS'),(2,'DISP-01','MAIN MENU')]:
    x,y=CTRL[n]
    o=box('MESH_'+code.replace('-','_'),(x,y+40,158),(45,32,7),M['black'])
    record(o,code,'','business_display','ST7735S_TFT',f'CTRL-{n:02}',status='LEGACY_ID_PRESERVED' if n==2 else 'PROPOSED_NEW_ID')
    box(code+'_LCD',(x,y+40,162),(37,25,2),M['screen'],o)
    toptext(code+'_TEXT',title,(x,y+40,164),5,M['white'],o)
    for dx in [-15,15]: cyl(code+f'_SUPPORT_{dx}',(x+dx,y+40,142),2,28,M['metal'],'Z')
for n in [1,4]:
    x,y=CTRL[n]
    num=1 if n==1 else 2
    rel=box('MESH_RELAY_01' if num==1 else 'RELAY-02',(x-55,y+35,137),(29,24,3),M['pcb'])
    record(rel,f'RELAY-{num:02}','','relay','ONE_RELAY_CHANNEL',f'CTRL-{n:02}',status='LEGACY_ID_PRESERVED' if num==1 else 'PROPOSED_NEW_ID')
    box(f'RELAY_{num}_COIL',(x-55,y+35,146),(18,15,14),M['blue'],rel)
    ina=box(f'INA226-{num:02}',(x+55,y+35,137),(26,17,3),M['pcb'])
    record(ina,f'INA226-{num:02}','','power_monitor','INA226',f'CTRL-{n:02}')
    box(f'INA_{num}_SHUNT',(x+55,y+35,141),(12,4,4),M['metal'],ina)
joy=cyl('JOYSTICK-01',(635,550,155),8,14,M['black'],'Z')
record(joy,'JOYSTICK-01','','joystick','ANALOG_JOYSTICK','CTRL-02')
buzz=cyl('MESH_BUZZ_01',(545,550,154),7,10,M['black'],'Z')
record(buzz,'BUZZ-01','','buzzer','ACTIVE_BUZZER','CTRL-02',status='LEGACY_ID_PRESERVED')
led=wire('MESH_LED_01',[(20,20,282),(20,680,282),(680,680,282),(680,20,282)],M['white'],1.4)
record(led,'LED-01','','led_strip','EXISTING_LED_STRIP_LENGTH_TBD','CTRL-02',status='LEGACY_ID_PRESERVED')
for n,(x,y) in enumerate([(530,687),(160,13)],1):
    fan=ring(f'FAN-{n:02}',(x,y,200),28,3,M['black'],'Y')
    record(fan,f'FAN-{n:02}','','fan','CHAMBER_AIR_EXHAUST',f'CTRL-{1 if n==1 else 4:02}',status='LEGACY_ID_PRESERVED')
    fan['airflow']='CHAMBER_TO_EXTERIOR'
    fan['connectedToProcessPipe']=False
    cyl(f'FAN_{n}_HUB',(x,y,200),9,14,M['metal'],'Y',fan)
    for angle in range(0,360,72):
        a=math.radians(angle)
        b=box(f'FAN_{n}_BLADE_{angle}',(x+16*math.cos(a),y,200+16*math.sin(a)),(22,4,8),M['metal'],fan)
        b.rotation_euler[1]=-a+.4
    for dx in [-27,27]:
        for dz in [-27,27]: box(f'FAN_{n}_MOUNT_{dx}_{dz}',(x+dx,y,200+dz),(10,18,10),M['frame'],fan)
    for dx in [-18,-9,0,9,18]: box(f'FAN_{n}_GUARD_{dx}',(x+dx,695 if n==1 else 5,200),(2,2,44),M['metal'],fan,bevel=.2)

ACTIVE='05_VOICE'
box('VOICE_PLATFORM',(610,350,143),(135,125,5),M['frame'])
for x in [560,660]:
    for y in [300,400]: cyl(f'VOICE_STAND_{x}_{y}',(x,y,78),3,128,M['metal'],'Z')
voice=box('VOICE-01',(585,350,151),(25,54,3),M['pcb'])
record(voice,'VOICE-01','ESP32-S3-VOICE','voice_controller','ESP32-S3_XIAOZHI')
box('VOICE_RF',(585,367,156),(20,15,5),M['metal'],voice)
mic=box('VOICE-MIC-01',(565,390,151),(14,15,3),M['pcb'])
record(mic,'VOICE-MIC-01','','microphone','INMP441','VOICE-01')
ring('MIC_PICKUP_APERTURE',(565,390,161),4,1.2,M['metal'],'Z')
amp=box('VOICE-AMP-01',(585,305,151),(18,17,3),M['pcb'])
record(amp,'VOICE-AMP-01','','amplifier','MAX98357','VOICE-01')
speaker=cyl('VOICE-SPK-01',(635,350,157),21,17,M['black'],'Z')
record(speaker,'VOICE-SPK-01','','speaker','8OHM_3W_RATED_SIZE_TBD','VOICE-01')
ring('SPEAKER_APERTURE',(635,350,171),22,2,M['metal'],'Z')
for dx in [-15,-10,-5,0,5,10,15]: box(f'SPEAKER_GRILLE_{dx}',(635+dx,350,171),(1.5,2*math.sqrt(20**2-dx**2),2),M['metal'],speaker)
oled=box('VOICE-OLED-01',(625,393,152),(29,13,4),M['screen'])
record(oled,'VOICE-OLED-01','','voice_display','0.91_INCH_OLED','VOICE-01')
toptext('OLED_TEXT','VOICE',(625,393,155),4,M['white'],oled)
button=cyl('VOICE-BUTTON-01',(697.5,305,160),5,5,M['signal'],'X')
record(button,'VOICE-BUTTON-01','','voice_button','PUSH_TO_TALK','VOICE-01')
cut(walls['RIGHT'],'VOICE_BUTTON_WALL_CUT',(698,305,160),radius=6,axis='X')
box('VOICE_BUTTON_BRACKET',(688,305,152),(20,16,3),M['metal'])
wire('VOICE_BUTTON_TO_BOARD',[(695,305,160),(675,305,160),(585,305,154)],M['signalB'],.6)
for tag,xy,radius in [('MIC',(565,390),5),('SPEAKER',(635,350),25)]:
    cut(cover,tag+'_LID_CUT',(*xy,296),radius=radius,axis='Z')
    ring(tag+'_LID_RIM',(*xy,298),radius,1,M['metal'],'Z',cover)
for dx in [-18,-12,-6,0,6,12,18]:
    box(f'SPEAKER_LID_GRILLE_{dx}',(635+dx,350,299),(1.3,2*math.sqrt(23**2-dx**2),1),M['metal'],cover,bevel=.2)
cover['voiceAperturesAdded']=True
button['externalWallAccess']=True
toptext('VOICE_TITLE','VOICE / 独立语音',(610,296,147),6,M['white'])
for name,route in [('MIC',[(565,390,154),(585,380,155)]),('AMP',[(585,323,154),(585,305,154)]),('SPK',[(585,305,154),(635,305,149),(635,330,150)]),('OLED',[(585,380,155),(625,385,155)])]: wire('VOICE_'+name+'_HARNESS',route,M['signalB'],.6)

# Generic, explicitly unmeasured standoffs for the small dry electronics.
bpy.context.view_layer.update()
stand_categories={'regulator','rs485_module','gateway','power_monitor','relay','buzzer','joystick','voice_controller','microphone','amplifier','speaker','voice_display'}
for a in ASSETS:
    if a['category'] not in stand_categories: continue
    obj=bpy.data.objects[a['meshNames'][0]]
    corners=[obj.matrix_world @ Vector(v) for v in obj.bound_box]
    bottom=min(v.z for v in corners)*1000
    top=145.5 if a['category'] in {'voice_controller','microphone','amplifier','speaker','voice_display','voice_button'} else 145 if a['category']=='gateway' or a['controllerId']=='NET-01' else 125.5
    width=(max(v.x for v in corners)-min(v.x for v in corners))*1000
    x,y,_=a['position_mm']
    for dx in [-width*.25,width*.25]: cyl(a['assetCode']+f'_GENERIC_MOUNT_{dx:.2f}',(x+dx,y,(bottom+top)/2),1.5,bottom-top,M['metal'],'Z')
for x in [340,360]: cyl('POWER_ENTRY_MOUNT_'+str(x),(x,676,71.75),2.5,121.5,M['metal'],'Z')

ACTIVE='90_ANNOTATIONS'
toptext('BASE_TITLE','700 x 700 x 300 / FIVE STATIONS',(350,39,13),11)
toptext('TOP_ORIENTATION','TOP / 上侧',(350,658,13),9)
ACTIVE='99_STUDIO'
box('STUDIO_GROUND',(350,350,-18),(5000,5000,25),mat('Pale studio',(.82,.86,.88)),bevel=0,export=False)
def area(name,xyz,energy,size):
    d=bpy.data.lights.new(name,'AREA'); d.energy=energy; d.shape='DISK'; d.size=size
    o=bpy.data.objects.new(name,d); COL[ACTIVE].objects.link(o); o.location=xyz
    o.rotation_euler=(Vector((.35,.35,.10))-o.location).to_track_quat('-Z','Y').to_euler()
area('KEY',(-.4,-.6,1.8),70,1.7)
area('FILL',(1.4,1.2,1.5),60,1.5)
area('FRONT',(.5,-.8,.8),20,1.2)
def camera(name,xyz,target,scale):
    d=bpy.data.cameras.new(name); d.type='ORTHO'; d.ortho_scale=scale
    o=bpy.data.objects.new(name,d); COL[ACTIVE].objects.link(o); o.location=xyz
    o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    return o
CAMS={
    'overall':camera('VIEW_OVERALL',(1.18,-1.04,1.21),(.35,.35,.12),1.15),
    'top':camera('VIEW_TOP',(.35,.35,2),(.35,.35,0),1.0),
    'front':camera('VIEW_FRONT',(.35,-1.6,.18),(.35,.35,.18),.88),
    'side':camera('VIEW_SIDE',(1.8,.35,.18),(.35,.35,.18),.88),
}
scene.camera=CAMS['overall']
for screen in bpy.data.screens:
    for a in screen.areas:
        if a.type=='VIEW_3D':
            a.spaces.active.region_3d.view_location=(.35,.35,.12)
            a.spaces.active.region_3d.view_distance=1.4
            a.spaces.active.region_3d.view_rotation=CAMS['overall'].rotation_euler.to_quaternion()
            a.spaces.active.shading.type='MATERIAL'

bpy.context.view_layer.update()
counts=Counter(a['category'] for a in ASSETS)
sensors=[a for a in ASSETS if a['category']=='external_sensor']
ownership=Counter(a['controllerId'] for a in sensors)
assert [ownership[f'CTRL-{n:02}'] for n in range(1,5)]==[7,6,11,7]
assert len(sensors)==31 and len({a['assetCode'] for a in ASSETS})==len(ASSETS)
assert Counter(a['family'] for a in sensors)=={'MQ2':5,'MQ4':5,'CO':5,'FLAME':5,'LEVEL':4,'SHT':4,'O2':3}
for s in STATIONS: assert len(s['memberAssetCodes'])==4
inventory={'revision':REV,'date':'2026-10-24','status':'CONCEPT_NOT_FABRICATION_APPROVED',
    'envelope_mm':[700,700,300],'coordinates':'Blender metres: +X right, +Y up in top view, +Z up; x/y origin bottom-left.',
    'sensor_total':31,'ownership':dict(ownership),'category_counts':dict(counts),'assets':ASSETS}
(ROOT/'asset-map.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (ROOT/'asset-map.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for a in ASSETS for k in a))
    w=csv.DictWriter(f,fields); w.writeheader()
    for a in ASSETS: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in a.items()})
bindings=[]
for a in sensors:
    x,y,z=[v/1000 for v in a['position_mm']]
    bindings.append({'assetCode':a['assetCode'],'physicalTag':a['physicalTag'],'targetNode':a['alarmTargetNode'],
        'relatedNodes':a['meshNames'],'stationId':a['stationId'],'stationGroupNode':a['stationGroupNode'],
        'stationLinkKind':a['stationLinkKind'],'controllerId':a['controllerId'],
        'positionBlender_m':[x,y,z],'positionGltf_m':[x,z,-y],
        'identityStatus':a['identityStatus'],'identityEvidence':'V15 identity continuity; live business registry still requires T01 review',
        'highlightPolicy':'Highlight targetNode subtree; emphasize station separately; never highlight entire controller as sensor alarm.'})
(ROOT/'sensor-bindings.json').write_text(json.dumps({'revision':REV,'status':'MODEL_BINDINGS_VALIDATED_FRONTEND_INTEGRATION_PENDING','bindings':bindings},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(ROOT/'station-focus.json').write_text(json.dumps({'revision':REV,'labelsToggleNode':'STATION_LABELS','stations':STATIONS},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
fixtures=[]
for p in range(1,6):
    b=next(b for b in bindings if b['physicalTag']==f'MQ2-{p:02}')
    fixtures.append({'fixtureId':f'SIMULATED-P{p}','dataSource':'SIMULATED_NOT_LIVE','assetCode':b['assetCode'],
        'expectedTargetNode':b['targetNode'],'expectedStationId':b['stationId'],'expectedControllerId':b['controllerId'],
        'message':'Synthetic mapping fixture only; no actual alarm or telemetry.'})
(ROOT/'alarm-location-fixtures.json').write_text(json.dumps({'status':'FOR_FUTURE_INTEGRATION_TEST_NOT_EXECUTED_ON_PLATFORM','fixtures':fixtures},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/(REV+'.blend')),compress=True)
bpy.ops.object.select_all(action='DESELECT')
for o in EXPORT: o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(ROOT/(REV+'.glb')),export_format='GLB',use_selection=True,
    export_extras=True,export_apply=True,export_cameras=False,export_lights=False,export_yup=True)
raw=(ROOT/(REV+'.glb')).read_bytes()
gltf=json.loads(raw[20:20+struct.unpack_from('<I',raw,12)[0]])
names={n.get('name') for n in gltf['nodes']}
assert all(name in names for a in ASSETS for name in a['meshNames'])
report={'revision':REV,'blender':bpy.app.version_string,'glb_bytes':len(raw),'glb_nodes':len(gltf['nodes']),
    'sha256':hashlib.sha256(raw).hexdigest(),'assets':len(ASSETS),'sensors':31,'stations':5,
    'liveFrontendIntegration':'NOT_EXECUTED','baseline':'2026-10-24 user authorized square layout; V15 preserved'}
(ROOT/'export-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if '--skip-renders' not in sys.argv:
    for view,cam in CAMS.items():
        scene.camera=cam
        scene.render.filepath=str(PREVIEW/(view+'.png'))
        bpy.ops.render.render(write_still=True)
    # A deliberate review cutaway removes the lid and front glazing only.
    for obj in [cover,*cover.children_recursive]: obj.hide_render=True
    walls['BOTTOM'].hide_render=True
    scene.camera=CAMS['overall']
    scene.render.filepath=str(PREVIEW/'cutaway.png')
    bpy.ops.render.render(write_still=True)
print('SQUARE_CONCEPT_BUILD_OK',json.dumps(report),flush=True)


