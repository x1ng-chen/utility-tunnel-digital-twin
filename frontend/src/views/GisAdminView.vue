<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
import type { HardwareProtocol } from '../types';
import '../assets/gis.css';
import '../assets/gis-admin.css';

const store = useOperationsStore();
const importText = ref(JSON.stringify({
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    geometry: { type: 'LineString', coordinates: [[121.473700, 31.230400], [121.473900, 31.230500]] },
    properties: { code: 'SEG-01', name: 'A 区管廊段', layerType: 'tunnel_segment', source: 'surveyed', sourceReference: '测绘成果编号', accuracyM: '0.250', status: 'draft' },
  }],
}, null, 2));
const importError = ref('');
const importSuccess = ref('');
const bindingError = ref('');
const bindingSuccess = ref('');
const reviewError = ref('');
const reviewSuccess = ref('');
const bindingAssetCode = ref('');
const bindingProtocol = ref<HardwareProtocol>('mqtt');
const deviceIdentifier = ref('');
const endpoint = ref('');
const expectedIntervalSeconds = ref(60);
const unboundAssets = computed(() => store.assets.filter((asset) => !store.hardwareBindings.some((binding) => binding.assetCode === asset.code)));
const drafts = computed(() => store.spatialFeatures.filter((feature) => feature.status === 'draft'));

async function importFeatures() {
  importError.value = ''; importSuccess.value = '';
  try {
    const payload = JSON.parse(importText.value) as Record<string, unknown>;
    const result = await store.importGisFeatures(payload);
    importSuccess.value = `已建立 ${result.meta.created} 个空间对象草稿。请在审核后将状态更新为 published。`;
  } catch (cause) {
    importError.value = cause instanceof Error ? cause.message : 'GeoJSON 导入失败。';
  }
}

async function createBinding() {
  bindingError.value = ''; bindingSuccess.value = '';
  try {
    const binding = await store.createHardwareBinding({ assetCode: bindingAssetCode.value, protocol: bindingProtocol.value, deviceIdentifier: deviceIdentifier.value, endpoint: endpoint.value, expectedIntervalSeconds: expectedIntervalSeconds.value, status: 'reserved' });
    bindingSuccess.value = `${binding.assetCode} 已预留 ${binding.protocol.toUpperCase()} 接口；未收到真实心跳前不会显示在线。`;
    bindingAssetCode.value = ''; deviceIdentifier.value = ''; endpoint.value = '';
  } catch (cause) {
    bindingError.value = cause instanceof Error ? cause.message : '硬件接口预留失败。';
  }
}

async function publishFeature(featureId: number) {
  reviewError.value = ''; reviewSuccess.value = '';
  const feature = store.spatialFeatures.find((item) => item.id === featureId);
  if (!feature) return;
  try {
    await store.updateGisFeature(feature, { status: 'published', verifiedAt: new Date().toISOString() });
    reviewSuccess.value = `${feature.code} 已通过审核并发布到运维地图。`;
  } catch (cause) {
    reviewError.value = cause instanceof Error ? cause.message : '空间对象审核发布失败。';
  }
}
</script>

