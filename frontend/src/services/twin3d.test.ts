import { describe, expect, it } from 'vitest';
import { modelNodeNames, resolveTwinVisualState } from './twin3d';
import type { Alert, Asset } from '../types';

const asset = { id: 1, code: 'ENV-01', mesh: 'MESH_ENV_01', status: 'normal' } as Asset;

describe('3D twin binding rules', () => {
  it('treats an active alert as an alarm even when the asset is otherwise normal', () => {
    expect(resolveTwinVisualState(asset, [{ assetCode: 'ENV-01', status: 'open' } as Alert])).toBe('alarm');
  });

  it('offers stable Blender object-name fallbacks for every asset', () => {
    expect(modelNodeNames(asset)).toEqual(['MESH_ENV_01', 'ENV-01', 'ASSET_ENV_01']);
  });
});
