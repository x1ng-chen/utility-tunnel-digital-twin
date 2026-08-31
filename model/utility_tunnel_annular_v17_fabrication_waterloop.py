"""V17: fabrication-scale fans, distributed FS-IR02 stations, formal water loop.

Uses the V16 model as source.  The two axial fans are 120 x 120 mm nominal;
the FS-IR02 PCB remains 38.6 x 22.1 mm from the supplied product image.  The
optical-probe thread was not visible in the source, so its bracket has a
serviceable slot and a VERIFY-THREAD annotation rather than a fabricated value.
"""
import bpy
import math
import os
import json
from mathutils import Vector

ROOT = r"D:\\shixi\\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v17-fabrication-waterloop.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v17-fabrication-waterloop.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v17-fabrication-waterloop-hero.png")
DETAIL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v17-fabrication-waterloop-levels.png")
os.makedirs(PREVIEW_DIR, exist_ok=True)

COL = bpy.data.collections.get("COL-UT_RING_V16_DISTRIBUTED_LEVELS")
if COL is None:
    raise RuntimeError("Open V16 distributed-levels before applying V17.")
M = bpy.data.materials
MAT_BLACK = M["MAT-v35_black"]
MAT_BLUE = M["MAT-v35_blue"]
MAT_CYAN = M["MAT-v35_cyan"]
MAT_RED = M["MAT-v35_red"]
MAT_GREEN = M["MAT-v35_green"]
MAT_ORANGE = M["MAT-v35_orange"]
MAT_YELLOW = M["MAT-v35_yellow"]
MAT_WHITE = M["MAT-v35_white"]
MAT_STEEL = M["MAT-v35_steel"]