<template>
  <AppShell>
    <section class="section-title gis-admin-title">
      <div><span class="eyebrow light">GIS GOVERNANCE CONSOLE</span><h1>空间数据管理</h1><p>导入、审核和发布真实 WGS84 空间数据；此页面不建立硬件连接，只登记受控通信契约。</p></div>
      <div class="gis-title-meta"><span class="insight-source">ADMIN ONLY</span><small>受控发布 · 审计留痕</small></div>
    </section>

    <section class="gis-governance-overview" aria-label="空间数据治理概览">
      <article><span>空间对象</span><strong>{{ store.spatialFeatures.length }}</strong><small>含草稿与已发布对象</small></article>
      <article><span>待审核</span><strong>{{ drafts.length }}</strong><small>发布前需要管理员复核</small></article>
      <article><span>接口契约</span><strong>{{ store.hardwareBindings.length }}</strong><small>仅登记，不代表设备在线</small></article>
    </section>

    <section class="gis-admin-grid">
      <article class="panel gis-import-panel">
        <div class="panel-head"><div><span class="eyebrow">GEOJSON IMPORT</span><h2>导入真实空间数据</h2></div><span class="panel-limit">1–100 个对象 / 次</span></div>
        <div class="gis-panel-body"><p class="panel-description">仅接受 <b>EPSG:4326 / WGS84</b> 的 Point、LineString、Polygon。导入后先保留草稿，补全测绘或 CAD 来源，审核后再发布到运维地图。</p>
        <label class="gis-textarea-label"><span>GeoJSON 内容</span><textarea v-model="importText" aria-label="GeoJSON 导入内容" spellcheck="false" /></label>
        <p v-if="importError" class="inline-message error-message" role="alert">{{ importError }}</p>
        <p v-if="importSuccess" class="inline-message success-message">{{ importSuccess }}</p>
        <div class="gis-panel-actions"><small>导入操作会生成版本记录，草稿不会直接出现在运行地图。</small><button class="primary-button" type="button" @click="importFeatures">校验并导入空间对象 <span>→</span></button></div></div>
      </article>

      <article class="panel gis-binding-panel">
        <div class="panel-head"><div><span class="eyebrow">HARDWARE CONTRACT</span><h2>硬件接口预留</h2></div><span class="panel-limit">{{ store.hardwareBindings.length }} 条契约</span></div>
        <div class="gis-panel-body"><p class="panel-description">通信主题、设备标识和期望心跳独立于地图坐标管理。登记后仍为“接口已预留”，不会制造已连接状态。</p>
        <form class="gis-binding-form" @submit.prevent="createBinding">
          <div class="gis-form-grid"><label class="span-two">未绑定资产<select v-model="bindingAssetCode" required><option value="" disabled>请选择资产</option><option v-for="asset in unboundAssets" :key="asset.id" :value="asset.code">{{ asset.code }} · {{ asset.name }}</option></select></label>
          <label>协议<select v-model="bindingProtocol"><option value="mqtt">MQTT</option><option value="http">HTTP</option><option value="serial">串口网关</option><option value="manual">人工登记</option></select></label>
          <label>期望心跳（秒）<input v-model.number="expectedIntervalSeconds" required type="number" min="1" max="86400" /></label>
          <label>设备标识<input v-model.trim="deviceIdentifier" required maxlength="80" placeholder="例如 gateway-ctrl-01" /></label>
          <label>接口地址 / 主题<input v-model.trim="endpoint" required maxlength="200" placeholder="例如 ut/v1/ctrl-01/telemetry" /></label></div>
          <p v-if="!unboundAssets.length" class="inline-message">所有当前资产均已有“接口已预留”契约；真实网关接入后可通过后端版本化更新状态。</p>
          <p v-if="bindingError" class="inline-message error-message" role="alert">{{ bindingError }}</p>
          <p v-if="bindingSuccess" class="inline-message success-message">{{ bindingSuccess }}</p>
          <div class="gis-panel-actions"><small>该操作只创建受控契约，不会连接现场设备。</small><button class="primary-button" :disabled="!unboundAssets.length" type="submit">预留硬件接口 <span>→</span></button></div>
        </form></div>
      </article>
    </section>

    <section class="table-panel gis-review-table">
      <div class="gis-review-heading"><div><span class="eyebrow">REVIEW QUEUE</span><h2>空间对象审核队列</h2></div><span>{{ drafts.length }} 个对象待处理</span></div>
      <div class="table-head"><span>空间对象</span><span>图层 / 来源</span><span>精度</span><span>审核状态</span><span>版本 / 操作</span></div>
      <div v-for="feature in drafts" :key="feature.id" class="table-row"><div><strong>{{ feature.name }}</strong><small>{{ feature.code }}</small></div><span>{{ feature.layerType }} · {{ feature.source }}</span><span>{{ feature.accuracyM ?? '未登记' }} m</span><b class="badge quality-suspect">待审核</b><span><code>v{{ feature.version }}</code><button type="button" class="text-button" @click="publishFeature(feature.id)">审核并发布</button></span></div>
      <div v-if="!drafts.length" class="empty-state">当前没有待审核空间对象。导入真实测绘或 CAD/GIS 转换成果后将在此处出现。</div>
      <p v-if="reviewError" class="inline-message error-message" role="alert">{{ reviewError }}</p>
      <p v-if="reviewSuccess" class="inline-message success-message">{{ reviewSuccess }}</p>
    </section>
  </AppShell>
</template>
