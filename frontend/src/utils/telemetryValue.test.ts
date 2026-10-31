import { describe, expect, it } from 'vitest';
import type { Telemetry } from '../types';
import { telemetryValue } from './telemetryValue';
const row = (quality: Telemetry['quality'], value = 0): Telemetry => ({id:1, assetCode:'FAN-01', metric:'功率', value, unit:'W', quality, recordedAt:'2026-10-28T00:00:00Z'});
describe('measurement placeholders', () => {
  it('distinguishes missing from measured zero and preserves suspect raw values', () => {
    expect(telemetryValue(row('missing'))).toBe('缺测');
    expect(telemetryValue(row('good'))).toBe('0 W');
    expect(telemetryValue(row('suspect', 4095))).toBe('4095 W');
    expect(telemetryValue(row('good', NaN))).toBe('缺测');
  });
});
