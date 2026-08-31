"""V03: fabricable rectangular utility-tunnel demonstrator.

Units are metres.  The annular G01 object is a closed monitored gas pipe in
zone C; it is deliberately independent from the cyan ventilation route.
"""
import bpy, math, os
from mathutils import Vector

ROOT = r"D:\shixi\model"
PRE = os.path.join(ROOT, "previews")
os.makedirs(PRE, exist_ok=True)
BLEND = os.path.join(ROOT, "utility-tunnel-rectangular-v03.blend")
GLB = os.path.join(ROOT, "utility-tunnel-rectangular-v03.glb")
HERO = os.path.join(PRE, "utility-tunnel-rectangular-v03-hero.png")
CUT = os.path.join(PRE, "utility-tunnel-rectangular-v03-functional.png")

scene=bpy.context.scene
scene.unit_settings.system='METRIC'; scene.unit_settings.length_unit='MILLIMETERS'
scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=1400; scene.render.resolution_y=900; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world.color=(0.018,0.028,0.040)

for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
for d in (bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.cameras,bpy.data.lights):
    pass

def mat(name,c,metal=0.0,rough=.4,alpha=1.0,emit=0.0):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name); m.use_nodes=True
    p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    p.inputs['Base Color'].default_value=(*c,1); p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    p.inputs['Alpha'].default_value=alpha
    if 'Emission Color' in p.inputs: p.inputs['Emission Color'].default_value=(*c,1); p.inputs['Emission Strength'].default_value=emit
    if alpha<1:
        m.surface_render_method='DITHERED'
    m.diffuse_color=(*c,alpha)
    return m

M_BASE=mat('MAT_Base',(0.035,.075,.105),.7,.25); M_FLOOR=mat('MAT_Floor',(.075,.14,.18),.35,.34)
M_FRAME=mat('MAT_2020_Aluminum',(.035,.055,.07),.8,.22); M_ACR=mat('MAT_Clear_Acrylic',(.36,.82,.95),0,.18,.12)
M_ORANGE=mat('MAT_G01_Orange',(1.0,.20,.018),.15,.26,1,.12); M_CYAN=mat('MAT_Vent_Cyan',(.02,.62,.76),.2,.25,1,.08)
M_RED=mat('MAT_Alarm_Red',(.95,.025,.015),.1,.25,1,.45); M_GREEN=mat('MAT_Safe_Green',(.03,.72,.27),.15,.28,1,.15)
M_BLUE=mat('MAT_Water_Blue',(.025,.34,.85),.1,.2,.86,.1); M_WHITE=mat('MAT_Label',(.82,.94,1),0,.3,1,.25)
M_DARK=mat('MAT_Enclosure',(.055,.085,.10),.45,.28); M_YELLOW=mat('MAT_Warning',(1,.62,.03),.1,.3,1,.15)

def box(n,loc,dims,m,bev=.005):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=n; o.data.name=n; o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(m)
    if bev:
        b=o.modifiers.new('Edge radius','BEVEL'); b.width=bev; b.segments=3
    return o
def cyl(n,loc,r,depth,m,rot=(0,0,0),verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts,radius=r,depth=depth,location=loc,rotation=rot); o=bpy.context.object; o.name=n; o.data.name=n; o.data.materials.append(m)
    for p in o.data.polygons:p.use_smooth=True
    return o
def curve(n,pts,r,m,cyclic=False):
    cu=bpy.data.curves.new(n,'CURVE'); cu.dimensions='3D'; cu.resolution_u=2; cu.bevel_depth=r; cu.bevel_resolution=4
    sp=cu.splines.new('NURBS'); sp.points.add(len(pts)-1)
    for p,co in zip(sp.points,pts): p.co=(*co,1)
    sp.order_u=min(3,len(pts)); sp.use_endpoint_u=not cyclic; sp.use_cyclic_u=cyclic
    ob=bpy.data.objects.new(n,cu); bpy.context.collection.objects.link(ob); ob.data.materials.append(m); return ob
def text(n,body,loc,scale=.028,m=M_WHITE):
    cu=bpy.data.curves.new(n,'FONT'); cu.body=body; cu.align_x='CENTER'; cu.align_y='CENTER'; cu.size=scale; cu.extrude=.0015
    ob=bpy.data.objects.new(n,cu); bpy.context.collection.objects.link(ob); ob.location=loc; ob.rotation_euler=(math.pi/2,0,0); ob.data.materials.append(m); return ob
