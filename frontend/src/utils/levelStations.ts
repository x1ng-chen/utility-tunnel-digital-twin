import type { Alert, Asset, HardwareBinding, Telemetry } from '../types';
import { activeTwinAlerts } from '../services/twin3d';
import { latestTelemetry, telemetryState, telemetryStateLabel } from './telemetryState';

export const levelStations = [
  { code: 'LEVEL-L01', section: '排水段' },
  { code: 'LEVEL-L02', section: '吸水段' },
  { code: 'LEVEL-L03', section: '泵入口' },
  { code: 'LEVEL-L04', section: '阀后段' },
  { code: 'LEVEL-L05', section: '回水段' },
] as const;

export function levelStationCards(
  assets: Asset[], alerts: Alert[], telemetry: Telemetry[], bindings: HardwareBinding[],
  source: 'demo' | 'api', offline: boolean, now = Date.now(),
) {
  return levelStations.map((station) => {
    const asset = assets.find((item) => item.code === station.code);
    const reading = latestTelemetry(telemetry, station.code, 'level.detected');
    const binding = bindings.find((item) => item.assetCode === station.code);
    const alert = activeTwinAlerts(station.code, alerts)[0];
    const state = telemetryState(reading, asset, binding, source, offline, now);
    const summary = source === 'demo' ? '演示节点 · 非现场告警'
      : offline ? '平台离线 · 无法确认当前状态'
        : alert ? '测点告警 · 核查对应管段'
          : asset?.integrationStatus === 'pending_verification' ? '待接入与现场核验'
            : telemetryStateLabel[state];
    return { ...station, asset, reading, alert, state, summary };
  });
}
