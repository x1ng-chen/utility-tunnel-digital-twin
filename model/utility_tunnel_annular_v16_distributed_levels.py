"""V16: distribute the five FS-IR02 liquid-level stations around the water path.

Each station keeps its 5 V FS-IR02 board beside its own external optical probe,
instead of grouping all five boards in the front service bay.  The V15 source on
disk is preserved; this patch saves new V16 Blend and GLB deliverables.
"""
import bpy
import os
import json

ROOT = r"D:\\shixi\\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_OUT = os.path.join(ROOT, "utility-tunnel-annular-v16-distributed-levels.blend")
GLB_OUT = os.path.join(ROOT, "utility-tunnel-annular-v16-distributed-levels.glb")
HERO_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v16-distributed-levels-hero.png")
LEVELS_OUT = os.path.join(PREVIEW_DIR, "utility-tunnel-annular-v16-distributed-levels-levels.png")
os.makedirs(PREVIEW_DIR, exist_ok=True)

COL = bpy.data.collections.get("COL-UT_RING_V15_WATER_AIR")
if COL is None:
    raise RuntimeError("Open the V15 water/air model before applying V16.")

M = bpy.data.materials
MAT_BLACK = M["MAT-v35_black"]
MAT_BLUE = M["MAT-v35_blue"]
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


def box(name, loc, dims, material, rotation=(0, 0, 0), bevel=0.001):
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


def cyl(name, loc, radius, depth, material, rotation=(1.5707963, 0, 0), vertices=20):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation)
    obj = link(bpy.context.object)
    obj.name = name
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def text(name, body, loc, size, material, rotation=(1.5707963, 0, 0)):
    data = bpy.data.curves.new(name + "_DATA", "FONT")
    data.body = body
    data.align_x = "CENTER"
    data.align_y = "CENTER"
    data.size = size
    data.extrude = 0.0003
    data.bevel_depth = 0.00007
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rotation
    obj.data.materials.append(material)
    return obj


def curve(name, points, material, radius=0.00055):
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


# tag, function, original probe, original board, new probe, new board, local loom
# The positions occupy separate areas of the annular water path and each board
# remains above the possible wet line, on an independently fastened bracket.
STATIONS = [
    ("L01", "LOW",    (-.060, -.168, .158), (-.078, -.208, .224), (-.145, -.168, .153), (-.160, -.204, .212), (-.180, -.184, .235)),
    ("L02", "NORMAL", (-.024, -.168, .164), (-.039, -.208, .224), ( .120, -.168, .174), ( .125, -.204, .238), ( .145, -.184, .262)),
    ("L03", "HIGH",   ( .020, -.168, .170), ( .000, -.208, .224), ( .160,  .040, .201), ( .184,  .008, .265), ( .170,  .016, .295)),
    ("L04", "HI-HI",  (-.055, -.095, .176), ( .039, -.208, .224), (-.125,  .078, .225), (-.148,  .045, .292), (-.145,  .052, .322)),
    ("L05", "LEAK",   ( .060, -.095, .158), ( .078, -.208, .224), ( .195, -.060, .138), ( .210, -.092, .202), ( .215, -.075, .232)),
]