def label(n,body,x,z,width=.18):
    # Black placard on the front face so the engineering label stays readable.
    box(n+'_PLATE',(x,-.336,z),(width,.008,.045),M_DARK,.003); text(n,body,(x,-.342,z),.027)
def sensor(n,code,loc,color):
    x,y,z=loc; box(n,(x,y,z),(.105,.07,.07),M_DARK,.008); box(n+'_FACE',(x,y-.038,z),(.078,.006,.042),color,.002)
    cyl(n+'_PORT',(x,y-.044,z),.012,.008,M_WHITE,(math.pi/2,0,0)); text(n+'_TXT',code,(x,y-.05,z+.035),.023,M_WHITE)
    # two stainless support posts make the module visibly separate from G01.
    cyl(n+'_STAND_A',(x-.034,y+.04,z-.065),.006,.11,M_FRAME); cyl(n+'_STAND_B',(x+.034,y+.04,z-.065),.006,.11,M_FRAME)

# Base and manufactured 2020 aluminium frame, 1400 x 650 x 550 mm.
box('BASE_1400x650',(0,0,.015),(1.40,.65,.03),M_BASE,.012); box('FLOOR_PANEL',(0,0,.042),(1.34,.59,.022),M_FLOOR,.004)
for x in (-.69,.69,-.235,.235):
    for y in (-.315,.315): cyl('FRAME_VERTICAL', (x,y,.285), .012,.51, M_FRAME)
for z in (.06,.53):
    for y in (-.315,.315): box('FRAME_LONG', (0,y,z),(1.40,.024,.024),M_FRAME,.003)
    for x in (-.69,.69): box('FRAME_SHORT',(x,0,z),(.024,.65,.024),M_FRAME,.003)
for x in (-.235,.235):
    box('FRAME_DIVIDER_TOP',(x,0,.53),(.024,.65,.024),M_FRAME,.003)

# Acrylic shell: the front is a transparent, removable facade with real seams.
for i,(cx,w) in enumerate(((-.462,.43),(0,.43),(.462,.43))):
    box('ACRYLIC_FRONT_PANEL_'+str(i),(cx,-.326,.29),(w,.006,.46),M_ACR,.002)
    box('ACRYLIC_BACK_PANEL_'+str(i),(cx,.326,.29),(w,.006,.46),M_ACR,.002)
    box('ACRYLIC_ROOF_PANEL_'+str(i),(cx,0,.545),(w,.62,.006),M_ACR,.002)
for x in (-.702,.702): box('ACRYLIC_END_PANEL',(x,0,.29),(.006,.62,.46),M_ACR,.002)

# A zone: service door / low-voltage control and environment node.
box('DOOR_01_SERVICE_PANEL',(-.58,-.333,.29),(.20,.012,.34),M_DARK,.006)
box('DOOR_01_WINDOW',(-.58,-.341,.33),(.13,.006,.15),M_ACR,.002)
cyl('DOOR_01_HANDLE',(-.505,-.35,.25),.012,.055,M_FRAME,(math.pi/2,0,0)); cyl('DOOR_MAG_01',(-.665,-.34,.40),.008,.016,M_RED,(math.pi/2,0,0))
box('CTRL_01_LOW_VOLT',(-.38,.10,.18),(.20,.20,.22),M_DARK,.012); box('CTRL_01_SCREEN',(-.38,-.006,.21),(.10,.008,.065),M_CYAN,.002)
cyl('ESTOP_01',(-.38,-.02,.105),.028,.018,M_RED,(math.pi/2,0,0)); box('NET_01',(-.38,.10,.335),(.12,.10,.035),M_GREEN,.004)
sensor('ENV_01','ENV',(-.14,.12,.20),M_CYAN); sensor('TEMP_A','T-A',(-.14,.12,.34),M_YELLOW)
label('LABEL_A','A  CONTROL',-.46,.485,.22)

# B zone: an isolated raised water tray and vertical drip line, partitioned from electronics.
box('B_WATER_PARTITION_L',(-.235,0,.29),(.008,.60,.43),M_ACR,.002); box('B_WATER_PARTITION_R',(.235,0,.29),(.008,.60,.43),M_ACR,.002)
box('LEAK_W01_RAISED_TRAY',(0,0,.105),(.32,.42,.10),M_DARK,.012); box('LEAK_W01_WATER',(0,0,.158),(.27,.36,.012),M_BLUE,.003)
for x in (-.135,.135):
    for y in (-.18,.18): cyl('TRAY_RAISED_LIP',(x,y,.19),.012,.065,M_FRAME)
