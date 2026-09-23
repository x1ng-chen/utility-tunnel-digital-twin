"""Clean-room planned-hardware assembly. SI units; illustrative, not machining CAD."""
import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector,Matrix
R=Path(sys.argv[sys.argv.index('--')+1]);O=R/'_qa_rebuild_20260911/demo-functional-v4';O.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(R/'tools'))
from pump_reference_geometry import build_water,build_air,hollow_route,gas_y
from enclosure_geometry import build_enclosure,set_inspection_view
from demo_reconstruction import rebuild_demo
C=json.loads((R/'model/rebuild-contract-2026-09-10.json').read_text(encoding='utf-8'))
C['unresolved']=['水泵80×40×50mm是否包含接头待复核；气泵其余尺寸为估计','螺纹、管径、密封、流向和气水管路完整贯通待核验','接口电路与围护尚未定版；不可直接加工或通电通水']
bpy.ops.wm.read_factory_settings(use_empty=True)
S=bpy.context.scene;S.unit_settings.system='METRIC';S.unit_settings.scale_length=1;S.world=bpy.data.worlds.new('展示环境')
registry=[]
def mat(n,c,metal=0):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);m.use_nodes=True;p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(*c,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=.38;return m
M={k:mat(k,c,me) for k,c,me in [('铝合金',(.46,.53,.58),.7),('深灰',(.035,.055,.07),.2),('浅灰',(.75,.79,.8),.1),('绿板',(.03,.25,.16),.1),('蓝板',(.015,.23,.36),.1),('水管',(.025,.43,.53),.3),('气管',(.65,.34,.09),.35),('白',(.93,.94,.92),0),('黑',(.012,.019,.027),0),('红',(.65,.035,.025),.1),('金',(.72,.49,.12),.6)]}
font=bpy.data.fonts.load('C:/Windows/Fonts/msyh.ttc')
def finish(o,n,m):
 o.name=n;o.data.materials.append(M[m]);return o
def box(n,p,d,m='深灰',b=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=finish(bpy.context.object,n,m);o.dimensions=d;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if b:
  md=o.modifiers.new('圆角','BEVEL');md.width=b;md.segments=3;md=o.modifiers.new('加权法线','WEIGHTED_NORMAL')
 return o
def cyl(n,a,b,r,m='铝合金',vertices=48):
 a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=(b-a).length,location=(a+b)/2);o=finish(bpy.context.object,n,m);o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
 for p in o.data.polygons:p.use_smooth=True
 return o
def line(n,pts,r=.001,m='黑'):
 c=bpy.data.curves.new(n,'CURVE');c.dimensions='3D';c.bevel_depth=r;c.bevel_resolution=3;c.use_fill_caps=True;s=c.splines.new('POLY');s.points.add(len(pts)-1)
 for p,v in zip(s.points,pts):p.co=(*v,1)
 o=bpy.data.objects.new(n,c);bpy.context.collection.objects.link(o);o.data.materials.append(M[m]);return o
def text(n,t,p,size=.008,front=True):
 c=bpy.data.curves.new(n,'FONT');c.body=t;c.font=font;c.size=size;c.align_x='CENTER';c.align_y='CENTER';c.extrude=0
 o=bpy.data.objects.new(n,c);bpy.context.collection.objects.link(o);o.location=p
 if front:o.rotation_euler=(math.pi/2,0,0)
 o.data.materials.append(M['黑']);return o
def plate(n,t,p,w=.054,h=.013,size=.008,front=True):
 x,y,z=p
 box(n+'-铭牌',p,(w,.001,h) if front else (w,h,.001),'白',.0005)
 text(n+'-中文',t,(x,y-.0006,z) if front else (x,y,z+.0006),size,front)
def asset(kind,n,o,status='计划配置／接口待核验'):
 registry.append({'kind':kind,'id':n,'object':o.name,'status':status});o['asset_id']=n;o['planned_type']=kind;o['state']=status
def annulus(n,rx,ry,ix,iy,z,h,m):
 vs=[];fs=[];N=160
 for zz in [z,z+h]:
  for xx,yy in [(rx,ry),(ix,iy)]:
   vs.extend([(xx*math.cos(i*2*math.pi/N),yy*math.sin(i*2*math.pi/N),zz) for i in range(N)])
 for i in range(N):
  j=(i+1)%N
  fs.extend([(i,j,N+j,N+i),(2*N+i,3*N+i,3*N+j,2*N+j),(i,2*N+i,2*N+j,j),(N+i,N+j,3*N+j,3*N+i)])
 me=bpy.data.meshes.new(n);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(n,me);bpy.context.collection.objects.link(o);o.data.materials.append(M[m]);return o
annulus('环形承重底座',.90,.60,.422,.172,0,.03,'浅灰')
for a in range(0,360,45):
 t=math.radians(a);x,y=.79*math.cos(t),.50*math.sin(t)
 box(f'立柱脚-{a}',(x,y,.035),(.04,.04,.01),'铝合金');box(f'立柱-{a}',(x,y,.215),(.016,.016,.36),'铝合金')
line('顶框',[(.79*math.cos(i*2*math.pi/160),.50*math.sin(i*2*math.pi/160),.395) for i in range(161)],.009,'铝合金')
line('内沿护边',[(.43*math.cos(i*2*math.pi/160),.18*math.sin(i*2*math.pi/160),.036) for i in range(161)],.005,'深灰')
# Thirty individually mounted sensors, equal arc-length spacing around rear semicircle.
types=[('MQ4','甲烷'),('MQ7','一氧化碳'),('ME2O2','氧气'),('MQ2','烟雾'),('FLAME','火焰'),('SHT30','温湿度')]
samples=[Vector((.74*math.cos(a*math.pi/1000),.445*math.sin(a*math.pi/1000),0)) for a in range(1001)]
dist=[0]
for a,b in zip(samples,samples[1:]):dist.append(dist[-1]+(b-a).length)
for k in range(30):
 d=(k+.5)*dist[-1]/30;idx=next(j for j,s in enumerate(dist) if s>=d);p=samples[idx];x,y=p.x,p.y;i=k//6+1;kind,title=types[k%6];n=f'{kind}-{i:02}';zz={'MQ4':.31,'MQ7':.21,'ME2O2':.18,'MQ2':.335,'FLAME':.245,'SHT30':.265}[kind]
 before=set(bpy.data.objects)
 box(n+'-脚',(x,y,.034),(.039,.039,.008),'铝合金');box(n+'-支柱',(x,y,(.038+zz)/2),(.008,.012,zz-.038),'铝合金')
 box(n+'-背板',(x,y,zz-.007),(.056,.005,.070),'浅灰')
 for dx in [-.018,.018]:cyl(n+f'-隔柱{dx}',(x+dx,y-.0025,zz-.012),(x+dx,y-.011,zz-.012),.002)
 o=box(n+'-板',(x,y-.012,zz),(.045,.002,.036),'绿板');asset(kind,n,o)
 if kind in ['MQ4','MQ7','MQ2','ME2O2']:
  cyl(n+'-探测罐',(x,y-.013,zz+.002),(x,y-.031,zz+.002),.010,'铝合金')
  for dz in [-.005,0,.005]:box(n+f'-网孔{dz}',(x,y-.0312,zz+.002+dz),(.012,.0004,.001),'深灰',0)
 elif kind=='FLAME':cyl(n+'-红外头',(x,y-.013,zz+.008),(x,y-.029,zz+.008),.005,'黑')
 else:box(n+'-感测芯片',(x,y-.015,zz+.004),(.008,.004,.008),'铝合金')
 box(n+'-插座',(x,y-.017,zz-.012),(.018,.008,.006),'白')
 plate(n,f'{title}{i}',(x,y-.003,zz-.030),.054,.012,.007)
 line(n+'-线束',[(x,y-.017,zz-.014),(x,y-.025,zz-.025),(x,y-.025,.065),(x,y,.065)],.0009,'黑')
 if kind in ['MQ4','MQ7','MQ2']:
  o=box(n+'-加热驱动',(x,y-.008,.085),(.038,.006,.022),'蓝板');asset('MQ_DRIVER',n+'-DRV',o)
  box(n+'-驱动背座',(x,y,.085),(.042,.010,.026),'浅灰')
 bpy.context.view_layer.update()
 rotation=Matrix.Translation(p)@Matrix.Rotation(math.atan2(-x,y),4,'Z')@Matrix.Translation(-p)
 for obj in set(bpy.data.objects)-before:obj.matrix_world=rotation@obj.matrix_world
# Single continuous planned LED strip along rear roof, one stock item.
pts=[(.72*math.cos(math.radians(a)),.45*math.sin(math.radians(a)),.387) for a in range(10,171,2)]
o=line('LED-STRIP',pts,.003,'白');asset('LED_STRIP','LED-STRIP',o)
for a in range(15,170,10):
 t=math.radians(a);box(f'LED-{a}',(.72*math.cos(t),.45*math.sin(t),.384),(.006,.006,.004),'金')
# Two ventilators on rigid stands, open rotors plus protective rings.
for i,x in enumerate([-.56,.56],1):
 y=.12;z=.275;n=f'FAN-{i:02}'
 o=box(n+'-下框',(x,y,z-.054),(.12,.025,.012),'深灰');asset('FAN120',n,o)
 box(n+'-上框',(x,y,z+.054),(.12,.025,.012),'深灰')
 for dx in [-.054,.054]:box(n+f'-边框{dx}',(x+dx,y,z),(.012,.025,.108),'深灰')
 for dx in [-.043,.043]:
  box(n+f'-足{dx}',(x+dx,y,.035),(.03,.04,.01),'铝合金');box(n+f'-支腿{dx}',(x+dx,y,.131),(.009,.018,.192),'铝合金')
 cyl(n+'-电机',(x,y-.008,z),(x,y+.009,z),.014,'深灰')
 for a in range(0,360,60):
  t=math.radians(a);o=box(n+f'-叶片{a}',(x+.029*math.sin(t),y,z+.029*math.cos(t)),(.02,.007,.042),'深灰',.004);o.rotation_euler[1]=t
 for rr in [.022,.035,.049]:line(n+f'-护网{rr}',[(x+rr*math.cos(a*math.pi/32),y-.016,z+rr*math.sin(a*math.pi/32)) for a in range(65)],.0009,'铝合金')
 for dx,dz in [(1,0),(0,1)]:line(n+f'-护网撑{dx}',[(x-.054*dx,y-.016,z-.054*dz),(x+.054*dx,y-.016,z+.054*dz)],.001,'铝合金')
 plate(n,'进气风机' if i==1 else '排气风机',(x,y-.014,z-.054),.072,.01,.007)
 o=box(n+'-接口',(x,y-.012,.17),(.05,.004,.028),'蓝板');asset('FAN_INTERFACE',n+'-PWM-TACH',o)
 line(n+'-四线束',[(x,y,.26),(x+.045,y,.21),(x,y-.015,.18)],.002,'黑')
# Dry control rack on left and supplementary rack on right.
for side,x in [('A',-.68),('B',.68)]:
 y=-.10;box('电控架'+side,(x,y,.19),(.235,.009,.30),'浅灰')
 for dx in [-.095,.095]:box('电控架脚'+side+str(dx),(x+dx,y,.035),(.025,.05,.01),'铝合金');box('电控架柱'+side+str(dx),(x+dx,y,.185),(.009,.018,.30),'铝合金')
def module(kind,n,title,x,y,z,w=.063,h=.04):
 box(n+'-支座',(x,y+.003,z),(w+.006,.01,h+.008),'深灰')
 o=box(n,(x,y-.003,z),(w,.002,h),'绿板');asset(kind,n,o)
 box(n+'-芯片',(x,y-.007,z),(.018,.006,.018),'黑')
 box(n+'-端子',(x,y-.009,z-h/2+.004),(w*.7,.01,.006),'金')
 plate(n,title,(x,y-.009,z+h/2+.012),w+.015,.012,.007)
 return o
for idx,x in enumerate([-.736,-.624],1):
 module('STM32',f'CTRL-{idx:02}',f'主控 {idx}',x,-.114,.267,.079,.042)
 module('ESP8266',f'NET-{idx:02}',f'无线 {idx}',x,-.114,.196,.035,.024)
module('TFT','TFT-01','本地显示',-.736,-.114,.12,.051,.039)
box('TFT-01-屏幕',(-.736,-.123,.12),(.034,.002,.028),'黑')
text('显示状态','计划装配',(-.736,-.1245,.12),.004)
module('RELAY','RELAY-01','继电器',-.624,-.114,.12,.05,.03)
module('BUZZER','BUZZ-01','蜂鸣器',-.624,-.114,.06,.03,.021)
cyl('蜂鸣头',(-.624,-.12,.06),(-.624,-.135,.06),.009,'黑')
aux=[('ADC_CONDITIONING','ADC','模拟调理',.624,.27),('I2C_MUX','MUX','温湿度复用',.736,.27),('INTERFACE','IF-01','主接口板',.624,.195),('INTERFACE','IF-02','备用接口板',.736,.195),('INA219','CURRENT','风机电流',.624,.12),('VOICE','VOICE','语音模块',.736,.12),('SIMULATOR','SIM','隔离模拟盒',.624,.06),('K210','K210','视觉模块',.736,.06)]
for kind,n,title,x,z in aux:module(kind,n,title,x,-.114,z,.061,.033)
# Power compartment safely elevated on left rack bottom/outer side.
o=box('POWER-SET',(-.68,-.21,.071),(.205,.11,.08),'深灰',.004);asset('POWER_SET','POWER-SET',o)
plate('POWER','12V / 5V / 3.3V',(-.68,-.266,.075),.18,.018,.009)
for x in [-.73,-.68,-.63]:box('电源脚'+str(x),(x,-.21,.035),(.02,.06,.01),'铝合金')
cyl('急停底',(-.60,-.235,.11),(-.60,-.235,.123),.014,'金');cyl('急停按钮',(-.60,-.235,.123),(-.60,-.235,.132),.012,'红')
# Tray and isolated, dry hydraulic design. No water surface or live-power connection.
o=box('TRAY-01',(0,-.355,.034),(.99,.21,.008),'浅灰');asset('TRAY','TRAY-01',o)
for y in [-.455,-.255]:box('托盘边'+str(y),(0,y,.055),(.99,.009,.05),'浅灰')
for x in [-.49,.49]:box('托盘端'+str(x),(x,-.355,.055),(.009,.20,.05),'浅灰')
def tube(n,a,b,outer=.012,inner=.009):
 a,b=Vector(a),Vector(b);q=(b-a).to_track_quat('Z','Y');length=(b-a).length;vs=[];fs=[];N=48
 for z in [0,length]:
  for r in [outer,inner]:vs.extend([tuple(a+q@Vector((r*math.cos(i*2*math.pi/N),r*math.sin(i*2*math.pi/N),z))) for i in range(N)])
 for i in range(N):
  j=(i+1)%N;fs.extend([(i,j,2*N+j,2*N+i),(N+i,3*N+i,3*N+j,N+j),(i,N+i,N+j,j),(2*N+i,2*N+j,3*N+j,3*N+i)])
 me=bpy.data.meshes.new(n);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(n,me);bpy.context.collection.objects.link(o);o.data.materials.append(M['水管'])
 for f in me.polygons:f.use_smooth=f.index%4<2
 return o
pipeL=tube('WATER-INTAKE',(-.43,-.36,.115),(.02,-.36,.115))
pipeR=tube('WATER-OUTLET',(.19,-.36,.115),(.43,-.36,.115))
pts=[(.43,-.36,.115)]
pts += [(.43+.03*math.sin(i*math.pi/32),-.39+.03*math.cos(i*math.pi/32),.115) for i in range(1,33)]
pts += [(-.43,-.42,.115)]
pts += [(-.43-.03*math.sin(i*math.pi/32),-.39-.03*math.cos(i*math.pi/32),.115) for i in range(1,33)]
pipeReturn=hollow_route('WATER-RETURN',pts,.012,.009)
for x in [-.40,-.23,0,.23,.40]:
 support=box('管托'+str(x),(x,-.39,.072),(.018,.09,.074),'铝合金',0)
 for yy in [-.36,-.42]:
  cutter=cyl('鞍座切削',(x-.02,yy,.115),(x+.02,yy,.115),.0121)
  bpy.context.view_layer.objects.active=support;md=support.modifiers.new('鞍座','BOOLEAN');md.operation='DIFFERENCE';md.object=cutter;bpy.ops.object.modifier_apply(modifier=md.name);bpy.data.objects.remove(cutter,do_unlink=True)
for i,(x,title) in enumerate(zip([-.40,-.23,-.07,.23,.40],['排水段','吸水段','泵入口','阀后段','回水段']),1):
 n=f'LEVEL-L{i:02}';pipe=pipeReturn if i==5 else (pipeL if x<0 else pipeR);yy=-.42 if i==5 else -.36
 beforeLevel=set(bpy.data.objects)
 cutter=cyl('cut',(x,yy,.11),(x,yy,.145),.005,'深灰')
 bpy.context.view_layer.objects.active=pipe;md=pipe.modifiers.new('测点孔','BOOLEAN');md.operation='DIFFERENCE';md.object=cutter;bpy.ops.object.modifier_apply(modifier=md.name);bpy.data.objects.remove(cutter,do_unlink=True)
 tube(n+'-测点座',(x,-.36,.12),(x,-.36,.142),.009,.005)
 o=cyl(n+'-探头',(x,-.36,.118),(x,-.36,.156),.0045,'白');asset('FSIR02',n,o)
 cyl(n+'-光学端',(x,-.36,.112),(x,-.36,.119),.004,'蓝板')
 box(n+'-板卡架',(x,-.237,.123),(.01,.018,.176),'铝合金');box(n+'-架脚',(x,-.237,.034),(.04,.028,.008),'铝合金')
 box(n+'-板卡',(x,-.24,.213),(.0386,.0221,.002),'蓝板');box(n+'-板卡承台',(x,-.237,.209),(.045,.027,.006),'深灰')
 box(n+'-插座',(x,-.249,.217),(.018,.008,.007),'白')
 line(n+'-探头线',[(x,-.36,.156),(x,-.36,.182),(x,-.249,.217)],.0013,'黑')
 plate(n,title,(x,-.237,.205),.067,.014,.008)
 plate(n+'号',f'L{i:02}',(x,-.36,.159),.021,.012,.006,False)
 if i==5:
  for obj in set(bpy.data.objects)-beforeLevel:
   if any(s in obj.name for s in ['测点座','探头','光学端','号']):obj.location.y-=.06
  wire=bpy.data.objects[n+'-探头线'];wire.location.y=0
  wire.data.splines[0].points[0].co.y=yy;wire.data.splines[0].points[1].co.y=yy
# Pump is an unpowered design component; no invented live 24V wiring.
build_water(box,cyl,tube,line,plate,asset)
valve=tube('截止阀',(.142,-.36,.115),(.19,-.36,.115),.017,.006);valve.data.materials.clear();valve.data.materials.append(M['金'])
cyl('阀杆',(.165,-.36,.131),(.165,-.36,.141),.003,'金');box('阀柄',(.165,-.36,.143),(.042,.008,.008),'红')
adaptor=tube('接口占位-水泵入口',(.02,-.36,.115),(.03,-.36,.115),.014,.006)
adaptor['spec_status']='待实测螺纹及密封';adaptor.data.materials.clear();adaptor.data.materials.append(M['金'])
tube('接口占位-入口内螺纹套',(.03,-.36,.115),(.04,-.36,.115),.014,.0102)
# Two wet alarms and independent float, attached to tray.
for i,x in enumerate([-.46,.46],1):
 o=box(f'LEAK-{i}',(x,-.32,.046),(.021,.025,.012),'蓝板');asset('LEAK',f'LEAK-{i}',o)
o=cyl('FLOAT-01',(.45,-.43,.045),(.45,-.43,.077),.015,'白');asset('FLOAT','FLOAT-01',o)
box('浮球固定桥',(.45,-.439,.075),(.014,.032,.004),'铝合金')
# Closed demonstration gas conduit, separate from wet circuit.
gaspoints=[(-.57+1.14*i/128,gas_y(-.57+1.14*i/128),.105) for i in range(129)]
o=hollow_route('PIPE-G01',gaspoints,.018,.014);o.data.materials.clear();o.data.materials.append(M['气管'])
o['design']='环廊弧形气管；外径36mm/内径28mm为布局占位，非加工规格'
for x in [-.54,-.27,0,.27,.54]:
 yy=gas_y(x)
 support=box('气管支座'+str(x),(x,yy,.0585),(.035,.055,.057),'铝合金',0)
 box('气管支座底脚'+str(x),(x,yy,.034),(.055,.065,.008),'铝合金')
for index in [0,-1]:
 p=Vector(gaspoints[index]);other=Vector(gaspoints[1 if index==0 else -2]);t=(p-other).normalized()
 cyl('气管封帽'+str(index),p,p+t*.004,.019,'金')
# Planned heater on its own insulated, floor-mounted base.
box('加热隔热座',(-.32,.18,.042),(.06,.03,.024),'白');o=box('HEATER',(-.32,.18,.056),(.05,.025,.004),'深灰');asset('HEATER','HEATER',o)
# Actual door and magnet, not another generic sensor stack.
door=box('检修门',(-.79,-.07,.175),(.008,.14,.23),'浅灰');box('门脚',(-.79,-.07,.044),(.03,.17,.028),'铝合金')
o=box('门磁',(-.783,-.025,.25),(.014,.025,.018),'白');asset('DOOR_CONTACT','DOOR-01',o)
box('门磁对磁',(-.783,.002,.25),(.014,.018,.018),'白');cyl('门铰',(-.79,-.135,.06),(-.79,-.135,.29),.006,'铝合金')
# Planned air pump from project gas-circuit record. Not identified with DCP-3620.
build_air(box,cyl,tube,line,plate,asset)
rebuild_demo(box,cyl,tube,line,plate,asset,registry,O)
# Traceable plan plate, supported on front floor lip rather than floating legend.
plate('总说明','计划装配 / 未投运',(0,-.50,.043),.27,.03,.015,False)
build_enclosure(M['浅灰'])
# Passive roof openings; no claim that these form tested fan ducts.
for i,xx in enumerate([-.56,.56]):
 cut=cyl('通风口切削',(xx,.12,.399),(xx,.12,.425),.059)
 for roof in list(bpy.data.objects):
  if roof.name.startswith('围护-屋面-'):
   bpy.context.view_layer.objects.active=roof;md=roof.modifiers.new('屋面通风口','BOOLEAN');md.operation='DIFFERENCE';md.object=cut;bpy.ops.object.modifier_apply(modifier=md.name)
 bpy.data.objects.remove(cut,do_unlink=True)
 ring=tube(f'屋面通风附件-口圈-{i}',(xx,.12,.410),(xx,.12,.416),.064,.059)
 for dy in [-.04,-.02,0,.02,.04]:
  w=2*math.sqrt(.059**2-dy**2)
  box(f'屋面通风附件-格栅-{i}-{dy}',(xx,.12+dy,.414),(w,.002,.002),'铝合金',.0003)
# Opening for the existing access-door assembly; clear aperture is a design proposal.
cut=box('围护门洞切削',(-.88,-.07,.175),(.10,.15,.232),'深灰',0)
for wall in list(bpy.data.objects):
 if wall.name.startswith('围护-外墙-'):
  bpy.context.view_layer.objects.active=wall;md=wall.modifiers.new('检修开口','BOOLEAN');md.operation='DIFFERENCE';md.object=cut;bpy.ops.object.modifier_apply(modifier=md.name)
bpy.data.objects.remove(cut,do_unlink=True)
for n in ['检修门','门脚','门磁','门磁对磁','门铰']:
 bpy.data.objects[n].location.x-=.094
# Frame depth bridges the curved skin to the flat door.
for yy in [-.146,.006]:box('门框立边'+str(yy),(-.882,yy,.175),(.035,.008,.244),'铝合金')
for zz in [.055,.295]:box('门框横边'+str(zz),(-.882,-.07,zz),(.035,.16,.008),'铝合金')
# Convert all visible geometry for portable GLB; preserve Chinese mesh labels.
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
 if o.type in {'MESH','CURVE','FONT'}:o.select_set(True)
bpy.context.view_layer.objects.active=next(o for o in bpy.context.selected_objects if o.type=='MESH');bpy.ops.object.convert(target='MESH')
counts={k:sum(a['kind']==k for a in registry) for k in C['sensorCounts']|C['equipmentCounts']}
assert counts==C['sensorCounts']|C['equipmentCounts'],counts
S.render.engine='BLENDER_WORKBENCH';S.display.shading.light='STUDIO';S.display.shading.color_type='MATERIAL';S.display.shading.show_shadows=True;S.display.shading.show_cavity=True;S.display.shading.cavity_type='BOTH';S.display.shading.background_type='WORLD';S.world.color=(.82,.82,.82);S.view_settings.view_transform='Standard'
S.render.resolution_x=1600;S.render.resolution_y=1100;S.render.resolution_percentage=100
bpy.ops.object.camera_add();cam=bpy.context.object;cam.name='审查相机';cam.data.type='ORTHO';S.camera=cam
views={'hero':((1.4,-2,1.5),(0,0,.14),2.1),'front':((0,-3,.3),(0,0,.2),1.9),'back':((0,3,.3),(0,0,.2),1.9),'left':((-3,0,.3),(0,0,.2),1.4),'right':((3,0,.3),(0,0,.2),1.4),'top':((0,0,3),(0,0,0),1.9),'station':((0,-1,.65),(0,.385,.19),.35),'water':((0,-1,.75),(0,-.33,.12),1.15),'controls':((-.68,-1,.6),(-.68,-.1,.2),.4)}
views.update({'water-pump':((.20,-.60,.36),(.075,-.36,.115),.20),'air-pump':((.47,-.10,.50),(.33,.19,.10),.30),'gas':((.85,-.7,1.1),(0,.26,.105),1.32)})
views.update({'probe':((-.10,-.62,.35),(0,-.404,.222),.18),'feed-gap':((.62,-.65,.48),(.45,-.38,.265),.22),'leak-valve':((-.24,.06,.38),(-.10,.31,.14),.25)})
for tag,(p,target,scale) in views.items():
 set_inspection_view(True)
 cam.location=p;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale;S.render.filepath=str(O/f'{tag}.png');bpy.ops.render.render(write_still=True)
p,target,scale=views['hero'];cam.location=p;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
set_inspection_view(False);S.render.filepath=str(O/'enclosure-full.png');bpy.ops.render.render(write_still=True)
bpy.ops.object.select_all(action='DESELECT')
for o in bpy.data.objects:
 if o.type=='MESH':o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(O/'planned-rebuild.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
set_inspection_view(True)
bpy.ops.wm.save_as_mainfile(filepath=str(O/'planned-rebuild.blend'),compress=True)
(O/'inventory.json').write_text(json.dumps({'counts':counts,'assets':registry,'unresolved':C['unresolved'],'views':views,'status':'AWAITING_VISUAL_REVIEW'},ensure_ascii=False,indent=2),encoding='utf-8')
print('CLEAN_REBUILD_DONE',flush=True)
