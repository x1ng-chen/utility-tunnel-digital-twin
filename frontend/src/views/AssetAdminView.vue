<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import { api } from '../services/api';
import type { TwinModelReadinessResponse } from '../services/twin3d';
import { useOperationsStore } from '../stores/operations';
import type { Asset, AssetMutation, IntegrationStatus, LocationSource, Status } from '../types';

const route = useRoute();
const store = useOperationsStore();
const managedAssets = ref<Asset[]>([]);
const selected = ref<Asset | null>(null);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const success = ref('');
const search = ref('');
const lifecycle = ref<'all' | 'true' | 'false'>('all');
const mappingFilter = ref<'all' | 'attention'>('all');
const readiness = ref<TwinModelReadinessResponse | null>(null);
const capabilitiesText = ref('');
const draft = reactive<AssetMutation>(emptyDraft());

const filteredAssets = computed(() => {
  const term = search.value.trim().toLowerCase();
  return managedAssets.value.filter((asset) => {
    const lifecycleMatch = lifecycle.value === 'all' || String(asset.isActive) === lifecycle.value;
    const mappingMatch = mappingFilter.value === 'all' || mappingStatus(asset.code) !== 'matched';
    return lifecycleMatch && mappingMatch && (!term || [asset.code, asset.hardwareCode, asset.name, asset.zone, asset.mesh].some((value) => String(value || '').toLowerCase().includes(term)));
  });
});
const writable = computed(() => store.source === 'api' && !store.offline);
const mappingProgress = computed(() => {
  const summary = readiness.value?.summary;
  return summary?.activeAssetCount ? Math.round(summary.mappedAssetCount / summary.activeAssetCount * 100) : 0;
});
const selectedMapping = computed(() => selected.value ? readiness.value?.mappings?.find((item) => item.assetCode === selected.value?.code) : null);

onMounted(loadAssets);
watch(() => store.source, loadAssets);

function emptyDraft(): AssetMutation {
  return { code: '', name: '', zone: '', type: '', status: 'unknown', hardwareCode: null, integrationStatus: 'pending_verification', interface: '', capabilities: [], mesh: '', position: { x: 50, y: 50, z: 0 }, latitude: null, longitude: null, locationSource: 'unassigned', installationNote: '', isActive: true };
}

async function loadAssets() {
  error.value = '';
  if (store.source !== 'api') {
    managedAssets.value = [...store.assets];
    focusRequestedAsset();
    return;
  }
  loading.value = true;
  try {
    const assetsResponse = await api.assets({ page: 1, pageSize: 200, isActive: 'all' });
    managedAssets.value = assetsResponse.data.items;
    void refreshReadiness();
    focusRequestedAsset();
  } catch (cause) {
    error.value = errorMessage(cause);
  } finally {
    loading.value = false;
  }
}

function focusRequestedAsset() {
  const code = typeof route.query.focus === 'string' ? route.query.focus : '';
  if (code) {
    const asset = managedAssets.value.find((item) => item.code === code);
    if (asset) edit(asset);
  }
}

function startCreate() {
  selected.value = null;
  Object.assign(draft, emptyDraft());
  capabilitiesText.value = '';
  error.value = '';
  success.value = '';
}

function edit(asset: Asset) {
  selected.value = asset;
  Object.assign(draft, {
    code: asset.code, name: asset.name, zone: asset.zone, type: asset.type, status: asset.status,
    hardwareCode: asset.hardwareCode, integrationStatus: asset.integrationStatus, interface: asset.interface,
    capabilities: [...asset.capabilities], mesh: asset.mesh, position: { ...asset.position },
    latitude: asset.latitude, longitude: asset.longitude, locationSource: asset.locationSource,
    installationNote: asset.installationNote, isActive: asset.isActive,
  });
  capabilitiesText.value = asset.capabilities.join('\n');
  error.value = '';
  success.value = '';
}

function normalizedPayload(): AssetMutation {
  const capabilities = [...new Set(capabilitiesText.value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean))];
  const hasLatitude = draft.latitude !== null && draft.latitude !== undefined && String(draft.latitude) !== '';
  const hasLongitude = draft.longitude !== null && draft.longitude !== undefined && String(draft.longitude) !== '';
  if (hasLatitude !== hasLongitude) throw new Error('GIS 纬度和经度必须同时填写。');
  if (!draft.code.trim() || !draft.name.trim() || !draft.zone.trim() || !draft.type.trim()) throw new Error('资产编码、名称、区域和类型均为必填项。');
  if (draft.locationSource === 'unassigned' && hasLatitude) throw new Error('已填写 GIS 坐标时，位置来源不能为“未配置”。');
  return {
    ...draft,
    code: draft.code.trim().toUpperCase(), name: draft.name.trim(), zone: draft.zone.trim(), type: draft.type.trim(),
    hardwareCode: draft.hardwareCode?.trim().toUpperCase() || null, interface: draft.interface.trim(), mesh: draft.mesh.trim(),
    installationNote: draft.installationNote.trim(), capabilities,
    latitude: hasLatitude ? Number(draft.latitude) : null, longitude: hasLongitude ? Number(draft.longitude) : null,
    position: { x: Number(draft.position.x), y: Number(draft.position.y), z: Number(draft.position.z || 0) },
  };
}

