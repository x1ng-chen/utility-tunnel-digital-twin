<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
const store = useOperationsStore();
const auth = useAuthStore();
const filter = ref('all');
const visible = computed(() => store.alerts.filter((item) => filter.value === 'all' || item.status === filter.value));
const canWrite = computed(() => auth.user?.role === 'administrator' || auth.user?.role === 'operator');
</script>
<template><AppShell><section class="section-title"><div><span class="eyebrow light">INCIDENT CENTER</span><h1>告警中心</h1><p>确认异常、关联工单并保留完整处理链路。</p></div><div class="filter-tabs"><button v-for="item in [['all','全部'],['open','待确认'],['acknowledged','已确认']]" :key="item[0]" :class="{ active: filter === item[0] }" @click="filter = item[0]">{{ item[1] }}</button></div></section><section class="table-panel"><div class="table-head"><span>告警编码</span><span>资产 / 事件</span><span>级别</span><span>状态</span><span>操作</span></div><div v-for="alert in visible" :key="alert.id" class="table-row"><div><b>{{ alert.code }}</b><small>{{ new Date(alert.openedAt).toLocaleString('zh-CN') }}</small></div><div><strong>{{ alert.title }}</strong><small>{{ alert.assetCode }} · {{ alert.category }}</small></div><span :class="['badge', alert.severity]">{{ alert.severity === 'critical' ? '严重' : alert.severity === 'warning' ? '警告' : '提示' }}</span><span :class="['status-text', alert.status]">{{ alert.status === 'open' ? '待确认' : alert.status === 'acknowledged' ? '已确认' : '已解决' }}</span><div class="row-actions"><template v-if="canWrite"><button v-if="alert.status === 'open'" @click="store.acknowledge(alert)">确认</button><button v-if="!store.workOrders.some((item) => item.sourceAlertId === alert.id)" @click="store.createAlertOrder(alert)">转工单</button></template><small v-else class="permission-hint">只读角色</small></div></div><div v-if="!visible.length" class="empty-state">当前筛选条件下没有告警。</div></section></AppShell></template>
