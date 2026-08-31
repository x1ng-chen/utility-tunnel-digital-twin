"""V10: serviceable A-zone low-voltage controller enclosure."""
import bpy
import math
import os
import runpy

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V09_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v09.py")
V10_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v10.blend")
V10_GLB = os.path.join(ROOT, "utility-tunnel-annular-v10.glb")
V10_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v10-hero.png")
V10_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v10-functional.png")
V10_CTRL_DETAIL = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v10-control-detail.png")

v09 = runpy.run_path(V09_SCRIPT)
MODEL = v09["MODEL"]
SCENE = v09["SCENE"]
add_box = v09["add_box"]
add_uvsphere = v09["add_uvsphere"]
add_cylinder = v09["add_cylinder"]
add_hose = v09["add_hose"]
look_at = v09["look_at"]
MAT_FRAME = v09["MAT_FRAME"]
MAT_ORANGE = v09["MAT_ORANGE"]
MAT_RED = v09["MAT_RED"]
MAT_GREEN = bpy.data.materials["MAT-sensor_green"]
MAT_WHITE = v09["MAT_WHITE"]
MAT_ACRYLIC = bpy.data.materials["MAT-acrylic_clearblue"]

# Clear service door and four-piece metal frame protect the board without
# hiding it. The door sits at the A-zone front face, clear of B-zone water.
add_box("MESH_CTRL_SERVICE_DOOR_01", (-0.320, -0.225, 0.216), (0.148, 0.004, 0.128), MAT_ACRYLIC, bevel=0.002)
for suffix, loc, dims in (
    ("TOP", (-0.320, -0.229, 0.280), (0.154, 0.009, 0.008)),
    ("BOTTOM", (-0.320, -0.229, 0.152), (0.154, 0.009, 0.008)),
    ("LEFT", (-0.397, -0.229, 0.216), (0.008, 0.009, 0.136)),
    ("RIGHT", (-0.243, -0.229, 0.216), (0.008, 0.009, 0.136)),
):
    add_box("GEO_CTRL_SERVICE_DOOR_FRAME_" + suffix, loc, dims, MAT_FRAME, bevel=0.002)
add_cylinder("GEO_CTRL_SERVICE_DOOR_HINGE_01", (-0.398, -0.231, 0.198), 0.006, 0.050, MAT_FRAME, vertices=20)
add_cylinder("GEO_CTRL_SERVICE_DOOR_HINGE_02", (-0.398, -0.231, 0.238), 0.006, 0.050, MAT_FRAME, vertices=20)
add_box("GEO_CTRL_SERVICE_DOOR_HANDLE", (-0.253, -0.237, 0.216), (0.008, 0.012, 0.034), MAT_ORANGE, bevel=0.002)

# Equipment arranged behind the PCB: 12 V PSU, fuse and relay rail. These are
# separate from the PCB's sensor I/O terminals and stay in the dry A-zone.
add_box("MESH_PSU_12V_01", (-0.362, -0.188, 0.235), (0.034, 0.020, 0.040), MAT_FRAME, bevel=0.003)
for index, z in enumerate((0.223, 0.235, 0.247)):
    add_box("GEO_PSU_12V_01_VENT_%02d" % index, (-0.362, -0.199, z), (0.024, 0.003, 0.003), MAT_WHITE, bevel=0.0006)
add_box("MESH_FUSE_HOLDER_01", (-0.346, -0.209, 0.180), (0.017, 0.008, 0.015), MAT_ORANGE, bevel=0.0015)
add_box("MESH_RELAY_RAIL_01", (-0.305, -0.188, 0.181), (0.065, 0.012, 0.016), MAT_FRAME, bevel=0.0015)
for index, x in enumerate((-0.327, -0.305, -0.283)):
    add_box("GEO_RELAY_RAIL_MODULE_%02d" % (index + 1), (x, -0.202, 0.185), (0.016, 0.006, 0.020), MAT_GREEN, bevel=0.0015)

# Cable strain relief and grommets make the route into the existing front duct
# appear physically fastened rather than simply drawn in space.
for index, x in enumerate((-0.354, -0.332, -0.310, -0.288)):
    add_cylinder("GEO_CTRL_CABLE_GROMMET_%02d" % (index + 1), (x, -0.228, 0.154), 0.0045, 0.008, MAT_FRAME, rotation=(math.pi / 2, 0.0, 0.0), vertices=20)
    add_hose("GEO_CTRL_CABLE_DROP_%02d" % (index + 1), [(x, -0.231, 0.154), (x, -0.223, 0.140), (x + 0.015, -0.215, 0.130)], MAT_WHITE if index % 2 else MAT_ORANGE, radius=0.0018)

os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
for name in cutaway_names:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.00, -1.22, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V10_HERO
bpy.ops.render.render(write_still=True)

states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V10_FUNCTION
bpy.ops.render.render(write_still=True)

cam.location = (-0.70, -0.72, 0.46)
cam.data.lens = 70
look_at(cam, (-0.320, -0.205, 0.210))
SCENE.render.filepath = V10_CTRL_DETAIL
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

bpy.ops.object.select_all(action="DESELECT")
for obj in MODEL.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=V10_GLB, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=V10_BLEND)
print({"V10_DONE": True, "blend": V10_BLEND, "glb": V10_GLB})
