"""Photo-informed pump assemblies. Only explicitly supplied dimensions are confirmed."""
import bpy,math
from mathutils import Vector

def gas_y(x):
    """Rearward bowed gas route, metres; 120 mm rise over 1140 mm chord."""
    return .20+.12*(1-(x/.57)**2)

def hollow_route(name,points,outer=.007,inner=.005):
    pts=[Vector(p) for p in points];vs=[];fs=[];N=48
    for j,p in enumerate(pts):
        tangent=(pts[min(j+1,len(pts)-1)]-pts[max(0,j-1)]).normalized()
        # Choose a stable transverse axis also for XY-plane return bends.
        spans=[max(p[k] for p in pts)-min(p[k] for p in pts) for k in range(3)]
        axis=min(range(3),key=lambda k:spans[k]);ref=Vector(tuple(1 if k==axis else 0 for k in range(3)))
        u=(ref-tangent*ref.dot(tangent)).normalized();v=tangent.cross(u).normalized()
        for r in [outer,inner]:
            vs.extend([tuple(p+r*(math.cos(i*2*math.pi/N)*u+math.sin(i*2*math.pi/N)*v)) for i in range(N)])
    for j in range(len(pts)-1):
        a=j*2*N;b=(j+1)*2*N
        for i in range(N):
            k=(i+1)%N;fs.extend([(a+i,a+k,b+k,b+i),(a+N+i,b+N+i,b+N+k,a+N+k)])
    for i in range(N):
        k=(i+1)%N;b=(len(pts)-1)*2*N;fs.extend([(i,N+i,N+k,k),(b+i,b+k,b+N+k,b+N+i)])
    me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update();o=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(o);me.materials.append(bpy.data.materials['水管'])
    for f in me.polygons:f.use_smooth=True
    return o

def build_water(box,cyl,tube,line,plate,asset):
    # 80 x 40 x 50 mm envelope including the modelled ports; inclusion in measurement is unconfirmed.
    o=box('PUMP24',(.052,-.36,.108),(.014,.04,.036),'深灰',.002)
    asset('PUMP24','P-01',o,'DCP-3620；80×40×50mm用户提供；接头/方向待核验')
    cyl('PUMP24-电机',(.059,-.36,.108),(.110,-.36,.108),.017,'深灰',64)
    for y in [-.373,-.347]:
        for z in [.095,.121]:
            cyl(f'PUMP24-螺钉{y}-{z}',(.0439,y,z),(.0455,y,z),.0018,'铝合金')
    for n,a,b in [('PUMP24-水平口',(.030,-.36,.115),(.045,-.36,.115)),('PUMP24-竖直口',(.052,-.36,.124),(.052,-.36,.140))]:
        tube(n,a,b,.0093,.006)
    # Thread ridges illustrate the reference silhouette only, not a specified thread standard.
    for i in range(6):
        x=.032+i*.002
        tube(f'PUMP24-水平螺纹{i}',(x,-.36,.115),(x+.0007,-.36,.115),.010,.0093)
        z=.127+i*.002
        tube(f'PUMP24-竖直螺纹{i}',(.052,-.36,z),(.052,-.36,z+.0007),.010,.0093)
    for obj in bpy.data.objects:
        if obj.name.startswith('PUMP24-') and ('口' in obj.name or '螺纹' in obj.name):
            obj.data.materials.clear();obj.data.materials.append(bpy.data.materials['深灰'])
    box('PUMP-脚',(.077,-.36,.064),(.07,.044,.052),'铝合金')
    box('PUMP-电机垫',(.086,-.36,.092),(.033,.013,.010),'黑')
    plate('PUMP','DCP-3620 水泵',(.077,-.3825,.068),.066,.013,.006)
    # Outlet is re-routed above motor, never through the rear of the motor housing.
    tube('接口占位-顶部内螺纹套',(.052,-.36,.132),(.052,-.36,.142),.013,.0102)
    tube('接口占位-顶部缩径',(.052,-.36,.142),(.052,-.36,.150),.013,.006)
    pts=[(.052,-.36,.150),(.052,-.36,.162)]
    pts += [(.064-.012*math.cos(i*math.pi/24),-.36,.162+.012*math.sin(i*math.pi/24)) for i in range(1,13)]
    pts += [(.118,-.36,.174)]
    pts += [(.118+.012*math.sin(i*math.pi/24),-.36,.162+.012*math.cos(i*math.pi/24)) for i in range(1,13)]
    pts += [(.130,-.36,.127)]
    pts += [(.142-.012*math.cos(i*math.pi/24),-.36,.127-.012*math.sin(i*math.pi/24)) for i in range(1,13)]
    hollow_route('WATER-连续泵出口',pts,.008,.006)
    tube('卡箍-泵出口',(.052,-.36,.152),(.052,-.36,.157),.009,.008)
    line('PUMP24-断电线',[(.109,-.352,.103),(.119,-.341,.102),(.116,-.316,.095)],.0015,'黑')

