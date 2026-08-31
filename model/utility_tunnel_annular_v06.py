"""V06: establish a visible, serviceable PCB control bay in Zone A.

V05 remains the preserved candidate.  This deterministic wrapper places the
main PCB in the dry controller bay, creates terminal and cable-routing detail,
and emits versioned V06 artifacts without altering the published web model.
"""
import bpy
import math
import os
import runpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V05_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v05.py")
V06_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v06.blend")
V06_GLB = os.path.join(ROOT, "utility-tunnel-annular-v06.glb")
V06_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v06-hero.png")
V06_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v06-functional.png")
V06_PCB_DETAIL = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v06-pcb-detail.png")

# Rebuild the validated V05 candidate first; V05 itself rebuilds V04.
v05 = runpy.run_path(V05_SCRIPT)
MODEL = v05["MODEL"]
SCENE = v05["SCENE"]
add_box = v05["add_box"]
add_uvsphere = v05["add_uvsphere"]
add_text = v05["add_text"]
look_at = v05["look_at"]
MAT_FRAME = v05["MAT_FRAME"]
MAT_ORANGE = v05["MAT_ORANGE"]
MAT_RED = v05["MAT_RED"]
MAT_GREEN = v05["MAT_GREEN"]
MAT_WHITE = v05["MAT_WHITE"]

MAT_PCB = bpy.data.materials["MAT-sensor_green"]
MAT_CABLE = MAT_FRAME
PCB_CENTER = Vector((-0.320, -0.205, 0.216))


def add_cable(name, points, material, radius=0.0025):
    """Create a named, smooth low-voltage signal lead in the model collection."""
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    MODEL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


# A-zone dry electrical bay: board face looks toward the front acrylic wall
# (negative Y) for inspection, but is clear of the water tray in Zone B.
pcb = bpy.data.objects["MESH_PCB_01"]
pcb.rotation_euler = (math.radians(90), 0.0, 0.0)
bpy.context.view_layer.update()
pcb.dimensions = (0.100, 0.008, 0.070)
pcb.location = PCB_CENTER
pcb.data.materials.clear()
pcb.data.materials.append(MAT_PCB)

# Mechanical attachment: an insulated plate, four standoffs and a guard frame
# make the board visibly serviceable rather than a floating green block.
add_box("MESH_PCB_01_MOUNT_PLATE", (-0.320, -0.197, 0.216), (0.122, 0.006, 0.095), MAT_FRAME, bevel=0.003)
for suffix, x, z in (("TL", -0.366, 0.246), ("TR", -0.274, 0.246), ("BL", -0.366, 0.186), ("BR", -0.274, 0.186)):
    add_uvsphere("GEO_PCB_01_STANDOFF_" + suffix, (x, -0.211, z), 0.005, MAT_WHITE)
for suffix, x, z, dims in (
    ("TOP", -0.320, 0.261, (0.122, 0.008, 0.007)),
    ("BOTTOM", -0.320, 0.171, (0.122, 0.008, 0.007)),
    ("LEFT", -0.381, 0.216, (0.007, 0.008, 0.097)),
    ("RIGHT", -0.259, 0.216, (0.007, 0.008, 0.097)),
):
    add_box("GEO_PCB_01_GUARD_" + suffix, (x, -0.214, z), dims, MAT_FRAME, bevel=0.002)

# Board-level components visibly distinguish the controller PCB from a generic
# sensor module: controller IC, isolated power module, status LEDs and I/O rail.
add_box("GEO_PCB_01_CPU", (-0.329, -0.211, 0.224), (0.031, 0.005, 0.023), MAT_FRAME, bevel=0.002)
add_box("GEO_PCB_01_POWER_ISO", (-0.354, -0.211, 0.211), (0.018, 0.005, 0.018), MAT_ORANGE, bevel=0.002)
for suffix, x, material in (("PWR", -0.344, MAT_GREEN), ("RUN", -0.332, MAT_WHITE), ("ALM", -0.320, MAT_RED)):
    add_uvsphere("GEO_PCB_01_LED_" + suffix, (x, -0.213, 0.244), 0.0035, material)

terminal_specs = [
    ("PWR", -0.356, MAT_ORANGE), ("CH4", -0.338, MAT_ORANGE),
    ("CO", -0.320, MAT_RED), ("O2", -0.302, MAT_GREEN), ("FAN", -0.284, MAT_WHITE),
]
for suffix, x, material in terminal_specs:
    add_box("MESH_PCB_01_TERM_" + suffix, (x, -0.214, 0.181), (0.013, 0.009, 0.010), material, bevel=0.0015)

# Signal leads leave the lower terminal row and enter the existing front cable
# duct. They are low-voltage demonstrator wiring, not real gas instrumentation.
for suffix, x, material in terminal_specs:
    add_cable(
        "GEO_PCB_01_CABLE_" + suffix,
        [(x, -0.219, 0.177), (x, -0.218, 0.153), (-0.185, -0.205, 0.135), (-0.130, -0.175, 0.125)],
        material,
    )

add_text("GEO_PCB_01_LABEL", "A区主控 PCB · 干区", (-0.320, -0.220, 0.268), 0.012, MAT_WHITE)
add_text("GEO_PCB_01_IO_LABEL", "PWR  CH4  CO  O2  FAN", (-0.320, -0.220, 0.160), 0.008, MAT_WHITE)

# Hero and cutaway preserve V05 framing.  A close view gives fabrication and
# wiring review a dedicated evidence image.
os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
for name in ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.00, -1.22, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V06_HERO
bpy.ops.render.render(write_still=True)

cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V06_FUNCTION
bpy.ops.render.render(write_still=True)

cam.location = (-0.73, -0.78, 0.52)
cam.data.lens = 64
look_at(cam, (-0.320, -0.195, 0.216))
SCENE.render.filepath = V06_PCB_DETAIL
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

# Runtime GLB retains geometry/curves and omits only high-cost rendered fonts.
bpy.ops.object.select_all(action="DESELECT")
for obj in MODEL.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(
    filepath=V06_GLB, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_cameras=False, export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=V06_BLEND)
print({"V06_DONE": True, "blend": V06_BLEND, "glb": V06_GLB})
