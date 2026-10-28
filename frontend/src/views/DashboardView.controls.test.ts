// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
import { useOperationsStore } from '../stores/operations';
import DashboardView from './DashboardView.vue';

describe('reviewed physical output controls', () => {
  let wrapper: VueWrapper | undefined;
  beforeEach(() => {
    vi.restoreAllMocks();sessionStorage.clear();setActivePinia(createPinia());
    const auth = useAuthStore();auth.user = { id: 1, email: 'operator@test.invalid', displayName: 'op', role: 'operator' };
    const store = useOperationsStore();store.source = 'api';store.offline = false;
    vi.spyOn(store, 'refresh').mockResolvedValue();
    vi.spyOn(api, 'agentContext').mockResolvedValue({ data: { dataContext: { mode: 'database_observation', label: '平台记录' } } } as never);
    vi.spyOn(api, 'controllerCommandCapabilities').mockResolvedValue({ data: { protocol: 'four-controller-v2', controlDisabled: false, manualLeaseMs: 10000 } } as never);
    vi.spyOn(api, 'controllerCommandConfirmation').mockResolvedValue({ data: { confirmationToken: 'fixture-token' } } as never);
    vi.spyOn(api, 'controllerCommand').mockResolvedValue({ data: { ack: { status: 'accepted' } } } as never);
  });
  afterEach(() => { wrapper?.unmount();wrapper = undefined; });

  async function show() {
    wrapper = mount(DashboardView, { global: { stubs: { AppShell: { template: '<main><slot /></main>' }, DashboardSignal: true, RouterLink: { template: '<a><slot /></a>' } } } });
    await flushPromises();return wrapper;
  }
  async function confirm() {
    await wrapper!.get('.confirm-command').trigger('click');await flushPromises();
  }
  it.each([
    [0, 'CTRL-04', 'fan_pwm'], [1, 'CTRL-02', 'fan2_pwm'],
  ])('the fan %i button waits for approval and sends to %s', async (index, controller, action) => {
    const w = await show();
    await w.findAll('.fan-unit')[index as number]!.findAll('button')[1]!.trigger('click');
    expect(w.get('[role=dialog]').text()).toContain(controller as string);
    expect(api.controllerCommand).not.toHaveBeenCalled();
    expect(api.controllerCommandConfirmation).not.toHaveBeenCalled();
    await confirm();
    expect(api.controllerCommandConfirmation).toHaveBeenCalledExactlyOnceWith(action, 60, controller);
    expect(api.controllerCommand).toHaveBeenCalledExactlyOnceWith(action, 'fixture-token', 60, controller);
    expect(w.text()).toContain('是否运转仍需核对');
  });
  it('cancel does not issue an approval token or publish a command', async () => {
    const w = await show();await w.findAll('.fan-unit')[0]!.get('button').trigger('click');
    await w.get('[role=dialog] button').trigger('click');
    expect(w.find('[role=dialog]').exists()).toBe(false);
    expect(api.controllerCommandConfirmation).not.toHaveBeenCalled();expect(api.controllerCommand).not.toHaveBeenCalled();
  });
  it('separate power controls and lighting keep their correct owners', async () => {
    const w = await show();
    const secondPower = w.findAll('.shared-power > div')[1]!;
    await secondPower.findAll('button')[1]!.trigger('click');await confirm();
    expect(api.controllerCommand).toHaveBeenLastCalledWith('relay_off', 'fixture-token', undefined, 'CTRL-02');
    await w.get('.light-blue').trigger('click');await confirm();
    expect(api.controllerCommand).toHaveBeenLastCalledWith('led_blue', 'fixture-token', undefined, 'CTRL-03');
  });
  it('failed configuration and evaluation mode cannot enable controls', async () => {
    vi.mocked(api.controllerCommandCapabilities).mockRejectedValueOnce(new Error('configuration unavailable'));
    const w = await show();
    expect(w.findAll('.fan-unit button').every(b => b.attributes('disabled') !== undefined)).toBe(true);
    expect(w.get('.control-access-note').text()).toContain('配置尚未加载成功');
    expect(api.controllerCommand).not.toHaveBeenCalled();
    w.unmount();wrapper = undefined;
    vi.mocked(api.controllerCommandCapabilities).mockResolvedValueOnce({ data: { protocol: 'four-controller-v2', controlDisabled: true } } as never);
    const disabled = await show();
    expect(disabled.findAll('.fan-unit button').every(b => b.attributes('disabled') !== undefined)).toBe(true);
    expect(disabled.get('.control-access-note').text()).toContain('服务端禁用设备控制');
  });
  it('a rejected or unknown result is not presented as a successful action', async () => {
    vi.mocked(api.controllerCommand).mockResolvedValueOnce({ data: { ack: { status: 'rejected', reason: 'local_protection' } } } as never);
    const w = await show();await w.findAll('.fan-unit')[0]!.get('button').trigger('click');await confirm();
    expect(w.text()).toContain('控制器拒绝命令：local_protection');
    vi.mocked(api.controllerCommand).mockResolvedValueOnce({ data: { ack: { status: 'unknown' } } } as never);
    await w.findAll('.fan-unit')[0]!.get('button').trigger('click');await confirm();
    expect(w.text()).toContain('执行结果未知');
  });
});
