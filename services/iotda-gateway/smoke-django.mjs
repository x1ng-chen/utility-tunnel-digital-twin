// End-to-end smoke: gateway forwarder -> Django ingest API -> PostgreSQL/SQLite.
// Uses the seeded operator account and the exact STM32 reading shape.
import { createDjangoForwarder, toDjangoBatch } from './src/django.js';

const baseUrl = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:8011';
const ingestApiKey = process.env.DJANGO_INGEST_API_KEY;
if (!ingestApiKey || ingestApiKey.length < 32) {
  throw new Error('DJANGO_INGEST_API_KEY must be configured with at least 32 characters for the smoke test.');
}

function waitFor(predicate, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const started = Date.now();
    const check = async () => {
      if (await predicate()) return resolve();
      if (Date.now() - started > timeoutMs) return reject(new Error('waitFor timed out'));
      setTimeout(check, 20);
    };
    check();
  });
}

// Wait for the Django server.
await waitFor(async () => {
  try {
    const response = await fetch(`${baseUrl}/api/health/`);
    return response.ok;
  } catch {
    return false;
  }
}, 30000);
console.log('Django server is up at', baseUrl);

const forwarder = createDjangoForwarder({
  baseUrl,
  apiKey: ingestApiKey,
  retryDelayMs: 500,
  maxRetryDelayMs: 2000,
});

// Fresh receivedAt per run so reruns do not collide with stored eventIds;
// the replay below reuses the same timestamp and therefore the same ids.
const receivedAt = new Date();
const message = {
  schema: 'ut.telemetry.v1',
  readings: [
    { assetCode: 'ENV-01', metric: 'temperature', value: 29.5, unit: 'degC', quality: 'good' },
    { assetCode: 'ENV-01', metric: 'humidity', value: 63, unit: '%RH', quality: 'good' },
    { assetCode: 'SEEP-W01', metric: 'water.raw', value: 640, unit: 'adc', quality: 'good' },
    { assetCode: 'CTRL-01', metric: 'vibration.alarm', value: 0, unit: 'bool', quality: 'good' },
  ],
};

forwarder.forward(message, receivedAt);
await waitFor(() => forwarder.counters.delivered + forwarder.counters.duplicates === 4 && forwarder.counters.queued === 0);
console.log('PASS 1 delivered:', { ...forwarder.counters });

forwarder.forward(message, receivedAt);
await waitFor(() => forwarder.counters.duplicates === 4 && forwarder.counters.queued === 0);
console.log('PASS 2 (idempotent replay):', { ...forwarder.counters });

forwarder.close();

const login = await fetch(`${baseUrl}/api/auth/login/`, {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email: 'operator@example.com', password: 'demo-password-2026' }),
});
const { accessToken } = await login.json();
const headers = { authorization: `Bearer ${accessToken}` };

const telemetry = await (await fetch(`${baseUrl}/api/telemetry/?assetCode=ENV-01&metricKey=temperature&pageSize=10`, { headers })).json();
console.log('ENV-01 temperature rows:', telemetry.items.map((item) => ({ value: item.value, unit: item.unit, eventId: item.eventId, recordedAt: item.recordedAt })));
assertRows: {
  const expectedEventId = toDjangoBatch(message, { deviceId: 'CTRL-01', receivedAt }).readings[0].eventId;
  const row = telemetry.items.find((item) => item.eventId === expectedEventId);
  if (!row) throw new Error(`expected this run's row ${expectedEventId} in the telemetry list`);
  if (row.unit !== '°C' || row.value !== 29.5) throw new Error('gateway row unit/value mismatch');
}

const alerts = await (await fetch(`${baseUrl}/api/alerts/?assetCode=ENV-01`, { headers })).json();
const ruleAlerts = alerts.items.filter((item) => item.ruleKey);
console.log('threshold rule alerts for ENV-01:', ruleAlerts.map((item) => ({ code: item.code, severity: item.severity, status: item.status, ruleKey: item.ruleKey, value: item.lastObservedValue })));
if (!ruleAlerts.some((item) => item.ruleKey === 'temperature' && item.severity === 'warning')) {
  throw new Error('expected an automatic warning alert for temperature above the 28 °C threshold');
}

console.log('SMOKE OK: gateway -> Django ingest -> threshold alert closed loop verified.');
