import { describe, expect, it } from 'vitest';
import type { Asset, HardwareBinding, Telemetry } from '../types';
import { latestTelemetry, telemetryState } from './telemetryState';

const now = Date.parse('2026-09-26T00:10:00Z');
const asset = { code: 'LEVEL-L03', status: 'normal' } as Asset;
const binding = { expectedIntervalSeconds: 30, connectivity: 'online' } as HardwareBinding;
const reading = { assetCode: 'LEVEL-L03', metricKey: 'level.detected', value: 1, quality: 'good', recordedAt: '2026-09-26T00:09:50Z' } as Telemetry;

describe('telemetry state shown to operators', () => {
  it('separates fresh readings from stale, offline, untrusted and demo values', () => {
    expect(telemetryState(reading, asset, binding, 'api', false, now)).toBe('current');
    expect(telemetryState({ ...reading, recordedAt: '2026-09-26T00:08:00Z' }, asset, binding, 'api', false, now)).toBe('stale');
    expect(telemetryState(reading, asset, binding, 'api', true, now)).toBe('offline');
    expect(telemetryState({ ...reading, quality: 'suspect' }, asset, binding, 'api', false, now)).toBe('suspect');
    expect(telemetryState({ ...reading, recordedAt: 'invalid' }, asset, binding, 'api', false, now)).toBe('invalid');
    expect(telemetryState(null, asset, binding, 'api', false, now)).toBe('missing');
    expect(telemetryState(reading, asset, binding, 'demo', false, now)).toBe('demo');
  });

  it('selects only the requested asset and metric', () => {
    expect(latestTelemetry([reading, { ...reading, id: 2, recordedAt: '2026-09-26T00:09:55Z' }, { ...reading, assetCode: 'LEVEL-L04', id: 3 }], 'LEVEL-L03', 'level.detected')?.id).toBe(2);
    expect(latestTelemetry([reading], 'LEVEL-L05')).toBeUndefined();
  });
});
