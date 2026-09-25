import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createDjangoForwarder, DJANGO_UNIT_MAP, toDjangoBatch } from '../src/django.js';
import { Outbox } from '../src/outbox.js';

const RECEIVED_AT = new Date('2026-08-29T08:00:00Z');
const EVENT_ID_PATTERN = /^[A-Za-z0-9._:-]{1,80}$/;

const SAMPLE = {
  schema: 'ut.telemetry.v1',
  readings: [
    { assetCode: 'ENV-01', metric: 'temperature', value: 29.5, unit: 'degC', quality: 'good' },
    { assetCode: 'ENV-01', metric: 'humidity', value: 63, unit: '%RH', quality: 'good' },
    { assetCode: 'SEEP-W01', metric: 'water.raw', value: 640, unit: 'adc', quality: 'good' },
    { assetCode: 'LEVEL-L01', metric: 'level.detected', value: 1, unit: 'bool', quality: 'good' },
    { assetCode: 'CTRL-01', metric: 'vibration.alarm', value: 0, unit: 'bool', quality: 'good' },
  ],
};

const SAMPLE_READING_COUNT = SAMPLE.readings.length;

function singleReading(value) {
  return { schema: 'ut.telemetry.v1', readings: [{ assetCode: 'ENV-01', metric: 'temperature', value, unit: 'degC', quality: 'good' }] };
}

function waitFor(predicate, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const check = () => {
      if (predicate()) {
        resolve();
        return;
      }
      if (Date.now() - started > timeoutMs) {
        reject(new Error('waitFor timed out'));
        return;
      }
      setTimeout(check, 10);
    };
    check();
  });
}

