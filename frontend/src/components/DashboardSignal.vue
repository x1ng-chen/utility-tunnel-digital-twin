<script setup lang="ts">
import { computed } from 'vue';
import OpsChart from './ui/OpsChart.vue';
import type { Telemetry } from '../types';
import { selectSignalWindow } from '../utils/dashboardSignal';

const props = defineProps<{ selected: Telemetry | null; samples: Telemetry[]; offline: boolean; threshold?: number }>();
const window = computed(() => selectSignalWindow(props.samples, props.selected));
const labels = computed(() => window.value.map((item) => new Date(item.recordedAt).toLocaleTimeString('zh-CN')));
const series = computed(() => [{ name: props.selected?.metric || '采集值', data: window.value.map((item) => item.value), color: '#38bdf8' }]);
const value = computed(() => props.selected && props.selected.quality !== 'missing' && Number.isFinite(props.selected.value)
  ? new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(props.selected.value) : '--');
const quality = computed(() => props.selected ? { good: '良好', suspect: '需核查', bad: '异常', missing: '缺失' }[props.selected.quality] : '暂无数据');
const collectedAt = computed(() => props.selected && Number.isFinite(Date.parse(props.selected.recordedAt))
  ? new Date(props.selected.recordedAt).toLocaleString('zh-CN') : '暂无采集时间');
</script>

<template>
  <article class="panel signal-panel dashboard-signal" :class="{ 'is-offline': offline }">
    <header class="panel-head">
      <div><span class="eyebrow">设备监测</span><h2>设备环境信号</h2></div>
      <span class="signal-state">{{ offline ? '离线 · 保留历史数据' : '最近上报' }}</span>
    </header>
    <div class="signal-reading">
      <p>{{ selected?.metric || '等待设备上报' }}<span>{{ selected?.assetCode || '尚无监测设备' }}</span></p>
      <div><strong>{{ value }}</strong><span>{{ selected?.unit }}</span></div>
      <time :datetime="selected?.recordedAt">采集于 {{ collectedAt }}</time>
    </div>
    <OpsChart v-if="window.length > 1" compact :labels="labels" :series="series" :threshold="threshold" />
    <div v-else class="signal-empty" role="status">{{ window.length ? '已收到首条记录，等待更多数据形成趋势。' : '暂无可绘制的同类数据，收到有效记录后自动更新。' }}</div>
    <footer class="signal-summary"><span>数据质量 <b>{{ quality }}</b></span><span>同设备同指标 · {{ window.length }} 条</span><RouterLink :to="selected ? { path: '/telemetry', query: { assetCode: selected.assetCode, metricKey: selected.metricKey } } : '/telemetry'">查看数据 →</RouterLink></footer>
  </article>
</template>

<style scoped>
.signal-state { color: #9fb4c8; font-size: 12px; text-align: right; }
.signal-reading { padding: 22px 24px 10px; }
.signal-reading p { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin: 0 0 14px; color: #cbd7e5; }
.signal-reading p span, .signal-reading time { color: #9fb4c8; font-size: 12px; }
.signal-reading strong { font-size: clamp(36px, 4vw, 56px); line-height: 1.2; font-variant-numeric: tabular-nums; }
.signal-reading div > span { margin-left: 8px; color: #9fb4c8; }
.signal-reading time { display: block; margin-top: 12px; }
.signal-empty { display: grid; place-items: center; min-height: 140px; padding: 24px; color: #9fb4c8; text-align: center; line-height: 1.8; }
.signal-summary { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; margin: 0 24px; padding: 16px 0; border-top: 1px solid #294055; font-size: 12px; color: #9fb4c8; }
.signal-summary b { margin-left: 6px; color: #dce7f2; }
.signal-summary a { color: #56e8cc; white-space: nowrap; }
.is-offline .signal-reading strong { color: #9aaabc; }
</style>
