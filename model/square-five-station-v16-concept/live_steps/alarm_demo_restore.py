import bpy,json
scene=bpy.context.scene
key='MCP_SIMULATED_ALARM_STATE'
state=json.loads(scene[key])
for name,materials in state['materials'].items():
    obj=bpy.data.objects[name]; obj.data.materials.clear()
    for material in materials: obj.data.materials.append(bpy.data.materials[material])
for name,hidden in state['hidden'].items(): bpy.data.objects[name].hide_set(hidden)
scene.camera=bpy.data.objects[state['camera']]
for obj in list(bpy.data.objects):
    if obj.name.startswith('DEMO_ONLY_'): bpy.data.objects.remove(obj,do_unlink=True)
for material in list(bpy.data.materials):
    if material.name.startswith('DEMO_ONLY_') and not material.users: bpy.data.materials.remove(material)
del scene[key]
assert not any(o.name.startswith('DEMO_ONLY_') for o in scene.objects)
print(json.dumps({'simulationRestored':True,'camera':scene.camera.name,'noBakedAlarmMaterials':True}))
