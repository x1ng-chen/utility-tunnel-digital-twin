<script setup lang="ts">
import { computed, ref } from 'vue';
import { Download, Lightbulb, RefreshCw, TrendingUp } from 'lucide-vue-next';
import AppShell from '../components/AppShell.vue';
import OpsChart from '../components/ui/OpsChart.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';

const store = useOperationsStore();
const auth = useAuthStore();
const signalWindow = computed(() => [...store.telemetry].slice(0, 30).reverse());
const signalLabels = computed(() => signalWindow.value.map((item) => new Date(item.recordedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })));
const signalSeries = computed(() => [{ name: store.dashboard.telemetry?.metric || '遥测值', data: signalWindow.value.map((item) => item.value), color: '#38bdf8' }]);
const signalThreshold = computed(() => store.thresholds.find((item) => item.key === store.dashboard.telemetry?.metricKey)?.warning);
const reportError = ref('');
const exporting = ref(false);
const commandError = ref('');
const commandResult = ref('');
const commandSending = ref(false);
const canControlLighting = computed(() => store.source === 'api' && ['operator', 'administrator'].includes(auth.user?.role || ''));

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
      <article class="metric-card accent-mint" data-index="02"><span>环境健康度 <TrendingUp /></span><strong>{{ store.dashboard.health.value }}<small>%</small></strong><em>稳定运行</em></article>
      <article class="metric-card accent-amber" data-index="03"><span>待确认事件 <TrendingUp /></span><strong>{{ String(store.openAlerts).padStart(2, '0') }}<small>项</small></strong><em>需关注</em></article>
      <article class="metric-card accent-violet" data-index="04"><span>进行中工单 <TrendingUp /></span><strong>{{ String(store.activeOrders).padStart(2, '0') }}<small>项</small></strong><em v-if="store.dashboard.workOrderSla?.overdue">{{ store.dashboard.workOrderSla.overdue }} 项已超时，优先处置</em><em v-else-if="store.dashboard.workOrderSla?.dueSoon">{{ store.dashboard.workOrderSla.dueSoon }} 项将在 4 小时内到期</em><em v-else>处理时限正常</em></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel twin-panel"><div class="panel-head"><div><span class="eyebrow">TWIN PULSE</span><h2>管廊实时态势</h2></div><RouterLink to="/twin-3d">进入三维孪生 →</RouterLink></div><div class="tunnel-map"><div class="map-grid" /><div class="map-track track-one" /><div class="map-track track-two" /><div v-for="asset in store.assets" :key="asset.id" class="map-node" :class="asset.status" :style="{ left: `${asset.position.x}%`, top: `${asset.position.y}%` }"><i /><span>{{ asset.code }}</span></div><div class="map-legend"><span><i class="normal" />正常 {{ store.assets.filter((item) => item.status === 'normal').length }}</span><span><i class="warning" />关注 {{ store.assets.filter((item) => item.status !== 'normal').length }}</span></div></div></article>
      <article class="panel signal-panel"><div class="panel-head"><div><span class="eyebrow">LIVE SIGNAL</span><h2>设备环境信号</h2></div><span class="live-dot">最新采集值</span></div><div class="signal-value"><strong>{{ store.dashboard.telemetry?.value.toFixed(0) || '--' }}</strong><span>{{ store.dashboard.telemetry?.unit }}</span><small>{{ store.dashboard.telemetry?.assetCode || '--' }} · {{ store.dashboard.telemetry?.metric || '暂无遥测' }}</small></div><OpsChart compact :labels="signalLabels" :series="signalSeries" :threshold="signalThreshold" /><div class="chart-meta"><span>运行记录</span><b>质量：{{ store.dashboard.telemetry?.quality === 'good' ? '良好' : store.dashboard.telemetry?.quality === 'suspect' ? '需关注' : store.dashboard.telemetry?.quality === 'bad' ? '异常' : store.dashboard.telemetry?.quality === 'missing' ? '缺失' : '暂无' }}</b><span>当前</span></div></article>
    </section>
    <section class="dashboard-grid lower-grid"><article class="panel activity-panel"><div class="panel-head"><div><span class="eyebrow">ACTIVITY STREAM</span><h2>最新运行动态</h2></div><RouterLink to="/audit">审计追踪 →</RouterLink></div><div v-for="item in store.audit.slice(0, 4)" :key="item.id" class="activity-item"><i /><time>{{ new Date(item.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><div><b>{{ presentAudit(item).title }}</b><p>{{ presentAudit(item).description }}</p></div></div><div v-if="!store.audit.length" class="empty-state">当前暂无审计记录。</div></article><article class="panel control-panel"><div class="panel-head"><div><span class="eyebrow">CTRL-01 · MQTT</span><h2>灯带联调</h2></div><Lightbulb /></div><p>仅限已登录的运维员或管理员；每次操作均生成唯一命令并写入审计。</p><div class="lighting-actions"><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_blue')">蓝色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_green')">绿色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_red')">红色</button><button :disabled="!canControlLighting || commandSending" @click="testLighting('led_off')">熄灭</button></div><small v-if="!canControlLighting">请使用在线 API 模式并以运维员或管理员身份登录。</small><b v-if="commandResult" class="command-ok">{{ commandResult }}</b><b v-if="commandError" class="command-error">{{ commandError }}</b></article></section>
  </AppShell>
</template>
