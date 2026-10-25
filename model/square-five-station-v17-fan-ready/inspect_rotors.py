import bpy,json
print(json.dumps({n:{'position':list(bpy.data.objects[n].matrix_world.translation),'matrix':[list(r) for r in bpy.data.objects[n].matrix_world],'local':[list(r) for r in bpy.data.objects[n].matrix_basis]} for n in ['FAN-01','FAN-01_ROTOR','FAN_1_HUB','FAN_1_BLADE_0','FAN-02_ROTOR','FAN_2_HUB']},indent=2))
