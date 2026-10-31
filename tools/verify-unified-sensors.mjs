/** Validate exact GLB bindings and transforms with the actual Three.js loader. */
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Vector3} from '../frontend/node_modules/three/build/three.module.js';
import {GLTFLoader} from '../frontend/node_modules/three/examples/jsm/loaders/GLTFLoader.js';
const root = new URL('../', import.meta.url);
const read = path => JSON.parse(readFileSync(new URL(path, root), 'utf8'));
const descriptor = read('backend/operations/agent_catalog/model-v24-unified-presentation.json');
const inventory = read('backend/operations/agent_catalog/station-inventory.json');
const raw = readFileSync(new URL(descriptor.modelPath, root));
assert.equal(createHash('sha256').update(raw).digest('hex'), descriptor.modelSha256);
const json = JSON.parse(raw.subarray(20, 20+raw.readUInt32LE(12)));
const gltf = await new GLTFLoader().parseAsync(raw.buffer.slice(raw.byteOffset, raw.byteOffset+raw.byteLength), '');
gltf.scene.updateMatrixWorld(true);
const objects = new Map();
for (const [object, association] of gltf.parser.associations) if (association.nodes !== undefined) objects.set(association.nodes, object);
const byName = new Map(json.nodes.map((node,index) => [node.name,objects.get(index)]));
assert.equal(byName.size, 755);
const checked = [];
for (const binding of inventory.bindings) {
  const code = binding.assetCode, target = descriptor.sensorMeshes[code], node = byName.get(target);
  assert.ok(node, `${code} target missing`);
  assert.equal(node.userData.assetCode, code);
  assert.equal(node.userData.physicalTag, binding.physicalTag);
  assert.equal(node.userData.controllerId, binding.controllerId);
  assert.equal(node.userData.stationId, descriptor.sensorStations[code]);
  const position = node.getWorldPosition(new Vector3()).toArray();
  assert.ok(position.every((v,i) => Math.abs(v-descriptor.sensorPositionsGltfM[code][i]) < 1e-6), code);
  checked.push({code, target, station: node.userData.stationId, physicalTag: node.userData.physicalTag});
}
assert.equal(new Set(checked.map(item => item.target)).size, 31);
assert.ok(byName.get('O2-03_TEXT'));
assert.ok(!byName.has('GAS-O2-05') && !byName.has('O2-05_TEXT'));
for (const code of ['FAN-01','FAN-02']) {
  const rotor = byName.get(code+'_ROTOR');
  assert.equal(rotor.parent, byName.get(code));
  assert.equal(rotor.children.filter(node => node.name.includes('BLADE')).length, 7);
  for (let n=0;n<24;n++) assert.equal(byName.get(`${code}_RGB_SEGMENT_${String(n).padStart(2,'0')}`).parent, byName.get(code));
}
const report = {revision: descriptor.revision, modelSha256: descriptor.modelSha256,
  status: 'PASS', sensorCount: 31, uniqueTargets: 31, nodeCount: 755, fanRotors: 2, fixedRgbSegments: 48,
  oxygenLabel: 'O2-03', checked, boundary: 'Actual GLB/Three.js validation; browser and physical trigger acceptance are separate.'};
writeFileSync(new URL('model/square-five-station-v24-unified-numbering/three-validation.json', root), JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report, checked: undefined}));
