import bpy,json
scene=bpy.context.scene
scene.camera=bpy.data.objects['VIEW_TOP']
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        space=area.spaces.active
        space.region_3d.view_perspective='CAMERA'
        space.shading.type='MATERIAL'
        space.overlay.show_overlays=False
bpy.data.collections['99_STUDIO'].hide_viewport=True
print(json.dumps({'camera':scene.camera.name,'objects':len(bpy.data.objects),'liveEditViaMCP':True}))
