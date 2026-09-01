<script setup lang="ts">
import { computed, ref, type Component } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { onKeyStroke, useLocalStorage, useNow } from '@vueuse/core';
import { Activity, Box, Boxes, ChevronDown, ClipboardCheck, Gauge, ListTree, LogOut, Map, MapPinned, PanelLeftClose, PanelLeftOpen, RefreshCw, Search, Server, Settings, ShieldAlert, Wifi, WifiOff } from 'lucide-vue-next';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const operations = useOperationsStore();
const now = useNow({ interval: 1000 }); const collapsed = useLocalStorage('ops.sidebar.collapsed', false);
const searchOpen = ref(false); const searchQuery = ref('');
const userName = computed(() => auth.user?.displayName || '运维员');
const clock = computed(() => now.value.toLocaleTimeString('zh-CN', { hour12: false }));
const date = computed(() => now.value.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }));
type NavItem = { path: string; icon: Component; label: string; adminOnly?: boolean };
const primaryNav: NavItem[] = [
  { path: '/dashboard', icon: Gauge, label: '运行总览' }, { path: '/alerts', icon: ShieldAlert, label: '告警中心' },
  { path: '/work-orders', icon: ClipboardCheck, label: '工单中心' }, { path: '/assets', icon: Server, label: '设备台账' },
  { path: '/twin-3d', icon: Box, label: '三维孪生' }, { path: '/gis', icon: Map, label: 'GIS 总览' }, { path: '/telemetry', icon: Activity, label: '数据洞察' },
];
const governanceNav: NavItem[] = [
  { path: '/asset-admin', icon: Boxes, label: '资产配置', adminOnly: true }, { path: '/gis-admin', icon: MapPinned, label: '空间配置', adminOnly: true },
  { path: '/settings', icon: Settings, label: '系统配置' }, { path: '/audit', icon: ListTree, label: '审计追踪' },
];
const nav = computed(() => [...primaryNav, ...governanceNav].filter((item) => !item.adminOnly || auth.user?.role === 'administrator'));
const visibleGovernanceNav = computed(() => governanceNav.filter((item) => !item.adminOnly || auth.user?.role === 'administrator'));
const criticalAlert = computed(() => operations.alerts.find((item) => item.severity === 'critical' && ['open', 'acknowledged'].includes(item.status)));
const searchResults = computed(() => {
  const needle = searchQuery.value.trim().toLowerCase();
  if (!needle) return nav.value.slice(0, 7).map((item) => ({ label: item.label, meta: '功能页面', path: item.path }));
  const pages = nav.value.filter((item) => item.label.toLowerCase().includes(needle)).map((item) => ({ label: item.label, meta: '功能页面', path: item.path }));
  const assets = operations.assets.filter((item) => `${item.code}${item.name}${item.zone}`.toLowerCase().includes(needle)).slice(0, 6).map((item) => ({ label: `${item.code} · ${item.name}`, meta: item.zone, path: `/assets?focus=${encodeURIComponent(item.code)}` }));
  return [...pages, ...assets].slice(0, 8);
});
onKeyStroke('k', (event) => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); searchOpen.value = true; } });
onKeyStroke('Escape', () => { searchOpen.value = false; });
function openSearchResult(path: string) { searchOpen.value = false; searchQuery.value = ''; void router.push(path); }
async function logout() { await auth.logout(); router.push('/login'); }
async function retrySync() { await operations.refresh('api'); }
</script>

