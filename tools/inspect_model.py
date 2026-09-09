"""Read-only published GLB inspection in an isolated Blender process."""
import bpy
import json
import sys
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=sys.argv[sys.argv.index('--') + 1])
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        points = [obj.matrix_world @ Vector(p) for p in obj.bound_box]
        print('BOUNDS', json.dumps({'name': obj.name, 'min': [min(p[i] for p in points) for i in range(3)], 'max': [max(p[i] for p in points) for i in range(3)]}))
