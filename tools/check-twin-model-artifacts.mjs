import { existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { inspectGlb, missingBindings } from './glb-contract.mjs';

const runtimePath = 'frontend/public/models/utility-tunnel.glb';
const rollbackPath = 'frontend/public/models/utility-tunnel-v07.glb';
const runtimeManifestPath = 'model/v13-runtime-handoff.json';
const v13BindingsPath = 'frontend/src/services/v13AssetBindings.json';
const candidatePath = 'model/utility-tunnel-annular-v09-candidate.glb';
const candidateMapPath = 'model/asset-map-v09-candidate.json';
const strict = process.argv.includes('--require-candidate');
const requireSource = process.argv.includes('--require-source');
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
const rollback = parseGlb(rollbackPath);
const runtimeManifest = existsSync(runtimeManifestPath) ? JSON.parse(readFileSync(runtimeManifestPath, 'utf8')) : null;
const v13Bindings = existsSync(v13BindingsPath) ? JSON.parse(readFileSync(v13BindingsPath, 'utf8')) : null;
const candidate = parseGlb(candidatePath);
const contract = currentAssetContract();
const readme = readFileSync(modelReadmePath, 'utf8');
const failures = [];

if (!v13Bindings || !Object.keys(v13Bindings).length) failures.push('缺少 V13 前端资产节点映射');
else {
  const assetCodes = new Set(contract.map((asset) => asset.code));
  const entries = Object.entries(v13Bindings);
  const unknownCodes = entries.filter(([code]) => !assetCodes.has(code)).map(([code]) => code);
  if (unknownCodes.length) failures.push(`V13 映射引用了台账中不存在的资产：${unknownCodes.join('、')}`);
  const duplicateNodes = entries.map(([, node]) => node).filter((node, index, nodes) => nodes.indexOf(node) !== index);
  if (duplicateNodes.length) failures.push(`V13 多个资产绑定同一个节点：${[...new Set(duplicateNodes)].join('、')}`);
  const missingNodes = runtime.available ? entries.filter(([, node]) => !runtime.bindable.has(node)).map(([code, node]) => `${code}=${node}`) : [];
  if (missingNodes.length) failures.push(`V13 资产映射引用了模型中不存在的网格：${missingNodes.join('、')}`);
  const expectedLevels = Array.from({ length: 5 }, (_, index) => `LEVEL-L0${index + 1}`);
  const missingLevelMappings = expectedLevels.filter((code) => v13Bindings[code] !== `${code}-探头`);
  if (missingLevelMappings.length) failures.push(`V13 五个液位测点映射不完整：${missingLevelMappings.join('、')}`);
}

if (!runtime.available) failures.push(`网页运行时模型不可用：${runtime.reason}`);
if (runtime.available && runtime.bytes > maxModelBytes) failures.push(`网页运行时模型 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
if (!rollback.available) failures.push(`V07 回退模型不可用：${rollback.reason}`);
const missingRollbackNodes = rollback.available ? missingBindings(rollback, contract) : contract;
if (missingRollbackNodes.length) failures.push(`V07 回退模型缺少资产节点：${missingRollbackNodes.map((asset) => asset.code).join('、')}`);
if (!runtimeManifest) failures.push('缺少 V13 运行模型同源导出记录');
else {
  if (runtimeManifest.runtime !== runtimePath) failures.push('V13 运行模型路径与导出记录不一致');
  if (runtime.available && runtime.sha256 !== runtimeManifest.runtimeSha256) failures.push('V13 运行模型 SHA-256 与导出记录不一致');
  if (runtime.available && runtime.nodeCount !== runtimeManifest.visibleMeshCount) failures.push('V13 运行模型节点数与可见网格导出记录不一致');
  if (runtimeManifest.rollback !== rollbackPath || rollback.available && runtimeManifest.rollbackSha256 !== rollback.sha256) failures.push('V07 回退模型 SHA-256 与导出记录不一致');
  const expectedLevels = Array.from({ length: 5 }, (_, index) => `LEVEL-L0${index + 1}-探头`);
  if (JSON.stringify(runtimeManifest.levelNodes) !== JSON.stringify(expectedLevels)) failures.push('V13 五个测点的导出契约不完整');
  const missingLevels = runtime.available ? expectedLevels.filter((name) => !runtime.bindable.has(name)) : expectedLevels;
  if (missingLevels.length) failures.push(`V13 运行模型缺少液位探头：${missingLevels.join('、')}`);
  if (requireSource) {
    if (!existsSync(runtimeManifest.source)) failures.push('V13 BLEND 源文件不存在');
    else {
      const source = readFileSync(runtimeManifest.source);
      if (source.toString('utf8', 0, 80).startsWith('version https://git-lfs.github.com/spec/v1')) failures.push('V13 BLEND 源文件 LFS 对象未下载');
      else if (createHash('sha256').update(source).digest('hex') !== runtimeManifest.sourceSha256) failures.push('V13 BLEND 源文件 SHA-256 与导出记录不一致');
    }
  }
}
if (!readme.includes('V13') || !readme.includes('frontend/public/models/utility-tunnel.glb')) failures.push('模型 README 未声明 V13 前端运行时模型');

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

console.log(`三维模型交付检查通过：V13 网页运行时 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB，${Object.keys(v13Bindings).length}/${contract.length} 个台账资产有确认节点（含 5/5 个液位探头）；其余资产显示为未映射。`);
if (candidate.available) console.log(`V09 候选：${(candidate.bytes / 1024 / 1024).toFixed(1)}MB，${candidate.nodeCount} 个 GLB 节点；${candidateNote}。`);
else console.log(`V09 候选暂不参与二进制门禁：${candidateNote}；网页使用 V13，已启用版本可单独切换。`);
