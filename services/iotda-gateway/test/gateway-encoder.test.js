import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { parseTelemetry } from '../src/schemas.js';
import { toDjangoBatch } from '../src/django.js';

test('actual gateway C++ encoder output passes the platform contract for all 31 modules', {
  skip: !process.env.UT_GATEWAY_FIXTURES && 'Run the firmware executable tests and set UT_GATEWAY_FIXTURES to their gateway-fixtures.json.',
}, () => {
  const fixtures = JSON.parse(readFileSync(process.env.UT_GATEWAY_FIXTURES, 'utf8'));
  const catalog = JSON.parse(readFileSync(new URL('../src/four-controller-catalog.json', import.meta.url), 'utf8'));
  const covered = new Set(); const events = new Set(); let metrics = 0;
  assert.equal(fixtures.length, 4);
  for (const [i, frame] of fixtures.entries()) {
    const device = 'CTRL-0' + (i + 1);
    const parsed = parseTelemetry(frame, device);
    assert.equal(parsed.readings.length, [14, 16, 8, 16][i]);
    const batch = toDjangoBatch(parsed, { deviceId: device });
    assert.equal(batch.skipped.length, 0);
    for (const row of batch.readings) {
      assert.ok(!events.has(row.eventId));events.add(row.eventId);
      if (catalog.bindings.some(b => b.assetCode === row.assetCode)) covered.add(row.assetCode);
      assert.ok(Number.isFinite(Date.parse(row.recordedAt)));
      if (row.metricKey === 'temperature') assert.equal(row.value, -4.25);
      if (row.metricKey === 'motor.current') assert.equal(row.value, -0.25);
    }
    metrics += batch.readings.length;
  }
  assert.equal(covered.size, 31);assert.equal(metrics, 54);assert.equal(events.size, 54);
});
