<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { WorkOrder } from '../types';

const store = useOperationsStore();
const auth = useAuthStore();
const search = ref('');
const actionError = ref('');
const busyId = ref<number | null>(null);
const canWrite = computed(() => !store.offline && (auth.user?.role === 'administrator' || auth.user?.role === 'operator'));
const canComplete = computed(() => auth.user?.role === 'administrator');
const visible = computed(() => store.workOrders.filter((item) => `${item.code} ${item.title} ${item.assetCode}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const nextStatus: Partial<Record<WorkOrder['status'], WorkOrder['status']>> = { open: 'assigned', assigned: 'in_progress', in_progress: 'pending_review', pending_review: 'completed' };
const form = reactive({ assetCode: '', title: '', description: '', priority: 'normal' as WorkOrder['priority'] });
const formOpen = ref(false);
const creating = ref(false);

async function advance(order: WorkOrder) {
  const target = nextStatus[order.status];
  if (!target) return;
  actionError.value = '';
  busyId.value = order.id;
  try {
    await store.transition(order, target);
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '工单流转失败，请稍后重试。';
  } finally {
    busyId.value = null;
  }
}

async function createOrder() {
  actionError.value = '';
  creating.value = true;
  try {
    await store.createWorkOrder(form);
    form.title = '';
    form.description = '';
    formOpen.value = false;
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '工单创建失败，请检查输入。';
  } finally {
    creating.value = false;
  }
}
</script>

<template>
  <AppShell>
    <section class="section-title">
      <div><span class="eyebrow light">WORKFLOW CENTER</span><h1>工单中心</h1><p>从告警关联到复核关闭，按状态推进每一条处置链路。</p></div>
      <div class="section-actions"><input v-model="search" class="search-input" placeholder="搜索工单、资产或标题" aria-label="搜索工单" /><button v-if="canWrite" class="primary-button compact-button" @click="formOpen = !formOpen">{{ formOpen ? '收起' : '+ 新建工单' }}</button></div>
    </section>
    <p v-if="actionError" class="inline-message error-message" role="alert">{{ actionError }}</p>
    <section v-if="formOpen" class="create-order-panel" aria-label="新建工单">
      <div class="settings-head"><span>新建运维工单</span><small>创建后进入“待分派”状态并写入审计日志</small></div>
      <form class="order-form" @submit.prevent="createOrder">
        <label>关联资产<select v-model="form.assetCode" required><option value="" disabled>选择资产</option><option v-for="asset in store.assets" :key="asset.code" :value="asset.code">{{ asset.code }} · {{ asset.name }}</option></select></label>
        <label>优先级<select v-model="form.priority"><option value="low">低</option><option value="normal">普通</option><option value="high">高</option><option value="urgent">紧急</option></select></label>
        <label class="wide-field">工单标题<input v-model="form.title" required maxlength="180" placeholder="例如：复核风机反馈与现场状态" /></label>
        <label class="wide-field">处置说明<textarea v-model="form.description" maxlength="2000" rows="2" placeholder="补充处置范围、验收标准或注意事项（可选）" /></label>
        <button class="primary-button form-submit" type="submit" :disabled="creating || !canWrite">{{ creating ? '创建中…' : '创建工单' }}</button>
      </form>
    </section>
    <p v-else-if="store.offline" class="inline-message">Django API 离线，当前快照只读；重新连接后可继续操作。</p>
    <p v-else-if="!canWrite" class="inline-message">查看者无权新建或流转工单。</p>
    <section class="kanban">
      <article v-for="status in ['open','assigned','in_progress','pending_review','completed']" :key="status" class="kanban-column">
        <header><span>{{ status === 'open' ? '待分派' : status === 'assigned' ? '已分派' : status === 'in_progress' ? '处理中' : status === 'pending_review' ? '待复核' : '已完成' }}</span><b>{{ visible.filter((item) => item.status === status).length }}</b></header>
        <div v-for="order in visible.filter((item) => item.status === status)" :key="order.id" class="order-card"><span :class="['badge', order.priority]">{{ order.priority === 'urgent' ? '紧急' : order.priority === 'high' ? '高' : order.priority === 'low' ? '低' : '普通' }}</span><b>{{ order.code }}</b><h3>{{ order.title }}</h3><small>{{ order.assetCode }} · {{ order.assigneeName || '待分配' }}</small><button v-if="nextStatus[order.status] && (nextStatus[order.status] !== 'completed' || canComplete)" :disabled="busyId === order.id" @click="advance(order)">{{ busyId === order.id ? '处理中…' : `推进至 ${nextStatus[order.status] === 'assigned' ? '已分派' : nextStatus[order.status] === 'in_progress' ? '处理中' : nextStatus[order.status] === 'pending_review' ? '待复核' : '已完成'}` }}</button></div>
      </article>
    </section>
  </AppShell>
</template>
