"""V18: fabrication gate, adjustable level-probe brackets and dry-safe routing.

Run with the V17 fabrication-waterloop Blend open.  This is deliberately a
mechanical/electrical review model, not a fabrication drawing or an approved
live water circuit.  Known values are limited to the 120 mm fan case and the
FS-IR02 board outline (38.6 x 22.1 mm); probe-thread, nut, hose and electrical
ratings remain explicit TBD measurements.
"""
import bpy
import math
import os
import json
from mathutils import Vector

ROOT = r"D:\\shixi\\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v18-fabrication-safety.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v18-fabrication-safety.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v18-fabrication-safety-hero.png")
DETAIL_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v18-fabrication-safety-detail.png")
os.makedirs(PREVIEW_DIR, exist_ok=True)

COL = (bpy.data.collections.get("COL-UT_RING_V17_FABRICATION_WATERLOOP")
       or bpy.data.collections.get("COL-UT_RING_V18_FABRICATION_SAFETY"))
if COL is None:
    raise RuntimeError("Open V17 fabrication-waterloop before applying V18.")

M = bpy.data.materials
MAT_BLACK = M["MAT-v35_black"]
MAT_CYAN = M["MAT-v35_cyan"]
MAT_RED = M["MAT-v35_red"]
MAT_GREEN = M["MAT-v35_green"]
MAT_YELLOW = M["MAT-v35_yellow"]
MAT_WHITE = M["MAT-v35_white"]
MAT_STEEL = M["MAT-v35_steel"]


def link(obj):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    COL.objects.link(obj)
    return obj


def clear_v18():
    for obj in list(bpy.data.objects):
        name = obj.name
        owned = (
            (name.startswith("GEO_V18_FAN") and any(token in name for token in
                ("_ADJUSTABLE_EDGE_RETAINER_", "_MFG_GATE", "_RETENTION_NOTE")))
            or name.startswith(("DIM_V18_FSIR02", "MESH_V18_IF01",
                             "GEO_V18_IF01", "MESH_V18_DRY_LOOM", "GEO_V18_L01_TO_IF01",
                             "GEO_V18_L02_TO_IF01", "GEO_V18_L03_TO_IF01", "GEO_V18_L04_TO_IF01",
                             "GEO_V18_L05_TO_IF01", "MESH_V18_B_WET", "GEO_V18_B_WET",
                             "MESH_V18_P01", "GEO_V18_P01", "GEO_V18_V01", "GEO_V18_WATER"))
            or (name.startswith("MESH_V18_FSIR02") and "CRADLE" in name)
            or (name.startswith("GEO_V18_FSIR02") and any(token in name for token in
                ("CLAMP_BLANK", "MEASURE_NOTE", "DRY_DRIP_LOOP", "DRY_LOOM_TAG")))
        )
        if owned:
            bpy.data.objects.remove(obj, do_unlink=True)


def v17_or_v18(name):
    """Allow idempotent reruns after this script has renamed the V17 nodes."""
    return bpy.data.objects.get(name) or bpy.data.objects.get(name.replace("V17", "V18"))


