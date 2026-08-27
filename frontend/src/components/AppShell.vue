<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const operations = useOperationsStore();
const userName = computed(() => auth.user?.displayName || '运维员');
const nav = [{ path: '/dashboard', icon: '⌂', label: '运行总览' }, { path: '/alerts', icon: '!', label: '告警中心' }, { path: '/work-orders', icon: '✓', label: '工单中心' }, { path: '/assets', icon: '▦', label: '设备台账' }, { path: '/settings', icon: '⚙', label: '系统配置' }, { path: '/audit', icon: '≡', label: '审计追踪' }];
async function logout() { await auth.logout(); router.push('/login'); }
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL</small></span></div>
      <div class="side-caption">运行工作台</div>
      <nav><button v-for="item in nav" :key="item.path" :class="['nav-item', { active: route.path === item.path }]" @click="router.push(item.path)"><span>{{ item.icon }}</span>{{ item.label }}<em v-if="item.path === '/alerts' && operations.openAlerts">{{ operations.openAlerts }}</em><em v-if="item.path === '/work-orders' && operations.activeOrders">{{ operations.activeOrders }}</em></button></nav>
      <div class="sidebar-foot"><div class="avatar">{{ userName.slice(0, 1) }}</div><div><b>{{ userName }}</b><small>{{ auth.user?.role === 'administrator' ? '管理员' : auth.user?.role === 'viewer' ? '查看者' : '运维员' }}</small></div><button title="退出登录" @click="logout">↪</button></div>
    </aside>
    <main class="main-panel">
      <header class="topbar"><div class="breadcrumb">综合管廊 <span>/</span> <b>{{ nav.find((item) => item.path === route.path)?.label || '运行总览' }}</b></div><div class="topbar-actions"><span class="status-pill"><i />{{ operations.source === 'api' ? 'Django API' : '本地演示' }}</span><span class="connection">● 数据链路在线</span><div class="top-avatar">{{ userName.slice(0, 1) }}</div></div></header>
      <div class="page-content"><slot /></div>
    </main>
  </div>
</template>
