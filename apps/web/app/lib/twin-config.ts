import type { Asset } from './operations';

export type TunnelZone = {
  code: string;
  name: string;
  left: number;
  top: number;
  width: number;
  height: number;
};

export type TwinPosition = {
  left: number;
  top: number;
};

// This configuration is intentionally separate from page components. In API mode
// the persisted asset x/y/z fields override these safe visual fallbacks.
export const tunnelZones: TunnelZone[] = [
  { code: 'UT-ZA', name: '入口与控制区', left: 7, top: 59, width: 25, height: 25 },
  { code: 'UT-ZB', name: '环境与排风区', left: 35, top: 33, width: 30, height: 30 },
  { code: 'UT-ZC', name: '燃气管线区', left: 68, top: 57, width: 25, height: 25 },
];

const fallbackAssetPositions: Record<string, TwinPosition> = {
  'CTRL-01': { left: 22, top: 68 },
  'FAN-01': { left: 57, top: 46 },
  'SEEP-W01': { left: 67, top: 73 },
  'GAS-01': { left: 82, top: 38 },
};

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function getTwinPosition(asset: Asset): TwinPosition {
  if (asset.position && Number.isFinite(asset.position.x) && Number.isFinite(asset.position.y)) {
    // Seed coordinates use a 0–28 m tunnel coordinate system. Keep labels inside
    // the visible plan regardless of the future model's exact dimensions.
    return {
      left: clamp(10 + asset.position.x * 3.05, 8, 88),
      top: clamp(79 - asset.position.y * 25, 22, 82),
    };
  }
  return fallbackAssetPositions[asset.code] ?? { left: 50, top: 50 };
}

export function getZone(asset: Asset): TunnelZone | undefined {
  return tunnelZones.find((zone) => zone.code === asset.zone);
}
