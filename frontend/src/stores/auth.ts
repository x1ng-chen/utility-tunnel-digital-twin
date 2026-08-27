import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../services/api';
import type { Role, User } from '../types';

const userStorageKey = 'ut-vue-user';
const demoRoles: Record<Role, string> = { administrator: '管理员', operator: '运维员', viewer: '查看者' };
const storage = typeof window !== 'undefined' ? window.localStorage : null;

export const useAuthStore = defineStore('auth', () => {
  const stored = storage?.getItem(userStorageKey);
  let parsedUser: User | null = null;
  try { parsedUser = stored ? JSON.parse(stored) as User : null; } catch { storage?.removeItem(userStorageKey); }
  const user = ref<User | null>(parsedUser);
  const loading = ref(false);
  const error = ref('');
  const isAuthenticated = computed(() => Boolean(user.value));

  function persist(next: User | null) {
    user.value = next;
    if (next) storage?.setItem(userStorageKey, JSON.stringify(next));
    else storage?.removeItem(userStorageKey);
  }

  async function login(email: string, password: string, role: Role, mode: 'demo' | 'api') {
    loading.value = true;
    error.value = '';
    try {
      if (mode === 'demo') {
        persist({ id: 0, email: email || `${role}@demo.local`, displayName: demoRoles[role], role });
        return;
      }
      const response = await api.login({ email, password });
      storage?.setItem('ut-django-token', response.data.accessToken);
      persist(response.data.user);
    } catch (cause: unknown) {
      error.value = axiosMessage(cause);
      throw cause;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    try { if (storage?.getItem('ut-django-token')) await api.logout(); } catch { /* local cleanup still wins */ }
    storage?.removeItem('ut-django-token');
    persist(null);
  }

  return { user, loading, error, isAuthenticated, login, logout, clearError: () => { error.value = ''; } };
});

function axiosMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause && 'response' in cause) return String((cause as { response?: { data?: { message?: string } } }).response?.data?.message || '登录失败，请检查账号或服务地址。');
  return 'API 暂不可用，请检查 Django 服务是否启动。';
}
