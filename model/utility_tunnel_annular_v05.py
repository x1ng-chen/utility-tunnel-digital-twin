"""V05 refinement of the classroom-safe annular utility-tunnel demonstrator.

The V04 source remains the preserved candidate. This wrapper normalizes the
aggregate envelope to the V3.3 target and improves C-zone sensor visibility.
It emits new V05 files and never overwrites the published V04 web GLB.
"""
import bpy
import os
import runpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V04_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v04.py")
V05_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v05.blend")
V05_GLB = os.path.join(ROOT, "utility-tunnel-annular-v05.glb")
V05_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v05-hero.png")
V05_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v05-functional.png")
TARGET_EXTENTS = Vector((1.000, 0.500, 0.420))

# Rebuild the preserved candidate using its deterministic source.
v04 = runpy.run_path(V04_SCRIPT)
MODEL = v04["MODEL"]
SCENE = v04["SCENE"]
add_box = v04["add_box"]
add_uvsphere = v04["add_uvsphere"]
add_text = v04["add_text"]
look_at = v04["look_at"]
MAT_FRAME = v04["MAT_FRAME"]
MAT_ORANGE = v04["MAT_ORANGE"]
MAT_RED = v04["MAT_RED"]
MAT_GREEN = v04["MAT_GREEN"]
MAT_WHITE = v04["MAT_WHITE"]

# The physical enclosure remains present, while the clearer material lets
# observers identify the internal sensor group without opening a service hatch.
acrylic = bpy.data.materials["MAT-acrylic_clearblue"]
acrylic.diffuse_color[3] = 0.018
for node in acrylic.node_tree.nodes:
    if node.type == "BSDF_PRINCIPLED" and node.inputs.get("Alpha"):
        node.inputs["Alpha"].default_value = 0.018


def model_objects():
    return [obj for obj in MODEL.objects if obj.type in {"MESH", "CURVE", "FONT"}]


def world_bounds(objects):
    points = []
    for obj in objects:
        if not getattr(obj, "bound_box", None):
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    low = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    high = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return low, high


# Normalize against the aggregate bounds, not just the base mesh.
bpy.context.view_layer.update()
before_low, before_high = world_bounds(model_objects())
before_size = before_high - before_low
layout_scale = Vector((TARGET_EXTENTS.x / before_size.x, TARGET_EXTENTS.y / before_size.y, TARGET_EXTENTS.z / before_size.z))
center = (before_low + before_high) * 0.5
for obj in model_objects():
    relative = obj.location - center
    obj.location = Vector((relative.x * layout_scale.x, relative.y * layout_scale.y, relative.z * layout_scale.z))
    obj.scale = Vector((obj.scale.x * layout_scale.x, obj.scale.y * layout_scale.y, obj.scale.z * layout_scale.z))
bpy.context.view_layer.update()

# The physical model is measured upward from the base datum.  Scaling around
# the aggregate centre would otherwise place part of the assembly below Z=0.
scaled_low, _ = world_bounds(model_objects())
for obj in model_objects():
    obj.location.z -= scaled_low.z
bpy.context.view_layer.update()

# Dedicated backplates, colour bars and beacons improve sensor recognition
# through the transparent enclosure while retaining the canonical mesh names.
sensor_specs = [
    ("CH4", "MESH_GAS_CH4_01", MAT_ORANGE, "CH4"),
    ("CO", "MESH_GAS_CO_01", MAT_RED, "CO"),
    ("O2", "MESH_GAS_O2_01", MAT_GREEN, "O2"),
]
for sensor_id, mesh_name, colour, label in sensor_specs:
    sensor = bpy.data.objects[mesh_name]
    sx, sy, sz = sensor.dimensions
    add_box(
        "MESH_GAS_%s_01_BACKPLATE" % sensor_id,
        (sensor.location.x, sensor.location.y + sy * 0.52, sensor.location.z),
        (sx * 1.24, 0.010, sz * 1.55), MAT_FRAME, bevel=0.003,
    )
    add_box(
        "GEO_GAS_%s_01_STATUS_STRIP" % sensor_id,
        (sensor.location.x, sensor.location.y + sy * 0.57, sensor.location.z + sz * 0.46),
        (sx * 0.62, 0.006, 0.008), colour, bevel=0.0015,
    )
    add_uvsphere(
        "GEO_GAS_%s_01_BEACON" % sensor_id,
        (sensor.location.x + sx * 0.46, sensor.location.y - sy * 0.68, sensor.location.z + sz * 0.36),
        0.008, colour,
    )
    add_text(
        "GEO_GAS_%s_01_PANEL_LABEL" % sensor_id,
        label,
        (sensor.location.x, sensor.location.y - sy * 0.72, sensor.location.z - sz * 0.42),
        0.013, colour,
    )

ch4 = bpy.data.objects["MESH_GAS_CH4_01"].location
co = bpy.data.objects["MESH_GAS_CO_01"].location
o2 = bpy.data.objects["MESH_GAS_O2_01"].location
rail_x = (ch4.x + o2.x) * 0.5
rail_y = min(ch4.y, co.y, o2.y) + 0.028
rail_z = min(ch4.z, co.z, o2.z) - 0.050
add_box("MESH_GAS_SENSOR_RAIL_C01", (rail_x, rail_y, rail_z), (abs(o2.x - ch4.x) + 0.085, 0.016, 0.016), MAT_FRAME, bevel=0.003)
add_text("GEO_GAS_SENSOR_RAIL_LABEL", "C 区多气体传感器", (rail_x, rail_y - 0.016, rail_z - 0.018), 0.012, MAT_WHITE)

# Re-render the same hero/cutaway evidence convention without changing V04.
os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
cam.location = (0.98, -1.18, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.205))
SCENE.render.filepath = V05_HERO
bpy.ops.render.render(write_still=True)

cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.205))
SCENE.render.filepath = V05_FUNCTION
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

bpy.ops.object.select_all(action="DESELECT")
# Labels remain in the editable Blend and evidence renders.  They are excluded
# from the runtime GLB because tessellated CJK text dominates the triangle
# budget while the platform provides its own asset labels on selection.
for obj in model_objects():
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(
    filepath=V05_GLB, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_cameras=False, export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=V05_BLEND)

bpy.context.view_layer.update()
after_low, after_high = world_bounds(model_objects())
after_size = after_high - after_low
required = [
    "MESH_PIPE_G01", "MESH_AIR_IN_01_FILTER_PORT", "MESH_AIR_IN_01_SAFE_ROUTE",
    "MESH_FAN_01", "MESH_VENT_01", "MESH_WATER_TRAY", "MESH_WATER_DROP_01",
    "MESH_HILEVEL_01", "MESH_CTRL_01", "MESH_SIMBOX_01", "MESH_GAS_CH4_01",
    "MESH_GAS_CO_01", "MESH_GAS_O2_01",
]
missing = [name for name in required if bpy.data.objects.get(name) is None]
print({
    "V05_DONE": not missing,
    "missing": missing,
    "before_size_m": tuple(round(value, 6) for value in before_size),
    "after_size_m": tuple(round(value, 6) for value in after_size),
    "blend": V05_BLEND,
    "glb": V05_GLB,
})
