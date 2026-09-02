"""Build the V07 final model from the immutable V06 release.

V07 removes historical duplicate display layers from the published scene and
keeps the current functional assets in four visually separated maintenance
zones.  All offsets are visual-only TEMP layout values, not fabrication data.
"""

from pathlib import Path
import re

import bpy
from mathutils import Vector


ROOT = Path(r"D:\\shixi\\model")
SOURCE = ROOT / "utility-tunnel-annular-v06-final.blend"
BLEND_OUT = ROOT / "utility-tunnel-annular-v07-final.blend"
GLB_OUT = ROOT / "utility-tunnel-annular-v07-final.glb"


def separate_group(scene, name, predicate, location):
    """Parent a functional zone to a named empty and place it reproducibly."""
    group = bpy.data.objects.get(name)
    if group is None:
        group = bpy.data.objects.new(name, None)
        scene.collection.objects.link(group)
    group.empty_display_type = "PLAIN_AXES"
    group.empty_display_size = 0.03

    moved = []
    for obj in list(scene.objects):
        if obj is not group and not obj.hide_get() and predicate(obj):
            obj.parent = group
            obj.matrix_parent_inverse = group.matrix_world.inverted()
            moved.append(obj.name)
    group.location = Vector(location)
    return moved


if not SOURCE.exists():
    raise RuntimeError(f"Missing V06 source: {SOURCE}")

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene

# These layers are retained in the V06 engineering source for traceability,
# but were historical duplicate layouts rather than current functional assets.
# V16/V17/V20/V21 are intentionally retained because V06 documents them as
# current roof/fan compatibility nodes.
legacy_versions = ("V09", "V11", "V12", "V13", "V14", "V15", "V18", "V35")
hidden = []
for obj in scene.objects:
    if any(re.search(rf"(?<!\\d){version}(?!\\d)", obj.name) for version in legacy_versions):
        obj.hide_set(True)
        obj.hide_render = True
        hidden.append(obj.name)

# A: control front-left; B: liquid-level front rail and low water equipment;
# C: gas/vent right-rear.  These are visual maintenance zones only.
moved = {
    "control": separate_group(
        scene,
        "GEO-V07-GRP-CONTROL",
        lambda o: o.name == "CTRL-01" or o.name.startswith("GEO_CTRL_") or o.name.startswith("MESH_CTRL_"),
        (-0.210, -0.155, 0.000),
    ),
    "levels": separate_group(
        scene,
        "GEO-V07-GRP-LEVEL",
        lambda o: o.name.startswith("LEVEL-L"),
        (0.000, -0.105, 0.055),
    ),
    "water": separate_group(
        scene,
        "GEO-V07-GRP-WATER",
        lambda o: ("WATER-TRAY" in o.name or "WATER_TANK" in o.name or
                   o.name in {"P-01", "V-01"} or o.name.startswith("GEO_AIR_PUMP")),
        (0.100, 0.075, 0.000),
    ),
    "gas_vent": separate_group(
        scene,
        "GEO-V07-GRP-GAS-VENT",
        lambda o: (o.name == "GAS-01" or o.name.startswith("GEO_GAS_") or
                   o.name.startswith("MESH_GAS_") or "PIPE_G01" in o.name),
        (0.270, 0.195, 0.020),
    ),
}

scene["model_version"] = "V07"
scene["source_version"] = "V06"
scene["layout_scope"] = "Historical overlap cleanup and functional-zone clearance."
scene["clearance_policy"] = "Visual TEMP layout only; not fabrication dimensions or safety approval."
scene["hidden_legacy_object_count"] = len(hidden)
scene["moved_object_counts"] = {key: len(value) for key, value in moved.items()}

bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_OUT))

# Only the current, non-hidden scene content is included in the web artifact.
if hasattr(bpy.context, "active_object"):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        if obj.type in {"MESH", "CURVE", "FONT", "EMPTY"} and not obj.hide_get():
            obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=str(GLB_OUT),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_materials="EXPORT",
        export_image_format="AUTO",
        export_yup=True,
        export_animations=True,
        export_normals=True,
    )

    if not GLB_OUT.exists() or GLB_OUT.stat().st_size == 0:
        raise RuntimeError(f"V07 GLB export failed: {GLB_OUT}")
else:
    print("GLB export deferred: Blender context was reloaded; execute the export in a fresh context.")

print({
    "version": "V07",
    "blend": str(BLEND_OUT),
    "glb": str(GLB_OUT),
    "glb_bytes": GLB_OUT.stat().st_size if GLB_OUT.exists() else 0,
    "hidden_legacy_object_count": len(hidden),
    "moved_object_counts": {key: len(value) for key, value in moved.items()},
})
