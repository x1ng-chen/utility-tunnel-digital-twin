import bpy,json
for n in [1,2]: bpy.data.objects[f'CTRL-{n:02}_LABEL'].location.y=.655
bpy.context.view_layer.update()
print(json.dumps({'upperControllerLabels':'Clear of both TFT and temperature/humidity module projections','newLabelY_mm':655}))
