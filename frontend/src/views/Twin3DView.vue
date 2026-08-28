<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import TwinScene from '../components/TwinScene.vue';
import { useOperationsStore } from '../stores/operations';
import { resolveTwinVisualState, twinModelUrl, twinStateLabel, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const route = useRoute();
const requestedCode = typeof route.query.asset === 'string' ? route.query.asset : '';
const selectedCode = ref(store.assets.some((asset) => asset.code === requestedCode) ? requestedCode : store.alerts.find((alert) => !['resolved', 'closed'].includes(alert.status))?.assetCode || store.assets[0]?.code || null);
const scene = ref<InstanceType<typeof TwinScene>>();
const query = ref('');
const stateFilter = ref<'all' | TwinVisualState>('all');
const selectedAsset = computed(() => store.assets.find((asset) => asset.code === selectedCode.value) || null);
const selectedAlerts = computed(() => selectedAsset.value ? store.alerts.filter((alert) => alert.assetCode === selectedAsset.value?.code) : []);
const selectedOrders = computed(() => selectedAsset.value ? store.workOrders.filter((order) => order.assetCode === selectedAsset.value?.code) : []);
const selectedTelemetry = computed(() => selectedAsset.value ? store.telemetry.find((reading) => reading.assetCode === selectedAsset.value?.code) : null);
const visibleAssets = computed(() => store.assets.filter((asset) => {
  const matchQuery = !query.value || `${asset.code} ${asset.name} ${asset.zone}`.toLowerCase().includes(query.value.toLowerCase());
  const matchState = stateFilter.value === 'all' || resolveTwinVisualState(asset, store.alerts) === stateFilter.value;
  return matchQuery && matchState;
}));
const counts = computed(() => store.assets.reduce<Record<TwinVisualState, number>>((result, asset) => {
  result[resolveTwinVisualState(asset, store.alerts)] += 1;
  return result;
}, { normal: 0, warning: 0, alarm: 0, unknown: 0 }));

function select(code: string) { selectedCode.value = code; scene.value?.focusAsset(code); }
function resetView() { scene.value?.resetView(); }
async function fullscreen() {
  const target = document.querySelector('.twin-workspace');
  if (!target) return;
  if (document.fullscreenElement) await document.exitFullscreen();
  else await target.requestFullscreen();
}
function statusLabel(state: TwinVisualState) { return twinStateLabel(state); }
function formatTime(value: string | null | undefined) { return value ? new Date(value).toLocaleString('zh-CN') : '暂无上报'; }
watch(() => route.query.asset, (code) => { if (typeof code === 'string' && store.assets.some((asset) => asset.code === code)) select(code); });
</script>

<template>
  <AppShell>
    <section class="twin-title section-title">
      <div><span class="eyebrow light">THREE-DIMENSIONAL DIGITAL TWIN</span><h1>三维孪生中心</h1><p>以真实实体模型定位设备、告警与工单；三维状态与运行数据实时同步。</p></div>
      <div class="twin-title-actions"><span class="twin-live"><i />三维数据联动</span><button class="primary-button compact-button" @click="resetView">⌖ 重置视角</button><button class="outline-button" @click="fullscreen">⛶ 全屏查看</button></div>
    </section>
    <section class="twin-stat-grid" aria-label="三维场景状态统计">
      <button class="twin-stat alarm" :class="{ active: stateFilter === 'alarm' }" @click="stateFilter = stateFilter === 'alarm' ? 'all' : 'alarm'"><span>告警定位</span><strong>{{ counts.alarm }}</strong><small>红色高亮设备</small></button>
      <button class="twin-stat warning" :class="{ active: stateFilter === 'warning' }" @click="stateFilter = stateFilter === 'warning' ? 'all' : 'warning'"><span>需要关注</span><strong>{{ counts.warning }}</strong><small>橙色关注设备</small></button>
      <button class="twin-stat normal" :class="{ active: stateFilter === 'normal' }" @click="stateFilter = stateFilter === 'normal' ? 'all' : 'normal'"><span>稳定运行</span><strong>{{ counts.normal }}</strong><small>绿色在线设备</small></button>
      <button class="twin-stat unknown" :class="{ active: stateFilter === 'unknown' }" @click="stateFilter = stateFilter === 'unknown' ? 'all' : 'unknown'"><span>待核验</span><strong>{{ counts.unknown }}</strong><small>灰蓝待验证设备</small></button>
    </section>
    <section class="twin-workspace">
      <article class="twin-stage-panel">
        <TwinScene ref="scene" :assets="store.assets" :alerts="store.alerts" :selected-code="selectedCode" @select="select" />
        <div class="twin-stage-footer"><div><span>模型地址</span><code>{{ twinModelUrl }}</code></div><div><span>绑定规则</span><b>Blender 对象名 = 资产 Mesh 编码</b></div><div class="twin-legend"><span class="alarm"><i />告警</span><span class="warning"><i />关注</span><span class="normal"><i />正常</span><span class="unknown"><i />待核验</span></div></div>
      </article>
      <aside class="twin-inspector" aria-live="polite">
        <template v-if="selectedAsset">
          <header><div><span class="eyebrow">SELECTED EQUIPMENT</span><h2>{{ selectedAsset.name }}</h2><code>{{ selectedAsset.code }}</code></div><span :class="['twin-state-chip', resolveTwinVisualState(selectedAsset, store.alerts)]">{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span></header>
          <div class="twin-inspector-grid"><div><span>所在区域</span><b>{{ selectedAsset.zone }}</b></div><div><span>实体模型</span><b>{{ selectedAsset.mesh || '待绑定' }}</b></div><div><span>最新上报</span><b>{{ formatTime(selectedAsset.lastSeenAt) }}</b></div><div><span>当前遥测</span><b>{{ selectedTelemetry ? `${selectedTelemetry.value} ${selectedTelemetry.unit}` : '暂无数据' }}</b></div></div>
          <section class="twin-detail-section"><span class="eyebrow">CURRENT ALERTS</span><p v-if="selectedAlerts.length" class="twin-alert-summary"><b>{{ selectedAlerts.length }} 项关联告警</b>{{ selectedAlerts[0].title }}</p><p v-else class="twin-empty">当前设备没有未关闭告警。</p></section>
          <section class="twin-detail-section"><span class="eyebrow">WORK ORDER STATUS</span><p v-if="selectedOrders.length" class="twin-order-summary"><b>{{ selectedOrders[0].code }}</b>{{ selectedOrders[0].title }}</p><p v-else class="twin-empty">当前设备没有关联工单。</p></section>
          <p class="twin-install-note">{{ selectedAsset.installationNote }}</p>
        </template>
        <div v-else class="twin-empty-inspector">从三维场景或设备列表中选择一个设备。</div>
      </aside>
    </section>
    <section class="twin-asset-panel">
      <header><div><span class="eyebrow">EQUIPMENT LOCATOR</span><h2>三维设备定位</h2></div><label class="twin-search">⌕<input v-model="query" aria-label="搜索三维设备" placeholder="搜索设备编码、名称或区域" /></label></header>
      <div class="twin-asset-list"><button v-for="asset in visibleAssets" :key="asset.id" :class="['twin-asset-item', resolveTwinVisualState(asset, store.alerts), { selected: asset.code === selectedCode }]" @click="select(asset.code)"><i /><span><b>{{ asset.code }}</b><small>{{ asset.name }} · {{ asset.zone }}</small></span><em>{{ statusLabel(resolveTwinVisualState(asset, store.alerts)) }}</em></button><p v-if="!visibleAssets.length" class="twin-empty">没有符合当前条件的设备。</p></div>
    </section>
  </AppShell>
</template>

<style src="../assets/twin3d.css" />
