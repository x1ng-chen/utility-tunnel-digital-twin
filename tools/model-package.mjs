// Run --write only after inspecting the final screenshots. Without --write,
// verify all deliverable bytes; a pointer-only checkout must fail release QA.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
const manifestPath = 'model/v09-package-manifest.json';
if (process.argv.includes('--write')) {
  // Canonical generated metadata uses LF on every platform, like Git's blobs.
  for (const file of ['model/asset-map-v09-candidate.json','model/v09-structural-audit.json']) {
    writeFileSync(file, JSON.stringify(JSON.parse(readFileSync(file,'utf8')),null,2)+'\n');
  }
}
const files = [
  'model/utility-tunnel-annular-v09-candidate.blend',
  'model/utility-tunnel-annular-v09-candidate.glb',
  'model/asset-map-v09-candidate.json',
  'model/v09-structural-audit.json',
  ...['overview','front','top','water','control','browser-candidate','assets'].map(view => `model/previews/v09-${view}.png`),
];
const actual = files.map(path => {
  const bytes = readFileSync(path);
  if (bytes.toString('utf8',0,80).startsWith('version https://git-lfs.github.com/spec/v1')) throw new Error(`${path}: missing LFS object`);
  return {path,bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')};
});
if (process.argv.includes('--write')) {
  writeFileSync(manifestPath, JSON.stringify({version:'V09-CANDIDATE',files:actual},null,2)+'\n');
  console.log('Candidate package manifest written; not a deployment authorization.');
} else {
  const expected = JSON.parse(readFileSync(manifestPath,'utf8'));
  if (JSON.stringify(expected.files) !== JSON.stringify(actual)) throw new Error('Candidate package changed after recorded QA; inspect and regenerate manifest.');
  console.log(`Candidate package verified: ${actual.length} files, all SHA-256 hashes match.`);
}
