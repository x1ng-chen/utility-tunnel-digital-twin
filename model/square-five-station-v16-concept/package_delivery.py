"""Assemble only reviewed model artifacts; hash-check each archived file."""
import hashlib
import json
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REV='square-five-station-v16-concept'
v=json.loads((ROOT/'validation-report.json').read_text(encoding='utf-8'))
assert v['blend']['status']==v['glb']['status']=='PASS' and v['protected_inputs_unchanged']
sim=json.loads((ROOT/'simulated-alarm-view-report.json').read_text(encoding='utf-8'))
assert len(sim['stations'])==5 and any('"simulationRestored": true' in x for x in sim['restoreOutput'])
names=['README.md',REV+'.blend',REV+'.glb','build_model.py','validate_model.py','package_delivery.py',
    'asset-map.json','asset-map.csv','sensor-bindings.json','station-focus.json','identity-migration-v15-v16.csv',
    'identity-baseline-v15.json','published-layout-baseline.md','alarm-location-fixtures.json',
    'export-report.json','validation-report.json','voice-opening-check.json','simulated-alarm-view-report.json','protected-input-hashes.json']
names += ['previews/'+name+'.png' for name in ['overall','top','front','side','cutaway']]
names += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'previews/simulated-alarm').glob('SIMULATED-P*.png'))]
names += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'live_steps').iterdir()) if p.suffix in {'.py','.json'}]
names += [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'mcp-evidence').glob('*.json'))]
assert len(names)==len(set(names))
entries=[]
for name in names:
    data=(ROOT/name).read_bytes()
    entries.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
manifest={'revision':REV,'date':'2026-10-24','status':'CONCEPT_FOR_REVIEW_NOT_FABRICATION_APPROVED',
    'baselineCommit':'12c1feebe811329c6370f8927dcb14bc733b40f7','modelEditRoute':'LIVE_MCP',
    'sensor_count':31,'station_count':5,'controller_ownership':[7,6,11,7],
    'modelChecks':'PASS','fiveSimulatedBlenderViews':'PASS','platformAlarmIntegration':'NOT_EXECUTED','files':entries}
(ROOT/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
target=ROOT/'v16-square-five-station-delivery.zip'
with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in [*names,'delivery-manifest.json']: z.write(ROOT/name,name)
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None
    for item in entries: assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
print(json.dumps({'archive':str(target),'bytes':target.stat().st_size,'verified_artifacts':len(entries),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)
