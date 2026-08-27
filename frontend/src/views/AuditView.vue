<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';

const store = useOperationsStore();
const search = ref('');
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return store.audit;
  return store.audit.filter((entry) => `${entry.action} ${entry.actorName} ${entry.resourceType} ${entry.resourceId} ${JSON.stringify(entry.detail)}`.toLowerCase().includes(query));
});
</script>

<template>
  <AppShell>
    <section class="section-title"><div><span class="eyebrow light">AUDIT TRAIL</span><h1>审计追踪</h1><p>每一次登录、确认、流转和配置变更都有迹可循。</p></div><div class="section-actions"><input v-model="search" class="search-input" placeholder="搜索动作、操作者或资源" aria-label="搜索审计记录" /><span class="audit-count">{{ visible.length || '—' }} 条记录</span></div></section>
    <section class="audit-panel"><div v-if="!visible.length" class="empty-state">{{ search ? '没有匹配的审计记录。' : '演示模式下的审计记录将在操作后实时出现；Django API 模式会从数据库加载完整审计日志。' }}</div><div v-for="entry in visible" :key="entry.id" class="audit-row"><i /><time>{{ new Date(entry.occurredAt).toLocaleString('zh-CN') }}</time><div><b>{{ entry.action }}</b><p>{{ entry.actorName }} · {{ entry.resourceType }} / {{ entry.resourceId }}</p></div><code>{{ JSON.stringify(entry.detail) }}</code></div></section>
  </AppShell>
</template>
