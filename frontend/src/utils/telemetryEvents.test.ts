import { describe, expect, it } from 'vitest';
import { init, use } from 'echarts/core';
import { SVGRenderer } from 'echarts/renderers';
import { LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent } from 'echarts/components';
import type { Alert } from '../types';
import { telemetryEventSeries } from './telemetryEvents';
use([SVGRenderer, LineChart, GridComponent, LegendComponent, MarkLineComponent]);
const event: Alert = { id: 1, code: 'ALM-TEST', assetCode: 'A', severity: 'critical', category: '环境', status: 'open', title: '测试', detail: '', openedAt: '2026-09-09T00:01:00Z' };
describe('independent telemetry event markers', () => {
  it('rejects invalid dates rather than adding invalid axis markers', () => {
    expect(telemetryEventSeries([event, { ...event, openedAt: 'invalid' }]).markLine.data).toHaveLength(1);
  });
  it('renders the alert line even after the first measurement is hidden', () => {
    const chart = init(null, undefined, { renderer: 'svg', ssr: true, width: 600, height: 340 });
    const time = Date.parse(event.openedAt);
    try {
      chart.setOption({ animation: false, legend: { data: ['A', 'B'] }, xAxis: { type: 'time' }, yAxis: { type: 'value' },
        series: [
          { name: 'A', type: 'line', data: [[time - 60000, 20], [time + 60000, 21]] },
          { name: 'B', type: 'line', data: [[time - 60000, 22], [time + 60000, 23]] },
          telemetryEventSeries([event]),
        ] });
      expect(chart.renderToSVGString()).toContain('stroke="#ff7289"');
      chart.dispatchAction({ type: 'legendUnSelect', name: 'A' });
      expect(chart.renderToSVGString()).toContain('stroke="#ff7289"');
      chart.setOption({ series: [{ id: 'historical-alert-events', markLine: { data: [] } }] });
      expect(chart.renderToSVGString()).not.toContain('stroke="#ff7289"');
    } finally { chart.dispose(); }
  });
});
