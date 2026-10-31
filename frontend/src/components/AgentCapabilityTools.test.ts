// @vitest-environment happy-dom
import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Tools from './AgentCapabilityTools.vue';
import { api } from '../services/api';
const show=(extra={})=>mount(Tools,{props:{station:'P5',canWrite:true,admin:false,...extra}});
describe('受控调查工具',()=>{
  beforeEach(()=>{vi.restoreAllMocks();sessionStorage.clear();sessionStorage.setItem('ut-django-token','TEST_STUB');});
  it('loads approved procedures and prepares a selection without executing it',async()=>{
    vi.spyOn(api,'agentProcedures').mockResolvedValue({data:{items:[{id:'approved-1',title:'火焰探头只读核查',status:'approved',stationId:'P5',revision:2},{id:'candidate-1',title:'未经审核',status:'candidate',revision:1}]}} as never);
    const execute=vi.spyOn(api,'createAgentRun');const wrapper=show();
    await wrapper.findAll('button').find(button=>button.text()==='加载检查模板')!.trigger('click');await flushPromises();
    const prepared=wrapper.findAll('button').filter(button=>button.text().startsWith('准备模板：'));expect(prepared).toHaveLength(1);await prepared[0].trigger('click');
    expect(wrapper.emitted('select-procedure')?.[0]?.[0]).toMatchObject({id:'approved-1'});expect(execute).not.toHaveBeenCalled();expect(wrapper.text()).not.toContain('批准检查模板');wrapper.unmount();
  });
  it('keeps viewer template access read-only and preserves revision when an administrator reviews',async()=>{
    vi.spyOn(api,'agentProcedures').mockResolvedValue({data:[{id:'candidate-1',title:'待审模板',status:'candidate',revision:4}]} as never);
    const review=vi.spyOn(api,'reviewAgentProcedure').mockResolvedValue({data:{}} as never);
    const viewer=show({canWrite:false,admin:false});await viewer.findAll('button').find(button=>button.text()==='加载检查模板')!.trigger('click');await flushPromises();expect(viewer.find('.candidate-form').exists()).toBe(false);expect(viewer.text()).not.toContain('批准检查模板');viewer.unmount();
    const administrator=show({admin:true});await administrator.findAll('button').find(button=>button.text()==='加载检查模板')!.trigger('click');await flushPromises();await administrator.findAll('button').find(button=>button.text()==='批准检查模板')!.trigger('click');await flushPromises();expect(review).toHaveBeenCalledWith('candidate-1','approve',4);administrator.unmount();
  });
  it('compares only an explicitly selected run and does not trigger model or hardware calls',async()=>{
    const compare=vi.spyOn(api,'compareAgentBranches').mockResolvedValue({data:{source:'SIMULATED_TEST',branches:[]}} as never);const run=vi.spyOn(api,'createAgentRun');const command=vi.spyOn(api,'proposeDemoCommand');
    const wrapper=show({runId:'run-frozen',runStatus:'completed'});expect(compare).not.toHaveBeenCalled();await wrapper.findAll('button').find(button=>button.text()==='比较隔离仿真分支')!.trigger('click');await flushPromises();expect(compare).toHaveBeenCalledWith('run-frozen');expect(run).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();wrapper.unmount();
  });
  it('extracts a candidate only on explicit request and never starts a model task',async()=>{
    const extract=vi.spyOn(api,'extractAgentProcedure').mockResolvedValue({data:{status:'candidate'}} as never);
    vi.spyOn(api,'agentProcedures').mockResolvedValue({data:[]} as never);
    const run=vi.spyOn(api,'createAgentRun');
    const wrapper=show({runId:'run-frozen',runStatus:'completed'});
    expect(extract).not.toHaveBeenCalled();
    await wrapper.findAll('button').find(b=>b.text()==='从本任务提取流程候选')!.trigger('click');await flushPromises();
    expect(extract).toHaveBeenCalledWith('run-frozen');expect(run).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('尚未批准');wrapper.unmount();
  });
});
