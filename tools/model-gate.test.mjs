import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { inspectGlb } from './glb-contract.mjs';

const script = resolve('tools/check-twin-model-artifacts.mjs');
const seed = readFileSync('backend/operations/management/commands/seed_demo.py','utf8');
const frontend = readFileSync('frontend/src/stores/operations.ts','utf8');
const contract = [...seed.matchAll(/'code':\s*'([^']+)'[\s\S]*?'mesh':\s*'([^']+)'/g)].map(m => ({asset_id:m[1],meshNames:[m[2]]}));
function binary(emptyLast=false) {
  const doc = {asset:{version:'2.0'}, nodes:contract.map((a,i) => ({name:a.meshNames[0], ...(emptyLast && i===contract.length-1 ? {} : {mesh:0})})), meshes:[{primitives:[{}]}]};
  const text = JSON.stringify(doc);
  const body = Buffer.from(text+' '.repeat((4-Buffer.byteLength(text)%4)%4));
  const b = Buffer.alloc(20+body.length);
  b.write('glTF'); b.writeUInt32LE(2,4); b.writeUInt32LE(b.length,8); b.writeUInt32LE(body.length,12); b.writeUInt32LE(0x4e4f534a,16); body.copy(b,20);
  return b;
}
for (const scenario of ['valid','missing-map','missing-candidate','pointer','wrong-hash','empty-binding']) {
  test(`release gate ${scenario}`, () => {
    const root = mkdtempSync(join(tmpdir(),'ut-model-gate-'));
    const put = (path,data) => { const file=join(root,path); mkdirSync(dirname(file),{recursive:true}); writeFileSync(file,data); };
    try {
      put('backend/operations/management/commands/seed_demo.py',seed);
      put('frontend/src/stores/operations.ts',frontend);
      put('model/README.md','V07 asset-map-v07-final.json');
      put('frontend/public/models/utility-tunnel.glb',binary());
      const candidate=binary(scenario==='empty-binding');
      if(scenario!=='missing-candidate') put('model/utility-tunnel-annular-v09-candidate.glb',scenario==='pointer'?'version https://git-lfs.github.com/spec/v1\n':candidate);
      if(scenario!=='missing-map') put('model/asset-map-v09-candidate.json',JSON.stringify({assets:contract,sha256:scenario==='wrong-hash'?'incorrect':inspectGlb(candidate).sha256,runtimeValidation:{glbNodes:contract.length}}));
      const result=spawnSync(process.execPath,[script,'--require-candidate'],{cwd:root,encoding:'utf8'});
      assert.equal(result.status,scenario==='valid'?0:1,result.stdout+result.stderr);
      if(scenario==='missing-candidate') assert.equal(spawnSync(process.execPath,[script],{cwd:root}).status,0);
    } finally {
      // Only the unique test-owned directory returned by mkdtemp is removed.
      rmSync(root,{recursive:true,force:true});
    }
  });
}
