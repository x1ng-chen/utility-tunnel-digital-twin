/** Passive real MQ-2 MQTT + committed WebSocket acceptance, with live mappings. */
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync, appendFileSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const require = createRequire(new URL('../../services/iotda-gateway/package.json', import.meta.url));
const mqtt = require('mqtt'), WebSocket = require('ws');
const root = new URL('../../', import.meta.url), runtime = new URL('.hardware-live/', root);
const access = JSON.parse(readFileSync(new URL('access.json', runtime), 'utf8'));
const base = 'http://127.0.0.1:8000/api';
async function api(path, token, body) {
  const response = await fetch(base + path, {method: body ? 'POST' : 'GET',
    headers: {'content-type': 'application/json', ...(token ? {authorization: `Bearer ${token}`} : {})},
    ...(body ? {body: JSON.stringify(body)} : {})});
  assert.ok(response.ok, `${path}: HTTP ${response.status}`); return response.json();
}
assert.equal((await api('/ready/')).profile, 'hardware-live');
const {accessToken} = await api('/auth/login/', null, {email: access.account, password: access.password});
assert.ok(accessToken);
const readiness = await api('/twin/model-readiness/', accessToken);
assert.equal(readiness.status, 'ready');
const snapshot = (await api('/assistant/inspection/', accessToken)).evidence[0].data;
const smokeMap = Object.fromEntries(snapshot.items.filter(i => /^MQ2-/.test(i.physicalTag)).map(i =>
  [i.assetCode, {station: i.stationId, controller: i.controllerId, target: i.targetNode, modelTag: i.modelPhysicalTag}]));
assert.equal(Object.keys(smokeMap).length, 5);
const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
const folder = new URL(`smoke-acceptance-${stamp}/`, runtime); mkdirSync(folder, {recursive: true});
const states = Object.fromEntries(Object.keys(smokeMap).map(code => [code,
  {mqttActive: false, mqttReturnedZero: false, committedActive: false, alertOpen: false, alertResolved: false, alertIds: []}]));
const startedAt = new Date().toISOString(); let completed = false, frames = 0, authenticated = false;
const env = readFileSync(new URL('.env', runtime), 'utf8');
const broker = env.match(/^LOCAL_MQTT_URL=(.+)$/m)?.[1].trim(); assert.ok(broker);
const mq = mqtt.connect(broker, {connectTimeout: 5000, reconnectPeriod: 2000});
const ws = new WebSocket('ws://127.0.0.1:8000/ws/events/', {origin: 'http://127.0.0.1:5173'});
function log(kind, data) {appendFileSync(new URL('events.jsonl', folder), JSON.stringify({receivedAt: new Date().toISOString(), kind, ...data}) + '\n');}
function save(reason = 'observing') {
  const result = {startedAt, updatedAt: new Date().toISOString(), reason, frames, authenticated,
    presentationRevision: readiness.presentation?.revision, smokeMap, states, hardwareCommands: 0, modelCalls: 0,
    browserHighlight: 'requires_user_observation', boundary: 'Physical MQTT and committed events; not calibrated smoke concentration or browser verification.'};
  writeFileSync(new URL('summary.json', folder), JSON.stringify(result, null, 2));
}
function finish(reason) {if (completed) return; completed = true; clearInterval(progress); clearTimeout(deadline); save(reason); mq.end(true); ws.terminate(); console.log(`FINISHED ${reason}`);}
mq.on('connect', () => mq.subscribe('ut/v1/+/telemetry', {qos: 1}, error => {
  if (error) {log('mqtt_error', {message: error.message}); return;}
  console.log(JSON.stringify({status: 'READY', report: fileURLToPath(new URL('summary.json', folder)), smokeMap}));
}));
mq.on('message', (topic, bytes, packet) => {
  if (packet.retain) return;
  try {
    const frame = JSON.parse(bytes); frames++;
    for (const r of frame.readings ?? []) {
      if (!smokeMap[r.assetCode] || r.metric !== 'smoke.alarm') continue;
      log('mqtt', {topic, controllerId: frame.controllerId, frameId: frame.frameId, reading: r});
      const s = states[r.assetCode];
      if (r.quality !== 'good') continue;
      if (r.value === 1 && !s.mqttActive) {s.mqttActive = true; console.log(`INPUT ${r.assetCode} value=1`);}
      if (r.value === 0 && s.mqttActive && !s.mqttReturnedZero) {s.mqttReturnedZero = true; console.log(`INPUT ${r.assetCode} returned=0`);}
    }
  } catch (error) {log('decode_error', {message: error.message});}
});
ws.on('open', () => ws.send(JSON.stringify({type: 'auth', token: accessToken})));
ws.on('message', bytes => {
  try {
    const event = JSON.parse(bytes), p = event.payload ?? {};
    if (event.type === 'ready') {authenticated = true; save(); return;}
    const code = p.assetCode ?? p.code, s = states[code]; if (!s || !authenticated) return;
    if (event.type === 'telemetry' && p.metricKey !== 'smoke.alarm') return;
    if (event.type === 'alert' && p.ruleKey !== 'smoke.alarm') return;
    log('committed_websocket', {event});
    if (event.type === 'telemetry' && p.value === 1 && p.quality === 'good') s.committedActive = true;
    if (event.type === 'alert') {
      if (p.status === 'open') {s.alertOpen = true; if (!s.alertIds.includes(p.id)) s.alertIds.push(p.id);}
      if (p.status === 'resolved' && s.alertIds.includes(p.id)) s.alertResolved = true;
      console.log(`ALERT ${code} ${p.status} id=${p.id}`); save();
    }
    if (Object.values(states).every(s => s.mqttActive && s.mqttReturnedZero && s.committedActive && s.alertOpen && s.alertResolved)) finish('all-five-trigger-recovery-observed');
  } catch (error) {log('websocket_error', {message: error.message});}
});
mq.on('error', error => log('mqtt_error', {message: error.message}));
ws.on('error', error => log('websocket_error', {message: error.message}));
const progress = setInterval(() => save(), 5000);
const deadline = setTimeout(() => finish('observation-window-ended'), 1800000);
process.on('SIGINT', () => finish('observer-stopped'));
save();
