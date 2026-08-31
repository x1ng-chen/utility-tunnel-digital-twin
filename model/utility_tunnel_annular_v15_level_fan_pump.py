"""V15: five FS-IR02 level sensors plus clearly visible fan/pump hardware.

Reference-derived facts: FS-IR02 is a 5 V optical level probe with a
38.6 x 22.1 mm controller PCB and XH2.54 connections.  The five positions
model low, normal, high, high-high, and leak/side monitoring.  The 24 V pump
is visibly modelled as a reserved test-loop device, not an enabled wet loop.
"""
import bpy
import math
import mathutils
import os

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v15-level-fan-pump.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v15-level-fan-pump.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v15-level-fan-pump-hero.png")
WATER_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v15-level-fan-pump-water.png")
AIR_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v15-level-fan-pump-air.png")
EXHAUST_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v15-level-fan-pump-exhaust.png")
SCENE = bpy.context.scene
os.makedirs(PREVIEW_DIR, exist_ok=True)

if bpy.data.collections.get("COL-UT_RING_V14_FABRICATION") is None:
    raise RuntimeError("V14 fabrication collection not found; open V14 first.")


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)


remove_collection("COL-UT_RING_V15_WATER_AIR")
COL = bpy.data.collections.new("COL-UT_RING_V15_WATER_AIR")
SCENE.collection.children.link(COL)


