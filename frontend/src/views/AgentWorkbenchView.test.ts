// @vitest-environment happy-dom
import { createPinia,setActivePinia } from 'pinia';
import { mount,flushPromises } from '@vue/test-utils';
import { describe,it,expect,vi,beforeEach,afterEach } from 'vitest';
import View from './AgentWorkbenchView.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
vi.mock('../components/AppShell.vue',()=>({default:{template:'<div><slot /></div>'}}));
describe('persistent Agent workbench',()=>{
 let wrapper:ReturnType<typeof mount>;
 beforeEach(()=>{
  vi.restoreAllMocks();setActivePinia(createPinia());
  useAuthStore().user={id:1,email:'operator',displayName:'operator',role:'operator'};
  vi.spyOn(api,'agentContext').mockResolvedValue({data:{dataContext:{label:'模拟测试 · 隔离库'},modelNotice:'旧模型文字'}} as never);
  vi.spyOn(api,'demoSession').mockResolvedValue({data:{session:{phase:0,running:false,tick:10},cases:['INS-01']}} as never);
  vi.spyOn(api,'agentRuns').mockResolvedValue({data:[]} as never);
 });
 afterEach(()=>wrapper?.unmount());
 it('never invokes models or commands just by mounting',async()=>{
  const start=vi.spyOn(api,'createAgentRun');const control=vi.spyOn(api,'proposeDemoCommand');
  wrapper=mount(View);await flushPromises();
  expect(wrapper.text()).toContain('模拟测试');expect(wrapper.text()).toContain('旧模型文字');
  expect(start).not.toHaveBeenCalled();expect(control).not.toHaveBeenCalled();
  expect(wrapper.text()).not.toContain('重置场景');
 });
 it('viewer cannot create a work-order draft',async()=>{
  useAuthStore().user!.role='viewer';wrapper=mount(View);await flushPromises();
  expect(wrapper.get('option[value=draft]').attributes('disabled')).toBeDefined();
 });
 it('does not create an order before review and confirmation',async()=>{
  const order=vi.spyOn(api,'createWorkOrder').mockResolvedValue({data:{code:'WO-TEST'}} as never);
  vi.spyOn(api,'agentRuns').mockResolvedValue({data:[{id:'run-test',status:'completed',input:{},steps:[],runtime:{},result:{proposals:[{assetCode:'MQ4-05',title:'检查',description:'模拟测试',priority:'normal'}]}}]} as never);
  wrapper=mount(View);await flushPromises();
  const button=wrapper.findAll('button').find(b=>b.text()==='审阅工单草案')!;await button.trigger('click');
  expect(order).not.toHaveBeenCalled();await wrapper.get('[role=alertdialog]').findAll('button')[1].trigger('click');await flushPromises();
  expect(order).not.toHaveBeenCalled();
  await button.trigger('click');await wrapper.get('[role=alertdialog]').findAll('button')[0].trigger('click');await flushPromises();
  expect(order).toHaveBeenCalledOnce();expect(wrapper.text()).toContain('WO-TEST');
 });
});