async function save() {
  error.value = '';
  success.value = '';
  saving.value = true;
  try {
    const payload = normalizedPayload();
    if (selected.value) {
      const updated = await store.updateAsset(selected.value, payload);
      Object.assign(selected.value, updated);
      edit(selected.value);
      success.value = `${updated.code} 已保存，当前版本 v${updated.version}。`;
    } else {
      const created = await store.createAsset(payload);
      managedAssets.value.unshift(created);
      edit(created);
      success.value = `${created.code} 已创建。`;
    }
    if (store.source === 'api') void refreshReadiness();
  } catch (cause) {
    const message = errorMessage(cause);
    if (selected.value && responseStatus(cause) === 409) {
      const selectedCode = selected.value.code;
      await loadAssets();
      const fresh = managedAssets.value.find((item) => item.code === selectedCode);
      if (fresh) edit(fresh);
    }
    error.value = message;
  } finally {
    saving.value = false;
  }
}

async function refreshReadiness() {
  try {
    readiness.value = (await api.twinModelReadiness()).data as TwinModelReadinessResponse;
  } catch {
    // Mapping health is supplementary governance information. A temporary
    // failure must never block the primary asset directory or a completed save.
    readiness.value = null;
  }
}

function mappingStatus(code: string) {
  return readiness.value?.mappings?.find((item) => item.assetCode === code)?.status ?? 'unverified';
}

function mappingLabel(status: ReturnType<typeof mappingStatus>) {
  return ({ matched: '模型已匹配', missing: '尚未配置', invalid: '命名不规范', not_in_model: '模型中未找到', unverified: '等待模型核验' })[status];
}

function suggestMeshName() {
  const code = draft.code.trim().toUpperCase();
  if (!code) {
    error.value = '请先填写资产编码，再生成模型节点名称。';
    return;
  }
  draft.mesh = `MESH_${code.replaceAll('-', '_')}`;
  error.value = '';
}

