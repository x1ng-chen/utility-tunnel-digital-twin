<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
import type { Asset } from '../types';
import '../assets/asset-twin.css';

const store = useOperationsStore();
const route = useRoute();
const search = ref('');
const selectedCode = ref<string>((route.query.focus as string) || '');

const visible = computed(() => store.assets.filter((item) => `${item.code} ${item.name} ${item.zone} ${item.type}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const selectedAsset = computed(() => visible.value.find((item) => item.code === selectedCode.value) || visible.value[0] || null);
const selectedAlerts = computed(() => selectedAsset.value ? store.alerts.filter((item) => item.assetCode === selectedAsset.value?.code) : []);
const selectedOrders = computed(() => selectedAsset.value ? store.workOrders.filter((item) => item.assetCode === selectedAsset.value?.code) : []);
const selectedTelemetry = computed(() => selectedAsset.value ? store.telemetry.find((item) => item.assetCode === selectedAsset.value?.code) || (store.dashboard.telemetry?.assetCode === selectedAsset.value.code ? store.dashboard.telemetry : null) : null);

watch(visible, (items) => {
  if (!items.some((item) => item.code === selectedCode.value)) selectedCode.value = items[0]?.code || '';
}, { immediate: true });

function selectAsset(asset: Asset) { selectedCode.value = asset.code; }

function positionStyle(asset: Asset) {
  const x = Math.min(95, Math.max(5, Number(asset.position?.x) || 50));
  const y = Math.min(88, Math.max(12, Number(asset.position?.y) || 50));
  return { left: `${x}%`, top: `${y}%` };
}

function statusLabel(status: Asset['status']) {
  return { normal: '正常', warning: '关注', alarm: '告警', offline: '离线', unknown: '未知' }[status];
}

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '暂无记录';
}
</script>

<template>
  <AppShell>
    <section class="section-title">
      <div><span class="eyebrow light">ASSET REGISTER / DIGITAL TWIN</span><h1>设备台账</h1><p>设备位置、健康状态与孪生模型统一维护，点击节点查看实时关联数据。</p></div>
      <input v-model="search" class="search-input" placeholder="搜索设备编码、名称或区域" aria-label="搜索设备" />
    </section>

    <section class="asset-workspace">
      <div class="asset-twin-panel">
        <header class="panel-head"><div><span class="eyebrow">SPATIAL MODEL</span><h2>管廊设备孪生视图</h2></div><span class="config-source"><i />{{ visible.length }} 个可定位节点</span></header>
        <div class="asset-map" role="list" aria-label="设备空间定位图">
          <div class="asset-map-grid" /><div class="asset-map-route route-a" /><div class="asset-map-route route-b" />
          <button v-for="asset in visible" :key="asset.id" class="asset-map-node" :class="[asset.status, { selected: selectedAsset?.code === asset.code }]" :style="positionStyle(asset)" :aria-label="`定位 ${asset.name}`" @click="selectAsset(asset)"><i /><span>{{ asset.code }}</span></button>
          <div class="asset-map-legend"><span><i class="normal" />正常</span><span><i class="warning" />关注</span><span><i class="alarm" />异常</span></div>
        </div>
      </div>

      <aside v-if="selectedAsset" class="asset-detail-panel" aria-live="polite">
        <div class="detail-heading"><div><span class="eyebrow">SELECTED NODE</span><h2>{{ selectedAsset.name }}</h2><b>{{ selectedAsset.code }}</b></div><span :class="['asset-status', selectedAsset.status]">{{ statusLabel(selectedAsset.status) }}</span></div>
        <div class="detail-grid"><div><small>区域</small><strong>{{ selectedAsset.zone }}</strong></div><div><small>模型</small><strong>{{ selectedAsset.mesh || '未配置' }}</strong></div><div><small>坐标</small><strong>{{ selectedAsset.position?.x ?? '-' }}, {{ selectedAsset.position?.y ?? '-' }}</strong></div><div><small>最近上报</small><strong>{{ formatTime(selectedAsset.lastSeenAt) }}</strong></div></div>
        <div class="detail-block"><span class="eyebrow">TELEMETRY</span><div v-if="selectedTelemetry" class="detail-reading"><strong>{{ selectedTelemetry.value }}</strong><span>{{ selectedTelemetry.unit }}</span><small>{{ selectedTelemetry.metric }} · {{ selectedTelemetry.quality }}</small></div><p v-else class="detail-empty">暂无遥测数据</p></div>
        <div class="detail-block"><span class="eyebrow">LINKED EVENTS</span><p v-if="selectedAlerts.length" class="detail-list">{{ selectedAlerts.length }} 条告警 · {{ selectedAlerts.filter((item) => ['open', 'acknowledged'].includes(item.status)).length }} 条待处置</p><p v-else class="detail-empty">暂无告警</p><p v-if="selectedOrders.length" class="detail-list">{{ selectedOrders.length }} 个关联工单</p><p v-else class="detail-empty">暂无关联工单</p></div>
      </aside>
      <div v-else class="asset-detail-panel empty-state">没有匹配的设备节点，请调整搜索条件。</div>
    </section>

    <section class="asset-grid">
      <button v-for="asset in visible" :key="asset.id" class="asset-card asset-card-button" :class="{ selected: selectedAsset?.code === asset.code }" @click="selectAsset(asset)"><div class="asset-icon" :class="asset.status">◈</div><div class="asset-card-copy"><span class="eyebrow">{{ asset.zone }}</span><h2>{{ asset.name }}</h2><b>{{ asset.code }}</b><p>{{ asset.type }} · {{ asset.mesh || '未配置模型' }}</p></div><span :class="['asset-status', asset.status]">{{ statusLabel(asset.status) }}</span></button>
    </section>
  </AppShell>
</template>