<template>
  <div :class="['app-shell', { 'sidebar-collapsed': collapsed }]">
    <aside :class="['sidebar', { collapsed }]">
      <div class="brand"><span class="brand-mark"><i /><i /><i /></span><span class="brand-copy"><b>综合管廊</b><small>数字孪生运维平台</small></span><button class="sidebar-toggle" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="collapsed = !collapsed"><PanelLeftOpen v-if="collapsed" /><PanelLeftClose v-else /></button></div>
      <div class="side-caption">[ 运行工作台 ]</div>
      <nav>
        <button v-for="item in primaryNav" :key="item.path" :title="item.label" :class="['nav-item', { active: route.path === item.path }]" @click="router.push(item.path)"><component :is="item.icon" /><span>{{ item.label }}</span><em v-if="item.path === '/alerts' && operations.openAlerts">{{ operations.openAlerts }}</em><em v-if="item.path === '/work-orders' && operations.activeOrders">{{ operations.activeOrders }}</em></button>
        <details class="governance-nav" :open="visibleGovernanceNav.some((item) => item.path === route.path)"><summary><span>平台治理</span><ChevronDown /></summary><button v-for="item in visibleGovernanceNav" :key="item.path" :title="item.label" :class="['nav-item governance-item', { active: route.path === item.path }]" @click="router.push(item.path)"><component :is="item.icon" /><span>{{ item.label }}</span></button></details>
      </nav>
      <div class="sidebar-foot"><div class="avatar">{{ userName.slice(0, 1) }}</div><div class="user-copy"><b>{{ userName }}</b><small>{{ auth.user?.role === 'administrator' ? '管理员' : auth.user?.role === 'viewer' ? '查看者' : '运维员' }}</small></div><button title="退出登录" aria-label="退出登录" @click="logout"><LogOut /></button></div>
    </aside>
    <main class="main-panel">
      <header class="topbar">
        <div class="breadcrumb"><span>综合管廊</span><b>/</b><strong>{{ nav.find((item) => item.path === route.path)?.label || '运行总览' }}</strong></div>
        <button class="global-search" type="button" @click="searchOpen = true"><Search /><span>搜索设备、告警、工单</span><kbd>CTRL K</kbd></button>
        <div class="topbar-actions"><div class="topbar-clock"><strong>{{ clock }}</strong><small>{{ date }}</small></div><span :class="['status-pill', { offline: operations.offline }]" :title="operations.lastSyncedAt ? `最近同步：${new Date(operations.lastSyncedAt).toLocaleString('zh-CN')}` : undefined"><WifiOff v-if="operations.offline" /><Wifi v-else />{{ operations.offline ? '离线快照' : '链路在线' }}</span><div class="top-avatar">{{ userName.slice(0, 1) }}</div></div>
      </header>
      <div v-if="criticalAlert" class="critical-ticker" role="alert"><ShieldAlert /><b>[ 紧急告警 ]</b><span>{{ criticalAlert.code }} / {{ criticalAlert.title }} / {{ criticalAlert.assetCode || '未绑定设备' }}</span><button @click="router.push('/alerts')">进入处置</button></div>
      <div v-if="operations.syncError" class="offline-banner" role="status"><div><strong>数据链路需要关注</strong><span>{{ operations.syncError }}</span></div><button :disabled="operations.loading" @click="retrySync"><RefreshCw />{{ operations.loading ? '重试中' : '重新连接' }}</button></div>
      <div class="page-content"><slot /></div>
      <Teleport to="body"><div v-if="searchOpen" class="command-mask" @click.self="searchOpen = false"><section class="command-panel" role="dialog" aria-modal="true" aria-label="全局搜索"><header><Search /><input v-model="searchQuery" autofocus placeholder="输入设备编码、名称或功能页面" /><kbd>ESC</kbd></header><button v-for="result in searchResults" :key="result.path" @click="openSearchResult(result.path)"><span>{{ result.label }}</span><small>{{ result.meta }}</small></button><p v-if="!searchResults.length">没有匹配结果</p></section></div></Teleport>
    </main>
  </div>
</template>

<style scoped>
.sidebar-toggle{margin-left:auto;width:34px;height:34px;display:grid;place-items:center;border:1px solid var(--ops-line);background:transparent;color:var(--ops-muted)}.sidebar-toggle svg,.sidebar-foot svg{width:17px}.governance-nav summary{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;color:var(--ops-muted);font-size:12px;border-top:1px solid var(--ops-line);list-style:none}.governance-nav summary svg{width:15px}.breadcrumb{display:flex;gap:10px;align-items:center;font-family:"Cascadia Mono",monospace}.breadcrumb span{color:var(--ops-signal);letter-spacing:.1em}.breadcrumb b{color:var(--ops-line)}.global-search{width:min(380px,34vw);height:38px;display:flex;align-items:center;gap:10px;padding:0 12px;border:1px solid var(--ops-line);background:#09111d;color:var(--ops-muted);text-align:left}.global-search svg{width:16px}.global-search span{flex:1}.global-search kbd{font:10px "Cascadia Mono",monospace;border:1px solid var(--ops-line);padding:3px 5px}.status-pill svg{width:14px}.critical-ticker{min-height:40px;display:flex;align-items:center;gap:10px;padding:8px 40px;border-bottom:1px solid var(--ops-danger);background:#250d13;color:#fecdd3;font:12px "Cascadia Mono",monospace}.critical-ticker svg{width:16px}.critical-ticker span{flex:1}.critical-ticker button{border:1px solid var(--ops-danger);background:transparent;color:#fecdd3;padding:5px 10px}.offline-banner button{display:flex;gap:6px;align-items:center}.offline-banner svg{width:15px}.sidebar.collapsed{width:76px!important}.sidebar.collapsed .brand-copy,.sidebar.collapsed .side-caption,.sidebar.collapsed .nav-item span,.sidebar.collapsed .user-copy,.sidebar.collapsed .governance-nav summary span{display:none}.sidebar.collapsed .brand{padding-inline:12px!important}.sidebar.collapsed .brand-mark{display:none}.sidebar.collapsed .nav-item{justify-content:center}.sidebar.collapsed .nav-item em{position:absolute;right:5px;top:5px}.sidebar-collapsed .main-panel{width:calc(100% - 76px)!important;margin-left:76px!important}
.command-mask{position:fixed;inset:0;z-index:12000;padding-top:12vh;background:rgba(0,0,0,.76)}.command-panel{width:min(680px,calc(100vw - 32px));margin:auto;border:1px solid var(--ops-line);background:#09111d;box-shadow:12px 12px 0 #000}.command-panel header{height:58px;display:flex;align-items:center;gap:12px;padding:0 15px;border-bottom:1px solid var(--ops-line)}.command-panel header svg{width:18px;color:var(--ops-signal)}.command-panel input{flex:1;border:0!important;background:transparent!important;outline:0!important}.command-panel kbd{border:1px solid var(--ops-line);padding:4px 6px;color:var(--ops-muted)}.command-panel>button{width:100%;display:flex;justify-content:space-between;padding:13px 16px;border:0;border-bottom:1px solid var(--ops-line-soft);background:transparent;color:var(--ops-text);text-align:left}.command-panel>button:hover{background:var(--ops-raised);color:var(--ops-signal)}.command-panel small,.command-panel p{color:var(--ops-muted)}.command-panel p{padding:18px}
</style>
