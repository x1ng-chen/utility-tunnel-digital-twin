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

export interface TwinModelDeliveryReadiness {
  activeAssetCount: number;
  mappedAssetCount: number;
  missingMeshCodes: string[];
  invalidMeshCodes: string[];
  isReady: boolean;
}

export interface TwinModelReadinessResponse {
  status: 'ready' | 'blocked';
  summary: { activeAssetCount: number; mappedAssetCount: number; unmappedAssetCount: number };
  missingMeshCodes: string[];
  invalidMeshCodes: string[];
  contract: { nodeNamePattern: string; nodeNamesUnique: boolean; modelFileVerified: boolean };
  updatedAt: string | null;
}

export const twinModelUrl = (import.meta.env.VITE_TWIN_MODEL_URL || '/models/utility-tunnel.glb').trim();
const modelNodeNamePattern = /^[A-Z0-9][A-Z0-9_-]{1,79}$/;

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

/**
 * Checks the Blender handoff contract before a model file is delivered. It
 * deliberately validates asset metadata only; it never treats the fallback
 * scene as proof that an entity model exists.
 */
export function summarizeTwinModelDelivery(assets: Asset[]): TwinModelDeliveryReadiness {
  const activeAssets = assets.filter((asset) => asset.isActive !== false);
  const missingMeshCodes = activeAssets.filter((asset) => !asset.mesh?.trim()).map((asset) => asset.code);
  const invalidMeshCodes = activeAssets
    .filter((asset) => Boolean(asset.mesh?.trim()) && !modelNodeNamePattern.test(asset.mesh.trim()))
    .map((asset) => asset.code);
  const mappedAssetCount = activeAssets.length - missingMeshCodes.length - invalidMeshCodes.length;
  return {
    activeAssetCount: activeAssets.length,
    mappedAssetCount,
    missingMeshCodes,
    invalidMeshCodes,
    isReady: missingMeshCodes.length === 0 && invalidMeshCodes.length === 0,
  };
}

export function twinStateLabel(state: TwinVisualState) {
  return ({ normal: '运行正常', warning: '需要关注', alarm: '告警定位', unknown: '待核验' })[state];
}
