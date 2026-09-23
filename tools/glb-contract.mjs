import { createHash } from 'node:crypto';

export function inspectGlb(data) {
  if (data.toString('utf8', 0, 80).startsWith('version https://git-lfs.github.com/spec/v1')) throw new Error('LFS 对象尚未下载');
  if (data.length < 20 || data.toString('ascii', 0, 4) !== 'glTF' || data.readUInt32LE(4) !== 2) throw new Error('无效 GLB 2.0');
  if (data.readUInt32LE(8) !== data.length) throw new Error('文件长度错误');
  let offset = 12;
  let document;
  while (offset < data.length) {
    if (offset + 8 > data.length) throw new Error('数据块头截断');
    const length = data.readUInt32LE(offset);
    const type = data.readUInt32LE(offset + 4);
    if (length % 4 || offset + 8 + length > data.length) throw new Error('数据块长度错误');
    if (offset === 12 && type !== 0x4e4f534a) throw new Error('首块必须为 JSON');
    if (type === 0x4e4f534a) {
      if (document) throw new Error('重复 JSON 块');
      document = JSON.parse(data.toString('utf8', offset + 8, offset + 8 + length).trim());
    }
    offset += length + 8;
  }
  if (document?.asset?.version !== '2.0') throw new Error('缺少 glTF 2.0 声明');
  const all = document.nodes || [];
  const nodes = new Set();
  const geometry = new Set();
  const parent = new Map();
  for (const [index, node] of all.entries()) {
    if (node.name) {
      if (nodes.has(node.name)) throw new Error(`重复节点名称：${node.name}`);
      nodes.add(node.name);
    }
    for (const [key, size] of Object.entries({ matrix: 16, translation: 3, rotation: 4, scale: 3 })) {
      if (node[key] !== undefined && (!Array.isArray(node[key]) || node[key].length !== size || !node[key].every(Number.isFinite))) throw new Error(`无效变换：${node.name}/${key}`);
    }
    if (node.matrix && (node.translation || node.rotation || node.scale)) throw new Error('matrix 与 TRS 不能混用');
    if (node.mesh !== undefined) {
      if (!Number.isInteger(node.mesh) || !document.meshes?.[node.mesh]?.primitives?.length) throw new Error(`无效网格：${node.name}`);
      geometry.add(index);
    }
    for (const child of node.children || []) {
      if (!Number.isInteger(child) || !all[child] || child === index || parent.has(child)) throw new Error('无效节点父子关系');
      parent.set(child, index);
    }
  }
  for (let i = 0; i < all.length; i++) {
    const seen = new Set([i]);
    let cursor = i;
    while (parent.has(cursor)) {
      cursor = parent.get(cursor);
      if (seen.has(cursor)) throw new Error('节点循环引用');
      seen.add(cursor);
    }
  }
  // A group is bindable only if it actually owns descendant geometry.
  const bindable = new Set();
  for (const index of geometry) {
    let cursor = index;
    while (cursor !== undefined) {
      if (all[cursor].name) bindable.add(all[cursor].name);
      cursor = parent.get(cursor);
    }
  }
  return { available: true, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex'), nodeCount: all.length, nodes, bindable, document };
}

export function missingBindings(model, contract) {
  return contract.filter(({ mesh }) => !model.bindable.has(mesh));
}
