import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from './stores/auth';
import LoginView from './views/LoginView.vue';
import type { Role } from './types';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', component: LoginView, meta: { guest: true } },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/alerts', component: () => import('./views/AlertsView.vue') },
    { path: '/work-orders', component: () => import('./views/WorkOrdersView.vue') },
    { path: '/assets', component: () => import('./views/AssetsView.vue') },
    { path: '/twin-3d', component: () => import('./views/Twin3DView.vue') },
    { path: '/asset-admin', component: () => import('./views/AssetAdminView.vue'), meta: { roles: ['administrator'] } },
    { path: '/gis', component: () => import('./views/GisView.vue') },
    { path: '/gis-admin', component: () => import('./views/GisAdminView.vue'), meta: { roles: ['administrator'] } },
    { path: '/telemetry', component: () => import('./views/TelemetryView.vue') },
    { path: '/settings', component: () => import('./views/SettingsView.vue') },
    { path: '/audit', component: () => import('./views/AuditView.vue') },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  const isPasswordSetup = to.path === '/login' && new URLSearchParams(to.hash.replace(/^#/, '')).has('setupToken');
  if (to.meta.guest && auth.isAuthenticated && !isPasswordSetup) return '/dashboard';
  if (!to.meta.guest && !auth.isAuthenticated) return '/login';
  const roles = to.meta.roles as Role[] | undefined;
  if (roles?.length && (!auth.user || !roles.includes(auth.user.role))) return '/dashboard';
  return true;
});

export default router;
