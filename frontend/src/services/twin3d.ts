import type { Alert, Asset } from '../types';

export type TwinVisualState = 'normal' | 'warning' | 'alarm' | 'unknown';

export interface TwinModelBindingSummary {
  expectedCount: number;
  boundCodes: string[];
  missingCodes: string[];
  isComplete: boolean;
}

export interface TwinModelBindingReport extends TwinModelBindingSummary {
  mode: 'loaded' | 'fallback';
}

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

/**
 * Keeps the Blender delivery contract separate from the interactive fallback
 * geometry. A fallback marker is clickable, but is never counted as a real
 * model-node binding.
 */
export function summarizeTwinModelBindings(assets: Asset[], boundCodes: Iterable<string>): TwinModelBindingSummary {
  const bound = new Set(boundCodes);
  const resolved = assets.filter((asset) => bound.has(asset.code)).map((asset) => asset.code);
  const missing = assets.filter((asset) => !bound.has(asset.code)).map((asset) => asset.code);
  return { expectedCount: assets.length, boundCodes: resolved, missingCodes: missing, isComplete: missing.length === 0 };
}

export function twinStateLabel(state: TwinVisualState) {
  return ({ normal: '运行正常', warning: '需要关注', alarm: '告警定位', unknown: '待核验' })[state];
}
