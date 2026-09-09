<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import TelemetryTrendChart from '../components/TelemetryTrendChart.vue';
import ReportExportButton from '../components/ReportExportButton.vue';
import { useOperationsStore } from '../stores/operations';
import type { Alert, TelemetryQuery } from '../types';
import { api } from '../services/api';
import { telemetryTrend } from '../utils/telemetryTrend';

const store = useOperationsStore();
const route = useRoute();
const router = useRouter();
const assetCode = ref('');
const metricKey = ref('');
const quality = ref('');
const recordedFrom = ref('');
const recordedTo = ref('');
const actionError = ref('');
const historyPage = ref(1);
const appliedQuery = ref<TelemetryQuery>({});
let searchSequence = 0;
const pageCount = computed(() => Math.max(1, Math.ceil(store.telemetryInsightsTotal / 100)));
const historyEvents = ref<Alert[]>([]);
const eventsError = ref('');
const eventsLoading = ref(false);
const eventsTotal = ref(0);
let eventSequence = 0;
let eventPage = 0;
let eventParams: Record<string, string> | null = null;
const alertTotal = ref<number | null>(null);
let alertCountSequence = 0;
const metricOptions = computed(() => {
  const options = new Map(store.thresholds.map((item) => [item.key, item.label]));
  for (const item of [...store.telemetry, ...store.telemetryInsights]) {
    if (item.metricKey) options.set(item.metricKey, item.metric);
  }
  if (metricKey.value && !options.has(metricKey.value)) options.set(metricKey.value, '当前指定监测项目');
  return [...options].map(([key, label]) => ({ key, label }));
});

