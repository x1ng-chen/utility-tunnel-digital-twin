"""V07: physically legible low-voltage air-intake and sampling hardware.

Air path: exterior weather hood -> replaceable filter -> flow meter ->
diaphragm pump -> check valve -> sampling manifold / annular G01 pipe -> vent.
V06 is preserved and this wrapper only writes versioned V07 artifacts.
"""
import bpy
import math
import os
import runpy

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V06_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v06.py")
V07_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v07.blend")
V07_GLB = os.path.join(ROOT, "utility-tunnel-annular-v07.glb")
V07_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v07-hero.png")
V07_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v07-functional.png")
V07_AIR_DETAIL = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v07-air-intake-detail.png")

v06 = runpy.run_path(V06_SCRIPT)
MODEL = v06["MODEL"]
SCENE = v06["SCENE"]
add_box = v06["add_box"]
add_uvsphere = v06["add_uvsphere"]
add_text = v06["add_text"]
look_at = v06["look_at"]
MAT_FRAME = v06["MAT_FRAME"]
MAT_ORANGE = v06["MAT_ORANGE"]
MAT_RED = v06["MAT_RED"]
MAT_GREEN = v06["MAT_GREEN"]
MAT_WHITE = v06["MAT_WHITE"]
MAT_CYAN = bpy.data.materials["MAT-sensor_cyan"]
MAT_ACRYLIC = bpy.data.materials["MAT-acrylic_clearblue"]


def relink_to_model(obj):
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)
    MODEL.objects.link(obj)
    return obj


def add_cylinder(name, location, radius, depth, material, rotation=(0.0, 0.0, 0.0), vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = relink_to_model(bpy.context.active_object)
    obj.name = name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def add_torus(name, location, major_radius, minor_radius, material, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major_radius, minor_radius=minor_radius, major_segments=32, minor_segments=8, location=location, rotation=rotation)
    obj = relink_to_model(bpy.context.active_object)
    obj.name = name
    obj.data.materials.append(material)
    return obj


def add_hose(name, points, material=MAT_CYAN, radius=0.004):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, co in zip(spline.bezier_points, points):
        point.co = co
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    MODEL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


# --- External intake: a flanged rain hood at the right-hand exterior wall. ---
# The outermost edge stays inside the 1.0 m project envelope.
add_cylinder("MESH_AIR_IN_01_WEATHER_FLANGE", (0.477, -0.052, 0.235), 0.043, 0.008, MAT_FRAME, rotation=(0.0, math.pi / 2, 0.0))
add_cylinder("MESH_AIR_IN_01_WEATHER_GRILLE", (0.486, -0.052, 0.235), 0.036, 0.012, MAT_CYAN, rotation=(0.0, math.pi / 2, 0.0))
add_box("MESH_AIR_IN_01_WEATHER_HOOD", (0.480, -0.052, 0.280), (0.026, 0.095, 0.012), MAT_FRAME, bevel=0.003)
for index, z in enumerate((0.217, 0.232, 0.247, 0.262)):
    add_box("GEO_AIR_IN_01_LOUVER_%02d" % index, (0.493, -0.052, z), (0.008, 0.068, 0.004), MAT_FRAME, bevel=0.001)
add_text("GEO_AIR_IN_01_WEATHER_LABEL", "外界进气 / 防雨罩", (0.455, -0.112, 0.293), 0.010, MAT_WHITE)

# --- Replaceable inline filter: clear body with dark caps and a paper element. ---
add_cylinder("MESH_AIR_FILTER_CARTRIDGE_01", (0.423, -0.052, 0.235), 0.026, 0.060, MAT_ACRYLIC, rotation=(0.0, math.pi / 2, 0.0))
for index, x in enumerate((0.393, 0.453)):
    add_cylinder("GEO_AIR_FILTER_CAP_%02d" % index, (x, -0.052, 0.235), 0.030, 0.009, MAT_FRAME, rotation=(0.0, math.pi / 2, 0.0))
    add_torus("GEO_AIR_FILTER_SEAL_%02d" % index, (x + (-0.005 if index == 0 else 0.005), -0.052, 0.235), 0.027, 0.0025, MAT_ORANGE, rotation=(0.0, math.pi / 2, 0.0))
for x in (0.406, 0.418, 0.430, 0.442):
    add_torus("GEO_AIR_FILTER_RIB_%03d" % int(x * 1000), (x, -0.052, 0.235), 0.022, 0.0015, MAT_WHITE, rotation=(0.0, math.pi / 2, 0.0))

# --- Metering and pumping hardware: recognizable 12 V demonstrator parts. ---
add_box("MESH_AIR_FLOW_METER_01_BASE", (0.378, -0.052, 0.213), (0.035, 0.035, 0.011), MAT_FRAME, bevel=0.002)
add_cylinder("MESH_AIR_FLOW_METER_01", (0.378, -0.052, 0.244), 0.012, 0.052, MAT_ACRYLIC, vertices=24)
for index, z in enumerate((0.230, 0.243, 0.256)):
    add_box("GEO_AIR_FLOW_METER_TICK_%02d" % index, (0.391, -0.066, z), (0.010, 0.003, 0.002), MAT_WHITE, bevel=0.0006)
add_uvsphere("GEO_AIR_FLOW_METER_FLOAT", (0.378, -0.052, 0.246), 0.005, MAT_ORANGE)

add_box("MESH_AIR_PUMP_01", (0.343, -0.053, 0.276), (0.055, 0.048, 0.050), MAT_FRAME, bevel=0.005)
add_cylinder("GEO_AIR_PUMP_01_DIAPHRAGM", (0.343, -0.081, 0.276), 0.022, 0.010, MAT_CYAN, rotation=(math.pi / 2, 0.0, 0.0))
add_cylinder("GEO_AIR_PUMP_01_INLET", (0.375, -0.053, 0.276), 0.007, 0.020, MAT_FRAME, rotation=(0.0, math.pi / 2, 0.0))
add_cylinder("GEO_AIR_PUMP_01_OUTLET", (0.311, -0.053, 0.276), 0.007, 0.020, MAT_FRAME, rotation=(0.0, math.pi / 2, 0.0))
for suffix, x, z in (("TL", 0.363, 0.294), ("TR", 0.323, 0.294), ("BL", 0.363, 0.258), ("BR", 0.323, 0.258)):
    add_uvsphere("GEO_AIR_PUMP_01_SCREW_" + suffix, (x, -0.081, z), 0.003, MAT_WHITE)

add_cylinder("MESH_AIR_CHECK_VALVE_01", (0.294, -0.058, 0.285), 0.012, 0.038, MAT_FRAME, rotation=(0.0, math.pi / 2, 0.0))
add_cone = None
bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=0.012, radius2=0.006, depth=0.020, location=(0.294, -0.058, 0.285), rotation=(0.0, -math.pi / 2, 0.0))
valve_arrow = relink_to_model(bpy.context.active_object)
valve_arrow.name = "GEO_AIR_CHECK_VALVE_01_ARROW"
valve_arrow.data.materials.append(MAT_ORANGE)

