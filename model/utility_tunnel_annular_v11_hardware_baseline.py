"""V11 hardware-baseline implementation for the annular tunnel.

Run inside the already-open V10 Blender scene.  This script keeps all V10
geometry intact, creates only the ``COL-UT_RING_V35`` collection, saves a new
editable checkpoint, exports a portable GLB, and renders two review views.

Model contract:
* ME2-O2, MQ-7, MQ-4, MQ-2, flame, and temperature/humidity: 5 each.
* 2 x 12 V four-wire fan; K210 x1; SU-03T1 x1; ESP8266-01S x2;
  JQC-3FF-S-Z x1; DCP-3620 x1 (function/interface intentionally unspecified).
* 24 V pump is a physical *reserve* object only.  It has no pipe connection:
  the V3.5 water demonstration remains dry/<=50 ml with manual drain.
"""
import bpy
import math
import os

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v11-hardware-baseline.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v11-hardware-baseline.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v11-hardware-baseline-hero.png")
DETAIL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v11-hardware-baseline-hardware-detail.png")
CONTROL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v11-hardware-baseline-control-detail.png")

SCENE = bpy.context.scene
os.makedirs(PREVIEW_DIR, exist_ok=True)


def remove_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        return
    for obj in list(col.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(col)


remove_collection("COL-UT_RING_V35")
COL = bpy.data.collections.new("COL-UT_RING_V35")
SCENE.collection.children.link(COL)


def mat(name, color, metallic=0.0, roughness=0.45, emission=None):
    out = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    out.use_nodes = True
    bsdf = next((node for node in out.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = out.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        output = next((node for node in out.node_tree.nodes if node.type == "OUTPUT_MATERIAL"), None)
        if output is not None:
            out.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        bsdf.inputs["Emission Color"].default_value = emission[0]
        bsdf.inputs["Emission Strength"].default_value = emission[1]
    return out


MAT_BLACK = mat("MAT-v35_black", (0.025, 0.032, 0.040, 1), 0.0, 0.34)
MAT_PCB = mat("MAT-v35_pcb", (0.018, 0.26, 0.10, 1), 0.0, 0.42)
MAT_BLUE = mat("MAT-v35_blue", (0.025, 0.22, 0.74, 1), 0.0, 0.30)
MAT_CYAN = mat("MAT-v35_cyan", (0.02, 0.65, 0.78, 1), 0.0, 0.28)
MAT_RED = mat("MAT-v35_red", (0.78, 0.035, 0.025, 1), 0.0, 0.34)
MAT_ORANGE = mat("MAT-v35_orange", (1.0, 0.28, 0.02, 1), 0.0, 0.34)
MAT_YELLOW = mat("MAT-v35_yellow", (1.0, 0.78, 0.02, 1), 0.0, 0.34, ((1.0, 0.4, 0.01, 1), 0.25))
MAT_WHITE = mat("MAT-v35_white", (0.82, 0.88, 0.90, 1), 0.0, 0.40)
MAT_STEEL = mat("MAT-v35_steel", (0.36, 0.40, 0.44, 1), 1.0, 0.28)
MAT_PURPLE = mat("MAT-v35_purple", (0.38, 0.04, 0.65, 1), 0.0, 0.33)
MAT_DISPLAY = mat("MAT-v35_display", (0.01, 0.06, 0.12, 1), 0.0, 0.20, ((0.03, 0.34, 0.8, 1), 0.55))


def link_to_col(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def box(name, loc, dims, material, bevel=0.0015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = link_to_col(bpy.context.object)
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def cyl(name, loc, radius, depth, material, rotation=(math.pi / 2, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link_to_col(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def text(name, body, loc, size, material, align="CENTER"):
    curve = bpy.data.curves.new(name + "_DATA", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.00035
    curve.bevel_depth = 0.00008
    obj = bpy.data.objects.new(name, curve)
    COL.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)  # face forward to the -Y review camera
    obj.data.materials.append(material)
    return obj


def curve(name, points, material, radius=0.0016):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
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


def sensor_group(key, label, center_x, center_z, board_mat, cap_mat, kind):
    """Five separately identifiable modules on a category carrier."""
    box("MESH_V35_RACK_" + key, (center_x, -0.127, center_z), (0.132, 0.011, 0.054), MAT_BLACK, 0.002)
    box("MESH_V35_RACK_FACE_" + key, (center_x, -0.134, center_z), (0.122, 0.003, 0.044), board_mat, 0.001)
    text("GEO_V35_LABEL_" + key, label + " ×5", (center_x, -0.137, center_z + 0.038), 0.010, MAT_WHITE)
    for i in range(5):
        x = center_x - 0.043 + i * 0.0215
        n = i + 1
        box("MESH_V35_" + key + "_%02d_PCB" % n, (x, -0.140, center_z - 0.004), (0.0155, 0.004, 0.023), MAT_PCB, 0.0007)
        # A contrasting body makes the five physical sensing heads readable.
        if kind == "electrochemical":
            cyl("MESH_V35_" + key + "_%02d_HEAD" % n, (x, -0.145, center_z + 0.007), 0.0065, 0.004, cap_mat)
        elif kind == "mq":
            cyl("MESH_V35_" + key + "_%02d_HEAD" % n, (x, -0.146, center_z + 0.006), 0.0075, 0.006, MAT_STEEL)
            cyl("MESH_V35_" + key + "_%02d_CORE" % n, (x, -0.150, center_z + 0.006), 0.0042, 0.002, cap_mat)
        elif kind == "flame":
            cyl("MESH_V35_" + key + "_%02d_HEAD" % n, (x, -0.146, center_z + 0.006), 0.0058, 0.006, MAT_BLACK)
            cyl("MESH_V35_" + key + "_%02d_LENS" % n, (x, -0.150, center_z + 0.006), 0.0032, 0.0015, cap_mat)
        else:  # temperature/humidity vented package
            box("MESH_V35_" + key + "_%02d_HEAD" % n, (x, -0.146, center_z + 0.006), (0.010, 0.004, 0.010), cap_mat, 0.0009)
        text("GEO_V35_" + key + "_%02d_ID" % n, str(n), (x, -0.151, center_z - 0.018), 0.0056, MAT_WHITE)
        curve("GEO_V35_" + key + "_%02d_CABLE" % n,
              [(x, -0.138, center_z - 0.014), (x, -0.124, center_z - 0.025), (center_x, -0.118, center_z - 0.035)],
              board_mat, 0.0008)


# C-zone: 30 named sensor modules, grouped by sensing mechanism and colour.
sensor_group("O2_ME2", "ME2-O2", -0.150, 0.333, MAT_CYAN, MAT_WHITE, "electrochemical")
sensor_group("CO_MQ7", "MQ-7 / CO", 0.000, 0.333, MAT_RED, MAT_ORANGE, "mq")
sensor_group("CH4_MQ4", "MQ-4 / CH4", 0.150, 0.333, MAT_GREEN := mat("MAT-v35_green", (0.02, 0.60, 0.16, 1), 0.0, 0.36), MAT_YELLOW, "mq")
sensor_group("SMOKE_MQ2", "MQ-2 / SMOKE", -0.150, 0.253, MAT_ORANGE, MAT_WHITE, "mq")
sensor_group("FLAME", "FLAME 4W", 0.000, 0.253, MAT_RED, MAT_YELLOW, "flame")
sensor_group("TH", "SHT30 / DHT22", 0.150, 0.253, MAT_BLUE, MAT_CYAN, "th")
text("GEO_V35_SENSOR_ARRAY_TITLE", "V3.5 MULTI-GAS SENSOR ARRAY  |  6 TYPES × 5", (0.0, -0.137, 0.388), 0.0115, MAT_YELLOW)

# H-28 to H-34 interface planning board, located in the dry A-zone.
box("MESH_V35_INTERFACE_BACKPLANE", (-0.185, -0.196, 0.240), (0.115, 0.008, 0.111), MAT_BLACK, 0.002)
text("GEO_V35_INTERFACE_TITLE", "V3.5 I/O", (-0.185, -0.202, 0.291), 0.009, MAT_WHITE)
interface_specs = [
    ("H28_ADC_AFE", "H-28 ADC / AFE", 0.270, MAT_CYAN),
    ("H29_I2C_MUX", "H-29 I2C MUX", 0.250, MAT_BLUE),
    ("H30_MQ_DRIVE", "H-30 MQ ×15", 0.230, MAT_ORANGE),
    ("H31_FAN_PWM", "H-31 FAN PWM/TACH", 0.210, MAT_PURPLE),
]
for key, label, z, color in interface_specs:
    box("MESH_V35_" + key, (-0.185, -0.203, z), (0.090, 0.006, 0.015), color, 0.001)
    text("GEO_V35_" + key + "_LABEL", label, (-0.185, -0.207, z), 0.0060, MAT_WHITE)
for p, z in enumerate((0.270, 0.250, 0.230, 0.210)):
    curve("GEO_V35_BACKPLANE_CABLE_%02d" % (p + 1), [(-0.130, -0.202, z), (-0.095, -0.175, z), (-0.085, -0.148, 0.215)], MAT_WHITE, 0.0011)

# Actual named controller-side modules.
box("MESH_V35_K210_01", (-0.190, -0.208, 0.170), (0.043, 0.007, 0.026), MAT_BLUE, 0.0012)
box("MESH_V35_K210_01_DISPLAY", (-0.190, -0.213, 0.170), (0.027, 0.002, 0.014), MAT_DISPLAY, 0.0004)
text("GEO_V35_K210_LABEL", "K210", (-0.190, -0.216, 0.151), 0.0065, MAT_WHITE)
box("MESH_V35_SU03T1_01", (-0.132, -0.208, 0.170), (0.040, 0.007, 0.026), MAT_GREEN, 0.0012)
for i in range(3):
    cyl("GEO_V35_SU03T1_MIC_%02d" % (i + 1), (-0.145 + i * 0.013, -0.214, 0.170), 0.0026, 0.0018, MAT_BLACK)
text("GEO_V35_SU03T1_LABEL", "SU-03T1", (-0.132, -0.216, 0.151), 0.0058, MAT_WHITE)
for i, x in enumerate((-0.244, -0.270)):
    box("MESH_V35_ESP8266_01S_%02d" % (i + 1), (x, -0.205, 0.293), (0.020, 0.007, 0.029), MAT_BLUE, 0.001)
    text("GEO_V35_ESP8266_01S_%02d_LABEL" % (i + 1), "ESP%02d" % (i + 1), (x, -0.210, 0.278), 0.0045, MAT_WHITE)
box("MESH_V35_JQC3FFSZ_01", (-0.244, -0.205, 0.247), (0.040, 0.010, 0.024), MAT_BLUE, 0.0016)
text("GEO_V35_JQC3FFSZ_LABEL", "JQC-3FF-S-Z", (-0.244, -0.212, 0.228), 0.0051, MAT_WHITE)

# DCP-3620: keep the type/quantity visible but avoid inventing its function.
box("MESH_V35_DCP3620_01", (-0.244, -0.205, 0.205), (0.048, 0.010, 0.020), MAT_STEEL, 0.0015)
text("GEO_V35_DCP3620_LABEL", "DCP-3620 / TBD", (-0.244, -0.212, 0.188), 0.0054, MAT_YELLOW)

# Second fan (first fan is the pre-existing V10 MESH_FAN_01); do not infer a
# water connection. Both fans get four clearly colour-coded tail wires.
fan_x, fan_y, fan_z = (0.424, -0.095, 0.232)
box("MESH_V35_FAN_02_FRAME", (fan_x, fan_y, fan_z), (0.071, 0.012, 0.071), MAT_BLACK, 0.002)
cyl("MESH_V35_FAN_02_HUB", (fan_x, fan_y - 0.008, fan_z), 0.010, 0.005, MAT_STEEL)
for a in range(0, 360, 90):
    blade = box("GEO_V35_FAN_02_BLADE_%03d" % a, (fan_x, fan_y - 0.006, fan_z + 0.015), (0.009, 0.004, 0.030), MAT_CYAN, 0.001)
    blade.rotation_euler[1] = math.radians(a)
for i, c in enumerate((MAT_RED, MAT_BLACK, MAT_YELLOW, MAT_BLUE)):
    curve("GEO_V35_FAN_02_WIRE_%02d" % (i + 1), [(fan_x - 0.026 + i * 0.006, fan_y - 0.004, fan_z - 0.030), (fan_x - 0.026 + i * 0.006, -0.120, 0.188), (0.270 + i * 0.006, -0.150, 0.185)], c, 0.0012)
text("GEO_V35_FAN_02_LABEL", "FAN-02  12V / PWM / TACH", (fan_x, -0.112, 0.183), 0.0057, MAT_WHITE)

# Inventory-only pump: on the B-zone reserve shelf, intentionally no hoses.
box("MESH_V35_PUMP24V_RESERVE_BASE", (0.155, -0.145, 0.145), (0.083, 0.042, 0.010), MAT_STEEL, 0.0015)
cyl("MESH_V35_PUMP24V_RESERVE_MOTOR", (0.155, -0.145, 0.162), 0.016, 0.040, MAT_RED, rotation=(0, math.pi / 2, 0))
cyl("MESH_V35_PUMP24V_RESERVE_PORT_A", (0.126, -0.145, 0.162), 0.007, 0.016, MAT_STEEL, rotation=(0, math.pi / 2, 0))
cyl("MESH_V35_PUMP24V_RESERVE_PORT_B", (0.184, -0.145, 0.162), 0.007, 0.016, MAT_STEEL, rotation=(0, math.pi / 2, 0))
text("GEO_V35_PUMP24V_LABEL", "24V PUMP / RESERVE\nNOT PIPED", (0.155, -0.178, 0.140), 0.0064, MAT_YELLOW)
text("GEO_V35_WATER_SAFETY_LABEL", "DRY TRAY  ≤50 ml  /  MANUAL DRAIN", (0.014, -0.176, 0.118), 0.0072, MAT_WHITE)


def look_at(obj, point):
    direction = mathutils.Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


import mathutils
cam = SCENE.camera
for name in ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"):
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (0.99, -1.22, 0.82)
cam.data.lens = 60
look_at(cam, (0.0, -0.02, 0.230))
SCENE.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

# Isolate hardware-facing view by opening acrylic only for this explanatory render.
state = {}
for name in ("MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"):
    if name in bpy.data.objects:
        state[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
# The middle rib is structural in the complete model, but hiding it only for
# this audit render keeps the central CO and flame five-packs verifiable.
detail_occluders = (
    "GEO_ZONE_A_RIB", "GEO_ZONE_B_RIB", "GEO_ZONE_C_RIB",
    "GEO_ACRYLIC_SERVICE_SEAM_01", "GEO_ACRYLIC_SERVICE_SEAM_02", "GEO_ACRYLIC_SERVICE_SEAM_03",
)
detail_states = {}
for name in detail_occluders:
    if name in bpy.data.objects:
        detail_states[name] = bpy.data.objects[name].hide_render
        bpy.data.objects[name].hide_render = True
cam.location = (0.0, -0.96, 0.47)
cam.data.lens = 58
look_at(cam, (0.0, -0.13, 0.300))
SCENE.render.filepath = DETAIL_OUT
bpy.ops.render.render(write_still=True)
for name, hidden in detail_states.items():
    bpy.data.objects[name].hide_render = hidden

cam.location = (-0.62, -0.66, 0.42)
cam.data.lens = 75
look_at(cam, (-0.205, -0.202, 0.235))
SCENE.render.filepath = CONTROL_OUT
bpy.ops.render.render(write_still=True)
for name, hidden in state.items():
    bpy.data.objects[name].hide_render = hidden

# Export every visible model object, including the new V3.5 collection.
bpy.ops.object.select_all(action="DESELECT")
for obj in bpy.context.scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print({"V11_V35_DONE": True, "new_collection": len(COL.objects), "blend": BLEND_OUT, "glb": GLB_OUT})
