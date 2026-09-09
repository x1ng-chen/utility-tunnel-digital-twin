import { describe, expect, it } from 'vitest';
import { emptySpatialPoint, spatialPointPayload } from './spatialPoint';

const point = () => ({ ...emptySpatialPoint(), code: ' point-a1 ', name: '现场点位', sourceReference: '登记记录 01', latitude: 0, longitude: 0 });

describe('现场点位登记', () => {
  it('不预填坐标、来源依据或定位精度', () => {
    expect(emptySpatialPoint()).toMatchObject({ latitude: null, longitude: null, sourceReference: '', accuracyM: null });
    expect(() => spatialPointPayload(emptySpatialPoint())).toThrow();
  });
  it('保留实际来源、零坐标及未知精度', () => {
    const payload = spatialPointPayload({ ...point(), source: 'surveyed', sourceReference: ' 测绘成果 01 ' });
    expect(payload.features[0]).toMatchObject({ geometry: { coordinates: [0, 0] }, properties: { code: 'POINT-A1', source: 'surveyed', sourceReference: '测绘成果 01', accuracyM: null, status: 'draft' } });
  });
  it('清空精度等同未登记，而不是零米', () => {
    expect(spatialPointPayload({ ...point(), accuracyM: '' }).features[0].properties.accuracyM).toBeNull();
    expect(spatialPointPayload({ ...point(), accuracyM: .25 }).features[0].properties.accuracyM).toBe('0.250');
  });
  it('拒绝缺失依据、无效坐标和无效精度', () => {
    for (const patch of [{ sourceReference: ' ' }, { latitude: null }, { longitude: NaN }, { latitude: 91 }, { longitude: -181 }, { accuracyM: 0 }, { accuracyM: Infinity }]) {
      expect(() => spatialPointPayload({ ...point(), ...patch })).toThrow();
    }
  });
});
