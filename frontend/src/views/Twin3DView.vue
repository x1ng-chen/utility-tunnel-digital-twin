<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useMediaQuery } from '@vueuse/core';
import { useNow } from '@vueuse/core';
import { Camera, Expand, MapPin, RefreshCw, RotateCcw, Search } from 'lucide-vue-next';
import { useRoute, useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import TwinScene from '../components/TwinScene.vue';
import TelemetryTrendChart from '../components/TelemetryTrendChart.vue';
import { useOperationsStore } from '../stores/operations';
import { api } from '../services/api';
import { newTwinAlert } from '../utils/newTwinAlert';
import { twinTelemetryTrend } from '../utils/twinTelemetryTrend';
import { levelStationCards } from '../utils/levelStations';
import { latestTelemetry, telemetryState, telemetryStateLabel } from '../utils/telemetryState';
import { activeTwinAlerts, primaryTwinAlert, resolveTwinVisualState, summarizeTwinModelDelivery, twinStateLabel, type TwinModelBindingReport, type TwinModelReadinessResponse, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const now = useNow({ interval: 10_000 });
const route = useRoute();
const router = useRouter();
const stage = ref<HTMLElement>();
const requestedCode = typeof route.query.asset === 'string' ? route.query.asset : '';
const selectedCode = ref(store.assets.some((asset) => asset.code === requestedCode) ? requestedCode : store.alerts.find((alert) => !['resolved', 'closed'].includes(alert.status))?.assetCode || store.assets[0]?.code || null);
const scene = ref<InstanceType<typeof TwinScene>>();
const autoLocate = ref(true);
const autoLocateMessage = ref('');
function pauseAutoLocate(event?: Event) {
  if (!autoLocate.value) return;
  // The fullscreen auto-locate switch lives inside the stage, so its own clicks
  // would otherwise pause auto-locate through the stage's pointerdown capture
  // and keep the checkbox stuck. Let that control operate without pausing.
  if (event?.target instanceof Element && event.target.closest('.twin-fullscreen-autolocate')) return;
  autoLocate.value = false;
  autoLocateMessage.value = '手动查看中，自动定位已暂停。';
}
watch(() => store.alerts.map(alert => ({ ...alert })), (next, previous) => {
  if (!previous || !autoLocate.value || store.source !== 'api' || store.offline) return;
  const alert = newTwinAlert(next, previous, store.assets.map(asset => asset.code));
  if (!alert?.assetCode) return;
  // Route the focus through the selectedCode watcher so the camera only jumps
  // once. When the alert targets the already-selected asset that watcher does
  // not fire, so focus it directly to keep the operator oriented on the fresh
  // incident without a duplicate focusAsset call.
  if (selectedCode.value === alert.assetCode) scene.value?.focusAsset(alert.assetCode);
  else selectedCode.value = alert.assetCode;
  autoLocateMessage.value = modelReport.value.mode === 'loaded' && modelReport.value.boundCodes.includes(alert.assetCode)
    ? `新告警 ${alert.code}：已定位 ${alert.assetCode} 测点`
    : `新告警 ${alert.code}：已选中 ${alert.assetCode}；实体模型节点尚未确认。`;
});
const query = ref('');
const stateFilter = ref<'all' | TwinVisualState>('all');
const finePointer = ref(false);
const fullscreenActive = ref(false);
const compactLayout = useMediaQuery('(max-width: 1180px)');
const fullscreenPointer = reactive({ x: -80, y: -80, active: false, pressed: false, draggingSwitcher: false });
const fullscreenTrail = ref(Array.from({ length: 6 }, (_, index) => ({ x: -80, y: -80, opacity: 0.34 - index * 0.045, scale: 1 - index * 0.1 })));
const fullscreenPulse = ref<{ key: number; x: number; y: number } | null>(null);
let pendingFullscreenPointer: PointerEvent | undefined;
let fullscreenPointerFrame = 0;
let fullscreenPulseTimer: number | undefined;
const modelReport = ref<TwinModelBindingReport>({ mode: 'fallback', expectedCount: store.assets.length, boundCodes: [], missingCodes: store.assets.map((asset) => asset.code), isComplete: false });
const serverModelReadiness = ref<TwinModelReadinessResponse | null>(null);
const activeModelUrl = ref<string>();
const modelSource = ref<'checking' | 'active' | 'preview' | 'candidate' | 'unavailable'>('checking');
const showV13Candidate = computed(() => route.query.model !== 'v07');
let modelRequestToken = 0;
let modelObjectUrl: string | undefined;
const filterOptions: Array<{ value: 'all' | TwinVisualState; label: string }> = [
  { value: 'all', label: '全部' }, { value: 'alarm', label: '告警' }, { value: 'warning', label: '关注' }, { value: 'normal', label: '正常' }, { value: 'unknown', label: '待核验' },
];
const selectedAsset = computed(() => store.assets.find((asset) => asset.code === selectedCode.value) || null);
const selectedModelNodeLabel = computed(() => {
  const asset = selectedAsset.value;
  if (!asset) return '待绑定';
  if (modelSource.value !== 'candidate') return asset.mesh || '待绑定';
  if (!modelReport.value.boundCodes.includes(asset.code)) return 'V13 模型未映射';
  return /^LEVEL-L0[1-5]$/.test(asset.code) ? `${asset.code}-探头` : asset.code;
});
const stationCards = computed(() => levelStationCards(store.assets, store.alerts, store.telemetry, store.hardwareBindings, store.source, store.offline, now.value.getTime()));
const selectedAlerts = computed(() => selectedAsset.value ? activeTwinAlerts(selectedAsset.value.code, store.alerts) : []);
const primaryAlert = computed(() => selectedAsset.value ? primaryTwinAlert(selectedAsset.value.code, store.alerts) : null);
const selectedOrders = computed(() => selectedAsset.value ? store.workOrders.filter((order) => order.assetCode === selectedAsset.value?.code) : []);
const selectedTelemetry = computed(() => selectedAsset.value ? latestTelemetry(store.telemetry, selectedAsset.value.code) ?? null : null);
const selectedBinding = computed(() => store.hardwareBindings.find((item) => item.assetCode === selectedAsset.value?.code));
const selectedTelemetryState = computed(() => telemetryState(selectedTelemetry.value, selectedAsset.value, selectedBinding.value, store.source, store.offline, now.value.getTime()));
const selectedTelemetrySeries = computed(() => twinTelemetryTrend(store.telemetry, selectedTelemetry.value ?? null));
const selectedTelemetrySampleCount = computed(() => selectedTelemetrySeries.value.reduce((count, series) => count + series.data.filter(point => point[1] !== null).length, 0));
const visibleAssets = computed(() => store.assets.filter((asset) => {
  const matchesQuery = !query.value || `${asset.code} ${asset.name} ${asset.zone}`.toLowerCase().includes(query.value.toLowerCase());
  return matchesQuery && (stateFilter.value === 'all' || resolveTwinVisualState(asset, store.alerts) === stateFilter.value);
}));
const riskAssets = computed(() => store.assets.filter((asset) => ['alarm', 'warning'].includes(resolveTwinVisualState(asset, store.alerts))));
const riskPatrolLabel = computed(() => {
  if (!riskAssets.value.length) return '';
  const current = riskAssets.value.findIndex((asset) => asset.code === selectedCode.value);
  return current < 0 ? `${riskAssets.value.length} 个异常待巡检` : `异常 ${current + 1} / ${riskAssets.value.length}`;
});
const selectedAssetName = computed(() => selectedAsset.value?.name.replace(/\s*[（(][^（）()]{1,16}[）)]\s*$/, '') || '');
const modelBindingText = computed(() => `${modelReport.value.boundCodes.length} / ${modelReport.value.expectedCount} 个设备已定位`);
const localModelReadiness = computed(() => summarizeTwinModelDelivery(store.assets));
const modelDeliveryReady = computed(() => modelSource.value === 'active' && serverModelReadiness.value?.status === 'ready');
const modelDeliveryCount = computed(() => modelSource.value === 'candidate' ? modelReport.value.boundCodes.length : serverModelReadiness.value?.summary.mappedAssetCount ?? localModelReadiness.value.mappedAssetCount);
const modelDeliveryTotal = computed(() => modelSource.value === 'candidate' ? modelReport.value.expectedCount : serverModelReadiness.value?.summary.activeAssetCount ?? localModelReadiness.value.activeAssetCount);
const nodeMappingsComplete = computed(() => modelDeliveryCount.value >= modelDeliveryTotal.value && modelDeliveryTotal.value > 0);
const modelDeliveryLabel = computed(() => {
  if (modelSource.value === 'candidate') return 'V13 当前模型';
  if (modelSource.value === 'checking') return '正在验证模型版本';
  if (modelSource.value === 'unavailable') return '模型文件暂不可用';
  if (modelSource.value === 'preview') return nodeMappingsComplete.value ? '等待启用模型版本' : `待补齐 ${Math.max(modelDeliveryTotal.value - modelDeliveryCount.value, 0)} 个节点`;
  if (modelDeliveryReady.value) return '模型节点已就绪';
  if (nodeMappingsComplete.value && !serverModelReadiness.value?.activeRelease) return '等待启用模型版本';
  return `待补齐 ${Math.max(modelDeliveryTotal.value - modelDeliveryCount.value, 0)} 个节点`;
});
const modelDeliveryHint = computed(() => {
  if (modelSource.value === 'candidate') return modelReport.value.mode === 'fallback'
    ? 'V13 模型尚未加载；请检查模型文件和网络。'
    : '当前加载由 V13 BLEND 导出的模型；五个液位探头可分别定位。其余未绑定设备仍按缺失节点显示，待资产映射补齐。';
  if (modelSource.value === 'checking') return '正在从服务端核验启用模型版本，暂不把预览场景标记为实体模型。';
  if (modelSource.value === 'unavailable') return '已启用的实体模型文件暂时无法获取，系统已切换到可交互预览，未将预览误标为实体模型。请检查模型存储与网络后重新检测。';
  if (modelSource.value === 'preview') return nodeMappingsComplete.value
    ? '设备节点名称已准备完成，请由管理员上传并启用经过校验的 GLB 模型。'
    : '资产台账仍缺少标准节点名称，暂不建议交付实体模型。';
  if (!modelDeliveryReady.value && nodeMappingsComplete.value && !serverModelReadiness.value?.activeRelease) return '设备节点名称已准备完成，请由管理员上传并启用经过校验的 GLB 模型。';
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

function select(code: string) {
  pauseAutoLocate();
  // Re-selecting the current asset should recentre it, but a new selection
  // must not fire focusAsset twice (once here and once via the selectedCode
  // watcher in TwinScene). Only the already-selected path focuses directly.
  if (selectedCode.value === code) { scene.value?.focusAsset(code); return; }
  selectedCode.value = code;
}
function inspectRisk(direction: 1 | -1) {
  const assets = riskAssets.value;
  if (!assets.length) return;
  const current = assets.findIndex((asset) => asset.code === selectedCode.value);
  const next = current < 0 ? (direction > 0 ? 0 : assets.length - 1) : (current + direction + assets.length) % assets.length;
  select(assets[next].code);
}
function openGis() { if (selectedAsset.value) void router.push({ path: '/gis', query: { asset: selectedAsset.value.code, source: 'twin' } }); }
function openAlertCenter() { if (primaryAlert.value) void router.push({ path: '/alerts', query: { focus: primaryAlert.value.code, source: 'twin' } }); }
function resetView() { pauseAutoLocate(); scene.value?.resetView(); }
function selectPreset(zone: string) {
  if (zone === '总览') { resetView(); return; }
  const asset = store.assets.find((item) => item.zone.includes(zone) || (zone === '水浸点' && /SEEP|水浸|水位/.test(`${item.code}${item.name}`)));
  if (asset) select(asset.code);
}
function retryModel() { scene.value?.reloadModel(); }
function toggleModelVersion() {
  const query = { ...route.query };
  if (showV13Candidate.value) query.model = 'v07';
  else delete query.model;
  void router.replace({ query });
}
function receiveModelReport(report: TwinModelBindingReport) { modelReport.value = report; }
async function refreshModelReadiness() {
  const requestToken = ++modelRequestToken;
  if (showV13Candidate.value) {
    serverModelReadiness.value = null;
    releaseModelObjectUrl();
    activeModelUrl.value = '/models/utility-tunnel.glb';
    modelSource.value = 'candidate';
    return;
  }
  modelSource.value = store.source !== 'api' || store.offline ? 'preview' : 'checking';
  if (store.source !== 'api' || store.offline) { serverModelReadiness.value = null; releaseModelObjectUrl(); activeModelUrl.value = '/models/utility-tunnel-v07.glb'; return; }
  try {
    const readiness = (await api.twinModelReadiness()).data as TwinModelReadinessResponse;
    if (requestToken !== modelRequestToken) return;
    serverModelReadiness.value = readiness;
    if (!readiness.activeRelease) { modelSource.value = 'preview'; releaseModelObjectUrl(); activeModelUrl.value = '/models/utility-tunnel-v07.glb'; return; }
    try {
      const response = await api.twinModelFile(readiness.activeRelease.id);
      if (requestToken !== modelRequestToken) return;
      releaseModelObjectUrl();
      modelObjectUrl = URL.createObjectURL(response.data as Blob);
      activeModelUrl.value = modelObjectUrl;
      modelSource.value = 'active';
    } catch {
      if (requestToken === modelRequestToken) {
        releaseModelObjectUrl();
        modelSource.value = 'unavailable';
      }
    }
  } catch {
    if (requestToken === modelRequestToken) {
      serverModelReadiness.value = null;
      releaseModelObjectUrl();
      modelSource.value = 'unavailable';
    }
  }
}
function releaseModelObjectUrl() {
  if (modelObjectUrl) URL.revokeObjectURL(modelObjectUrl);
  modelObjectUrl = undefined;
  activeModelUrl.value = undefined;
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
    const easing = 0.78 - index * 0.055;
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
function formatTime(value: string | null | undefined) { return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN') : '暂无有效时间'; }
watch(() => route.query.asset, (code) => { if (typeof code === 'string' && store.assets.some((asset) => asset.code === code)) select(code); });
watch(() => [store.source, store.offline, route.query.model], () => { void refreshModelReadiness(); });
onMounted(() => {
  finePointer.value = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  document.addEventListener('fullscreenchange', updateFullscreenState);
  void refreshModelReadiness();
});
onBeforeUnmount(() => {
  modelRequestToken += 1;
  releaseModelObjectUrl();
  document.removeEventListener('fullscreenchange', updateFullscreenState);
  if (fullscreenPointerFrame) window.cancelAnimationFrame(fullscreenPointerFrame);
  if (fullscreenPulseTimer) window.clearTimeout(fullscreenPulseTimer);
});
</script>

<template>
  <AppShell>
    <section class="twin-title section-title">
      <div><span class="eyebrow light">实体设备可视化</span><h1>三维孪生中心</h1><p>以真实实体模型定位设备、告警与工单；三维状态与运行数据实时同步。</p></div>
      <div class="twin-title-actions"><span :class="['twin-live', { blocked: !modelDeliveryReady && modelSource !== 'candidate' }]" :title="modelDeliveryHint"><i />{{ modelDeliveryLabel }}</span><button type="button" class="outline-button" @click="toggleModelVersion">{{ showV13Candidate ? '查看已启用版本' : '返回 V13 模型' }}</button><button v-if="modelReport.mode === 'fallback' || modelSource === 'unavailable'" type="button" class="outline-button twin-model-retry-top" @click="retryModel"><RefreshCw />检测模型</button><button class="primary-button compact-button" @click="resetView"><RotateCcw />重置视角</button><button class="outline-button" @click="fullscreen"><Expand />全屏查看</button></div>
    </section>
    <section class="twin-workspace">
      <div class="twin-auto-locate" role="group" aria-label="新告警自动定位">
        <label><input v-model="autoLocate" type="checkbox" @change="autoLocateMessage = autoLocate ? '将定位新产生或升级的告警。' : '自动定位已关闭。'" /> 新告警自动定位</label>
        <span role="status">{{ autoLocateMessage || '手动拖动、缩放或选择设备后暂停，避免抢占视角。' }}</span>
      </div>
      <article ref="stage" :class="['twin-stage-panel', { 'twin-fullscreen-active': fullscreenActive }]" @pointerdown.capture="pauseAutoLocate" @wheel.capture.passive="pauseAutoLocate" @keydown.capture="pauseAutoLocate" @pointermove="onStagePointerMove" @pointerdown="onStagePointerDown" @pointerup="onStagePointerUp" @pointerleave="onStagePointerLeave">
        <nav class="twin-preset-hud" aria-label="三维视角预设"><span><Camera />视角预设</span><button v-for="preset in ['总览','电力舱','燃气舱','水浸点']" :key="preset" @click="selectPreset(preset)">{{ preset }}</button></nav>
        <aside class="twin-risk-hud" aria-label="风险设备列表"><strong>风险设备 · {{ riskAssets.length }} 台</strong><button v-for="asset in riskAssets" :key="asset.id" type="button" :aria-pressed="selectedCode === asset.code" :title="asset.name" @click="select(asset.code)"><i :class="resolveTwinVisualState(asset, store.alerts)" /><span>{{ asset.code }}</span><small>{{ asset.name }}</small></button><p v-if="!riskAssets.length">当前无风险设备</p></aside>
        <TwinScene ref="scene" :assets="store.assets" :alerts="store.alerts" :selected-code="selectedCode" :model-url="activeModelUrl" :model-enabled="modelSource === 'active' || modelSource === 'preview' || modelSource === 'candidate'" :show-unbound-markers="modelSource !== 'candidate'" @select="select" @model-report="receiveModelReport" />
        <div v-if="selectedAsset" class="twin-focus-status" aria-live="polite"><span :class="resolveTwinVisualState(selectedAsset, store.alerts)"><i />{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span><b :title="selectedAsset.name">{{ selectedAssetName }}</b><small>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</small><div v-if="riskAssets.length" class="twin-risk-patrol"><em>{{ riskPatrolLabel }}</em><button type="button" aria-label="巡检上一异常设备" @click="inspectRisk(-1)">← 上一异常</button><button type="button" aria-label="巡检下一异常设备" @click="inspectRisk(1)">下一异常 →</button></div></div>
        <nav class="twin-quick-switch" aria-label="场景内设备切换" @pointerenter="onQuickSwitchPointerMove" @pointerdown.capture="onQuickSwitchPointerDown" @pointermove.capture="onQuickSwitchPointerMove" @pointerup.capture="onQuickSwitchPointerEnd" @pointercancel.capture="onQuickSwitchPointerEnd" @mousedown.stop>
          <div class="twin-quick-switch-tools"><div class="twin-quick-switch-heading"><span>设备快速切换 · {{ visibleAssets.length }}/{{ store.assets.length }}</span><b>{{ selectedAssetName || '请选择设备' }}</b></div><div class="twin-switch-filters" role="group" aria-label="按运行状态筛选设备"><button v-for="filter in filterOptions" :key="filter.value" :class="{ selected: stateFilter === filter.value }" type="button" @pointerdown.stop @click.stop="stateFilter = filter.value">{{ filter.label }}</button></div></div>
          <div class="twin-quick-switch-list"><button v-for="asset in visibleAssets" :key="asset.id" :class="[resolveTwinVisualState(asset, store.alerts), { selected: asset.code === selectedCode }]" :aria-label="`选择 ${asset.name}，设备编码 ${asset.code}`" :title="`${asset.name} · ${asset.zone}`" @pointerdown.stop @click.stop="select(asset.code)"><i /><span><b>{{ asset.code }}</b><small>{{ asset.name }}</small></span></button></div>
        </nav>
        <div v-if="fullscreenActive" class="twin-fullscreen-autolocate" role="group" aria-label="全屏新告警自动定位">
          <label><input v-model="autoLocate" type="checkbox" @change="autoLocateMessage = autoLocate ? '将定位新产生或升级的告警。' : '自动定位已关闭。'" /> 新告警自动定位</label>
          <button v-if="!autoLocate" type="button" @click="autoLocate = true; autoLocateMessage = '已恢复新告警自动定位。'">恢复自动定位</button>
        </div>
        <div v-if="finePointer" class="twin-fullscreen-fx" :class="{ active: fullscreenPointer.active, pressed: fullscreenPointer.pressed, dragging: fullscreenPointer.draggingSwitcher }" aria-hidden="true" :style="{ transform: `translate3d(${fullscreenPointer.x}px, ${fullscreenPointer.y}px, 0)` }">
          <i v-for="(point, index) in fullscreenTrail" :key="index" class="twin-fx-trail" :style="{ transform: `translate3d(${point.x - fullscreenPointer.x}px, ${point.y - fullscreenPointer.y}px, 0) scale(${point.scale})`, opacity: point.opacity }" />
          <i class="twin-fx-ring" /><i class="twin-fx-dot" /><i v-if="fullscreenPulse" :key="fullscreenPulse.key" class="twin-fx-pulse" :style="{ '--twin-pulse-x': `${fullscreenPulse.x - fullscreenPointer.x}px`, '--twin-pulse-y': `${fullscreenPulse.y - fullscreenPointer.y}px` }" />
        </div>
      </article>
      <aside class="twin-inspector" aria-live="polite">
        <template v-if="selectedAsset">
          <header><div><span class="eyebrow">当前设备</span><h2 :title="selectedAsset.name">{{ selectedAssetName }}</h2><code>{{ selectedAsset.code }} · {{ selectedAsset.zone }}</code></div><span :class="['twin-state-chip', resolveTwinVisualState(selectedAsset, store.alerts)]">{{ statusLabel(resolveTwinVisualState(selectedAsset, store.alerts)) }}</span></header>
          <section :class="['twin-model-readiness', modelReport.mode, modelSource]"><span>实体模型接入</span><div><b>{{ modelSource === 'unavailable' ? '模型文件不可用' : modelSource === 'checking' ? '正在核验模型' : modelReport.mode === 'loaded' ? '模型已加载' : '预览场景' }}</b><strong>{{ modelBindingText }}</strong></div><p>{{ modelDeliveryHint }}</p><button v-if="modelReport.mode === 'fallback' || modelSource === 'unavailable'" type="button" class="twin-model-retry" @click="retryModel">重新检测模型</button></section>
          <section :class="['twin-model-contract', { ready: modelDeliveryReady, blocked: !modelDeliveryReady }]" :title="modelDeliveryHint"><span>模型交付检查</span><b>{{ modelDeliveryLabel }}</b><p>{{ modelDeliveryCount }} / {{ modelDeliveryTotal }} {{ modelSource === 'candidate' ? '个设备在 V13 模型中已定位' : '个设备已具备标准节点名称' }}</p></section>
          <details class="twin-model-binding-list"><summary>查看实体模型映射</summary><p v-if="modelReport.isComplete">模型中的设备节点已全部绑定，可进行状态高亮与点击定位。</p><p v-else>待补齐：{{ modelReport.missingCodes.join('、') }}</p><div><span v-for="code in modelReport.boundCodes" :key="code">{{ code }}</span></div></details>
          <p v-if="navigationContext" class="twin-navigation-context" role="status">{{ navigationContext }}</p>
          <div class="twin-inspector-grid"><div><span>所在区域</span><b>{{ selectedAsset.zone }}</b></div><div><span>实体模型</span><b>{{ selectedModelNodeLabel }}</b></div><div><span>最新上报</span><b>{{ formatTime(selectedAsset.lastSeenAt) }}</b></div><div><span>最近采集值</span><b>{{ selectedTelemetry && !['invalid', 'missing'].includes(selectedTelemetryState) ? `${selectedTelemetry.value} ${selectedTelemetry.unit}` : '暂无可信读数' }}</b><small>{{ telemetryStateLabel[selectedTelemetryState] }}{{ selectedTelemetry ? ` · ${formatTime(selectedTelemetry.recordedAt)}` : '' }}</small></div></div>
          <section class="twin-detail-section">
            <span class="eyebrow">实时数据</span>
            <p v-if="selectedTelemetry" class="twin-empty">{{ selectedTelemetry.metric }} · {{ selectedTelemetry.unit }} · {{ selectedTelemetrySampleCount }} 条同类有效样本（当前已加载数据）</p>
            <TelemetryTrendChart v-if="selectedTelemetrySampleCount && !compactLayout" :series="selectedTelemetrySeries" :unit="selectedTelemetry?.unit || ''" />
            <p v-if="!selectedTelemetrySampleCount || compactLayout" class="twin-empty">{{ !selectedTelemetrySampleCount ? '当前设备暂无可绘制遥测。' : '窄屏已收起趋势图，可前往数据洞察查看。' }}</p>
            <p v-else class="twin-empty">{{ selectedTelemetrySampleCount === 1 ? '仅有一个有效测点，暂无连续趋势。' : '按真实时间间隔绘制；缺失样本保留断点，不插值。' }}</p>
          </section>
          <section class="twin-detail-section"><span class="eyebrow">当前告警</span><div v-if="primaryAlert" class="twin-alert-summary"><b>{{ primaryAlert.severity === 'critical' ? '严重告警' : primaryAlert.severity === 'warning' ? '待处置告警' : '提示告警' }} · {{ primaryAlert.code }}</b><strong>{{ primaryAlert.title }}</strong><p>{{ primaryAlert.detail }}</p><button type="button" class="twin-alert-action" @click="openAlertCenter">进入告警中心处置</button></div><p v-else class="twin-empty">当前设备没有未关闭告警。</p></section>
          <section class="twin-detail-section"><span class="eyebrow">关联工单</span><p v-if="selectedOrders.length" class="twin-order-summary"><b>{{ selectedOrders[0].code }}</b>{{ selectedOrders[0].title }}</p><p v-else class="twin-empty">当前设备没有关联工单。</p></section>
          <button class="twin-gis-link" type="button" @click="openGis"><MapPin />在 GIS 地图中查看</button>
          <p class="twin-install-note">{{ selectedAsset.installationNote }}</p>
        </template>
        <div v-else class="twin-empty-inspector">从三维场景或设备列表中选择一个设备。</div>
      </aside>
    </section>
    <section class="level-stations" aria-labelledby="level-stations-title">
      <div class="level-stations-heading"><div><span class="eyebrow">水路测点</span><h2 id="level-stations-title">五个独立液位节点</h2></div><p>异常定位到测点及对应管段；不能仅凭液位判断裂口的精确位置。</p></div>
      <div class="level-stations-grid">
        <button v-for="station in stationCards" :key="station.code" type="button" class="level-station-card" :class="{ alarm: station.alert, selected: selectedCode === station.code }" :aria-pressed="selectedCode === station.code" :disabled="!station.asset" @click="select(station.code)">
          <span>{{ station.code }}</span><strong>{{ station.section }}</strong><small>{{ station.summary }}</small>
          <em v-if="station.reading">{{ station.reading.metric }} · {{ telemetryStateLabel[station.state] }} · {{ formatTime(station.reading.recordedAt) }}</em>
          <em v-else>尚无此测点的独立遥测</em>
        </button>
      </div>
    </section>
    <section class="twin-asset-panel">
      <header><div><span class="eyebrow">设备定位</span><h2>三维设备定位</h2></div><label class="twin-search"><Search /><input v-model="query" aria-label="搜索三维设备" placeholder="搜索设备编码、名称或区域" /></label></header>
      <div class="twin-asset-list"><button v-for="asset in visibleAssets" :key="asset.id" :class="['twin-asset-item', resolveTwinVisualState(asset, store.alerts), { selected: asset.code === selectedCode }]" @click="select(asset.code)"><i /><span><b>{{ asset.code }}</b><small>{{ asset.name }} · {{ asset.zone }}</small></span><em>{{ statusLabel(resolveTwinVisualState(asset, store.alerts)) }}</em></button><p v-if="!visibleAssets.length" class="twin-empty">没有符合当前条件的设备。</p></div>
    </section>
  </AppShell>
</template>

<style src="../assets/twin3d.css" />
<style src="../assets/operational-layout-polish.css" />
<style scoped>
.level-stations { margin: 0 0 18px; padding: 18px; border: 1px solid var(--ops-line); border-radius: 12px; background: #0b1c30; }
.level-stations-heading { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 8px 24px; margin-bottom: 14px; }
.level-stations-heading h2 { margin: 5px 0 0; color: var(--ops-text); font-size: 18px; }
.level-stations-heading p { max-width: 520px; margin: 0; color: var(--ops-muted); font-size: 12px; line-height: 1.6; }
.level-stations-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 9px; }
.level-station-card { display: grid; align-content: start; gap: 5px; min-width: 0; min-height: 114px; padding: 12px; border: 1px solid #31506f; border-radius: 9px; background: #10263d; color: #cddff2; text-align: left; cursor: pointer; }
.level-station-card:hover, .level-station-card:focus-visible, .level-station-card.selected { border-color: #66d9c6; outline: 0; }
.level-station-card.alarm { border-color: #f47787; background: #3a2033; }
.level-station-card span { color: #85a4c1; font-size: 11px; font-weight: 700; }
.level-station-card strong { font-size: 15px; }
.level-station-card small, .level-station-card em { color: #a8bfd6; font-size: 11px; font-style: normal; line-height: 1.5; overflow-wrap: anywhere; }
.level-station-card:disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 1050px) { .level-stations-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 600px) { .level-stations-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .level-stations { padding: 12px; } }
.twin-auto-locate { grid-column: 1 / -1; display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px 16px; border: 1px solid var(--ops-line); background: var(--ops-panel); }
.twin-auto-locate label { display: inline-flex; align-items: center; gap: 8px; min-height: 32px; font-size: 13px; }
.twin-auto-locate input { width: 16px; height: 16px; min-height: 0; padding: 0; }
.twin-auto-locate span { color: var(--ops-muted); font-size: 12px; }
.twin-stage-panel::before{position:absolute;z-index:2;top:0;right:0;left:0;height:62px;border-bottom:1px solid #29445f99;background:linear-gradient(180deg,#0a192beb,#091727c4);content:'';pointer-events:none;backdrop-filter:blur(10px)}.twin-preset-hud{position:absolute;top:12px;left:50%;z-index:7;display:flex;align-items:center;overflow:hidden;border:1px solid #3d5d7c;background:#091727f2;box-shadow:0 10px 26px #0005;transform:translateX(-50%)}.twin-preset-hud span,.twin-preset-hud button{display:flex;align-items:center;justify-content:center;height:38px;padding:0 14px;border:0;border-right:1px solid var(--ops-line);background:transparent;color:var(--ops-muted);font:11px "Cascadia Mono",monospace;line-height:1;white-space:nowrap}.twin-preset-hud span{min-width:112px;gap:8px;color:var(--ops-signal);font-family:inherit;font-weight:800}.twin-preset-hud button{min-width:60px;cursor:pointer}.twin-preset-hud button:last-child{border-right:0}.twin-preset-hud svg{width:15px;flex:0 0 auto}.twin-preset-hud button:hover,.twin-preset-hud button:focus-visible{color:#fff;background:var(--ops-raised);outline:0;box-shadow:inset 0 -2px var(--ops-signal)}.twin-risk-hud{position:absolute;left:16px;top:74px;z-index:6;width:210px;border:1px solid var(--ops-line);background:#09111de8}.twin-stage-panel:not(.twin-fullscreen-active) .twin-focus-status{top:74px}.twin-risk-hud>strong{display:block;padding:10px 12px;border-bottom:1px solid var(--ops-line);color:var(--ops-danger);font:10px "Cascadia Mono",monospace;letter-spacing:.12em}.twin-risk-hud button{width:100%;display:grid;grid-template-columns:8px 55px 1fr;gap:8px;align-items:center;padding:9px 11px;border:0;border-bottom:1px solid var(--ops-line-soft);background:transparent;color:var(--ops-text);text-align:left}.twin-risk-hud button:hover{background:var(--ops-raised)}.twin-risk-hud i{width:7px;height:7px;background:var(--ops-warn)}.twin-risk-hud i.alarm{background:var(--ops-danger)}.twin-risk-hud span{font:10px "Cascadia Mono",monospace}.twin-risk-hud small{overflow:hidden;color:var(--ops-muted);text-overflow:ellipsis;white-space:nowrap}.twin-risk-hud p{padding:10px;margin:0;color:var(--ops-muted);font-size:11px}.twin-title-actions button,.twin-gis-link{display:inline-flex!important;align-items:center;justify-content:center;gap:7px}.twin-title-actions svg,.twin-gis-link svg,.twin-search svg{width:16px}.twin-search{display:flex!important;align-items:center;gap:8px;padding-left:10px}
.twin-risk-hud { max-height: 230px; overflow-y: auto; scrollbar-width: thin; }
.twin-stage-panel { container-type: inline-size; display: flex; flex-direction: column; }
/* The inspector may be taller than the initial viewport-sized scene. Grow
   the actual canvas with the grid row instead of leaving an empty strip. */
.twin-stage-panel > .twin-scene { flex: 1 1 auto; width: 100%; }
.twin-risk-hud > strong { position: sticky; top: 0; z-index: 1; background: #09111d; }
.twin-risk-hud button { min-height: 44px; }
.twin-risk-hud button[aria-pressed="true"] { background: var(--ops-raised); box-shadow: inset 3px 0 var(--ops-signal); }
.twin-risk-hud button:focus-visible { outline: 2px solid var(--ops-signal); outline-offset: -2px; }
:deep(.twin-camera-controls button) { width: 44px; height: 44px; min-width: 44px; display: grid; place-items: center; padding: 0; }
:deep(.twin-camera-controls button:focus-visible) { outline: 2px solid var(--ops-signal); outline-offset: -3px; }
:deep(.twin-camera-controls svg) { width: 18px; height: 18px; margin: 0; }
:deep(.twin-model-state), :deep(.twin-model-progress) { z-index: 7; }
@container (max-width: 640px) {
  .twin-preset-hud { top: 56px; left: 16px; right: 16px; transform: none; }
  .twin-preset-hud span { min-width: 0; padding: 0 8px; }
  .twin-preset-hud button { flex: 1; min-width: 0; padding: 0 8px; }
  :deep(.twin-camera-controls) { top: 110px; left: 16px; }
  .twin-risk-hud { top: 164px; width: calc(50% - 24px); max-height: 145px; }
  .twin-stage-panel:not(.twin-fullscreen-active) .twin-focus-status,
  .twin-stage-panel.twin-fullscreen-active .twin-focus-status { top: 164px; right: 16px; width: calc(50% - 24px); }
  .twin-risk-hud button { grid-template-columns: 7px minmax(0, 1fr); gap: 5px; }
  .twin-risk-hud small { grid-column: 2; }
}
.twin-fullscreen-autolocate { position: absolute; z-index: 9; bottom: 150px; left: 22px; display: flex; align-items: center; flex-wrap: wrap; gap: 10px; padding: 9px 12px; border: 1px solid #3d5d7c; border-radius: 10px; background: #091727f2; box-shadow: 0 10px 26px #0005; }
.twin-fullscreen-autolocate label { display: inline-flex; align-items: center; gap: 7px; min-height: 28px; color: #c7daf1; font-size: 11px; cursor: pointer; }
.twin-fullscreen-autolocate input { width: 15px; height: 15px; min-height: 0; margin: 0; padding: 0; }
.twin-fullscreen-autolocate button { min-height: 28px; padding: 0 10px; border: 1px solid #397b78; border-radius: 7px; background: #103b42; color: #9de8d8; font-size: 10px; font-weight: 800; cursor: pointer; }
.twin-fullscreen-autolocate button:hover, .twin-fullscreen-autolocate button:focus-visible { border-color: #6adfca; background: #16554f; color: #fff; outline: 0; }
/* During twin fullscreen the stage draws its own pointer, trail, drag and pulse
   feedback. Keep the site-wide experience cursor from stacking a second ring on
   top (and hiding those states); its container stays mounted for the global
   cursor regression but contributes no visual while the scene is fullscreen. */
.twin-stage-panel.twin-fullscreen-active :deep(.experience-cursor) > * { display: none; }
</style>
