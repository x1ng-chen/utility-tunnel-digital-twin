import 'dotenv/config';
import { readFileSync } from 'node:fs';
import mqtt from 'mqtt';
import { z } from 'zod';
import { createDeviceCredentials } from './auth.js';
import { createDjangoForwarder } from './django.js';
import { addCalculatedOxygenConcentration } from './telemetry.js';

const environment = z.object({
  LOCAL_MQTT_URL: z.string().url().default('mqtt://127.0.0.1:1883'),
  LOCAL_MQTT_USERNAME: z.string().optional(),
  LOCAL_MQTT_PASSWORD: z.string().optional(),
  LOCAL_DEVICE_ID: z.string().regex(/^[a-z0-9-]{1,64}$/i).default('CTRL-01'),
  IOTDA_ENABLED: z.enum(['true', 'false']).default('true'),
  IOTDA_HOST: z.string().min(4).optional(),
  IOTDA_PORT: z.coerce.number().int().min(1).max(65535).default(8883),
  IOTDA_DEVICE_ID: z.string().min(4).max(256).optional(),
  IOTDA_DEVICE_SECRET: z.string().min(8).optional(),
  IOTDA_CA_FILE: z.string().optional(),
  DJANGO_API_URL: z.string().url().optional(),
  DJANGO_INGEST_EMAIL: z.string().optional(),
  DJANGO_INGEST_PASSWORD: z.string().optional(),
  DJANGO_INGEST_API_KEY: z.string().min(32).optional(),
  DJANGO_TIMEOUT_MS: z.coerce.number().int().min(500).max(60000).default(5000),
  DJANGO_QUEUE_MAX: z.coerce.number().int().min(1).max(500000).default(43200),
  DJANGO_QUEUE_DB: z.string().min(1).default('./data/iotda-outbox.sqlite'),
});

const telemetrySchema = z.object({
  schema: z.literal('ut.telemetry.v1'),
  seq: z.number().int().nonnegative().optional(),
  ts: z.string().optional(),
  readings: z.array(z.object({
    assetCode: z.string(),
    metric: z.string(),
    value: z.number().finite(),
    unit: z.string(),
    quality: z.enum(['good', 'suspect', 'bad', 'missing']).default('suspect'),
  })).min(1).max(32),
});

