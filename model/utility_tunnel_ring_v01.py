"""Build the transparent-acrylic oval utility-tunnel demo model in Blender 5.2+.

The script creates only task-owned collections (COL-UT_RING_*), preserving
unrelated objects in the open scene. Units are metres; dimensions match the
1000 x 500 x 420 mm concept drawing.
"""
import bpy
import math
import os
from mathutils import Vector

ROOT = r"D:\shixi\model"
PREVIEW_DIR = os.path.join(ROOT, "previews")
BLEND_PATH = os.path.join(ROOT, "utility-tunnel-ring-v02.blend")
GLB_PATH = os.path.join(ROOT, "utility-tunnel-ring-v02.glb")
PREVIEW_PATH = os.path.join(PREVIEW_DIR, "utility-tunnel-ring-v02-hero.png")
FUNCTIONAL_PREVIEW_PATH = os.path.join(PREVIEW_DIR, "utility-tunnel-ring-v02-functional.png")
os.makedirs(PREVIEW_DIR, exist_ok=True)

SCENE = bpy.context.scene
SCENE.unit_settings.system = 'METRIC'
SCENE.unit_settings.length_unit = 'MILLIMETERS'


def get_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        SCENE.collection.children.link(coll)
    return coll


MODEL = get_collection('COL-UT_RING_V02')
RENDER = get_collection('COL-UT_RING_RENDER_V02')