const goodRate = computed(() => store.telemetrySummary.sampleCount ? Math.round(store.telemetrySummary.qualityCounts.good / store.telemetrySummary.sampleCount * 100) : 0);
const trendSeries = computed(() => telemetryTrend(store.telemetryInsights, store.telemetrySummary.latest));
const trendPointCount = computed(() => trendSeries.value.reduce((count, series) => count + series.data.filter(point => point[1] !== null).length, 0));
const spanLabel = computed(() => formatSpan(store.telemetrySummary.startedAt, store.telemetrySummary.endedAt));
const spanRange = computed(() => {
  const { startedAt, endedAt } = store.telemetrySummary;
  if (!startedAt || !endedAt) return '按真实采集时间的样本最早—最晚跨度';
  return `最早 ${new Date(startedAt).toLocaleString('zh-CN')} · 最晚 ${new Date(endedAt).toLocaleString('zh-CN')}`;
});
function formatSpan(startedAt: string | null, endedAt: string | null): string {
  if (!startedAt || !endedAt) return '--';
  const milliseconds = Date.parse(endedAt) - Date.parse(startedAt);
  if (!Number.isFinite(milliseconds) || milliseconds < 0) return '--';
  const totalSeconds = Math.floor(milliseconds / 1000);
  if (totalSeconds < 60) return `${totalSeconds} 秒`;
  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时 ${minutes % 60} 分`;
  const days = Math.floor(hours / 24);
  return `${days} 天 ${hours % 24} 小时`;
}
watch(trendSeries, (series) => {
  ++eventSequence;
  eventPage = 0; eventParams = null;
  historyEvents.value = []; eventsTotal.value = 0; eventsError.value = ''; eventsLoading.value = false;
  const times = series.flatMap(item => item.data.map(point => point[0]));
  if (!times.length || store.source !== 'api') return;
  eventParams = { openedFrom: new Date(Math.min(...times)).toISOString(),
    openedTo: new Date(Math.max(...times)).toISOString(), assetCodes: series.map(item => item.name).join(',') };
  void loadMoreEvents();
}, { immediate: true });

async function loadMoreEvents() {
  if (!eventParams || eventsLoading.value) return;
  const sequence = eventSequence;
  const nextPage = eventPage + 1;
  eventsLoading.value = true;
  eventsError.value = '';
  try {
    const response = await api.alerts({ ...eventParams, page: nextPage, pageSize: 100 });
    if (sequence !== eventSequence) return;
    const records = new Map(historyEvents.value.map(event => [event.id, event]));
    for (const event of response.data.items as Alert[]) records.set(event.id, event);
    historyEvents.value = [...records.values()];
    eventPage = nextPage;
    eventsTotal.value = response.data.total;
  } catch {
    if (sequence === eventSequence) eventsError.value = '告警事件加载失败，趋势数据仍可查看。';
  } finally {
    if (sequence === eventSequence) eventsLoading.value = false;
  }
}
onUnmounted(() => { eventSequence++; alertCountSequence++; });

function readUrlValue(key: string): string {
  const value = route.query[key];
  return typeof value === 'string' ? value : '';
}

function applyUrlState() {
  assetCode.value = readUrlValue('assetCode');
  metricKey.value = readUrlValue('metricKey');
  quality.value = readUrlValue('quality');
  recordedFrom.value = readUrlValue('recordedFrom');
  recordedTo.value = readUrlValue('recordedTo');
  const page = Number(route.query.page);
  historyPage.value = Number.isInteger(page) && page >= 1 ? page : 1;
}

function writeUrlState(page = historyPage.value) {
  const query: Record<string, string> = {};
  if (assetCode.value) query.assetCode = assetCode.value;
  if (metricKey.value) query.metricKey = metricKey.value;
  if (quality.value) query.quality = quality.value;
  if (recordedFrom.value) query.recordedFrom = recordedFrom.value;
  if (recordedTo.value) query.recordedTo = recordedTo.value;
  if (page > 1) query.page = String(page);
  void router.replace({ query });
}

function alertCountParams(): Record<string, string> {
  const query = appliedQuery.value;
  const params: Record<string, string> = {};
  if (query.assetCode) params.assetCode = query.assetCode;
  if (query.recordedFrom) params.openedFrom = query.recordedFrom;
  if (query.recordedTo) params.openedTo = query.recordedTo;
  return params;
}

async function loadAlertCount() {
  const sequence = ++alertCountSequence;
  if (store.source === 'demo') {
    const query = appliedQuery.value;
    const from = query.recordedFrom ? Date.parse(query.recordedFrom) : Number.NEGATIVE_INFINITY;
    const to = query.recordedTo ? Date.parse(query.recordedTo) : Number.POSITIVE_INFINITY;
    alertTotal.value = store.alerts.filter((alert) => (!query.assetCode || alert.assetCode === query.assetCode) && Date.parse(alert.openedAt) >= from && Date.parse(alert.openedAt) <= to).length;
    return;
  }
  alertTotal.value = null;
  try {
    const response = await api.alerts({ ...alertCountParams(), page: 1, pageSize: 1 });
    if (sequence === alertCountSequence) alertTotal.value = response.data.total;
  } catch {
    if (sequence === alertCountSequence) alertTotal.value = null;
  }
}

function toIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) throw new Error('请输入有效的采集时间。');
  return date.toISOString();
}

function buildQuery(): TelemetryQuery {
  return {
    assetCode: assetCode.value || undefined,
    metricKey: metricKey.value.trim() || undefined,
    quality: (quality.value || undefined) as TelemetryQuery['quality'],
    recordedFrom: toIso(recordedFrom.value),
    recordedTo: toIso(recordedTo.value),
  };
}

async function runSearch(page: number) {
  const sequence = ++searchSequence;
  actionError.value = '';
  alertTotal.value = null;
  try {
    const query = buildQuery();
    const accepted = await store.loadTelemetryInsights(query, page);
    if (accepted === false || sequence !== searchSequence) return;
    appliedQuery.value = { ...query };
    historyPage.value = page;
    writeUrlState(page);
    void loadAlertCount();
  } catch (cause) {
    if (sequence !== searchSequence) return;
    actionError.value = cause instanceof Error ? cause.message : '遥测查询失败，请稍后重试。';
  }
}

function search() {
  void runSearch(1);
}

async function changePage(next: number) {
  if (store.telemetryInsightsLoading || next < 1 || next > pageCount.value) return;
  const sequence = ++searchSequence;
  actionError.value = '';
  try {
    const accepted = await store.loadTelemetryInsights(appliedQuery.value, next);
    if (accepted !== false && sequence === searchSequence) {
      historyPage.value = next;
      writeUrlState(next);
    }
  } catch (cause) {
    if (sequence === searchSequence) actionError.value = cause instanceof Error ? cause.message : '翻页失败，请重试。';
  }
}

function reset() {
  assetCode.value = ''; metricKey.value = ''; quality.value = ''; recordedFrom.value = ''; recordedTo.value = '';
  void search();
}

function qualityLabel(value: string) {
  return ({ good: '良好', suspect: '需关注', bad: '异常', missing: '缺失' } as Record<string, string>)[value] || '未知';
}

function snapshot() {
  return JSON.stringify([assetCode.value, metricKey.value, quality.value, recordedFrom.value, recordedTo.value, historyPage.value]);
}
onMounted(() => {
  applyUrlState();
  void runSearch(historyPage.value);
});
watch(() => route.query, () => {
  const before = snapshot();
  applyUrlState();
  if (snapshot() !== before) void runSearch(historyPage.value);
});
watch(() => store.source, (next, previous) => {
  if (next !== previous) void runSearch(historyPage.value);
});
</script>

<template>
  <AppShell>
    <section class="section-title telemetry-title">
      <div><span class="eyebrow light">运行数据分析</span><h1>数据洞察</h1><p>按采集时间追踪遥测趋势与质量，不承担告警处置或资产维护职责。</p></div>
      <ReportExportButton report="telemetry" label="导出全部历史记录" />
    </section>

    <form class="telemetry-filters" @submit.prevent="search">
      <label>资产<select v-model="assetCode"><option value="">全部资产</option><option v-for="asset in store.assets" :key="asset.id" :value="asset.code">{{ asset.code }} · {{ asset.name }}</option></select></label>
      <label>监测项目<select v-model="metricKey"><option value="">全部监测项目</option><option v-for="item in metricOptions" :key="item.key" :value="item.key">{{ item.label }}</option></select></label>
      <label>质量<select v-model="quality"><option value="">全部质量</option><option value="good">良好</option><option value="suspect">可疑</option><option value="bad">异常</option><option value="missing">缺失</option></select></label>
      <label>开始时间<input v-model="recordedFrom" type="datetime-local" /></label>
      <label>结束时间<input v-model="recordedTo" type="datetime-local" /></label>
      <div class="telemetry-filter-actions"><button type="button" @click="reset">重置</button><button class="primary-button" :disabled="store.telemetryInsightsLoading" type="submit">{{ store.telemetryInsightsLoading ? '查询中…' : '查询数据' }}</button></div>
    </form>
    <p v-if="actionError" class="inline-message error-message" role="alert">{{ actionError }}</p>

    <section class="insight-metrics">
      <article><span>样本总量</span><strong>{{ store.telemetrySummary.sampleCount }}</strong><small>当前条件内全部记录</small></article>
      <article><span>平均值</span><strong>{{ store.telemetrySummary.average == null ? '--' : store.telemetrySummary.average.toFixed(2) }}</strong><small>{{ store.telemetrySummary.comparable ? (store.telemetrySummary.latest?.unit || '暂无单位') : '请选择单一指标' }}</small></article>
      <article><span>值域范围</span><strong>{{ store.telemetrySummary.minimum == null ? '--' : `${store.telemetrySummary.minimum}—${store.telemetrySummary.maximum}` }}</strong><small>最小值—最大值</small></article>
      <article><span>良好率</span><strong>{{ goodRate }}<em>%</em></strong><small>{{ store.telemetrySummary.qualityCounts.good }} 条可信样本</small></article>
      <article><span>报警次数</span><strong>{{ alertTotal == null ? '--' : alertTotal }}</strong><small>资产与时间范围告警总数</small></article>
      <article><span>采集时段</span><strong>{{ spanLabel }}</strong><small>{{ spanRange }}</small></article>
    </section>

    <section class="telemetry-layout">
      <article class="panel telemetry-chart-panel">
        <div class="panel-head"><div><span class="eyebrow">历史测点对比</span><h2>{{ store.telemetrySummary.latest?.metric || '监测趋势' }}</h2><p>同指标、同单位 · {{ trendSeries.length }} 个设备 · {{ trendPointCount }} 个有效测点。点击图例筛选，拖动底部滑块查看时段。</p><p>基于第 {{ historyPage }} 页的 {{ store.telemetryInsights.length }} 条记录；按真实采集时间绘制，缺失值不补线。全部项目时以最新样本的指标为准。</p></div></div>
        <TelemetryTrendChart v-if="trendPointCount" :series="trendSeries" :unit="store.telemetrySummary.latest?.unit || ''" :events="historyEvents" />
        <div v-else class="empty-state">当前条件下没有可绘制的监测数据。</div>
        <section class="history-events" aria-label="趋势时段告警事件">
          <h3>同时间段告警事件</h3>
          <p>虚线标记告警产生时间，不代表因果关系。仅匹配本页曲线设备。</p>
          <p v-if="store.source !== 'api'">连接数据服务后可查询历史告警事件。</p>
          <p v-else-if="eventsLoading" role="status">正在加载告警事件…</p>
          <p v-else-if="eventsError" role="alert">{{ eventsError }}</p>
          <p v-else-if="!historyEvents.length">已加载范围内没有匹配事件。</p>
          <p v-if="eventsTotal">本页趋势时段及设备共 {{ eventsTotal }} 条告警，已加载 {{ historyEvents.length }} 条。</p>
          <button v-if="eventsError || historyEvents.length < eventsTotal" type="button" :disabled="eventsLoading" @click="loadMoreEvents">{{ eventsLoading ? '加载中…' : eventsError ? '重试加载事件' : '加载更多事件' }}</button>
          <article v-for="event in historyEvents" :key="event.id">
            <time>{{ new Date(event.openedAt).toLocaleString('zh-CN') }}</time>
            <strong>{{ event.code }} · {{ event.title }}</strong>
            <span>{{ event.assetCode }} · {{ event.severity === 'critical' ? '严重' : event.severity === 'warning' ? '警告' : '提示' }}</span>
          </article>
        </section>
        <div class="quality-strip"><span><i class="good" />良好 {{ store.telemetrySummary.qualityCounts.good }}</span><span><i class="suspect" />可疑 {{ store.telemetrySummary.qualityCounts.suspect }}</span><span><i class="bad" />异常 {{ store.telemetrySummary.qualityCounts.bad }}</span><span><i class="missing" />缺失 {{ store.telemetrySummary.qualityCounts.missing }}</span></div>
      </article>
      <article class="panel latest-reading-panel">
        <h2>最新采集样本</h2>
        <template v-if="store.telemetrySummary.latest">
          <strong>{{ store.telemetrySummary.latest.value }}<small>{{ store.telemetrySummary.latest.unit }}</small></strong>
          <h3>{{ store.telemetrySummary.latest.metric }}</h3>
          <p>{{ store.telemetrySummary.latest.assetCode }} · {{ store.telemetrySummary.latest.metricKey || '未定义监测项目' }}</p>
          <time>{{ new Date(store.telemetrySummary.latest.recordedAt).toLocaleString('zh-CN') }}</time>
          <b :class="store.telemetrySummary.latest.quality">{{ qualityLabel(store.telemetrySummary.latest.quality) }}</b>
          <div class="query-quality"><span>当前查询样本良好率</span><strong>{{ goodRate }}%</strong><small>良好 {{ store.telemetrySummary.qualityCounts.good }} / 全部 {{ store.telemetrySummary.sampleCount }}</small></div>
        </template>
        <div v-else class="empty-state">暂无最新样本。</div>
      </article>
    </section>

    <section class="table-panel telemetry-table">
      <nav class="history-pagination" aria-label="历史采集记录分页">
        <span>第 {{ historyPage }} / {{ pageCount }} 页 · 每页 100 条</span>
        <button type="button" :disabled="store.telemetryInsightsLoading || historyPage <= 1" @click="changePage(historyPage - 1)">上一页</button>
        <button type="button" :disabled="store.telemetryInsightsLoading || historyPage >= pageCount" @click="changePage(historyPage + 1)">下一页</button>
      </nav>
      <header class="panel-head"><h2>采集记录</h2><span>本页 {{ store.telemetryInsights.length }} 条 / 共 {{ store.telemetryInsightsTotal }} 条</span></header>
      <div class="table-head"><span>采集时间</span><span>资产 / 指标</span><span>数值</span><span>质量</span><span>事件编号</span></div>
      <div v-for="item in store.telemetryInsights" :key="item.id" class="table-row"><time>{{ new Date(item.recordedAt).toLocaleString('zh-CN') }}</time><div><strong>{{ item.metric }}</strong><small>{{ item.assetCode }} · {{ item.metricKey || '未定义' }}</small></div><b>{{ item.value }} {{ item.unit }}</b><span :class="['badge', `quality-${item.quality}`]">{{ qualityLabel(item.quality) }}</span><code>{{ item.eventId || '历史记录' }}</code></div>
      <div v-if="!store.telemetryInsights.length" class="empty-state">当前筛选条件下没有遥测记录。</div>
    </section>
  </AppShell>
</template>

<style scoped>
.history-events { padding: 16px 20px; border-top: 1px solid var(--ops-line); }
.history-events h3 { margin: 0 0 8px; font-size: 14px; }
.history-events p, .history-events time, .history-events span { color: var(--ops-muted); font-size: 12px; line-height: 1.7; }
.history-events article { display: grid; gap: 5px; padding: 10px 0; border-top: 1px solid var(--ops-line); overflow-wrap: anywhere; }
.history-events strong { font-size: 13px; }
.latest-reading-panel h2 { font-size: 16px; margin: 0 0 16px; }
.latest-reading-panel h3 { font-size: 16px; margin: 12px 0; }
.query-quality { display: grid; gap: 8px; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--ops-line); }
.query-quality span, .query-quality small { color: var(--ops-muted); font-size: 12px; }
.query-quality strong { font-size: 24px; }
.history-pagination { display: flex; justify-content: flex-end; align-items: center; flex-wrap: wrap; gap: 12px; padding: 16px; border-bottom: 1px solid var(--ops-line); }
.history-pagination span { margin-right: auto; color: var(--ops-muted); font-size: 12px; }
.history-pagination button { min-height: 44px; padding: 8px 16px; }
.telemetry-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: 16px !important;
  padding: 20px !important;
  background: var(--ops-panel) !important;
}
.telemetry-filters label { display: grid; gap: 8px; min-width: 0; padding: 0; }
.telemetry-filters input, .telemetry-filters select { width: 100%; min-width: 0; min-height: 44px; }
.telemetry-filter-actions { grid-column: auto; display: flex; gap: 10px; align-items: end; justify-content: flex-end; }
.telemetry-filter-actions button { min-height: 44px; white-space: nowrap; }
.insight-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.insight-metrics article { min-width: 0; padding: 22px; }
.insight-metrics strong { font-size: clamp(24px, 2.5vw, 38px); overflow-wrap: anywhere; }
.telemetry-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(240px, 1fr); gap: 20px; }
.telemetry-layout > article { min-width: 0; }
.telemetry-chart-panel .panel-head p { color: var(--ops-muted); font-size: 12px; line-height: 1.6; margin: 8px 0 0; }
.telemetry-table .panel-head { gap: 12px; flex-wrap: wrap; }
.telemetry-table .panel-head > span { color: var(--ops-muted); font-size: 12px; }
.telemetry-table .table-head, .telemetry-table .table-row { display: grid; grid-template-columns: minmax(140px, 1fr) minmax(140px, 1.2fr) minmax(90px, .7fr) 76px minmax(100px, 1fr); gap: 16px; }
.telemetry-table .table-row > * { min-width: 0; overflow-wrap: anywhere; }
.telemetry-table code { font-size: 11px; color: var(--ops-muted); white-space: normal; }
@container (max-width: 1000px) {
  .telemetry-filters { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
  .telemetry-layout { grid-template-columns: minmax(0, 1fr); }
  .telemetry-table .table-head { display: none !important; }
  .telemetry-table .table-row { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 80px; }
  .telemetry-table .table-row > time { grid-column: 1 / -1; color: var(--ops-muted); font-size: 12px; }
  .telemetry-table .table-row > code { grid-column: 1 / -1; }
  .insight-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@container (max-width: 480px) {
  .telemetry-filters { grid-template-columns: minmax(0, 1fr) !important; }
  .telemetry-filter-actions { justify-content: stretch; }
  .telemetry-filter-actions button { flex: 1; }
  .telemetry-table .table-row { grid-template-columns: minmax(0, 1fr) 80px; }
  .telemetry-table .table-row > div { grid-column: 1 / -1; }
}
</style>