def box(name, loc, dims, material, rotation=(0, 0, 0), bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width, mod.segments = bevel, 2
    return obj


def cyl(name, loc, radius, depth, material, rotation=(math.pi / 2, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def text(name, body, loc, size, material, rotation=(math.pi / 2, 0, 0)):
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


def curve(name, points, material, radius=.001):
    data = bpy.data.curves.new(name + "_DATA", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(points) - 1)
    for bp, co in zip(spl.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.data.materials.append(material)
    return obj


clear_v18()

# The V17 four corner dots implied a real fan pitch.  They are deliberately
# removed: case size is known, but hole pitch, hole diameter and thickness are
# not.  V18 shows only adjustable edge retainers and a measurement gate.
for obj in list(COL.objects):
    if "FAN-01_INTAKE_MOUNT_" in obj.name or "FAN-02_EXHAUST_MOUNT_" in obj.name:
        bpy.data.objects.remove(obj, do_unlink=True)


def fan_measurement_gate(tag, loc, sign_y):
    # Retainers grip the case edges; their placement is not an drilling pattern.
    for x, z in ((-.055, -.052), (.055, -.052), (-.055, .052), (.055, .052)):
        box("GEO_V18_%s_ADJUSTABLE_EDGE_RETAINER_%s_%s" % (tag, int(x * 1000), int(z * 1000)),
            (loc[0] + x, loc[1] + sign_y * .013, loc[2] + z),
            (.014, .008, .014), MAT_STEEL, bevel=.001)
    text("GEO_V18_%s_MFG_GATE" % tag,
         "120 mm CASE: CONFIRMED\nPITCH / HOLE DIA / THICKNESS / A: MEASURE\nPWM + TACH + CURRENT: VERIFY",
         (loc[0], loc[1] + sign_y * .026, loc[2] + .084), .00215, MAT_YELLOW)
    text("GEO_V18_%s_RETENTION_NOTE" % tag, "ADJUSTABLE EDGE RETAINERS — NOT A DRILL TEMPLATE",
         (loc[0], loc[1] + sign_y * .025, loc[2] - .086), .00185, MAT_WHITE)


fan_measurement_gate("FAN-01", (.432, -.154, .270), -1)
fan_measurement_gate("FAN-02", (.170, .040, .370), -1)

# Each probe now has a split, non-drilled cradle: the two cheeks are a blank
# fixture envelope, while the yellow datum leaders request the three actual
# caliper measurements needed before a hole is selected.
STATIONS = ("L01", "L02", "L03", "L04", "L05")
for tag in STATIONS:
    probe = v17_or_v18("MESH_V17_FSIR02_%s_PROBE_COLLAR" % tag)
    board = v17_or_v18("MESH_V17_FSIR02_%s_BOARD" % tag)
    if probe is None or board is None:
        raise RuntimeError("Missing V17 FS-IR02 station %s" % tag)
    p, b = probe.location.copy(), board.location.copy()
    side = -1 if p.y < -.13 else 1
    y = p.y + side * .016
    # Open split cradle: no circle, bore or stated clamp diameter is modelled.
    box("MESH_V18_FSIR02_%s_CRADLE_LEFT" % tag, (p.x - .015, y, p.z), (.004, .003, .034), MAT_STEEL, bevel=.0006)
    box("MESH_V18_FSIR02_%s_CRADLE_RIGHT" % tag, (p.x + .015, y, p.z), (.004, .003, .034), MAT_STEEL, bevel=.0006)
    box("MESH_V18_FSIR02_%s_CRADLE_TOP" % tag, (p.x, y, p.z + .015), (.034, .003, .004), MAT_STEEL, bevel=.0006)
    box("MESH_V18_FSIR02_%s_CRADLE_BOTTOM" % tag, (p.x, y, p.z - .015), (.034, .003, .004), MAT_STEEL, bevel=.0006)
    box("GEO_V18_FSIR02_%s_CLAMP_BLANK" % tag, (p.x, y + side * .0035, p.z), (.028, .002, .006), MAT_BLACK, bevel=.0004)
    # Yellow datum leaders are review geometry only; they do not prescribe a bore.
    curve("DIM_V18_FSIR02_%s_THREAD_DATUM" % tag,
          [(p.x - .012, y + side * .004, p.z + .020), (p.x - .030, y + side * .006, p.z + .030),
           (p.x - .034, y + side * .006, p.z + .041)], MAT_YELLOW, .00045)
    text("GEO_V18_FSIR02_%s_MEASURE_NOTE" % tag,
         "%s: MEASURE THREAD OD / NUT AF / CABLE L\nNO BORE — SPLIT CLAMP BLANK" % tag,
         (p.x, y + side * .008, p.z + .045), .00175, MAT_YELLOW)
    # A separate drip loop anchors the four-core loom on the dry-board side.
    curve("GEO_V18_FSIR02_%s_DRY_DRIP_LOOP" % tag,
          [(b.x + .017, b.y - .007, b.z - .002), (b.x + .024, b.y - .014, b.z - .020),
           (b.x + .030, b.y - .008, b.z - .006)], MAT_GREEN, .0008)
    text("GEO_V18_FSIR02_%s_DRY_LOOM_TAG" % tag, "W-%s: 5V / GND / DO / AO" % tag,
         (b.x, b.y - .013, b.z - .039), .0017, MAT_WHITE)

# IF-01 is intentionally a review-layout interface in the dry bay.  It makes
# the mandatory signal-domain boundary visible without inventing final resistor,
# isolation or threshold values.
box("MESH_V18_IF01_INTERFACE_PCB", (-.255, -.205, .238), (.082, .007, .046), MAT_GREEN, bevel=.001)
box("MESH_V18_IF01_COVER", (-.255, -.212, .238), (.088, .006, .054), MAT_BLACK, bevel=.001)
for idx in range(5):
    z = .256 - idx * .009
    box("GEO_V18_IF01_SENSOR_PORT_%02d" % (idx + 1), (-.286, -.216, z), (.012, .003, .005), MAT_WHITE, bevel=.0004)
for idx in range(2):
    z = .247 - idx * .012
    box("GEO_V18_IF01_MCU_PORT_%02d" % (idx + 1), (-.223, -.216, z), (.014, .003, .006), MAT_CYAN, bevel=.0004)
box("GEO_V18_IF01_5V_FUSE_TBD", (-.255, -.219, .270), (.014, .003, .007), MAT_RED, bevel=.0004)
text("GEO_V18_IF01_LABEL", "IF-01 DRY-SIDE REVIEW\n5V SENSOR BUS: FUSE TBD\nDO: LOGIC LEVEL TBD | AO: 5V→3V3 SCALE TBD\nNO LIVE WIRING / NO MCU DIRECT 5V", (-.255, -.220, .294), .00205, MAT_YELLOW)
text("GEO_V18_IF01_SEPARATION", "WET ZONE ↔ DRIP LOOP ↔ DRY IF-01", (-.255, -.221, .201), .00195, MAT_WHITE)

# Dry loom trunk carries labelled station looms to IF-01, visibly above the wet
# tray and behind a splash barrier.  It represents routing only, not a circuit.
box("MESH_V18_DRY_LOOM_TRUNK", (-.130, -.193, .305), (.220, .010, .014), MAT_BLACK, bevel=.002)
for idx, tag in enumerate(STATIONS):
    board = v17_or_v18("MESH_V17_FSIR02_%s_BOARD" % tag)
    target = (-.286, -.214, .256 - idx * .009)
    curve("GEO_V18_%s_TO_IF01_ROUTE" % tag,
          [(board.location.x, board.location.y - .007, board.location.z),
           (board.location.x, -.193, .305), (-.130, -.193, .305), target], MAT_GREEN, .00075)

# Physical splash/dry boundary and interlocked non-energised water service
# representation.  It makes it impossible to read V18 as an approved loop.
box("MESH_V18_B_WET_DRY_SPLASH_BARRIER", (.090, -.176, .205), (.190, .004, .155), MAT_STEEL, bevel=.001)
text("GEO_V18_B_WET_DRY_BARRIER_LABEL", "WET SIDE / DRY SIDE\nNO SHARED CABLE HOLE", (.090, -.181, .286), .0023, MAT_WHITE)

pump_in = v17_or_v18("MESH_V17_PUMP24V_IN")
pump_out = v17_or_v18("MESH_V17_PUMP24V_OUT")
if pump_in is None or pump_out is None:
    raise RuntimeError("Missing V17 pump ports")
for suffix, obj, yoff in (("IN", pump_in, -.011), ("OUT", pump_out, .011)):
    cyl("MESH_V18_P01_%s_DRY_CAP" % suffix,
        (obj.location.x, obj.location.y + yoff, obj.location.z), .010, .008, MAT_RED)
    text("GEO_V18_P01_%s_CAP_NOTE" % suffix, "%s PORT: OD / HOSE ID TBD\nDRY CAP INSTALLED" % suffix,
         (obj.location.x, obj.location.y + yoff * 2.1, obj.location.z - .026), .0017, MAT_YELLOW)
box("MESH_V18_P01_SERVICE_DISCONNECT", (.118, -.211, .152), (.034, .008, .024), MAT_RED, bevel=.001)
text("GEO_V18_P01_LOCKOUT", "P-01 LOCKOUT\n24V FUSE / CURRENT / RELAY CONTACT: VERIFY\nNO POWER — NO WATER", (.118, -.218, .188), .0020, MAT_YELLOW)
box("GEO_V18_V01_LOCK_CLIP", (.242, -.205, .213), (.035, .007, .011), MAT_RED, bevel=.001)
text("GEO_V18_V01_LOCKED_CLOSED", "V-01 LOCKED CLOSED\nPROJECT LEAD APPROVAL REQUIRED", (.272, -.211, .225), .00195, MAT_YELLOW)
text("GEO_V18_WATER_SAFETY_BANNER", "LOW-WATER REVIEW PATH ONLY — NOT CONNECTED TO BUILDING WATER — NO ENERGISATION", (.080, -.218, .105), .0027, MAT_RED)

# Convert this version's identifiers only after V17 lookups have completed.
COL.name = "COL-UT_RING_V18_FABRICATION_SAFETY"
for obj in list(COL.objects):
    if "V17" in obj.name:
        obj.name = obj.name.replace("V17", "V18")
    if obj.data and "V17" in obj.data.name:
        obj.data.name = obj.data.name.replace("V17", "V18")

scene = bpy.context.scene
cam = scene.camera
cam.location = (.690, -.900, .560)
target = Vector((.040, -.060, .205))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 52
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_percentage = 100
scene.render.resolution_x, scene.render.resolution_y = 1400, 960
scene.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

original_loc, original_rot, original_lens = cam.location.copy(), cam.rotation_euler.copy(), cam.data.lens
cam.location = (.355, -.625, .320)
cam.rotation_euler = (Vector((.000, -.150, .205)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 58
scene.render.filepath = DETAIL_OUT
bpy.ops.render.render(write_still=True)
cam.location, cam.rotation_euler, cam.data.lens = original_loc, original_rot, original_lens

bpy.ops.object.select_all(action="DESELECT")
for obj in scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True,
                          export_apply=True, export_yup=True, export_materials="EXPORT",
                          export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)

print(json.dumps({
    "V18_DONE": True,
    "known_dimensions_mm": {"FSIR02_pcb": [38.6, 22.1], "fan_case": [120, 120]},
    "measurement_gates": ["probe_thread_od", "probe_nut_af", "probe_cable_length",
                          "fan_pitch_hole_thickness_current_pwm_tach", "pump_port_hose_current"],
    "safety": "dry-capped-pump; V01-locked-closed; no-live-wiring; no-building-water",
    "blend": BLEND_OUT, "glb": GLB_OUT
}, ensure_ascii=False))
