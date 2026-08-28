import type { Alert, Asset } from '../types';

export type TwinVisualState = 'normal' | 'warning' | 'alarm' | 'unknown';

export const twinModelUrl = (import.meta.env.VITE_TWIN_MODEL_URL || '/models/utility-tunnel.glb').trim();

export function resolveTwinVisualState(asset: Asset, alerts: Alert[]): TwinVisualState {
  if (alerts.some((alert) => alert.assetCode === asset.code && !['resolved', 'closed'].includes(alert.status))) return 'alarm';
  if (asset.status === 'warning') return 'warning';
  if (asset.status === 'normal') return 'normal';
  return 'unknown';
}

export function modelNodeNames(asset: Asset) {
  return [asset.mesh, asset.code, `ASSET_${asset.code.replaceAll('-', '_')}`].filter(Boolean);
}

export function twinStateLabel(state: TwinVisualState) {
  return ({ normal: '运行正常', warning: '需要关注', alarm: '告警定位', unknown: '待核验' })[state];
}
