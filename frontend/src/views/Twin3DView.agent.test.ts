// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { route, push } = vi.hoisted(() => ({ route: { query: { asset: 'MQ4-05', source: 'agent' } }, push: vi.fn() }));
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push }) }));
import Twin3DView from './Twin3DView.vue';
import { useOperationsStore } from '../stores/operations';

describe('agent to twin asset focus', () => {
  beforeEach(() => {
    sessionStorage.clear(); setActivePinia(createPinia());
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('focuses the requested asset after the real registry arrives, without changing its identity', async () => {
    const store = useOperationsStore();
    store.source = 'demo';
    store.assets = store.assets.filter(a => a.code !== 'MQ4-05');
    const scene = defineComponent({
      props: ['selectedCode', 'fanFeedback'],
      setup(_props, { expose }) { expose({ focusAsset: vi.fn(), resetView: vi.fn() }); return {}; },
      template: '<div data-testid="selected-asset">{{ selectedCode }}</div>',
    });
    const wrapper = mount(Twin3DView, { global: { stubs: {
      AppShell: { template: '<main><slot /></main>' }, TwinScene: scene, OpsChart: true,
    } } });
    try {
      expect(wrapper.get('[data-testid="selected-asset"]').text()).not.toBe('MQ4-05');
      store.assets.push({ ...store.assets[0], id: 9001, code: 'MQ4-05', name: '中央甲烷检测', mesh: 'MQ4-05' });
      await nextTick();
      expect(wrapper.get('[data-testid="selected-asset"]').text()).toBe('MQ4-05');
      expect(wrapper.text()).toContain('智能体证据');
      expect(wrapper.findComponent(scene).props('fanFeedback')).toMatchObject({ source: 'demo', offline: false });
    } finally { wrapper.unmount(); }
  });
});
