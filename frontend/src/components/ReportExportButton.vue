<script setup lang="ts">
import { ref } from 'vue';
import { useOperationsStore } from '../stores/operations';
import type { TelemetryQuery } from '../types';
const props = defineProps<{ report: 'alerts' | 'assets' | 'telemetry'; label: string; filters?: TelemetryQuery }>();
const store = useOperationsStore();
const busy = ref(false);
const error = ref('');
async function download() {
  if (busy.value || store.offline || store.source !== 'api') return;
  busy.value = true; error.value = '';
  try { await store.createReport(props.report, props.filters); }
  catch { error.value = '导出未完成，请检查网络后重试。'; }
  finally { busy.value = false; }
}
</script>
<template>
  <div class="report-export-action">
    <button type="button" :disabled="busy || store.offline || store.source !== 'api'" :aria-busy="busy" :title="filters ? '将当前已提交筛选固化为可复核 CSV 快照。' : '导出服务端全部记录，不受当前页面筛选和分页限制。'" @click="download">{{ busy ? '正在生成…' : label }}</button>
    <small>{{ filters ? '当前筛选 · CSV 快照' : '全部记录 · CSV' }}</small>
    <span v-if="error" role="alert">{{ error }}</span>
  </div>
</template>
<style scoped>
.report-export-action { display: grid; gap: 5px; justify-items: end; max-width: 100%; }
button { min-height: 40px; padding: 8px 12px; border: 1px solid var(--ops-line); color: var(--ops-signal); background: var(--ops-panel); }
button:disabled { opacity: .5; }
small { color: var(--ops-muted); font-size: 10px; }
span { color: var(--ops-danger); font-size: 12px; }
</style>
