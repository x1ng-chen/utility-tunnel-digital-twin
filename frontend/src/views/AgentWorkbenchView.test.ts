// @vitest-environment happy-dom
import { createPinia,setActivePinia } from 'pinia';
import { mount,flushPromises } from '@vue/test-utils';
import { describe,it,expect,vi,beforeEach,afterEach } from 'vitest';
import View from './AgentWorkbenchView.vue';
import { api } from '../services/api';
import { useAuthStore } from '../stores/auth';
import AgentInvestigationPanel from '../components/AgentInvestigationPanel.vue';
import AgentCapabilityTools from '../components/AgentCapabilityTools.vue';
const { entryQuery } = vi.hoisted(()=>({entryQuery:{} as Record<string,string>}));
vi.mock('vue-router',()=>({useRoute:()=>({query:entryQuery})}));
vi.mock('../components/AppShell.vue',()=>({default:{template:'<div><slot /></div>'}}));
describe('persistent Agent workbench',()=>{
 let wrapper:ReturnType<typeof mount>;
 const show=()=>mount(View,{global:{stubs:{RouterLink:{template:'<a><slot /></a>'}}}});
 beforeEach(()=>{
  vi.restoreAllMocks();sessionStorage.clear();sessionStorage.setItem('ut-django-token','TEST_STUB');setActivePinia(createPinia());
  Object.keys(entryQuery).forEach(key=>delete entryQuery[key]);
  useAuthStore().user={id:1,email:'operator',displayName:'operator',role:'operator'};
  vi.spyOn(api,'agentContext').mockResolvedValue({data:{dataContext:{label:'模拟测试 · 隔离库',demoControlsAvailable:true},modelNotice:'旧模型文字'}} as never);
  vi.spyOn(api,'demoSession').mockResolvedValue({data:{session:{phase:0,running:false,tick:10},cases:['INS-01']}} as never);
  vi.spyOn(api,'agentRuns').mockResolvedValue({data:[]} as never);
  vi.spyOn(api,'reviewExperiences').mockResolvedValue({data:{items:[],truncated:false}} as never);
 });
 afterEach(()=>wrapper?.unmount());
 it('never invokes models or commands just by mounting',async()=>{
  const start=vi.spyOn(api,'createAgentRun');const control=vi.spyOn(api,'proposeDemoCommand');
  wrapper=show();await flushPromises();
  expect(wrapper.text()).toContain('模拟测试');expect(wrapper.text()).toContain('旧模型文字');
  expect(start).not.toHaveBeenCalled();expect(control).not.toHaveBeenCalled();
  expect(wrapper.text()).not.toContain('重置场景');
  expect(wrapper.find('[aria-labelledby=agent-result-title]').exists()).toBe(true);
  expect(wrapper.find('[aria-label=实际Agent执行阶段]').exists()).toBe(false);
  expect(wrapper.findAll('details.tool-panel').every(panel=>panel.attributes('open')===undefined)).toBe(true);
 });
 it('viewer cannot create a work-order draft',async()=>{
  useAuthStore().user!.role='viewer';wrapper=show();await flushPromises();
  expect(wrapper.get('option[value=draft]').attributes('disabled')).toBeDefined();
  expect(wrapper.get('[data-task-kind=draft]').attributes('disabled')).toBeDefined();
 });
 it('task entry prepares the full inspection without a model call or actuator request',async()=>{
  const create=vi.spyOn(api,'createAgentRun');const command=vi.spyOn(api,'proposeDemoCommand');
  wrapper=show();await flushPromises();
  await wrapper.get('.action-options input[type=checkbox]').setValue(true);
  await wrapper.get('[data-task-kind=inspection]').trigger('click');await flushPromises();
  expect(wrapper.get('[data-task-kind=inspection]').attributes('aria-current')).toBe('step');
  expect((wrapper.get('.task-fields select').element as HTMLSelectElement).value).toBe('all');
  expect(wrapper.get('textarea').element.value).toContain('31路物理传感器');
  expect(wrapper.text()).toContain('尚未调用模型');
  expect(create).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
 });
 it('review entry asks for a real work-order number and keeps manual investigation collapsed',async()=>{
  const create=vi.spyOn(api,'createAgentRun');wrapper=show();await flushPromises();
  expect(wrapper.get('.investigation-section').attributes('open')).toBeUndefined();
  await wrapper.get('[data-task-kind=review]').trigger('click');await flushPromises();
  expect(wrapper.text()).toContain('请填写需要复核的工单编号');
  await wrapper.findAll('button').find(button=>button.text()==='开始任务（调用模型）')!.trigger('click');
  expect(create).not.toHaveBeenCalled();
 });
 it('prepares an explicit diagnosis from a page link without running or confirming it',async()=>{
  Object.assign(entryQuery,{task:'diagnosis',station:'P5',asset:'FLAME-05',alert:'ALM-TEST-05'});
  const start=vi.spyOn(api,'createAgentRun');const order=vi.spyOn(api,'createWorkOrder');
  wrapper=show();await flushPromises();
  expect(wrapper.get('.prepared-task').text()).toContain('FLAME-05');
  expect(wrapper.get('.prepared-task').text()).toContain('尚未调用模型');
  expect(wrapper.get('textarea').element.value).toContain('ALM-TEST-05');
  expect(start).not.toHaveBeenCalled();expect(order).not.toHaveBeenCalled();
 });
 it('does not let a task URL select an operator-only draft for a viewer',async()=>{
  useAuthStore().user!.role='viewer';Object.assign(entryQuery,{task:'draft',asset:'FLAME-05'});
  const start=vi.spyOn(api,'createAgentRun');wrapper=show();await flushPromises();
  expect(wrapper.find('.prepared-task').exists()).toBe(false);
  expect(wrapper.text()).toContain('当前账号不能准备工单草案');expect(start).not.toHaveBeenCalled();
 });
 it('honors server model pause while retaining read-only tools and collapsed model details',async()=>{
  vi.mocked(api.agentContext).mockResolvedValue({data:{dataContext:{label:'实物遥测 · 独立联调库',modelCallsDisabled:true},modelNotice:'V20完整布局说明'}} as never);
  vi.mocked(api.agentRuns).mockResolvedValue({data:[{id:'paused-history',status:'completed',input:{},steps:[],runtime:{},result:{}}]} as never);
  const start=vi.spyOn(api,'createAgentRun');
  const search=vi.spyOn(api,'searchKnowledge').mockResolvedValue({data:{mode:'keyword',hits:[],missing:[]}} as never);
  wrapper=show();await flushPromises();
  const actions=wrapper.get('.task-actions').findAll('button');
  expect(actions[0].attributes('disabled')).toBeDefined();
  expect(actions[1].attributes('disabled')).toBeDefined();
  await actions[0].trigger('click');await actions[1].trigger('click');await flushPromises();
  expect(start).not.toHaveBeenCalled();
  expect(wrapper.text()).toContain('当前环境已暂停模型调用，仍可查看历史记录和使用只读工具');
  expect(wrapper.get('.model-context').attributes('open')).toBeUndefined();
  expect(wrapper.get('.model-context').text()).toContain('V20完整布局说明');
  const searchButton=wrapper.findAll('button').find(button=>button.text()==='检索依据')!;
  expect(searchButton.attributes('disabled')).toBeUndefined();
  await searchButton.trigger('click');await flushPromises();expect(search).toHaveBeenCalledOnce();
 });
 it('does not create an order before review and confirmation',async()=>{
  const order=vi.spyOn(api,'createWorkOrder').mockResolvedValue({data:{code:'WO-TEST'}} as never);
  vi.spyOn(api,'agentRuns').mockResolvedValue({data:[{id:'run-test',status:'completed',input:{},steps:[],runtime:{},result:{proposals:[{assetCode:'MQ4-05',title:'检查',description:'模拟测试',priority:'normal'}]}}]} as never);
  wrapper=show();await flushPromises();
  const button=wrapper.findAll('button').find(b=>b.text()==='审阅工单草案')!;await button.trigger('click');
  expect(order).not.toHaveBeenCalled();await wrapper.get('[role=alertdialog]').findAll('button')[1].trigger('click');await flushPromises();
  expect(order).not.toHaveBeenCalled();
  await button.trigger('click');await wrapper.get('[role=alertdialog]').findAll('button')[0].trigger('click');await flushPromises();
  expect(order).toHaveBeenCalledOnce();expect(wrapper.text()).toContain('WO-TEST');
 });
 it('links a continuation to the saved case and clears any prior actuator request',async()=>{
  const create=vi.spyOn(api,'createAgentRun').mockResolvedValue({data:{id:'continued-run',status:'queued',input:{kind:'diagnosis',case_id:'case-1'},steps:[],runtime:{},result:{}}} as never);
  const command=vi.spyOn(api,'proposeDemoCommand');wrapper=show();await flushPromises();
  await wrapper.get('.action-options input[type=checkbox]').setValue(true);
  wrapper.getComponent(AgentInvestigationPanel).vm.$emit('continue-case',{id:'case-1',title:'火焰间歇异常',stationId:'P5',assetCode:'FLAME-05',status:'waiting',revision:1,hypotheses:[],checks:[],history:[],runs:[]});await flushPromises();
  expect(create).toHaveBeenCalledOnce();expect(create.mock.calls[0][0]).toMatchObject({case_id:'case-1',kind:'diagnosis',station_id:'P5',asset_code:'FLAME-05'});
  expect(create.mock.calls[0][0]).not.toHaveProperty('control_request');expect(command).not.toHaveBeenCalled();
 });
 it('prepares an approved procedure and only attaches it after explicit start',async()=>{
  const create=vi.spyOn(api,'createAgentRun').mockResolvedValue({data:{id:'procedure-run',status:'queued',input:{kind:'diagnosis'},steps:[],runtime:{},result:{}}} as never);
  wrapper=show();await flushPromises();wrapper.getComponent(AgentCapabilityTools).vm.$emit('select-procedure',{id:'procedure-1',title:'风机反馈只读检查',stationId:'P2',status:'approved',revision:2});await flushPromises();
  expect(create).not.toHaveBeenCalled();expect(wrapper.text()).toContain('尚未启动');
  await wrapper.findAll('button').find(button=>button.text()==='开始任务（调用模型）')!.trigger('click');await flushPromises();
  expect(create.mock.calls[0][0]).toMatchObject({procedure_id:'procedure-1',station_id:'P2'});
 });
 it('does not bypass a server model pause through a case continuation event',async()=>{
  vi.mocked(api.agentContext).mockResolvedValue({data:{dataContext:{label:'实物联调',modelCallsDisabled:true},modelNotice:''}} as never);
  const create=vi.spyOn(api,'createAgentRun');wrapper=show();await flushPromises();
  wrapper.getComponent(AgentInvestigationPanel).vm.$emit('continue-case',{id:'case-1',title:'只读档案',stationId:'P5',status:'waiting',revision:1,hypotheses:[],checks:[],history:[],runs:[]});await flushPromises();expect(create).not.toHaveBeenCalled();
 });
});
