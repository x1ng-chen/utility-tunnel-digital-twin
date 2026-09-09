/** Fit a bounding sphere to both dimensions of a perspective viewport. */
export function cameraFitDistance(radius: number, verticalFovDegrees: number, aspect: number): number {
  if (![radius, verticalFovDegrees, aspect].every(Number.isFinite)
    || radius <= 0 || aspect <= 0 || verticalFovDegrees <= 0 || verticalFovDegrees >= 180) {
    throw new Error('相机适配参数必须为有效的正数与视角。');
  }
  const verticalHalf = verticalFovDegrees * Math.PI / 360;
  const horizontalHalf = Math.atan(Math.tan(verticalHalf) * aspect);
  return radius / Math.sin(Math.min(verticalHalf, horizontalHalf)) * 1.12;
}
