// Run --write only AFTER final multi-view review and fresh Blender verification.
// This is an additional candidate gate; V07 runtime and V09 CI remain unchanged.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { inspectGlb } from './glb-contract.mjs';

const readJson = path => JSON.parse(readFileSync(path, 'utf8'));
const model = inspectGlb(readFileSync('model/utility-tunnel-annular-v10-candidate.glb'));
const mapping = readJson('model/asset-map-v10-candidate.json');
const audit = readJson('model/v10-floor-audit.json');
const validation = readJson('model/v10-export-validation.json');
assert.equal(mapping.sha256, model.sha256);
assert.equal(validation.sha256, model.sha256, 'Fresh-import evidence is stale');
assert.equal(validation.status, 'PASS');
assert.equal(audit.after.status, 'PASS');
assert.equal(validation.freshImportFloor.status, 'PASS');
assert.equal(validation.floorRegressionFixtures.status, 'PASS');
assert.equal(validation.newUnexpectedSurfacePairs.length, 0);
assert.equal(model.nodeCount, validation.meshCount);
assert.equal(model.nodeCount, mapping.runtimeValidation.glbNodes);
assert(model.bytes < 15 * 1024 * 1024, 'Candidate exceeds export size budget');
for (const asset of mapping.assets) {
  for (const name of asset.meshNames) assert(model.bindable.has(name), `${asset.asset_id}: ${name} missing`);
}
assert.equal(mapping.assets.filter(a => /^LEVEL-L0[1-5]$/.test(a.asset_id)).length, 5);
const files = [
  'model/utility-tunnel-annular-v10-candidate.blend',
  'model/utility-tunnel-annular-v10-candidate.glb',
  'model/asset-map-v10-candidate.json',
  'model/v10-floor-audit.json',
  'model/v10-export-validation.json',
  'model/quality-report-v10-candidate.md',
  ...['overview','front','side','water','drain','floor','bottom'].map(v => `model/previews/v10-${v}.png`),
  'tools/model_floor_audit.py', 'tools/repair_model_v10.py',
  'tools/verify_model_v10.py', 'tools/check-model-v10.mjs',
];
const actual = files.map(path => {
  const bytes = readFileSync(path);
  assert(!bytes.toString('utf8',0,80).startsWith('version https://git-lfs.github.com/spec/v1'), `${path}: missing LFS object`);
  return {path, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')};
});
const manifest = 'model/v10-package-manifest.json';
if (process.argv.includes('--write')) {
  writeFileSync(manifest, JSON.stringify({version:'V10-CANDIDATE', date:'2026-09-08', files:actual}, null, 2)+'\n');
} else {
  assert.deepEqual(readJson(manifest).files, actual, 'Package changed after QA');
}
console.log(`V10 PASS: ${model.nodeCount} nodes, ${mapping.assets.length} mapped assets, ${actual.length} hashed files; production V07 unchanged.`);
