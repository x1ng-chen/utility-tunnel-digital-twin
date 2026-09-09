import type { Alert } from '../types';

/** Keep event markers independent of which measurement legend is selected. */
export function telemetryEventSeries(events: Alert[]) {
  return {
    id: 'historical-alert-events', name: '告警事件', type: 'line' as const,
    data: [] as Array<[number, number]>, silent: true,
    markLine: {
      symbol: 'none', silent: true, label: { show: false },
      data: events.filter(event => Number.isFinite(Date.parse(event.openedAt))).map(event => ({
        name: event.code, xAxis: Date.parse(event.openedAt),
        lineStyle: { color: event.severity === 'critical' ? '#ff7289' : '#f2b064', type: 'dashed' as const },
      })),
    },
  };
}
