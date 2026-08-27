import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from './stores/auth';
import LoginView from './views/LoginView.vue';
import DashboardView from './views/DashboardView.vue';
import AlertsView from './views/AlertsView.vue';
import WorkOrdersView from './views/WorkOrdersView.vue';
import AssetsView from './views/AssetsView.vue';
import GisView from './views/GisView.vue';
import SettingsView from './views/SettingsView.vue';
import AuditView from './views/AuditView.vue';
import AssetAdminView from './views/AssetAdminView.vue';
import type { Role } from './types';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: LoginView, meta: { guest: true } },
    { path: '/dashboard', component: DashboardView },
    { path: '/alerts', component: AlertsView },
    { path: '/work-orders', component: WorkOrdersView },
    { path: '/assets', component: AssetsView },
    { path: '/asset-admin', component: AssetAdminView, meta: { roles: ['administrator'] } },
    { path: '/gis', component: GisView },
    { path: '/settings', component: SettingsView },
    { path: '/audit', component: AuditView },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.guest && auth.isAuthenticated) return '/dashboard';
  if (!to.meta.guest && !auth.isAuthenticated) return '/login';
  const roles = to.meta.roles as Role[] | undefined;
  if (roles?.length && (!auth.user || !roles.includes(auth.user.role))) return '/dashboard';
  return true;
});

export default router;
