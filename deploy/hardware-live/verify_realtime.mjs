/** Actual network feed check; no browser automation, MQTT publish or model call. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const require = createRequire(new URL('../../services/iotda-gateway/package.json', import.meta.url));
const WebSocket = require('ws');
const runtime = new URL('../../.hardware-live/', import.meta.url);
const access = JSON.parse(readFileSync(new URL('access.json', runtime), 'utf8'));
const ready = await fetch('http://127.0.0.1:8000/api/ready/').then(r => r.json());
assert.equal(ready.profile, 'hardware-live');
const login = await fetch('http://127.0.0.1:8000/api/auth/login/', {
  method: 'POST', headers: {'content-type':'application/json'},
  body: JSON.stringify({email:access.account, password:access.password}),
}).then(r => r.json());
assert.ok(login.accessToken);
const seen = new Map();
let authenticated = false;
let lastSequence = -1;
let frames = 0;
await new Promise((resolve, reject) => {
  const ws = new WebSocket('ws://127.0.0.1:8000/ws/events/', {origin:'http://127.0.0.1:5173'});
  const timer = setTimeout(() => { ws.close(); resolve(); }, 12000);
  ws.on('open', () => ws.send(JSON.stringify({type:'auth', token:login.accessToken})));
  ws.on('error', error => { clearTimeout(timer); reject(error); });
  ws.on('message', bytes => {
    try {
      const event = JSON.parse(bytes.toString());
      if (event.type === 'ready') authenticated = true;
      if (!authenticated || event.type !== 'telemetry') return;
      assert.ok(event.seq > lastSequence, 'Live sequence must advance.');
      lastSequence = event.seq;
      const p = event.payload.provenance;
      assert.equal(p.source, 'four-controller-rtu-v2');
      assert.equal(p.layoutVersion, 'four-controller-20261026.1');
      const metrics = seen.get(p.controllerId) ?? new Set();
      metrics.add(`${event.payload.assetCode}/${event.payload.metricKey}`);
      seen.set(p.controllerId, metrics); frames++;
    } catch (error) { clearTimeout(timer); ws.close(); reject(error); }
  });
});
assert.ok(authenticated, 'WebSocket did not authenticate.');
assert.deepEqual([...seen.keys()].sort(), ['CTRL-01','CTRL-02','CTRL-03','CTRL-04']);
const metrics = Object.fromEntries([...seen].map(([key,value]) => [key,value.size]));
assert.deepEqual(metrics, {'CTRL-01':14, 'CTRL-02':16, 'CTRL-03':8, 'CTRL-04':16});
const result = {verifiedAt:new Date().toISOString(), windowSeconds:12, authenticated,
  telemetryEvents:frames, metricsByController:metrics, modelCalls:0, hardwareCommands:0,
  boundary:'Real authenticated WebSocket feed; does not certify browser rendering or physical sensor accuracy.'};
const output = new URL('realtime-verification.json', runtime);
writeFileSync(output, JSON.stringify(result, null, 2));
console.log(JSON.stringify({report:fileURLToPath(output), ...result}));
