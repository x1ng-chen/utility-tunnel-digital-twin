import { createHash } from 'node:crypto';
import { Outbox } from './outbox.js';

// The STM32 reports units from the fixed device enum in the README
// (degC, %RH, ...). Django thresholds store display units (°C), and a
// mismatching unit rejects the whole batch. Map device units to platform
// units here; unknown units pass through unchanged.
export const DJANGO_UNIT_MAP = {
  degC: '°C',
};

export const DJANGO_METRIC_LABELS = {
  temperature: '环境温度',
  humidity: '环境湿度',
  'water.raw': '水位 ADC',
  'level.detected': '液位检测',
  'smoke.alarm': '烟雾告警',
  'flame.alarm': '火焰告警',
  'oxygen.raw': '氧传感器 ADC',
  'oxygen.voltage': '氧传感器电压',
  'oxygen.concentration': '氧气浓度（电压换算）',
  'vibration.alarm': '振动锁存',
  'supply.voltage': '供电电压',
  'motor.current': '电机电流',
  power: '功率',
  'rotational.speed': '转速',
};

const ASSET_CODE_PATTERN = /^[A-Z0-9][A-Z0-9_-]{1,39}$/;
const METRIC_KEY_PATTERN = /^[a-z][a-z0-9_.-]{1,39}$/;

function shortDeviceId(deviceId) {
  // eventId must stay within [A-Za-z0-9._:-]{1,80}, so a long device id is
  // compressed to its first characters plus a short digest.
  if (deviceId.length <= 24) return deviceId;
  const digest = createHash('sha256').update(deviceId).digest('hex').slice(0, 8);
  return `${deviceId.slice(0, 15)}.${digest}`;
}

function normalizeRecordedAt(telemetry, receivedAt) {
  const fallback = receivedAt.toISOString();
  if (typeof telemetry.ts !== 'string' || !telemetry.ts) return fallback;
  const parsed = new Date(telemetry.ts);
  return Number.isNaN(parsed.getTime()) ? fallback : parsed.toISOString();
}

export function toDjangoBatch(telemetry, { deviceId = 'CTRL-01', receivedAt = new Date() } = {}) {
  const recordedAt = normalizeRecordedAt(telemetry, receivedAt);
  // A content-derived frame id is stable across MQTT redelivery while still
  // distinguishing different payloads received in the same millisecond.
  // Keep the digest compact so the per-reading suffix remains under Django's
  // 80-character eventId contract.
  const frameDigest = createHash('sha256')
    .update(JSON.stringify({ deviceId, recordedAt, readings: telemetry.readings }))
    .digest('hex')
    .slice(0, 24);
  const idBase = `gw:${shortDeviceId(deviceId)}:${frameDigest}`;
  const readings = [];
  const skipped = [];
  telemetry.readings.forEach((reading, index) => {
    const assetCode = String(reading.assetCode || '').toUpperCase();
    const metricKey = String(reading.metric || '').toLowerCase();
    const rawValue = reading.value;
    const value = Number(rawValue);
    if (!ASSET_CODE_PATTERN.test(assetCode)) {
      skipped.push({ assetCode: reading.assetCode, metric: reading.metric, reason: 'assetCode does not match the platform pattern' });
      return;
    }
    if (!METRIC_KEY_PATTERN.test(metricKey)) {
      skipped.push({ assetCode, metric: reading.metric, reason: 'metricKey does not match the platform pattern' });
      return;
    }
    if ((typeof rawValue !== 'number' && (typeof rawValue !== 'string' || !rawValue.trim())) || !Number.isFinite(value)) {
      skipped.push({ assetCode, metric: metricKey, reason: 'value is missing or not a finite number' });
      return;
    }
    readings.push({
      eventId: `${idBase}:${index}`.slice(0, 80),
      assetCode,
      metricKey,
      metric: DJANGO_METRIC_LABELS[metricKey] || metricKey,
      value,
      unit: DJANGO_UNIT_MAP[reading.unit] || reading.unit,
      quality: reading.quality ?? 'suspect',
      recordedAt,
    });
  });
  return { readings, skipped };
}

