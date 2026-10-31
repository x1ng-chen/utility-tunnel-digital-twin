// @vitest-environment happy-dom
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import TwinAlarmOverlay from './TwinAlarmOverlay.vue';
import type { VisualAlarm } from '../utils/twinAlarmStyle';
const alarm:VisualAlarm={assetCode:'FLAME-05',zone:'P5',title:'火焰告警',severity:'critical',alertId:408};
const label={...alarm,anchorX:300,anchorY:260,x:320,y:180,width:174};
describe('alarm position overlay',()=>{
  it('shows the exact station/device, emits a location request and disappears on recovery',async()=>{
    const wrapper=mount(TwinAlarmOverlay,{props:{alarms:[alarm],labels:[label],unplacedCodes:[]}});
    expect(wrapper.text()).toContain('P5');expect(wrapper.text()).toContain('火焰告警');expect(wrapper.text()).toContain('FLAME-05');
    await wrapper.get('button.twin-alarm-tag').trigger('click');
    expect(wrapper.emitted('select')).toEqual([['FLAME-05']]);
    await wrapper.setProps({alarms:[],labels:[]});expect(wrapper.find('[data-testid="twin-alarm-overlay"]').exists()).toBe(false);wrapper.unmount();
  });
  it('reports missing bindings instead of claiming the device was marked',()=>{
    const wrapper=mount(TwinAlarmOverlay,{props:{alarms:[alarm],labels:[],unplacedCodes:['FLAME-05']}});
    expect(wrapper.text()).toContain('三维位置未绑定');expect(wrapper.get('.twin-alarm-summary button').attributes('disabled')).toBeDefined();wrapper.unmount();
  });
});
