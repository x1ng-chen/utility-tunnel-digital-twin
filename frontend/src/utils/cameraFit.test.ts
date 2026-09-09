import { describe, expect, it } from 'vitest';
import { cameraFitDistance } from './cameraFit';

describe('全景相机适配', () => {
  it('横竖两方向都能容纳包围球，并保留边距', () => {
    for (const aspect of [.3, .6, 1, 1.5, 3]) {
      const distance = cameraFitDistance(8, 45, aspect);
      const angularRadius = Math.asin(8 / distance);
      expect(angularRadius).toBeLessThan(45 * Math.PI / 360);
      expect(angularRadius).toBeLessThan(Math.atan(Math.tan(45 * Math.PI / 360) * aspect));
    }
  });
  it('窄屏拉远距离，模型尺寸变化按比例适配', () => {
    expect(cameraFitDistance(2, 45, .5)).toBeGreaterThan(cameraFitDistance(2, 45, 2));
    expect(cameraFitDistance(4, 45, 1)).toBeCloseTo(cameraFitDistance(2, 45, 1) * 2);
  });
  it('拒绝不可渲染的参数', () => {
    for (const values of [[0, 45, 1], [1, 0, 1], [1, 180, 1], [1, 45, 0], [NaN, 45, 1]]) {
      expect(() => cameraFitDistance(values[0], values[1], values[2])).toThrow();
    }
  });
});
