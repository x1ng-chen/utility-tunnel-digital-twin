<script setup lang="ts">
import { computed, ref } from 'vue';
import { Download, Lightbulb, RefreshCw, TrendingUp } from 'lucide-vue-next';
import AppShell from '../components/AppShell.vue';
import DashboardSignal from '../components/DashboardSignal.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';
import { resolveTwinVisualState, twinStateLabel, type TwinVisualState } from '../services/twin3d';

const store = useOperationsStore();
const auth = useAuthStore();
const mapAssets = computed(() => store.assets.map((asset) => ({ ...asset, visualState: resolveTwinVisualState(asset, store.alerts) })));
const mapStates: TwinVisualState[] = ['alarm', 'warning', 'normal', 'unknown'];
const signalOffline = computed(() => store.offline || store.dashboard.assets.online === 0 || store.assets.find((item) => item.code === store.dashboard.telemetry?.assetCode)?.status === 'offline');
const signalThreshold = computed(() => store.thresholds.find((item) => item.key === store.dashboard.telemetry?.metricKey)?.warning);
const reportError = ref('');
const exporting = ref(false);
const commandError = ref('');
const commandResult = ref('');
const commandSending = ref(false);
const canControlLighting = computed(() => store.source === 'api' && !store.offline && ['operator', 'administrator'].includes(auth.user?.role || ''));

async function sync() {
  reportError.value = '';
  await store.refresh(store.source);
  if (store.syncError) reportError.value = store.syncError;
}

async function report() {
  reportError.value = '';
  exporting.value = true;
  try {
    await store.createReport('daily');
  } catch (cause) {
    reportError.value = cause instanceof Error ? cause.message : '报表导出失败，请稍后重试。';
  } finally {
    exporting.value = false;
  }
}

async function testLighting(action: 'led_red' | 'led_green' | 'led_blue' | 'led_off') {
  if (!canControlLighting.value || commandSending.value) return;
  commandError.value = '';
  commandResult.value = '';
  commandSending.value = true;
  try {
    const response = await api.controllerLedTest(action);
    const ack = response.data.ack as { status?: string; reason?: string } | null;
    commandResult.value = ack?.status === 'accepted'
      ? `设备已确认：${ack.reason || action}`
      : '命令已交给 MQTT，等待设备回执。';
    await store.refresh('api');
  } catch (cause) {
    commandError.value = cause instanceof Error ? cause.message : '灯带命令下发失败，请稍后重试。';
  } finally {
    commandSending.value = false;
  }
}
</script>

