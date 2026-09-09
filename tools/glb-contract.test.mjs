import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectGlb, missingBindings } from './glb-contract.mjs';

function glb(doc) {
  const json = JSON.stringify({ asset: { version: '2.0' }, ...doc });
  const body = Buffer.from(json + ' '.repeat((4 - Buffer.byteLength(json) % 4) % 4));
  const result = Buffer.alloc(20 + body.length);
  result.write('glTF'); result.writeUInt32LE(2, 4); result.writeUInt32LE(result.length, 8);
  result.writeUInt32LE(body.length, 12); result.writeUInt32LE(0x4e4f534a, 16); body.copy(result, 20);
  return result;
}
test('geometry and owning group bind, empty placeholder does not', () => {
  const m = inspectGlb(glb({ nodes: [{name:'GROUP',children:[1]},{name:'PROBE',mesh:0},{name:'EMPTY'}], meshes:[{primitives:[{}]}] }));
  assert.deepEqual(missingBindings(m, ['GROUP','PROBE','EMPTY'].map(mesh => ({mesh}))), [{mesh:'EMPTY'}]);
  assert.match(m.sha256, /^[a-f0-9]{64}$/);
});
for (const [name, doc] of Object.entries({
  duplicate: {nodes:[{name:'same'},{name:'same'}]},
  badMesh: {nodes:[{name:'broken',mesh:99}]},
  cycle: {nodes:[{children:[1]},{children:[0]}]},
  multipleParents: {nodes:[{children:[2]},{children:[2]},{}]},
  badTransform: {nodes:[{translation:[null,0,0]}]},
  conflictingTransform: {nodes:[{matrix:Array(16).fill(0),translation:[0,0,0]}]},
})) test(`reject ${name}`, () => assert.throws(() => inspectGlb(glb(doc))));
test('reject LFS pointer and truncated binary', () => {
  assert.throws(() => inspectGlb(Buffer.from('version https://git-lfs.github.com/spec/v1\n')), /LFS/);
  assert.throws(() => inspectGlb(glb({}).subarray(0, 20)), /长度/);
});
