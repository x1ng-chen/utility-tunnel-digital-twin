import type { Asset, HardwareBinding, Telemetry } from '../types';

export type TelemetryState = 'demo' | 'missing' | 'offline' | 'stale' | 'invalid' | 'suspect' | 'current';

export function telemetryState(
  reading: Telemetry | null | undefined,
  asset: Asset | null | undefined,
  binding: HardwareBinding | null | undefined,
  source: 'demo' | 'api',
  serviceOffline: boolean,
  now = Date.now(),
): TelemetryState {
  if (source === 'demo') return 'demo';
  if (serviceOffline || asset?.status === 'offline' || binding?.connectivity === 'offline' || binding?.connectivity === 'error') return 'offline';
  if (!reading) return 'missing';
  const sampledAt = Date.parse(reading.recordedAt);
  if (!Number.isFinite(sampledAt) || sampledAt > now + 60_000 || reading.quality === 'bad' || reading.quality === 'missing' || !Number.isFinite(reading.value)) return 'invalid';
  const expectedSeconds = binding?.expectedIntervalSeconds;
  const staleAfterMs = Math.max(15, (expectedSeconds && expectedSeconds > 0 ? expectedSeconds : 60) * 3) * 1000;
  if (now - sampledAt > staleAfterMs) return 'stale';
  if (reading.quality === 'suspect') return 'suspect';
  return 'current';
}

export const telemetryStateLabel: Record<TelemetryState, string> = {
  demo: '演示数据', missing: '暂无采集数据', offline: '离线 · 历史数据', stale: '采集已过期',
  invalid: '数据待核验', suspect: '数据需核查', current: '最近有效上报',
};

export function displayTelemetryValue(reading: Telemetry | null | undefined, state: TelemetryState, digits = 0): string {
  if (!reading || !Number.isFinite(reading.value) || (state !== 'current' && state !== 'demo')) return '—';
  return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(reading.value);
}

export function latestTelemetry(readings: Telemetry[], assetCode: string, metricKey?: string): Telemetry | undefined {
  return readings
    .filter((reading) => reading.assetCode === assetCode && (!metricKey || reading.metricKey === metricKey || reading.metric === metricKey))
    .reduce<Telemetry | undefined>((latest, reading) => !latest || Date.parse(reading.recordedAt) > Date.parse(latest.recordedAt) ? reading : latest, undefined);
}
