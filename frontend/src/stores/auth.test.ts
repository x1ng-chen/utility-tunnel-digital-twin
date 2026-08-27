import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from './auth';

describe('auth session lifecycle', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('clears the current identity when a bearer session expires', async () => {
    const store = useAuthStore();
    await store.login('', '', 'operator', 'demo');
    expect(store.isAuthenticated).toBe(true);

    store.expireSession();

    expect(store.isAuthenticated).toBe(false);
    expect(store.user).toBeNull();
    expect(store.error).toBe('登录状态已过期，请重新登录。');
  });
});