function errorMessage(cause: unknown): string {
  if (cause instanceof Error && !('response' in cause)) return cause.message;
  if (typeof cause === 'object' && cause && 'response' in cause) {
    const response = (cause as { response?: { data?: { message?: string; details?: Record<string, string[] | string> } } }).response;
    const details = response?.data?.details;
    if (details) return Object.entries(details).map(([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join('、') : messages}`).join('；');
    return response?.data?.message || '资产保存失败，请稍后重试。';
  }
  return '资产保存失败，请稍后重试。';
}

function responseStatus(cause: unknown): number | null {
  if (typeof cause !== 'object' || !cause || !('response' in cause)) return null;
  const status = (cause as { response?: { status?: unknown } }).response?.status;
  return typeof status === 'number' ? status : null;
}

const statuses: Array<{ value: Status; label: string }> = [{ value: 'normal', label: '正常' }, { value: 'warning', label: '关注' }, { value: 'alarm', label: '告警' }, { value: 'offline', label: '离线' }, { value: 'unknown', label: '未知' }];
const integrations: Array<{ value: IntegrationStatus; label: string }> = [{ value: 'verified', label: '已验证' }, { value: 'firmware_connected', label: '固件已接入' }, { value: 'calibration_required', label: '待标定' }, { value: 'pending_verification', label: '待验证' }, { value: 'optional', label: '可选模块' }, { value: 'non_operational', label: '非运行资产' }];
const locations: Array<{ value: LocationSource; label: string }> = [{ value: 'unassigned', label: '未配置' }, { value: 'demo_anchor', label: '演示锚点' }, { value: 'configured', label: '人工配置' }, { value: 'surveyed', label: '测绘坐标' }, { value: 'gps', label: 'GPS 定位' }];
</script>

<template>
  <AppShell>
    <section class="section-title asset-admin-title"><div><span class="eyebrow light">设备资料维护</span><h1>资产主数据</h1><p>集中维护设备身份、数字孪生坐标与生命周期；所有变更均进行权限校验并记录审计日志。</p></div><button class="primary-button" :disabled="!writable" @click="startCreate">＋ 新建资产</button></section>
    <div v-if="!writable" class="asset-readonly" role="status"><b>当前为只读模式</b><span>{{ store.source !== 'api' ? '请使用企业 API 登录后维护主数据；演示数据不会被写入数据库。' : 'API 已离线，恢复连接后方可修改。' }}</span></div>
    <p v-if="error" class="inline-message error-message" role="alert">{{ error }}</p><p v-if="success" class="inline-message success-message" role="status">{{ success }}</p>
    <section class="mapping-overview" aria-label="三维模型映射概况">
      <div><span>设备节点配置</span><b>{{ readiness?.summary.mappedAssetCount ?? 0 }} / {{ readiness?.summary.activeAssetCount ?? 0 }}</b><small>已按规范填写模型设备节点</small></div>
      <div><span>节点配置率</span><b>{{ mappingProgress }}%</b><small>{{ readiness?.status === 'ready' ? '当前模型可用于正式孪生' : '仍有设备需要处理' }}</small></div>
      <div><span>当前模型版本</span><b>{{ readiness?.activeRelease?.version || '尚未启用' }}</b><small>{{ readiness?.contract.modelNodeInventoryAvailable ? '节点清单已校验' : '等待新版模型校验' }}</small></div>
    </section>
    <section class="asset-admin-grid">
      <article class="asset-directory panel"><div class="asset-toolbar"><input v-model="search" placeholder="搜索设备或模型节点" /><select v-model="lifecycle"><option value="all">全部生命周期</option><option value="true">在用</option><option value="false">已停用</option></select><select v-model="mappingFilter" class="mapping-filter"><option value="all">全部映射状态</option><option value="attention">只看待处理映射</option></select></div><div class="asset-count"><span>资产目录</span><b>{{ filteredAssets.length }}</b></div><div v-if="loading" class="empty-state">正在加载资产主数据…</div><button v-for="asset in filteredAssets" v-else :key="asset.id" :class="['asset-directory-item', { active: selected?.id === asset.id, inactive: !asset.isActive }]" @click="edit(asset)"><span :class="['asset-state-dot', asset.status]" /><div><b>{{ asset.code }}</b><small>{{ asset.hardwareCode || '无硬件编号' }} · {{ asset.name }}</small><small v-if="asset.isActive" :class="['mapping-state', mappingStatus(asset.code)]">{{ mappingLabel(mappingStatus(asset.code)) }}</small></div><em>{{ asset.isActive ? `v${asset.version}` : '已停用' }}</em></button><div v-if="!loading && !filteredAssets.length" class="empty-state">没有符合条件的资产。</div></article>
      <form class="asset-editor panel" @submit.prevent="save"><div class="editor-head"><div><span class="eyebrow">{{ selected ? 'EDIT ASSET' : 'CREATE ASSET' }}</span><h2>{{ selected ? selected.code : '新建资产' }}</h2></div><span v-if="selected" class="version-chip">乐观锁 v{{ selected.version }}</span></div>
        <div class="form-section"><h3>资产身份</h3><div class="asset-form-grid"><label>资产编码<input v-model="draft.code" required maxlength="40" :disabled="!!selected" placeholder="例如 ENV-02" /></label><label>硬件编号<input v-model="draft.hardwareCode" maxlength="16" placeholder="例如 H-12" /></label><label>资产名称<input v-model="draft.name" required maxlength="120" /></label><label>所属区域<input v-model="draft.zone" required maxlength="60" /></label><label>资产类型<input v-model="draft.type" required maxlength="60" /></label><label>运行状态<select v-model="draft.status"><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>接入状态<select v-model="draft.integrationStatus"><option v-for="item in integrations" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>接口说明<input v-model="draft.interface" maxlength="160" /></label><label class="span-two">能力标签<textarea v-model="capabilitiesText" rows="2" placeholder="每行或逗号分隔，重复项会自动合并" /></label></div></div>
        <div class="form-section"><div class="section-heading"><h3>三维孪生与地理位置</h3><span v-if="selected?.isActive && selectedMapping" :class="['mapping-pill', selectedMapping.status]">{{ mappingLabel(selectedMapping.status) }}</span></div><div class="asset-form-grid"><label class="span-two">模型设备节点<div class="mesh-input-row"><input v-model="draft.mesh" maxlength="80" placeholder="例如 MESH_ENV_01" spellcheck="false" /><button type="button" class="compact-button" @click="suggestMeshName">按设备编码生成</button></div><small class="field-help">与 Blender 中对应设备的对象名称保持一致；仅使用大写字母、数字、短横线和下划线。</small></label><label>位置来源<select v-model="draft.locationSource"><option v-for="item in locations" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><span /><label>平面 X（0–100）<input v-model.number="draft.position.x" type="number" min="0" max="100" step="0.1" required /></label><label>平面 Y（0–100）<input v-model.number="draft.position.y" type="number" min="0" max="100" step="0.1" required /></label><label>高程 Z<input v-model.number="draft.position.z" type="number" min="-1000" max="1000" step="0.1" required /></label><span /><label>纬度<input v-model="draft.latitude" type="number" min="-90" max="90" step="0.000001" placeholder="留空表示未定位" /></label><label>经度<input v-model="draft.longitude" type="number" min="-180" max="180" step="0.000001" placeholder="留空表示未定位" /></label><label class="span-two">安装备注<textarea v-model="draft.installationNote" rows="3" maxlength="1000" /></label></div></div>
        <div class="asset-lifecycle"><label><input v-model="draft.isActive" type="checkbox" />资产处于在用状态</label><small>停用前，系统会检查该资产是否仍有关联的活动告警或未结束工单。</small></div>
        <div class="editor-actions"><button type="button" class="compact-button" @click="startCreate">清空</button><button class="primary-button" type="submit" :disabled="!writable || saving">{{ saving ? '正在保存…' : selected ? '保存变更' : '创建资产' }}</button></div>
      </form>
    </section>
  </AppShell>
</template>

<style src="../assets/asset-admin.css"></style>
