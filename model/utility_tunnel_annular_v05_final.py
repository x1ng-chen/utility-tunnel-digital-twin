"""Re-export the official V05 model after its same-day history was consolidated."""
import bpy
import os

ROOT = r"D:\shixi\model"
BLEND = os.path.join(ROOT, "utility-tunnel-annular-v05-final.blend")
GLB = os.path.join(ROOT, "utility-tunnel-annular-v05-final.glb")

if not os.path.exists(BLEND):
    raise RuntimeError("Open or restore the official V05 Blend before re-exporting.")
if os.path.normcase(bpy.data.filepath) != os.path.normcase(BLEND):
    bpy.ops.wm.open_mainfile(filepath=BLEND)


def first(*names):
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj:
            return obj
    raise RuntimeError("Missing required V05 object: " + " / ".join(names))


def named(obj, target, asset_id):
    obj.name = target
    if obj.type == "CURVE":
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.convert(target="MESH")
        obj = bpy.context.object
    if obj.type == "MESH":
        if obj.data.users > 1:
            obj.data = obj.data.copy()
        obj.data.name = target
    obj["asset_id"] = asset_id
    obj["physical_interface"] = "TEMP_NOT_MEASURED"
    return obj


for code in ("L01", "L02", "L03", "L04", "L05"):
    prefix = "V17_FSIR02_" + code
    named(first("LEVEL-" + code, "MESH_" + prefix + "_BOARD"), "LEVEL-" + code, "LEVEL-" + code)
    named(first("LEVEL-" + code + "-PROBE_TEMP", "MESH_" + prefix + "_PROBE_BODY"), "LEVEL-" + code + "-PROBE_TEMP", "LEVEL-" + code)
    named(first("LEVEL-" + code + "-BRACKET_TEMP", "MESH_" + prefix + "_MOUNT_PLATE"), "LEVEL-" + code + "-BRACKET_TEMP", "LEVEL-" + code)
    named(first("LEVEL-" + code + "-HARNESS", "GEO_" + prefix + "_TO_LOCAL_LOOM"), "LEVEL-" + code + "-HARNESS", "LEVEL-" + code)
    named(first("LEVEL-" + code + "-STATUS", "GEO_" + prefix + "_OPTIC"), "LEVEL-" + code + "-STATUS", "LEVEL-" + code)

for old, target in (("MESH_PIPE_G01", "PIPE-G01"), ("MESH_WATER_TRAY", "WATER-TRAY-01"),
                    ("MESH_FAN_01", "FAN-01"), ("MESH_GAS_CH4_01", "GAS-01")):
    obj = bpy.data.objects.get(target) or bpy.data.objects.get(old)
    if obj:
        named(obj, target, target)

bpy.ops.object.select_all(action="DESELECT")
for obj in bpy.context.scene.objects:
    if obj.type in {"MESH", "CURVE", "FONT", "EMPTY"}:
        obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", use_selection=True,
                           export_apply=True, export_materials="EXPORT", export_yup=True)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print({"version": "V05", "blend": BLEND, "glb": GLB, "stations": 5})
