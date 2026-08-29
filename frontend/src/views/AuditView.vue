<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';

const store = useOperationsStore();
const search = ref('');
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return store.audit;
  return store.audit.filter((entry) => { const item = presentAudit(entry); return `${item.title} ${item.description} ${entry.actorName}`.toLowerCase().includes(query); });
});
</script>

<template>
  <AppShell>
    <section class="section-title"><div><span class="eyebrow light">AUDIT TRAIL</span><h1>审计追踪</h1><p>每一次登录、确认、流转和配置变更都有迹可循。</p></div><div class="section-actions"><input v-model="search" class="search-input" placeholder="搜索动作、操作者或资源" aria-label="搜索审计记录" /><span class="audit-count">{{ visible.length || '—' }} 条记录</span></div></section>
    <section class="audit-panel"><div v-if="!visible.length" class="empty-state">{{ search ? '没有匹配的审计记录。' : '当前暂无审计记录。' }}</div><div v-for="entry in visible" :key="entry.id" class="audit-row readable-audit-row"><i /><time>{{ new Date(entry.occurredAt).toLocaleString('zh-CN') }}</time><div><b>{{ presentAudit(entry).title }}</b><p>{{ presentAudit(entry).description }}</p></div><span class="audit-actor">操作人：{{ entry.actorName }}</span></div></section>
  </AppShell>
</template>
