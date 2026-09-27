// @vitest-environment happy-dom

import { createPinia, setActivePinia } from 'pinia';
import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('../services/api')>();
  return {
    ...original,
    api: {
      ...original.api,
      controllerCommand: vi.fn().mockResolvedValue({
        data: { ack: { status: 'accepted', reason: 'fan_pwm_set' } },
      }),
    },
  };
});

import DashboardView from './DashboardView.vue';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';

describe('Dashboard fan PWM feedback', () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    sessionStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
  });

  it('highlights 60% only after the fan confirms the 60% command', async () => {
    const store = useOperationsStore();
    const auth = useAuthStore();
    store.source = 'api';
    store.offline = false;
    auth.user = { id: 1, email: 'admin', displayName: '管理员', role: 'administrator' };
    vi.spyOn(store, 'refresh').mockResolvedValue();

    const wrapper = mount(DashboardView, {
      global: {
        plugins: [pinia],
        stubs: {
          AppShell: { template: '<main><slot /></main>' },
          DashboardSignal: true,
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    });
    const speedGroups = wrapper.findAll('.fan-speed-actions');
    const fan1Buttons = speedGroups[0].findAll('button');

    expect(fan1Buttons.map((button) => button.classes())).toEqual([[], [], []]);

    await fan1Buttons[1].trigger('click');

    expect(wrapper.find('.command-ok').text()).toContain('设备已确认');

    expect(fan1Buttons.map((button) => button.classes())).toEqual([[], ['active'], []]);
  });
});
