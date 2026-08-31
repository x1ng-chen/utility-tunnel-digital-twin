<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import TwinScene from '../components/TwinScene.vue';
import { useOperationsStore } from '../stores/operations';
import { api } from '../services/api';
import { activeTwinAlerts, primaryTwinAlert, resolveTwinVisualState, summarizeTwinModelDelivery, twinStateLabel, type TwinModelBindingReport, type TwinModelReadinessResponse, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const route = useRoute();
const router = useRouter();
const stage = ref<HTMLElement>();
const requestedCode = typeof route.query.asset === 'string' ? route.query.asset : '';
const selectedCode = ref(store.assets.some((asset) => asset.code === requestedCode) ? requestedCode : store.alerts.find((alert) => !['resolved', 'closed'].includes(alert.status))?.assetCode || store.assets[0]?.code || null);
const scene = ref<InstanceType<typeof TwinScene>>();
const query = ref('');
const stateFilter = ref<'all' | TwinVisualState>('all');
const finePointer = ref(false);
const fullscreenActive = ref(false);
const fullscreenPointer = reactive({ x: -80, y: -80, active: false, pressed: false, draggingSwitcher: false });
const fullscreenTrail = ref(Array.from({ length: 8 }, (_, index) => ({ x: -80, y: -80, opacity: 0.42 - index * 0.043, scale: 1 - index * 0.07 })));
const fullscreenPulse = ref<{ key: number; x: number; y: number } | null>(null);
let pendingFullscreenPointer: PointerEvent | undefined;
let fullscreenPointerFrame = 0;
let fullscreenPulseTimer: number | undefined;
const modelReport = ref<TwinModelBindingReport>({ mode: 'fallback', expectedCount: store.assets.length, boundCodes: [], missingCodes: store.assets.map((asset) => asset.code), isComplete: false });
const serverModelReadiness = ref<TwinModelReadinessResponse | null>(null);
const filterOptions: Array<{ value: 'all' | TwinVisualState; label: string }> = [
  { value: 'all', label: '全部' }, { value: 'alarm', label: '告警' }, { value: 'warning', label: '关注' }, { value: 'normal', label: '正常' }, { value: 'unknown', label: '待核验' },
];
const selectedAsset = computed(() => store.assets.find((asset) => asset.code === selectedCode.value) || null);
const selectedAlerts = computed(() => selectedAsset.value ? activeTwinAlerts(selectedAsset.value.code, store.alerts) : []);
const primaryAlert = computed(() => selectedAsset.value ? primaryTwinAlert(selectedAsset.value.code, store.alerts) : null);
const selectedOrders = computed(() => selectedAsset.value ? store.workOrders.filter((order) => order.assetCode === selectedAsset.value?.code) : []);
const selectedTelemetry = computed(() => selectedAsset.value ? store.telemetry.find((reading) => reading.assetCode === selectedAsset.value?.code) : null);
const visibleAssets = computed(() => store.assets.filter((asset) => {
  const matchesQuery = !query.value || `${asset.code} ${asset.name} ${asset.zone}`.toLowerCase().includes(query.value.toLowerCase());
  return matchesQuery && (stateFilter.value === 'all' || resolveTwinVisualState(asset, store.alerts) === stateFilter.value);
}));
const riskAssets = computed(() => store.assets.filter((asset) => ['alarm', 'warning'].includes(resolveTwinVisualState(asset, store.alerts))));
const selectedAssetName = computed(() => selectedAsset.value?.name.replace(/\s*[（(][^（）()]{1,16}[）)]\s*$/, '') || '');
const modelBindingText = computed(() => `${modelReport.value.boundCodes.length} / ${modelReport.value.expectedCount} 个设备已定位`);
const localModelReadiness = computed(() => summarizeTwinModelDelivery(store.assets));
const modelDeliveryReady = computed(() => serverModelReadiness.value ? serverModelReadiness.value.status === 'ready' : localModelReadiness.value.isReady);
const modelDeliveryCount = computed(() => serverModelReadiness.value?.summary.mappedAssetCount ?? localModelReadiness.value.mappedAssetCount);
const modelDeliveryTotal = computed(() => serverModelReadiness.value?.summary.activeAssetCount ?? localModelReadiness.value.activeAssetCount);
const modelDeliveryLabel = computed(() => modelDeliveryReady.value ? '模型节点已就绪' : `待补齐 ${modelDeliveryTotal.value - modelDeliveryCount.value} 个节点`);
const modelDeliveryHint = computed(() => {
  if (!modelDeliveryReady.value) return '资产台账仍缺少标准节点名称，暂不建议交付实体模型。';
  if (modelReport.value.mode === 'fallback') return `已完成 ${modelDeliveryCount.value} 个设备的节点准备；等待实体模型文件后可自动核验。`;
  if (modelReport.value.isComplete) return '实体模型已完成全部设备定位，可直接用于告警可视化。';
  return `实体模型已加载，仍有 ${modelReport.value.missingCodes.length} 个设备待补齐节点名称。`;
});
const navigationContext = computed(() => {
  const source = typeof route.query.source === 'string' ? route.query.source : '';
  const alertCode = typeof route.query.alert === 'string' ? route.query.alert : '';
  if (source === 'alert' && alertCode) return `已从告警 ${alertCode} 定位到当前设备。`;
  if (source === 'gis') return '已从 GIS 地图定位到当前设备。';
  if (source === 'asset') return '已从设备台账定位到当前设备。';
  return '';
});

function select(code: string) { selectedCode.value = code; scene.value?.focusAsset(code); }
function inspectRisk(direction: 1 | -1) {
  const assets = riskAssets.value;
  if (!assets.length) return;
  const current = assets.findIndex((asset) => asset.code === selectedCode.value);
  const next = current < 0 ? (direction > 0 ? 0 : assets.length - 1) : (current + direction + assets.length) % assets.length;
  select(assets[next].code);
}
function openGis() { if (selectedAsset.value) void router.push({ path: '/gis', query: { asset: selectedAsset.value.code, source: 'twin' } }); }
function openAlertCenter() { if (primaryAlert.value) void router.push({ path: '/alerts', query: { focus: primaryAlert.value.code, source: 'twin' } }); }
function resetView() { scene.value?.resetView(); }
function retryModel() { scene.value?.reloadModel(); }
function receiveModelReport(report: TwinModelBindingReport) { modelReport.value = report; }
async function refreshModelReadiness() {
  if (store.source !== 'api' || store.offline) { serverModelReadiness.value = null; return; }
  try { serverModelReadiness.value = (await api.twinModelReadiness()).data as TwinModelReadinessResponse; }
  catch { serverModelReadiness.value = null; }
}
function updateFullscreenState() {
  fullscreenActive.value = document.fullscreenElement === stage.value;
  if (!fullscreenActive.value) {
    fullscreenPointer.active = false;
    fullscreenPointer.pressed = false;
    fullscreenPointer.draggingSwitcher = false;
  }
}
function paintFullscreenPointer() {
  fullscreenPointerFrame = 0;
  const event = pendingFullscreenPointer;
  pendingFullscreenPointer = undefined;
  if (!event || !stage.value || !fullscreenActive.value) return;
  const bounds = stage.value.getBoundingClientRect();
  const x = event.clientX - bounds.left;
  const y = event.clientY - bounds.top;
  fullscreenPointer.x = x;
  fullscreenPointer.y = y;
  fullscreenPointer.active = true;
  fullscreenTrail.value = fullscreenTrail.value.map((point, index, points) => {
    const leader = index === 0 ? { x, y } : points[index - 1];
    const easing = 0.45 - index * 0.028;
    return { ...point, x: point.x + (leader.x - point.x) * easing, y: point.y + (leader.y - point.y) * easing };
  });
}
function onStagePointerMove(event: PointerEvent) {
  if (!fullscreenActive.value || (event.pointerType !== 'mouse' && !finePointer.value)) return;
  // Some desktop/headless Chromium builds report an imprecise media query even
  // when a real mouse pointer is active. Trust the actual pointer event so the
  // fullscreen interaction layer remains usable on those browsers.
  if (event.pointerType === 'mouse') finePointer.value = true;
  pendingFullscreenPointer = event;
  if (!fullscreenPointerFrame) fullscreenPointerFrame = window.requestAnimationFrame(paintFullscreenPointer);
}
function onStagePointerDown(event: PointerEvent) {
  if (!fullscreenActive.value || !stage.value || (event.pointerType !== 'mouse' && !finePointer.value)) return;
  if (event.pointerType === 'mouse') finePointer.value = true;
  const bounds = stage.value.getBoundingClientRect();
  fullscreenPointer.pressed = true;
  fullscreenPulse.value = { key: Date.now(), x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  if (fullscreenPulseTimer) window.clearTimeout(fullscreenPulseTimer);
  fullscreenPulseTimer = window.setTimeout(() => { fullscreenPulse.value = null; }, 700);
}
function onStagePointerUp() {
  fullscreenPointer.pressed = false;
  fullscreenPointer.draggingSwitcher = false;
}
function onStagePointerLeave(event?: PointerEvent) {
  const target = event?.currentTarget;
  if (event && target instanceof HTMLElement && target.hasPointerCapture(event.pointerId)) return;
  fullscreenPointer.active = false;
  fullscreenPointer.draggingSwitcher = false;
}
function onQuickSwitchPointerDown(event: PointerEvent) {
  if (!fullscreenActive.value || (event.pointerType !== 'mouse' && !finePointer.value)) return;
  if (event.pointerType === 'mouse') finePointer.value = true;
  const target = event.currentTarget;
  const origin = event.target;
  const isDeviceControl = origin instanceof Element && Boolean(origin.closest('button'));
  // Capturing a pointer that began on a device button prevents browsers from
  // dispatching its click after the pointer is released. Capture only rail drags.
  if (!isDeviceControl && target instanceof HTMLElement && event.pointerType !== 'touch') target.setPointerCapture(event.pointerId);
  fullscreenPointer.draggingSwitcher = !isDeviceControl;
  onStagePointerMove(event);
  onStagePointerDown(event);
}
function onQuickSwitchPointerMove(event: PointerEvent) {
  // The quick switcher stops bubbling pointer events so WebGL never receives
  // a drag intended for the horizontal device rail. Keep the fullscreen cursor
  // in sync here for both hover and drag, not just after a press.
  onStagePointerMove(event);
}
function onQuickSwitchPointerEnd(event: PointerEvent) {
  const target = event.currentTarget;
  if (target instanceof HTMLElement && target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
  onStagePointerUp();
}
async function fullscreen() {
  const target = stage.value;
  if (!target) return;
  if (document.fullscreenElement) await document.exitFullscreen();
  else await target.requestFullscreen();
}
function statusLabel(state: TwinVisualState) { return twinStateLabel(state); }
function formatTime(value: string | null | undefined) { return value ? new Date(value).toLocaleString('zh-CN') : '暂无上报'; }
watch(() => route.query.asset, (code) => { if (typeof code === 'string' && store.assets.some((asset) => asset.code === code)) select(code); });
watch(() => [store.source, store.offline], () => { void refreshModelReadiness(); });
onMounted(() => {
  finePointer.value = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  document.addEventListener('fullscreenchange', updateFullscreenState);
  void refreshModelReadiness();
});
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', updateFullscreenState);
  if (fullscreenPointerFrame) window.cancelAnimationFrame(fullscreenPointerFrame);
  if (fullscreenPulseTimer) window.clearTimeout(fullscreenPulseTimer);
});
</script>

<template>
  <AppShell>
    <section class="twin-title section-title">
      <div><span class="eyebrow light">THREE-DIMENSIONAL DIGITAL TWIN</span><h1>三维孪生中心</h1><p>以真实实体模型定位设备、告警与工单；三维状态与运行数据实时同步。</p></div>
      <div class="twin-title-actions"><span :class="['twin-live', { blocked: !modelDeliveryReady }]" :title="modelDeliveryHint"><i />{{ modelDeliveryLabel }}</span><button v-if="modelReport.mode === 'fallback'" type="button" class="outline-button twin-model-retry-top" @click="retryModel">↻ 检测模型</button><button class="primary-button compact-button" @click="resetView">⌖ 重置视角</button><button class="outline-button" @click="fullscreen">⛶ 全屏查看</button></div>
    </section>
    <section class="twin-workspace">
      <article ref="stage" :class="['twin-stage-panel', { 'twin-fullscreen-active': fullscreenActive }]" @pointermove="onStagePointerMove" @pointerdown="onStagePointerDown" @pointerup="onStagePointerUp" @pointerleave="onStagePointerLeave">
        <TwinScene ref="scene" :assets="store.assets" :alerts="store.alerts" :selected-code="selectedCode" @select="select" @model-report="receiveModelReport" />
        <div v-if="selectedAsset" class="twin-focus-status" aria-live="polite"><span :class="resolveTwinVisualState(selectedAsset, store.alerts)"><i />{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span><b :title="selectedAsset.name">{{ selectedAssetName }}</b><small>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</small><div v-if="riskAssets.length" class="twin-risk-patrol"><button type="button" aria-label="巡检上一异常设备" @click="inspectRisk(-1)">← 上一异常</button><button type="button" aria-label="巡检下一异常设备" @click="inspectRisk(1)">下一异常 →</button></div></div>
        <nav class="twin-quick-switch" aria-label="场景内设备切换" @pointerenter="onQuickSwitchPointerMove" @pointerdown.capture="onQuickSwitchPointerDown" @pointermove.capture="onQuickSwitchPointerMove" @pointerup.capture="onQuickSwitchPointerEnd" @pointercancel.capture="onQuickSwitchPointerEnd" @mousedown.stop>
          <div class="twin-quick-switch-tools"><div class="twin-quick-switch-heading"><span>设备快速切换 · {{ visibleAssets.length }}/{{ store.assets.length }}</span><b>{{ selectedAssetName || '请选择设备' }}</b></div><div class="twin-switch-filters" role="group" aria-label="按运行状态筛选设备"><button v-for="filter in filterOptions" :key="filter.value" :class="{ selected: stateFilter === filter.value }" type="button" @pointerdown.stop @click.stop="stateFilter = filter.value">{{ filter.label }}</button></div></div>
          <div class="twin-quick-switch-list"><button v-for="asset in visibleAssets" :key="asset.id" :class="[resolveTwinVisualState(asset, store.alerts), { selected: asset.code === selectedCode }]" :aria-label="`选择 ${asset.name}，设备编码 ${asset.code}`" :title="`${asset.name} · ${asset.zone}`" @pointerdown.stop @click.stop="select(asset.code)"><i /><span><b>{{ asset.code }}</b><small>{{ asset.name }}</small></span></button></div>
        </nav>
        <div v-if="finePointer" class="twin-fullscreen-fx" :class="{ active: fullscreenPointer.active, pressed: fullscreenPointer.pressed, dragging: fullscreenPointer.draggingSwitcher }" aria-hidden="true" :style="{ transform: `translate3d(${fullscreenPointer.x}px, ${fullscreenPointer.y}px, 0)` }">
          <i v-for="(point, index) in fullscreenTrail" :key="index" class="twin-fx-trail" :style="{ transform: `translate3d(${point.x - fullscreenPointer.x}px, ${point.y - fullscreenPointer.y}px, 0) scale(${point.scale})`, opacity: point.opacity }" />
          <i class="twin-fx-ring" /><i class="twin-fx-dot" /><i v-if="fullscreenPulse" :key="fullscreenPulse.key" class="twin-fx-pulse" :style="{ '--twin-pulse-x': `${fullscreenPulse.x - fullscreenPointer.x}px`, '--twin-pulse-y': `${fullscreenPulse.y - fullscreenPointer.y}px` }" />
        </div>
      </article>
      <aside class="twin-inspector" aria-live="polite">
        <template v-if="selectedAsset">
          <header><div><span class="eyebrow">SELECTED EQUIPMENT</span><h2 :title="selectedAsset.name">{{ selectedAssetName }}</h2><code>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</code></div><span :class="['twin-state-chip', resolveTwinVisualState(selectedAsset, store.alerts)]">{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span></header>
          <section :class="['twin-model-readiness', modelReport.mode]"><span>实体模型接入</span><div><b>{{ modelReport.mode === 'loaded' ? '模型已加载' : '预览场景' }}</b><strong>{{ modelBindingText }}</strong></div><p>{{ modelDeliveryHint }}</p><button v-if="modelReport.mode === 'fallback'" type="button" class="twin-model-retry" @click="retryModel">重新检测模型</button></section>
          <section :class="['twin-model-contract', { ready: modelDeliveryReady, blocked: !modelDeliveryReady }]" :title="modelDeliveryHint"><span>模型交付检查</span><b>{{ modelDeliveryLabel }}</b><p>{{ modelDeliveryCount }} / {{ modelDeliveryTotal }} 个设备已具备标准节点名称</p></section>
          <details class="twin-model-binding-list"><summary>查看实体模型映射</summary><p v-if="modelReport.isComplete">模型中的设备节点已全部绑定，可进行状态高亮与点击定位。</p><p v-else>待补齐：{{ modelReport.missingCodes.join('、') }}</p><div><span v-for="code in modelReport.boundCodes" :key="code">{{ code }}</span></div></details>
          <p v-if="navigationContext" class="twin-navigation-context" role="status">{{ navigationContext }}</p>
          <div class="twin-inspector-grid"><div><span>所在区域</span><b>{{ selectedAsset.zone }}</b></div><div><span>实体模型</span><b>{{ selectedAsset.mesh || '待绑定' }}</b></div><div><span>最新上报</span><b>{{ formatTime(selectedAsset.lastSeenAt) }}</b></div><div><span>当前遥测</span><b>{{ selectedTelemetry ? `${selectedTelemetry.value} ${selectedTelemetry.unit}` : '暂无数据' }}</b></div></div>
          <section class="twin-detail-section"><span class="eyebrow">CURRENT ALERTS</span><div v-if="primaryAlert" class="twin-alert-summary"><b>{{ primaryAlert.severity === 'critical' ? '严重告警' : primaryAlert.severity === 'warning' ? '待处置告警' : '提示告警' }} · {{ primaryAlert.code }}</b><strong>{{ primaryAlert.title }}</strong><p>{{ primaryAlert.detail }}</p><button type="button" class="twin-alert-action" @click="openAlertCenter">进入告警中心处置</button></div><p v-else class="twin-empty">当前设备没有未关闭告警。</p></section>
          <section class="twin-detail-section"><span class="eyebrow">WORK ORDER STATUS</span><p v-if="selectedOrders.length" class="twin-order-summary"><b>{{ selectedOrders[0].code }}</b>{{ selectedOrders[0].title }}</p><p v-else class="twin-empty">当前设备没有关联工单。</p></section>
          <button class="twin-gis-link" type="button" @click="openGis">在 GIS 地图中查看</button>
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
