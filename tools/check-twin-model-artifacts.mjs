import { readFileSync, statSync } from 'node:fs';

const runtimePath = 'frontend/public/models/utility-tunnel.glb';
const candidatePath = 'model/utility-tunnel-annular-v05-final.glb';
const candidateMapPath = 'model/asset-map-v05-final.json';
const seedPath = 'backend/operations/management/commands/seed_demo.py';
const modelReadmePath = 'model/README.md';
const maxRuntimeBytes = 32 * 1024 * 1024;

function parseGlb(file) {
  const data = readFileSync(file);
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
  return { bytes: data.length, nodes: new Set((document.nodes || []).map((node) => node.name).filter(Boolean)) };
}

function currentAssetContract() {
  const seed = readFileSync(seedPath, 'utf8');
  const entries = [...seed.matchAll(/'code':\s*'([^']+)'[\s\S]*?'mesh':\s*'([^']+)'/g)].map((match) => ({ code: match[1], mesh: match[2] }));
  if (entries.length < 10) throw new Error(`${seedPath}: 未能读取完整的运行资产节点契约`);
  return entries;
}

const runtime = parseGlb(runtimePath);
const candidate = parseGlb(candidatePath);
const contract = currentAssetContract();
const candidateMap = JSON.parse(readFileSync(candidateMapPath, 'utf8'));
const readme = readFileSync(modelReadmePath, 'utf8');
const failures = [];

if (runtime.bytes > maxRuntimeBytes) failures.push(`运行时模型 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
const missingRuntimeNodes = contract.filter((asset) => !runtime.nodes.has(asset.mesh));
if (missingRuntimeNodes.length) failures.push(`运行时模型缺少资产节点：${missingRuntimeNodes.map((asset) => `${asset.code}=${asset.mesh}`).join('、')}`);

const candidateMappedNodes = Object.values(candidateMap.assets || {}).flat();
const missingCandidateMapNodes = candidateMappedNodes.filter((name) => !candidate.nodes.has(name));
if (missingCandidateMapNodes.length) failures.push(`V05 映射引用了模型中不存在的节点：${missingCandidateMapNodes.join('、')}`);

const candidateReady = candidate.bytes <= maxRuntimeBytes && contract.every((asset) => candidate.nodes.has(asset.mesh));
if (!candidateReady) {
  if (!/完成模型压缩、资产映射切换和浏览器加载回归/.test(readme)) failures.push('V05 尚未满足运行条件，但 README 未披露压缩、映射和回归门禁');
  if (statSync(runtimePath).size === statSync(candidatePath).size) failures.push('未就绪的 V05 不得覆盖当前受控运行时模型');
}

if (failures.length) {
  console.error('三维模型交付检查失败：');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`三维模型交付检查通过：运行时 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB，${contract.length}/${contract.length} 个资产节点可定位。`);
if (candidateReady) console.log('V05 候选模型已满足浏览器运行时替换条件。');
else console.log(`V05 候选模型暂不替换：${(candidate.bytes / 1024 / 1024).toFixed(1)}MB，仍需压缩并补齐当前 ${contract.length} 个资产节点映射。`);
