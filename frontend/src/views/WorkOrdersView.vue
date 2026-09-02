<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { WorkOrder } from '../types';

const store = useOperationsStore();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const search = ref(typeof route.query.asset === 'string' ? route.query.asset : '');
const actionError = ref('');
const busyId = ref<number | null>(null);
const canWrite = computed(() => !store.offline && (auth.user?.role === 'administrator' || auth.user?.role === 'operator'));
const canComplete = computed(() => auth.user?.role === 'administrator');
const visible = computed(() => store.workOrders.filter((item) => `${item.code} ${item.title} ${item.assetCode}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const focusedCode = computed(() => typeof route.query.focus === 'string' ? route.query.focus : '');
const navigationHint = computed(() => {
  if (focusedCode.value && route.query.source === 'alert') return `已打开告警 ${String(route.query.alert || '')} 生成的处置工单`;
  if (typeof route.query.asset === 'string' && route.query.source === 'asset') return `正在查看设备 ${route.query.asset} 的维护与处置记录`;
  return '';
});
const nextStatus: Partial<Record<WorkOrder['status'], WorkOrder['status']>> = { open: 'assigned', assigned: 'in_progress', in_progress: 'pending_review', pending_review: 'completed' };
const transitionLabel: Partial<Record<WorkOrder['status'], string>> = { open: '接单并分派', assigned: '开始现场处理', in_progress: '提交复核', pending_review: '复核并完成' };
const form = reactive({ assetCode: '', title: '', description: '', priority: 'normal' as WorkOrder['priority'] });
const formOpen = ref(false);
const creating = ref(false);
const noteOrderId = ref<number | null>(null);
const transitionNote = ref('');

function openTwin(order: WorkOrder) { void router.push({ path: '/twin-3d', query: { asset: order.assetCode, source: 'work-order', order: order.code } }); }
function openGis(order: WorkOrder) { void router.push({ path: '/gis', query: { asset: order.assetCode, source: 'work-order', order: order.code } }); }
function openSourceAlert(order: WorkOrder) {
  const alert = order.sourceAlertId ? store.alerts.find((item) => item.id === order.sourceAlertId) : undefined;
  if (alert) void router.push({ path: '/alerts', query: { focus: alert.code, source: 'work-order', order: order.code } });
}

function slaLabel(order: WorkOrder) {
  if (order.slaStatus === 'closed') return '已按流程关闭';
  if (!order.dueAt || order.slaStatus === 'not_set') return '未设置处理时限';
  const minutes = Math.abs(order.remainingMinutes ?? Math.trunc((new Date(order.dueAt).getTime() - Date.now()) / 60_000));
  const readable = minutes >= 60 ? `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分` : `${minutes} 分钟`;
  if (order.slaStatus === 'overdue') return `已超时 ${readable}`;
  if (order.slaStatus === 'due_soon') return `即将到期 · 剩余 ${readable}`;
  return `时限正常 · 剩余 ${readable}`;
}

function requestAdvance(order: WorkOrder) {
  const target = nextStatus[order.status];
  if (!target) return;
  if (target === 'pending_review' || target === 'completed') {
    noteOrderId.value = order.id;
    transitionNote.value = '';
    return;
  }
  void advance(order);
}

function cancelAdvance() {
  noteOrderId.value = null;
  transitionNote.value = '';
}

async function advance(order: WorkOrder) {
  const target = nextStatus[order.status];
  if (!target) return;
  actionError.value = '';
  busyId.value = order.id;
  try {
    await store.transition(order, target, transitionNote.value.trim());
    cancelAdvance();
  } catch (cause) {
    actionError.value = cause instanceof Error ? cause.message : '工单流转失败，请稍后重试。';
  } finally {
    busyId.value = null;
  }
}

const statusText: Record<WorkOrder['status'], string> = { draft: '草稿', open: '待分派', assigned: '已分派', in_progress: '处理中', pending_review: '待复核', completed: '已完成', cancelled: '已取消' };
function eventTitle(event: NonNullable<WorkOrder['timeline']>[number]) {
  if (event.eventType === 'created') return '创建工单';
  return `${event.fromStatus ? statusText[event.fromStatus] : '初始状态'} → ${event.toStatus ? statusText[event.toStatus] : '状态更新'}`;
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
      <div><span class="eyebrow light">处置流程</span><h1>工单中心</h1><p>从告警关联到复核关闭，按状态推进每一条处置链路。</p></div>
      <div class="section-actions"><input v-model="search" class="search-input" placeholder="搜索工单、资产或标题" aria-label="搜索工单" /><button v-if="canWrite" class="primary-button compact-button" @click="formOpen = !formOpen">{{ formOpen ? '收起' : '+ 新建工单' }}</button></div>
    </section>
    <p v-if="actionError" class="inline-message error-message" role="alert">{{ actionError }}</p>
    <p v-if="navigationHint" class="inline-message success-message work-order-navigation" role="status">{{ navigationHint }}，已为你定位到对应卡片。</p>
    <section class="workflow-guide" aria-label="工单处理流程"><div><b>1</b><span>待分派<small>确认责任人</small></span></div><i>→</i><div><b>2</b><span>处理中<small>执行现场任务</small></span></div><i>→</i><div><b>3</b><span>待复核<small>核对处理结果</small></span></div><i>→</i><div><b>4</b><span>已完成<small>关闭处置链路</small></span></div></section>
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
    <p v-else-if="store.offline" class="inline-message">数据服务离线，当前快照只读；重新连接后可继续操作。</p>
    <p v-else-if="!canWrite" class="inline-message">查看者无权新建或流转工单。</p>
    <section class="kanban">
      <article v-for="status in ['open','assigned','in_progress','pending_review','completed']" :key="status" class="kanban-column">
        <header><span>{{ status === 'open' ? '待分派' : status === 'assigned' ? '已分派' : status === 'in_progress' ? '处理中' : status === 'pending_review' ? '待复核' : '已完成' }}</span><b>{{ visible.filter((item) => item.status === status).length }}</b></header>
        <div v-for="order in visible.filter((item) => item.status === status)" :key="order.id" :class="['order-card', { focused: order.code === focusedCode }]" :data-testid="`work-order-${order.code}`">
          <span :class="['badge', order.priority]">{{ order.priority === 'urgent' ? '紧急' : order.priority === 'high' ? '高' : order.priority === 'low' ? '低' : '普通' }}</span>
          <b>{{ order.code }}</b><h3>{{ order.title }}</h3><small>{{ order.assetCode }} · {{ order.assigneeName || '待分配' }}</small>
          <small :class="['due-time', `sla-${order.slaStatus || 'not_set'}`]">{{ slaLabel(order) }}</small><small v-if="order.dueAt" class="due-deadline">截止 {{ new Date(order.dueAt).toLocaleString('zh-CN') }}</small>
          <div class="order-card-links" aria-label="查看工单关联信息"><button type="button" @click="openTwin(order)">三维定位</button><button type="button" @click="openGis(order)">地图定位</button><button v-if="order.sourceAlertId" type="button" @click="openSourceAlert(order)">源告警</button></div>
          <details v-if="order.timeline?.length" class="order-timeline"><summary>处理记录（{{ order.timeline.length }}）</summary><ol><li v-for="event in order.timeline" :key="event.id"><div><b>{{ eventTitle(event) }}</b><time>{{ new Date(event.createdAt).toLocaleString('zh-CN') }}</time></div><p v-if="event.note">{{ event.note }}</p><small>{{ event.actorName }}</small></li></ol></details>
          <div v-if="noteOrderId === order.id" class="transition-note"><label :for="`transition-note-${order.id}`">{{ order.status === 'pending_review' ? '复核意见' : '处理结果' }}</label><textarea :id="`transition-note-${order.id}`" v-model="transitionNote" maxlength="1000" rows="3" :placeholder="order.status === 'pending_review' ? '填写复核结论、验收结果或补充说明' : '填写已完成事项、现场结果和待复核内容'" autofocus></textarea><div><button type="button" class="ghost-button" @click="cancelAdvance">取消</button><button type="button" class="primary-button" :disabled="busyId === order.id || !transitionNote.trim()" @click="advance(order)">{{ busyId === order.id ? '提交中…' : '确认提交' }}</button></div></div>
          <button v-else-if="nextStatus[order.status] && (nextStatus[order.status] !== 'completed' || canComplete)" class="order-transition" :disabled="busyId === order.id" @click="requestAdvance(order)">{{ busyId === order.id ? '处理中…' : transitionLabel[order.status] }}</button>
        </div>
      </article>
    </section>
  </AppShell>
</template>

<style scoped>
.order-card-links{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin-top:11px}.order-card-links button{min-width:0;margin:0;padding:7px 4px;border-color:#2d4a69;background:#0d2036;color:#9db5d2;white-space:nowrap}.order-card-links button:hover,.order-card-links button:focus-visible{border-color:#5b86c2;background:#18385d;color:#fff;outline:0}.order-card .order-transition{margin-top:7px;border-color:#4b69bd;background:#223b73;color:#dce5ff}
.order-timeline{margin-top:10px;border-top:1px solid #253d58;padding-top:8px;color:#adc2dc}.order-timeline summary{cursor:pointer;font-size:12px;list-style:none}.order-timeline summary::-webkit-details-marker{display:none}.order-timeline summary::after{content:'＋';float:right;color:#6d92c2}.order-timeline[open] summary::after{content:'－'}.order-timeline ol{display:grid;gap:9px;margin:9px 0 0;padding:0;list-style:none}.order-timeline li{position:relative;padding-left:12px;border-left:2px solid #345a86}.order-timeline li div{display:flex;justify-content:space-between;gap:8px}.order-timeline li b{font-size:11px;color:#dce9f8}.order-timeline time,.order-timeline small{font-size:10px;color:#7892ae}.order-timeline p{margin:4px 0;font-size:11px;line-height:1.55;color:#aebfd3;white-space:pre-wrap}.transition-note{display:grid;gap:7px;margin-top:10px;padding:10px;border:1px solid #40628c;background:#0a1a2c}.transition-note label{font-size:12px;color:#dce9f8}.transition-note textarea{width:100%;box-sizing:border-box;resize:vertical;border:1px solid #355372;background:#081522;color:#e8f2ff;padding:9px;font:inherit}.transition-note>div{display:flex;justify-content:flex-end;gap:7px}.transition-note button{margin:0;padding:7px 10px}
</style>
