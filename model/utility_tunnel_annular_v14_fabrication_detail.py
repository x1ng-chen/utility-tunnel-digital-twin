"""V14: fabrication-facing details for the V13 annular sensor stations.

Assumptions intentionally exposed in the model (replace after physical check):
G01 OD≈35 mm, clear acrylic=3 mm, station bracket=90 x 110 x 3 mm,
four M3 clearance holes (Ø3.2 mm), and six-position service connector.
"""
import bpy
import math
import mathutils
import os

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v14-fabrication-detail.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v14-fabrication-detail.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v14-fabrication-detail-hero.png")
FAB_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v14-fabrication-detail-station.png")
CTRL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v14-fabrication-detail-control.png")
SCENE = bpy.context.scene
os.makedirs(PREVIEW_DIR, exist_ok=True)

if bpy.data.collections.get("COL-UT_RING_V13_ANNULAR") is None:
    raise RuntimeError("V13 annular-station collection not found; open V13 first.")


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if col:
        for obj in list(col.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(col)


remove_collection("COL-UT_RING_V14_FABRICATION")
COL = bpy.data.collections.new("COL-UT_RING_V14_FABRICATION")
SCENE.collection.children.link(COL)


def link(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def box(name, loc, dims, material, yaw=0, bevel=0.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = link(bpy.context.object)
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.rotation_euler[2] = yaw
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cyl(name, loc, radius, depth, material, yaw=0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=radius, depth=depth, location=loc, rotation=(math.pi/2, 0, yaw))
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, loc, major, minor, material, yaw=0):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=20, minor_segments=8, location=loc, rotation=(math.pi/2, 0, yaw))
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
    data.extrude = 0.00028
    data.bevel_depth = 0.00006
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi/2, 0, yaw)
    obj.data.materials.append(material)
    return obj


def cable(name, points, material, radius=0.00135):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for point, co in zip(spl.bezier_points, points):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def xf(center, yaw, local):
    x, y, z = local
    c, s = math.cos(yaw), math.sin(yaw)
    return (center[0] + c*x - s*y, center[1] + s*x + c*y, center[2] + z)


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

STATIONS = ["S01", "S02", "S03", "S04", "S05"]
TYPES = [("O2", MAT_CYAN, "electro"), ("CO", MAT_RED, "mq"), ("CH4", MAT_GREEN, "mq"), ("SMOKE", MAT_ORANGE, "mq"), ("FLAME", MAT_RED, "flame"), ("TH", MAT_BLUE, "th")]
wire_mats = [MAT_CYAN, MAT_RED, MAT_GREEN, MAT_ORANGE, MAT_BLUE]

# Five station-specific machining aids and more recognisable sensor I/O.
for index, sid in enumerate(STATIONS):
    panel = bpy.data.objects["MESH_V13_%s_PANEL" % sid]
    center = tuple(panel.location)
    yaw = panel.rotation_euler.z
    # 3 mm bracket plate behind the existing station, with four M3 positions.
    box("MESH_V14_%s_BRACKET_PLATE" % sid, xf(center, yaw, (0, 0.014, 0)), (0.090, 0.003, 0.110), MAT_STEEL, yaw, 0.0008)
    for hx, hz, suffix in [(-0.035, 0.043, "TL"), (0.035, 0.043, "TR"), (-0.035, -0.043, "BL"), (0.035, -0.043, "BR")]:
        loc = xf(center, yaw, (hx, -0.013, hz))
        torus("GEO_V14_%s_M3_%s" % (sid, suffix), loc, 0.0032, 0.00055, MAT_YELLOW, yaw)
    # G01 saddle under the station: a visible pipe-clamp block and U-bolt legs.
    box("MESH_V14_%s_G01_SADDLE" % sid, xf(center, yaw, (0, 0.017, -0.067)), (0.058, 0.020, 0.009), MAT_STEEL, yaw, 0.001)
    for x in (-0.022, 0.022):
        box("GEO_V14_%s_UBOLT_%s" % (sid, "L" if x < 0 else "R"), xf(center, yaw, (x, 0.017, -0.050)), (0.004, 0.006, 0.034), MAT_STEEL, yaw, 0.0006)
    text("GEO_V14_%s_FAB_LABEL" % sid, "BRKT 90x110x3 | 4xM3 Ø3.2 | G01 Ø35", xf(center, yaw, (0, -0.022, 0.084)), 0.0034, MAT_YELLOW, yaw)

    # One keyed JST-style connector per sensor PCB.  The bodies remain generic
    # since exact breakout-board dimensions have not been supplied.
    for key, color, kind in TYPES:
        pcb = bpy.data.objects["MESH_V13_%s_%s_PCB" % (sid, key)]
        head = bpy.data.objects["MESH_V13_%s_%s_HEAD" % (sid, key)]
        # Keyed 4-pin plug at the lower PCB edge.
        connector_loc = (pcb.location.x, pcb.location.y - 0.004, pcb.location.z - 0.011)
        box("MESH_V14_%s_%s_JST" % (sid, key), connector_loc, (0.012, 0.005, 0.006), MAT_WHITE, yaw, 0.0005)
        for pin in range(4):
            cyl("GEO_V14_%s_%s_PIN_%02d" % (sid, key, pin+1), (pcb.location.x - 0.0045 + pin*0.003, pcb.location.y - 0.008, pcb.location.z - 0.011), 0.00085, 0.0025, MAT_STEEL, yaw)
        # Distinguish the actual sensing head/connector interface by family.
        if kind == "electro":
            torus("GEO_V14_%s_%s_CAP_RING" % (sid, key), (head.location.x, head.location.y - 0.003, head.location.z), 0.0048, 0.0006, color, yaw)
        elif kind == "mq":
            for ring in (-0.0018, 0.0, 0.0018):
                torus("GEO_V14_%s_%s_MESH_%02d" % (sid, key, int((ring+0.002)*1000)), (head.location.x, head.location.y + ring, head.location.z), 0.0053, 0.00035, MAT_STEEL, yaw)
        elif kind == "flame":
            box("GEO_V14_%s_%s_VISOR" % (sid, key), (head.location.x, head.location.y - 0.004, head.location.z + 0.004), (0.011, 0.004, 0.004), MAT_BLACK, yaw, 0.0005)
        else:
            for dot in (-0.0025, 0.0, 0.0025):
                cyl("GEO_V14_%s_%s_VENT_%02d" % (sid, key, int((dot+0.003)*1000)), (head.location.x + dot, head.location.y - 0.003, head.location.z), 0.0008, 0.0015, MAT_BLACK, yaw)