const configResult = environment.safeParse(process.env);
if (!configResult.success) {
  throw new Error(`Invalid IoTDA gateway configuration: ${configResult.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
}
const config = configResult.data;

// Dual-output sinks: Huawei Cloud IoTDA and/or the Django ingest API. At
// least one must stay enabled; keeping both disabled would silently drop
// every reading.
const iotdaEnabled = config.IOTDA_ENABLED !== 'false';
const djangoEnabled = Boolean(config.DJANGO_API_URL);
const missing = [];
if (iotdaEnabled) {
  if (!config.IOTDA_HOST) missing.push('IOTDA_HOST');
  if (!config.IOTDA_DEVICE_ID) missing.push('IOTDA_DEVICE_ID');
  if (!config.IOTDA_DEVICE_SECRET) missing.push('IOTDA_DEVICE_SECRET');
}
if (djangoEnabled && !config.DJANGO_INGEST_API_KEY && (!config.DJANGO_INGEST_EMAIL || !config.DJANGO_INGEST_PASSWORD)) {
  missing.push('DJANGO_INGEST_EMAIL', 'DJANGO_INGEST_PASSWORD');
}
if (!iotdaEnabled && !djangoEnabled) {
  missing.push('IOTDA_ENABLED or DJANGO_API_URL (one output target is required)');
}
if (missing.length) {
  throw new Error(`Invalid IoTDA gateway configuration: ${missing.join(', ')}`);
}

const localTelemetryTopic = `ut/v1/${config.LOCAL_DEVICE_ID}/telemetry`;
const localCloudCommandTopic = `ut/v1/${config.LOCAL_DEVICE_ID}/cmd/iotda`;
const cloudMessageUpTopic = `$oc/devices/${config.IOTDA_DEVICE_ID}/sys/messages/up`;

const local = mqtt.connect(config.LOCAL_MQTT_URL, {
  username: config.LOCAL_MQTT_USERNAME,
  password: config.LOCAL_MQTT_PASSWORD,
  reconnectPeriod: 3000,
});

let cloud = null;
let credentials = null;
if (iotdaEnabled) {
  credentials = createDeviceCredentials(config.IOTDA_DEVICE_ID, config.IOTDA_DEVICE_SECRET);
  const cloudMessageDownTopic = `$oc/devices/${config.IOTDA_DEVICE_ID}/sys/messages/down`;
  const cloudCommandsTopic = `$oc/devices/${config.IOTDA_DEVICE_ID}/sys/commands/#`;

  const cloudOptions = {
    protocol: 'mqtts',
    port: config.IOTDA_PORT,
    clientId: credentials.clientId,
    username: credentials.username,
    password: credentials.password,
    rejectUnauthorized: true,
    reconnectPeriod: 5000,
    connectTimeout: 15000,
    clean: true,
    ...(config.IOTDA_CA_FILE ? { ca: readFileSync(config.IOTDA_CA_FILE) } : {}),
  };
  cloud = mqtt.connect(`mqtts://${config.IOTDA_HOST}:${config.IOTDA_PORT}`, cloudOptions);

  cloud.on('connect', () => {
    cloud.subscribe([cloudMessageDownTopic, cloudCommandsTopic], { qos: 1 }, (error) => {
      if (error) console.error('IoTDA subscribe failed:', error.message);
      else console.info(`IoTDA connected securely as ${config.IOTDA_DEVICE_ID}.`);
    });
  });

  cloud.on('message', (topic, payload) => {
    let commandPayload = payload.toString('utf8');
    /* IoTDA device messages are delivered in an envelope whose content is
     * the application-supplied message.  STM32 accepts the inner
     * ut.command.v1 JSON directly, not gateway metadata. */
    try {
      const envelope = JSON.parse(commandPayload);
      if (typeof envelope.message === 'string') commandPayload = envelope.message;
      else if (envelope.message && typeof envelope.message === 'object') commandPayload = JSON.stringify(envelope.message);
    } catch (_) {
      /* Direct MQTT custom messages are already the controller payload. */
    }
    local.publish(localCloudCommandTopic, commandPayload, { qos: 1 }, (error) => {
      if (error) console.error('Local cloud-command publish failed:', error.message);
      else console.info(`Forwarded IoTDA command from ${topic}.`);
    });
  });
}

const django = djangoEnabled
  ? createDjangoForwarder({
    baseUrl: config.DJANGO_API_URL,
    email: config.DJANGO_INGEST_EMAIL,
    password: config.DJANGO_INGEST_PASSWORD,
    apiKey: config.DJANGO_INGEST_API_KEY,
    deviceId: config.LOCAL_DEVICE_ID,
    timeoutMs: config.DJANGO_TIMEOUT_MS,
    queueMax: config.DJANGO_QUEUE_MAX,
    queueDbPath: config.DJANGO_QUEUE_DB,
  })
  : null;

local.on('connect', () => {
  local.subscribe(localTelemetryTopic, { qos: 1 }, (error) => {
    if (error) console.error('Local MQTT subscribe failed:', error.message);
    else console.info(`Local MQTT ready: ${localTelemetryTopic}`);
  });
});

local.on('message', (_topic, payload) => {
  let telemetry;
  try {
    telemetry = addCalculatedOxygenConcentration(telemetrySchema.parse(JSON.parse(payload.toString('utf8'))));
  } catch (error) {
    console.warn('Rejected invalid local telemetry:', error instanceof Error ? error.message : error);
    return;
  }
  if (cloud) {
    const cloudPayload = JSON.stringify({
      object_device_id: config.IOTDA_DEVICE_ID,
      name: 'ut.telemetry.v1',
      content: telemetry,
    });
    cloud.publish(cloudMessageUpTopic, cloudPayload, { qos: 1 }, (error) => {
      if (error) console.error('IoTDA publish failed:', error.message);
      else console.info(`Forwarded ${telemetry.readings.length} reading(s) to IoTDA.`);
    });
  }
  if (django) {
    django.forward(telemetry);
  }
});

for (const [name, client] of [['Local MQTT', local], ...(cloud ? [['IoTDA', cloud]] : [])]) {
  client.on('error', (error) => console.error(`${name} error:`, error.message));
}

if (django) {
  console.info(`Django ingestion target: ${config.DJANGO_API_URL} (${config.DJANGO_INGEST_API_KEY ? 'scoped ingest API key' : `legacy service account ${config.DJANGO_INGEST_EMAIL}`}).`);
}

const shutdown = () => {
  local.end(true);
  if (cloud) cloud.end(true);
  if (django) django.close();
};
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);
