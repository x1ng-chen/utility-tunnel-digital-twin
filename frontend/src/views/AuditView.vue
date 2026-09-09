<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useOperationsStore } from '../stores/operations';
import { presentAudit } from '../utils/audit';

const store = useOperationsStore();
const search = ref('');
const category = ref('');
const actor = ref('');
const categories = [
  { key: 'auth', label: '登录与退出' }, { key: 'alert', label: '告警处置' },
  { key: 'work_order', label: '工单流转' }, { key: 'asset', label: '设备台账' },
  { key: 'gis', label: '空间数据' }, { key: 'hardware', label: '设备接入' },
  { key: 'admin', label: '权限管理' }, { key: 'registration', label: '账号审批' },
  { key: 'setting', label: '系统设置' }, { key: 'report', label: '报告导出' },
];
const actors = computed(() => [...new Set(store.audit.map((entry) => entry.actorName).filter(Boolean))].sort());
const presented = computed(() => store.audit.map((entry) => ({ ...entry, ...presentAudit(entry) }))
  .sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt) || b.id - a.id));
const page = ref(1);
const pageSize = 25;
const visible = computed(() => {
  const query = search.value.trim().toLowerCase();
  return presented.value.filter((entry) => (!category.value || entry.action.startsWith(`${category.value}.`))
    && (!actor.value || entry.actorName === actor.value)
    && (!query || `${entry.title} ${entry.description} ${entry.actorName} ${entry.requestId}`.toLowerCase().includes(query)));
});
const pageCount = computed(() => Math.max(1, Math.ceil(visible.value.length / pageSize)));
const paged = computed(() => visible.value.slice((page.value - 1) * pageSize, page.value * pageSize));
watch([search, category, actor], () => { page.value = 1; });
watch(pageCount, (count) => { if (page.value > count) page.value = count; });
function reset() { search.value = ''; category.value = ''; actor.value = ''; }
</script>

<template>
  <AppShell>
    <section class="section-title">
      <div><span class="eyebrow light">操作留痕</span><h1>审计追踪</h1><p>查看谁在何时进行了什么操作，帮助交接班核查与问题追溯。</p></div>
      <span class="audit-count">已加载 {{ store.audit.length }} 条近期记录</span>
    </section>
    <form class="audit-filters" @submit.prevent>
      <label>查找记录<input v-model="search" type="search" placeholder="操作内容、操作人或追踪编号" aria-label="搜索审计记录" /></label>
      <label>操作类型<select v-model="category"><option value="">全部类型</option><option v-for="item in categories" :key="item.key" :value="item.key">{{ item.label }}</option></select></label>
      <label>操作人<select v-model="actor"><option value="">全部操作人</option><option v-for="name in actors" :key="name" :value="name">{{ name }}</option></select></label>
      <button type="button" @click="reset">清除筛选</button>
    </form>
    <section class="audit-panel audit-records" aria-label="操作记录">
      <header class="audit-results"><h2>近期操作记录</h2><span role="status">匹配 {{ visible.length }} 条 · 时间由近到远</span></header>
      <div v-if="!visible.length" class="empty-state"><p>{{ search || category || actor ? '没有匹配的记录，请调整筛选条件。' : '当前暂无操作记录。' }}</p></div>
      <article v-for="entry in paged" :key="entry.id" class="audit-record">
        <time :datetime="entry.occurredAt">{{ new Date(entry.occurredAt).toLocaleString('zh-CN') }}</time>
        <div class="audit-description"><h3>{{ entry.title }}</h3><p>{{ entry.description }}</p>
          <details v-if="entry.requestId"><summary>查看追踪编号</summary><code>{{ entry.requestId }}</code></details>
        </div>
        <span class="audit-person"><small>操作人</small>{{ entry.actorName || '系统自动处理' }}</span>
      </article>
      <footer v-if="visible.length" class="audit-pagination">
        <span>第 {{ page }} / {{ pageCount }} 页 · 每页 {{ pageSize }} 条</span>
        <div><button type="button" :disabled="page === 1" @click="page--">上一页</button><button type="button" :disabled="page === pageCount" @click="page++">下一页</button></div>
      </footer>
    </section>
  </AppShell>
</template>

<style scoped>
.audit-filters { display: grid; grid-template-columns: minmax(0, 2fr) repeat(2, minmax(0, 1fr)) auto; align-items: end; gap: 16px; padding: 20px; margin-bottom: 20px; border: 1px solid var(--ops-line); background: var(--ops-panel); }
.audit-filters label { display: grid; min-width: 0; gap: 8px; color: var(--ops-muted); font-size: 12px; }
.audit-filters input, .audit-filters select { width: 100%; min-width: 0; min-height: 44px; }
.audit-filters button, .audit-pagination button { min-height: 44px; padding: 10px 18px; border: 1px solid var(--ops-line); background: var(--ops-panel); color: var(--ops-text); white-space: nowrap; }
.audit-results { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding: 20px 24px; border-bottom: 1px solid var(--ops-line); }
.audit-results h2 { margin: 0; font-size: 18px; }
.audit-results span, .audit-count { font-size: 12px; color: var(--ops-muted); }
.audit-record { display: grid; grid-template-columns: minmax(150px, .8fr) minmax(0, 2.3fr) minmax(90px, .7fr); gap: 24px; padding: 24px; border-bottom: 1px solid var(--ops-line); }
.audit-record > time { color: var(--ops-muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.audit-description { min-width: 0; }
.audit-description h3 { margin: 0 0 8px; font-size: 15px; }
.audit-description p { margin: 0; color: var(--ops-muted); line-height: 1.8; font-size: 13px; overflow-wrap: anywhere; }
.audit-description details { margin-top: 12px; font-size: 12px; color: var(--ops-muted); }
.audit-description summary { cursor: pointer; width: fit-content; }
.audit-description code { display: block; padding-top: 8px; overflow-wrap: anywhere; }
.audit-person { overflow-wrap: anywhere; font-size: 13px; }
.audit-person small { display: block; margin-bottom: 7px; color: var(--ops-muted); font-size: 11px; }
.audit-pagination { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px; padding: 20px 24px; }
.audit-pagination > div { display: flex; gap: 10px; }
@container (max-width: 850px) {
  .audit-filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .audit-record { grid-template-columns: minmax(0, 1fr) 110px; gap: 14px; }
  .audit-record > time { grid-column: 1 / -1; }
}
@container (max-width: 480px) {
  .audit-filters, .audit-record { grid-template-columns: minmax(0, 1fr); }
  .audit-person small { display: inline; margin-right: 8px; }
}
</style>
