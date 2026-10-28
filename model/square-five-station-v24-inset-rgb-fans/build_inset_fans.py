"""Live Blender MCP: two 120 mm inset RGB fans with independent rotor and power lighting."""
import bpy,math,json,hashlib,colorsys,copy
from pathlib import Path
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'sources'/'square-five-station-v23-refined-acrylic'
assert Path(bpy.data.filepath).resolve()==(BASE/(BASE.name+'.blend')).resolve()
ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'previews').mkdir(exist_ok=True)
scene=bpy.context.scene
protected={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [BASE/(BASE.name+'.blend'),BASE/(BASE.name+'.glb')]}
oldassets={o['assetCode']:{'matrix':[list(r) for r in o.matrix_world],'props':dict(o.items())} for o in scene.objects if o.get('assetCode')}
coll=bpy.data.collections.new('10_INSET_RGB_FANS');scene.collection.children.link(coll)
def material(name,color,metal=0,rough=.3):
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    p=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
    mat.diffuse_color=(*color,1);return mat
housing=material('V24 Black fan polymer',(.012,.016,.023),.1,.27)
rubber=material('V24 Fan corner elastomer',(.005,.009,.013),0,.6)
blade_mat=material('V24 Frosted translucent rotor',(.51,.62,.68),.08,.27)
bp=next(n for n in blade_mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bp.inputs['Transmission Weight'].default_value=.15
steel=bpy.data.materials['05 Stainless / visual proxy']
letter=bpy.data.materials['06 Light typography'];glass=bpy.data.materials['Clear removable acrylic / conceptual']

def meshob(name,verts,faces,mat,parent=None,bevel=0,smooth=False):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    ob=bpy.data.objects.new(name,mesh);coll.objects.link(ob);mesh.materials.append(mat)
    if parent:ob.parent=parent;ob.matrix_parent_inverse=Matrix.Identity(4);ob.matrix_basis=Matrix.Identity(4)
    if smooth:
        for p in mesh.polygons:p.use_smooth=True
    if bevel:
        mod=ob.modifiers.new('Moulded edge radius','BEVEL');mod.width=bevel;mod.segments=3
    return ob
def boxmesh(name,dims,mat,parent=None,centre=(0,0,0),bevel=0):
    x,y,z=centre;a,b,c=[v/2 for v in dims]
    verts=[(x+sx*a,y+sy*b,z+sz*c) for sx,sy,sz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
    return meshob(name,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat,parent,bevel)
def ring(name,inner,outer,z0,z1,mat,parent=None,a0=0,a1=2*math.pi,steps=128):
    verts=[]
    for z,r in [(z0,inner),(z0,outer),(z1,inner),(z1,outer)]:
        verts += [(r*math.cos(a0+(a1-a0)*i/steps),r*math.sin(a0+(a1-a0)*i/steps),z) for i in range(steps+1)]
    stride=steps+1;faces=[]
    for i in range(steps):
        j=i+1
        faces += [(i,j,stride+j,stride+i),(2*stride+i,3*stride+i,3*stride+j,2*stride+j),(i,2*stride+i,2*stride+j,j),(stride+i,stride+j,3*stride+j,3*stride+i)]
    faces += [(0,stride,3*stride,2*stride),(steps,2*stride+steps,3*stride+steps,stride+steps)]
    return meshob(name,verts,faces,mat,parent)
def cylinder(name,r,depth,z,mat,parent=None,n=64,x=0,y=0):
    verts=[(x+r*math.cos(2*math.pi*i/n),y+r*math.sin(2*math.pi*i/n),z+side*depth/2) for side in [-1,1] for i in range(n)]
    faces=[tuple(reversed(range(n))),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return meshob(name,verts,faces,mat,parent,bevel=.00025)
def rounded_square(half,radius,steps=16):
    points=[]
    # Uniform polar sampling is essential: corner-only samples would turn
    # the circular throat into four long chords.
    for i in range(steps*12):
        a=2*math.pi*i/(steps*12);dx,dy=math.cos(a),math.sin(a)
        lo,hi=0,half*math.sqrt(2)
        for _ in range(30):
            mid=(lo+hi)/2;qx=abs(mid*dx)-half+radius;qy=abs(mid*dy)-half+radius
            distance=math.hypot(max(qx,0),max(qy,0))+min(max(qx,qy),0)-radius
            if distance>0:hi=mid
            else:lo=mid
        points.append((lo*dx,lo*dy))
    return points
def square_ring(name,half,radius,inner,z0,z1,mat,parent=None):
    outer=rounded_square(half,radius);n=len(outer);innerpts=[(inner*math.cos(math.atan2(y,x)),inner*math.sin(math.atan2(y,x))) for x,y in outer]
    verts=[(x,y,z) for z,ps in [(z0,outer),(z0,innerpts),(z1,outer),(z1,innerpts)] for x,y in ps]
    faces=[]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,2*n+j,2*n+i),(n+i,3*n+i,3*n+j,n+j),(i,n+i,n+j,j),(2*n+i,2*n+j,3*n+j,3*n+i)]
    return meshob(name,verts,faces,mat,parent,bevel=.00045)
def square_bezel(name,half,opening,z0,z1,mat,parent):
    # Four clean strips around the square aperture; no material crosses the rotor.
    a=half;b=opening;verts=[];faces=[]
    for cx,cy,dx,dy in [(0,(a+b)/2,2*a,a-b),(0,-(a+b)/2,2*a,a-b),((a+b)/2,0,a-b,2*b),(-(a+b)/2,0,a-b,2*b)]:
        k=len(verts);verts += [(cx+sx*dx/2,cy+sy*dy/2,z) for z in [z0,z1] for sx,sy in [(-1,-1),(1,-1),(1,1),(-1,1)]]
        faces += [tuple(k+t for t in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]]
    return meshob(name,verts,faces,mat,parent,bevel=.0004)
def choice(owner,prop,wanted):
    valid={i.identifier for i in owner.bl_rna.properties[prop].enum_items};assert wanted in valid,(prop,wanted,valid);return wanted
def apply_mod(ob,mod):
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
    bpy.ops.object.modifier_apply(modifier=mod.name)
def cut(ob,cutter):
    mod=ob.modifiers.new('Inset opening, applied','BOOLEAN');mod.operation=choice(mod,'operation','DIFFERENCE');mod.object=cutter
    apply_mod(ob,mod);bpy.data.objects.remove(cutter,do_unlink=True)

fans=[]
for n,wallname,y,side in [(1,'CLEAR_WALL_TOP',.700,1),(2,'CLEAR_WALL_BOTTOM',.000,-1)]:
    code=f'FAN-{n:02}';old=bpy.data.objects[code];props=dict(old.items())
    for child in list(old.children_recursive):bpy.data.objects.remove(child,do_unlink=True)
    bpy.data.objects.remove(old,do_unlink=True)
    root=bpy.data.objects.new(code,None);coll.objects.link(root)
    # Local X/Y lie in the side plate, +Z points outwards. Front face is flush.
    root.matrix_world=Matrix(((-side,0,0,.35),(0,0,side,y),(0,1,0,.220),(0,0,0,1)))
    for k,v in props.items():root[k]=v
    root['physicalTag']=code;root['dimensionEvidence']='USER_CONFIRMED_120x120MM;25MM_DEPTH_ASSUMED'
    root['frameDimensionsMm']=[120,120,25];root['mounting']='INSET_THROUGH_ACRYLIC_PLATE_FRONT_FLUSH'
    root['wallNode']=wallname;root['openingDimensionsMm']=[120.4,120.4]
    root['clearancePerSideMm']=.2;root['frameDepthEvidence']='25mm visual placeholder; measure the actual fan'
    root['rgbPowerMetric']='supply.voltage';root['rgbIndependentOfRpm']=True
    root['rgbColorEvidence']='Reference-photo rainbow appearance; no addressable lighting channel or color sensor assumed'
    frame=square_ring(code+'_FRAME',.060,.0045,.0555,-.025,0,housing,root)
    # Actual screw bores through fan corners; 105 mm pitch is explicitly a proxy.
    for x in [-.0525,.0525]:
        for u in [-.0525,.0525]:
            cutter=cylinder('TEMP_FAN_SCREW',.00215,.05,-.0125,housing,n=32,x=x,y=u);cutter.matrix_world=root.matrix_world
            cut(frame,cutter)
            cylinder(code+f'_FASTENER_{int(x*1000)}_{int(u*1000)}',.0037,.0025,.001,steel,root,32,x,u)
            pad=boxmesh(code+f'_PAD_{int(x*1000)}_{int(u*1000)}',(.012,.012,.0011),rubber,root,(x,u,-.0006),.0014)
    frame['fanFrameSizeMm']=[120,120,25];frame['mountingPitchEvidence']='105mm illustrative standard-pattern proxy, not verified on user hardware'
    square_bezel(code+'_ACRYLIC_RETAINING_LIP',.064,.0602,-.001,.0005,housing,root)
    # Fixed rear stator and cable strain relief.
    for a in [45,135,225,315]:
        arm=boxmesh(code+f'_STATOR_{a}',(.046,.004,.003),housing,root,(.035,0,-.023))
        arm.rotation_euler.z=math.radians(a)
    cylinder(code+'_STATOR_MOTOR',.019,.005,-.023,housing,root)
    rotor=bpy.data.objects.new(code+'_ROTOR',None);coll.objects.link(rotor);rotor.parent=root;rotor.matrix_parent_inverse=Matrix.Identity(4)
    rotor['nativeSpinAxisLocal']=[0,0,1];rotor['spinAxisLocal']=[0,1,0]
    rotor['animationSource']='FRESH_GOOD_PER_FAN_ROTATIONAL_SPEED_ONLY';rotor['fanAssetCode']=code
    rotor['spinAxisCoordinateSystem']='glTF local, after +Z-native to +Y-glTF export conversion'
    cylinder(code+'_ROTOR_HUB',.0185,.015,-.012,blade_mat,rotor)
    cylinder(code+'_HUB_CAP',.0145,.0012,-.0038,housing,rotor)
    # Seven swept, pitched moulded blades, with clear air gaps.
    for blade in range(7):
        verts=[];rows=16
        for zoffset in [-.00065,.00065]:
            for i in range(rows):
                t=i/(rows-1);r=.018+t*.0342
                centre=math.radians(blade*360/7+5+24*t)
                width=math.radians(26+6*t)
                for edge in [-1,1]:
                    a=centre+edge*width/2;verts.append((r*math.cos(a),r*math.sin(a),-.013+edge*.0025+zoffset))
        stride=rows*2;faces=[]
        for i in range(rows-1):
            k=i*2;j=k+2
            faces += [(k,j,j+1,k+1),(stride+k,stride+k+1,stride+j+1,stride+j),(k,stride+k,stride+j,j),(k+1,j+1,stride+j+1,stride+k+1)]
        faces += [(0,1,stride+1,stride),(stride-2,2*stride-2,2*stride-1,stride-1)]
        meshob(code+f'_ROTOR_BLADE_{blade:02}',verts,faces,blade_mat,rotor,bevel=.00035,smooth=True)
    # The LED/diffuser belongs to the stationary frame, not to the rotor.
    for segment in range(24):
        hue=segment/24;color=colorsys.hsv_to_rgb(hue,.92,.95)
        # Convert display RGB to linear shader values.
        color=tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in color)
        mat=material(code+f' RGB {segment:02}',tuple(v*.14 for v in color),0,.24)
        p=next(node for node in mat.node_tree.nodes if node.type=='BSDF_PRINCIPLED')
        p.inputs['Emission Color'].default_value=(*color,1);p.inputs['Emission Strength'].default_value=0
        mat['fanRgbColor']=list(color);mat['fanRgbOnIntensity']=3.0;mat['fanPowerOnly']=True
        verts=[];faces=[]
        for inner,outer,z0,z1 in [(.0518,.0552,-.0027,-.0010),(.0518,.0552,-.0240,-.0223),(.0162,.0190,-.0018,-.0005)]:
            a0=2*math.pi*(segment+.05)/24;a1=2*math.pi*(segment+.95)/24
            tmp=ring('TEMP_LED',inner,outer,z0,z1,mat,a0=a0,a1=a1,steps=5)
            k=len(verts);verts.extend(tuple(v.co) for v in tmp.data.vertices);faces.extend(tuple(k+i for i in f.vertices) for f in tmp.data.polygons)
            mesh=tmp.data;bpy.data.objects.remove(tmp,do_unlink=True);bpy.data.meshes.remove(mesh)
        led=meshob(code+f'_RGB_SEGMENT_{segment:02}',verts,faces,mat,root)
        led['fanRgb']=True;led['fanAssetCode']=code;led['fanRgbColor']=list(color);led['fanRgbOnIntensity']=3.0
        led['lightingControl']='FRESH_SUPPLY_VOLTAGE_ONLY_INDEPENDENT_OF_TACH'
    # Rebuild this side plate to fill the old circular vent, then cut one square aperture.
    wall=bpy.data.objects[wallname]
    rebuilt=boxmesh('TEMP_NEW_SIDE',(.676,.004,.276),glass)
    olddata=wall.data;wall.data=rebuilt.data;wall.data.name=wallname+'_INSET_MESH';bpy.data.objects.remove(rebuilt,do_unlink=True)
    if olddata.users==0:bpy.data.meshes.remove(olddata)
    cutter=boxmesh('TEMP_INSET_CUTTER',(.1204,.045,.1204),housing,bevel=.0038)
    cutter.matrix_world=Matrix.Translation((.35,.002 if side<0 else .698,.220))
    for mod in list(cutter.modifiers):apply_mod(cutter,mod)
    cut(wall,cutter)
    wall['insetFanNode']=code;wall['openingShape']='ROUNDED_SQUARE';wall['openingWidthMm']=120.4;wall['openingHeightMm']=120.4
    wall['openingCentreWorld_m']=[.35,.002 if side<0 else .698,.220];wall['cutApplied']=True
    # Move only the power/feedback lead for the replacement fan assembly.
    for ob in scene.objects:
        if ob.type=='CURVE' and (ob.name.startswith(code+'_') or ob.name.startswith('FAN_'+str(n)+'_')):
            if any(q in ob.name for q in ['WIRE','CABLE','HARNESS']):ob['geometryRequiresReview']=True
    fans.append({'assetCode':code,'wallNode':wallname,'centreBlender_m':list(root.matrix_world.translation),'outwardAxisBlender':[0,side,0],'frameMm':[120,120,25],'cutoutMm':[120.4,120.4],'openingCentreBlender_m':list(wall['openingCentreWorld_m']),'depthAssumed':True,'rotorNode':rotor.name,'spinAxisGltfLocal':[0,1,0],'rgbNodePrefix':code+'_RGB_SEGMENT_','originalControllerIdPreserved':root['controllerId']})