def clear_collection(coll):
    for obj in list(coll.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


clear_collection(MODEL)
clear_collection(RENDER)
for datablocks in (bpy.data.meshes, bpy.data.curves):
    for datablock in list(datablocks):
        if datablock.users == 0:
            datablocks.remove(datablock)

# Keep the prior V01 collection intact for rollback, but never let it overlap
# the V02 evidence renders. Only V02 is selected for the exported GLB below.
legacy_model = bpy.data.collections.get('COL-UT_RING_V01')
if legacy_model:
    for legacy_obj in legacy_model.objects:
        if not legacy_obj.name.startswith('LEGACY_V01_'):
            legacy_obj.name = 'LEGACY_V01_' + legacy_obj.name
        legacy_obj.hide_render = True


def set_input(node, name, value):
    for socket in node.inputs:
        if socket.name == name:
            socket.default_value = value
            return True
    return False


def material(name, color, metallic=0.0, roughness=0.45, alpha=1.0, emission=None):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, alpha)
    bsdf = next((node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is None:
        raise RuntimeError(f'Principled BSDF is missing from {name}')
    set_input(bsdf, 'Base Color', (*color, 1.0))
    set_input(bsdf, 'Metallic', metallic)
    set_input(bsdf, 'Roughness', roughness)
    set_input(bsdf, 'Alpha', alpha)
    if emission:
        set_input(bsdf, 'Emission Color', (*emission[0], 1.0))
        set_input(bsdf, 'Emission Strength', emission[1])
    if alpha < 1.0:
        if hasattr(mat, 'surface_render_method'):
            mat.surface_render_method = 'DITHERED'
    return mat


MAT_BASE = material('MAT-base_bluegray', (0.055, 0.12, 0.17), metallic=0.45, roughness=0.27)
MAT_FLOOR = material('MAT-floor_slate', (0.09, 0.18, 0.24), metallic=0.25, roughness=0.38)
MAT_FRAME = material('MAT-frame_graphite', (0.025, 0.045, 0.06), metallic=0.72, roughness=0.25)
MAT_SHELL = material('MAT-shell_powdercoat', (0.15, 0.23, 0.29), metallic=0.52, roughness=0.30)
MAT_ROOF = material('MAT-roof_bluegray', (0.07, 0.13, 0.18), metallic=0.62, roughness=0.26)
MAT_ACRYLIC = material('MAT-acrylic_clearblue', (0.70, 0.92, 1.0), metallic=0.0, roughness=0.20, alpha=0.035)
# Blended transparency keeps the acrylic visually clear in the real-time hero
# render; dithered alpha introduces grain across overlapping curved panels.
MAT_ACRYLIC.surface_render_method = 'BLENDED'
MAT_ACRYLIC.blend_method = 'BLEND'
MAT_ACRYLIC.use_transparency_overlap = True
MAT_ACRYLIC.show_transparent_back = True
MAT_ACRYLIC.use_transparent_shadow = False
ACRYLIC_BSDF = next(node for node in MAT_ACRYLIC.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
set_input(ACRYLIC_BSDF, 'Transmission Weight', 0.0)
set_input(ACRYLIC_BSDF, 'IOR', 1.49)
MAT_PIPE = material('MAT-pipe_steel', (0.34, 0.40, 0.44), metallic=0.82, roughness=0.26)
MAT_GAS = material('MAT-pipe_gas_orange', (1.0, 0.16, 0.015), metallic=0.0, roughness=0.32, emission=((0.38, 0.015, 0.0), 0.30))
MAT_CYAN = material('MAT-sensor_cyan', (0.02, 0.56, 0.72), metallic=0.12, roughness=0.32, emission=((0.01, 0.24, 0.35), 0.45))
MAT_ORANGE = material('MAT-sensor_orange', (1.0, 0.34, 0.035), metallic=0.08, roughness=0.31, emission=((0.45, 0.07, 0.0), 0.42))
MAT_GREEN = material('MAT-sensor_green', (0.04, 0.72, 0.30), metallic=0.05, roughness=0.33, emission=((0.0, 0.3, 0.08), 0.42))
MAT_RED = material('MAT-sensor_red', (0.95, 0.07, 0.045), metallic=0.05, roughness=0.30, emission=((0.45, 0.0, 0.0), 0.65))
MAT_WATER = material('MAT-water', (0.03, 0.48, 0.78), metallic=0.1, roughness=0.16, alpha=0.65)
MAT_WHITE = material('MAT-label_white', (0.87, 0.96, 1.0), metallic=0.0, roughness=0.35, emission=((0.27, 0.54, 0.75), 0.25))


def link(obj, coll=MODEL):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def add_box(name, location, dims, mat, bevel=0.0, coll=MODEL):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new('Bevel', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = 'ANGLE'
    obj.data.materials.append(mat)
    return link(obj, coll)


def add_cylinder(name, location, radius, depth, mat, rotation=(0, 0, 0), coll=MODEL, vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return link(obj, coll)


def add_uvsphere(name, location, radius, mat, coll=MODEL):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name
    obj.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return link(obj, coll)


def racetrack_points(half_straight, radius, straight_steps=18, arc_steps=20):
    points = []
    for i in range(straight_steps + 1):
        points.append((-half_straight + 2 * half_straight * i / straight_steps, radius))
    for i in range(1, arc_steps + 1):
        a = math.pi / 2 - math.pi * i / arc_steps
        points.append((half_straight + radius * math.cos(a), radius * math.sin(a)))
    for i in range(1, straight_steps + 1):
        points.append((half_straight - 2 * half_straight * i / straight_steps, -radius))
    for i in range(1, arc_steps):
        a = -math.pi / 2 - math.pi * i / arc_steps
        points.append((-half_straight + radius * math.cos(a), radius * math.sin(a)))
    return points


def add_ribbon(name, points, half_width, z0, z1, mat, coll=MODEL):
    verts, faces = [], []
    count = len(points)
    for i, p in enumerate(points):
        prev_p, next_p = points[(i - 1) % count], points[(i + 1) % count]
        dx, dy = next_p[0] - prev_p[0], next_p[1] - prev_p[1]
        length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        nx, ny = -dy / length, dx / length
        left, right = (p[0] + nx * half_width, p[1] + ny * half_width), (p[0] - nx * half_width, p[1] - ny * half_width)
        verts.extend([(left[0], left[1], z0), (right[0], right[1], z0), (left[0], left[1], z1), (right[0], right[1], z1)])
    for i in range(count):
        j = (i + 1) % count
        a, b = 4 * i, 4 * j
        faces.extend([(a, b, b + 1, a + 1), (a + 2, a + 3, b + 3, b + 2), (a, a + 2, b + 2, b), (a + 1, b + 1, b + 3, a + 3)])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


def add_annular_roof(name, outer_points, inner_points, z0, z1, mat, coll=MODEL):
    """Create a solid, closed roof between two equal-count racetrack paths."""
    if len(outer_points) != len(inner_points):
        raise ValueError('roof paths need identical point counts')
    verts, faces = [], []
    count = len(outer_points)
    for outer, inner in zip(outer_points, inner_points):
        verts.extend([
            (outer[0], outer[1], z0), (inner[0], inner[1], z0),
            (outer[0], outer[1], z1), (inner[0], inner[1], z1),
        ])
    for i in range(count):
        j = (i + 1) % count
        a, b = 4 * i, 4 * j
        faces.extend([
            (a, a + 1, b + 1, b), (a + 2, b + 2, b + 3, a + 3),
            (a, b, b + 2, a + 2), (a + 1, a + 3, b + 3, b + 1),
        ])
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    coll.objects.link(obj)
    return obj


def add_pipe(name, points, radius, mat, coll=MODEL, closed=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 4
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new('NURBS')
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0) if len(co) == 3 else (co[0], co[1], 0.126, 1.0)
    spline.order_u = min(3, len(points))
    spline.use_endpoint_u = True
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, curve)
    curve.materials.append(mat)
    coll.objects.link(obj)
    return obj


def add_text(name, body, location, size, mat, align='CENTER'):
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body = body
    curve.align_x = align
    curve.align_y = 'CENTER'
    curve.size = size
    curve.extrude = 0.0012
    curve.bevel_depth = 0.00025
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    curve.materials.append(mat)
    MODEL.objects.link(obj)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


# 1) Structural blockout: a fully enclosed annular tunnel with clear acrylic walls and roof.
add_box('MESH_BASE_01', (0, 0, 0.04), (1.05, 0.58, 0.08), MAT_BASE, bevel=0.018)
floor_path = racetrack_points(0.285, 0.145)
outer_path = racetrack_points(0.285, 0.195)
inner_path = racetrack_points(0.205, 0.085)
add_ribbon('MESH_RING_FLOOR', floor_path, 0.056, 0.08, 0.112, MAT_FLOOR)
add_ribbon('MESH_RING_OUTER_ACRYLIC', outer_path, 0.008, 0.112, 0.345, MAT_ACRYLIC)
add_ribbon('MESH_RING_INNER_ACRYLIC', inner_path, 0.008, 0.112, 0.345, MAT_ACRYLIC)
add_annular_roof('MESH_RING_ACRYLIC_ROOF', outer_path, inner_path, 0.345, 0.370, MAT_ACRYLIC)
add_ribbon('MESH_RING_OUTER_RAIL', outer_path, 0.008, 0.370, 0.380, MAT_FRAME)
add_ribbon('MESH_RING_INNER_RAIL', inner_path, 0.008, 0.370, 0.380, MAT_FRAME)

# Roof-mounted removable hatches make the sealed enclosure physically credible:
# each sensing zone has an independent maintenance access point.
hatch_specs = [
    ('A', (-0.265, -0.140, 0.377), MAT_CYAN),
    ('B', (0.000, -0.140, 0.377), MAT_CYAN),
    ('C', (0.255, -0.140, 0.377), MAT_ORANGE),
]
for zone, loc, accent in hatch_specs:
    add_box('MESH_ROOF_HATCH_' + zone, loc, (0.135, 0.075, 0.008), MAT_FRAME, bevel=0.004)
    add_box('GEO_HATCH_STRIPE_' + zone, (loc[0], loc[1] - 0.021, 0.382), (0.080, 0.008, 0.004), accent, bevel=0.001)
    for dx in (-0.052, 0.052):
        for dy in (-0.025, 0.025):
            add_cylinder('GEO_HATCH_BOLT_%s_%s_%s' % (zone, 'L' if dx < 0 else 'R', 'F' if dy < 0 else 'B'), (loc[0] + dx, loc[1] + dy, 0.383), 0.004, 0.005, MAT_WHITE, vertices=16)
add_box('MESH_ROOF_VENT_C', (0.255, -0.105, 0.382), (0.082, 0.020, 0.006), MAT_FRAME, bevel=0.002)
for idx, xoff in enumerate((-0.026, -0.013, 0.0, 0.013, 0.026)):
    add_box('GEO_ROOF_LOUVER_C_%02d' % idx, (0.255 + xoff, -0.105, 0.387), (0.006, 0.026, 0.004), MAT_ORANGE, bevel=0.001)

# Structural cross-ribs that define A/B/C zones.
for name, x, mat in [('GEO_ZONE_A_RIB', -0.205, MAT_CYAN), ('GEO_ZONE_B_RIB', 0.0, MAT_CYAN), ('GEO_ZONE_C_RIB', 0.215, MAT_ORANGE)]:
    add_box(name, (x, -0.145, 0.227), (0.012, 0.11, 0.20), mat, bevel=0.003)

# Low-profile floor keys make the three sensing zones legible in a real build
# without competing with the pipes, water tray, or sensor enclosures.
add_box('GEO_ZONE_A_FLOOR_KEY', (-0.295, -0.090, 0.116), (0.105, 0.020, 0.004), MAT_CYAN, bevel=0.002)
add_box('GEO_ZONE_B_FLOOR_KEY', (0.020, -0.205, 0.116), (0.105, 0.020, 0.004), MAT_CYAN, bevel=0.002)
add_box('GEO_ZONE_C_FLOOR_KEY', (0.305, -0.090, 0.116), (0.105, 0.020, 0.004), MAT_ORANGE, bevel=0.002)

# Vertical seam bars denote removable acrylic service panels.  Their front
# placement also makes the A/B/C split readable with the shell installed.
for idx, x in enumerate((-0.205, 0.0, 0.215)):
    seam_mat = MAT_ORANGE if idx == 2 else MAT_CYAN
    add_box('GEO_ACRYLIC_SERVICE_SEAM_%02d' % (idx + 1), (x, -0.198, 0.226), (0.006, 0.010, 0.205), seam_mat, bevel=0.002)

# 2) Independent systems: sealed monitored gas pipe, ventilation, utility/cable,
#    and controlled drip-water. G01 is intentionally not a classroom gas-flow
#    experiment: it is the monitored pipe and its abnormal state is simulated by
#    an isolated signal box, as required by the project safety baseline.
gas_ring_path = [(x, y, 0.205) for x, y in racetrack_points(0.245, 0.112)]
add_pipe('MESH_PIPE_G01', gas_ring_path, 0.016, MAT_GAS, closed=True)
# Capped service bosses make the closed-pipe condition legible without implying
# a live supply connection. They are removable inspection features only.
add_cylinder('MESH_G01_SERVICE_CAP_A', (-0.330, -0.112, 0.205), 0.024, 0.014, MAT_FRAME, rotation=(0, math.pi / 2, 0))
add_cylinder('MESH_G01_SERVICE_CAP_B', (0.330, -0.112, 0.205), 0.024, 0.014, MAT_FRAME, rotation=(0, math.pi / 2, 0))
add_cylinder('MESH_LEAK_G01', (-0.245, 0.112, 0.226), 0.007, 0.042, MAT_RED)
add_uvsphere('GEO_LEAK_G01_GLOW', (-0.245, 0.112, 0.250), 0.010, MAT_RED)
# Separate low-pressure ventilation route: it removes air from C zone when a
# simulated alarm is active. Cyan arrows communicate its direction clearly.
vent_route = [(0.345, -0.108, 0.215), (0.405, -0.108, 0.215), (0.430, -0.020, 0.245), (0.340, 0.055, 0.275), (0.255, 0.055, 0.300)]
add_pipe('MESH_VENT_01', vent_route, 0.010, MAT_CYAN)
for idx, pos in enumerate([(0.392, -0.108, 0.218), (0.415, -0.050, 0.246), (0.335, 0.056, 0.278)]):
    arrow = add_box('GEO_VENT_FLOW_ARROW_%02d' % (idx + 1), pos, (0.025, 0.006, 0.008), MAT_CYAN, bevel=0.001)
    arrow.rotation_euler[2] = math.radians(30 if idx == 1 else 0)
utility_loop = [(x, y, 0.165) for x, y in racetrack_points(0.265, 0.125)]
data_loop = [(x, y, 0.145) for x, y in racetrack_points(0.235, 0.102)]
add_pipe('MESH_PIPE_UTILITY_01', utility_loop, 0.0095, MAT_PIPE, closed=True)
add_pipe('MESH_PIPE_UTILITY_02', data_loop, 0.0065, MAT_CYAN, closed=True)
drip_route = [(-0.185, -0.145, 0.240), (-0.185, -0.145, 0.185), (-0.085, -0.145, 0.185), (-0.040, -0.150, 0.165), (-0.015, -0.152, 0.150)]
add_pipe('MESH_PIPE_W01', drip_route, 0.006, MAT_CYAN)
add_cylinder('MESH_DRIP_W01', (-0.185, -0.145, 0.242), 0.010, 0.035, MAT_CYAN)
for idx, pos in enumerate([(0.425, -0.108, 0.205), (0.235, 0.125, 0.205), (-0.20, 0.125, 0.165), (-0.20, -0.125, 0.165)]):
    add_box('GEO_PIPE_CLAMP_%02d' % idx, pos, (0.018, 0.026, 0.032), MAT_FRAME, bevel=0.002)
add_pipe('MESH_LED_RING', racetrack_points(0.245, 0.118), 0.0035, MAT_CYAN)

# Water tray at the low B zone.
add_box('MESH_WATER_TRAY', (0.015, -0.152, 0.132), (0.17, 0.072, 0.024), MAT_CYAN, bevel=0.008)
add_box('MESH_WATER_SURFACE', (0.015, -0.152, 0.147), (0.145, 0.052, 0.004), MAT_WATER, bevel=0.003)
# The independent high-level switch is deliberately taller than the wet probe,
# so the physical protection path is not confused with normal seepage sensing.
add_cylinder('MESH_HILEVEL_01', (0.095, -0.152, 0.188), 0.004, 0.076, MAT_FRAME)
add_uvsphere('GEO_HILEVEL_FLOAT_01', (0.095, -0.152, 0.166), 0.011, MAT_ORANGE)
add_box('MESH_LEAK_W01', (-0.185, -0.145, 0.258), (0.030, 0.030, 0.018), MAT_CYAN, bevel=0.003)
add_box('MESH_DRIP_GUARD_01', (-0.185, -0.145, 0.222), (0.044, 0.044, 0.006), MAT_FRAME, bevel=0.002)

# Fan enclosure and blades in C zone.
fan = add_cylinder('MESH_FAN_01', (0.345, -0.108, 0.215), 0.047, 0.018, MAT_FRAME, rotation=(math.pi / 2, 0, 0))
for a in range(0, 360, 72):
    blade = add_box('GEO_FAN_BLADE_%03d' % a, (0.345, -0.119, 0.215), (0.010, 0.004, 0.038), MAT_ORANGE, bevel=0.002)
    blade.rotation_euler[1] = math.radians(a)
add_cylinder('GEO_FAN_HUB', (0.345, -0.121, 0.215), 0.010, 0.006, MAT_ORANGE, rotation=(math.pi / 2, 0, 0))
# These two adjacent modules represent real execution evidence: speed pulses and
# motor current, so the twin need not treat a control command as proof of motion.
add_box('MESH_FAN_TACH_01', (0.405, -0.121, 0.215), (0.026, 0.018, 0.022), MAT_GREEN, bevel=0.003)
add_box('MESH_FAN_CURR_01', (0.405, -0.121, 0.182), (0.026, 0.018, 0.022), MAT_CYAN, bevel=0.003)

# 3) Sensor enclosures: independently named objects for digital-twin interaction.
def sensor_box(name, loc, color, dims=(0.042, 0.023, 0.030)):
    obj = add_box(name, loc, dims, color, bevel=0.005)
    add_cylinder('GEO_' + name + '_LENS', (loc[0], loc[1] - dims[1] / 2 - 0.002, loc[2]), 0.008, 0.005, MAT_WHITE, rotation=(math.pi / 2, 0, 0))
    return obj

# The gas sensors are distributed around the annular G01 main rather than
# clustered on a straight run, representing three distinct monitoring zones.
sensor_box('MESH_GAS_CH4_01', (-0.155, -0.124, 0.305), MAT_ORANGE, dims=(0.070, 0.032, 0.042))
sensor_box('MESH_GAS_CO_01', (0.155, -0.124, 0.270), MAT_RED, dims=(0.070, 0.032, 0.042))
sensor_box('MESH_GAS_O2_01', (0.355, 0.000, 0.235), MAT_GREEN, dims=(0.070, 0.032, 0.042))
# Each sensor sits above a removable inline sampling chamber.  The chambers
# deliberately overlap the pipe by 12 mm, so the route reads as continuous.
for sensor_id, chamber_loc in [
    ('CH4', (-0.155, -0.112, 0.205)),
    ('CO', (0.155, -0.112, 0.205)),
    ('O2', (0.357, 0.000, 0.205)),
]:
    add_box('MESH_G01_SAMPLE_CHAMBER_' + sensor_id, chamber_loc, (0.070, 0.046, 0.048), MAT_FRAME, bevel=0.004)
sensor_box('MESH_ENV_01', (-0.345, 0.070, 0.215), MAT_CYAN)
sensor_box('MESH_DOOR_01', (-0.395, -0.075, 0.205), MAT_CYAN, dims=(0.030, 0.018, 0.055))
sensor_box('MESH_SEEP_W01', (-0.040, -0.150, 0.165), MAT_CYAN, dims=(0.036, 0.020, 0.023))
sensor_box('MESH_LEVEL_01', (0.075, -0.150, 0.172), MAT_CYAN, dims=(0.026, 0.018, 0.050))
sensor_box('MESH_MOIST_01', (-0.090, -0.150, 0.158), MAT_CYAN, dims=(0.025, 0.018, 0.018))
# One DS18B20-style local-temperature point in each zone supports the required
# A/B/C comparison; the small heat pad is low-voltage and only a demo source.
sensor_box('MESH_TEMP_A01', (-0.315, 0.112, 0.185), MAT_CYAN, dims=(0.032, 0.018, 0.022))
sensor_box('MESH_TEMP_B01', (0.012, 0.090, 0.160), MAT_CYAN, dims=(0.032, 0.018, 0.022))
sensor_box('MESH_TEMP_C01', (0.255, 0.090, 0.185), MAT_ORANGE, dims=(0.032, 0.018, 0.022))
add_box('MESH_HEATER_01', (0.045, 0.070, 0.136), (0.080, 0.040, 0.008), MAT_ORANGE, bevel=0.003)
add_cylinder('MESH_SMOKE_01', (0.115, 0.120, 0.314), 0.022, 0.016, MAT_RED)
add_cylinder('GEO_SMOKE_GRILLE', (0.115, 0.120, 0.305), 0.015, 0.004, MAT_WHITE)
sensor_box('MESH_VIB_01', (0.285, -0.132, 0.175), MAT_RED, dims=(0.028, 0.020, 0.022))

# Gas sensor brackets keep the three modules adjacent to the monitored pipe and
# leak point, while explicitly leaving G01 sealed. The modules sample enclosure
# air and report a real baseline; abnormal values come from the isolated simulator.
gas_sensor_specs = [
    ('CH4', (-0.155, -0.112, 0.205), MAT_ORANGE, (0, math.pi / 2, 0), 0.305),
    ('CO', (0.155, -0.112, 0.205), MAT_RED, (0, math.pi / 2, 0), 0.270),
    ('O2', (0.357, 0.000, 0.205), MAT_GREEN, (math.pi / 2, 0, 0), 0.235),
]
for sensor_id, collar_loc, sensor_mat, collar_rotation, sensor_z in gas_sensor_specs:
    add_cylinder('MESH_G01_COLLAR_' + sensor_id, collar_loc, 0.023, 0.030, MAT_FRAME, rotation=collar_rotation, vertices=24)
    add_cylinder('GEO_G01_COLOR_BAND_' + sensor_id, collar_loc, 0.025, 0.008, sensor_mat, rotation=collar_rotation, vertices=24)
    stand_top = sensor_z - 0.015
    stand_height = max(0.022, stand_top - 0.205)
    add_box('GEO_G01_SENSOR_STAND_' + sensor_id, (collar_loc[0], collar_loc[1], 0.205 + stand_height / 2), (0.012, 0.016, stand_height), sensor_mat, bevel=0.002)
    add_uvsphere('GEO_G01_STATUS_' + sensor_id, (collar_loc[0], collar_loc[1] - 0.012, sensor_z + 0.028), 0.007, sensor_mat)
add_text('GEO_G01_SENSOR_LABEL_CH4', 'CH4', (-0.155, -0.146, 0.328), 0.014, MAT_ORANGE)
add_text('GEO_G01_SENSOR_LABEL_CO', 'CO', (0.155, -0.146, 0.296), 0.014, MAT_RED)
add_text('GEO_G01_SENSOR_LABEL_O2', 'O2', (0.355, -0.032, 0.260), 0.014, MAT_GREEN)
add_text('GEO_G01_FLOW', 'PIPE-G01  SEALED / MONITORED', (0.000, -0.146, 0.174), 0.010, MAT_ORANGE)
# Four low-profile stanchions stop the ring from appearing to float and provide
# realistic support points for the physical acrylic-tunnel prototype.
for idx, (x, y) in enumerate([(0.000, -0.112), (0.245, 0.112), (-0.245, 0.112), (-0.357, 0.000)]):
    add_box('GEO_G01_STANCHION_%02d' % (idx + 1), (x, y, 0.157), (0.012, 0.018, 0.092), MAT_FRAME, bevel=0.002)
    add_box('GEO_G01_STANCHION_FOOT_%02d' % (idx + 1), (x, y, 0.116), (0.042, 0.036, 0.008), MAT_FRAME, bevel=0.002)

# 3b) Physical build details: isolated control bay, service trunking, mounting plates and water barrier.
add_box('MESH_CTRL_DRY_BAY', (-0.355, -0.190, 0.145), (0.165, 0.095, 0.085), MAT_FRAME, bevel=0.008)
sensor_box('MESH_CTRL_01', (-0.355, -0.190, 0.205), MAT_GREEN, dims=(0.095, 0.045, 0.070))
add_box('MESH_DISP_01', (-0.355, -0.238, 0.220), (0.050, 0.006, 0.030), MAT_WHITE, bevel=0.003)
add_box('MESH_PCB_01', (-0.314, -0.166, 0.190), (0.062, 0.036, 0.006), MAT_GREEN, bevel=0.002)
add_box('MESH_RELAY_01', (-0.400, -0.180, 0.205), (0.030, 0.026, 0.025), MAT_CYAN, bevel=0.003)
add_cylinder('MESH_BUZZ_01', (-0.355, -0.190, 0.260), 0.016, 0.010, MAT_RED)
sensor_box('MESH_BT_01', (-0.305, -0.205, 0.220), MAT_CYAN, dims=(0.030, 0.020, 0.018))
# Network, alarm and physical emergency-stop elements are individually named
# because they each have an independent twin/telemetry state in the project.
sensor_box('MESH_NET_01', (-0.300, -0.205, 0.248), MAT_CYAN, dims=(0.034, 0.022, 0.018))
add_cylinder('GEO_NET_ANTENNA_01', (-0.300, -0.205, 0.272), 0.003, 0.040, MAT_FRAME)
add_cylinder('MESH_ESTOP_01', (-0.405, -0.238, 0.245), 0.018, 0.016, MAT_RED)
add_cylinder('GEO_ESTOP_BEZEL_01', (-0.405, -0.238, 0.235), 0.024, 0.008, MAT_FRAME)
add_cylinder('MESH_ALARM_01', (-0.455, -0.180, 0.267), 0.014, 0.016, MAT_RED)
add_cylinder('GEO_ALARM_BASE_01', (-0.455, -0.180, 0.253), 0.018, 0.006, MAT_FRAME)
add_box('MESH_SIMBOX_01', (-0.240, -0.205, 0.190), (0.055, 0.034, 0.030), MAT_ORANGE, bevel=0.004)
add_box('GEO_SIMBOX_ISOLATION_STRIPE', (-0.240, -0.223, 0.190), (0.032, 0.003, 0.010), MAT_WHITE, bevel=0.001)
for idx, z in enumerate((0.195, 0.215, 0.235)):
    led_mat = (MAT_GREEN, MAT_ORANGE, MAT_RED)[idx]
    add_uvsphere('MESH_LED_01' if idx == 0 else 'GEO_LED_STACK_%02d' % idx, (-0.450, -0.020, z), 0.008, led_mat)
add_box('MESH_CABLE_DUCT_01', (-0.020, -0.248, 0.112), (0.700, 0.026, 0.032), MAT_FRAME, bevel=0.004)
add_box('GEO_CABLE_DUCT_COVER', (-0.020, -0.248, 0.131), (0.690, 0.020, 0.006), MAT_PIPE, bevel=0.002)
add_box('MESH_WATER_BARRIER_01', (-0.125, -0.150, 0.165), (0.010, 0.095, 0.080), MAT_CYAN, bevel=0.002)
add_box('MESH_WATER_BARRIER_02', (0.145, -0.150, 0.165), (0.010, 0.095, 0.080), MAT_CYAN, bevel=0.002)

mount_specs = [
    ('GAS_CH4_01', (-0.155, -0.087, 0.305), MAT_FRAME),
    ('GAS_CO_01', (0.155, -0.087, 0.270), MAT_FRAME),
    ('GAS_O2_01', (0.355, 0.033, 0.235), MAT_FRAME),
    ('ENV_01', (-0.345, 0.091, 0.215), MAT_FRAME),
]
for mount_id, mount_loc, mount_mat in mount_specs:
    add_box('MESH_MOUNT_' + mount_id, mount_loc, (0.064, 0.006, 0.066), mount_mat, bevel=0.003)
    for dx in (-0.021, 0.021):
        add_cylinder('GEO_MOUNT_SCREW_' + mount_id + ('_L' if dx < 0 else '_R'), (mount_loc[0] + dx, mount_loc[1] - 0.005, mount_loc[2]), 0.003, 0.006, MAT_WHITE, rotation=(math.pi / 2, 0, 0), vertices=16)
add_box('MESH_SMOKE_MOUNT_01', (0.115, 0.120, 0.300), (0.062, 0.062, 0.006), MAT_FRAME, bevel=0.003)
add_box('MESH_SERVICE_HANDLE_A', (-0.460, -0.030, 0.275), (0.012, 0.045, 0.018), MAT_FRAME, bevel=0.004)
# A paired latch and header make the left access panel unambiguous for assembly.
add_box('GEO_SERVICE_LATCH_A', (-0.460, -0.030, 0.235), (0.012, 0.025, 0.012), MAT_ORANGE, bevel=0.003)
add_box('GEO_SERVICE_HEADER_A', (-0.355, -0.198, 0.318), (0.145, 0.010, 0.010), MAT_FRAME, bevel=0.002)
add_box('MESH_DOOR_CONTACT_01', (-0.445, -0.065, 0.220), (0.026, 0.012, 0.046), MAT_CYAN, bevel=0.002)
add_box('GEO_DOOR_MAGNET_01', (-0.426, -0.065, 0.220), (0.008, 0.012, 0.035), MAT_WHITE, bevel=0.001)

# 4) Zone and functional labels are shallow mesh-text for the preview and GLB.
add_text('GEO_LABEL_ZONE_A', 'A  环境', (-0.285, -0.020, 0.117), 0.026, MAT_WHITE)
add_text('GEO_LABEL_ZONE_B', 'B  渗水', (0.010, -0.188, 0.117), 0.022, MAT_WHITE)
add_text('GEO_LABEL_ZONE_C', 'C  气体', (0.315, 0.012, 0.117), 0.024, MAT_WHITE)
add_text('GEO_LABEL_CH4', 'CH4', (-0.155, -0.150, 0.338), 0.014, MAT_ORANGE)
add_text('GEO_LABEL_CO', 'CO', (0.155, -0.150, 0.315), 0.014, MAT_RED)
add_text('GEO_LABEL_O2', 'O2', (0.355, -0.040, 0.280), 0.014, MAT_GREEN)
add_text('GEO_LABEL_SMOKE', 'SMOKE', (0.115, 0.095, 0.335), 0.010, MAT_RED)
add_text('GEO_LABEL_TEMP_A', 'T-A', (-0.315, 0.092, 0.205), 0.010, MAT_CYAN)
add_text('GEO_LABEL_TEMP_B', 'T-B', (0.012, 0.070, 0.180), 0.010, MAT_CYAN)
add_text('GEO_LABEL_TEMP_C', 'T-C', (0.255, 0.070, 0.205), 0.010, MAT_ORANGE)
add_text('GEO_LABEL_HILEVEL', 'HH', (0.095, -0.178, 0.205), 0.011, MAT_ORANGE)
add_text('GEO_LABEL_ESTOP', 'STOP', (-0.405, -0.252, 0.270), 0.010, MAT_RED)
add_text('GEO_LABEL_SIMBOX', 'SIM', (-0.240, -0.226, 0.212), 0.010, MAT_ORANGE)
# Exterior labels deliberately repeat the internal zones so operation remains
# legible while the enclosure is fully closed.
add_text('GEO_ROOF_LABEL_A', 'A  ENV', (-0.265, -0.158, 0.384), 0.015, MAT_WHITE)
add_text('GEO_ROOF_LABEL_B', 'B  WTR', (0.000, -0.158, 0.384), 0.015, MAT_WHITE)
add_text('GEO_ROOF_LABEL_C', 'C  GAS', (0.255, -0.158, 0.384), 0.015, MAT_WHITE)

# 5) Dedicated hero camera, floor, and lights. Existing scene objects remain untouched.
bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.002))
ground = bpy.context.object
ground.name = 'GEO_UT_RING_RENDER_GROUND'
ground.data.materials.append(material('MAT-render_ground', (0.012, 0.021, 0.03), roughness=0.48))
link(ground, RENDER)

cam_data = bpy.data.cameras.get('CAM-UT_RING_HERO') or bpy.data.cameras.new('CAM-UT_RING_HERO')
cam = bpy.data.objects.get('CAM-UT_RING_HERO') or bpy.data.objects.new('CAM-UT_RING_HERO', cam_data)
if not cam.users_collection:
    RENDER.objects.link(cam)
elif RENDER not in cam.users_collection:
    link(cam, RENDER)
cam.location = (1.02, -1.22, 0.82)
cam.data.lens = 56
look_at(cam, (0.0, 0.0, 0.17))
SCENE.camera = cam

def area(name, location, energy, size, color):
    data = bpy.data.lights.get(name) or bpy.data.lights.new(name, 'AREA')
    data.energy, data.shape, data.size, data.color = energy, 'DISK', size, color
    obj = bpy.data.objects.get(name) or bpy.data.objects.new(name, data)
    if not obj.users_collection:
        RENDER.objects.link(obj)
    elif RENDER not in obj.users_collection:
        link(obj, RENDER)
    obj.location = location
    look_at(obj, (0.0, 0.0, 0.15))
    return obj

area('LGT-UT_RING_KEY', (0.65, -0.82, 1.15), 210, 0.55, (0.92, 0.97, 1.0))
area('LGT-UT_RING_FILL', (-0.72, -0.30, 0.65), 70, 0.65, (0.30, 0.62, 1.0))
area('LGT-UT_RING_RIM', (0.10, 0.72, 1.00), 135, 0.42, (1.0, 0.34, 0.12))

SCENE.world.color = (0.007, 0.012, 0.02)
try:
    SCENE.render.engine = 'BLENDER_EEVEE_NEXT'
except (TypeError, ValueError):
    SCENE.render.engine = 'BLENDER_EEVEE'
SCENE.render.resolution_x = 1500
SCENE.render.resolution_y = 1050
SCENE.render.resolution_percentage = 100
SCENE.render.image_settings.file_format = 'PNG'
SCENE.render.image_settings.color_mode = 'RGBA'
SCENE.render.filepath = PREVIEW_PATH
SCENE.render.film_transparent = False
SCENE.view_settings.exposure = -1.15
if hasattr(SCENE.view_settings, 'look'):
    try:
        SCENE.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass

# Temporarily hide only the prior test cube during this deliverable's render.
prior_cube = bpy.data.objects.get('立方体')
prior_render_state = prior_cube.hide_render if prior_cube else None
if prior_cube:
    prior_cube.hide_render = True
bpy.ops.render.render(write_still=True)
if prior_cube:
    prior_cube.hide_render = prior_render_state

# A companion presentation-cutaway removes only the roof and outer acrylic at
# render time. The stored/exported model remains fully enclosed; this view is
# evidence for reviewers who need to read sensors and safety hardware clearly.
cutaway_names = [
    'MESH_RING_ACRYLIC_ROOF', 'MESH_RING_OUTER_ACRYLIC', 'MESH_RING_INNER_ACRYLIC',
    'MESH_RING_OUTER_RAIL', 'MESH_RING_INNER_RAIL'
]
cutaway_state = {}
for name in cutaway_names:
    obj = bpy.data.objects.get(name)
    if obj:
        cutaway_state[name] = obj.hide_render
        obj.hide_render = True
cam_location_before_cutaway = cam.location.copy()
cam_lens_before_cutaway = cam.data.lens
cam.location = (0.78, -1.15, 1.18)
cam.data.lens = 60
look_at(cam, (0.0, -0.01, 0.19))
SCENE.render.filepath = FUNCTIONAL_PREVIEW_PATH
bpy.ops.render.render(write_still=True)
for name, hide_render in cutaway_state.items():
    bpy.data.objects[name].hide_render = hide_render
cam.location = cam_location_before_cutaway
cam.data.lens = cam_lens_before_cutaway
look_at(cam, (0.0, 0.0, 0.17))
SCENE.render.filepath = PREVIEW_PATH

# Export the task-owned model objects only; cameras/lights/ground stay out of GLB.
bpy.ops.object.select_all(action='DESELECT')
for obj in MODEL.objects:
    if obj.type in {'MESH', 'CURVE', 'FONT'}:
        obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get('MESH_BASE_01')

try:
    bpy.ops.export_scene.gltf(
        filepath=GLB_PATH,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials='EXPORT',
        export_cameras=False,
        export_lights=False,
    )
except TypeError:
    bpy.ops.export_scene.gltf(filepath=GLB_PATH, export_format='GLB', export_apply=True, export_yup=True)

bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)

mesh_objects = [obj for obj in MODEL.objects if obj.type == 'MESH']
triangles = sum(len(obj.data.polygons) for obj in mesh_objects)
print({
    'model_collection': MODEL.name,
    'objects': len(MODEL.objects),
    'mesh_objects': len(mesh_objects),
    'polygon_count': triangles,
    'blend': BLEND_PATH,
    'glb': GLB_PATH,
    'preview': PREVIEW_PATH,
    'functional_preview': FUNCTIONAL_PREVIEW_PATH,
})
