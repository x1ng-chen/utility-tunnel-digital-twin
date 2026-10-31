import { Color, type MeshStandardMaterial } from 'three';
import type { Alert, Asset } from '../types';
import { primaryTwinAlert, type TwinVisualState } from '../services/twin3d';

export const twinVisualColors = {normal:0x4ee7c3, warning:0xffb24a, alarm:0xff3157, unknown:0x6d87aa};
export type MaterialBaseline = {color:Color; emissive:Color};

export function visualIntensity(state: TwinVisualState, selected: boolean, critical: boolean, seconds = 0) {
  if (state === 'alarm') return (critical ? 3.25 : 2.2) + Math.sin(seconds * 2.7) * .3 + (selected ? .25 : 0);
  if (selected) return 1.35;
  return state === 'warning' ? .95 : .32;
}

export function paintTwinMaterial(material: MeshStandardMaterial, baseline: MaterialBaseline,
  state: TwinVisualState, selected: boolean, critical: boolean) {
  const color = new Color(state === 'alarm' && !critical ? twinVisualColors.warning : twinVisualColors[state]);
  material.color.copy(baseline.color).lerp(color, state === 'alarm' ? .66 : selected ? .31 : .06);
  material.emissive.copy(baseline.emissive).lerp(color, state === 'alarm' ? .96 : state === 'warning' ? .52 : .26);
  material.emissiveIntensity = visualIntensity(state, selected, critical);
}

export function collectVisualAlarms(assets: Asset[], alerts: Alert[]) {
  return assets.flatMap(asset => {
    const alert = primaryTwinAlert(asset.code, alerts);
    if (asset.status !== 'alarm' && (!alert || !['critical','warning'].includes(alert.severity))) return [];
    const severity = alert?.severity === 'warning' ? 'warning' as const : 'critical' as const;
    return [{assetCode:asset.code, zone:asset.zone || '未分区', severity,
      title:alert?.ruleKey === 'flame.alarm' ? '火焰告警' : alert?.title || '设备告警',
      alertId:alert?.id ?? null}];
  }).sort((a,b) => Number(b.severity === 'critical')-Number(a.severity === 'critical') || a.assetCode.localeCompare(b.assetCode));
}

export type VisualAlarm = ReturnType<typeof collectVisualAlarms>[number];
