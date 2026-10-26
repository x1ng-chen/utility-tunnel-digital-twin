<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent } from 'echarts/components';
import type { Alert } from '../types';
import { telemetryEventSeries } from '../utils/telemetryEvents';
use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, MarkLineComponent]);
const props = defineProps<{ series: Array<{ name: string; data: Array<[number, number | null]> }>; unit: string; events?: Alert[] }>();
// Expose the rendered alert-marker contract to the DOM so browser tests can
// verify the chart actually drew markers, not just that an event list exists.
const validEvents = computed(() => (props.events ?? []).filter((event) => Number.isFinite(Date.parse(event.openedAt))));
const marklineCount = computed(() => validEvents.value.length);
const marklineTimes = computed(() => validEvents.value.map((event) => Date.parse(event.openedAt)).join(','));
const option = computed(() => ({
  animation: false,
  color: ['#1766c3', '#147d64', '#7551bd', '#a45f13', '#b93451', '#517914'],
  tooltip: { trigger: 'axis', renderMode: 'richText', backgroundColor: '#ffffff', borderColor: '#c5d5e8', textStyle: { color: '#1c3049' } },
  legend: { type: 'scroll', data: props.series.map(series => series.name), textStyle: { color: '#53657b' }, top: 0 },
  grid: { left: 64, right: 24, top: 56, bottom: 72 },
  xAxis: { type: 'time', axisLine: { lineStyle: { color: '#c5d5e8' } }, axisLabel: { color: '#53657b' } },
  yAxis: { type: 'value', name: props.unit, scale: true, axisLabel: { color: '#53657b' },
    nameTextStyle: { color: '#53657b' }, splitLine: { lineStyle: { color: 'rgba(148,172,202,.24)' } } },
  dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 20, borderColor: '#c5d5e8', backgroundColor: '#f8fafc', fillerColor: 'rgba(23,102,195,.14)', textStyle: { color: '#53657b' }, dataBackground: { lineStyle: { color: '#94afd0' }, areaStyle: { color: '#dce8f7' } } }],
  series: [...props.series.map(series => ({ ...series, type: 'line', smooth: false,
    connectNulls: false, showSymbol: true, symbolSize: 5, emphasis: { focus: 'series' } })),
    telemetryEventSeries(props.events || [])],
}));
</script>

<template>
  <div class="telemetry-history-chart-host" :data-markline-count="marklineCount" :data-markline-times="marklineTimes">
    <VChart class="telemetry-history-chart" :option="option" autoresize aria-label="同指标多设备历史趋势" />
  </div>
</template>

<style scoped>
.telemetry-history-chart-host { width: 100%; height: 340px; min-width: 0; }
.telemetry-history-chart { width: 100%; height: 100%; min-width: 0; }
</style>
