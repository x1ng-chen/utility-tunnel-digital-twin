// @vitest-environment happy-dom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import Trace from './AgentDecisionEvidence.vue';
describe('AnyJev实际路由记录',()=>{
  it('does not invent local model execution for historical runs',()=>{
    const wrapper=mount(Trace,{props:{result:{}}});expect(wrapper.text()).toContain('未记录本地路由调用');expect(wrapper.findAll('.decisions li')).toHaveLength(0);wrapper.unmount();
  });
  it('distinguishes the chosen option from a fallback and from actual tool execution',()=>{
    const wrapper=mount(Trace,{props:{result:{decisionTrace:[{status:'selected',selectedOption:'read_snapshot',model:'AnyJev Tacit-1.7B',modelRevision:'local-sha',probabilities:{read_snapshot:.7},executedTool:'asset_snapshot',executedEvidenceId:'E4'},{status:'fallback',fallbackReason:'decision_timeout',model:'AnyJev Tacit-1.7B'}]}}});
    expect(wrapper.text()).toContain('实际工具：asset_snapshot');expect(wrapper.text()).toContain('证据：E4');expect(wrapper.text()).toContain('回退原因：decision_timeout');expect(wrapper.text()).toContain('选项分布不等于火灾');expect(wrapper.text()).not.toContain('官方Jev');wrapper.unmount();
  });
});