function startServer(handler) {
  return new Promise((resolve) => {
    const seen = [];
    const server = createServer((request, response) => {
      let body = '';
      request.on('data', (chunk) => { body += chunk; });
      request.on('end', () => {
        const record = {
          url: request.url,
          method: request.method,
          headers: request.headers,
          body: body ? JSON.parse(body) : null,
        };
        seen.push(record);
        handler(record, response);
      });
    });
    server.listen(0, '127.0.0.1', () => {
      resolve({ server, seen, baseUrl: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function loginResponse(response, token) {
  response.writeHead(200, { 'content-type': 'application/json' });
  response.end(JSON.stringify({ accessToken: token, tokenType: 'Bearer', user: { role: 'operator' } }));
}

test('maps device units and display names onto the Django contract', () => {
  const batch = toDjangoBatch(SAMPLE, { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  assert.equal(batch.readings.length, 5);
  assert.equal(batch.skipped.length, 0);
  const [temperature, humidity, water, level, vibration] = batch.readings;
  assert.equal(temperature.unit, DJANGO_UNIT_MAP.degC);
  assert.equal(temperature.metric, '环境温度');
  assert.equal(humidity.unit, '%RH');
  assert.equal(water.metricKey, 'water.raw');
  assert.equal(water.unit, 'adc');
  assert.equal(level.metricKey, 'level.detected');
  assert.equal(level.metric, '液位检测');
  assert.equal(level.unit, 'bool');
  assert.equal(vibration.metricKey, 'vibration.alarm');
  assert.equal(vibration.metric, '振动锁存');
  assert.equal(temperature.recordedAt, RECEIVED_AT.toISOString());

  const eventIds = batch.readings.map((reading) => reading.eventId);
  assert.equal(new Set(eventIds).size, eventIds.length);
  for (const eventId of eventIds) {
    assert.match(eventId, EVENT_ID_PATTERN);
    assert.ok(eventId.startsWith('gw:CTRL-01:'));
  }
});

test('labels automatic ventilation state for platform telemetry', () => {
  const telemetry = {
    schema: 'ut.telemetry.v1',
    readings: [
      { assetCode: 'FAN-01', metric: 'control.autoVentilation', value: 1, unit: 'bool', quality: 'good' },
      { assetCode: 'FAN-01', metric: 'control.cooldown', value: 0, unit: 'bool', quality: 'good' },
    ],
  };

  const batch = toDjangoBatch(telemetry, { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });

  assert.deepEqual(batch.readings.map(({ metricKey, metric }) => ({ metricKey, metric })), [
    { metricKey: 'control.autoventilation', metric: '气体报警自动排风' },
    { metricKey: 'control.cooldown', metric: '报警解除延时排风' },
  ]);
});

test('uses the device timestamp when the message carries one', () => {
  const telemetry = { ...SAMPLE, ts: '2026-08-29T07:59:58Z' };
  const batch = toDjangoBatch(telemetry, { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  assert.equal(batch.readings[0].recordedAt, '2026-08-29T07:59:58.000Z');
});

test('normalizes sloppy device readings and skips contract-breaking ones', () => {
  const telemetry = {
    schema: 'ut.telemetry.v1',
    readings: [
      { assetCode: 'env-01', metric: 'temperature', value: 1, unit: 'degC' },
      { assetCode: 'ENV-01', metric: 'Temperature!', value: 1, unit: 'degC' },
      { assetCode: 'ENV-01', metric: 'temperature', value: 'oops', unit: 'degC' },
      { assetCode: 'ENV-01', metric: 'temperature', value: 22.5, unit: 'degC' },
    ],
  };
  const batch = toDjangoBatch(telemetry, { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  assert.equal(batch.readings.length, 2);
  assert.equal(batch.readings[0].assetCode, 'ENV-01');
  assert.equal(batch.readings[0].value, 1);
  assert.equal(batch.readings[1].value, 22.5);
  assert.equal(batch.skipped.length, 2);
});

test('keeps eventIds inside the 80 character contract for long device ids', () => {
  const batch = toDjangoBatch(singleReading(1), { deviceId: 'ctrl-'.repeat(16), receivedAt: RECEIVED_AT });
  assert.ok(batch.readings[0].eventId.length <= 80);
  assert.match(batch.readings[0].eventId, EVENT_ID_PATTERN);
});

test('uses stable but collision-resistant eventIds for frames in the same millisecond', () => {
  const first = toDjangoBatch(singleReading(1), { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  const redelivery = toDjangoBatch(singleReading(1), { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  const differentPayload = toDjangoBatch(singleReading(2), { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT });
  assert.equal(first.readings[0].eventId, redelivery.readings[0].eventId);
  assert.notEqual(first.readings[0].eventId, differentPayload.readings[0].eventId);
});

test('delivers telemetry to the Django ingest API with a service account', async () => {
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(SAMPLE, RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === SAMPLE_READING_COUNT);
    const telemetryCalls = server.seen.filter((record) => record.url === '/api/telemetry/');
    assert.equal(telemetryCalls.length, 1);
    assert.equal(telemetryCalls[0].headers.authorization, 'Bearer token-1');
    assert.equal(telemetryCalls[0].body.readings.length, SAMPLE_READING_COUNT);
    assert.equal(forwarder.counters.queued, 0);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('delivers telemetry with the scoped ingest API key without logging in', async () => {
  const apiKey = 'test-ingest-key-that-is-longer-than-32-characters';
  const server = await startServer((record, response) => {
    assert.notEqual(record.url, '/api/auth/login/');
    assert.equal(record.headers['x-ingest-key'], apiKey);
    assert.equal(record.headers.authorization, undefined);
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({ baseUrl: server.baseUrl, apiKey });
    forwarder.forward(singleReading(22), RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === 1);
    assert.equal(forwarder.counters.logins, 0);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('re-authenticates and replays the batch when the ingest token expires', async () => {
  let loginCount = 0;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginCount += 1;
      loginResponse(response, `token-${loginCount}`);
      return;
    }
    if (record.headers.authorization !== 'Bearer token-2') {
      response.writeHead(401, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'unauthorized' }));
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(SAMPLE, RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === SAMPLE_READING_COUNT);
    assert.equal(loginCount, 2);
    const telemetryCalls = server.seen.filter((record) => record.url === '/api/telemetry/');
    assert.equal(telemetryCalls.length, 2);
    assert.equal(telemetryCalls[0].headers.authorization, 'Bearer token-1');
    assert.equal(telemetryCalls[1].headers.authorization, 'Bearer token-2');
    assert.equal(forwarder.counters.queued, 0);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('retries a transient server error until it succeeds', async () => {
  let failures = 0;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    if (failures < 2) {
      failures += 1;
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'server_error' }));
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(SAMPLE, RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === SAMPLE_READING_COUNT);
    assert.ok(forwarder.counters.retries >= 1);
    assert.equal(failures, 2);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('replays the same eventIds after a concurrency conflict', async () => {
  let conflicts = 0;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    if (conflicts < 1) {
      conflicts += 1;
      response.writeHead(409, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'conflict' }));
      return;
    }
    response.writeHead(200, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: 0, duplicates: record.body.readings.length, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(SAMPLE, RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === SAMPLE_READING_COUNT);
    assert.equal(forwarder.counters.duplicates, SAMPLE_READING_COUNT);
    const telemetryCalls = server.seen.filter((record) => record.url === '/api/telemetry/');
    assert.equal(telemetryCalls.length, 2);
    assert.deepEqual(telemetryCalls[0].body, telemetryCalls[1].body);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('dead-letters an idempotency conflict instead of retrying forever', async () => {
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    response.writeHead(409, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ error: 'idempotency_conflict', message: 'eventId belongs to another payload' }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(singleReading(1), RECEIVED_AT);
    await waitFor(() => forwarder.counters.deadLetters === 1 && forwarder.counters.queued === 0);
    assert.equal(server.seen.filter((record) => record.url === '/api/telemetry/').length, 1);
    assert.equal(forwarder.counters.retries, 0);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('drops a batch rejected with a validation error and keeps the lane flowing', async () => {
  let rejected = true;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    if (rejected) {
      response.writeHead(400, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'validation_error', message: 'Telemetry references missing or inactive assets.' }));
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
    });
    forwarder.forward(SAMPLE, RECEIVED_AT);
    await waitFor(() => forwarder.counters.dropped === 1 && forwarder.counters.queued === 0);
    assert.equal(forwarder.counters.deadLetters, 1);
    rejected = false;
    forwarder.forward(singleReading(23), RECEIVED_AT);
    await waitFor(() => forwarder.counters.delivered === 1);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('drops the oldest batch when the retry queue overflows', async () => {
  let released = false;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    if (!released) {
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'server_error' }));
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const forwarder = createDjangoForwarder({
      baseUrl: server.baseUrl,
      email: 'gateway@example.com',
      password: 'secret',
      retryDelayMs: 10,
      maxRetryDelayMs: 20,
      queueMax: 2,
    });
    forwarder.forward(singleReading(1), RECEIVED_AT);
    forwarder.forward(singleReading(2), RECEIVED_AT);
    forwarder.forward(singleReading(3), RECEIVED_AT);
    await waitFor(() => forwarder.counters.dropped === 1);
    assert.equal(forwarder.counters.deadLetters, 1);
    released = true;
    await waitFor(() => forwarder.counters.delivered === 2);
    assert.equal(forwarder.counters.queued, 0);
    forwarder.close();
  } finally {
    server.server.close();
  }
});

test('persists dead-letter payloads and reasons across restarts', () => {
  const directory = mkdtempSync(join(tmpdir(), 'ut-iotda-dlq-'));
  const queueDbPath = join(directory, 'outbox.sqlite');
  try {
    const first = new Outbox(queueDbPath, 1);
    first.enqueue(toDjangoBatch(singleReading(1), { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT }), RECEIVED_AT.toISOString());
    first.enqueue(toDjangoBatch(singleReading(2), { deviceId: 'CTRL-01', receivedAt: RECEIVED_AT }), RECEIVED_AT.toISOString());
    assert.equal(first.count(), 1);
    assert.equal(first.deadLetterCount(), 1);
    assert.equal(first.listDeadLetters()[0].reason, 'queue_overflow');
    first.close();

    const second = new Outbox(queueDbPath, 1);
    assert.equal(second.deadLetterCount(), 1);
    assert.equal(second.listDeadLetters()[0].batch.readings[0].value, 1);
    second.close();
  } finally {
    try { rmSync(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); } catch { /* Windows may retain a transient WAL handle. */ }
  }
});

test('replays a durable SQLite outbox after a gateway restart', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'ut-iotda-outbox-'));
  const queueDbPath = join(directory, 'outbox.sqlite');
  let available = false;
  const server = await startServer((record, response) => {
    if (record.url === '/api/auth/login/') {
      loginResponse(response, 'token-1');
      return;
    }
    if (!available) {
      response.writeHead(503, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'unavailable' }));
      return;
    }
    response.writeHead(201, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ items: [], created: record.body.readings.length, duplicates: 0, rules: {} }));
  });
  try {
    const first = createDjangoForwarder({ baseUrl: server.baseUrl, email: 'gateway@example.com', password: 'secret', queueDbPath, retryDelayMs: 1000 });
    first.forward(singleReading(31), RECEIVED_AT);
    await waitFor(() => first.counters.queued === 1 && first.counters.retries === 1);
    first.close();
    await new Promise((resolve) => setTimeout(resolve, 20));

    const inspection = new Outbox(queueDbPath);
    assert.equal(inspection.count(), 1);
    inspection.close();

    available = true;
    const second = createDjangoForwarder({ baseUrl: server.baseUrl, email: 'gateway@example.com', password: 'secret', queueDbPath, retryDelayMs: 10 });
    await waitFor(() => second.counters.delivered === 1 && second.counters.queued === 0);
    second.close();
  } finally {
    server.server.close();
    try { rmSync(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); } catch { /* Windows may retain a transient WAL handle. */ }
  }
});
