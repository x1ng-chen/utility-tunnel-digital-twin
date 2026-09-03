import { existsSync, readFileSync } from 'node:fs';

const runtimePath = 'frontend/public/models/utility-tunnel.glb';
const candidatePath = 'model/utility-tunnel-annular-v08-final.glb';
const candidateMapPath = 'model/asset-map-v08-final.json';
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
  if (data.length < 20 || data.toString('ascii', 0, 4) !== 'glTF') throw new Error(`${file}: 不是有效的 GLB 文件`);
  if (data.readUInt32LE(4) !== 2) throw new Error(`${file}: 仅支持 GLB 2.0`);
  if (data.readUInt32LE(8) !== data.length) throw new Error(`${file}: 文件长度与 GLB 头不一致`);
  let offset = 12;
  let document;
  while (offset + 8 <= data.length) {
    const length = data.readUInt32LE(offset);
    const type = data.readUInt32LE(offset + 4);
    const end = offset + 8 + length;
    if (end > data.length) throw new Error(`${file}: GLB 数据块越界`);
    if (type === 0x4e4f534a) document = JSON.parse(data.toString('utf8', offset + 8, end).replace(/\u0000+$/g, '').trim());
    offset = end;
  }
  if (!document || document.asset?.version !== '2.0') throw new Error(`${file}: 缺少有效的 glTF 2.0 JSON 数据块`);
  return { available: true, bytes: data.length, nodeCount: (document.nodes || []).length, nodes: new Set((document.nodes || []).map((node) => node.name).filter(Boolean)) };
}

function currentAssetContract() {
  const seed = readFileSync(seedPath, 'utf8');
  const entries = [...seed.matchAll(/'code':\s*'([^']+)'[\s\S]*?'mesh':\s*'([^']+)'/g)].map((match) => ({ code: match[1], mesh: match[2] }));
  if (entries.length < 10) throw new Error(`${seedPath}: 未能读取完整的运行资产节点契约`);
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
const candidateMap = JSON.parse(readFileSync(candidateMapPath, 'utf8'));
const readme = readFileSync(modelReadmePath, 'utf8');
const failures = [];

if (!runtime.available) failures.push(`网页运行时模型不可用：${runtime.reason}`);
if (runtime.available && runtime.bytes > maxModelBytes) failures.push(`网页运行时模型 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
const missingRuntimeNodes = runtime.available ? contract.filter((asset) => !runtime.nodes.has(asset.mesh)) : contract;
if (missingRuntimeNodes.length) failures.push(`运行时模型缺少资产节点：${missingRuntimeNodes.map((asset) => `${asset.code}=${asset.mesh}`).join('、')}`);
if (!readme.includes('V07') || !readme.includes('asset-map-v07-final.json')) failures.push('模型 README 未声明已验证的 V07 网页运行时基线');

let candidateReady = false;
let candidateNote = candidate.reason || 'V08 候选模型已进入审查';
if (candidate.available) {
  if (candidate.bytes > maxModelBytes) failures.push(`V08 候选模型 ${(candidate.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
  if (!existsSync(candidateMapPath)) failures.push('V08 候选缺少资产映射文件');
  else {
    const map = JSON.parse(readFileSync(candidateMapPath, 'utf8'));
    const mapAssets = mappedAssets(map);
    const missingCandidateMapNodes = mapAssets.flatMap((asset) => asset.meshNames || []).filter((name) => !candidate.nodes.has(name));
    if (missingCandidateMapNodes.length) failures.push(`V08 候选映射引用了模型中不存在的节点：${missingCandidateMapNodes.join('、')}`);
    candidateReady = candidate.bytes <= maxModelBytes && missingCandidateMapNodes.length === 0;
    candidateNote = candidateReady ? 'V08 候选通过节点和体积门禁，仍需独立发布审批' : 'V08 候选需要补齐映射或体积门禁';
  }
}

if (failures.length) {
  console.error('三维模型交付检查失败：');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`三维模型交付检查通过：网页运行时 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB，${contract.length}/${contract.length} 个资产节点可定位。`);
if (candidate.available) console.log(`V08 候选：${(candidate.bytes / 1024 / 1024).toFixed(1)}MB，${candidate.nodeCount} 个 GLB 节点；${candidateNote}。`);
else console.log(`V08 候选暂不参与二进制门禁：${candidateNote}；网页继续使用已验证的 V07。`);
