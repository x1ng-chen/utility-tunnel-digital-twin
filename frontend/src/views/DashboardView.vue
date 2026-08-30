<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';

const store = useOperationsStore();
const bars = computed(() => {
  const signal = store.dashboard.telemetry?.value ?? 0;
  return Array.from({ length: 28 }, (_, index) => 28 + ((index * 17 + signal) % 62));
});
const reportError = ref('');
const exporting = ref(false);

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
</script>

<template>
  <AppShell>
    <section class="hero">
      <div><span class="eyebrow light">CONTROL ROOM · LIVE FEED</span><h1>运行，一眼掌握</h1><p>集中掌握综合管廊运行状态，所有关键操作均记录审计。</p><p v-if="store.lastSyncedAt">最近同步：{{ new Date(store.lastSyncedAt).toLocaleString('zh-CN') }}</p><p v-if="reportError" class="inline-message error-message" role="alert">{{ reportError }}</p></div>
      <div class="section-actions"><button class="primary-button compact-button" :disabled="store.loading" @click="sync">{{ store.loading ? '同步中…' : '↻ 刷新数据' }}</button><button class="primary-button" :disabled="exporting" @click="report">{{ exporting ? '正在生成…' : '↓ 导出运行快照' }}</button></div>
    </section>
    <section class="metric-grid">
      <article class="metric-card accent-blue"><span>在线设备 <b>↗</b></span><strong>{{ store.dashboard.assets.online }}<small>/ {{ store.dashboard.assets.total }}</small></strong><em>按约定上报周期判定</em></article>
      <article class="metric-card accent-mint"><span>环境健康度 <b>↗</b></span><strong>{{ store.dashboard.health.value }}<small>%</small></strong><em>稳定运行</em></article>
      <article class="metric-card accent-amber"><span>待确认事件 <b>↗</b></span><strong>{{ String(store.openAlerts).padStart(2, '0') }}<small>项</small></strong><em>需关注</em></article>
      <article class="metric-card accent-violet"><span>进行中工单 <b>↗</b></span><strong>{{ String(store.activeOrders).padStart(2, '0') }}<small>项</small></strong><em v-if="store.dashboard.workOrderSla?.overdue">{{ store.dashboard.workOrderSla.overdue }} 项已超时，优先处置</em><em v-else-if="store.dashboard.workOrderSla?.dueSoon">{{ store.dashboard.workOrderSla.dueSoon }} 项将在 4 小时内到期</em><em v-else>处理时限正常</em></article>
    </section>
    <section class="dashboard-grid">
      <article class="panel twin-panel"><div class="panel-head"><div><span class="eyebrow">TWIN PULSE</span><h2>管廊实时态势</h2></div><RouterLink to="/twin-3d">进入三维孪生 →</RouterLink></div><div class="tunnel-map"><div class="map-grid" /><div class="map-track track-one" /><div class="map-track track-two" /><div v-for="asset in store.assets" :key="asset.id" class="map-node" :class="asset.status" :style="{ left: `${asset.position.x}%`, top: `${asset.position.y}%` }"><i /><span>{{ asset.code }}</span></div><div class="map-legend"><span><i class="normal" />正常 {{ store.assets.filter((item) => item.status === 'normal').length }}</span><span><i class="warning" />关注 {{ store.assets.filter((item) => item.status !== 'normal').length }}</span></div></div></article>
      <article class="panel signal-panel"><div class="panel-head"><div><span class="eyebrow">LIVE SIGNAL</span><h2>设备环境信号</h2></div><span class="live-dot">● 最新采集值</span></div><div class="signal-value"><strong>{{ store.dashboard.telemetry?.value.toFixed(0) || '--' }}</strong><span>{{ store.dashboard.telemetry?.unit }}</span><small>{{ store.dashboard.telemetry?.assetCode || '--' }} · {{ store.dashboard.telemetry?.metric || '暂无遥测' }}</small></div><div class="chart-bars"><i v-for="(height, index) in bars" :key="index" :style="{ height: `${height}%` }" :class="{ current: index > 20 }" /></div><div class="chart-meta"><span>运行记录</span><b>质量：{{ store.dashboard.telemetry?.quality || '暂无' }}</b><span>当前</span></div></article>
    </section>
    <section class="dashboard-grid lower-grid"><article class="panel activity-panel"><div class="panel-head"><div><span class="eyebrow">ACTIVITY STREAM</span><h2>最新运行动态</h2></div><RouterLink to="/audit">审计追踪 →</RouterLink></div><div v-for="item in store.audit.slice(0, 4)" :key="item.id" class="activity-item"><i /><time>{{ new Date(item.occurredAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</time><div><b>{{ presentAudit(item).title }}</b><p>{{ presentAudit(item).description }}</p></div></div><div v-if="!store.audit.length" class="empty-state">当前暂无审计记录。</div></article></section>
  </AppShell>
</template>
