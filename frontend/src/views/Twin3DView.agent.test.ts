// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { route, push } = vi.hoisted(() => ({ route: { query: { asset: 'MQ4-05', source: 'agent' } }, push: vi.fn() }));
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => ({ push }) }));
import Twin3DView from './Twin3DView.vue';
import { useOperationsStore } from '../stores/operations';
import { api } from '../services/api';

describe('agent to twin asset focus', () => {
  beforeEach(() => {
    sessionStorage.clear(); setActivePinia(createPinia());
    route.query.asset = 'MQ4-05'; route.query.source = 'agent';
    vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('opens the overview without focusing an arbitrary historic alarm and keeps the risk list closed', async () => {
    route.query.asset = ''; route.query.source = '';
    const store = useOperationsStore(); store.source = 'demo';
    const focusAsset = vi.fn();
    const scene = defineComponent({ props: ['selectedCode'], setup(_props, { expose }) {
      expose({ focusAsset, resetView: vi.fn() }); return {};
    }, template: '<div />' });
    const wrapper = mount(Twin3DView, { global: { stubs: {
      AppShell: { template: '<main><slot /></main>' }, TwinScene: scene, OpsChart: true,
    } } });
    try {
      await nextTick();
      expect(wrapper.findComponent(scene).props('selectedCode')).toBeNull();
      expect(focusAsset).not.toHaveBeenCalled();
      expect(wrapper.get('details.twin-risk-hud').attributes('open')).toBeUndefined();
      expect(wrapper.get('.twin-empty-inspector').text()).toContain('选择一个设备');
    } finally { wrapper.unmount(); }
  });

  it('shows V20 numbering and sends the pipe-front camera direction without guessing new sensor IDs', async () => {
    const store = useOperationsStore(); store.source='api'; store.offline=false;
    vi.spyOn(api,'twinModelReadiness').mockResolvedValue({data:{status:'ready',summary:{activeAssetCount:1,mappedAssetCount:1},
      activeRelease:{id:2},presentation:{revision:'v20-presentation-20261028.1',modelVersion:'hardware-live-v20',
        frontCameraDirection:[-1,.85,0],stations:[{id:'P1',position:'后左'},{id:'P2',position:'后右'},
          {id:'P3',position:'前左'},{id:'P4',position:'前右'},{id:'P5',position:'中央'}]}}} as never);
    vi.spyOn(api,'twinModelFile').mockResolvedValue({data:new Blob(['model'])} as never);
    vi.stubGlobal('URL', {createObjectURL:()=> 'blob:test-v20',revokeObjectURL:vi.fn()});
    const focusStation=vi.fn();
    const scene=defineComponent({props:['overviewDirection'],setup(_props,{expose}){expose({focusStation});return{};},template:'<div />'});
    const wrapper=mount(Twin3DView,{global:{stubs:{AppShell:{template:'<main><slot /></main>'},TwinScene:scene,OpsChart:true}}});
    try {
      await new Promise(resolve=>setTimeout(resolve,0)); await nextTick();
      expect(wrapper.get('[data-testid="model-numbering-notice"]').text()).toContain('P1 后左');
      expect(wrapper.get('[data-testid="model-numbering-notice"]').text()).toContain('前左2、前右1');
      expect(wrapper.findComponent(scene).props('overviewDirection')).toEqual([-1,.85,0]);
      const p1=wrapper.findAll('.twin-preset-hud button').find(button=>button.text()==='P1');
      expect(p1).toBeTruthy(); await p1!.trigger('click');
      expect(focusStation).toHaveBeenCalledWith('P1');
    } finally { wrapper.unmount(); }
  });

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
