import type { Asset, IntegrationStatus, LocationSource } from '../types';

export const integrationLabels: Record<IntegrationStatus, string> = {
  verified: '已验证',
  firmware_connected: '固件已接入',
  calibration_required: '待标定',
  pending_verification: '待验证',
  optional: '可选模块',
  non_operational: '非运行资产',
};

export const locationSourceLabels: Record<LocationSource, string> = {
  unassigned: '未配置',
  demo_anchor: '演示锚点',
  configured: '人工配置',
  surveyed: '现场测绘',
  gps: 'GPS 定位',
};

export function hasValidLocation(asset: Asset): asset is Asset & { latitude: number; longitude: number } {
  return typeof asset.latitude === 'number'
    && Number.isFinite(asset.latitude)
    && asset.latitude >= -90
    && asset.latitude <= 90
    && typeof asset.longitude === 'number'
    && Number.isFinite(asset.longitude)
    && asset.longitude >= -180
    && asset.longitude <= 180;
}

export function escapeMapText(value: string): string {
  return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ?? character);
}
