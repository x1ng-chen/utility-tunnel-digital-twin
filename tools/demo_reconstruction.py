"""Approved demo topology, replacing obsolete generated geometry in a clean build.

All measurements in metres. This is assembly intent, never pressure/electrical approval.
"""
import bpy, math, json
from mathutils import Vector
from pump_reference_geometry import hollow_route, gas_y

WATER_X = [.36,.18,0,-.18,-.36]
WATER_DZ = [-.009,-.009,.007,.007,-.009]
WATER_TITLES = ['入口到水','上游有水','中部高位','下游高位','回水到达']

def water_z(x):
    return .185+.075*(x+.4)

def remove_matching(prefixes, exact=()):
    for obj in list(bpy.data.objects):
        if obj.name in exact or obj.name.startswith(tuple(prefixes)):
            bpy.data.objects.remove(obj,do_unlink=True)

def bore(obj, cutter):
    bpy.context.view_layer.objects.active=obj
    md=obj.modifiers.new('实际通孔','BOOLEAN');md.operation='DIFFERENCE';md.object=cutter
    bpy.ops.object.modifier_apply(modifier=md.name)
    bpy.data.objects.remove(cutter,do_unlink=True)

def rebuild_demo(box,cyl,tube,line,plate,asset,registry,out):
    # Only deterministic geometry built earlier in THIS clean process is replaced.
    remove_matching(['WATER-','LEVEL-L','管托','LEAK-','FLOAT-','浮球固定桥'],
                    ['截止阀','阀杆','阀柄'])
    registry[:]=[a for a in registry if a['kind'] not in ['FSIR02','LEAK','FLOAT']]

    def basin(name,cx,cy,w,d,bottom,top):
        pieces=[]
        pieces.append(box(name+'-底',(cx,cy,bottom+.002),(w,d,.004),'浅灰',0))
        for sign in [-1,1]:
            pieces.append(box(name+f'-端{sign}',(cx+sign*(w/2-.002),cy,(bottom+top)/2),(.004,d,top-bottom),'浅灰',0))
            pieces.append(box(name+f'-边{sign}',(cx,cy+sign*(d/2-.002),(bottom+top)/2),(w-.008,.004,top-bottom),'浅灰',0))
        return pieces

    tank=basin('储水箱',-.36,-.37,.20,.13,.038,.160)
    plate('储水箱标识','储水箱 / 未注水',(-.36,-.4355,.094),.15,.022,.010)
    # Reservoir to axial pump inlet. Existing threaded adapter is retained.
    tube('WATER-吸水管',(-.285,-.36,.115),(.020,-.36,.115),.008,.006)
    for wall in tank:
        if wall.name=='储水箱-端1':bore(wall,cyl('切削',(-.275,-.36,.115),(-.245,-.36,.115),.0081))
    plate('最低水位','入口须淹没',(-.36,-.4355,.132),.10,.013,.007)
    # Inclined, vented gravity pipe, open at both ends.
    a=(-.4,-.395,water_z(-.4));b=(.425,-.395,water_z(.425))
    gravity=hollow_route('WATER-重力测量管',[tuple(Vector(a).lerp(Vector(b),i/80)) for i in range(81)],.020,.017)
    gravity['medium']='gravity_water';gravity['slope']=.075
    for i,x in enumerate([-.24,-.10,.14,.26,.40]):
        z=water_z(x)
        saddle=box(f'管托-重力-{i}',(x,-.395,(.038+z+.004)/2),(.016,.05,z+.004-.038),'铝合金',0)
        bore(saddle,cyl('切削',(x-.03,-.395,water_z(x-.03)),(x+.03,-.395,water_z(x+.03)),.0201))
        box(f'重力底脚-{i}',(x,-.395,.041),(.033,.062,.006),'铝合金',0)
    # Raised open receiving box separates pressure delivery from the gravity measurement.
    header=basin('敞口供水盒',.452,-.38,.074,.10,.220,.275)
    for wall in header:
        if wall.name=='敞口供水盒-端-1':
            bore(wall,cyl('切削',(.405,-.395,water_z(.405)),(.435,-.395,water_z(.435)),.0201))
    for yy in [-.414,-.346]:
        box('供水盒支脚'+str(yy),(.466,yy,.129),(.015,.013,.182),'铝合金')
    plate('供水盒标识','敞口供水',(.442,-.4305,.252),.050,.014,.007)
    # Smooth pump feed ends 30 mm above the receiving box lip.
    pts=[(.052,-.36,.150),(.052,-.36,.310)]
    pts += [(.067-.015*math.cos(i*math.pi/24),-.36,.310+.015*math.sin(i*math.pi/24)) for i in range(1,13)]
    pts += [(.435,-.36,.325)]
    pts += [(.435+.015*math.sin(i*math.pi/24),-.36,.310+.015*math.cos(i*math.pi/24)) for i in range(1,13)]
    pts += [(.450,-.36,.305)]
    hollow_route('WATER-连续泵出口',pts,.008,.006)
    # Supports for the elevated delivery hose, away from probe boards and gravity pipe.
    for xx in [.13,.30]:
        box('供水管支柱'+str(xx),(xx,-.32,.18),(.01,.012,.284),'铝合金')
        box('供水管悬臂'+str(xx),(xx,-.342,.313),(.012,.056,.004),'铝合金')
        tube('供水管卡圈'+str(xx),(xx-.006,-.36,.325),(xx+.006,-.36,.325),.010,.0081)
    points=[]
    for i,(x,dz,title) in enumerate(zip(WATER_X,WATER_DZ,WATER_TITLES),1):
        n=f'LEVEL-L{i:02}';zz=water_z(x)+dz
        bore(gravity,cyl('切削',(x,-.44,zz),(x,-.392,zz),.0052))
        tube(n+'-测点座',(x,-.432,zz),(x,-.408,zz),.008,.0052)
        probe=cyl(n+'-探头',(x,-.445,zz),(x,-.409,zz),.0045,'白')
        asset('FSIR02',n,probe,'局部单阈值；实物安装/输入电平待核验')
        cyl(n+'-光学端',(x,-.409,zz),(x,-.399,zz),.004,'蓝板')
        probe['local_threshold_axis_mm']=round((.017+dz)*1000)
        box(n+'-板卡架',(x,-.237,.151),(.009,.015,.226),'铝合金')
        box(n+'-架脚',(x,-.237,.034),(.04,.028,.008),'铝合金')
        box(n+'-板卡',(x,-.242,.257),(.0386,.003,.0221),'蓝板')
        box(n+'-板卡背座',(x,-.237,.257),(.043,.006,.027),'浅灰')
        box(n+'-插座',(x,-.249,.250),(.018,.008,.007),'白')
        # Wiring is supported on the board stand; cabinet termination deliberately pending.
        line(n+'-探头线',[(x,-.445,zz),(x,-.452,.29),(x,-.249,.29),(x,-.249,.25)],.0011,'黑')
        plate(n,f'L{i:02} {title}',(x,-.247,.233),.088,.014,.007)
        points.append({'id':n,'zone':f'Z{i}','kind':'FSIR02','x_m':x,'y_m':-.404,'z_m':zz,
                       'threshold_axis_above_local_invert_mm':round((.017+dz)*1000),
                       'meaning':title,'data_source':'REAL_WHEN_CONNECTED','state':'NOT_CONNECTED',
                       'route':'CTRL-01:PC0' if i==1 else f'PENDING:L{i:02}'})
    # Independent high float in reservoir, bracket carries its body from the side wall.
    obj=cyl('FLOAT-01',(-.30,-.405,.128),(-.30,-.405,.152),.012,'白');asset('FLOAT','FLOAT-01',obj)
    box('浮球固定桥',(-.30,-.419,.154),(.016,.032,.004),'铝合金',0)
    box('浮球桥支柱',(-.30,-.433,.150),(.016,.004,.012),'铝合金',0)
    for i,x in enumerate([-.20,.20],1):
        obj=box(f'LEAK-{i}',(x,-.30,.044),(.021,.025,.012),'蓝板');asset('LEAK',f'LEAK-{i}',obj)
    # Both overflow paths discharge openly into the tray; they do not recirculate pressure.
    for name,x,y,z,wall in [('储水溢流',-.28,-.37,.148,tank[1]),('供水溢流',.473,-.38,.264,header[1])]:
        # Front-wall outlet to downward drain, bored through the corresponding front wall.
        front_y=-.435 if name=='储水溢流' else -.43
        for piece in (tank if name=='储水溢流' else header):
            if piece.name.endswith('边-1'):bore(piece,cyl('切削',(x,front_y-.015,z),(x,front_y+.015,z),.0041))
        pts=[(x,front_y+.008,z),(x,front_y-.006,z),(x,front_y-.006,.090)]
        hollow_route('WATER-'+name,pts,.004,.003)

    # Reset main gas pipe so the obsolete recirculation intake hole is not left open.
    remove_matching(['气管取样支路-进气过滤'],['PIPE-G01','气管封帽0'])
    main=hollow_route('PIPE-G01',[(-.57+1.14*i/128,gas_y(-.57+1.14*i/128),.105) for i in range(129)],.018,.014)
    main.data.materials.clear();main.data.materials.append(bpy.data.materials['气管'])
    bore(main,cyl('切削',(.44,gas_y(.44),.115),(.44,gas_y(.44),.130),.0031))
    # Existing right-hand accessory becomes the supply coupling, not a return sampler.
    for name,new in [('回气出口-中文','供气接头'),('进气过滤-中文','开放进气')]:
        bpy.data.objects[name].data.body=new
    bpy.data.objects['气管取样支路-回气出口']['purpose']='clean_air_supply'
    plate('正常排气','常开排气',(-.54,gas_y(-.54)-.029,.058),.082,.018,.009)
    # Valve branch is a mechanical leak-action demonstration, not a target-gas source.
    xx=-.10;yy=gas_y(xx)
    bore(main,cyl('切削',(xx,yy,.115),(xx,yy,.130),.0031))
    branch=tube('GAS-泄漏支管',(xx,yy,.117),(xx,yy,.154),.005,.003)
    valve=tube('GAS-手动阀',(xx,yy,.154),(xx,yy,.176),.010,.003)
    valve.data.materials.clear();valve.data.materials.append(bpy.data.materials['金'])
    tube('GAS-泄漏排气口',(xx,yy,.176),(xx,yy,.190),.005,.003)
    cyl('GAS-阀杆',(xx,yy-.009,.165),(xx,yy-.020,.165),.0025,'金')
    box('GAS-阀柄',(xx,yy-.021,.165),(.04,.006,.007),'红')
    box('GAS-阀支柱',(xx+.029,yy-.04,.102),(.009,.016,.144),'铝合金')
    box('GAS-阀支脚',(xx+.029,yy-.04,.034),(.027,.036,.008),'铝合金')
    valve_support=box('GAS-阀托',(xx+.017,yy-.020,.154),(.025,.056,.005),'铝合金',0)
    bore(valve_support,cyl('阀托避让切削',(xx,yy,.145),(xx,yy,.165),.0053))
    plate('泄漏说明','手动泄漏演示',(xx+.029,yy-.049,.087),.096,.018,.008)
    for obj in list(bpy.data.objects):
        if obj.name.startswith(('气泵管路-','气管取样支路-')) or obj.name in ['GAS-泄漏支管','GAS-泄漏排气口']:
            obj.data.materials.clear();obj.data.materials.append(bpy.data.materials['气管'])
        for old,new in [('气管取样支路-回气出口','GAS-主供气支路'),('气泵管路-回气出口','GAS-泵供气软管'),
                        ('气泵管路-进气过滤','GAS-泵进气软管'),('回气出口','GAS-供气接头'),('进气过滤','GAS-进气过滤')]:
            if obj.name.startswith(old):obj.name=new+obj.name[len(old):];break
    # Explicit source labels are affixed to existing rack parts, not floating legends.
    bpy.data.objects['显示状态'].data.body='未接入'
    bpy.data.objects['SIM-中文'].data.body='模拟输入 / 隔离'
    bpy.data.objects['CTRL-01-中文'].data.body='节点A 采控'
    bpy.data.objects['CTRL-02-中文'].data.body='节点B 显示'
    plate('电源待核','24V 接入待核',(-.68,-.266,.047),.15,.014,.008)
    for kind in ['MQ4','MQ7','ME2O2','MQ2','FLAME','SHT30']:
        for i in range(1,6):
            name=f'{kind}-{i:02}-板';obj=bpy.data.objects[name]
            if kind=='SHT30':
                # Lift the sensing heads above the fan-frame discharge projection,
                # extending their own columns rather than floating the assembly.
                for part in list(bpy.data.objects):
                    if not part.name.startswith(f'SHT30-{i:02}-'):continue
                    if part.name.endswith('-脚'):continue
                    if part.name.endswith('-支柱'):
                        part.dimensions.z+=.09;part.location.z+=.045
                    elif part.name.endswith('-线束'):
                        for pt in part.data.splines[0].points[:2]:pt.co.z+=.09
                    else:part.location.z+=.09
            obj['measurement_domain']='corridor_environment' if kind!='FLAME' else 'corridor_optical'
            obj['acquisition_state']='NOT_CONNECTED';obj['zone']=f'Z{i}'
            direct={'MQ4':'CTRL-01:PC2/ADC1_IN12','ME2O2':'CTRL-01:PC1/ADC1_IN11','MQ2':'CTRL-01:PB12',
                    'FLAME':'CTRL-01:PB14','SHT30':'CTRL-01:I2C1/0x44'}
            points.append({'id':f'{kind}-{i:02}','zone':f'Z{i}','kind':kind,
                           'measurement':obj['measurement_domain'],'state':'NOT_CONNECTED',
                           'route':direct[kind] if i==1 and kind in direct else f'PENDING:{kind}-{i:02}',
                           'data_source':'REAL_WHEN_CONNECTED'})
    manifest={'status':'DESIGN_CANDIDATE_NOT_COMMISSIONED','points':points,'fsir02_count':5,
              'water_edges':[['储水箱','水泵'],['水泵','敞口供水盒'],['敞口供水盒','重力测量管'],['重力测量管','储水箱']],
              'feed_air_gap_m':.030,'gas_edges':[['环境空气','开放进气'],['开放进气','气泵'],['气泵','弧形气管'],['弧形气管','常开排气'],['弧形气管','手动泄漏阀']],
              'not_verified':['pressure_protection','seals','hydraulics','electrical','firmware_full_channels']}
    assert len(points)==35 and sum(p['kind']=='FSIR02' for p in points)==5
    (out/'demo-topology.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
