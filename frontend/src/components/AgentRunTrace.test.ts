// @vitest-environment happy-dom
import {mount} from '@vue/test-utils';
import {describe,it,expect} from 'vitest';
import Trace from './AgentRunTrace.vue';
describe('actual Agent stage evidence',()=>{
  it('shows actual tools, evidence and a revision without inventing absent agents',()=>{
    const wrapper=mount(Trace,{props:{running:false,steps:[{role:'evidence',startedAt:'2026-10-29T00:00:00Z',calls:[{provider:{}}],traces:[{id:'E1',tool:'station_snapshot',status:'ok',queriedAt:'2026-10-29T00:00:00Z'},{id:'E2',tool:'propose_control',status:'rejected'}],output:{summary:'31路需核查',evidence_ids:['E1'],missing:['RPM缺失']}},{role:'review',startedAt:'2026-10-29T00:00:01Z',calls:[{}],traces:[],output:{summary:'不能从电流推断转动',decision:'revise',findings:['补充独立转速']}}]}});
    expect(wrapper.text()).toContain('巡检站点快照');expect(wrapper.text()).toContain('要求修改');
    expect(wrapper.text()).toContain('RPM缺失');expect(wrapper.text()).toContain('拒绝／失败');
    expect(wrapper.findAll('.agent-handoffs>li')).toHaveLength(2);
    expect(wrapper.findAll('h3').map(h=>h.text())).toEqual(['取证Agent','复核Agent']);
    expect(wrapper.findAll('details').every(d=>d.attributes('open')===undefined)).toBe(true);
    wrapper.unmount();
  });
  it('never labels a missing output as complete after an interrupted run',()=>{
    const wrapper=mount(Trace,{props:{running:false,steps:[{role:'diagnosis',startedAt:'',calls:[],traces:[],output:null}]}});
    expect(wrapper.text()).toContain('未完成，记录保留');expect(wrapper.find('.review-decision').exists()).toBe(false);wrapper.unmount();
  });
});
