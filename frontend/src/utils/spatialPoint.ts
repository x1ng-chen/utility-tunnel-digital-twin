import type { SpatialSource } from '../types';

export interface SpatialPointDraft {
  code: string;
  name: string;
  layerType: 'installation_point' | 'manhole';
  source: SpatialSource;
  sourceReference: string;
  latitude: number | null;
  longitude: number | null;
  accuracyM: number | null | '';
}

export function emptySpatialPoint(): SpatialPointDraft {
  return { code: '', name: '', layerType: 'installation_point', source: 'configured', sourceReference: '', latitude: null, longitude: null, accuracyM: null };
}

export function spatialPointPayload(item: SpatialPointDraft) {
  if (!item.name.trim() || !/^[A-Z0-9][A-Z0-9_-]{1,39}$/.test(item.code.trim().toUpperCase())) {
    throw new Error('请填写对象名称和有效编码（2–40 位字母、数字、下划线或短横线）。');
  }
  if (typeof item.latitude !== 'number' || typeof item.longitude !== 'number' || !Number.isFinite(item.latitude) || !Number.isFinite(item.longitude)) {
    throw new Error('请填写有效的位置坐标。');
  }
  if (Math.abs(item.latitude) > 90 || Math.abs(item.longitude) > 180) {
    throw new Error('位置坐标超出范围：纬度应在 -90 到 90 之间，经度应在 -180 到 180 之间。');
  }
  if (!item.sourceReference.trim()) throw new Error('请填写来源依据，例如测绘成果编号、图纸版本或现场登记记录。');
  const accuracy = item.accuracyM === '' ? null : item.accuracyM;
  if (accuracy !== null && (!Number.isFinite(accuracy) || accuracy < .001 || accuracy > 99999.999)) {
    throw new Error('已知定位精度应为 0.001–99999.999 米；不确定时请留空。');
  }
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [item.longitude, item.latitude] },
      properties: {
        code: item.code.trim().toUpperCase(), name: item.name.trim(), layerType: item.layerType,
        source: item.source, sourceReference: item.sourceReference.trim(),
        accuracyM: accuracy === null ? null : accuracy.toFixed(3), status: 'draft',
      },
    }],
  };
}
