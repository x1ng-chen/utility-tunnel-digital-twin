import assert from 'node:assert/strict';
import test from 'node:test';

process.env.DATABASE_URL ??= 'postgresql://test:test@127.0.0.1:5432/test';
process.env.JWT_SECRET ??= 'test-secret-with-at-least-thirty-two-characters';
process.env.WEB_ORIGIN ??= 'http://localhost:5173';

const { parseDeviceTelemetry, parseTelemetry } = await import('./telemetry.js');

test('parses the documented MQTT telemetry envelope', () => {
  const telemetry = parseTelemetry('ut/v1/ctrl-01/telemetry', JSON.stringify({
    schema: 'ut.telemetry.v1',
    ts: '2026-08-27T09:00:00.000+09:00',
    readings: [{ assetCode: 'ENV-01', metric: 'temperature', value: 25.4, unit: 'degC' }],
  }));
  assert.equal(telemetry.deviceId, 'CTRL-01');
  assert.equal(telemetry.readings[0]?.quality, 'good');
});

test('rejects malformed telemetry topics and payloads', () => {
  assert.throws(() => parseTelemetry('ut/v1/ctrl-01/state', '{}'), /Unexpected telemetry topic/);
  assert.throws(() => parseTelemetry('ut/v1/ctrl-01/telemetry', '{'), /not valid JSON/);
});

test('parses a JDY-31 payload after the gateway removes its newline delimiter', () => {
  const telemetry = parseDeviceTelemetry('ctrl-01', {
    schema: 'ut.telemetry.v1',
    readings: [{ assetCode: 'CTRL-01', metric: 'vibration.alarm', value: 0, unit: 'bool' }],
  });
  assert.equal(telemetry.deviceId, 'CTRL-01');
  assert.equal(telemetry.recordedAt.length > 0, true);
});
