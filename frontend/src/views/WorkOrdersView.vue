<script setup lang="ts">
import { computed, ref } from 'vue';
import AppShell from '../components/AppShell.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import type { WorkOrder } from '../types';
const store = useOperationsStore();
const auth = useAuthStore();
const search = ref('');
const visible = computed(() => store.workOrders.filter((item) => `${item.code} ${item.title} ${item.assetCode}`.toLowerCase().includes(search.value.toLowerCase())));
const nextStatus: Partial<Record<WorkOrder['status'], WorkOrder['status']>> = { open: 'assigned', assigned: 'in_progress', in_progress: 'pending_review', pending_review: 'completed' };
const canComplete = computed(() => auth.user?.role === 'administrator');
</script>
<template><AppShell><section class="section-title"><div><span class="eyebrow light">WORKFLOW CENTER</span><h1>工单中心</h1><p>从告警关联到复核关闭，按状态推进每一条处置链路。</p></div><input v-model="search" class="search-input" placeholder="搜索工单、资产或标题" /></section><section class="kanban"><article v-for="status in ['open','assigned','in_progress','pending_review','completed']" :key="status" class="kanban-column"><header><span>{{ status === 'open' ? '待分派' : status === 'assigned' ? '已分派' : status === 'in_progress' ? '处理中' : status === 'pending_review' ? '待复核' : '已完成' }}</span><b>{{ visible.filter((item) => item.status === status).length }}</b></header><div v-for="order in visible.filter((item) => item.status === status)" :key="order.id" class="order-card"><span :class="['badge', order.priority]">{{ order.priority }}</span><b>{{ order.code }}</b><h3>{{ order.title }}</h3><small>{{ order.assetCode }} · {{ order.assigneeName || '待分配' }}</small><button v-if="nextStatus[order.status] && (nextStatus[order.status] !== 'completed' || canComplete)" @click="store.transition(order, nextStatus[order.status]!)">推进至 {{ nextStatus[order.status] }}</button></div></article></section></AppShell></template>
