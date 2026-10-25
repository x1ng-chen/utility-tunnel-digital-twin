// Read-only GLB loading and deterministic synthetic telemetry tests. No WebGL or hardware commands.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { Vector3, Quaternion } from '../../frontend/node_modules/three/build/three.module.js';
import { GLTFLoader } from '../../frontend/node_modules/three/examples/jsm/loaders/GLTFLoader.js';
import { createFanAnimator, resolveFanMotion } from './fan-motion.mjs';

const checks = [];
function check(name, fn) { fn(); checks.push({ name, status: 'PASS' }); }
const contract = JSON.parse(await readFile(new URL('./fan-animation-contract.json', import.meta.url)));
const raw = await readFile(new URL('./square-five-station-v17-fan-ready.glb', import.meta.url));
async function load(url) {
  const b = await readFile(url);
  return await new GLTFLoader().parseAsync(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength), '');
}
const [loaded, baseline] = await Promise.all([
  load(new URL('./square-five-station-v17-fan-ready.glb', import.meta.url)),
  load(new URL('../square-five-station-v16-concept/square-five-station-v16-concept.glb', import.meta.url)),
]);
const root = loaded.scene;
root.updateMatrixWorld(true); baseline.scene.updateMatrixWorld(true);
function find(root, name) {
  const list = [];
  root.traverse((o) => { if (o.name === name || o.userData?.name === name) list.push(o); });
  assert.equal(list.length, 1, `Unique node ${name}`);
  return list[0];
}
const delta = (a, b) => Math.max(...a.elements.map((n, i) => Math.abs(n - b.elements[i])));
check('Every prior node and mesh retains its rest geometry and world transform', () => {
  const json = baseline.parser.json;
  for (const node of json.nodes) {
    const a = find(baseline.scene, node.name), b = find(root, node.name);
    assert.ok(delta(a.matrixWorld, b.matrixWorld) < 1e-6, node.name);
    if (a.isMesh) {
      assert.ok(b.isMesh, node.name);
      const ap = a.geometry.attributes.position.array, bp = b.geometry.attributes.position.array;
      assert.equal(ap.length, bp.length, node.name);
      assert.ok(ap.every((v, i) => Math.abs(v - bp[i]) < 1e-7), node.name);
    }
  }
});
check('GLB adds exactly two rotors and no autoplay animation', () => {
  assert.equal(loaded.parser.json.nodes.length, baseline.parser.json.nodes.length + 2);
  assert.equal(loaded.animations.length, 0);
});
check('All five station groups survive', () => {
  for (let i = 1; i <= 5; i++) find(root, `STATION_P${i}`);
});
const bindings = JSON.parse(await readFile(new URL('../square-five-station-v16-concept/sensor-bindings.json', import.meta.url)));
check('31 sensor targets remain unique', () => {
  assert.equal(bindings.bindings.length, 31);
  bindings.bindings.forEach((b) => find(root, b.targetNode));
});
for (const fan of contract.fans) check(`${fan.assetCode}: pivot, local axis and six moving children`, () => {
  const rotor = find(root, fan.rotorNode);
  assert.ok(rotor.getWorldPosition(new Vector3()).distanceTo(new Vector3().fromArray(fan.pivotGltf_m)) < 1e-6);
  const axis = new Vector3().fromArray(fan.axisGltfLocal).applyQuaternion(rotor.getWorldQuaternion(new Quaternion()));
  assert.ok(axis.distanceTo(new Vector3().fromArray(fan.axisGltfWorld)) < 1e-6);
  assert.equal(rotor.children.length, 6);
  for (const name of fan.movingNodes) assert.equal(find(root, name).parent, rotor);
  for (const name of fan.fixedNodes) if (name !== fan.housingNode) assert.equal(find(root, name).parent, find(root, fan.housingNode));
});

