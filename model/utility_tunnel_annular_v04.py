"""V04 annular utility-tunnel demonstrator.

This wraps the earlier polished annular construction and completes the two
previously unclear functional paths: safe ambient-air sampling and drip-tray
leak demonstration.  It is a classroom-safe digital-twin demonstrator;
CH4/CO alarms originate in SIMBOX_01 and not from real hazardous gases.
"""
import bpy, os, math

ROOT = r"D:\shixi\model"
PRE = os.path.join(ROOT, "previews")
V04_BLEND = os.path.join(ROOT, "utility-tunnel-annular-v04.blend")
V04_GLB = os.path.join(ROOT, "utility-tunnel-annular-v04.glb")
WEB_GLB = r"D:\shixi\frontend\public\models\utility-tunnel.glb"
V04_HERO = os.path.join(PRE, "utility-tunnel-annular-v04-hero.png")
V04_FUNCTION = os.path.join(PRE, "utility-tunnel-annular-v04-functional.png")

# The shared live Blender session can contain earlier concept iterations.
# V04 must be generated in isolation so no V03 labels or geometry contaminate
# either the render or the exported asset.
for _obj in list(bpy.data.objects):
    bpy.data.objects.remove(_obj, do_unlink=True)

# The base generator contains the enclosed acrylic annulus, frame, G01 ring,
# A/B/C equipment, sensor mounting, roof hatches, lighting and camera.
BASE = os.path.join(ROOT, "utility_tunnel_ring_v01.py")
exec(compile(open(BASE, encoding="utf-8").read(), BASE, "exec"))

# ------------------------ V04 functional completion ------------------------
# C zone: external safe-air inlet -> inline sampling manifold -> fan -> roof.
# This cyan route is deliberately independent of the orange sealed G01 ring.
add_cylinder('MESH_AIR_IN_01_FILTER_PORT', (0.468, -0.060, 0.218), 0.027, 0.028,
             MAT_CYAN, rotation=(0, math.pi / 2, 0), vertices=32)
add_box('MESH_AIR_IN_01_FILTER_HOUSING', (0.445, -0.060, 0.218), (0.043, 0.066, 0.066), MAT_CYAN, bevel=0.006)
add_box('MESH_GAS_SAMPLE_MANIFOLD_01', (0.278, -0.090, 0.246), (0.086, 0.054, 0.048), MAT_FRAME, bevel=0.005)
safe_air_path = [(0.478, -0.060, 0.218), (0.425, -0.060, 0.218), (0.365, -0.082, 0.230), (0.320, -0.090, 0.246), (0.292, -0.100, 0.238), (0.345, -0.108, 0.215)]
add_pipe('MESH_AIR_IN_01_SAFE_ROUTE', safe_air_path, 0.009, MAT_CYAN)

# Three cyan chevrons express direction in a physical model, not just a label.
for idx, (x, y, z, rot) in enumerate(((0.415, -0.071, 0.222, 0), (0.355, -0.090, 0.236, -0.18), (0.315, -0.104, 0.231, 0.22))):
    arrow = add_box('GEO_AIRFLOW_ARROW_%02d' % (idx + 1), (x, y, z), (0.020, 0.006, 0.008), MAT_CYAN, bevel=0.001)
    arrow.rotation_euler[2] = rot
add_text('GEO_LABEL_AIR_IN', '安全进气', (0.405, -0.145, 0.271), 0.012, MAT_CYAN)
add_text('GEO_LABEL_AIR_OUT', '顶部排气', (0.255, 0.022, 0.326), 0.012, MAT_CYAN)

# B zone: nozzle -> visible droplets -> raised tray -> wet probe and HH float.
# The tray stays isolated from the dry control bay and is emptied manually.
for idx, z in enumerate((0.213, 0.190, 0.168)):
    add_uvsphere('MESH_WATER_DROP_%02d' % (idx + 1), (-0.015, -0.152, z), 0.010 - idx * 0.0015, MAT_WATER)