bpy.context.view_layer.update()
# All non-fan semantic roots and identities, especially sensors/controllers, are protected.
for code,row in oldassets.items():
    if code in ['FAN-01','FAN-02']:continue
    ob=next(o for o in scene.objects if o.get('assetCode')==code)
    assert max(abs(ob.matrix_world[i][j]-row['matrix'][i][j]) for i in range(4) for j in range(4))<1e-6,code
    assert dict(ob.items())==row['props'],code
assert len([o for o in scene.objects if o.get('assetCode')])==69
assert len([o for o in scene.objects if o.get('category')=='external_sensor'])==31
assert protected=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in protected}
for filename in ['asset-map.json','sensor-bindings.json','station-focus.json']:
    data=json.loads((BASE/filename).read_text(encoding='utf-8'));data['revision']=ROOT.name;data['date']='2026-10-29'
    data['provenance']={'sourceRevision':BASE.name,'change':'Two user-confirmed 120x120 mm RGB fans embedded in equal side-plate apertures; separate TACH rotor and power-only lighting. Other asset identities/positions preserved.'}
    if filename=='asset-map.json':
        for row in data['assets']:
            if row['assetCode'] in ['FAN-01','FAN-02']:
                fan=next(p for p in fans if p['assetCode']==row['assetCode']);x,y,z=fan['centreBlender_m']
                row.update({'position_mm':[x*1000,y*1000,z*1000],'positionBlender_m':[x,y,z],'positionGltf_m':[x,z,-y],'physicalTag':row['assetCode'],'dimensionEvidence':'120x120mm user confirmed; depth=25mm placeholder','insetMount':fan,'rgbPowerMetric':'supply.voltage','rgbIndependentOfRpm':True})
    (ROOT/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
contract={'revision':ROOT.name,'date':'2026-10-29','fans':fans,'motion':{'metricKey':'rotational.speed','unit':'rpm','source':'api','quality':'good','requiresFreshBindingAndHeartbeat':True,'nativeAxes':[0,0,1],'gltfLocalAxis':[0,1,0],'visualSpeedCapRpm':90},'lighting':{'metricKey':'supply.voltage','unit':'V','source':'api','quality':'good','independentOfRpm':True,'unknownVoltage':'unknown/dark, never infer power from RPM','colorMode':'Fixed rainbow visual approximation of supplied photo; no RGB control channel or actual color feedback','voltageDisplayPolicy':'Positive measured supply -> on; zero -> off. This is a display rule, not an LED voltage specification.'},'evidence':{'frameXY':'USER_CONFIRMED_120x120MM','frameDepth':'25mm assumed for display','cutoutClearance':'.2mm per side conceptual allowance; verify outer frame, corner radius, tooling and retention before fabrication','screwPitch':'105mm illustrative proxy; measure actual holes','hardware':'User confirms TACH wired and lights follow supply, independent of speed; no physical commands sent by this edit'}}
(ROOT/'fan-animation-contract.json').write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
scene['revision']=ROOT.name;scene['fanLightingRule']='Supply voltage alone controls RGB; RPM only controls rotor motion'
scene['fanDefaultVisualState']='Power unknown: emission off and stationary. Running/lit preview is synthetic only.'
scene.camera=bpy.data.objects['VIEW_REFINED_HERO'];scene.render.filepath=str(ROOT/'previews/overall.png')
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/(ROOT.name+'.blend')),compress=True)
report={'status':'NATIVE_PREPARED','route':'LIVE_BLENDER_MCP','semanticAssets':69,'externalSensors':31,'fans':fans,'sameOpeningDimensions':True,'other67AssetRootsAndIdentitiesUnchanged':True,'protectedInputFiles':protected,'hardwareCommandsSent':False,'realDeviceLinkageVerified':False}
(ROOT/'fan-mount-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'fans':fans,'otherAssetsPreserved':67},ensure_ascii=False))
