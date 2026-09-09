import { describe, expect, it } from 'vitest';
import type { Telemetry } from '../types';
import { selectSignalWindow } from './dashboardSignal';

const sample: Telemetry = { id: 1, assetCode: 'ENV-01', metricKey: 'temperature', metric: '温度', value: 20, unit: '°C', quality: 'good', recordedAt: '2026-09-05T00:00:00Z' };
describe('dashboard signal window', () => {
  it('separates devices, metrics and units', () => {
    const items = [sample, { ...sample, id: 2, assetCode: 'ENV-02' }, { ...sample, id: 3, metricKey: 'humidity' }, { ...sample, id: 4, unit: '°F' }];
    expect(selectSignalWindow(items, sample)).toEqual([sample]);
    expect(items).toHaveLength(4);
  });
  it('orders the latest 30 samples chronologically without mutating the source', () => {
    const items = Array.from({ length: 35 }, (_, id) => ({ ...sample, id, recordedAt: new Date(Date.parse(sample.recordedAt) + id * 1000).toISOString() }));
    expect(selectSignalWindow(items, sample).map((item) => item.id)).toEqual(Array.from({ length: 30 }, (_, i) => i + 5));
    expect(items[0].id).toBe(0);
  });
  it('does not plot missing, non-finite or invalid-time readings', () => {
    expect(selectSignalWindow([{ ...sample, quality: 'missing' }, { ...sample, value: NaN }, { ...sample, recordedAt: 'invalid' }], sample)).toEqual([]);
    expect(selectSignalWindow([sample], null)).toEqual([]);
  });
  it('supports legacy measurements without a metric key', () => {
    expect(selectSignalWindow([sample, { ...sample, metric: '湿度' }], { ...sample, metricKey: undefined })).toEqual([sample]);
  });
});
