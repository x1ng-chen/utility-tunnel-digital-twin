// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import AppShell from './AppShell.vue';

describe('responsive shell navigation', () => {
  let wrapper: VueWrapper | undefined;
  beforeEach(() => {
    sessionStorage.clear(); localStorage.clear(); setActivePinia(createPinia());
    vi.stubGlobal('matchMedia', vi.fn((query: string) => ({matches:query === '(max-width: 820px)',media:query,
      addEventListener:vi.fn(),removeEventListener:vi.fn(),addListener:vi.fn(),removeListener:vi.fn(),dispatchEvent:vi.fn(),onchange:null})));
    useAuthStore().user = {id:1,email:'viewer@example.invalid',displayName:'查看者',role:'viewer'};
    useOperationsStore().source = 'demo';
    document.body.style.overflow = '';
  });
  afterEach(() => { wrapper?.unmount(); wrapper=undefined; document.body.innerHTML=''; document.body.style.overflow=''; vi.unstubAllGlobals(); });
  async function show() {
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/:pathMatch(.*)*',component:{template:'<div />'}}]});
    await router.push('/dashboard'); await router.isReady();
    wrapper=mount(AppShell,{attachTo:document.body,slots:{default:'<p>当前页面</p>'},global:{plugins:[router],stubs:{AiAssistant:true}}});
    await flushPromises(); return {wrapper,router};
  }
  it('opens a labelled drawer, contains focus and restores scrolling and the opener on Escape',async()=>{
    const {wrapper:w}=await show();
    const opener=w.get<HTMLButtonElement>('.mobile-navigation-toggle');opener.element.focus();
    expect(w.get('#main-navigation').attributes('inert')).toBeDefined();
    await opener.trigger('click');await flushPromises();
    expect(w.get('#main-navigation').attributes('role')).toBe('dialog');
    expect(w.get('#main-navigation').attributes('aria-modal')).toBe('true');
    expect(opener.attributes('aria-expanded')).toBe('true');
    expect(w.get('main').attributes('inert')).toBeDefined();
    expect(document.body.style.overflow).toBe('hidden');
    expect(document.activeElement).toBe(w.get('.sidebar-toggle').element);
    window.dispatchEvent(new KeyboardEvent('keydown',{key:'k',ctrlKey:true}));await flushPromises();
    expect(w.find('[aria-label="全局搜索"]').exists()).toBe(false);
    const buttons=w.findAll<HTMLButtonElement>('#main-navigation button');
    buttons.at(-1)!.element.focus();await buttons.at(-1)!.trigger('keydown',{key:'Tab'});
    expect(document.activeElement).toBe(buttons[0].element);
    window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));await flushPromises();
    expect(opener.attributes('aria-expanded')).toBe('false');
    expect(document.body.style.overflow).toBe('');
    expect(document.activeElement).toBe(opener.element);
  });
  it('closes after navigation and keeps administrator-only destinations unavailable to viewers',async()=>{
    const {wrapper:w,router}=await show();
    expect(w.find('button[aria-label="资产配置"]').exists()).toBe(false);
    expect(w.find('button[aria-label="空间配置"]').exists()).toBe(false);
    await w.get('.mobile-navigation-toggle').trigger('click');await flushPromises();
    await w.get('button[aria-label="告警中心"]').trigger('click');await flushPromises();
    expect(router.currentRoute.value.path).toBe('/alerts');
    expect(w.get('.mobile-navigation-toggle').attributes('aria-expanded')).toBe('false');
    expect(document.body.style.overflow).toBe('');
    expect(w.find('.route-progress').exists()).toBe(false);
    expect(w.find('.nav-sequence').exists()).toBe(false);
  });
});
