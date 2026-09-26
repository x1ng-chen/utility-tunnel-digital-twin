import { describe, expect, it } from 'vitest';
import type { Alert, Asset, Telemetry } from '../types';
import { levelStationCards, levelStations } from './levelStations';
import { newTwinAlert } from './newTwinAlert';

describe('five independent pipe level stations', () => {
  it('keeps each alert on its own station and never borrows another station reading', () => {
    const assets = levelStations.map((station, index) => ({ id: index + 1, code: station.code, integrationStatus: 'firmware_connected', status: 'normal' } as Asset));
    const now = Date.parse('2026-09-26T00:10:00Z');
    for (const [index, station] of levelStations.entries()) {
      const alert = { id: index + 1, code: `ALM-${index + 1}`, assetCode: station.code, severity: 'warning', status: 'open', openedAt: new Date(now).toISOString() } as Alert;
      const reading = { id: index + 1, assetCode: station.code, metricKey: 'level.detected', value: 1, quality: 'good', recordedAt: new Date(now).toISOString() } as Telemetry;
      const cards = levelStationCards(assets, [alert], [reading], [], 'api', false, now);
      expect(cards.map((card) => Boolean(card.alert))).toEqual(levelStations.map((_, position) => position === index));
      expect(cards.map((card) => Boolean(card.reading))).toEqual(levelStations.map((_, position) => position === index));
      expect(newTwinAlert([alert], [], assets.map((asset) => asset.code))?.assetCode).toBe(station.code);
    }
  });

  it('does not claim a verified leak when the service is offline or the station is not commissioned', () => {
    const asset = { code: 'LEVEL-L01', status: 'unknown', integrationStatus: 'pending_verification' } as Asset;
    expect(levelStationCards([asset], [], [], [], 'api', false)[0].summary).toBe('待接入与现场核验');
    expect(levelStationCards([asset], [], [], [], 'api', true)[0].summary).toContain('无法确认');
  });
});
