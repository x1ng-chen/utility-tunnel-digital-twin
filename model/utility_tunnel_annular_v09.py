"""V09: make the B-zone water demo tray physically safer and more legible.

The tray remains an independent, low-volume (<50 mL) teaching-water module:
raised rim, sight gauge, high-level marker, manual drain valve and no recirculation.
"""
import bpy
import math
import os
import runpy

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V08_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v08.py")
V09_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v09.blend")
V09_GLB = os.path.join(ROOT, "utility-tunnel-annular-v09.glb")
V09_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v09-hero.png")
V09_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v09-functional.png")
V09_WATER_DETAIL = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v09-water-detail.png")

v08 = runpy.run_path(V08_SCRIPT)
MODEL = v08["MODEL"]
SCENE = v08["SCENE"]
add_box = v08["add_box"]
add_uvsphere = v08["add_uvsphere"]
add_cylinder = v08["add_cylinder"]
add_torus = v08["v07"]["add_torus"]
add_hose = v08["add_hose"]
look_at = v08["look_at"]
MAT_FRAME = v08["MAT_FRAME"]
MAT_ORANGE = v08["MAT_ORANGE"]
MAT_RED = v08["MAT_RED"]
MAT_WHITE = v08["MAT_WHITE"]
MAT_CYAN = bpy.data.materials["MAT-sensor_cyan"]
MAT_WATER = bpy.data.materials["MAT-water"]
MAT_ACRYLIC = bpy.data.materials["MAT-acrylic_clearblue"]

# Inner, removable catch pan with three raised sides. The existing base tray
# remains the required platform node; this makes the functional shape readable.
add_box("MESH_WATER_TRAY_INNER_PAN", (0.014, -0.131, 0.145), (0.148, 0.055, 0.010), MAT_FRAME, bevel=0.002)
for suffix, location, dims in (
    ("FRONT_LIP", (0.014, -0.164, 0.170), (0.154, 0.006, 0.045)),
    ("REAR_LIP", (0.014, -0.098, 0.170), (0.154, 0.006, 0.045)),
    ("RIGHT_LIP", (0.091, -0.131, 0.170), (0.006, 0.072, 0.045)),
):
    add_box("GEO_WATER_TRAY_" + suffix, location, dims, MAT_CYAN, bevel=0.002)

# A shallow blue level surface and an orange physical maximum-fill marker
# communicate a teaching-only water volume rather than a recirculating system.
add_box("GEO_WATER_50ML_LEVEL", (0.014, -0.131, 0.160), (0.132, 0.046, 0.004), MAT_WATER, bevel=0.001)
add_box("GEO_WATER_MAX_FILL_MARK", (0.035, -0.166, 0.177), (0.085, 0.004, 0.004), MAT_ORANGE, bevel=0.001)

# Transparent vertical sight gauge and a separate high-level float give two
# visibly distinct measurement modes: continuous level and discrete alarm.
add_cylinder("MESH_WATER_SIGHT_GAUGE_01", (0.077, -0.157, 0.194), 0.007, 0.070, MAT_ACRYLIC, vertices=24)
add_uvsphere("GEO_WATER_SIGHT_GAUGE_FLOAT", (0.077, -0.157, 0.175), 0.006, MAT_CYAN)
add_torus("GEO_WATER_SIGHT_GAUGE_MAX_RING", (0.077, -0.157, 0.220), 0.008, 0.0018, MAT_ORANGE)
add_box("GEO_WATER_HILEVEL_FLAG", (0.096, -0.157, 0.223), (0.018, 0.004, 0.010), MAT_RED, bevel=0.001)

# Manual drain: brass-style union, red quarter-turn lever, capped outlet and
# a visibly isolated flexible drain lead. It is only a manual emptying path.
add_cylinder("MESH_WATER_DRAIN_VALVE_01", (0.014, -0.176, 0.145), 0.010, 0.026, MAT_FRAME, rotation=(math.pi / 2, 0.0, 0.0), vertices=24)
add_cylinder("GEO_WATER_DRAIN_UNION_01", (0.014, -0.188, 0.145), 0.014, 0.006, MAT_ORANGE, rotation=(math.pi / 2, 0.0, 0.0), vertices=6)
add_box("GEO_WATER_DRAIN_LEVER_01", (0.014, -0.190, 0.160), (0.040, 0.006, 0.006), MAT_RED, bevel=0.002)
add_cylinder("MESH_WATER_DRAIN_CAP_01", (0.014, -0.199, 0.145), 0.012, 0.008, MAT_FRAME, rotation=(math.pi / 2, 0.0, 0.0), vertices=24)
add_hose("MESH_WATER_DRAIN_TUBE_01", [(0.014, -0.199, 0.145), (0.014, -0.210, 0.130), (0.055, -0.210, 0.120)], MAT_CYAN, radius=0.003)

# Partition seal at the dry/wet boundary prevents the water demo from visually
# or mechanically sharing the PCB/control bay.
add_box("GEO_WET_DRY_PARTITION_GASKET", (-0.119, -0.131, 0.145), (0.012, 0.075, 0.008), MAT_FRAME, bevel=0.0015)
for index, y in enumerate((-0.154, -0.131, -0.108)):
    add_uvsphere("GEO_WET_DRY_PARTITION_BOLT_%02d" % index, (-0.125, y, 0.162), 0.003, MAT_WHITE)

# Renders use the established overview convention and a close B-zone view.
os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
for name in cutaway_names:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.00, -1.22, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V09_HERO
bpy.ops.render.render(write_still=True)

states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V09_FUNCTION
bpy.ops.render.render(write_still=True)

cam.location = (0.32, -0.72, 0.36)
cam.data.lens = 70
look_at(cam, (0.014, -0.140, 0.170))
SCENE.render.filepath = V09_WATER_DETAIL
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

bpy.ops.object.select_all(action="DESELECT")
for obj in MODEL.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(
    filepath=V09_GLB, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_cameras=False, export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=V09_BLEND)
print({"V09_DONE": True, "blend": V09_BLEND, "glb": V09_GLB})
