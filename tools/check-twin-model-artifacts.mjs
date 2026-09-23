import { existsSync, readFileSync } from 'node:fs';
import { inspectGlb, missingBindings } from './glb-contract.mjs';

const runtimePath = 'frontend/public/models/utility-tunnel.glb';
const candidatePath = 'model/utility-tunnel-annular-v09-candidate.glb';
const candidateMapPath = 'model/asset-map-v09-candidate.json';
const strict = process.argv.includes('--require-candidate');
const seedPath = 'backend/operations/management/commands/seed_demo.py';
const modelReadmePath = 'model/README.md';
const maxModelBytes = 32 * 1024 * 1024;

function parseGlb(file) {
  if (!existsSync(file)) return { available: false, reason: '文件不存在' };
  const data = readFileSync(file);
  const header = data.toString('utf8', 0, Math.min(data.length, 80));
  if (header.startsWith('version https://git-lfs.github.com/spec/v1')) {
    return { available: false, reason: 'LFS 对象尚未下载' };
  }
  return inspectGlb(data);

}

function currentAssetContract() {
  const seed = readFileSync(seedPath, 'utf8');
  const entries = [...seed.matchAll(/'code':\s*'([^']+)'[\s\S]*?'mesh':\s*'([^']+)'/g)].map((match) => ({ code: match[1], mesh: match[2] }));
  if (entries.length < 18 || new Set(entries.map(a => a.code)).size !== entries.length) throw new Error(`${seedPath}: 未能读取完整的运行资产节点契约`);
  const frontend = readFileSync('frontend/src/stores/operations.ts', 'utf8');
  for (const asset of entries) {
    const line = frontend.split('\n').find(line => line.includes(`code: '${asset.code}'`));
    if (!line?.includes(`mesh: '${asset.mesh}'`)) throw new Error(`${asset.code}: 前后端节点契约不一致`);
  }
  return entries;
}

function mappedAssets(assetMap) {
  return Array.isArray(assetMap.assets)
    ? assetMap.assets
    : Object.entries(assetMap.assets || {}).map(([asset_id, meshNames]) => ({ asset_id, meshNames }));
}

const runtime = parseGlb(runtimePath);
const candidate = parseGlb(candidatePath);
const contract = currentAssetContract();
const readme = readFileSync(modelReadmePath, 'utf8');
const failures = [];

if (!runtime.available) failures.push(`网页运行时模型不可用：${runtime.reason}`);
if (runtime.available && runtime.bytes > maxModelBytes) failures.push(`网页运行时模型 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
const missingRuntimeNodes = runtime.available ? missingBindings(runtime, contract) : contract;
if (missingRuntimeNodes.length) failures.push(`运行时模型缺少资产节点：${missingRuntimeNodes.map((asset) => `${asset.code}=${asset.mesh}`).join('、')}`);
if (!readme.includes('V07') || !readme.includes('asset-map-v07-final.json')) failures.push('模型 README 未声明已验证的 V07 网页运行时基线');

let candidateReady = false;
if (strict && !candidate.available) failures.push(`候选模型不可用：${candidate.reason}`);
let candidateNote = candidate.reason || 'V09 候选模型已进入审查';
if (candidate.available) {
  if (candidate.bytes > maxModelBytes) failures.push(`V09 候选模型 ${(candidate.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
  if (!existsSync(candidateMapPath)) failures.push('V09 候选缺少资产映射文件');
  else {
    const map = JSON.parse(readFileSync(candidateMapPath, 'utf8'));
    const mapAssets = mappedAssets(map);
    const missing = missingBindings(candidate, contract);
    if (missing.length) failures.push(`候选缺少最新运行绑定：${missing.map(a => a.code + '=' + a.mesh).join('、')}`);
    if (map.sha256 !== candidate.sha256) failures.push('候选 SHA-256 与映射不一致');
    if (map.runtimeValidation?.glbNodes !== candidate.nodeCount) failures.push('候选节点数与映射不一致');
    for (const asset of contract) {
      if (!mapAssets.some(a => a.asset_id === asset.code && a.meshNames?.includes(asset.mesh))) failures.push(`候选映射未覆盖最新台账：${asset.code}`);
    }
    const missingCandidateMapNodes = mapAssets.flatMap((asset) => asset.meshNames || []).filter((name) => !candidate.bindable.has(name));
    if (missingCandidateMapNodes.length) failures.push(`V09 候选映射引用了模型中不存在的节点：${missingCandidateMapNodes.join('、')}`);
    candidateReady = candidate.bytes <= maxModelBytes && missingCandidateMapNodes.length === 0 && missing.length === 0 && map.sha256 === candidate.sha256;
    candidateNote = candidateReady ? 'V09 候选通过节点和体积门禁，仍需独立发布审批' : 'V09 候选需要补齐映射或体积门禁';
  }
}

if (failures.length) {
  console.error('三维模型交付检查失败：');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`三维模型交付检查通过：网页运行时 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB，${contract.length}/${contract.length} 个资产节点可定位。`);
if (candidate.available) console.log(`V09 候选：${(candidate.bytes / 1024 / 1024).toFixed(1)}MB，${candidate.nodeCount} 个 GLB 节点；${candidateNote}。`);
else console.log(`V09 候选暂不参与二进制门禁：${candidateNote}；网页继续使用已验证的 V07。`);
