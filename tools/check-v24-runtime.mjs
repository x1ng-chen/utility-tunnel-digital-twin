// Independently load the actual runtime binary; no database, sockets or hardware.
import assert from 'node:assert/strict';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = file => JSON.parse(readFileSync(path.join(root, file), 'utf8'));
const modelRoot = 'model/square-five-station-v24-inset-rgb-fans';
const descriptor = read('backend/operations/agent_catalog/model-v24-presentation.json');
const wire = read('backend/operations/agent_catalog/station-inventory.json');
const packageBindings = read(`${modelRoot}/sensor-bindings.json`).bindings;
const sourceMigration = read(`${modelRoot}/history/sensor-numbering-migration.json`).sensors;
const oxygenMigration = read(`${modelRoot}/history/oxygen-placement-migration.json`).sensors;
const sourceAssets = read(`${modelRoot}/asset-map.json`).assets;
const contract = read(`${modelRoot}/fan-animation-contract.json`);
const threeRoot = path.join(root, 'frontend/node_modules/three');
const { Vector3 } = await import(pathToFileURL(path.join(threeRoot, 'build/three.module.js')));
const { GLTFLoader } = await import(pathToFileURL(path.join(threeRoot, 'examples/jsm/loaders/GLTFLoader.js')));
const runtimeFile = 'frontend/public/models/utility-tunnel-v24.glb';
const bytes = readFileSync(path.join(root, runtimeFile));
assert.equal(bytes.readUInt32LE(0), 0x46546c67, 'Runtime file must be an actual GLB, not an LFS pointer');
const source = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)));
const gltf = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
gltf.scene.updateMatrixWorld(true);
const objects = new Map();
for (const [object, association] of gltf.parser.associations) {
  if (association.nodes !== undefined) objects.set(association.nodes, object);
}
const byName = new Map();
for (let index = 0; index < source.nodes.length; index++) {
  const name = source.nodes[index].name;
  assert(name && !byName.has(name), `Missing or duplicate source node name: ${name}`);
  byName.set(name, objects.get(index));
}
const get = name => {
  const object = byName.get(name);
  assert(object, `Node is not loaded exactly once: ${name}`);
  return object;
};
const position = name => get(name).getWorldPosition(new Vector3()).toArray();
const near = (actual, expected, label) => {
  assert.equal(actual.length, expected.length, label);
  assert(actual.every((value, index) => Math.abs(value - expected[index]) <= 1e-5),
    `${label}: actual ${JSON.stringify(actual)} != expected ${JSON.stringify(expected)}`);
};
const checks = [];
const check = (name, run) => {
  try { checks.push({ name, status: 'PASS', evidence: run() }); }
  catch (error) { checks.push({ name, status: 'FAIL', error: error.message }); }
};

check('exact_runtime_binary_hash_and_scene', () => {
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  assert.equal(sha256, descriptor.modelSha256);
  assert.equal(source.nodes.length, 755);
  assert.equal(byName.size, 755);
  assert.equal(source.animations?.length ?? 0, 0);
  const assets = source.nodes.filter(node => node.extras?.assetCode);
  assert.equal(assets.length, 69);
  assert.equal(assets.filter(node => node.extras.category === 'external_sensor').length, 31);
  return { sha256, bytes: bytes.length, uniqueNodes: byName.size, semanticAssets: assets.length,
    externalSensors: 31, autoPlayingAnimations: 0 };
});

const renames = new Map([...sourceMigration, ...oxygenMigration].map(row => [row.oldAssetCode, row.newAssetCode]));
const targets = new Map(packageBindings.map(row => [row.assetCode, row]));
check('all_31_wire_identities_have_unique_exact_model_targets', () => {
  assert.equal(wire.bindings.length, 31);
  const wireIds = wire.bindings.map(row => row.assetCode).sort();
  for (const field of ['sensorStations', 'sensorMeshes', 'sensorModelTags', 'sensorPositionsGltfM']) {
    assert.deepEqual(Object.keys(descriptor[field]).sort(), wireIds, `${field} must cover only all 31 wire IDs`);
  }
  assert.equal(new Set(Object.values(descriptor.sensorMeshes)).size, 31);
  const evidence = [];
  for (const row of wire.bindings) {
    const modelId = renames.get(row.assetCode) ?? row.assetCode;
    const target = targets.get(modelId);
    assert(target, `Source migration does not resolve ${row.assetCode}`);
    assert.equal(descriptor.sensorMeshes[row.assetCode], target.targetNode, row.assetCode);
    assert.equal(descriptor.sensorStations[row.assetCode], target.stationId, row.assetCode);
    assert.equal(descriptor.sensorModelTags[row.assetCode], target.physicalTag, row.assetCode);
    near(position(target.targetNode), descriptor.sensorPositionsGltfM[row.assetCode], row.assetCode);
    near(position(target.targetNode), target.positionGltf_m, `${row.assetCode} source position`);
    evidence.push({ wireAssetCode: row.assetCode, wireControllerId: row.controllerId,
      targetNode: target.targetNode, modelTag: target.physicalTag, stationId: target.stationId,
      positionGltfM: position(target.targetNode) });
  }
  return evidence;
});

