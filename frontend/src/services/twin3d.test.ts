import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { activeTwinAlerts, alertIndicatesLeak, isUnoccupiedTwinModelNodeName, leakCapableAsset, leakPipeLabel, leakPipeNodeNames, modelNodeNames, nextTwinCameraDistance, primaryTwinAlert, resolveTwinVisualState, summarizeTwinModelBindings, summarizeTwinModelDelivery, twinSensorModelNodeNames } from './twin3d';
import type { Alert, Asset } from '../types';

const asset = { id: 1, code: 'ENV-01', mesh: 'MESH_ENV_01', status: 'normal' } as Asset;

describe('3D twin binding rules', () => {
  it('preserves an asset alarm before its event record arrives', () => {
    expect(resolveTwinVisualState({ ...asset, status: 'alarm' }, [])).toBe('alarm');
    expect(resolveTwinVisualState(asset, [{ assetCode: asset.code, status: 'resolved' } as Alert])).toBe('normal');
  });
  it('uses alert severity for the model colour even when the asset is otherwise normal', () => {
    expect(resolveTwinVisualState(asset, [{ assetCode: 'ENV-01', status: 'open', severity: 'warning' } as Alert])).toBe('warning');
    expect(resolveTwinVisualState(asset, [{ assetCode: 'ENV-01', status: 'open', severity: 'critical' } as Alert])).toBe('alarm');
    expect(resolveTwinVisualState(asset, [{ assetCode: 'ENV-01', status: 'open', severity: 'info' } as Alert])).toBe('normal');
  });

  it('keeps resolved alerts out of the current scene state and prioritizes critical incidents', () => {
    const alerts = [
      { id: 1, assetCode: 'ENV-01', code: 'ALM-OLD', severity: 'critical', status: 'resolved', openedAt: '2026-08-01T00:00:00Z' },
      { id: 2, assetCode: 'ENV-01', code: 'ALM-WARN', severity: 'warning', status: 'open', openedAt: '2026-08-03T00:00:00Z' },
      { id: 3, assetCode: 'ENV-01', code: 'ALM-CRITICAL', severity: 'critical', status: 'acknowledged', openedAt: '2026-08-04T00:00:00Z' },
    ] as Alert[];
    expect(activeTwinAlerts('ENV-01', alerts).map((alert) => alert.code)).toEqual(['ALM-CRITICAL', 'ALM-WARN']);
    expect(primaryTwinAlert('ENV-01', alerts)?.code).toBe('ALM-CRITICAL');
  });

  it('offers stable Blender object-name fallbacks for every asset', () => {
    expect(modelNodeNames(asset)).toEqual(['MESH_ENV_01', 'ENV-01', 'ASSET_ENV_01']);
  });

  it('leaves SHT model slot 03 empty and shifts physical 03/04 to model slots 04/05', () => {
    expect(['SHT-01', 'SHT-02', 'SHT-03', 'SHT-04'].map(twinSensorModelNodeNames)).toEqual([
      ['SHT30-01-板'], ['SHT30-02-板'], ['SHT30-04-板'], ['SHT30-05-板'],
    ]);
    expect(twinSensorModelNodeNames('SHT30-03')).toEqual(['SHT30-04-板']);
    expect(twinSensorModelNodeNames('SHT-05')).toEqual([]);
    expect(modelNodeNames({ ...asset, code: 'SHT-03', mesh: 'SHT30-03-板' })[0]).toBe('SHT30-04-板');
    expect(modelNodeNames({ ...asset, code: 'SHT-03', mesh: 'SHT30-03-板' })).not.toContain('SHT30-03-板');
    expect(modelNodeNames({ ...asset, code: 'SHT-04', mesh: 'SHT30-04-板' })[0]).toBe('SHT30-05-板');
    expect(modelNodeNames({ ...asset, code: 'SHT-04', mesh: 'SHT30-04-板' })).not.toContain('SHT30-04-板');
    expect(modelNodeNames({ ...asset, code: 'SHT-05', mesh: 'SHT30-05-板' })).toEqual([]);
    expect(isUnoccupiedTwinModelNodeName('SHT30-03-板')).toBe(true);
    expect(isUnoccupiedTwinModelNodeName('SHT30-04-板')).toBe(false);
  });

  it('places three physical oxygen sensors at V13 stations 01, 03 and 05', () => {
    expect(['O2-01', 'O2-02', 'O2-03'].map(twinSensorModelNodeNames)).toEqual([
      ['ME2O2-01-板'], ['ME2O2-03-板'], ['ME2O2-05-板'],
    ]);
    expect(modelNodeNames({ ...asset, code: 'O2-02', mesh: 'ME2O2-02-板' })[0]).toBe('ME2O2-03-板');
    expect(modelNodeNames({ ...asset, code: 'O2-02', mesh: 'ME2O2-02-板' })).not.toContain('ME2O2-02-板');
    expect(modelNodeNames({ ...asset, code: 'O2-03', mesh: 'ME2O2-03-板' })[0]).toBe('ME2O2-05-板');
    expect(modelNodeNames({ ...asset, code: 'O2-03', mesh: 'ME2O2-03-板' })).not.toContain('ME2O2-03-板');
    expect(isUnoccupiedTwinModelNodeName('ME2O2-02-板')).toBe(true);
    expect(isUnoccupiedTwinModelNodeName('ME2O2-04-支架')).toBe(true);
    expect(isUnoccupiedTwinModelNodeName('ME2O2-03-板')).toBe(false);
    expect(modelNodeNames({ ...asset, code: 'O2-04', mesh: 'ME2O2-04-板' })).toEqual([]);
  });

  it('binds every other bench code to its own V13 model node without locating removed level 05', () => {
    expect(twinSensorModelNodeNames('SHT-02')).toEqual(['SHT30-02-板']);
    expect(twinSensorModelNodeNames('CO-05')).toEqual(['MQ7-05-板']);
    expect(twinSensorModelNodeNames('MQ4-03')).toEqual(['MQ4-03-板']);
    expect(twinSensorModelNodeNames('O2-03')).toEqual(['ME2O2-05-板']);
    expect(twinSensorModelNodeNames('MQ2-04')).toEqual(['MQ2-04-板']);
    expect(twinSensorModelNodeNames('FLAME-05')).toEqual(['FLAME-05-板']);
    expect(twinSensorModelNodeNames('LEVEL-04')).toEqual(['LEVEL-L04-探头']);
    expect(twinSensorModelNodeNames('LEVEL-L05')).toEqual([]);
    expect(modelNodeNames({ ...asset, code: 'CO-05', mesh: '' })).toContain('MQ7-05-板');
  });

  it('finds all 31 connected bench sensors in the deployed GLB', () => {
    const glb = readFileSync(new URL('../../public/models/utility-tunnel.glb', import.meta.url));
    const jsonSize = glb.readUInt32LE(12);
    const model = JSON.parse(glb.subarray(20, 20 + jsonSize).toString('utf8')) as { nodes: Array<{ name?: string }> };
    const names = new Set(model.nodes.map((node) => node.name));
    const groups = { SHT: 4, CO: 5, MQ4: 5, O2: 3, MQ2: 5, FLAME: 5, LEVEL: 4 };
    Object.entries(groups).forEach(([family, count]) => {
      for (let i = 1; i <= count; i += 1) {
        const code = `${family}-${String(i).padStart(2, '0')}`;
        expect(twinSensorModelNodeNames(code).some((name) => names.has(name)), code).toBe(true);
      }
    });
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

  it('keeps the model handoff check separate from actual model-file loading', () => {
    const secondAsset = { ...asset, id: 2, code: 'FAN-01', mesh: '' };
    expect(summarizeTwinModelDelivery([asset, secondAsset])).toEqual({
      activeAssetCount: 2,
      mappedAssetCount: 1,
      missingMeshCodes: ['FAN-01'],
      invalidMeshCodes: [],
      isReady: false,
    });
    expect(summarizeTwinModelDelivery([{ ...asset, mesh: 'mesh_env_01' }])).toMatchObject({
      mappedAssetCount: 0,
      invalidMeshCodes: ['ENV-01'],
      isReady: false,
    });
  });

  it('zooms in and out without crossing the camera safety bounds', () => {
    expect(nextTwinCameraDistance(10, .62, 2, 20)).toBe(6.2);
    expect(nextTwinCameraDistance(10, 1.55, 2, 20)).toBe(15.5);
    expect(nextTwinCameraDistance(2, .62, 2, 20)).toBe(2);
    expect(nextTwinCameraDistance(20, 1.55, 2, 20)).toBe(20);
  });

  it('maps gas and water incidents to deterministic pipe nodes', () => {
    expect(alertIndicatesLeak({ category: '气体安全', title: '甲烷泄漏', detail: '燃气浓度上升' } as Alert)).toBe(true);
    expect(alertIndicatesLeak({ category: '设备反馈', title: '风机离线', detail: '无反馈' } as Alert)).toBe(false);
    const level = { ...asset, code: 'LEVEL-L03', name: '液位3 · 泵入口', type: '管道液位测点', mesh: 'MESH_V12-FSIR02_L03_PROBE', capabilities: [] };
    expect(leakCapableAsset(level)).toBe(true);
    expect(leakPipeNodeNames(level)).toContain('MESH_V12-FSIR02_L03_PIPE');
    expect(leakPipeLabel(level)).toBe('管段 · 泵入口');
  });
});
