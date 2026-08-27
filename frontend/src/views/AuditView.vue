<script setup lang="ts">
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
const store = useOperationsStore();
</script>
<template><AppShell><section class="section-title"><div><span class="eyebrow light">AUDIT TRAIL</span><h1>审计追踪</h1><p>每一次登录、确认、流转和配置变更都有迹可循。</p></div><span class="audit-count">{{ store.audit.length || '—' }} 条记录</span></section><section class="audit-panel"><div v-if="!store.audit.length" class="empty-state">演示模式下的审计记录将在操作后实时出现；Django API 模式会从数据库加载完整审计日志。</div><div v-for="entry in store.audit" :key="entry.id" class="audit-row"><i /><time>{{ new Date(entry.occurredAt).toLocaleString('zh-CN') }}</time><div><b>{{ entry.action }}</b><p>{{ entry.actorName }} · {{ entry.resourceType }} / {{ entry.resourceId }}</p></div><code>{{ JSON.stringify(entry.detail) }}</code></div></section></AppShell></template>
