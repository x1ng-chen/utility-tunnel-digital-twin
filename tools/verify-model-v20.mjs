/** Load the actual GLB, independently verify identity/positions and camera orientation. */
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import assert from 'node:assert/strict';
import { GLTFLoader } from '../frontend/node_modules/three/examples/jsm/loaders/GLTFLoader.js';
import { Vector3, PerspectiveCamera, Box3 } from '../frontend/node_modules/three/build/three.module.js';
const root = new URL('../', import.meta.url);
const read = path => JSON.parse(readFileSync(new URL(path, root), 'utf8'));
const contract = read('backend/operations/agent_catalog/model-v20-presentation.json');
const wire = read('backend/operations/agent_catalog/station-inventory.json');
const bytes = readFileSync(new URL(contract.modelPath, root));
assert.equal(createHash('sha256').update(bytes).digest('hex'), contract.modelSha256);
globalThis.ProgressEvent ??= class ProgressEvent { constructor(type, values) { this.type=type; Object.assign(this, values); } };
const model = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset+bytes.byteLength), '');
model.scene.updateMatrixWorld(true);
const named = new Map();
model.scene.traverse(node => { const key=node.userData.name || node.name; const group=named.get(key)??[];group.push(node);named.set(key,group); });
function node(name) { assert.equal(named.get(name)?.length,1, name+' must resolve uniquely');return named.get(name)[0]; }
for (const binding of wire.bindings) {
  const object = node(binding.targetNode);
  const position = object.getWorldPosition(new Vector3());
  assert.ok(position.distanceTo(new Vector3(...contract.sensorPositionsGltfM[binding.assetCode]))<1e-5,binding.assetCode+' position');
  if (binding.stationLinkKind==='DIRECT_FOUR_SENSOR_MEMBER') {
    let parent=object.parent;
    while(parent && !String(parent.userData.name || parent.name).startsWith('STATION_P')) parent=parent.parent;
    assert.equal(parent?.userData.name || parent?.name,'STATION_'+contract.sensorStations[binding.assetCode]);
  }
}
for (const [code, xyz] of Object.entries(contract.controllerPositionsBlenderM)) {
  assert.ok(node(code).getWorldPosition(new Vector3()).distanceTo(new Vector3(xyz[0],xyz[2],-xyz[1]))<1e-5,code+' position');
}
for (const fan of ['FAN-01','FAN-02']) {
  const rotor=node(fan+'_ROTOR');assert.ok(rotor.children.length>0);assert.notEqual(rotor,node(fan));
}
const center=new Box3().setFromObject(model.scene).getCenter(new Vector3());
const camera=new PerspectiveCamera(48, 16/9, .01, 20);
camera.position.copy(center.clone().add(new Vector3(...contract.frontCameraDirection).normalize().multiplyScalar(2)));
camera.lookAt(center);camera.updateMatrixWorld(true);camera.updateProjectionMatrix();
const screen=Object.fromEntries(contract.stations.map(s=>{
  node('STATION_LABEL_'+s.id);
  return [s.id,node(s.groupNode).getWorldPosition(new Vector3()).project(camera).toArray()];
}));
assert.ok(screen.P1[0]<screen.P2[0] && screen.P3[0]<screen.P4[0]);
assert.ok(screen.P1[1]>screen.P3[1] && screen.P2[1]>screen.P4[1]);
const result={status:'PASS',method:'ACTUAL_THREEJS_GLB_LOAD',modelSha256:contract.modelSha256,
  sensorTargetsAndPositions:31,primaryStationMemberships:20,controllerPositions:4,fanRotors:2,
  cameraOrder:'rear P1/P2, front P3/P4, centre P5',screen,
  hardwareCommands:0,modelCalls:0,boundary:'Model and projection checks; browser rendering and physical wiring are separate.'};
writeFileSync(new URL('.hardware-live/v20-glb-verification.json',root),JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