# Rebuild the existing required AIR_IN route as the one physical flexible hose
# rather than showing an ambiguous parallel line.  Each waypoint lands on a
# real fitting: hood, filter, meter, pump, check valve and sampling manifold.
main_route = bpy.data.objects["MESH_AIR_IN_01_SAFE_ROUTE"]
main_route.location = (0.0, 0.0, 0.0)
main_route.scale = (1.0, 1.0, 1.0)
main_path = [
    (0.493, -0.052, 0.235), (0.453, -0.052, 0.235),
    (0.393, -0.052, 0.235), (0.378, -0.052, 0.221),
    (0.378, -0.052, 0.270), (0.375, -0.053, 0.276),
    (0.311, -0.053, 0.276), (0.275, -0.058, 0.285),
    (0.264, -0.078, 0.266),
]
for spline in list(main_route.data.splines):
    main_route.data.splines.remove(spline)
main_spline = main_route.data.splines.new("BEZIER")
main_spline.bezier_points.add(len(main_path) - 1)
for point, co in zip(main_spline.bezier_points, main_path):
    point.co = co
    point.handle_left_type = "AUTO"
    point.handle_right_type = "AUTO"
main_route.data.bevel_depth = 0.004
main_route.data.bevel_resolution = 3

# Branches explicitly show that the pump-fed manifold samples CH4, CO and O2
# positions around the annular pipe before the original route reaches the vent.
for suffix, points, material in (
    ("CH4", [(0.250, -0.080, 0.263), (0.120, -0.091, 0.240), (-0.148, -0.096, 0.231)], MAT_ORANGE),
    ("CO", [(0.250, -0.080, 0.263), (0.200, -0.090, 0.240), (0.148, -0.096, 0.231)], MAT_RED),
    ("O2", [(0.265, -0.070, 0.263), (0.300, -0.030, 0.245), (0.338, 0.000, 0.241)], MAT_GREEN),
):
    add_hose("GEO_AIR_SAMPLE_BRANCH_" + suffix, points, material, radius=0.0028)

add_text("GEO_AIR_FLOW_LABEL_01", "过滤", (0.423, -0.102, 0.190), 0.009, MAT_WHITE)
add_text("GEO_AIR_FLOW_LABEL_02", "流量计", (0.378, -0.102, 0.190), 0.009, MAT_WHITE)
add_text("GEO_AIR_FLOW_LABEL_03", "12V抽气泵", (0.343, -0.105, 0.240), 0.009, MAT_WHITE)
add_text("GEO_AIR_FLOW_LABEL_04", "止回阀", (0.294, -0.100, 0.305), 0.008, MAT_WHITE)
add_text("GEO_AIR_FLOW_CHAIN", "进气 → 过滤 → 计量 → 抽气 → 环形采样 → 顶部排气", (0.155, -0.180, 0.150), 0.010, MAT_WHITE)

# Renders: overview, enclosure-open function view, and an intake close-up.
os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
for name in cutaway_names:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.00, -1.22, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V07_HERO
bpy.ops.render.render(write_still=True)

states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V07_FUNCTION
bpy.ops.render.render(write_still=True)

cam.location = (0.77, -0.67, 0.48)
cam.data.lens = 68
look_at(cam, (0.355, -0.058, 0.260))
SCENE.render.filepath = V07_AIR_DETAIL
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

bpy.ops.object.select_all(action="DESELECT")
for obj in MODEL.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(
    filepath=V07_GLB, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_cameras=False, export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=V07_BLEND)
print({"V07_DONE": True, "blend": V07_BLEND, "glb": V07_GLB})