for tag, role, old_probe, old_board, new_probe, new_board, loom in STATIONS:
    probe_delta = tuple(new_probe[i] - old_probe[i] for i in range(3))
    board_delta = tuple(new_board[i] - old_board[i] for i in range(3))
    key = "FSIR02_%s_" % tag
    # Remove V15 wiring first.  It would otherwise retain the former shared-bay path.
    for obj in list(COL.objects):
        if key in obj.name and obj.type == "CURVE":
            bpy.data.objects.remove(obj, do_unlink=True)
    # Move the existing true board/probe geometry, retaining FS-IR02 details.
    for obj in list(COL.objects):
        if key not in obj.name:
            continue
        if any(part in obj.name for part in ("PROBE_COLLAR", "PROBE_BODY", "OPTIC", "O_RING")):
            delta = probe_delta
        else:
            delta = board_delta
        obj.location = tuple(obj.location[i] + delta[i] for i in range(3))

    # Distinct mounting plate, four raised standoffs, and a short named station rail.
    plate_y = new_board[1] + 0.005
    box("MESH_V16_FSIR02_%s_MOUNT_PLATE" % tag, (new_board[0], plate_y, new_board[2]), (.058, .003, .036), MAT_BLACK, bevel=.001)
    for ix in (-.021, .021):
        for iz in (-.012, .012):
            cyl("GEO_V16_FSIR02_%s_STANDOFF_%s_%s" % (tag, int(ix*1000), int(iz*1000)), (new_board[0]+ix, new_board[1]+.0025, new_board[2]+iz), .0022, .006, MAT_STEEL)
    box("GEO_V16_FSIR02_%s_STATION_RAIL" % tag, (new_board[0], new_board[1]+.009, new_board[2]-.025), (.068, .005, .003), MAT_CYAN, bevel=.0005)
    text("GEO_V16_FSIR02_%s_STATION_TAG" % tag, "%s  LEVEL STATION" % tag, (new_board[0], new_board[1]-.009, new_board[2]+.029), .0027, MAT_YELLOW)

    direction = -1 if new_probe[1] < -0.13 else 1
    wire_mats = (MAT_WHITE, MAT_BLUE, MAT_YELLOW, MAT_RED)
    for core, mat in enumerate(wire_mats):
        off = (core - 1.5) * .0012
        curve(
            "GEO_V16_FSIR02_%s_PROBE_WIRE_%02d" % (tag, core+1),
            [
                (new_probe[0]+off, new_probe[1]-direction*.022, new_probe[2]),
                ((new_probe[0]+new_board[0])/2+off, (new_probe[1]+new_board[1])/2-direction*.020, max(new_probe[2], new_board[2])+.012),
                (new_board[0]-.010+core*.0025, new_board[1]-.005, new_board[2]-.007),
            ],
            mat,
        )
    curve(
        "GEO_V16_FSIR02_%s_TO_LOCAL_LOOM" % tag,
        [(new_board[0]+.013, new_board[1]-.006, new_board[2]), (new_board[0]+.013, new_board[1]-.012, new_board[2]+.025), loom],
        MAT_GREEN,
        .00075,
    )

# Replace the front-bay heading with a distributed-station heading.
old_title = bpy.data.objects.get("GEO_V15_LEVEL_TITLE")
if old_title:
    old_title.data.body = "5x FS-IR02 | DISTRIBUTED LEVEL STATIONS | 5V / AO / DO"
    old_title.location = (-.030, -.218, .322)
    old_title.data.size = .0042

# Turn V15 identifiers into V16 identifiers only after all lookups are complete.
COL.name = "COL-UT_RING_V16_DISTRIBUTED_LEVELS"
for obj in list(COL.objects):
    if "V15" in obj.name:
        obj.name = obj.name.replace("V15", "V16")
    if obj.data and "V15" in obj.data.name:
        obj.data.name = obj.data.name.replace("V15", "V16")

# Render the validated overall view plus a clear left-front inspection view.
scene = bpy.context.scene
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_percentage = 100
scene.render.resolution_x = 1280
scene.render.resolution_y = 900
scene.render.filepath = HERO_OUT
bpy.ops.render.render(write_still=True)

cam = scene.camera
original_loc = cam.location.copy()
original_rot = cam.rotation_euler.copy()
cam.location = (-.455, -.615, .390)
target = __import__("mathutils").Vector((.010, -.060, .205))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.render.filepath = LEVELS_OUT
bpy.ops.render.render(write_still=True)
cam.location = original_loc
cam.rotation_euler = original_rot

# Export all visible scene assets as V16 portable deliverable, then preserve editable source.
bpy.ops.object.select_all(action="DESELECT")
for obj in scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT"} and not obj.hide_viewport:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get("MESH_BASE_01")
bpy.ops.export_scene.gltf(filepath=GLB_OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUT)
print(json.dumps({"V16_DONE": True, "stations": len(STATIONS), "collection": COL.name, "blend": BLEND_OUT, "glb": GLB_OUT}, ensure_ascii=False))
