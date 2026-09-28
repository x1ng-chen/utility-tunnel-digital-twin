<script setup lang="ts">
import { computed, nextTick, ref, watch, type Component } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { onKeyStroke, useLocalStorage, useNow } from '@vueuse/core';
import {
  Activity,
  Box,
  Boxes,
  ClipboardCheck,
  Gauge,
  ListTree,
  LogOut,
  Map,
  MapPinned,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldAlert,
  Wifi,
  WifiOff,
} from 'lucide-vue-next';
import { useAuthStore } from '../stores/auth';
import AiAssistant from './AiAssistant.vue';
import { useOperationsStore } from '../stores/operations';
import { serviceStatus } from '../utils/serviceStatus';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const operations = useOperationsStore();
const dataService = computed(() => serviceStatus(operations.source, operations.offline, operations.lastSyncedAt));
const now = useNow({ interval: 1000 });
const collapsed = useLocalStorage('ops.sidebar.collapsed', false);
const searchOpen = ref(false);
const searchQuery = ref('');
const searchInput = ref<HTMLInputElement>();
const searchPanel = ref<HTMLElement>();
let searchOpener: HTMLElement | null = null;
watch(searchOpen, async (open) => {
  if (open) {
    searchOpener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    await nextTick();
    searchInput.value?.focus();
  } else {
    searchOpener?.focus();
  }
});

function containSearchFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return;
  const controls = searchPanel.value?.querySelectorAll<HTMLElement>('input, button:not(:disabled)');
  if (!controls?.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

type NavItem = { path: string; icon: Component; label: string; description: string; adminOnly?: boolean };

const primaryNav: NavItem[] = [
  { path: '/dashboard', icon: Gauge, label: '运行总览', description: '实时态势与关键指标' },
  { path: '/alerts', icon: ShieldAlert, label: '告警中心', description: '异常确认与处置入口' },
  { path: '/work-orders', icon: ClipboardCheck, label: '工单中心', description: '派发、执行与复核' },
  { path: '/assets', icon: Server, label: '设备台账', description: '资产状态与维护记录' },
  { path: '/twin-3d', icon: Box, label: '三维孪生', description: '实体模型与告警定位' },
  { path: '/gis', icon: Map, label: 'GIS 总览', description: '空间位置与区域态势' },
  { path: '/telemetry', icon: Activity, label: '数据洞察', description: '遥测趋势与数据质量' },
];

const governanceNav: NavItem[] = [
  { path: '/asset-admin', icon: Boxes, label: '资产配置', description: '设备主数据治理', adminOnly: true },
  { path: '/gis-admin', icon: MapPinned, label: '空间配置', description: '坐标、图层与发布', adminOnly: true },
  { path: '/settings', icon: Settings, label: '系统配置', description: '阈值、账号与模型' },
  { path: '/audit', icon: ListTree, label: '审计追踪', description: '操作记录与责任追溯' },
];

const userName = computed(() => auth.user?.displayName || '运维员');
const userRole = computed(() => auth.user?.role === 'administrator' ? '管理员' : auth.user?.role === 'viewer' ? '查看者' : '运维员');
const clock = computed(() => now.value.toLocaleTimeString('zh-CN', { hour12: false }));
const date = computed(() => now.value.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }));
const visiblePrimaryNav = computed(() => primaryNav.filter((item) => !item.adminOnly || auth.user?.role === 'administrator'));
const visibleGovernanceNav = computed(() => governanceNav.filter((item) => !item.adminOnly || auth.user?.role === 'administrator'));
const nav = computed(() => [...visiblePrimaryNav.value, ...visibleGovernanceNav.value]);
const currentNavIndex = computed(() => nav.value.findIndex((item) => item.path === route.path));
const currentNav = computed(() => nav.value[currentNavIndex.value] || { label: '页面未找到', description: '请选择有效的导航入口' });
const navProgress = computed(() => nav.value.length > 1 ? Math.max(0, currentNavIndex.value) / (nav.value.length - 1) : 0);
const criticalAlert = computed(() => operations.alerts.find((item) => item.severity === 'critical' && ['open', 'acknowledged'].includes(item.status)));
const searchResults = computed(() => {
  const needle = searchQuery.value.trim().toLowerCase();
  if (!needle) return nav.value.slice(0, 7).map((item) => ({ label: item.label, meta: item.description, path: item.path }));
  const pages = nav.value
    .filter((item) => `${item.label}${item.description}`.toLowerCase().includes(needle))
    .map((item) => ({ label: item.label, meta: item.description, path: item.path }));
  const assets = operations.assets
    .filter((item) => `${item.code}${item.name}${item.zone}`.toLowerCase().includes(needle))
    .slice(0, 6)
    .map((item) => ({ label: `${item.code} · ${item.name}`, meta: item.zone, path: `/assets?focus=${encodeURIComponent(item.code)}` }));
  const alerts = operations.alerts
    .filter((item) => `${item.code} ${item.title} ${item.assetCode || ''}`.toLowerCase().includes(needle))
    .slice(0, 4)
    .map((item) => ({ label: `${item.code} · ${item.title}`, meta: '告警记录', path: `/alerts?focus=${encodeURIComponent(item.code)}` }));
  const orders = operations.workOrders
    .filter((item) => `${item.code} ${item.title} ${item.assetCode}`.toLowerCase().includes(needle))
    .slice(0, 4)
    .map((item) => ({ label: `${item.code} · ${item.title}`, meta: '处置工单', path: `/work-orders?focus=${encodeURIComponent(item.code)}` }));
  return [...pages, ...assets.slice(0, 4), ...alerts, ...orders];
});

