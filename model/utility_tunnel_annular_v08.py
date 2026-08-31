"""V08: improve flow readability and complete annular sampling interfaces.

This pass keeps V07 as the preserved candidate. It removes floating render
text, uses physical flow indicators, adds quick-connect take-off fittings for
each gas position, and creates a visible return connection to the vent.
"""
import bpy
import math
import os
import runpy

ROOT = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(ROOT, "previews")
V07_SCRIPT = os.path.join(ROOT, "utility_tunnel_annular_v07.py")
V08_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v08.blend")
V08_GLB = os.path.join(ROOT, "utility-tunnel-annular-v08.glb")
V08_HERO = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v08-hero.png")
V08_FUNCTION = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v08-functional.png")
V08_FLOW_DETAIL = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v08-flow-detail.png")

v07 = runpy.run_path(V07_SCRIPT)
MODEL = v07["MODEL"]
SCENE = v07["SCENE"]
add_box = v07["add_box"]
add_uvsphere = v07["add_uvsphere"]
add_cylinder = v07["add_cylinder"]
add_hose = v07["add_hose"]
relink_to_model = v07["relink_to_model"]
look_at = v07["look_at"]
MAT_FRAME = v07["MAT_FRAME"]
MAT_ORANGE = v07["MAT_ORANGE"]
MAT_RED = v07["MAT_RED"]
MAT_GREEN = v07["MAT_GREEN"]
MAT_WHITE = v07["MAT_WHITE"]
MAT_CYAN = bpy.data.materials["MAT-sensor_cyan"]

# In final evidence, labels are represented by physical arrows and colour
# coding; this removes unreadable floating font outlines at model scale.
for obj in MODEL.objects:
    if obj.type == "FONT":
        obj.hide_render = True


def add_arrow(name, center, material, direction=-1):
    """Low-profile rigid flow arrow pointing along X on the visible front side."""
    add_box(name + "_SHAFT", (center[0] + direction * 0.006, center[1], center[2]), (0.020, 0.006, 0.004), material, bevel=0.001)
    bpy.ops.mesh.primitive_cone_add(
        vertices=20, radius1=0.008, radius2=0.0, depth=0.016,
        location=(center[0] + direction * 0.022, center[1], center[2]),
        rotation=(0.0, direction * math.pi / 2, 0.0),
    )
    head = relink_to_model(bpy.context.active_object)
    head.name = name + "_HEAD"
    head.data.materials.append(material)
    return head


# Rigid flow indicators attach to the actual hose stage rather than hovering
# in open space. Direction is exterior (+X) toward the sampling manifold (-X).
for index, center in enumerate(((0.468, -0.109, 0.235), (0.414, -0.109, 0.235), (0.352, -0.109, 0.276))):
    add_arrow("GEO_AIR_FLOW_INDICATOR_%02d" % (index + 1), center, MAT_CYAN, direction=-1)

# Three identifiable take-off collars sit on the annular pipe at the actual
# CH4, CO and O2 sample locations. Each collar overlaps its chamber connector.
takeoffs = [
    ("CH4", (-0.148, -0.119, 0.221), MAT_ORANGE),
    ("CO", (0.148, -0.119, 0.221), MAT_RED),
    ("O2", (0.338, -0.024, 0.221), MAT_GREEN),
]
for suffix, location, material in takeoffs:
    add_cylinder("MESH_G01_TAKEOFF_" + suffix, location, 0.014, 0.024, material, rotation=(math.pi / 2, 0.0, 0.0), vertices=24)
    add_cylinder("GEO_G01_TAKEOFF_" + suffix + "_NUT", (location[0], location[1] - 0.014, location[2]), 0.018, 0.006, MAT_FRAME, rotation=(math.pi / 2, 0.0, 0.0), vertices=6)
    add_uvsphere("GEO_G01_TAKEOFF_" + suffix + "_STATUS", (location[0], location[1] - 0.020, location[2] + 0.012), 0.004, material)

# A dedicated rear return port makes the loop closure legible: used sample
# gas returns from the ring to the existing VENT-01 path above the enclosure.
add_cylinder("MESH_G01_RETURN_PORT_01", (0.242, 0.096, 0.221), 0.016, 0.022, MAT_CYAN, rotation=(math.pi / 2, 0.0, 0.0), vertices=24)
add_hose(
    "MESH_G01_RETURN_TO_VENT_01",
    [(0.242, 0.108, 0.221), (0.250, 0.106, 0.258), (0.252, 0.082, 0.294), (0.243, 0.047, 0.324)],
    MAT_CYAN,
    radius=0.0038,
)
add_arrow("GEO_G01_RETURN_FLOW_INDICATOR", (0.248, 0.104, 0.260), MAT_CYAN, direction=-1)

# Renders retain the V07 camera language but emphasize the now-closed gas path.
os.makedirs(PREVIEW_DIR, exist_ok=True)
cam = SCENE.camera
cutaway_names = ["MESH_RING_ACRYLIC_ROOF", "MESH_RING_OUTER_ACRYLIC", "MESH_RING_INNER_ACRYLIC", "MESH_RING_OUTER_RAIL", "MESH_RING_INNER_RAIL"]
for name in cutaway_names:
    if name in bpy.data.objects:
        bpy.data.objects[name].hide_render = False
cam.location = (1.00, -1.22, 0.82)
cam.data.lens = 58
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V08_HERO
bpy.ops.render.render(write_still=True)

states = {name: bpy.data.objects[name].hide_render for name in cutaway_names if name in bpy.data.objects}
for name in states:
    bpy.data.objects[name].hide_render = True
cam.location = (0.82, -1.16, 1.16)
cam.data.lens = 60
look_at(cam, (0.0, 0.0, 0.210))
SCENE.render.filepath = V08_FUNCTION
bpy.ops.render.render(write_still=True)

cam.location = (0.72, -0.85, 0.70)
cam.data.lens = 62
look_at(cam, (0.115, -0.055, 0.245))
SCENE.render.filepath = V08_FLOW_DETAIL
bpy.ops.render.render(write_still=True)
for name, state in states.items():
    bpy.data.objects[name].hide_render = state

bpy.ops.object.select_all(action="DESELECT")
for obj in MODEL.objects:
    if obj.type in {"MESH", "CURVE"}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(
    filepath=V08_GLB, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_materials="EXPORT",
    export_cameras=False, export_lights=False,
)
bpy.ops.wm.save_as_mainfile(filepath=V08_BLEND)
print({"V08_DONE": True, "blend": V08_BLEND, "glb": V08_GLB})
