import assert from 'node:assert/strict';
import test from 'node:test';
import { setTimeout as pause } from 'node:timers/promises';
import { createTelemetryRoutes } from '../src/telemetry-routes.js';
import { createDjangoForwarder } from '../src/django.js';

test('legacy single-topic default and explicit four-node subscriptions', () => {
  assert.deepEqual(createTelemetryRoutes().topics, ['ut/v1/CTRL-01/telemetry']);
  const routes = createTelemetryRoutes('CTRL-01, CTRL-02,CTRL-03,CTRL-04');
  assert.equal(routes.topics.length, 4);
  assert.equal(routes.deviceForTopic('ut/v1/CTRL-04/telemetry'), 'CTRL-04');
  for (const topic of ['ut/v1/CTRL-04/cmd', 'ut/v1/UNKNOWN/telemetry', 'ut/v1/CTRL-04/telemetry/extra']) {
    assert.equal(routes.deviceForTopic(topic), null);
  }
});

test('reject ambiguous, wildcard, duplicate and excessive controller lists', () => {
  for (const ids of ['', 'CTRL-01,', 'CTRL-01,CTRL-01', '#', 'CTRL/04', 'A,B,C,D,E']) {
    assert.throws(() => createTelemetryRoutes(ids));
  }
});

test('one persistent forwarder preserves source identity in both controller batches', async () => {
  const sent = [];
  const forwarder = createDjangoForwarder({ baseUrl: 'https://test.invalid/api', apiKey: 'fixture-only',
    fetchImpl: async (_url, options) => {
      sent.push(JSON.parse(options.body));
      return new Response(JSON.stringify({ created: 1, duplicates: 0, rules: {} }), { status: 201 });
    }, log: { info() {}, warn() {}, error() {} },
  });
  const frame = { schema: 'ut.telemetry.v1', readings: [
    { assetCode: 'ENV-01', metric: 'temperature', value: 20, unit: 'degC', quality: 'good' },
  ] };
  try {
    const at = new Date('2026-10-25T00:00:00Z');
    forwarder.forward(frame, at, 'CTRL-01');
    forwarder.forward(frame, at, 'CTRL-04');
    for (let n = 0; n < 100 && sent.length < 2; n++) await pause(10);
    assert.equal(sent.length, 2);
    assert.match(sent[0].readings[0].eventId, /^gw:CTRL-01:/);
    assert.match(sent[1].readings[0].eventId, /^gw:CTRL-04:/);
    assert.notEqual(sent[0].readings[0].eventId, sent[1].readings[0].eventId);
    assert.throws(() => forwarder.forward(frame, at, 'bad/#'));
  } finally { forwarder.close(); }
});
