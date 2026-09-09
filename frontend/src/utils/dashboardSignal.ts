import type { Telemetry } from '../types';

/** A trend must never combine different devices, measurements, or units. */
export function selectSignalWindow(items: Telemetry[], selected: Telemetry | null): Telemetry[] {
  if (!selected) return [];
  return items
    .filter((item) => item.assetCode === selected.assetCode
      && (selected.metricKey ? item.metricKey === selected.metricKey : item.metric === selected.metric)
      && item.unit === selected.unit
      && item.quality !== 'missing'
      && Number.isFinite(item.value)
      && Number.isFinite(Date.parse(item.recordedAt)))
    .sort((a, b) => Date.parse(b.recordedAt) - Date.parse(a.recordedAt))
    .slice(0, 30)
    .reverse();
}
