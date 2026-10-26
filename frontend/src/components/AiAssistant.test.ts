// @vitest-environment happy-dom
import { createPinia, setActivePinia } from 'pinia';
import { mount, flushPromises } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AiAssistant from './AiAssistant.vue';
import { api, type AgentProposal } from '../services/api';
import { useAiAssistantStore } from '../stores/aiAssistant';
import { useOperationsStore } from '../stores/operations';
import { useAuthStore } from '../stores/auth';
const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }));

describe('agent proposal human confirmation', () => {
  let wrapper: ReturnType<typeof mount>;
  const proposal: AgentProposal = { kind: 'work_order', assetCode: 'CTRL-01', title: '节点通信巡检',
    description: '核对供电与 ESP8266 链路', priority: 'high', requires_confirmation: true };
  beforeEach(() => {
    vi.restoreAllMocks(); vi.spyOn(api, 'agentContext').mockResolvedValue({ data: { dataContext: { mode: 'simulated_test', label: '模拟测试 · 隔离验收库' }, modelNotice: '模型主控文字旧编号' } } as never); push.mockClear(); sessionStorage.clear(); setActivePinia(createPinia());
    const operations = useOperationsStore(); operations.source = 'api'; operations.offline = false;
    useAuthStore().user = { id: 1, email: 'test', displayName: '测试人员', role: 'operator' };
    useAiAssistantStore().messages = [{ role: 'assistant', content: '等待人工确认。', proposals: [{ ...proposal }] }];
    wrapper = mount(AiAssistant, { props: { pageName: '运行总览' }, global: { stubs: { Teleport: true } } });
  });
  afterEach(() => { wrapper.unmount(); });

  it('creates nothing until reviewed and explicitly confirmed', async () => {
    const create = vi.spyOn(api, 'createWorkOrder').mockResolvedValue({ data: { code: 'WO-TEST-1' } } as never);
    const control = vi.spyOn(api, 'controllerCommand');
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-proposal button').trigger('click');
    expect(create).not.toHaveBeenCalled();
    expect(wrapper.get('.ai-agent-confirm').text()).toContain('不会执行风机');
    await wrapper.get('.ai-agent-confirm').findAll('button')[1].trigger('click');
    await flushPromises();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create.mock.calls[0][0]).toEqual({ assetCode: 'CTRL-01', title: proposal.title,
      description: proposal.description, priority: 'high' });
    expect(create.mock.calls[0][1]).toMatch(/^agent-/);
    expect(wrapper.get('.ai-agent-proposal').text()).toContain('WO-TEST-1');
    expect(control).not.toHaveBeenCalled();
    control.mockRestore();
  });

  it('retries uncertain submissions with the same idempotency key', async () => {
    const create = vi.spyOn(api, 'createWorkOrder').mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ data: { code: 'WO-TEST-2' } } as never);
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-proposal button').trigger('click');
    await wrapper.get('.ai-agent-confirm').findAll('button')[1].trigger('click');
    await flushPromises();
    expect(wrapper.get('.ai-agent-confirm').text()).toContain('同一幂等键');
    await wrapper.get('.ai-agent-confirm').findAll('button')[1].trigger('click');
    await flushPromises();
    expect(create.mock.calls[0][1]).toBe(create.mock.calls[1][1]);
  });

  it('disables write proposals for viewers', async () => {
    useAuthStore().user!.role = 'viewer';
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    expect(wrapper.get('.ai-agent-proposal button').attributes('disabled')).toBeDefined();
  });

  it('opens only registered asset codes through a fixed twin route', async () => {
    useAiAssistantStore().messages = [{ role: 'assistant', content: '[E1] 核查节点', locations: [{
      assetCode: 'CTRL-01', physicalTag: 'test', controllerId: 'CTRL-01', stationId: 'P1',
      mappingStatus: 'not_checked', evidenceId: 'E1',
    }] }];
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-location button').trigger('click');
    expect(push).toHaveBeenCalledWith({ path: '/twin-3d', query: { asset: 'CTRL-01', source: 'agent' } });
  });

  it('refuses fabricated or external location codes', async () => {
    useAiAssistantStore().messages = [{ role: 'assistant', content: '核查', locations: [{
      assetCode: 'https://evil.invalid', physicalTag: 'test', controllerId: 'CTRL-01', stationId: 'P1',
      mappingStatus: 'not_checked', evidenceId: 'E1',
    }] }];
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-location button').trigger('click');
    expect(push).not.toHaveBeenCalled();
    expect(wrapper.get('[role="alert"]').text()).toContain('台账');
  });
  it('sends the explicit selected station task and shows sandbox provenance', async () => {
    const chat = vi.spyOn(api, 'assistantChat').mockResolvedValue({ data: { reply: '模拟测试：排查结果' } } as never);
    await wrapper.get('.ai-assistant-launcher').trigger('click'); await flushPromises();
    await wrapper.get('[aria-label="选择排障检测点"]').setValue('P2');
    await wrapper.findAll('.ai-agent-workflow button')[0].trigger('click'); await flushPromises();
    expect(chat).toHaveBeenCalled();
    expect(chat.mock.calls[0][2]).toEqual({ kind: 'diagnosis', station_id: 'P2' });
    expect(wrapper.get('.ai-agent-context').text()).toContain('模拟测试');
  });

  it('uses the returned work order code for a read-only follow-up', async () => {
    vi.spyOn(api, 'createWorkOrder').mockResolvedValue({ data: { code: 'WO-RETURNED-123' } } as never);
    const chat = vi.spyOn(api, 'assistantChat').mockResolvedValue({ data: { reply: '待人工复核' } } as never);
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-proposal button').trigger('click');
    await wrapper.get('.ai-agent-confirm').findAll('button')[1].trigger('click'); await flushPromises();
    await wrapper.get('.ai-agent-proposal button').trigger('click'); await flushPromises();
    expect(chat.mock.calls[0][2]).toEqual({ kind: 'review', work_order_code: 'WO-RETURNED-123' });
  });

  it('cancels a proposal without creating a work order', async () => {
    const create = vi.spyOn(api, 'createWorkOrder');
    await wrapper.get('.ai-assistant-launcher').trigger('click');
    await wrapper.get('.ai-agent-proposal button').trigger('click');
    await wrapper.get('.ai-agent-confirm').findAll('button')[0].trigger('click');
    expect(wrapper.find('.ai-agent-confirm').exists()).toBe(false);
    expect(create).not.toHaveBeenCalled();
  });

});