onKeyStroke('k', (event) => {
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault();
    searchOpen.value = true;
  }
});
onKeyStroke('Escape', () => { searchOpen.value = false; });

function navigateTo(path: string, direction?: 'next' | 'previous') {
  if (path === route.path) return;
  const destination = nav.value.findIndex((item) => item.path === path);
  document.documentElement.dataset.routeDirection = direction || (destination >= currentNavIndex.value ? 'next' : 'previous');
  void router.push(path);
}

function openSearchResult(path: string) {
  searchOpen.value = false;
  searchQuery.value = '';
  navigateTo(path);
}

async function logout() {
  await auth.logout();
  void router.push('/login');
}

async function retrySync() {
  await operations.refresh('api');
}

function alertCount(path: string) {
  if (path === '/alerts') return operations.openAlerts;
  if (path === '/work-orders') return operations.activeOrders;
  return 0;
}

</script>

<template>
  <div :class="['app-shell command-deck', { 'sidebar-collapsed': collapsed }]">
    <aside :class="['sidebar command-sidebar', { collapsed }]" aria-label="主导航">
      <header class="brand command-brand">
        <span class="brand-mark" aria-hidden="true"><i /><i /><i /><i /></span>
        <span class="brand-copy"><b>综合管廊</b><small>数字孪生运维平台</small></span>
        <button class="sidebar-toggle" :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'" @click="collapsed = !collapsed">
          <PanelLeftOpen v-if="collapsed" /><PanelLeftClose v-else />
        </button>
      </header>

      <div :class="['sidebar-system-state', dataService.tone]"><i /><span>数据服务</span><strong>{{ dataService.label }}</strong></div>

      <nav class="command-nav" :style="{ '--nav-progress': navProgress }">
        <section class="nav-group" aria-labelledby="operations-nav-title">
          <h2 id="operations-nav-title">运行工作台</h2>
          <button
            v-for="(item, index) in visiblePrimaryNav"
            :key="item.path"
            :title="`${item.label}：${item.description}`"
            :aria-label="item.label"
            :aria-current="route.path === item.path ? 'page' : undefined"
            :class="['nav-item', { active: route.path === item.path }]"
            @click="navigateTo(item.path)"
          >
            <span class="nav-sequence">{{ String(index + 1).padStart(2, '0') }}</span>
            <component :is="item.icon" />
            <span class="nav-copy"><b>{{ item.label }}</b><small>{{ item.description }}</small></span>
            <em v-if="alertCount(item.path)">{{ alertCount(item.path) }}</em>
          </button>
        </section>

        <section class="nav-group governance-nav" aria-labelledby="governance-nav-title">
          <h2 id="governance-nav-title">平台治理</h2>
          <button
            v-for="(item, index) in visibleGovernanceNav"
            :key="item.path"
            :title="`${item.label}：${item.description}`"
            :aria-label="item.label"
            :aria-current="route.path === item.path ? 'page' : undefined"
            :class="['nav-item governance-item', { active: route.path === item.path }]"
            @click="navigateTo(item.path)"
          >
            <span class="nav-sequence">{{ String(visiblePrimaryNav.length + index + 1).padStart(2, '0') }}</span>
            <component :is="item.icon" />
            <span class="nav-copy"><b>{{ item.label }}</b><small>{{ item.description }}</small></span>
          </button>
        </section>
      </nav>

      <footer class="sidebar-foot">
        <div class="avatar">{{ userName.slice(0, 1) }}</div>
        <div class="user-copy"><b>{{ userName }}</b><small>{{ userRole }}</small></div>
        <button title="退出登录" aria-label="退出登录" @click="logout"><LogOut /></button>
      </footer>
    </aside>

    <main class="main-panel command-main">
      <header class="topbar command-topbar">
        <div class="page-identity">
          <span>{{ currentNavIndex < 0 ? '--' : String(currentNavIndex + 1).padStart(2, '0') }} / {{ String(nav.length).padStart(2, '0') }}</span>
          <div><strong>{{ currentNav.label }}</strong><small>{{ currentNav.description }}</small></div>
        </div>
        <button class="global-search" type="button" aria-label="搜索设备、告警、工单" @click="searchOpen = true">
          <Search /><span>搜索设备、告警、工单</span><kbd>CTRL K</kbd>
        </button>
        <div class="topbar-actions">
          <div class="topbar-clock"><strong>{{ clock }}</strong><small>{{ date }}</small></div>
          <span :class="['status-pill', dataService.tone]" :title="operations.lastSyncedAt ? `数据服务最近同步：${new Date(operations.lastSyncedAt).toLocaleString('zh-CN')}；不代表现场设备在线` : '尚未完成数据同步'">
            <WifiOff v-if="dataService.tone !== 'online'" /><Wifi v-else />数据服务{{ dataService.label }}
          </span>
          <div class="top-avatar" :title="`${userName} · ${userRole}`">{{ userName.slice(0, 1) }}</div>
          <button class="compact-logout" type="button" title="退出登录" aria-label="退出登录" @click="logout"><LogOut /></button>
        </div>
      </header>

      <div class="route-progress" aria-hidden="true"><i :style="{ transform: `scaleX(${navProgress})` }" /></div>

      <div v-if="criticalAlert" class="critical-ticker" role="alert">
        <ShieldAlert /><b>紧急告警</b><span>{{ criticalAlert.code }} · {{ criticalAlert.title }} · {{ criticalAlert.assetCode || '未绑定设备' }}</span>
        <button @click="router.push('/alerts')">立即处置</button>
      </div>

      <div v-if="operations.syncError" class="offline-banner" role="status">
        <div><strong>数据链路需要关注</strong><span>{{ operations.syncError }}</span></div>
        <button :disabled="operations.loading" @click="retrySync"><RefreshCw />{{ operations.loading ? '重试中' : '重新连接' }}</button>
      </div>

      <div class="page-content"><slot /></div>
      <AiAssistant :page-name="currentNav.label" />

      <Teleport to="body">
        <div v-if="searchOpen" class="command-mask" @click.self="searchOpen = false">
          <section ref="searchPanel" class="command-panel" role="dialog" aria-modal="true" aria-label="全局搜索" @keydown="containSearchFocus">
            <header><Search /><input ref="searchInput" v-model="searchQuery" aria-label="搜索设备、告警、工单或页面" placeholder="输入设备、告警、工单或页面名称" @keydown.enter.prevent="searchResults[0] && openSearchResult(searchResults[0].path)" /><button class="search-close" type="button" aria-label="关闭搜索" @click="searchOpen = false">关闭</button></header>
            <button v-for="result in searchResults" :key="result.path" @click="openSearchResult(result.path)"><span>{{ result.label }}</span><small>{{ result.meta }}</small></button>
            <p v-if="!searchResults.length">没有匹配结果</p>
          </section>
        </div>
      </Teleport>
    </main>
  </div>
</template>
