import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename, join } from 'node:path';

const runtimePath = 'frontend/public/models/utility-tunnel.glb';
const modelDirectory = 'model';
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
  return {
    bytes: data.length,
    digest: createHash('sha256').update(data).digest('hex'),
    nodeCount: (document.nodes || []).length,
    nodes: new Set((document.nodes || []).map((node) => node.name).filter(Boolean)),
  };
}

function currentAssetContract() {
  const seed = readFileSync(seedPath, 'utf8');
  const entries = [...seed.matchAll(/'code':\s*'([^']+)'[\s\S]*?'mesh':\s*'([^']+)'/g)].map((match) => ({ code: match[1], mesh: match[2] }));
  if (entries.length < 10) throw new Error(`${seedPath}: 未能读取完整的运行资产节点契约`);
  return entries;
}

function latestFormalDelivery() {
  const maps = readdirSync(modelDirectory)
    .map((name) => ({ name, match: name.match(/^asset-map-v(\d+)-final\.json$/i) }))
    .filter((entry) => entry.match)
    .sort((left, right) => Number(right.match[1]) - Number(left.match[1]));
  if (!maps.length) throw new Error(`${modelDirectory}: 缺少正式模型资产映射`);
  const mapPath = join(modelDirectory, maps[0].name);
  const map = JSON.parse(readFileSync(mapPath, 'utf8'));
  const modelName = map.model || map.modelFile;
  if (!modelName) throw new Error(`${mapPath}: 缺少 model/modelFile 字段`);
  const modelPath = join(modelDirectory, modelName);
  if (!existsSync(modelPath)) throw new Error(`${mapPath}: 声明的模型不存在：${modelName}`);
  const version = map.version || map.modelVersion || `V${maps[0].match[1]}`;
  const mappings = Array.isArray(map.assets)
    ? map.assets.map((asset) => ({ code: asset.asset_id, names: asset.meshNames || [] }))
    : Object.entries(map.assets || {}).map(([code, names]) => ({ code, names: Array.isArray(names) ? names : [] }));
  return { map, mapPath, mappings, modelName, modelPath, version };
}

const runtime = parseGlb(runtimePath);
const formalDelivery = latestFormalDelivery();
const formalModel = parseGlb(formalDelivery.modelPath);
const contract = currentAssetContract();
const readme = readFileSync(modelReadmePath, 'utf8');
const failures = [];

if (runtime.bytes > maxRuntimeBytes) failures.push(`运行时模型 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB 超过 32MB 浏览器发布上限`);
const missingRuntimeNodes = contract.filter((asset) => !runtime.nodes.has(asset.mesh));
if (missingRuntimeNodes.length) failures.push(`运行时模型缺少资产节点：${missingRuntimeNodes.map((asset) => `${asset.code}=${asset.mesh}`).join('、')}`);

const formalMappedNodes = formalDelivery.mappings.flatMap((mapping) => mapping.names);
const missingFormalMapNodes = formalMappedNodes.filter((name) => !formalModel.nodes.has(name));
if (missingFormalMapNodes.length) failures.push(`${formalDelivery.version} 映射引用了模型中不存在的节点：${missingFormalMapNodes.join('、')}`);
if (!readme.includes(formalDelivery.modelName) || !readme.includes(basename(formalDelivery.mapPath))) {
  failures.push(`README 未声明当前正式交付 ${formalDelivery.version} 的模型与资产映射`);
}
const validation = formalDelivery.map.runtimeValidation;
if (validation) {
  if (validation.glbNodes !== formalModel.nodeCount) failures.push(`${formalDelivery.version} 映射记录的节点总数与 GLB 不一致`);
  if (validation.requiredNodes !== formalDelivery.mappings.length) failures.push(`${formalDelivery.version} 映射记录的必需节点数与资产条目不一致`);
  if (validation.missingRequiredNodes !== 0) failures.push(`${formalDelivery.version} 映射仍报告缺失必需节点`);
}

const formalMappingsByCode = new Map(formalDelivery.mappings.map((mapping) => [mapping.code, mapping.names]));
const missingRuntimeContractMappings = contract.filter((asset) => {
  const names = formalMappingsByCode.get(asset.code) || [];
  return !names.some((name) => formalModel.nodes.has(name));
});
const formalReady = formalModel.bytes <= maxRuntimeBytes && missingRuntimeContractMappings.length === 0;
if (!formalReady) {
  if (!/完成模型压缩、资产映射切换和浏览器加载回归/.test(readme)) failures.push(`${formalDelivery.version} 尚未满足 Web 运行条件，但 README 未披露压缩、映射和回归门禁`);
  if (runtime.digest === formalModel.digest) failures.push(`未就绪的 ${formalDelivery.version} 不得覆盖当前受控运行时模型`);
}

if (failures.length) {
  console.error('三维模型交付检查失败：');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`三维模型交付检查通过：运行时 ${(runtime.bytes / 1024 / 1024).toFixed(1)}MB，${contract.length}/${contract.length} 个资产节点可定位。`);
console.log(`当前正式工程模型：${formalDelivery.version}，${(formalModel.bytes / 1024 / 1024).toFixed(1)}MB，${formalModel.nodeCount} 个 GLB 节点，${formalDelivery.mappings.length} 条资产映射。`);
if (formalReady) console.log(`${formalDelivery.version} 已满足浏览器运行时替换条件。`);
else console.log(`${formalDelivery.version} 暂不替换 Web 运行模型：当前 13 资产契约仍有 ${missingRuntimeContractMappings.length} 条未完成映射兼容。`);
