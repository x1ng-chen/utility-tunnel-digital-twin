import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { api } from '../services/api';
import type { Role, User } from '../types';

const userStorageKey = 'ut-vue-user';
const sessionModeKey = 'ut-session-mode';
const tokenStorageKey = 'ut-django-token';
const demoRoles: Record<Role, string> = { administrator: '管理员', operator: '运维员', viewer: '查看者' };
// Keep identity and bearer credentials in the current browser session only.
// The API base URL is non-sensitive and remains managed by services/api.ts.
const storage = typeof window !== 'undefined' ? window.sessionStorage : null;

export const useAuthStore = defineStore('auth', () => {
  const stored = storage?.getItem(userStorageKey);
  const storedMode = storage?.getItem(sessionModeKey);
  let parsedUser: User | null = null;
  try { parsedUser = stored ? JSON.parse(stored) as User : null; } catch { storage?.removeItem(userStorageKey); }
  // Do not revive an API identity without its bearer token after a browser restart
  // or an interrupted cleanup. Demo sessions intentionally have no token.
  if (storedMode === 'api' && !storage?.getItem(tokenStorageKey)) {
    parsedUser = null;
    storage?.removeItem(userStorageKey);
    storage?.removeItem(sessionModeKey);
  }
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
        // A demo session must never inherit an API bearer token from an older session.
        storage?.removeItem(tokenStorageKey);
        storage?.setItem(sessionModeKey, 'demo');
        persist({ id: 0, email: email || `${role}@demo.local`, displayName: demoRoles[role], role });
        return;
      }
      const response = await api.login({ email, password });
      storage?.setItem(tokenStorageKey, response.data.accessToken);
      storage?.setItem(sessionModeKey, 'api');
      persist(response.data.user);
    } catch (cause: unknown) {
      error.value = axiosMessage(cause);
      throw cause;
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    try { if (storage?.getItem(tokenStorageKey)) await api.logout(); } catch { /* local cleanup still wins */ }
    storage?.removeItem(tokenStorageKey);
    storage?.removeItem(sessionModeKey);
    persist(null);
  }

  async function changePassword(currentPassword: string, newPassword: string) {
    loading.value = true;
    error.value = '';
    try {
      const response = await api.changePassword({ currentPassword, newPassword });
      storage?.setItem(tokenStorageKey, response.data.accessToken);
      storage?.setItem(sessionModeKey, 'api');
      return response.data.message as string;
    } catch (cause: unknown) {
      error.value = axiosMessage(cause);
      throw cause;
    } finally {
      loading.value = false;
    }
  }

  function expireSession(message = '登录状态已过期，请重新登录。') {
    storage?.removeItem(tokenStorageKey);
    storage?.removeItem(sessionModeKey);
    persist(null);
    error.value = message;
  }

  return { user, loading, error, isAuthenticated, login, logout, changePassword, expireSession, clearError: () => { error.value = ''; } };
});

function axiosMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause) {
    const failure = cause as { code?: string; response?: { status?: number; data?: { message?: string } } };
    if (failure.response) {
      if ((failure.response.status ?? 0) >= 500) return '登录服务异常，请联系管理员检查后端服务后重试。';
      return failure.response.data?.message || '登录失败，请检查账号或服务地址。';
    }
    if (failure.code === 'ECONNABORTED' || failure.code === 'ETIMEDOUT') return '登录连接超时，请检查网络和后端服务后重试。';
  }
  return '无法连接登录服务，请确认后端已启动、网络及服务地址正确后重试。';
}
