import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from './stores/auth';
import LoginView from './views/LoginView.vue';
import DashboardView from './views/DashboardView.vue';
import AlertsView from './views/AlertsView.vue';
import WorkOrdersView from './views/WorkOrdersView.vue';
import AssetsView from './views/AssetsView.vue';
import SettingsView from './views/SettingsView.vue';
import AuditView from './views/AuditView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: LoginView, meta: { guest: true } },
    { path: '/dashboard', component: DashboardView },
    { path: '/alerts', component: AlertsView },
    { path: '/work-orders', component: WorkOrdersView },
    { path: '/assets', component: AssetsView },
    { path: '/settings', component: SettingsView },
    { path: '/audit', component: AuditView },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.meta.guest && auth.isAuthenticated) return '/dashboard';
  if (!to.meta.guest && !auth.isAuthenticated) return '/login';
  return true;
});

export default router;