<template>
  <AppShell>
    <section class="hero">
      <div><span class="eyebrow light">CONTROL ROOM · LIVE FEED</span><h1>运行，一眼掌握</h1><p>集中掌握综合管廊运行状态，所有关键操作均记录审计。</p><p v-if="store.lastSyncedAt">最近同步：{{ new Date(store.lastSyncedAt).toLocaleString('zh-CN') }}</p><p v-if="reportError" class="inline-message error-message" role="alert">{{ reportError }}</p></div>
      <div class="section-actions"><button class="primary-button compact-button" :disabled="store.loading" @click="sync"><RefreshCw />{{ store.loading ? '同步中…' : '刷新数据' }}</button><button class="primary-button" :disabled="exporting" @click="report"><Download />{{ exporting ? '正在生成…' : '导出运行快照' }}</button></div>
    </section>
    <section class="metric-grid">
      <article class="metric-card accent-blue" data-index="01"><span>在线设备 <TrendingUp /></span><strong>{{ store.dashboard.assets.online }}<small>/ {{ store.dashboard.assets.total }}</small></strong><em>按约定上报周期判定</em></article>
      <article class="metric-card accent-mint" data-index="02">
        <span>环境健康度 <TrendingUp /></span>
        <strong>{{ store.dashboard.assets.online > 0 ? store.dashboard.health.value : '--' }}<small v-if="store.dashboard.assets.online > 0">%</small></strong>
        <em>{{ store.dashboard.assets.online === 0 ? '无在线设备，暂无法判断' : store.dashboard.assets.online < store.dashboard.assets.total ? '部分设备离线，请结合告警核查' : '依据已上报数据计算，请结合告警核查' }}</em>
      </article>
      <article class="metric-card accent-amber" data-index="03"><span>待确认事件 <TrendingUp /></span><strong>{{ String(store.openAlerts).padStart(2, '0') }}<small>项</small></strong><em>需关注</em></article>
      <article class="metric-card accent-violet" data-index="04"><span>进行中工单 <TrendingUp /></span><strong>{{ String(store.activeOrders).padStart(2, '0') }}<small>项</small></strong><em v-if="store.dashboard.workOrderSla?.overdue">{{ store.dashboard.workOrderSla.overdue }} 项已超时，优先处置</em><em v-else-if="store.dashboard.workOrderSla?.dueSoon">{{ store.dashboard.workOrderSla.dueSoon }} 项将在 4 小时内到期</em><em v-else>处理时限正常</em></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel twin-panel">
        <div class="panel-head"><div><span class="eyebrow">TWIN PULSE</span><h2>管廊实时态势</h2></div><RouterLink to="/twin-3d">进入三维孪生 →</RouterLink></div>
        <div class="tunnel-map">
          <div class="map-grid" /><div class="map-track track-one" /><div class="map-track track-two" />
          <RouterLink v-for="asset in mapAssets" :key="asset.id" class="map-node" :class="asset.visualState" :to="{ path: '/twin-3d', query: { asset: asset.code } }" :aria-label="`查看${asset.name}：${twinStateLabel(asset.visualState)}`" :style="{ left: `${asset.position.x}%`, top: `${asset.position.y}%` }"><i /><span>{{ asset.code }}</span></RouterLink>
          <div class="map-legend"><span v-for="state in mapStates" :key="state"><i :class="state" />{{ twinStateLabel(state) }} {{ mapAssets.filter((item) => item.visualState === state).length }}</span></div>
        </div>
        <p class="map-disclaimer">位置示意，不代表真实坐标；状态与三维告警一致，在线数量请查看上方统计。点击设备可定位三维模型。</p>
      </article>
      <DashboardSignal :selected="store.dashboard.telemetry" :samples="store.telemetry" :offline="signalOffline" :threshold="signalThreshold" />
    </section>
    <section class="dashboard-grid lower-grid"><article class="panel activity-panel"><div class="panel-head"><div><span class="eyebrow">ACTIVITY STREAM</span><h2>最新运行动态</h2></div><RouterLink to="/audit">审计追踪 →</RouterLink></div><div v-for="item in store.audit.slice(0, 4)" :key="item.id" class="activity-item"><i /><time>{{ new Date(item.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><div><b>{{ presentAudit(item).title }}</b><p>{{ presentAudit(item).description }}</p></div></div><div v-if="!store.audit.length" class="empty-state">当前暂无审计记录。</div></article><article class="panel control-panel"><div class="panel-head"><div><span class="eyebrow">CTRL-01 · MQTT</span><h2>灯带联调</h2></div><Lightbulb /></div><p>仅限已登录的运维员或管理员；每次操作均生成唯一命令并写入审计。</p><div class="lighting-actions"><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_blue')">蓝色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_green')">绿色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_red')">红色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_off')">熄灭</button></div><small v-if="!canControlLighting">请使用在线 API 模式并以运维员或管理员身份登录。</small><b v-if="commandResult" class="command-ok">{{ commandResult }}</b><b v-if="commandError" class="command-error">{{ commandError }}</b></article></section>
  </AppShell>
</template>

<style scoped>
.map-node { text-decoration: none; }
.map-node:focus-visible { outline: 2px solid var(--ops-signal); outline-offset: 5px; z-index: 3; }
.map-node.alarm i, .map-legend i.alarm { background: #ff526e; box-shadow: 0 0 0 5px #ff526e22; }
.map-node.unknown i, .map-legend i.unknown { background: #8191a7; box-shadow: 0 0 0 5px #8191a722; }
.map-legend { flex-wrap: wrap; gap: 10px; }
.map-disclaimer { padding: 0 20px 15px; color: var(--ops-muted); font-size: 11px; line-height: 1.7; }
@media (max-width: 600px) {
  .tunnel-map { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-content: start; gap: 10px; height: auto; min-height: 0; padding: 18px 12px; }
  .tunnel-map .map-grid, .tunnel-map .map-track, .tunnel-map::after { display: none; }
  .tunnel-map .map-node { position: relative; inset: auto !important; display: flex; align-items: center; gap: 10px; min-width: 0; min-height: 44px; padding: 10px; border: 1px solid var(--ops-line); transform: none !important; animation: none; }
  .tunnel-map .map-node i { flex-shrink: 0; }
  .tunnel-map .map-node span { min-width: 0; overflow-wrap: anywhere; white-space: normal; }
  .tunnel-map .map-legend { grid-column: 1 / -1; position: static; margin-top: 8px; }
}
</style>