check('five_station_groups_and_sensor_family_constraints', () => {
  assert.deepEqual(descriptor.stations.map(row => row.id).sort(), ['P1', 'P2', 'P3', 'P4', 'P5']);
  for (const row of descriptor.stations) get(row.groupNode);
  const counts = Object.fromEntries(descriptor.stations.map(row => [row.id,
    wire.bindings.filter(sensor => descriptor.sensorStations[sensor.assetCode] === row.id).length]));
  assert.equal(Object.values(counts).reduce((sum, count) => sum + count, 0), 31);
  assert(wire.bindings.filter(row => row.physicalTag.startsWith('SHT-')).every(row =>
    descriptor.sensorStations[row.assetCode] !== 'P5'), 'P5 must not gain a temperature/humidity module');
  const oxygen = wire.bindings.filter(row => row.physicalTag.startsWith('O2-')).map(row => ({
    wireAssetCode: row.assetCode, targetNode: descriptor.sensorMeshes[row.assetCode],
    stationId: descriptor.sensorStations[row.assetCode] }));
  assert.deepEqual(oxygen.map(row => row.stationId).sort(), ['P1', 'P2', 'P5']);
  assert.deepEqual(oxygen.map(row => row.targetNode).sort(), ['GAS-O2-01', 'GAS-O2-02', 'GAS-O2-05']);
  return { counts, oxygen, temperatureHumidityAtP5: false };
});

check('canonical_controller_positions_and_independent_fan_roots', () => {
  const evidence = [];
  for (const [code, target] of Object.entries(descriptor.controllerMeshes)) {
    assert.equal(code, target, 'Current accepted controller mesh names remain canonical');
    const [x, y, z] = descriptor.controllerPositionsBlenderM[code];
    near(position(target), [x, z, -y], code);
    evidence.push({ wireControllerId: code, targetNode: target, positionGltfM: position(target) });
  }
  assert.equal(evidence.length, 4);
  for (const fan of contract.fans) {
    get(fan.assetCode); get(fan.rotorNode);
    near(fan.spinAxisGltfLocal, [0, 1, 0], `${fan.assetCode} glTF spin axis`);
    const segments = [...byName.keys()].filter(name => name.startsWith(fan.rgbNodePrefix));
    assert.equal(segments.length, 24, `${fan.assetCode} must have 24 independent RGB meshes`);
    const sourceAsset = sourceAssets.find(row => row.assetCode === fan.assetCode);
    near(position(fan.assetCode), sourceAsset.positionGltf_m, fan.assetCode);
  }
  return { controllers: evidence, fans: contract.fans.map(row => ({ assetCode: row.assetCode,
    rotorNode: row.rotorNode, rgbSegments: 24, spinAxisGltfLocal: row.spinAxisGltfLocal })),
    controllerOwnershipTakenFromModelMetadata: false };
});

const result = { schemaVersion: 1, evaluatedAtUtc: new Date().toISOString(),
  status: checks.every(row => row.status === 'PASS') ? 'PASS' : 'FAIL',
  route: 'ACTUAL_RUNTIME_GLB_THREE_GLTFLOADER', runtimeFile,
  descriptorRevision: descriptor.revision, wireLayoutVersion: wire.revision,
  source: 'STATIC_GEOMETRY_AND_MAPPING_VERIFICATION', checks,
  hardwareCommands: 0, modelCalls: 0, hardwareAcceptance: 'NOT_RUN', browserVisualQa: 'NOT_RUN',
  boundary: 'Actual GLB loading and exact mapping checks; not proof of live alarm, physical wiring, RPM or RGB feedback.' };
const destination = path.join(root, 'docs/model-v24-runtime-20261029/glb-verification.json');
mkdirSync(path.dirname(destination), { recursive: true });
writeFileSync(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ status: result.status, checks: checks.map(row => ({ name: row.name, status: row.status,
  ...(row.error ? { error: row.error } : {}) })), output: path.relative(root, destination) }));
process.exitCode = result.status === 'PASS' ? 0 : 1;
