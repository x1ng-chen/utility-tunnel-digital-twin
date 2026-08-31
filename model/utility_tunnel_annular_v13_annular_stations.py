"""V13: annularly distributed, serviceable V3.5 sensor stations.

Run from the V12 scene.  The V12 front-side stations are removed as one scoped
collection.  Five new stations are rebuilt around the actual G01 ring:
right inlet, front run, left bend, rear run, and right return/vent.
"""
import bpy
import math
import mathutils
import os

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v13-annular-stations.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v13-annular-stations.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v13-annular-stations-hero.png")
LAYOUT_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v13-annular-stations-layout.png")
DETAIL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v13-annular-stations-detail.png")
SCENE = bpy.context.scene
os.makedirs(PREVIEW_DIR, exist_ok=True)

if bpy.data.collections.get("COL-UT_RING_V12_DISTRIBUTED") is None:
    raise RuntimeError("V12 distributed-sensor collection not found; open the V12 model first.")


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)


remove_collection("COL-UT_RING_V12_DISTRIBUTED")
remove_collection("COL-UT_RING_V13_ANNULAR")
COL = bpy.data.collections.new("COL-UT_RING_V13_ANNULAR")
SCENE.collection.children.link(COL)


def link(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def box(name, loc, dims, material, bevel=0.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = link(bpy.context.object)
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
    return obj


def cyl(name, loc, radius, depth, material, rotation=(math.pi/2, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def cone(name, loc, radius, depth, material, rotation=(0, math.pi/2, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=radius, radius2=0, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    return obj


def text(name, body, loc, size, material, yaw=0):
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
    obj.rotation_euler = (math.pi/2, 0, yaw)
    obj.data.materials.append(material)
    return obj


def cable(name, points, material):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = 0.0011
    data.bevel_resolution = 2
    spline = data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def xf(center, yaw, local):
    """Transform a station-local point to the annular tunnel coordinate system."""
    x, y, z = local
    c, s = math.cos(yaw), math.sin(yaw)
    return (center[0] + c*x - s*y, center[1] + s*x + c*y, center[2] + z)


def box_local(name, center, yaw, local, dims, material, bevel=0.001):
    obj = box(name, xf(center, yaw, local), dims, material, bevel)
    obj.rotation_euler[2] = yaw
    return obj


def cyl_local(name, center, yaw, local, radius, depth, material):
    obj = cyl(name, xf(center, yaw, local), radius, depth, material)
    obj.rotation_euler[2] = yaw
    return obj


def text_local(name, center, yaw, local, body, size, material):
    return text(name, body, xf(center, yaw, local), size, material, yaw)


M = bpy.data.materials
MAT_BLACK = M["MAT-v35_black"]
MAT_PCB = M["MAT-v35_pcb"]
MAT_CYAN = M["MAT-v35_cyan"]
MAT_RED = M["MAT-v35_red"]
MAT_GREEN = M["MAT-v35_green"]
MAT_ORANGE = M["MAT-v35_orange"]
MAT_YELLOW = M["MAT-v35_yellow"]
MAT_BLUE = M["MAT-v35_blue"]
MAT_WHITE = M["MAT-v35_white"]
MAT_STEEL = M["MAT-v35_steel"]

# Local -Y is the sensing-panel face.  Yaw turns each panel outward around G01.
STATIONS = [
    ("S01", "INLET", "AIR IN → G01", (0.360, -0.060, 0.292), math.pi/2),
    ("S02", "FRONT RUN", "SAMPLE FLOW →", (0.045, -0.139, 0.325), 0.0),
    ("S03", "LEFT BEND", "RETURN ←", (-0.330, -0.028, 0.300), -math.pi/2),
    ("S04", "REAR RUN", "RETURN → VENT", (-0.075, 0.103, 0.323), math.pi),
    ("S05", "VENT RETURN", "VENT UP ↑", (0.285, 0.078, 0.302), math.pi/2),
]
SENSORS = [
    ("O2", "ME2-O2", MAT_CYAN, MAT_WHITE, "electro"),
    ("CO", "MQ-7", MAT_RED, MAT_ORANGE, "mq"),
    ("CH4", "MQ-4", MAT_GREEN, MAT_YELLOW, "mq"),
    ("SMOKE", "MQ-2", MAT_ORANGE, MAT_WHITE, "mq"),
    ("FLAME", "FLAME", MAT_RED, MAT_YELLOW, "flame"),
    ("TH", "SHT30", MAT_BLUE, MAT_CYAN, "th"),
]
SLOTS = [(-0.028, 0.022), (0.000, 0.022), (0.028, 0.022), (-0.028, -0.022), (0.000, -0.022), (0.028, -0.022)]

for sid, zone, flow, center, yaw in STATIONS:
    # Bracket: upper and lower rails, two side struts, and a terminal block.
    box_local("MESH_V13_%s_MOUNT_RAIL_TOP" % sid, center, yaw, (0, 0.010, 0.055), (0.091, 0.010, 0.007), MAT_STEEL, 0.001)
    box_local("MESH_V13_%s_MOUNT_RAIL_BOTTOM" % sid, center, yaw, (0, 0.010, -0.055), (0.091, 0.010, 0.007), MAT_STEEL, 0.001)
    for side in (-0.041, 0.041):
        box_local("GEO_V13_%s_STRUT_%s" % (sid, "L" if side < 0 else "R"), center, yaw, (side, 0.009, 0), (0.006, 0.010, 0.110), MAT_STEEL, 0.0008)
    box_local("MESH_V13_%s_PANEL" % sid, center, yaw, (0, -0.002, 0), (0.088, 0.010, 0.093), MAT_BLACK, 0.0018)
    box_local("MESH_V13_%s_FACE" % sid, center, yaw, (0, -0.008, 0), (0.078, 0.003, 0.077), MAT_STEEL, 0.0006)
    box_local("MESH_V13_%s_CONNECTOR" % sid, center, yaw, (0, -0.014, -0.058), (0.048, 0.008, 0.012), MAT_ORANGE, 0.001)
    for pin in range(6):
        cyl_local("GEO_V13_%s_PIN_%02d" % (sid, pin+1), center, yaw, (-0.018 + pin*0.0072, -0.020, -0.058), 0.0016, 0.003, MAT_STEEL)
    text_local("GEO_V13_%s_TITLE" % sid, center, yaw, (0, -0.015, 0.056), sid + "  " + zone, 0.0058, MAT_YELLOW)
    text_local("GEO_V13_%s_FLOW" % sid, center, yaw, (0, -0.015, -0.043), flow, 0.0045, MAT_WHITE)
    text_local("GEO_V13_%s_WIRE_ID" % sid, center, yaw, (0, -0.016, -0.071), "J-%s / WH-%s" % (sid, sid), 0.0042, MAT_ORANGE)

    for (key, short, color, cap, kind), (dx, dz) in zip(SENSORS, SLOTS):
        token = "%s_%s" % (sid, key)
        box_local("MESH_V13_%s_PCB" % token, center, yaw, (dx, -0.015, dz), (0.017, 0.004, 0.019), MAT_PCB, 0.0005)
        if kind == "electro":
            cyl_local("MESH_V13_%s_HEAD" % token, center, yaw, (dx, -0.019, dz+0.004), 0.0054, 0.004, cap)
        elif kind == "mq":
            cyl_local("MESH_V13_%s_HEAD" % token, center, yaw, (dx, -0.019, dz+0.004), 0.0061, 0.005, MAT_STEEL)
            cyl_local("GEO_V13_%s_CORE" % token, center, yaw, (dx, -0.022, dz+0.004), 0.0033, 0.0015, cap)
        elif kind == "flame":
            cyl_local("MESH_V13_%s_HEAD" % token, center, yaw, (dx, -0.019, dz+0.004), 0.0050, 0.005, MAT_BLACK)
            cyl_local("GEO_V13_%s_LENS" % token, center, yaw, (dx, -0.022, dz+0.004), 0.0027, 0.0013, cap)
        else:
            box_local("MESH_V13_%s_HEAD" % token, center, yaw, (dx, -0.019, dz+0.004), (0.009, 0.0035, 0.008), cap, 0.0006)
        text_local("GEO_V13_%s_LABEL" % token, center, yaw, (dx, -0.023, dz-0.010), short, 0.0029, color)

    # Numbered harness terminates at the cable tray; it is electrical only and
    # deliberately does not connect gas paths or the reserve water pump.
    start = xf(center, yaw, (0, -0.018, -0.065))
    mid = xf(center, yaw, (0.018, -0.040, -0.088))
    end = (center[0]*0.58, center[1]*0.58 - 0.130, 0.185)
    cable("GEO_V13_%s_HARNESS" % sid, [start, mid, end], MAT_WHITE)
    # A small yellow flow arrow is fixed above every station in the local pipe tangent.
    box_local("GEO_V13_%s_FLOW_SHAFT" % sid, center, yaw, (0, -0.018, 0.072), (0.026, 0.003, 0.003), MAT_YELLOW, 0.0004)
    tip = cone("GEO_V13_%s_FLOW_TIP" % sid, xf(center, yaw, (0.019, -0.018, 0.072)), 0.006, 0.011, MAT_YELLOW)
    tip.rotation_euler = (0, math.pi/2, yaw)

text("GEO_V13_ANNULAR_TITLE", "G01 ANNULAR DISTRIBUTED SENSORS  |  S01 INLET → S05 VENT RETURN", (0.0, -0.162, 0.405), 0.0074, MAT_YELLOW)


def look_at(camera, point):
    camera.rotation_euler = (mathutils.Vector(point) - camera.location).to_track_quat('-Z', 'Y').to_euler()


cam = SCENE.camera
enclosure = ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL")
for name in enclosure:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.03, -1.23, 0.85)
cam.data.lens = 59
look_at(cam, (0.0, 0.0, 0.235))
SCENE.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

# Roof-off, elevated validation render proves the stations surround G01.
state = {}
for name in enclosure + ("GEO_ZONE_A_RIB", "GEO_ZONE_B_RIB", "GEO_ZONE_C_RIB", "GEO_ACRYLIC_SERVICE_SEAM_01", "GEO_ACRYLIC_SERVICE_SEAM_02", "GEO_ACRYLIC_SERVICE_SEAM_03"):
    if name in bpy.data.objects:
        state[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
cam.location = (0.72, -0.82, 1.28)
cam.data.lens = 55
look_at(cam, (0.0, 0.0, 0.235))
SCENE.render.filepath = LAYOUT_OUT
bpy.ops.render.render(write_still=True)

cam.location = (0.70, -0.72, 0.60)
cam.data.lens = 70
look_at(cam, (0.18, -0.08, 0.305))
SCENE.render.filepath = DETAIL_OUT
bpy.ops.render.render(write_still=True)
for name, value in state.items():
    bpy.data.objects[name].hide_render = value

bpy.ops.object.select_all(action="DESELECT")
for obj in SCENE.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print({"V13_DONE": True, "stations": len(STATIONS), "sensor_modules": len(STATIONS)*len(SENSORS), "blend": BLEND_OUT, "glb": GLB_OUT})
