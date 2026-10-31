// @vitest-environment happy-dom
import {mount} from '@vue/test-utils';
import {describe,it,expect} from 'vitest';
import Hub from './AgentMissionHub.vue';
import type {Asset,Alert,WorkOrder} from '../types';
const link={props:['to'],template:'<a><slot /></a>'};
describe('Agent-first task hub',()=>{
  it('prepares the actual alarm station and existing recovery order without performing actions',()=>{
    const wrapper=mount(Hub,{props:{assets:[{code:'FLAME-05',zone:'P5'} as Asset],alerts:[{code:'ALM-TEST-05',assetCode:'FLAME-05',title:'火焰告警',severity:'critical',status:'open',openedAt:'2026-10-29T00:00:00Z'} as Alert],orders:[{code:'WO-TEST-01',title:'复查',status:'pending_review'} as WorkOrder],modelPaused:true},global:{stubs:{RouterLink:link}}});
    const links=wrapper.findAllComponents(link);
    expect(links[1].props('to')).toMatchObject({query:{task:'inspection',station:'all'}});
    expect(links[2].props('to')).toMatchObject({query:{task:'diagnosis',station:'P5',asset:'FLAME-05',alert:'ALM-TEST-05'}});
    expect(links[3].props('to')).toMatchObject({query:{task:'review',order:'WO-TEST-01'}});
    expect(wrapper.text()).toContain('当前环境暂停模型调用');expect(wrapper.text()).toContain('职责说明');wrapper.unmount();
  });
});
