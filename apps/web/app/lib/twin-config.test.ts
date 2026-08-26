import assert from 'node:assert/strict';
import test from 'node:test';
import { getTwinPosition, tunnelZones } from './twin-config.ts';

test('twin configuration contains the three planned tunnel zones', () => {
  assert.deepEqual(tunnelZones.map((zone) => zone.code), ['UT-ZA', 'UT-ZB', 'UT-ZC']);
});

test('persisted asset coordinates override the visual fallback and stay on the map', () => {
  const position = getTwinPosition({
    code: 'CUSTOM-01', name: '自定义资产', zone: 'UT-ZA', type: 'sensor', status: 'normal', mesh: 'MESH_CUSTOM', lastSeenAt: '2026-08-26T00:00:00.000Z',
    position: { x: 1000, y: -1000, z: 0 },
  });
  assert.equal(position.left, 88);
  assert.equal(position.top, 82);
});