curve('SEEP_W01_DRIP_LINE',[(0,.04,.47),(0,.04,.30),(0,.04,.20)],.008,M_CYAN)
cyl('SEEP_W01_NOZZLE',(0,.04,.47),.018,.04,M_CYAN); cyl('HILEVEL_W01_FLOAT',(.115,0,.205),.018,.055,M_RED)
# The water function is intentionally a one-way classroom demonstration:
# nozzle -> visible droplets -> raised isolated tray -> leak/high-level probes.
for i,z in enumerate((.405,.345,.275)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=.013-(i*.002), location=(0,.04,z))
    drop=bpy.context.object; drop.name='SEEP_W01_VISIBLE_DROP_'+str(i+1); drop.data.materials.append(M_BLUE)
box('LEAK_W01_MANUAL_DRAIN_CAP',(0,-.218,.12),(.050,.018,.040),M_BLUE,.004)
sensor('LEAK_W01_PROBE','LEAK',(-.095,-.06,.205),M_CYAN)
text('WATER_FLOW','DRIP  ↓  TRAY  →  LEVEL ALARM',(0,-.352,.085),.016,M_WHITE)
sensor('TEMP_B','T-B',(-.15,.16,.39),M_YELLOW); label('LABEL_B','B  WATER',0,.485,.20)

# C zone: one and only one closed orange monitored ring G01. It is in the X/Z plane.
cx=.455; cy=.02; cz=.285; rx=.175; rz=.165
pts=[]
for i in range(49):
    a=2*math.pi*i/48; pts.append((cx+rx*math.cos(a),cy,cz+rz*math.sin(a)))
curve('PIPE_G01_SEALED_ANNULAR',pts,.018,M_ORANGE,True)
# supports beneath the pipe so it cannot read as floating.
for x in (.33,.58):
    cyl('PIPE_G01_SUPPORT',(x,.02,.125),.010,.18,M_FRAME); box('PIPE_G01_CLAMP',(x,.02,.19),(.045,.065,.014),M_FRAME,.004)
# pre-set leak point is a red collar, deliberately not a gas opening.
cyl('LEAK_G01_SIM_COLLAR',(.63,.02,.285),.032,.04,M_RED,(0,math.pi/2,0)); box('LEAK_G01_SIGNAL_BOX',(.63,.11,.285),(.06,.055,.07),M_RED,.005)
# High/mid/low sensor sampling positions are called out directly on the front.
sensor('GAS_CH4_01','CH4',(.455,-.14,.465),M_ORANGE)
sensor('GAS_CO_01','CO',(.61,-.14,.285),M_RED)
sensor('GAS_O2_01','O2',(.455,-.14,.105),M_CYAN)
sensor('SMOKE_01','SMK',(.29,.13,.445),M_GREEN); sensor('TEMP_C','T-C',(.30,.13,.28),M_YELLOW)
# Safe real airflow is NOT inside orange G01.  Ambient air enters through an
# external filtered intake, passes a separate sampling manifold, then leaves
# through the fan and roof exhaust.  Toxic gases are never introduced.
box('AIR_IN_01_FILTER',(.67,-.02,.40),(.055,.075,.075),M_CYAN,.006)
cyl('AIR_IN_01_PORT',(.708,-.02,.40),.026,.04,M_CYAN,(0,math.pi/2,0))
box('GAS_01_SAMPLE_MANIFOLD',(.35,.12,.40),(.15,.09,.09),M_DARK,.008)
curve('AIR_IN_01_SAFE_ROUTE',[(.70,-.02,.40),(.60,.04,.40),(.50,.10,.40),(.43,.12,.40)],.014,M_CYAN)
curve('SAMPLE_TO_FAN_ROUTE',[(.43,.12,.40),(.54,.16,.40),(.57,.16,.40)],.014,M_CYAN)
# Direction arrows make the inlet -> sensing chamber -> fan -> roof route legible.
for i,(x,y,z) in enumerate(((.60,.04,.40),(.48,.11,.40),(.61,.19,.47))):
    bpy.ops.mesh.primitive_cone_add(vertices=20, radius1=.020, depth=.045, location=(x,y,z), rotation=(0,math.pi/2 if i<2 else 0,0))
    arrow=bpy.context.object; arrow.name='AIRFLOW_ARROW_'+str(i+1); arrow.data.materials.append(M_CYAN)