export function createDjangoForwarder({
  baseUrl,
  email,
  password,
  apiKey,
  deviceId = 'CTRL-01',
  fetchImpl = fetch,
  timeoutMs = 5000,
  retryDelayMs = 2000,
  maxRetryDelayMs = 60000,
  queueMax = 43200,
  queueDbPath = ':memory:',
  log = console,
} = {}) {
  if (!baseUrl) throw new Error('baseUrl is required.');
  if (!apiKey && (!email || !password)) throw new Error('apiKey or email and password are required.');

  const outbox = new Outbox(queueDbPath, queueMax);
  const state = {
    token: null,
    timer: null,
    flushing: false,
    stopped: false,
    closePending: false,
    currentItemId: null,
    retryDelay: retryDelayMs,
  };
  const counters = {
    delivered: 0,
    duplicates: 0,
    rulesTriggered: 0,
    dropped: 0,
    queued: outbox.count(),
    retries: 0,
    logins: 0,
    deadLetters: outbox.deadLetterCount(),
  };

  async function login() {
    if (apiKey) return;
    const response = await fetchImpl(`${baseUrl}/api/auth/login/`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ email, password }),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      throw Object.assign(new Error(`Django login failed with status ${response.status}.`), { status: response.status });
    }
    const data = await response.json();
    if (!data.accessToken) {
      throw new Error('Django login response did not contain an accessToken.');
    }
    state.token = data.accessToken;
    counters.logins += 1;
    log.info(`Django ingest account authenticated: ${email}.`);
  }

  async function postTelemetry(batch) {
    return fetchImpl(`${baseUrl}/api/telemetry/`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        ...(apiKey ? { 'x-ingest-key': apiKey } : { authorization: `Bearer ${state.token}` }),
      },
      body: JSON.stringify(batch),
      signal: AbortSignal.timeout(timeoutMs),
    });
  }

  function scheduleRetry() {
    if (state.timer || state.stopped) return;
    counters.retries += 1;
    state.timer = setTimeout(() => {
      state.timer = null;
      void flush();
    }, state.retryDelay);
    state.retryDelay = Math.min(state.retryDelay * 2, maxRetryDelayMs);
  }

  function resetBackoff() {
    state.retryDelay = retryDelayMs;
  }

  function dropHead(reason) {
    const item = outbox.peek();
    if (!item) return;
    outbox.deadLetter(item.id, reason);
    counters.dropped += 1;
    counters.deadLetters += 1;
    log.error(`Django batch moved to persistent dead letter (${reason}): ${JSON.stringify(item.batch.readings.map((reading) => `${reading.assetCode}/${reading.metricKey}`))}`);
  }

  async function flush() {
    if (state.flushing || state.stopped) return;
    state.flushing = true;
    try {
      while (outbox.count() && !state.stopped) {
        const item = outbox.peek();
        if (!item) break;
        state.currentItemId = item.id;
        let response;
        try {
          if (!apiKey && !state.token) await login();
          response = await postTelemetry(item.batch);
        } catch (error) {
          log.error(`Django request failed, will retry: ${error instanceof Error ? error.message : error}`);
          scheduleRetry();
          break;
        }

        if (response.status === 401 && !apiKey) {
          // Token expired (platform TTL is 15 minutes by default): drop the
          // cached token, re-login and replay the same batch once.
          state.token = null;
          try {
            await login();
            response = await postTelemetry(item.batch);
          } catch (error) {
            log.error(`Django re-login failed, will retry: ${error instanceof Error ? error.message : error}`);
            scheduleRetry();
            break;
          }
          if (response.status === 401) {
            log.error('Django rejected the fresh ingest token, will retry later.');
            scheduleRetry();
            break;
          }
        }

        if (response.ok) {
          outbox.delete(item.id);
          resetBackoff();
          counters.delivered += item.batch.readings.length;
          const body = await response.json().catch(() => ({}));
          const duplicates = Number(body.duplicates) || 0;
          const created = Number(body.created) || item.batch.readings.length - duplicates;
          const rules = body.rules && typeof body.rules === 'object'
            ? Object.values(body.rules).reduce((sum, count) => sum + (Number(count) || 0), 0)
            : 0;
          counters.duplicates += duplicates;
          if (rules) counters.rulesTriggered += rules;
          log.info(`Django stored ${created} reading(s) (duplicates ${duplicates}, queued ${outbox.count()}).`);
          continue;
        }

        if (response.status === 409) {
          const details = await response.json().catch(() => ({}));
          if (details.error === 'idempotency_conflict') {
            dropHead(`idempotency conflict ${JSON.stringify(details).slice(0, 300)}`);
            continue;
          }
          // A database concurrency conflict is safe to retry because the
          // exact queued batch retains its original eventIds.
          log.warn(`Django reported a transient conflict, will replay the same batch: ${JSON.stringify(details).slice(0, 300)}`);
          scheduleRetry();
          break;
        }

        if (response.status === 429 || response.status >= 500) {
          log.warn(`Django returned status ${response.status}, will retry.`);
          scheduleRetry();
          break;
        }

        // 4xx validation errors never heal by retrying: drop the batch and
        // keep the live lane flowing, matching the platform contract that
        // invalid data must not enter the database.
        const details = await response.json().catch(() => ({}));
        dropHead(`status ${response.status} ${JSON.stringify(details).slice(0, 300)}`);
      }
    } finally {
      state.flushing = false;
      state.currentItemId = null;
      counters.queued = outbox.count();
      if (state.closePending) outbox.close();
    }
  }

  function forward(telemetry, receivedAt = new Date()) {
    if (state.stopped) return;
    const batch = toDjangoBatch(telemetry, { deviceId, receivedAt });
    for (const item of batch.skipped) {
      log.warn(`Django reading skipped (${item.reason}): ${item.assetCode}/${item.metric}`);
    }
    if (!batch.readings.length) return;
    const overflow = outbox.enqueue(batch, receivedAt.toISOString(), state.currentItemId);
    for (const item of overflow) {
      counters.dropped += 1;
      counters.deadLetters += 1;
      log.error(`Django batch moved to persistent dead letter (queue overflow): ${JSON.stringify(item.batch.readings.map((reading) => `${reading.assetCode}/${reading.metricKey}`))}`);
    }
    counters.queued = outbox.count();
    void flush();
  }

  function close() {
    state.stopped = true;
    if (state.timer) {
      clearTimeout(state.timer);
      state.timer = null;
    }
    if (state.flushing) state.closePending = true;
    else outbox.close();
  }

  if (counters.queued) {
    log.info(`Django outbox restored ${counters.queued} queued batch(es).`);
    setTimeout(() => { void flush(); }, 0);
  }
  return { forward, close, counters, toDjangoBatch: (telemetry, options) => toDjangoBatch(telemetry, { deviceId, ...options }) };
}
