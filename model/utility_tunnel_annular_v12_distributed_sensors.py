"""V12: distribute the V3.5 sensor inventory across five tunnel stations.

Run this from the V11 hardware-baseline scene.  It removes only the former central sensor
array, retains all V11 hardware/pipe/water geometry, and creates five
physically separate six-sensor stations.  Each sensor family therefore has one
module at each station rather than five copies mounted together.
"""
import bpy
import math
import mathutils
import os

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v12-distributed-sensors.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v12-distributed-sensors.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v12-distributed-sensors-hero.png")
DETAIL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v12-distributed-sensors-detail.png")
SCENE = bpy.context.scene
os.makedirs(PREVIEW_DIR, exist_ok=True)

if bpy.data.collections.get("COL-UT_RING_V35") is None:
    raise RuntimeError("V11 hardware-baseline collection not found; open utility-tunnel-annular-v11-hardware-baseline.blend first.")


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)


remove_collection("COL-UT_RING_V12_DISTRIBUTED")
COL = bpy.data.collections.new("COL-UT_RING_V12_DISTRIBUTED")
SCENE.collection.children.link(COL)

# Delete only the V11 central sensor-array parts; all tubing, control modules,
# pump reserve and V10 structure remain user-owned and untouched.
sensor_prefixes = (
    "MESH_V35_RACK_", "GEO_V35_LABEL_", "GEO_V35_SENSOR_ARRAY_TITLE",
    "MESH_V35_O2_ME2_", "GEO_V35_O2_ME2_",
    "MESH_V35_CO_MQ7_", "GEO_V35_CO_MQ7_",
    "MESH_V35_CH4_MQ4_", "GEO_V35_CH4_MQ4_",
    "MESH_V35_SMOKE_MQ2_", "GEO_V35_SMOKE_MQ2_",
    "MESH_V35_FLAME_", "GEO_V35_FLAME_",
    "MESH_V35_TH_", "GEO_V35_TH_",
)
for obj in list(bpy.data.objects):
    if obj.name.startswith(sensor_prefixes):
        bpy.data.objects.remove(obj, do_unlink=True)


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
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cyl(name, loc, radius, depth, material, rotation=(math.pi/2, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def text(name, body, loc, size, material):
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
    obj.rotation_euler = (math.pi/2, 0, 0)
    obj.data.materials.append(material)
    return obj


def cable(name, points, material):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = 0.0011
    data.bevel_resolution = 2
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for p, co in zip(spl.bezier_points, points):
        p.co = co
        p.handle_left_type = "AUTO"
        p.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


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

# Five different functional locations around the annular passage.
STATIONS = [
    ("S01", "ENTRY / A", (-0.345, -0.125, 0.330)),
    ("S02", "A-B LINK", (-0.145, -0.132, 0.350)),
    ("S03", "DRY TRAY", (0.030, -0.146, 0.300)),
    ("S04", "C SAMPLE", (0.205, -0.110, 0.350)),
    ("S05", "RETURN", (0.355, -0.055, 0.295)),
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

for station_idx, (sid, label, (cx, cy, cz)) in enumerate(STATIONS, 1):
    # Each station is a separate, serviceable panel, not one large type rack.
    box("MESH_V12_%s_PANEL" % sid, (cx, cy, cz), (0.096, 0.011, 0.102), MAT_BLACK, 0.002)
    box("MESH_V12_%s_FACE" % sid, (cx, cy - 0.007, cz), (0.086, 0.003, 0.084), MAT_STEEL, 0.0008)
    text("GEO_V12_%s_TITLE" % sid, sid + "  " + label, (cx, cy - 0.010, cz + 0.060), 0.0068, MAT_YELLOW)
    for sensor_idx, ((key, short, color, cap, kind), (dx, dz)) in enumerate(zip(SENSORS, SLOTS), 1):
        x, z = cx + dx, cz + dz
        token = "%s_%s_%s" % (sid, key, short.replace("-", ""))
        box("MESH_V12_" + token + "_PCB", (x, cy - 0.011, z), (0.018, 0.004, 0.021), MAT_PCB, 0.0006)
        if kind == "electro":
            cyl("MESH_V12_" + token + "_HEAD", (x, cy - 0.015, z + 0.005), 0.0058, 0.004, cap)
        elif kind == "mq":
            cyl("MESH_V12_" + token + "_HEAD", (x, cy - 0.015, z + 0.005), 0.0065, 0.005, MAT_STEEL)
            cyl("GEO_V12_" + token + "_CORE", (x, cy - 0.018, z + 0.005), 0.0035, 0.0015, cap)
        elif kind == "flame":
            cyl("MESH_V12_" + token + "_HEAD", (x, cy - 0.015, z + 0.005), 0.0052, 0.005, MAT_BLACK)
            cyl("GEO_V12_" + token + "_LENS", (x, cy - 0.018, z + 0.005), 0.0028, 0.0013, cap)
        else:
            box("MESH_V12_" + token + "_HEAD", (x, cy - 0.015, z + 0.005), (0.010, 0.0035, 0.009), cap, 0.0007)
        text("GEO_V12_" + token + "_LABEL", short, (x, cy - 0.019, z - 0.011), 0.0033, color)
    # One labelled harness per station makes physical routing clear without
    # pretending the sensors are joined in a single gas path.
    cable("GEO_V12_%s_HARNESS" % sid,
          [(cx, cy - 0.010, cz - 0.046), (cx, cy - 0.035, 0.205), (cx * 0.60, -0.170, 0.190)],
          MAT_WHITE)

text("GEO_V12_DISTRIBUTED_TITLE", "DISTRIBUTED SENSING  |  5 STATIONS  |  EACH TYPE SEPARATED", (0.01, -0.155, 0.405), 0.0080, MAT_YELLOW)


def look_at(camera, point):
    camera.rotation_euler = (mathutils.Vector(point) - camera.location).to_track_quat('-Z', 'Y').to_euler()


# Render an overall tunnel view and an unobstructed audit view of the five stations.
cam = SCENE.camera
enclosure = ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL")
for name in enclosure:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.02, -1.23, 0.84)
cam.data.lens = 59
look_at(cam, (0.02, -0.03, 0.235))
SCENE.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

hide_state = {}
for name in enclosure + ("GEO_ZONE_A_RIB", "GEO_ZONE_B_RIB", "GEO_ZONE_C_RIB", "GEO_ACRYLIC_SERVICE_SEAM_01", "GEO_ACRYLIC_SERVICE_SEAM_02", "GEO_ACRYLIC_SERVICE_SEAM_03"):
    if name in bpy.data.objects:
        hide_state[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
cam.location = (0.03, -1.08, 0.48)
cam.data.lens = 56
look_at(cam, (0.02, -0.12, 0.325))
SCENE.render.filepath = DETAIL_OUT
bpy.ops.render.render(write_still=True)
for name, value in hide_state.items():
    bpy.data.objects[name].hide_render = value

bpy.ops.object.select_all(action="DESELECT")
for obj in SCENE.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print({"V12_DONE": True, "stations": len(STATIONS), "sensor_modules": len(STATIONS) * len(SENSORS), "blend": BLEND_OUT, "glb": GLB_OUT})