text('AIR_IN_LABEL','AIR IN',(.63,-.352,.44),.016,M_WHITE)
text('AIR_OUT_LABEL','ROOF OUT',(.58,-.352,.50),.016,M_WHITE)
# Independent cyan ventilation and fan route, intentionally above and behind G01.
cyl('FAN_01',(.61,.16,.39),.065,.06,M_CYAN,(math.pi/2,0,0));
for a in range(5):
    ang=a*2*math.pi/5; curve('FAN_01_BLADE',[(.61,.125,.39),(.61+.038*math.cos(ang),.125,.39+.038*math.sin(ang))],.006,M_WHITE)
curve('VENT_01_SAFE_EXHAUST',[(.61,.19,.39),(.61,.19,.48),(.61,.04,.50),(.56,.04,.50)],.018,M_CYAN)
box('VENT_01_ROOF_GRILLE',(.56,.04,.535),(.13,.13,.015),M_CYAN,.003)
sensor('FAN_FB_01','RPM',(.62,.25,.25),M_CYAN)
label('LABEL_C','C  GAS',.47,.485,.20)

# Independent simulation box and visual safety/alarm panel on C zone facade.
box('SIMBOX_01',(.66,-.24,.15),(.075,.06,.09),M_DARK,.006); box('SIMBOX_01_SIGNAL',(.66,-.273,.15),(.04,.006,.032),M_GREEN,.002)
box('ALARM_01',(.66,-.27,.40),(.08,.035,.045),M_RED,.005); cyl('ALARM_01_BEACON',(.66,-.27,.435),.018,.03,M_RED)

# Structural access detail: hinges, roof hatch seams and explicit service tags.
for x in (-.64,-.52): cyl('DOOR_01_HINGE',(x,-.337,.29),.008,.28,M_FRAME)
for x in (-.46,0,.46): box('ROOF_HATCH_SEAM',(x,0,.551),(.012,.56,.009),M_FRAME,.002)
# The product view stays uncluttered; sensor codes are engraved directly on
# the three module faces rather than repeated as floating presentation text.

# Ground, camera and studio lighting.
box('GROUND',(0,0,-.045),(2.4,1.8,.03),mat('MAT_Ground',(.012,.018,.026),.05,.55),.01)
def camera(name,loc,target,lens=52):
    bpy.ops.object.camera_add(location=loc); c=bpy.context.object; c.name=name; c.data.lens=lens
    q=(Vector(target)-c.location).to_track_quat('-Z','Y'); c.rotation_euler=q.to_euler(); return c
cam=camera('CAM_HERO',(1.72,-1.65,1.10),(.05,0,.26),54); scene.camera=cam
def light(name,kind,loc,energy,color,size=1.0):
    bpy.ops.object.light_add(type=kind,location=loc); o=bpy.context.object; o.name=name; o.data.energy=energy; o.data.color=color
    if kind=='AREA':o.data.shape='DISK';o.data.size=size
    q=(Vector((0,0,.24))-o.location).to_track_quat('-Z','Y'); o.rotation_euler=q.to_euler(); return o
light('KEY','AREA',(0,-1.1,1.5),950,(.72,.88,1.0),1.5); light('RIM','AREA',(1.2,.9,1.0),750,(.22,.63,1.0),1.0); light('FILL','AREA',(-1,-.3,.7),450,(1.0,.35,.12),.8)

# Hero with acrylic, then functional cutaway by hiding only front facade and roof.
scene.render.filepath=HERO; bpy.ops.wm.save_as_mainfile(filepath=BLEND); bpy.ops.render.render(write_still=True)
for o in bpy.data.objects:
    if o.name.startswith('ACRYLIC_FRONT_PANEL') or o.name.startswith('ACRYLIC_ROOF_PANEL'): o.hide_render=True
scene.render.filepath=CUT; bpy.ops.render.render(write_still=True)
for o in bpy.data.objects: o.hide_render=False

# Preserve material and semantic object names in a portable GLB.
bpy.ops.object.select_all(action='SELECT'); bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB', export_apply=True, export_materials='EXPORT')
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('V03_DONE', BLEND, GLB, HERO, CUT)
