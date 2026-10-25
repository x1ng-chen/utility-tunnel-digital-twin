"""Read-only verification in a separate background Blender, never in the live scene."""
import bpy,json
from pathlib import Path
from mathutils import Matrix
ROOT=Path(__file__).resolve().parent
assert Path(bpy.data.filepath).resolve()==(ROOT/(ROOT.name+'.blend')).resolve()
contract=json.loads((ROOT/'fan-animation-contract.json').read_text(encoding='utf-8'))
sensor_map=json.loads((ROOT.parent/'square-five-station-v16-concept/sensor-bindings.json').read_text(encoding='utf-8'))
assert len(sensor_map['bindings'])==31
for binding in sensor_map['bindings']:
    obj=bpy.data.objects[binding['targetNode']]
    assert obj['assetCode']==binding['assetCode']
    assert max(abs(obj.matrix_world.translation[i]-binding['positionBlender_m'][i]) for i in range(3))<1e-6
assets=[o for o in bpy.context.scene.objects if o.get('assetCode')]
assert len(assets)==69
checks={}
for fan in contract['fans']:
    rotor=bpy.data.objects[fan['rotorNode']]
    assert rotor.type=='EMPTY' and rotor.parent.name==fan['housingNode']
    assert not rotor.animation_data
    assert sorted(o.name for o in rotor.children)==sorted(fan['movingNodes'])
    before={n:bpy.data.objects[n].matrix_world.copy() for n in fan['fixedNodes']}
    rest=rotor.matrix_world.copy()
    rotor.matrix_world=rest@Matrix.Rotation(.47,4,'Y')
    bpy.context.view_layer.update()
    for name,matrix in before.items():
        actual=bpy.data.objects[name].matrix_world
        assert max(abs(actual[r][c]-matrix[r][c]) for r in range(4) for c in range(4))<1e-7
    rotor.matrix_world=rest
    bpy.context.view_layer.update()
    checks[fan['assetCode']]='PASS'
report={'status':'PASS','method':'FRESH_BACKGROUND_BLENDER_NATIVE_FILE_READ','blenderVersion':bpy.app.version_string,
    'semanticAssets':len(assets),'sensors':31,'independentRotorChecks':checks,'fileSavedByValidator':False}
(ROOT/'native-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