def link(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def box(name, loc, dims, material, rotation=(0, 0, 0), bevel=0.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cyl(name, loc, radius, depth, material, rotation=(math.pi/2, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, loc, major, minor, material, rotation=(math.pi/2, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=8, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    return obj


def text(name, body, loc, size, material, rotation=(math.pi/2, 0, 0)):
    data = bpy.data.curves.new(name + "_DATA", "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = 0.0003
    data.bevel_depth = 0.00007
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    return obj


def curve(name, points, material, radius=0.0012):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for bp, co in zip(spl.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


M = bpy.data.materials
MAT_BLACK = M["MAT-v35_black"]
MAT_PCB = M["MAT-v35_pcb"]
MAT_BLUE = M["MAT-v35_blue"]
MAT_CYAN = M["MAT-v35_cyan"]
MAT_RED = M["MAT-v35_red"]
MAT_GREEN = M["MAT-v35_green"]
MAT_ORANGE = M["MAT-v35_orange"]
MAT_YELLOW = M["MAT-v35_yellow"]
MAT_WHITE = M["MAT-v35_white"]
MAT_STEEL = M["MAT-v35_steel"]

# FS-IR02 stations: probe heads touch the outside of the tray, electronics stay
# above the wet line in the accessible front service rail.  Board dimensions
# follow the supplied image: 38.6 x 22.1 mm (modelled as 39 x 22 mm).
LEVELS = [
    ("L01", "LOW", (-0.060, -0.168, 0.158), (-0.078, -0.208, 0.224)),
    ("L02", "NORMAL", (-0.024, -0.168, 0.164), (-0.039, -0.208, 0.224)),
    ("L03", "HIGH", (0.020, -0.168, 0.170), (0.000, -0.208, 0.224)),
    ("L04", "HI-HI", (-0.055, -0.095, 0.176), (0.039, -0.208, 0.224)),
    ("L05", "LEAK", (0.060, -0.095, 0.158), (0.078, -0.208, 0.224)),
]
for idx, (tag, role, probe_loc, board_loc) in enumerate(LEVELS):
    # Threaded, externally mounted optical probe: collar, nut, sensor body and 4-pin tail.
    direction = -1 if probe_loc[1] < -0.13 else 1
    cyl("MESH_V15_FSIR02_%s_PROBE_COLLAR" % tag, probe_loc, 0.0095, 0.004, MAT_STEEL)
    torus("GEO_V15_FSIR02_%s_O_RING" % tag, (probe_loc[0], probe_loc[1] - direction*0.003, probe_loc[2]), 0.0072, 0.0007, MAT_YELLOW)
    cyl("MESH_V15_FSIR02_%s_PROBE_BODY" % tag, (probe_loc[0], probe_loc[1] - direction*0.010, probe_loc[2]), 0.0065, 0.016, MAT_BLACK)
    cyl("GEO_V15_FSIR02_%s_OPTIC" % tag, (probe_loc[0], probe_loc[1] - direction*0.019, probe_loc[2]), 0.0042, 0.003, MAT_CYAN)
    # 39 x 22 mm blue board, XH2.54 probe connector, four output pads and adjustment trimmer.
    box("MESH_V15_FSIR02_%s_BOARD" % tag, board_loc, (0.039, 0.004, 0.022), MAT_BLUE, bevel=0.0007)
    box("MESH_V15_FSIR02_%s_XH254" % tag, (board_loc[0]-0.010, board_loc[1]-0.004, board_loc[2]-0.007), (0.012, 0.003, 0.006), MAT_WHITE, bevel=0.0004)
    box("GEO_V15_FSIR02_%s_TRIM" % tag, (board_loc[0]-0.013, board_loc[1]-0.005, board_loc[2]+0.006), (0.007, 0.0025, 0.008), MAT_CYAN, bevel=0.0004)
    cyl("GEO_V15_FSIR02_%s_TRIM_KNOB" % tag, (board_loc[0]-0.013, board_loc[1]-0.007, board_loc[2]+0.006), 0.0021, 0.0015, MAT_ORANGE)
    box("GEO_V15_FSIR02_%s_IC" % tag, (board_loc[0]+0.007, board_loc[1]-0.004, board_loc[2]+0.004), (0.010, 0.0025, 0.006), MAT_BLACK, bevel=0.0003)
    for p in range(4):
        cyl("GEO_V15_FSIR02_%s_OUT_%02d" % (tag, p+1), (board_loc[0]+0.002+p*0.004, board_loc[1]-0.005, board_loc[2]-0.007), 0.0010, 0.0018, MAT_STEEL)
    text("GEO_V15_FSIR02_%s_LABEL" % tag, "FS-IR02 %s\n%s" % (tag, role), (board_loc[0], board_loc[1]-0.007, board_loc[2]+0.016), 0.0030, MAT_WHITE)
    # Four-core probe tail is coloured by function, then a single service lead goes to TB-01.
    for core, mat in enumerate((MAT_WHITE, MAT_BLUE, MAT_YELLOW, MAT_RED)):
        offset = (core-1.5)*0.0012
        curve("GEO_V15_FSIR02_%s_PROBE_WIRE_%02d" % (tag, core+1), [(probe_loc[0]+offset, probe_loc[1]-direction*0.022, probe_loc[2]), (probe_loc[0]+offset, -0.190, 0.190), (board_loc[0]-0.010+core*0.0025, board_loc[1]-0.005, board_loc[2]-0.007)], mat, 0.00055)
    curve("GEO_V15_FSIR02_%s_TO_TB01" % tag, [(board_loc[0], board_loc[1]-0.006, board_loc[2]), (board_loc[0], -0.190, 0.235), (-0.185, -0.214, 0.278-idx*0.008)], MAT_GREEN, 0.00075)

text("GEO_V15_LEVEL_TITLE", "5x FS-IR02 LEVEL SENSORS | 5V | AO / DO | XH2.54", (0.005, -0.218, 0.254), 0.0050, MAT_YELLOW)


def make_fan(tag, loc, airflow_label, wire_target):
    # 80 mm, 12 V four-wire axial fan with frame, grill, hub, seven blades and cable tail.
    box("MESH_V15_%s_FRAME" % tag, loc, (0.082, 0.014, 0.082), MAT_BLACK, bevel=0.002)
    torus("GEO_V15_%s_RING" % tag, (loc[0], loc[1]-0.010, loc[2]), 0.029, 0.003, MAT_STEEL)
    cyl("MESH_V15_%s_HUB" % tag, (loc[0], loc[1]-0.014, loc[2]), 0.010, 0.006, MAT_BLACK)
    for angle in range(0, 360, 51):
        rad = math.radians(angle)
        blade = box("GEO_V15_%s_BLADE_%03d" % (tag, angle), (loc[0]+0.016*math.sin(rad), loc[1]-0.012, loc[2]+0.016*math.cos(rad)), (0.009, 0.004, 0.030), MAT_CYAN, bevel=0.0007)
        blade.rotation_euler[1] = rad
    for cross in (-0.022, 0.0, 0.022):
        box("GEO_V15_%s_GRILL_H_%02d" % (tag, int((cross+0.03)*1000)), (loc[0], loc[1]-0.018, loc[2]+cross), (0.058, 0.0016, 0.0016), MAT_STEEL, bevel=0.0002)
        box("GEO_V15_%s_GRILL_V_%02d" % (tag, int((cross+0.03)*1000)), (loc[0]+cross, loc[1]-0.018, loc[2]), (0.0016, 0.0016, 0.058), MAT_STEEL, bevel=0.0002)
    for wire, mat in enumerate((MAT_RED, MAT_BLACK, MAT_YELLOW, MAT_BLUE)):
        curve("GEO_V15_%s_WIRE_%02d" % (tag, wire+1), [(loc[0]-0.026+wire*0.006, loc[1]-0.003, loc[2]-0.034), (loc[0]-0.026+wire*0.006, -0.125, 0.180), wire_target], mat, 0.00095)
    text("GEO_V15_%s_LABEL" % tag, tag + " 12V 4-WIRE\n" + airflow_label, (loc[0], loc[1]-0.023, loc[2]-0.057), 0.0043, MAT_WHITE)


# Intake and extraction sides are visibly separate and route to H-31 fan control.
make_fan("FAN-01 INTAKE", (0.430, -0.154, 0.267), "AIR IN →", (-0.180, -0.205, 0.210))
# Raised beside the roof-return duct so it remains inspectable instead of
# disappearing behind station S05.
make_fan("FAN-02 EXHAUST", (0.215, 0.040, 0.355), "→ VENT", (-0.174, -0.205, 0.206))

# Clearly visible 24 V pump, separated from the tray by a service gap.  Short
# labelled hoses end at quick couplers, signalling future/test-loop only.
pump = (0.185, -0.184, 0.156)
box("MESH_V15_PUMP24V_BASE", (pump[0], pump[1], pump[2]-0.020), (0.105, 0.066, 0.012), MAT_STEEL, bevel=0.0015)
cyl("MESH_V15_PUMP24V_MOTOR", (pump[0]-0.020, pump[1], pump[2]), 0.020, 0.052, MAT_RED, rotation=(0, math.pi/2, 0))
box("MESH_V15_PUMP24V_HEAD", (pump[0]+0.030, pump[1], pump[2]), (0.038, 0.044, 0.040), MAT_BLACK, bevel=0.002)
cyl("MESH_V15_PUMP24V_IN", (pump[0]+0.030, pump[1]-0.030, pump[2]), 0.0075, 0.018, MAT_CYAN)
cyl("MESH_V15_PUMP24V_OUT", (pump[0]+0.030, pump[1]+0.030, pump[2]), 0.0075, 0.018, MAT_ORANGE)
for x in (pump[0]-0.040, pump[0]+0.040):
    cyl("GEO_V15_PUMP24V_FOOT_%s" % str(x).replace(".", "_"), (x, pump[1], pump[2]-0.028), 0.004, 0.006, MAT_BLACK, rotation=(0,0,0))
curve("GEO_V15_PUMP24V_TEST_IN", [(pump[0]+0.030, pump[1]-0.041, pump[2]), (pump[0]+0.030, pump[1]-0.060, pump[2]), (0.120, -0.205, 0.148)], MAT_CYAN, 0.0020)
curve("GEO_V15_PUMP24V_TEST_OUT", [(pump[0]+0.030, pump[1]+0.041, pump[2]), (pump[0]+0.065, pump[1]+0.050, pump[2]), (0.240, -0.120, 0.148)], MAT_ORANGE, 0.0020)
text("GEO_V15_PUMP24V_LABEL", "24V WATER PUMP\nTEST LOOP / NOT CONTINUOUS", (pump[0], -0.226, 0.115), 0.0050, MAT_YELLOW)


def look_at(camera, point):
    camera.rotation_euler = (mathutils.Vector(point) - camera.location).to_track_quat('-Z', 'Y').to_euler()


cam = SCENE.camera
enclosure = ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL")
for name in enclosure:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.04, -1.25, 0.87)
cam.data.lens = 59
look_at(cam, (0.03, -0.03, 0.230))
SCENE.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

state = {}
for name in enclosure + ("GEO_ZONE_A_RIB", "GEO_ZONE_B_RIB", "GEO_ZONE_C_RIB", "GEO_ACRYLIC_SERVICE_SEAM_01", "GEO_ACRYLIC_SERVICE_SEAM_02", "GEO_ACRYLIC_SERVICE_SEAM_03"):
    if name in bpy.data.objects:
        state[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
cam.location = (0.32, -0.82, 0.45)
cam.data.lens = 74
look_at(cam, (0.03, -0.174, 0.185))
SCENE.render.filepath = WATER_OUT
bpy.ops.render.render(write_still=True)

cam.location = (0.78, -0.78, 0.57)
cam.data.lens = 70
look_at(cam, (0.325, -0.040, 0.270))
SCENE.render.filepath = AIR_OUT
bpy.ops.render.render(write_still=True)

cam.location = (0.50, -0.30, 0.66)
cam.data.lens = 76
look_at(cam, (0.215, 0.040, 0.355))
SCENE.render.filepath = EXHAUST_OUT
bpy.ops.render.render(write_still=True)
for name, value in state.items():
    bpy.data.objects[name].hide_render = value

bpy.ops.object.select_all(action="DESELECT")
for obj in SCENE.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print({"V15_DONE": True, "fs_ir02": len(LEVELS), "fans": 2, "pump": 1, "blend": BLEND_OUT, "glb": GLB_OUT})
