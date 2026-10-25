"""Executed inside live Blender by MCP, with VIEW supplied by the small entry file."""
import bpy,json
from pathlib import Path
ROOT=Path('D:/shixi/utility-tunnel-digital-twin/model/square-five-station-v16-concept')
scene=bpy.context.scene
assert VIEW in {'overall','top','front','side','cutaway'}
lid=bpy.data.objects['REMOVABLE_TRANSPARENT_LID']
front=bpy.data.objects['CLEAR_WALL_BOTTOM']
parts=[lid,*lid.children_recursive]
old=(scene.camera,{o.name:o.hide_render for o in parts},front.hide_render)
try:
    scene.camera=bpy.data.objects['VIEW_OVERALL' if VIEW=='cutaway' else 'VIEW_'+VIEW.upper()]
    for obj in parts: obj.hide_render=VIEW=='cutaway'
    front.hide_render=VIEW=='cutaway'
    scene.render.resolution_x=1600; scene.render.resolution_y=1300; scene.render.resolution_percentage=100
    scene.cycles.samples=32; scene.cycles.use_denoising=True
    scene.render.filepath=str(ROOT/'previews'/(VIEW+'.png'))
    bpy.ops.render.render(write_still=True)
    print(json.dumps({'rendered':VIEW,'file':scene.render.filepath,'route':'LIVE_MCP','lidRemovedForCutaway':VIEW=='cutaway'}))
finally:
    scene.camera=old[0]
    for name,value in old[1].items(): bpy.data.objects[name].hide_render=value
    front.hide_render=old[2]
