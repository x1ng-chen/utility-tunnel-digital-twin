// @vitest-environment happy-dom
import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Panel from './AgentInvestigationPanel.vue';
import { api, type InvestigationCase } from '../services/api';

const fixture=():InvestigationCase=>({id:'case-test',title:'P5间歇异常',stationId:'P5',assetCode:'FLAME-05',status:'waiting',revision:3,source:{label:'模拟测试'},layoutVersion:'layout-test',presentationVersion:'V20',hypotheses:[{id:'h1',label:'探头视场受干扰',status:'candidate',supportRefs:['E1'],counterRefs:['E2'],missing:['现场观察'],snapshotHash:'snapshot-old'}],checks:[{id:'human-check',label:'观察探头周围光源',kind:'human',status:'pending'},{id:'software-check',label:'读取设备心跳',kind:'software',status:'pending'}],history:[],runs:[]});
const show=(extra={})=>mount(Panel,{props:{station:'P5',running:false,modelCallsDisabled:false,...extra}});
async function createArchive(wrapper:ReturnType<typeof show>){await wrapper.findAll('button').find(button=>button.text()==='新建档案')!.trigger('click');await wrapper.get('form.case-create').trigger('submit');await flushPromises();}
describe('可接续排障档案',()=>{
  beforeEach(()=>{vi.restoreAllMocks();sessionStorage.clear();sessionStorage.setItem('ut-django-token','TEST_STUB');});
  it('creates and selects an archive without invoking a model',async()=>{
    const create=vi.spyOn(api,'createInvestigationCase').mockResolvedValue({data:fixture()} as never);
    const run=vi.spyOn(api,'createAgentRun');const wrapper=show();
    expect(create).not.toHaveBeenCalled();await createArchive(wrapper);
    expect(create).toHaveBeenCalledWith({station_id:'P5'});expect(run).not.toHaveBeenCalled();
    expect(wrapper.emitted('select-case')?.[0]?.[0]).toMatchObject({id:'case-test'});
    expect(wrapper.text()).toContain('尚未调用模型');expect(wrapper.text()).toContain('snapshot-old');
    wrapper.unmount();
  });
  it('accepts human feedback with a revision and never offers to overwrite software evidence',async()=>{
    const item=fixture();vi.spyOn(api,'createInvestigationCase').mockResolvedValue({data:item} as never);
    const feedback=vi.spyOn(api,'investigationFeedback').mockResolvedValue({data:{...item,revision:4,checks:[{...item.checks[0],status:'completed',report:'移开红色灯光后不再触发'}]}} as never);
    const wrapper=show();await createArchive(wrapper);
    expect(wrapper.findAll('textarea')).toHaveLength(1);
    await wrapper.get('textarea').setValue('移开红色灯光后不再触发');await wrapper.get('textarea').element.closest('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await flushPromises();
    expect(feedback).toHaveBeenCalledWith('case-test',{check_id:'human-check',status:'completed',report:'移开红色灯光后不再触发',revision:3});
    expect(wrapper.text()).toContain('未自动判定故障恢复');wrapper.unmount();
  });
  it('retains a report after a stale-revision rejection',async()=>{
    vi.spyOn(api,'createInvestigationCase').mockResolvedValue({data:fixture()} as never);
    vi.spyOn(api,'investigationFeedback').mockRejectedValue({response:{status:409}});
    const wrapper=show();await createArchive(wrapper);
    await wrapper.get('textarea').setValue('当前无法接近探头');
    await wrapper.findAll('button').find(button=>button.text()==='记录无法执行')!.trigger('click');await flushPromises();
    expect(wrapper.get('[role=alert]').text()).toContain('档案已被更新');expect(wrapper.get('textarea').element.value).toBe('当前无法接近探头');
    expect(wrapper.emitted('continue-case')).toBeUndefined();wrapper.unmount();
  });
  it('honors the server model pause when continuing a saved archive',async()=>{
    vi.spyOn(api,'createInvestigationCase').mockResolvedValue({data:fixture()} as never);
    const wrapper=show({modelCallsDisabled:true});await createArchive(wrapper);
    const button=wrapper.findAll('button').find(button=>button.text()==='继续调查（调用模型）')!;
    expect(button.attributes('disabled')).toBeDefined();await button.trigger('click');expect(wrapper.emitted('continue-case')).toBeUndefined();wrapper.unmount();
  });
});
