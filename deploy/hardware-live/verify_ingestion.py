"""Read actual HTTP observations twice; never seed data, call a model or publish MQTT."""
import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument('--seconds', type=int, default=12)
parser.add_argument('--expect-offline', choices=['CTRL-01','CTRL-02','CTRL-03','CTRL-04'])
parser.add_argument('--expect-presentation', help='Require a specific presentation revision and verify the actual served GLB.')
options = parser.parse_args()
if not 2 <= options.seconds <= 60: raise SystemExit('Choose a window from 2 to 60 seconds.')
root = Path(__file__).resolve().parents[2]
runtime = root / '.hardware-live'
access = json.loads((runtime / 'access.json').read_text(encoding='utf-8'))
base = 'http://127.0.0.1:8000/api'

def request(path, body=None, token=None):
    req = Request(base+path, data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', **({'Authorization':f'Bearer {token}'} if token else {})})
    with urlopen(req, timeout=15) as response: return json.load(response)

assert request('/ready/')['profile'] == 'hardware-live'
token = request('/auth/login/', {'email':access['account'], 'password':access['password']})['accessToken']
context = request('/assistant/context/', token=token)
assert context['dataContext']['hardwareLive'] and context['dataContext']['controlDisabled']
assert context['dataContext']['modelCallsDisabled']
capabilities = request('/controllers/command-capabilities/', token=token)
assert capabilities['protocol'] == 'four-controller-v2' and capabilities['controlDisabled']
model_check = None
if options.expect_presentation:
    readiness = request('/twin/model-readiness/', token=token)
    presentation = readiness['presentation']
    assert readiness['status'] == 'ready' and presentation['revision'] == options.expect_presentation
    release = readiness['activeRelease']
    model_request = Request(base+f'/twin/model-file/?release={release["id"]}', headers={'Authorization':f'Bearer {token}'})
    with urlopen(model_request, timeout=20) as response: data = response.read()
    assert data[:4] == b'glTF'
    assert hashlib.sha256(data).hexdigest() == release['sha256'] == presentation['modelSha256']
    assets = {a['code']:a for a in request('/assets/?pageSize=100', token=token)['items']}
    assert all(assets[code]['mesh'] == mesh for code,mesh in presentation['controllerMeshes'].items())
    assert all(assets[code]['zone'] == station for code,station in presentation['sensorStations'].items())
    model_check = {'revision':presentation['revision'], 'version':release['version'],
        'servedGlbSha256':release['sha256'], 'controllerMeshesVerified':4, 'sensorZonesVerified':31}
first = request('/assistant/inspection/', token=token)
time.sleep(options.seconds)
second = request('/assistant/inspection/', token=token)
before = first['evidence'][0]['data']; after = second['evidence'][0]['data']
counts = Counter(i['controllerId'] for i in after['items'])
assert counts == {'CTRL-01':11, 'CTRL-02':7, 'CTRL-03':6, 'CTRL-04':7}, counts
assert after['registered_sensor_count'] == 31
assert all(i['mapping_status'] == 'active_model_node_verified' for i in after['items'])
progress = {}
for code in counts:
    old = before['controllers'][code]; new = after['controllers'][code]
    old_ids = {r['id'] for r in old['readings']}; new_ids = {r['id'] for r in new['readings']}
    if code == options.expect_offline:
        assert old_ids == new_ids and new['connection']['state'] == 'offline', code
        assert all(r['freshness'] == 'stale' and not r['usable'] for r in new['readings']), code
    else:
        assert old_ids != new_ids and new['connection']['state'] == 'online', code
    assert all(r['source_metadata']['controllerId'] == code and r['source_metadata']['source'] == 'four-controller-rtu-v2' for r in new['readings']), code
    progress[code] = {'beforeIds':sorted(old_ids), 'afterIds':sorted(new_ids), 'state':new['connection']['state']}
assert all(r['source_metadata']['controllerId'] == item['controllerId']
    for item in after['items'] for r in item['snapshot']['readings'])
if options.expect_presentation:
    assert after['presentation_revision'] == options.expect_presentation
    assert all(i['stationId'] == presentation['sensorStations'][i['assetCode']] for i in after['items'])
summary = {'verifiedAt':datetime.now(timezone.utc).isoformat(), 'windowSeconds':options.seconds,
    'mode':'real_hardware_http_observations', 'registeredSensors':31, 'ownership':dict(counts),
    'expectedTransportOffline':options.expect_offline,
    'mappedSensors':31, 'usableObservationSensors':after['usable_observation_sensor_count'],
    'modelPresentation':model_check,
    'issues':{i['assetCode']:i['data_issues'] for i in after['items'] if i['data_issues']},
    'controllers':progress, 'modelCalls':0, 'hardwareCommands':0,
    'boundary':'Verifies ingestion and read-only evidence APIs, not sensor calibration, browser rendering or physical disconnect recovery.'}
folder = runtime / ('verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
folder.mkdir()
for name, value in [('before.json',first),('after.json',second),('summary.json',summary)]:
    (folder/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report':str(folder/'summary.json'), **summary}, ensure_ascii=True))
