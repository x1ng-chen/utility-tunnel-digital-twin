<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { Threshold } from '../types';

const store = useOperationsStore();
const auth = useAuthStore();
const canWrite = computed(() => !store.offline && auth.user?.role === 'administrator');
const message = ref('');
const drafts = reactive<Record<string, { warning: number; alarm: number }>>({});

watch(() => store.thresholds.map((item) => ({ key: item.key, warning: item.warning, alarm: item.alarm })), (items) => {
  items.forEach((item) => {
    drafts[item.key] = { warning: item.warning, alarm: item.alarm };
  });
}, { immediate: true, deep: true });

function draft(item: Threshold) {
  return drafts[item.key] || (drafts[item.key] = { warning: item.warning, alarm: item.alarm });
}

async function save(item: Threshold) {
  message.value = '';
  const values = draft(item);
  try {
    await store.updateThreshold(item, values.warning, values.alarm);
    message.value = `${item.label} 已保存`;
  } catch (cause) {
    message.value = cause instanceof Error ? cause.message : '保存失败';
  }
}
</script>

<template>
  <AppShell>
    <section class="section-title"><div><span class="eyebrow light">SYSTEM CONFIGURATION</span><h1>系统配置</h1><p>管理告警阈值与数据源，管理员变更会写入审计日志。</p></div><span class="config-source"><i />{{ store.source === 'api' ? 'Django API' : '本地演示数据' }}</span></section>
    <section class="settings-panel">
      <div class="settings-head"><span>阈值策略</span><small>报警值必须高于预警值</small></div>
      <div v-for="item in store.thresholds" :key="item.key" class="threshold-row">
        <div><b>{{ item.label }}</b><small>{{ item.key }} · {{ item.unit }}</small></div>
        <label>预警<input v-model.number="draft(item).warning" :disabled="!canWrite" type="number" min="0" /></label>
        <label>报警<input v-model.number="draft(item).alarm" :disabled="!canWrite" type="number" min="0" /></label>
        <button :disabled="!canWrite" @click="save(item)">保存 v{{ item.version }}</button>
      </div>
      <p v-if="store.offline" class="inline-message">Django API 离线，当前配置只读；重新连接后可继续修改。</p>
      <p v-else-if="!canWrite" class="inline-message">查看者无权修改阈值。</p>
      <p v-else-if="message" class="inline-message" role="status">{{ message }}</p>
    </section>
  </AppShell>
</template>