def build_air(box,cyl,tube,line,plate,asset):
    # Grey rectangular head and upright silver motor from supplied photographs.
    # Head face 40.5 mm; nozzle OD 6.6 mm. Other dimensions are proportional estimates.
    x,y=.33,.190
    box('AIR-PUMP-BASE',(x,y,.036),(.066,.072,.012),'铝合金')
    o=box('AIR-PUMP',(x,y-.016,.06225),(.0405,.024,.0405),'浅灰',.0015)
    asset('AIR_PUMP','AIR-PUMP-01',o,'DC24V气泵；泵头40.5mm与管嘴6.6mm据图；其他尺寸估计')
    cyl('AIR-PUMP-电机座',(x,y+.008,.043),(x,y+.008,.079),.018,'浅灰',64)
    cyl('AIR-PUMP-银色电机',(x,y+.008,.079),(x,y+.008,.112),.018,'铝合金',64)
    cyl('AIR-PUMP-端盖',(x,y+.008,.111),(x,y+.008,.114),.0185,'铝合金',64)
    cyl('AIR-PUMP-轴承',(x,y+.008,.114),(x,y+.008,.117),.005,'铝合金')
    for dx in [-.012,.012]:
        box('AIR-PUMP-插片'+str(dx),(x+dx,y+.008,.117),(.003,.0008,.008),'金',.0003)
    for dx in [-.016,.016]:
        for zz in [.047,.077]:cyl(f'AIR-PUMP-螺钉{dx}-{zz}',(x+dx,y-.029,zz),(x+dx,y-.027,zz),.002,'铝合金')
    for dx in [-.009,.009]:
        tube('AIR-PUMP-管嘴'+str(dx),(x+dx,y-.016,.0825),(x+dx,y-.016,.0945),.0033,.002)
    for xx,tt,port,zz in [(.25,'进气过滤',x-.009,.170),(.44,'回气出口',x+.009,.185)]:
        direction=1 if xx>port else -1
        pts=[(port,.174,.0945),(port,.174,zz-.008)]
        pts += [(port+direction*.008*(1-math.cos(i*math.pi/24)),.174,zz-.008+.008*math.sin(i*math.pi/24)) for i in range(1,13)]
        pts += [(xx-direction*.008,.174,zz)]
        pts += [(xx-direction*.008+direction*.008*math.sin(i*math.pi/24),.174,zz-.008+.008*math.cos(i*math.pi/24)) for i in range(1,13)]
        pts += [(xx,.174,.150)]
        hollow_route('气泵管路-'+tt,pts,.003,.002)
        tube('气泵套管-'+tt,(port,.174,.089),(port,.174,.099),.0045,.0033)
        box(tt+'座',(xx,.174,.048),(.032,.034,.036),'浅灰')
        body=tube(tt,(xx,.174,.130),(xx,.174,.150),.009,.002);body.data.materials.clear();body.data.materials.append(bpy.data.materials['深灰'])
        box(tt+'支撑',(xx+.012,.174,.099),(.006,.018,.066),'铝合金')
        # A dedicated hollow branch enters the orange pipe through a bored socket.
        yy=gas_y(xx)
        pts=[(xx,yy,.117),(xx,yy,.130)]
        pts += [(xx,yy-.006*(1-math.cos(i*math.pi/24)),.130+.006*math.sin(i*math.pi/24)) for i in range(1,13)]
        pts += [(xx,.180,.136)]
        pts += [(xx,.180-.006*math.sin(i*math.pi/24),.130+.006*math.cos(i*math.pi/24)) for i in range(1,13)]
        hollow_route('气管取样支路-'+tt,pts,.003,.002)
        main=bpy.data.objects['PIPE-G01'];cut=cyl('气管开孔',(xx,yy,.115),(xx,yy,.13),.003)
        bpy.context.view_layer.objects.active=main;md=main.modifiers.new('取样口','BOOLEAN');md.operation='DIFFERENCE';md.object=cut;bpy.ops.object.modifier_apply(modifier=md.name);bpy.data.objects.remove(cut,do_unlink=True)
        plate(tt,tt,(xx,.1565,.051),.030,.012,.0045)
    plate('气泵','DC24V 气泵',(x,y-.0286,.062),.036,.012,.0045)
