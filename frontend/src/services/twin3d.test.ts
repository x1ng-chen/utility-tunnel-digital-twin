import { describe, expect, it } from 'vitest';
import { modelNodeNames, resolveTwinVisualState, summarizeTwinModelBindings } from './twin3d';
import type { Alert, Asset } from '../types';

const asset = { id: 1, code: 'ENV-01', mesh: 'MESH_ENV_01', status: 'normal' } as Asset;

describe('3D twin binding rules', () => {
  it('treats an active alert as an alarm even when the asset is otherwise normal', () => {
    expect(resolveTwinVisualState(asset, [{ assetCode: 'ENV-01', status: 'open' } as Alert])).toBe('alarm');
  });

  it('offers stable Blender object-name fallbacks for every asset', () => {
    expect(modelNodeNames(asset)).toEqual(['MESH_ENV_01', 'ENV-01', 'ASSET_ENV_01']);
  });

  it('does not count interactive fallback markers as Blender model bindings', () => {
    const secondAsset = { ...asset, id: 2, code: 'FAN-01', mesh: 'MESH_FAN_01' };
    expect(summarizeTwinModelBindings([asset, secondAsset], ['ENV-01'])).toEqual({
      expectedCount: 2,
      boundCodes: ['ENV-01'],
      missingCodes: ['FAN-01'],
      isComplete: false,
    });
  });
});
