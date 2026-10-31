"""MCP synthetic visual demonstration; does not connect to or command any device."""
import bpy,math,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'previews/motion-frames';OUT.mkdir(exist_ok=True)
s=bpy.context.scene
original=(s.camera,s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage,s.cycles.samples,s.render.filepath)
rotors=[bpy.data.objects[f'FAN-{n:02}_ROTOR'] for n in [1,2]]
rotations=[r.rotation_euler.copy() for r in rotors]
materials=[m for m in bpy.data.materials if m.get('fanPowerOnly')]
file=ROOT/(ROOT.name+'.blend');before=hashlib.sha256(file.read_bytes()).hexdigest()
manifest=[]
try:
    s.camera=bpy.data.objects['VIEW_FAN_INSET_DETAIL'];s.render.resolution_x=640;s.render.resolution_y=580;s.render.resolution_percentage=100;s.cycles.samples=20
    angle=0
    for i in range(30):
        powered=i<18
        running=i<12 or 18<=i<24
        if running:angle+=2*math.pi/7/12
        for r in rotors:r.rotation_euler.z=angle
        for m in materials:
            node=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');node.inputs['Emission Strength'].default_value=3 if powered else 0
        filename=OUT/f'{i:03}.png';s.render.filepath=str(filename);bpy.ops.render.render(write_still=True)
        manifest.append({'frame':i,'file':str(filename),'powered':powered,'rotorTurning':running,'evidence':'SYNTHETIC_PREVIEW_NOT_REAL_DEVICE'})
finally:
    for r,rotation in zip(rotors,rotations):r.rotation_euler=rotation
    for m in materials:
        node=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');node.inputs['Emission Strength'].default_value=0
    s.camera,s.render.resolution_x,s.render.resolution_y,s.render.resolution_percentage,s.cycles.samples,s.render.filepath=original
assert hashlib.sha256(file.read_bytes()).hexdigest()==before
(ROOT/'previews/motion-example-manifest.json').write_text(json.dumps({'scope':'SYNTHETIC_POWER_AND_ROTATION_VISUAL_EXAMPLE','nativeFileUnchanged':True,'frames':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','frames':len(manifest),'nativeFileUnchanged':True,'hardwareCommands':0}))
