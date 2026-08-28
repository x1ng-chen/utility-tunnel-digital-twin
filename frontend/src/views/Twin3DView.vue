<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import TwinScene from '../components/TwinScene.vue';
import { useOperationsStore } from '../stores/operations';
import { resolveTwinVisualState, twinStateLabel, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const route = useRoute();
const requestedCode = typeof route.query.asset === 'string' ? route.query.asset : '';
const selectedCode = ref(store.assets.some((asset) => asset.code === requestedCode) ? requestedCode : store.alerts.find((alert) => !['resolved', 'closed'].includes(alert.status))?.assetCode || store.assets[0]?.code || null);
const scene = ref<InstanceType<typeof TwinScene>>();
const query = ref('');
const selectedAsset = computed(() => store.assets.find((asset) => asset.code === selectedCode.value) || null);
const selectedAlerts = computed(() => selectedAsset.value ? store.alerts.filter((alert) => alert.assetCode === selectedAsset.value?.code) : []);
const selectedOrders = computed(() => selectedAsset.value ? store.workOrders.filter((order) => order.assetCode === selectedAsset.value?.code) : []);
const selectedTelemetry = computed(() => selectedAsset.value ? store.telemetry.find((reading) => reading.assetCode === selectedAsset.value?.code) : null);
const visibleAssets = computed(() => store.assets.filter((asset) => !query.value || `${asset.code} ${asset.name} ${asset.zone}`.toLowerCase().includes(query.value.toLowerCase())));
const selectedAssetName = computed(() => selectedAsset.value?.name.replace(/\s*[（(][^（）()]{1,16}[）)]\s*$/, '') || '');

function select(code: string) { selectedCode.value = code; scene.value?.focusAsset(code); }
function resetView() { scene.value?.resetView(); }
async function fullscreen() {
  const target = document.querySelector('.twin-stage-panel');
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
    <section class="twin-workspace">
      <article class="twin-stage-panel">
        <TwinScene ref="scene" :assets="store.assets" :alerts="store.alerts" :selected-code="selectedCode" @select="select" />
        <div v-if="selectedAsset" class="twin-focus-status" aria-live="polite"><span :class="resolveTwinVisualState(selectedAsset, store.alerts)"><i />{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span><b :title="selectedAsset.name">{{ selectedAssetName }}</b><small>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</small></div>
        <div class="twin-quick-switch" aria-label="场景内设备切换"><button v-for="asset in visibleAssets" :key="asset.id" :class="[resolveTwinVisualState(asset, store.alerts), { selected: asset.code === selectedCode }]" @click="select(asset.code)"><i />{{ asset.code }}</button></div>
      </article>
      <aside class="twin-inspector" aria-live="polite">
        <template v-if="selectedAsset">
          <header><div><span class="eyebrow">SELECTED EQUIPMENT</span><h2 :title="selectedAsset.name">{{ selectedAssetName }}</h2><code>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</code></div><span :class="['twin-state-chip', resolveTwinVisualState(selectedAsset, store.alerts)]">{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span></header>
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
<style src="../assets/operational-layout-polish.css" />
