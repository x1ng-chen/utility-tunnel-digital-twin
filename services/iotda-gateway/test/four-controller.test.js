import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, rmSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { setTimeout as pause } from 'node:timers/promises';
import { parseTelemetry } from '../src/schemas.js';
import { toDjangoBatch, createDjangoForwarder } from '../src/django.js';
import { Outbox } from '../src/outbox.js';
import { addCalculatedOxygenConcentration } from '../src/telemetry.js';
import { createTelemetryRoutes } from '../src/telemetry-routes.js';

const at = new Date('2026-10-27T00:00:00.000Z');
const clone = (value) => JSON.parse(JSON.stringify(value));
const reading = (assetCode, metric, value, unit, age = 110) =>
  ({ assetCode, metric, value, unit, quality: 'good', sampleAgeMs: age });
function frame(board) {
  const controllerId = 'CTRL-0' + board;
  const readings = [];
  const stations = { 1: 4, 2: 3, 3: 1, 4: 2, 5: 1 };
  for (const [station, owner] of Object.entries(stations)) {
    if (owner !== board) continue;
    const suffix = station.padStart(2, '0');
    readings.push(reading(station === '1' ? 'SMOKE-01' : 'MQ2-' + suffix, 'smoke.alarm', 0, 'bool'));
    readings.push(reading(station === '1' ? 'GAS-CH4-01' : 'MQ4-' + suffix, 'methane.raw', 321, 'adc'));
    readings.push(reading(station === '1' ? 'GAS-CO-01' : 'CO-' + suffix, 'co.raw', 234, 'adc'));
    readings.push(reading('FLAME-' + suffix, 'flame.alarm', 0, 'bool'));
  }
  const zone = { 1: '03', 2: '04', 3: '02', 4: '01' }[board];
  readings.push(reading('ENV-' + zone, 'temperature', -4.25, 'degC', 2110));
  readings.push(reading('ENV-' + zone, 'humidity', 52.31, '%RH', 2110));
  readings.push(reading('LEVEL-L' + zone, 'level.detected', 0, 'bool'));
  const oxygen = { 4: '01', 1: '02', 2: '03' }[board];
  if (oxygen) {
    readings.push(reading('GAS-O2-' + oxygen, 'oxygen.raw', 14, 'adc'));
    readings.push(reading('GAS-O2-' + oxygen, 'oxygen.voltage', 11, 'mV'));
  }
  if (board === 2 || board === 4) {
    const fan = board === 4 ? 'FAN-01' : 'FAN-02';
    readings.push(reading(fan, 'rotational.speed', 1200, 'rpm'));
    readings.push(reading(fan, 'supply.voltage', 12.1, 'V'));
    readings.push(reading(fan, 'motor.current', -0.25, 'mA'));
    readings.push(reading(fan, 'power', 0.02, 'W'));
    readings.push(reading(fan, 'pwm.duty', 60, '%'));
    readings.push(reading(fan, 'relay.commanded', 1, 'bool'));
  }
  readings.push(reading(controllerId, 'heartbeat', 1, 'bool'));
  return { schema: 'ut.telemetry.v1', seq: 17, frameId: 'boot-test:' + board + ':0:2:17',
    source: 'four-controller-rtu-v2', controllerId, layoutVersion: 'four-controller-20261026.1',
    rawOnly: true, clockSource: 'gateway-ntp', ts: at.toISOString(), readings };
}
test('the four explicit MQTT topics deliver 31 unique physical sensors and 54 metrics', () => {
  const catalog = JSON.parse(readFileSync(new URL('../src/four-controller-catalog.json', import.meta.url), 'utf8'));
  const inventory = JSON.parse(readFileSync(new URL('../../../backend/operations/agent_catalog/station-inventory.json', import.meta.url), 'utf8'));
  assert.deepEqual(catalog.bindings, inventory.bindings.map(({ assetCode, controllerId, physicalTag }) => ({ assetCode, controllerId, physicalTag })));
  const routes = createTelemetryRoutes('CTRL-01,CTRL-02,CTRL-03,CTRL-04');
  const sensors = new Set(); let metrics = 0;
  for (const board of [1, 2, 3, 4]) {
    const raw = frame(board);
    const parsed = parseTelemetry(JSON.stringify(raw), routes.deviceForTopic('ut/v1/CTRL-0' + board + '/telemetry'));
    assert.equal(parsed.readings.length, [14, 16, 8, 16][board - 1]);
    const physical = new Set(parsed.readings.filter((r) => !r.assetCode.startsWith('FAN-') && !r.assetCode.startsWith('CTRL-')).map((r) => r.assetCode));
    assert.equal(physical.size, [11, 7, 6, 7][board - 1]);
    for (const code of physical) { assert.ok(!sensors.has(code)); sensors.add(code); }
    metrics += parsed.readings.length;
  }
  assert.equal(sensors.size, 31); assert.equal(metrics, 54);
});
test('reject controller topic mismatch, omissions, duplicate evidence and cross-zone assets', () => {
  assert.throws(() => parseTelemetry(frame(4), 'CTRL-02'));
  for (const change of [
    (f) => { f.readings.pop(); },
    (f) => { f.readings.push(clone(f.readings[0])); },
    (f) => { f.readings[0].assetCode = 'MQ2-04'; },
    (f) => { f.layoutVersion = 'old-layout'; },
    (f) => { delete f.frameId; },
    (f) => { delete f.readings[0].sampleAgeMs; },
    (f) => { f.rawOnly = false; },
  ]) {
    const f = frame(4); change(f);
    assert.throws(() => parseTelemetry(f, 'CTRL-04'));
  }
});
test('reject fabricated oxygen concentration, malformed units, impossible digital and ADC values', () => {
  for (const [metric, value, unit] of [
    ['smoke.alarm', 2, 'bool'], ['smoke.alarm', 0.5, 'bool'], ['smoke.alarm', 0, 'V'],
    ['oxygen.concentration', 20.9, '%Vol'], ['methane.raw', 4096, 'adc'],
  ]) {
    const f = frame(4);
    let r = f.readings.find((r) => r.metric === metric);
    if (!r) r = f.readings.find((r) => r.metric === 'oxygen.raw');
    Object.assign(r, { metric, value, unit });
    assert.throws(() => parseTelemetry(f, 'CTRL-04'));
  }
});
test('signed temperatures, measured negative current and per-reading source ages survive mapping', () => {
  const parsed = parseTelemetry(frame(4), 'CTRL-04');
  const batch = toDjangoBatch(parsed, { deviceId: 'CTRL-04', receivedAt: new Date(at.getTime() + 30000) });
  assert.equal(batch.skipped.length, 0);
  const t = batch.readings.find((r) => r.metricKey === 'temperature');
  assert.equal(t.value, -4.25); assert.equal(t.unit, '°C');
  assert.equal(t.recordedAt, '2026-10-26T23:59:57.890Z');
  const current = batch.readings.find((r) => r.metricKey === 'motor.current');
  assert.equal(current.value, -0.25);
  assert.ok(batch.readings.every((r) => r.eventId.startsWith('gw:CTRL-04:')));
});
test('raw oxygen remains suspect and does not turn into an estimated concentration', () => {
  const parsed = parseTelemetry(frame(4), 'CTRL-04');
  const oxygen = parsed.readings.filter((r) => r.metric.startsWith('oxygen.'));
  assert.equal(oxygen.length, 2);
  assert.ok(oxygen.every((r) => r.quality === 'suspect'));
  const result = addCalculatedOxygenConcentration(parsed);
  assert.equal(result.readings.length, 16);
  assert.ok(!result.readings.some((r) => r.metric === 'oxygen.concentration'));
  const legacyAlias = { schema: 'ut.telemetry.v1', rawOnly: true, readings: [
    { assetCode: 'GAS-01', metric: 'oxygen.voltage', value: 11, unit: 'mV', quality: 'good' },
  ] };
  assert.equal(addCalculatedOxygenConcentration(legacyAlias).readings.length, 1);
});
test('stale observations and receiver-estimated time cannot be marked good', () => {
  const f = frame(4); f.readings[0].sampleAgeMs = 5001;
  assert.equal(parseTelemetry(f, 'CTRL-04').readings[0].quality, 'bad');
  f.readings[0].quality = 'missing';
  assert.equal(parseTelemetry(f, 'CTRL-04').readings[0].quality, 'missing');
  const unclocked = frame(4); unclocked.clockSource = 'receiver-estimated'; delete unclocked.ts;
  assert.ok(parseTelemetry(unclocked, 'CTRL-04').readings.every((r) => r.quality === 'suspect'));
  unclocked.ts = at.toISOString();
  assert.throws(() => parseTelemetry(unclocked, 'CTRL-04'));
});
test('frame identity is independent of redelivery time and detects changed content through backend idempotency', () => {
  const f = parseTelemetry(frame(4), 'CTRL-04');
  const first = toDjangoBatch(f, { deviceId: 'CTRL-04', receivedAt: at });
  const redelivery = toDjangoBatch(f, { deviceId: 'CTRL-04', receivedAt: new Date(at.getTime() + 10000) });
  assert.deepEqual(first, redelivery);
  f.readings[0].value = 1;
  const mutated = toDjangoBatch(f, { deviceId: 'CTRL-04', receivedAt: at });
  assert.equal(first.readings[0].eventId, mutated.readings[0].eventId);
  assert.notDeepEqual(first.readings[0], mutated.readings[0]);
  const reboot = clone(f); reboot.frameId = 'different-boot:4:0:2:17';
  assert.notEqual(first.readings[0].eventId, toDjangoBatch(reboot, { deviceId: 'CTRL-04', receivedAt: at }).readings[0].eventId);
});
test('first receipt time for an unsynchronized frame persists across SQLite restarts and device namespaces', () => {
  const folder = mkdtempSync(join(tmpdir(), 'four-frame-clock-'));
  const path = join(folder, 'clock.sqlite');
  try {
    const first = new Outbox(path, 1);
    assert.equal(first.frameReceivedAt('CTRL-04:boot-one', at).toISOString(), at.toISOString());
    first.close();
    const second = new Outbox(path, 1);
    assert.equal(second.frameReceivedAt('CTRL-04:boot-one', new Date(at.getTime() + 30000)).toISOString(), at.toISOString());
    assert.equal(second.frameReceivedAt('CTRL-02:boot-one', new Date(at.getTime() + 30000)).toISOString(), new Date(at.getTime() + 30000).toISOString());
    for (let i = 0; i < 1030; i++) second.frameReceivedAt('other:' + i, at);
    assert.equal(Number(second.db.prepare('SELECT COUNT(*) AS n FROM frame_clock').get().n), 1024);
    second.close();
  } finally { rmSync(folder, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});
test('the real persistent forwarder gives an unclocked duplicate exactly the same backend batch', async () => {
  const f = frame(4); delete f.ts; f.clockSource = 'receiver-estimated';
  const parsed = parseTelemetry(f, 'CTRL-04'); const sent = [];
  const gateway = createDjangoForwarder({ baseUrl: 'https://fixture.invalid', apiKey: 'fixture-only',
    fetchImpl: async (_url, request) => {
      sent.push(JSON.parse(request.body));
      return new Response(JSON.stringify({ created: 0, duplicates: 16, rules: {} }), { status: 200 });
    }, log: { info() {}, warn() {}, error() {} },
  });
  try {
    gateway.forward(parsed, at, 'CTRL-04');
    gateway.forward(parsed, new Date(at.getTime() + 20000), 'CTRL-04');
    for (let i = 0; i < 100 && sent.length < 2; i++) await pause(10);
    assert.equal(sent.length, 2); assert.deepEqual(sent[0], sent[1]);
  } finally { gateway.close(); }
});
test('legacy frames continue to parse without four-controller metadata or fabricated coverage', () => {
  const old = { schema: 'ut.telemetry.v1', readings: [
    { assetCode: 'ENV-01', metric: 'temperature', value: 20, unit: 'degC' },
  ] };
  assert.equal(parseTelemetry(old, 'CTRL-01').readings[0].quality, 'good');
});



test('an observed short digital event stays alarm-capable without masquerading as a current input', () => {
  const f = frame(1);
  const r = f.readings.find((r) => r.assetCode === 'MQ2-05');
  r.value = 1; r.eventLatched = true; r.sampleAgeMs = 2300;
  const parsed = parseTelemetry(f, 'CTRL-01');
  const evidence = parsed.readings.find((r) => r.assetCode === 'MQ2-05');
  assert.equal(evidence.quality, 'good');
  const row = toDjangoBatch(parsed, { deviceId: 'CTRL-01', receivedAt: at }).readings.find((r) => r.assetCode === 'MQ2-05');
  assert.equal(row.observationKind, 'latched_event');
  assert.equal(row.recordedAt, '2026-10-26T23:59:57.700Z');
  r.sampleAgeMs = 6000;
  assert.equal(parseTelemetry(f, 'CTRL-01').readings.find((r) => r.assetCode === 'MQ2-05').quality, 'bad');
  r.sampleAgeMs = 1000; r.value = 0;
  assert.throws(() => parseTelemetry(f, 'CTRL-01'));
  r.value = 1; delete r.eventLatched;
  f.readings.find((r) => r.metric === 'heartbeat').eventLatched = true;
  assert.throws(() => parseTelemetry(f, 'CTRL-01'));
});
