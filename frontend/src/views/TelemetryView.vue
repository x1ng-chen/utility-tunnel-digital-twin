<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import OpsChart from '../components/ui/OpsChart.vue';
import { useOperationsStore } from '../stores/operations';
import type { TelemetryQuery } from '../types';

const store = useOperationsStore();
const assetCode = ref('');
const metricKey = ref('');
const quality = ref('');
const recordedFrom = ref('');
const recordedTo = ref('');
const actionError = ref('');

const goodRate = computed(() => store.telemetrySummary.sampleCount ? Math.round(store.telemetrySummary.qualityCounts.good / store.telemetrySummary.sampleCount * 100) : 0);
const trendWindow = computed(() => [...store.telemetryInsights].slice(0, 100).reverse());
const trendLabels = computed(() => trendWindow.value.map((item) => new Date(item.recordedAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })));
const trendSeries = computed(() => [{ name: store.telemetrySummary.latest?.metric || '遥测值', data: trendWindow.value.map((item) => item.value), color: '#38bdf8' }]);
const trendThreshold = computed(() => store.thresholds.find((item) => item.key === store.telemetrySummary.latest?.metricKey)?.warning);
const qualityDonut = computed(() => {
  const total = Math.max(1, store.telemetrySummary.sampleCount);
  const good = store.telemetrySummary.qualityCounts.good / total * 100;
  const suspect = good + store.telemetrySummary.qualityCounts.suspect / total * 100;
  const bad = suspect + store.telemetrySummary.qualityCounts.bad / total * 100;
  return { background: `conic-gradient(#55e3bd 0 ${good}%, #f2b064 ${good}% ${suspect}%, #ff7289 ${suspect}% ${bad}%, #7186a5 ${bad}% 100%)` };
});

function toIso(value: string): string | undefined {
  return value ? new Date(value).toISOString() : undefined;
}

async function search() {
  actionError.value = '';
  const query: TelemetryQuery = {
    assetCode: assetCode.value || undefined,
    metricKey: metricKey.value.trim() || undefined,
    quality: (quality.value || undefined) as TelemetryQuery['quality'],
    recordedFrom: toIso(recordedFrom.value),
    recordedTo: toIso(recordedTo.value),
  };
  try {
    await store.loadTelemetryInsights(query);
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '遥测查询失败，请稍后重试。';
  }
}

function reset() {
  assetCode.value = ''; metricKey.value = ''; quality.value = ''; recordedFrom.value = ''; recordedTo.value = '';
  void search();
}

function qualityLabel(value: string) {
  return ({ good: '良好', suspect: '需关注', bad: '异常', missing: '缺失' } as Record<string, string>)[value] || '未知';
}

onMounted(search);
</script>

<template>
  <AppShell>
    <section class="section-title telemetry-title">
      <div><span class="eyebrow light">运行数据分析</span><h1>数据洞察</h1><p>按采集时间追踪遥测趋势与质量，不承担告警处置或资产维护职责。</p></div>
      <span class="insight-source">运行数据</span>
    </section>

    <form class="telemetry-filters" @submit.prevent="search">
      <label>资产<select v-model="assetCode"><option value="">全部资产</option><option v-for="asset in store.assets" :key="asset.id" :value="asset.code">{{ asset.code }} · {{ asset.name }}</option></select></label>
      <label>指标键<input v-model="metricKey" placeholder="例如 temperature" pattern="[a-z][a-z0-9_.\x2D]{1,39}" /></label>
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
    </section>

    <section class="telemetry-layout">
      <article class="panel telemetry-chart-panel">
        <div class="panel-head"><div><span class="eyebrow">RECENT WINDOW</span><h2>最近 30 条趋势</h2></div><span class="insight-count">显示 {{ store.telemetryInsights.length }} / {{ store.telemetryInsightsTotal }}</span></div>
        <OpsChart v-if="trendWindow.length && store.telemetrySummary.comparable" zoom :labels="trendLabels" :series="trendSeries" :threshold="trendThreshold" />
        <div v-else class="empty-state">{{ trendWindow.length ? '混合指标不可直接比较，请选择单一指标后查看趋势。' : '当前条件下没有遥测趋势。' }}</div>
        <div class="quality-strip"><span><i class="good" />良好 {{ store.telemetrySummary.qualityCounts.good }}</span><span><i class="suspect" />可疑 {{ store.telemetrySummary.qualityCounts.suspect }}</span><span><i class="bad" />异常 {{ store.telemetrySummary.qualityCounts.bad }}</span><span><i class="missing" />缺失 {{ store.telemetrySummary.qualityCounts.missing }}</span></div>
      </article>
      <article class="panel latest-reading-panel"><span class="eyebrow">LATEST SAMPLE</span><template v-if="store.telemetrySummary.latest"><strong>{{ store.telemetrySummary.latest.value }}<small>{{ store.telemetrySummary.latest.unit }}</small></strong><h2>{{ store.telemetrySummary.latest.metric }}</h2><p>{{ store.telemetrySummary.latest.assetCode }} · {{ store.telemetrySummary.latest.metricKey || '未定义监测项目' }}</p><time>{{ new Date(store.telemetrySummary.latest.recordedAt).toLocaleString('zh-CN') }}</time><b :class="store.telemetrySummary.latest.quality">{{ qualityLabel(store.telemetrySummary.latest.quality) }}</b><div class="quality-donut" :style="qualityDonut"><span>{{ goodRate }}%</span><small>可信率</small></div></template><div v-else class="empty-state">暂无最新样本。</div></article>
    </section>

    <section class="table-panel telemetry-table">
      <div class="table-head"><span>采集时间</span><span>资产 / 指标</span><span>数值</span><span>质量</span><span>事件编号</span></div>
      <div v-for="item in store.telemetryInsights" :key="item.id" class="table-row"><time>{{ new Date(item.recordedAt).toLocaleString('zh-CN') }}</time><div><strong>{{ item.metric }}</strong><small>{{ item.assetCode }} · {{ item.metricKey || '未定义' }}</small></div><b>{{ item.value }} {{ item.unit }}</b><span :class="['badge', `quality-${item.quality}`]">{{ qualityLabel(item.quality) }}</span><code>{{ item.eventId || '历史记录' }}</code></div>
      <div v-if="!store.telemetryInsights.length" class="empty-state">当前筛选条件下没有遥测记录。</div>
    </section>
  </AppShell>
</template>