const nowMs = Date.parse('2026-10-24T12:00:00Z');
const options = { nowMs, maxAgeMs: 3000, source: 'api' }; // Synthetic test cadence, not production configuration.
const row = (assetCode, value, overrides = {}) => ({ assetCode, metricKey: 'rotational.speed', value, quality: 'good', unit: 'rpm', recordedAt: new Date(nowMs - 100).toISOString(), ...overrides });
const cases = [
  ['measured RPM starts', [row('FAN-01', 720)], {}, 'running', 'fresh_measured_rpm'],
  ['measured zero stops', [row('FAN-01', 0)], {}, 'stopped', 'fresh_measured_rpm'],
  ['missing stays unknown', [], {}, 'unknown', 'missing'],
  ['stale expires without a new payload', [row('FAN-01', 720)], { nowMs: nowMs + 4000 }, 'unknown', 'stale'],
  ['future timestamp rejected', [row('FAN-01', 720, { recordedAt: new Date(nowMs + 1000).toISOString() })], {}, 'unknown', 'future_timestamp'],
  ['invalid timestamp rejected', [row('FAN-01', 720, { recordedAt: 'invalid' })], {}, 'unknown', 'invalid_timestamp'],
  ['bad quality freezes', [row('FAN-01', 720, { quality: 'bad' })], {}, 'unknown', 'quality'],
  ['suspect quality freezes', [row('FAN-01', 720, { quality: 'suspect' })], {}, 'unknown', 'quality'],
  ['negative RPM rejected', [row('FAN-01', -1)], {}, 'unknown', 'invalid_rpm'],
  ['nonfinite RPM rejected', [row('FAN-01', NaN)], {}, 'unknown', 'invalid_rpm'],
  ['numeric strings rejected', [row('FAN-01', '720')], {}, 'unknown', 'invalid_rpm'],
  ['wrong units rejected', [row('FAN-01', 12, { unit: 'rps' })], {}, 'unknown', 'unit'],
  ['offline is unknown', [row('FAN-01', 720)], { offline: true }, 'unknown', 'offline'],
  ['demo source cannot imply live motion', [row('FAN-01', 720)], { source: 'demo' }, 'unknown', 'non_live_source'],
  ['fan data cannot drive another asset', [row('FAN-02', 720)], {}, 'unknown', 'missing'],
  ['relay command cannot imply motion', [row('FAN-01', 1, { metricKey: 'relay.state' })], {}, 'unknown', 'missing'],
  ['newest zero defeats an old running value', [row('FAN-01', 720, { recordedAt: new Date(nowMs - 2000).toISOString() }), row('FAN-01', 0)], {}, 'stopped', 'fresh_measured_rpm'],
  ['conflicting same-time RPM is unknown', [row('FAN-01', 720), row('FAN-01', 0)], {}, 'unknown', 'conflicting_latest_readings'],
  ['newest bad reading cannot revive old good RPM', [row('FAN-01', 720, { recordedAt: new Date(nowMs - 2000).toISOString() }), row('FAN-01', 720, { quality: 'bad' })], {}, 'unknown', 'quality'],
];
for (const [name, rows, override, state, reason] of cases) check(name, () => {
  const result = resolveFanMotion(rows, 'FAN-01', { ...options, ...override });
  assert.equal(result.state, state); assert.equal(result.reason, reason);
});
check('Production freshness must be supplied explicitly', () => assert.throws(() => createFanAnimator(root, contract, {})));
const animator = createFanAnimator(root, contract, { maxAgeMs: 3000 });
const fixed = contract.fans.flatMap((f) => f.fixedNodes).map((name) => ({ object: find(root, name), matrix: find(root, name).matrixWorld.clone() }));
const rotor1 = find(root, 'FAN-01_ROTOR'), rotor2 = find(root, 'FAN-02_ROTOR');
const start1 = rotor1.quaternion.clone(), start2 = rotor2.quaternion.clone();
const blade = find(root, 'FAN_1_BLADE_0'), bladeStart = blade.getWorldPosition(new Vector3());
check('Actual GLB FAN-01 starts while FAN-02 stays stopped; housing remains fixed', () => {
  const snapshot = animator.update([row('FAN-01', 720), row('FAN-02', 0)], options, .1);
  root.updateMatrixWorld(true);
  assert.ok(rotor1.quaternion.angleTo(start1) > .1);
  assert.ok(rotor2.quaternion.angleTo(start2) < 1e-7);
  assert.ok(blade.getWorldPosition(new Vector3()).distanceTo(bladeStart) > .001);
  fixed.forEach(({ object, matrix }) => assert.ok(delta(object.matrixWorld, matrix) < 1e-9));
  assert.equal(snapshot[0].measuredRpm, 720); assert.equal(snapshot[0].visualRpm, 90);
});
check('Zero stops at the current phase without snapping back', () => {
  const stoppedAt = rotor1.quaternion.clone();
  for (let i = 0; i < 20; i++) animator.update([row('FAN-01', 0), row('FAN-02', 0)], options, 1 / 60);
  assert.ok(rotor1.quaternion.angleTo(stoppedAt) < 1e-7);
});
check('Restart and FAN-02 can run independently', () => {
  const q1 = rotor1.quaternion.clone(), q2 = rotor2.quaternion.clone();
  animator.update([row('FAN-01', 960), row('FAN-02', 840)], options, .1);
  assert.ok(rotor1.quaternion.angleTo(q1) > .1); assert.ok(rotor2.quaternion.angleTo(q2) > .1);
});
check('Stale and per-fan offline data freeze without claiming measured stop', () => {
  const q1 = rotor1.quaternion.clone(), q2 = rotor2.quaternion.clone();
  let result = animator.update([row('FAN-01', 960), row('FAN-02', 840)], { ...options, nowMs: nowMs + 5000 }, .1);
  assert.ok(result.every((r) => r.state === 'unknown' && r.measuredRpm === null));
  assert.ok(rotor1.quaternion.angleTo(q1) < 1e-7); assert.ok(rotor2.quaternion.angleTo(q2) < 1e-7);
  result = animator.update([row('FAN-01', 960), row('FAN-02', 840)], { ...options, offlineAssetCodes: ['FAN-01'] }, .1);
  assert.equal(result[0].state, 'unknown'); assert.equal(result[1].state, 'running');
});
check('30 and 60 rendered frames produce the same angle for the same elapsed second', () => {
  const roots = [root.clone(true), root.clone(true)];
  roots.forEach((r, i) => {
    const a = createFanAnimator(r, contract, { maxAgeMs: 3000 });
    const fps = i === 0 ? 30 : 60;
    for (let f = 0; f < fps; f++) a.update([row('FAN-01', 720)], options, 1 / fps);
    a.dispose();
  });
  assert.ok(find(roots[0], 'FAN-01_ROTOR').quaternion.angleTo(find(roots[1], 'FAN-01_ROTOR').quaternion) < 1e-7);
});
check('Disposed controller cannot retain motion after model replacement', () => {
  const q = rotor1.quaternion.clone(); animator.dispose();
  assert.deepEqual(animator.update([row('FAN-01', 720)], options, .1), []);
  assert.ok(rotor1.quaternion.angleTo(q) < 1e-7);
});
const report = { status: 'PASS', testType: 'ACTUAL_GLB_THREEJS_LOAD_WITH_SYNTHETIC_TELEMETRY', checkCount: checks.length, checks,
  glbSha256: createHash('sha256').update(raw).digest('hex'), realHardwareConnected: false, productionFrontendModified: false,
  limitations: ['Synthetic inputs only; no live relay, tachometer, backend, browser rendering or deployment test.'] };
await writeFile(new URL('./glb-animation-verification.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ status: report.status, checkCount: checks.length, glbSha256: report.glbSha256 }));
