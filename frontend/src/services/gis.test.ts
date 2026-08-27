import { describe, expect, it } from 'vitest';
import type { Asset } from '../types';
import { escapeMapText, hasValidLocation, integrationLabels, locationSourceLabels } from './gis';

const locatedAsset = { latitude: 31.23, longitude: 121.47 } as Asset;

describe('GIS data safeguards', () => {
  it('accepts only finite WGS84 coordinates', () => {
    expect(hasValidLocation(locatedAsset)).toBe(true);
    expect(hasValidLocation({ ...locatedAsset, latitude: 91 })).toBe(false);
    expect(hasValidLocation({ ...locatedAsset, longitude: Number.NaN })).toBe(false);
    expect(hasValidLocation({ ...locatedAsset, latitude: null })).toBe(false);
  });

  it('keeps location provenance and hardware state explicit', () => {
    expect(locationSourceLabels.demo_anchor).toBe('演示锚点');
    expect(integrationLabels.calibration_required).toBe('待标定');
  });

  it('escapes data before inserting it into marker HTML', () => {
    expect(escapeMapText('<img src=x onerror=alert(1)>')).toBe('&lt;img src=x onerror=alert(1)&gt;');
  });
});
