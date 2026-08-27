<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
const store = useOperationsStore();
const auth = useAuthStore();
const canWrite = computed(() => auth.user?.role === 'administrator');
const message = ref('');
async function save(item: typeof store.thresholds[number]) { try { await store.updateThreshold(item, item.warning, item.alarm); message.value = `${item.label} 已保存`; } catch (cause) { message.value = cause instanceof Error ? cause.message : '保存失败'; } }
</script>
<template><AppShell><section class="section-title"><div><span class="eyebrow light">SYSTEM CONFIGURATION</span><h1>系统配置</h1><p>管理告警阈值与数据源，管理员变更会写入审计日志。</p></div><span class="config-source"><i />{{ store.source === 'api' ? 'Django API' : '本地演示数据' }}</span></section><section class="settings-panel"><div class="settings-head"><span>阈值策略</span><small>报警值必须高于预警值</small></div><div v-for="item in store.thresholds" :key="item.key" class="threshold-row"><div><b>{{ item.label }}</b><small>{{ item.key }} · {{ item.unit }}</small></div><label>预警<input v-model.number="item.warning" :disabled="!canWrite" type="number" min="0" /></label><label>报警<input v-model.number="item.alarm" :disabled="!canWrite" type="number" min="0" /></label><button :disabled="!canWrite" @click="save(item)">保存 v{{ item.version }}</button></div><p v-if="!canWrite" class="inline-message">查看者无权修改阈值。</p><p v-else-if="message" class="inline-message">{{ message }}</p></section></AppShell></template>