def link(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def box(name, loc, dims, material, rotation=(0, 0, 0), bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rotation)
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


def cyl(name, loc, radius, depth, material, rotation=(math.pi/2, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def torus(name, loc, major, minor, material, rotation=(math.pi/2, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=28, minor_segments=8, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    return obj


def text(name, body, loc, size, material, rotation=(math.pi/2, 0, 0)):
    data = bpy.data.curves.new(name + "_DATA", "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = .0003
    data.bevel_depth = .00007
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    return obj


def curve(name, points, material, radius=.0011):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points)-1)
    for bp, co in zip(spl.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


# Replace the V15 80 mm placeholder fans with two 120 mm assemblies.
for obj in list(COL.objects):
    if "V16_FAN-01 INTAKE" in obj.name or "V16_FAN-02 EXHAUST" in obj.name:
        bpy.data.objects.remove(obj, do_unlink=True)


def make_120mm_fan(tag, loc, airflow, loom, panel_side="FRONT"):
    side, depth, half = .120, .018, .060
    # Four-frame construction leaves a genuine open fan aperture.
    for suffix, offset, dims in (
        ("FRAME_TOP", (0, 0, half-.006), (side, depth, .012)),
        ("FRAME_BOTTOM", (0, 0, -half+.006), (side, depth, .012)),
        ("FRAME_LEFT", (-half+.006, 0, 0), (.012, depth, .096)),
        ("FRAME_RIGHT", (half-.006, 0, 0), (.012, depth, .096)),
    ):
        box("MESH_V17_%s_%s" % (tag, suffix), tuple(loc[i]+offset[i] for i in range(3)), dims, MAT_BLACK, bevel=.002)
    torus("GEO_V17_%s_GRILLE_RING" % tag, (loc[0], loc[1]-.012, loc[2]), .044, .003, MAT_STEEL)
    cyl("MESH_V17_%s_HUB" % tag, (loc[0], loc[1]-.014, loc[2]), .013, .008, MAT_BLACK)
    for angle in range(0, 360, 45):
        r = math.radians(angle)
        blade = box("GEO_V17_%s_BLADE_%03d" % (tag, angle), (loc[0]+.025*math.sin(r), loc[1]-.012, loc[2]+.025*math.cos(r)), (.014, .004, .050), MAT_CYAN, bevel=.001)
        blade.rotation_euler[1] = r + .34
    for cross in (-.032, 0, .032):
        box("GEO_V17_%s_GRILLE_H_%s" % (tag, int((cross+.04)*1000)), (loc[0], loc[1]-.019, loc[2]+cross), (.090, .0017, .0017), MAT_STEEL, bevel=.0002)
        box("GEO_V17_%s_GRILLE_V_%s" % (tag, int((cross+.04)*1000)), (loc[0]+cross, loc[1]-.019, loc[2]), (.0017, .0017, .090), MAT_STEEL, bevel=.0002)
    for x in (-.050, .050):
        for z in (-.050, .050):
            cyl("GEO_V17_%s_MOUNT_%s_%s" % (tag, int(x*1000), int(z*1000)), (loc[0]+x, loc[1]-.014, loc[2]+z), .003, .006, MAT_STEEL)
    for idx, mat in enumerate((MAT_RED, MAT_BLACK, MAT_YELLOW, MAT_BLUE)):
        start = (loc[0]-.040+idx*.008, loc[1], loc[2]-.055)
        curve("GEO_V17_%s_W%02d" % (tag, idx+1), [start, (start[0], loc[1]-.052, loc[2]-.070), loom], mat, .0009)
    text("GEO_V17_%s_LABEL" % tag, "%s | 120 x 120 mm\n12V / 4-WIRE | %s" % (tag, airflow), (loc[0], loc[1]-.025, loc[2]-.078), .0042, MAT_WHITE)
    text("GEO_V17_%s_DIM" % tag, "120 mm", (loc[0], loc[1]-.023, loc[2]+.070), .0035, MAT_YELLOW)


make_120mm_fan("FAN-01_INTAKE", (.432, -.154, .270), "AIR IN -> H-31", (-.180, -.205, .210))
make_120mm_fan("FAN-02_EXHAUST", (.170, .040, .370), "H-31 -> VENT", (-.174, -.205, .206))

# Mark every sensor as a buildable station.  PCB size is sourced; probe bore stays
# explicitly adaptable until the threaded probe arrives for calliper measurement.
for tag in ("L01", "L02", "L03", "L04", "L05"):
    board = bpy.data.objects.get("MESH_V16_FSIR02_%s_BOARD" % tag)
    probe = bpy.data.objects.get("MESH_V16_FSIR02_%s_PROBE_COLLAR" % tag)
    if board is None or probe is None:
        raise RuntimeError("Missing FS-IR02 %s geometry" % tag)
    b = board.location
    p = probe.location
    box("GEO_V17_FSIR02_%s_SLOT_BRACKET" % tag, (p.x, p.y+.011 if p.y >= -.13 else p.y-.011, p.z), (.030, .003, .026), MAT_STEEL, bevel=.001)
    text("GEO_V17_FSIR02_%s_PCB_DIM" % tag, "PCB 38.6 x 22.1 mm\nJ-%s: GND / DO / AO / 5V" % tag, (b.x, b.y-.010, b.z-.027), .00215, MAT_WHITE)
    text("GEO_V17_FSIR02_%s_HOLE_NOTE" % tag, "SLOT: VERIFY\nPROBE THREAD", (p.x, p.y-.015 if p.y < -.13 else p.y+.015, p.z+.024), .0019, MAT_YELLOW)
    # Visible numbered board-to-loom identifier, one per station.
    text("GEO_V17_FSIR02_%s_LOOM_ID" % tag, "W-%s-01..04" % tag, (b.x+.030, b.y-.008, b.z), .0020, MAT_GREEN)

# Formal water circulation: tray -> P-01 suction -> pump -> V-01 -> raised fill
# manifold -> level tray; overflow returns to the tray's low side.  It is a model
# water circuit, independent from the gas sampling ring.
pump_motor = bpy.data.objects.get("MESH_V16_PUMP24V_MOTOR")
pump_head = bpy.data.objects.get("MESH_V16_PUMP24V_HEAD")
if pump_motor is None or pump_head is None:
    raise RuntimeError("V16 24V pump geometry not found")

# Cover the former test-only legend with formal-loop identification.
for obj in list(COL.objects):
    if "PUMP24V_LABEL" in obj.name:
        bpy.data.objects.remove(obj, do_unlink=True)
box("MESH_V17_PUMP_P01_BASE", (.192, -.184, .128), (.126, .054, .010), MAT_BLACK, bevel=.002)
text("GEO_V17_PUMP_P01_LABEL", "P-01 24V WATER PUMP\nFORMAL LEVEL-TEST LOOP", (.190, -.215, .119), .0034, MAT_YELLOW)

# Suction hose: water tray low point into pump.  Discharge rises through a manual
# isolation valve to a raised manifold and falls into the instrumented water tray.
curve("GEO_V17_WATER_P01_SUCTION", [(.070, -.150, .146), (.112, -.184, .138), (.196, -.184, .145)], MAT_CYAN, .0040)
curve("GEO_V17_WATER_P01_DISCHARGE", [(.236, -.184, .156), (.252, -.184, .205), (.118, -.184, .224), (.082, -.150, .224)], MAT_CYAN, .0040)
curve("GEO_V17_WATER_RETURN_OVERFLOW", [(-.060, -.150, .181), (-.078, -.151, .164), (-.030, -.150, .148)], MAT_CYAN, .0035)
box("MESH_V17_WATER_FILL_MANIFOLD", (.084, -.151, .224), (.078, .012, .012), MAT_STEEL, bevel=.001)
for x in (.060, .084, .108):
    cyl("GEO_V17_WATER_FILL_NOZZLE_%03d" % int(x*1000), (x, -.151, .215), .0035, .018, MAT_STEEL, rotation=(0, 0, 0))
    cyl("GEO_V17_WATER_FILL_DROP_%03d" % int(x*1000), (x, -.151, .201), .0022, .014, MAT_CYAN, rotation=(0, 0, 0))

# V-01 manual ball valve on discharge and K-01 relay module control it.
cyl("MESH_V17_VALVE_V01_BODY", (.242, -.184, .198), .010, .020, MAT_STEEL)
box("GEO_V17_VALVE_V01_LEVER", (.242, -.198, .213), (.030, .003, .005), MAT_ORANGE, bevel=.0005)
text("GEO_V17_VALVE_V01_LABEL", "V-01\nISOLATION", (.255, -.207, .205), .0025, MAT_WHITE)
box("MESH_V17_RELAY_K01_PCB", (-.070, -.205, .194), (.052, .006, .028), MAT_GREEN, bevel=.001)
box("MESH_V17_RELAY_K01_BODY", (-.070, -.210, .197), (.026, .010, .016), MAT_BLACK, bevel=.001)
for x in (-.088, -.080, -.062, -.054):
    cyl("GEO_V17_RELAY_K01_PIN_%03d" % int(x*1000), (x, -.212, .184), .0013, .002, MAT_STEEL)
text("GEO_V17_RELAY_K01_LABEL", "K-01 JQC-3FF-S-Z\n24V PUMP CONTROL", (-.070, -.215, .217), .0028, MAT_WHITE)
curve("GEO_V17_RELAY_K01_TO_P01", [(-.050, -.211, .194), (.055, -.211, .190), (.155, -.195, .158)], MAT_RED, .00115)
curve("GEO_V17_PUMP_24V_RETURN", [(.150, -.192, .150), (.050, -.212, .174), (-.060, -.212, .184)], MAT_BLACK, .00115)
text("GEO_V17_WATER_FLOW_LABEL", "TRAY -> P-01 -> V-01 -> FILL MANIFOLD -> OVERFLOW RETURN", (.085, -.213, .244), .0030, MAT_YELLOW)

# Save only V17 after building.  V16 remains the unmodified source checkpoint.
COL.name = "COL-UT_RING_V17_FABRICATION_WATERLOOP"
for obj in list(COL.objects):
    if "V16" in obj.name:
        obj.name = obj.name.replace("V16", "V17")
    if obj.data and "V16" in obj.data.name:
        obj.data.name = obj.data.name.replace("V16", "V17")

scene = bpy.context.scene
cam = scene.camera
cam.location = (.690, -.900, .560)
target = Vector((.045, -.050, .205))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 52
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_percentage = 100
scene.render.resolution_x = 1400
scene.render.resolution_y = 960
scene.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

original_loc, original_rot, original_lens = cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens
cam.location = (.375, -.580, .320)
cam.rotation_euler = (Vector((.045, -.135, .190)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 58
scene.render.filepath = DETAIL_OUT
bpy.ops.render.render(write_still=True)
cam.location, cam.rotation_euler, cam.data.lens = original_loc, original_rot, original_lens

bpy.ops.object.select_all(action="DESELECT")
for obj in scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print(json.dumps({"V17_DONE": True, "fan_size_mm": [120, 120], "level_stations": 5, "water_loop": "tray-P01-V01-manifold-overflow-return", "blend": BLEND_OUT, "glb": GLB_OUT}, ensure_ascii=False))
