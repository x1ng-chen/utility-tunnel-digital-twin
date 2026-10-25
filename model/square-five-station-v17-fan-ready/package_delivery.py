"""Package only this candidate; baseline and runtime files are read-only."""
import csv,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'square-five-station-v16-concept'
for name in ['asset-map.json','sensor-bindings.json','station-focus.json']:
    data=json.loads((BASE/name).read_text(encoding='utf-8'))
    data['revision']=ROOT.name
    data['provenance']={'sourceRevision':BASE.name,'change':'Two independent fan rotors only; existing static geometry and all sensor targets verified unchanged.'}
    if name=='asset-map.json':
        for asset in data['assets']:
            if asset['assetCode'] in ['FAN-01','FAN-02']:
                asset['rotorNode']=asset['assetCode']+'_ROTOR'
    (ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assets=json.loads((ROOT/'asset-map.json').read_text(encoding='utf-8'))['assets']
with (ROOT/'asset-map.csv').open('w',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for a in assets for k in a))
    writer=csv.DictWriter(f,fields); writer.writeheader()
    for a in assets:
        writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in a.items()})
(ROOT/'layout-and-hardware-notes-v16.md').write_text(
    '> 以下为 V16 的历史布局与概念限制说明；V17 的新增验证和交付状态以本目录 README 为准。\n\n'+(BASE/'README.md').read_text(encoding='utf-8'),encoding='utf-8')
for report_name in ['native-verification.json','glb-animation-verification.json']:
    assert json.loads((ROOT/report_name).read_text(encoding='utf-8'))['status']=='PASS'
model=json.loads((ROOT/'model-readiness-report.json').read_text(encoding='utf-8'))
assert model['glbExport']=='PASS'
for name,digest in model['protectedFilesBefore'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
files=sorted(p for p in ROOT.rglob('*') if p.is_file() and p.suffix!='.zip' and p.name!='delivery-manifest.json' and '__pycache__' not in p.parts)
manifest={'revision':ROOT.name,'status':'MODEL_READY_REAL_DEVICE_INTEGRATION_PENDING','artifacts':[
    {'path':p.relative_to(ROOT).as_posix(),'sizeBytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(ROOT/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
archive=ROOT/'v17-fan-ready-delivery.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files+[ROOT/'delivery-manifest.json']:
        z.write(p,ROOT.name+'/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
    for item in manifest['artifacts']:
        assert hashlib.sha256(z.read(ROOT.name+'/'+item['path'])).hexdigest()==item['sha256']
print(json.dumps({'archive':str(archive),'artifactsVerified':len(files),'sizeBytes':archive.stat().st_size}))
