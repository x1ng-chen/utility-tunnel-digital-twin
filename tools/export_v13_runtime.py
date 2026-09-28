"""Export the visible V13 Blender scene as the frontend's GLB.

Run with Blender: blender -b --python tools/export_v13_runtime.py -- input.blend output.glb
The source file is opened read-only and is never saved by this script.
"""

import bpy
import json
import sys


def main():
    args = sys.argv[sys.argv.index("--") + 1 :]
    if len(args) != 2:
        raise SystemExit("expected source .blend and output .glb")
    source, output = args
    bpy.ops.wm.open_mainfile(filepath=source)
    for obj in bpy.data.objects:
        obj.select_set(False)
    visible = [
        obj for obj in bpy.data.objects
        if obj.type == "MESH" and not obj.hide_get() and not obj.hide_viewport and not obj.hide_render
    ]
    for obj in visible:
        obj.select_set(True)
    for number in range(1, 6):
        name = f"LEVEL-L{number:02}-探头"
        if not any(obj.name == name for obj in visible):
            raise RuntimeError(f"visible station node missing: {name}")
    print("V13_EXPORT_INPUT", json.dumps({"visible_meshes": len(visible), "blender": bpy.app.version_string}), flush=True)
    bpy.ops.export_scene.gltf(
        filepath=output,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_animations=False,
    )
    print("V13_EXPORT_DONE", output, flush=True)


if __name__ == "__main__":
    main()
