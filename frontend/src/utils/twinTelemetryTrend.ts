import type { Telemetry } from '../types';
import { telemetryTrend } from './telemetryTrend';

/** A device inspector must preserve gaps without including another device. */
export function twinTelemetryTrend(items: Telemetry[], selected: Telemetry | null) {
  return telemetryTrend(selected ? items.filter(item => item.assetCode === selected.assetCode) : [], selected);
}
