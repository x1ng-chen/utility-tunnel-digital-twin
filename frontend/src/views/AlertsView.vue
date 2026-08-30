<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { Alert } from '../types';

const store = useOperationsStore();
const auth = useAuthStore();
const router = useRouter();
const filter = ref('all');
const actionError = ref('');
const busyId = ref<number | null>(null);
const visible = computed(() => store.alerts.filter((item) => filter.value === 'all' || item.status === filter.value));
const canWrite = computed(() => !store.offline && (auth.user?.role === 'administrator' || auth.user?.role === 'operator'));

async function acknowledge(alert: Alert) {
  await runAction(alert.id, () => store.acknowledge(alert));
}

async function createWorkOrder(alert: Alert) {
  await runAction(alert.id, () => store.createAlertOrder(alert));
}

function openTwin(alert: Alert) {
  if (!alert.assetCode) return;
  void router.push({ path: '/twin-3d', query: { asset: alert.assetCode, source: 'alert', alert: alert.code } });
}

async function runAction(id: number, action: () => Promise<unknown>) {
  actionError.value = '';
  busyId.value = id;
  try {
    await action();
  } catch (cause) {
    if (getResponseStatus(cause) === 409) {
      await store.refresh('api');
      actionError.value = '该告警的状态已更新，页面已同步为最新结果。';
      return;
    }
    actionError.value = getUserFacingError(cause);
  } finally {
    busyId.value = null;
  }
}

function getResponseStatus(cause: unknown) {
  if (typeof cause !== 'object' || cause === null || !('response' in cause)) return undefined;
  const response = (cause as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : undefined;
}

function getUserFacingError(cause: unknown) {
  if (typeof cause === 'object' && cause !== null && 'response' in cause) {
    const data = (cause as { response?: { data?: { message?: unknown } } }).response?.data;
    if (typeof data?.message === 'string' && data.message.trim()) return data.message;
  }
  return '操作未完成，请检查网络后重试。';
}
</script>

<template>
  <AppShell>
    <section class="section-title">
      <div><span class="eyebrow light">INCIDENT CENTER</span><h1>告警中心</h1><p>确认异常、关联工单并保留完整处理链路。</p></div>
      <div class="filter-tabs"><button v-for="item in [['all','全部'],['open','待确认'],['acknowledged','已确认']]" :key="item[0]" :class="{ active: filter === item[0] }" @click="filter = item[0]">{{ item[1] }}</button></div>
    </section>
    <p v-if="actionError" class="inline-message error-message" role="alert">{{ actionError }}</p>
    <section class="table-panel">
      <div class="table-head"><span>告警编码</span><span>资产 / 事件</span><span>级别</span><span>状态</span><span>操作</span></div>
      <div v-for="alert in visible" :key="alert.id" class="table-row">
        <div><b>{{ alert.code }}</b><small>{{ new Date(alert.openedAt).toLocaleString('zh-CN') }}</small></div>
        <div><strong>{{ alert.title }}</strong><small>{{ alert.assetCode || '未关联资产' }} · {{ alert.category }}<template v-if="alert.ruleKey"> · 自动规则 {{ alert.ruleKey }}<template v-if="alert.lastObservedValue != null">（最新值 {{ alert.lastObservedValue }}）</template></template></small></div>
        <span :class="['badge', alert.severity]">{{ alert.severity === 'critical' ? '严重' : alert.severity === 'warning' ? '警告' : '提示' }}</span>
        <span :data-testid="`alert-status-${alert.code}`" :class="['status-text', alert.status]">{{ alert.status === 'open' ? '待确认' : alert.status === 'acknowledged' ? '已确认' : alert.status === 'resolved' ? '已解决' : '已关闭' }}</span>
        <div class="row-actions">
          <button v-if="alert.assetCode" class="alert-locate-button" type="button" @click="openTwin(alert)">三维定位</button>
          <template v-if="canWrite">
            <button v-if="alert.status === 'open'" :disabled="busyId === alert.id" @click="acknowledge(alert)">{{ busyId === alert.id ? '处理中…' : '确认' }}</button>
            <button v-if="!store.workOrders.some((item) => item.sourceAlertId === alert.id)" :disabled="busyId === alert.id" @click="createWorkOrder(alert)">转工单</button>
          </template>
          <small v-else class="permission-hint">{{ store.offline ? '离线只读' : '只读角色' }}</small>
        </div>
      </div>
      <div v-if="!visible.length" class="empty-state">当前筛选条件下没有告警。</div>
    </section>
  </AppShell>
</template>
