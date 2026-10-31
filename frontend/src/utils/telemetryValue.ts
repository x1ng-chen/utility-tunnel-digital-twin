import type { Telemetry } from '../types';

/** Keep placeholder zero distinct from a valid measured zero. */
export function telemetryValue(item: Telemetry): string {
  return item.quality === 'missing' || !Number.isFinite(item.value) ? '缺测' : `${item.value} ${item.unit}`;
}
