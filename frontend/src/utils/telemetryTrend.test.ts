import { describe, expect, it } from 'vitest';
import type { Telemetry } from '../types';
import { telemetryTrend } from './telemetryTrend';
const row = (overrides: Partial<Telemetry> = {}): Telemetry => ({ id: 1, assetCode: 'A', metricKey: 'temperature', metric: '温度', value: 20, unit: '℃', quality: 'good', recordedAt: '2026-09-09T00:00:00Z', ...overrides });
describe('historical multi-device trend', () => {
  it('separates devices and excludes different metrics and units', () => {
    const result = telemetryTrend([row(), row({ assetCode: 'B' }), row({ unit: 'F' }), row({ metricKey: 'humidity' })], row());
    expect(result.map(item => item.name)).toEqual(['A', 'B']);
    expect(result.every(item => item.data.length === 1)).toBe(true);
  });
  it('keeps irregular time spacing and missing readings as explicit gaps', () => {
    const result = telemetryTrend([row({ id: 3, recordedAt: '2026-09-09T00:07:00Z', quality: 'missing' }), row(), row({ id: 2, recordedAt: '2026-09-09T00:01:00Z', value: NaN })], row());
    expect(result[0]!.data.map(point => point[1])).toEqual([20, null, null]);
    expect(result[0]!.data[2]![0] - result[0]!.data[1]![0]).toBe(360000);
  });
  it('deduplicates consistently, ignores invalid dates and handles no selection', () => {
    const rows = [row(), row({ id: 2, value: 22 }), row({ recordedAt: 'invalid' })];
    expect(telemetryTrend(rows, row())).toEqual(telemetryTrend([...rows].reverse(), row()));
    expect(telemetryTrend(rows, row())[0]!.data).toHaveLength(1);
    expect(telemetryTrend(rows, null)).toEqual([]);
  });
});
