import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../services/api';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from './auth';

describe('auth session lifecycle', () => {
  beforeEach(() => { vi.restoreAllMocks(); setActivePinia(createPinia()); });

  it.each([
    [{ code: 'ERR_NETWORK', response: undefined }, '无法连接登录服务'],
    [{ code: 'ECONNABORTED' }, '登录连接超时'],
    [{ response: { status: 503 } }, '登录服务异常'],
    [{ response: { status: 401, data: { message: '账号或密码错误。' } } }, '账号或密码错误。'],
  ])('distinguishes login failures without leaving the form busy', async (failure, message) => {
    vi.spyOn(api, 'login').mockRejectedValueOnce(failure);
    const store = useAuthStore();
    await expect(store.login('admin', '123', 'administrator', 'api')).rejects.toEqual(failure);
    expect(store.error).toContain(message);
    expect(store.loading).toBe(false);
    expect(store.isAuthenticated).toBe(false);
  });

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
