import type { Alert, Asset, TwinModelRelease } from '../types';
import v13AssetBindings from './v13AssetBindings.json';

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
  modelMismatchCodes: string[];
  mappings: Array<{ assetCode: string; meshName: string; status: 'missing' | 'invalid' | 'unverified' | 'matched' | 'not_in_model' }>;
  contract: { nodeNamePattern: string; nodeNamesUnique: boolean; modelFileVerified: boolean; modelNodesCompatible: boolean; modelNodeInventoryAvailable: boolean };
  activeRelease: TwinModelRelease | null;
  updatedAt: string | null;
}

export const twinModelUrl = (import.meta.env.VITE_TWIN_MODEL_URL || '/models/utility-tunnel.glb').trim();
const modelNodeNamePattern = /^[A-Z0-9][A-Z0-9_-]{1,79}$/;
const activeAlertStatuses = new Set<Alert['status']>(['open', 'acknowledged']);
const severityRank: Record<Alert['severity'], number> = { info: 0, warning: 1, critical: 2 };

export function nextTwinCameraDistance(currentDistance: number, scale: number, minDistance: number, maxDistance: number) {
  return Math.min(maxDistance, Math.max(minDistance, Math.max(currentDistance, .001) * scale));
}

export function activeTwinAlerts(assetCode: string, alerts: Alert[]) {
  return alerts
    .filter((alert) => alert.assetCode === assetCode && activeAlertStatuses.has(alert.status))
    .sort((left, right) => severityRank[right.severity] - severityRank[left.severity] || left.openedAt.localeCompare(right.openedAt));
}

export function primaryTwinAlert(assetCode: string, alerts: Alert[]) {
  return activeTwinAlerts(assetCode, alerts)[0] ?? null;
}

const leakPattern = /泄漏|渗漏|水浸|积水|甲烷|燃气|可燃气/i;

export function alertIndicatesLeak(alert: Alert) {
  return leakPattern.test(`${alert.category} ${alert.title} ${alert.detail}`);
}

export function leakCapableAsset(asset: Asset) {
  return leakPattern.test(`${asset.code} ${asset.name} ${asset.type} ${asset.capabilities.join(' ')}`)
    || asset.code.startsWith('LEVEL-L')
    || asset.code === 'GAS-01'
    || asset.code === 'SEEP-W01';
}

export function leakPipeNodeNames(asset: Asset) {
  const code = asset.code.replaceAll('-', '_');
  const mesh = asset.mesh?.trim();
  return [
    `PIPE_${code}`,
    `PIPE_SEGMENT_${code}`,
    mesh ? `${mesh}_PIPE` : '',
    mesh ? mesh.replace(/_PROBE$/i, '_PIPE') : '',
  ].filter(Boolean);
}

export function leakPipeLabel(asset: Asset) {
  if (asset.code === 'GAS-01') return '燃气主管监测段';
  if (asset.code === 'SEEP-W01') return '排水管渗漏监测段';
  if (asset.code.startsWith('LEVEL-L')) return asset.name.replace(/^液位\d+\s*·\s*/, '管段 · ');
  return `${asset.zone} · ${asset.name}关联管段`;
}

export function resolveTwinVisualState(asset: Asset, alerts: Alert[]): TwinVisualState {
  const active = activeTwinAlerts(asset.code, alerts);
  if (asset.status === 'alarm' || active.some((alert) => alert.severity === 'critical')) return 'alarm';
  if (asset.status === 'warning' || active.some((alert) => alert.severity === 'warning')) return 'warning';
  if (asset.status === 'normal') return 'normal';
  return 'unknown';
}

export function modelNodeNames(asset: Asset) {
  // These physical sensors do not exist. A stale mesh value must not attach
  // them to a station occupied by another sensor.
  if (/^(?:SHT30|SHT)-05$|^LEVEL-(?:L)?05$|^O2-0[4-5]$/.test(asset.code)) return [];
  const legacyBinding = (v13AssetBindings as Record<string, string>)[asset.code];
  const positionMappedSensor = /^(?:(?:SHT30|SHT)-0[1-4]|O2-0[1-3])$/.test(asset.code);
  const stalePositionMesh = /^(?:SHT30|ME2O2)-0[1-5]-/.test(asset.mesh ?? '');
  const mesh = positionMappedSensor && stalePositionMesh ? null : asset.mesh;
  return [...twinSensorModelNodeNames(asset.code), mesh, legacyBinding, asset.code, `ASSET_${asset.code.replaceAll('-', '_')}`].filter((name): name is string => Boolean(name));
}

/** Empty V13 display stations have no physical sensor or live alarm location. */
export function isUnoccupiedTwinModelNodeName(name: string): boolean {
  return /^(?:SHT30-03|ME2O2-(?:02|04))-/.test(name);
}

/** Match bench telemetry codes to the individually numbered nodes in the user's V13 GLB. */
export function twinSensorModelNodeNames(code: string): string[] {
  const match = /^(SHT30|SHT|MQ7|CO|MQ4|ME2O2|O2|MQ2|FLAME|LEVEL)-(?:L)?(0[1-5])$/.exec(code);
  if (!match) return [];
  const [, family, index] = match;
  // The fifth level station remains visible in the model but its physical
  // sensor has been removed; never bind a live alarm to that visual station.
  if (family === 'LEVEL') return Number(index) <= 4 ? [`LEVEL-L${index}-探头`] : [];
  // Four physical SHTs occupy model slots 01, 02, 04 and 05. Slot 03 is empty.
  if (family === 'SHT' || family === 'SHT30') {
    const modelIndex = ({ '01': '01', '02': '02', '03': '04', '04': '05' } as Record<string, string>)[index];
    return modelIndex ? [`SHT30-${modelIndex}-板`] : [];
  }
  // Three physical oxygen sensors use the five V13 display stations 01/03/05.
  if (family === 'O2') {
    const modelIndex = ({ '01': '01', '02': '03', '03': '05' } as Record<string, string>)[index];
    return modelIndex ? [`ME2O2-${modelIndex}-板`] : [];
  }
  const modelFamily = ({ SHT: 'SHT30', CO: 'MQ7', O2: 'ME2O2' } as Record<string, string>)[family] ?? family;
  return [`${modelFamily}-${index}-板`];
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