add_box('MESH_WATER_TRAY_RAISED_LIP_F', (0.015, -0.190, 0.151), (0.175, 0.008, 0.030), MAT_FRAME, bevel=0.003)
add_box('MESH_WATER_TRAY_RAISED_LIP_L', (-0.073, -0.152, 0.151), (0.008, 0.075, 0.030), MAT_FRAME, bevel=0.003)
add_box('MESH_WATER_TRAY_RAISED_LIP_R', (0.103, -0.152, 0.151), (0.008, 0.075, 0.030), MAT_FRAME, bevel=0.003)
add_cylinder('MESH_WATER_MANUAL_DRAIN_01', (0.015, -0.196, 0.132), 0.012, 0.012, MAT_CYAN, rotation=(math.pi / 2, 0, 0), vertices=24)
add_text('GEO_LABEL_WATER_FLOW', '滴水 → 水盘 → 液位报警', (0.015, -0.204, 0.116), 0.010, MAT_CYAN)

# G01 tells the correct story: a closed monitored mock pipeline with a marked
# simulated crack.  There is no second orange route and therefore no overlap.
add_box('MESH_LEAK_G01_SIGNAL_TAG', (-0.245, 0.092, 0.253), (0.045, 0.010, 0.020), MAT_RED, bevel=0.002)
add_text('GEO_LABEL_LEAK_G01', '模拟漏点', (-0.245, 0.077, 0.271), 0.010, MAT_RED)
add_text('GEO_LABEL_G01_CLOSED', 'G01 密闭环管', (0.010, 0.123, 0.225), 0.012, MAT_ORANGE)

# Clear visual separation between B wet zone and A dry control bay.
add_box('MESH_WET_DRY_PARTITION_V04', (-0.125, -0.150, 0.185), (0.008, 0.100, 0.105), MAT_ACRYLIC, bevel=0.002)

# Render full enclosure, then a readable cutaway.  The exported GLB retains
# all acrylic, access hatches and functional hardware.
SCENE.render.filepath = V04_HERO
bpy.ops.render.render(write_still=True)
cutaway_names = ['MESH_RING_ACRYLIC_ROOF', 'MESH_RING_OUTER_ACRYLIC', 'MESH_RING_INNER_ACRYLIC', 'MESH_RING_OUTER_RAIL', 'MESH_RING_INNER_RAIL']
states = {n: bpy.data.objects[n].hide_render for n in cutaway_names if n in bpy.data.objects}
for n in states: bpy.data.objects[n].hide_render = True
cam = SCENE.camera
old_location, old_lens = cam.location.copy(), cam.data.lens
cam.location = (0.78, -1.15, 1.18); cam.data.lens = 60; look_at(cam, (0.0, -0.01, 0.19))
SCENE.render.filepath = V04_FUNCTION
bpy.ops.render.render(write_still=True)
for n, state in states.items(): bpy.data.objects[n].hide_render = state
cam.location, cam.data.lens = old_location, old_lens; look_at(cam, (0.0, 0.0, 0.17))

bpy.ops.object.select_all(action='DESELECT')
for obj in MODEL.objects:
    if obj.type in {'MESH', 'CURVE', 'FONT'}: obj.select_set(True)
bpy.context.view_layer.objects.active = bpy.data.objects.get('MESH_BASE_01')
bpy.ops.export_scene.gltf(filepath=V04_GLB, export_format='GLB', use_selection=True, export_apply=True, export_yup=True, export_materials='EXPORT', export_cameras=False, export_lights=False)
# Web runtime delivery uses the project-standard filename.  Both GLB files
# are generated from the same selected objects and preserve asset mesh names.
os.makedirs(os.path.dirname(WEB_GLB), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=WEB_GLB, export_format='GLB', use_selection=True, export_apply=True, export_yup=True, export_materials='EXPORT', export_cameras=False, export_lights=False)
bpy.ops.wm.save_as_mainfile(filepath=V04_BLEND)
required = ['MESH_PIPE_G01', 'MESH_AIR_IN_01_FILTER_PORT', 'MESH_AIR_IN_01_SAFE_ROUTE', 'MESH_FAN_01', 'MESH_VENT_01', 'MESH_WATER_TRAY', 'MESH_WATER_DROP_01', 'MESH_HILEVEL_01', 'MESH_CTRL_01', 'MESH_SIMBOX_01']
missing = [n for n in required if bpy.data.objects.get(n) is None]
print({'V04_DONE': not missing, 'missing': missing, 'blend': V04_BLEND, 'glb': V04_GLB, 'web_glb': WEB_GLB})