# Dry A-zone terminal strip: five labelled harness plugs, one per annular station.
tb_center = (-0.225, -0.205, 0.315)
box("MESH_V14_TB01_BACKPLATE", tb_center, (0.114, 0.009, 0.080), MAT_BLACK, 0, 0.0015)
box("MESH_V14_TB01_RAIL", (-0.225, -0.212, 0.315), (0.098, 0.006, 0.052), MAT_STEEL, 0, 0.001)
text("GEO_V14_TB01_TITLE", "TB-01  SENSOR HARNESS", (-0.225, -0.217, 0.356), 0.006, MAT_YELLOW)
for idx, sid in enumerate(STATIONS):
    z = 0.339 - idx * 0.012
    box("MESH_V14_TB01_%s_TERMINAL" % sid, (-0.225, -0.218, z), (0.082, 0.006, 0.009), wire_mats[idx], 0, 0.0007)
    text("GEO_V14_TB01_%s_LABEL" % sid, sid + "  J-%s / WH-%s" % (sid, sid), (-0.225, -0.222, z), 0.0043, MAT_WHITE)
    panel = bpy.data.objects["MESH_V13_%s_PANEL" % sid]
    start = (panel.location.x, panel.location.y, panel.location.z - 0.064)
    cable("GEO_V14_%s_TO_TB01" % sid, [start, (panel.location.x*0.68, panel.location.y*0.68 - 0.105, 0.205), (-0.150, -0.190, z), (-0.184, -0.214, z)], wire_mats[idx])

text("GEO_V14_ASSUMPTION", "FAB ASSUMPTIONS: G01 Ø35 | CLEAR ACRYLIC 3mm | VERIFY AGAINST REAL BOARDS", (-0.02, -0.168, 0.112), 0.0055, MAT_YELLOW)


def look_at(camera, point):
    camera.rotation_euler = (mathutils.Vector(point) - camera.location).to_track_quat('-Z', 'Y').to_euler()


cam = SCENE.camera
enclosure = ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL")
for name in enclosure:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.04, -1.23, 0.86)
cam.data.lens = 59
look_at(cam, (0.0, 0.0, 0.235))
SCENE.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

states = {}
for name in enclosure + ("GEO_ZONE_A_RIB", "GEO_ZONE_B_RIB", "GEO_ZONE_C_RIB", "GEO_ACRYLIC_SERVICE_SEAM_01", "GEO_ACRYLIC_SERVICE_SEAM_02", "GEO_ACRYLIC_SERVICE_SEAM_03"):
    if name in bpy.data.objects:
        states[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
cam.location = (0.72, -0.72, 0.62)
cam.data.lens = 74
look_at(cam, (0.21, -0.07, 0.295))
SCENE.render.filepath = FAB_OUT
bpy.ops.render.render(write_still=True)

cam.location = (-0.66, -0.65, 0.43)
cam.data.lens = 74
look_at(cam, (-0.225, -0.210, 0.305))
SCENE.render.filepath = CTRL_OUT
bpy.ops.render.render(write_still=True)
for name, hidden in states.items():
    bpy.data.objects[name].hide_render = hidden

bpy.ops.object.select_all(action="DESELECT")
for obj in SCENE.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print({"V14_DONE": True, "stations": len(STATIONS), "terminal_inputs": len(STATIONS), "fabrication_assumption": "G01_OD35 acrylic3 M3", "blend": BLEND_OUT, "glb": GLB_OUT})
