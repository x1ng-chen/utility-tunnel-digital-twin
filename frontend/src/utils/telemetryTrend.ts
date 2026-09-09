import type { Telemetry } from '../types';

/** Preserve actual timestamps; never interpolate or combine units/devices. */
export function telemetryTrend(items: Telemetry[], selected: Telemetry | null) {
  if (!selected) return [];
  const groups = new Map<string, Map<number, Telemetry>>();
  for (const item of items) {
    const time = Date.parse(item.recordedAt);
    if ((selected.metricKey ? item.metricKey !== selected.metricKey : item.metric !== selected.metric)
      || item.unit !== selected.unit || !Number.isFinite(time)) continue;
    const points = groups.get(item.assetCode) ?? new Map<number, Telemetry>();
    // A deterministic winner for duplicate timestamps, independent of API ordering.
    if (!points.has(time) || points.get(time)!.id < item.id) points.set(time, item);
    groups.set(item.assetCode, points);
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([name, points]) => ({
    name,
    data: [...points].sort(([a], [b]) => a - b).map(([time, item]): [number, number | null] =>
      [time, item.quality === 'missing' || !Number.isFinite(item.value) ? null : item.value]),
  }));
}
