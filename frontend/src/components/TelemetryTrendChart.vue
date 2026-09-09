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
  color: ['#38bdf8', '#55e3bd', '#c4b5fd', '#f2b064', '#ff7289', '#a3e635'],
  tooltip: { trigger: 'axis', renderMode: 'richText' },
  legend: { type: 'scroll', data: props.series.map(series => series.name), textStyle: { color: '#a8bacb' }, top: 0 },
  grid: { left: 64, right: 24, top: 56, bottom: 72 },
  xAxis: { type: 'time', axisLabel: { color: '#a8bacb' } },
  yAxis: { type: 'value', name: props.unit, scale: true, axisLabel: { color: '#a8bacb' },
    nameTextStyle: { color: '#a8bacb' }, splitLine: { lineStyle: { color: '#243746' } } },
  dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 20 }],
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
