import { describe, expect, it } from 'vitest';
import type { Telemetry } from '../types';
import { twinTelemetryTrend } from './twinTelemetryTrend';

const row = (overrides: Partial<Telemetry> = {}): Telemetry => ({ id: 1, assetCode: 'A', metricKey: 'temperature', metric: '温度', value: 20, unit: '℃', quality: 'good', recordedAt: '2026-09-09T00:00:00Z', ...overrides });
describe('twin inspector telemetry', () => {
  it('retains explicit gaps and irregular timestamps between valid samples', () => {
    const series = twinTelemetryTrend([row(), row({ id: 2, quality: 'missing', recordedAt: '2026-09-09T00:01:00Z' }), row({ id: 3, value: 24, recordedAt: '2026-09-09T00:07:00Z' })], row());
    expect(series[0]!.data.map(point => point[1])).toEqual([20, null, 24]);
    expect(series[0]!.data[2]![0] - series[0]!.data[1]![0]).toBe(360000);
  });
  it('excludes other devices, metrics, units and handles no selection', () => {
    const items = [row(), row({ assetCode: 'B' }), row({ metricKey: 'humidity' }), row({ unit: 'F' })];
    expect(twinTelemetryTrend(items, row())).toEqual([{ name: 'A', data: [[Date.parse(row().recordedAt), 20]] }]);
    expect(twinTelemetryTrend(items, null)).toEqual([]);
  });
});
