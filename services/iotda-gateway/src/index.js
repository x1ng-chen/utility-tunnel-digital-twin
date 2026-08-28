import 'dotenv/config';
import { readFileSync } from 'node:fs';
import mqtt from 'mqtt';
import { z } from 'zod';
import { createDeviceCredentials } from './auth.js';

const environment = z.object({
  LOCAL_MQTT_URL: z.string().url().default('mqtt://127.0.0.1:1883'),
  LOCAL_MQTT_USERNAME: z.string().optional(),
  LOCAL_MQTT_PASSWORD: z.string().optional(),
  LOCAL_DEVICE_ID: z.string().regex(/^[a-z0-9-]{1,64}$/i).default('CTRL-01'),
  IOTDA_HOST: z.string().min(4),
  IOTDA_PORT: z.coerce.number().int().min(1).max(65535).default(8883),
  IOTDA_DEVICE_ID: z.string().min(4).max(256),
  IOTDA_DEVICE_SECRET: z.string().min(8),
  IOTDA_CA_FILE: z.string().optional(),
});

const telemetrySchema = z.object({
  schema: z.literal('ut.telemetry.v1'),
  ts: z.string().optional(),
  readings: z.array(z.object({
    assetCode: z.string(),
    metric: z.string(),
    value: z.number().finite(),
    unit: z.string(),
    quality: z.enum(['good', 'suspect', 'bad', 'missing']).default('good'),
  })).min(1).max(32),
});

const configResult = environment.safeParse(process.env);
if (!configResult.success) {
  throw new Error(`Invalid IoTDA gateway configuration: ${configResult.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
}
const config = configResult.data;
const credentials = createDeviceCredentials(config.IOTDA_DEVICE_ID, config.IOTDA_DEVICE_SECRET);
const localTelemetryTopic = `ut/v1/${config.LOCAL_DEVICE_ID}/telemetry`;
const localCloudCommandTopic = `ut/v1/${config.LOCAL_DEVICE_ID}/cmd/iotda`;
const cloudMessageUpTopic = `$oc/devices/${config.IOTDA_DEVICE_ID}/sys/messages/up`;
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

const local = mqtt.connect(config.LOCAL_MQTT_URL, {
  username: config.LOCAL_MQTT_USERNAME,
  password: config.LOCAL_MQTT_PASSWORD,
  reconnectPeriod: 3000,
});
const cloud = mqtt.connect(`mqtts://${config.IOTDA_HOST}:${config.IOTDA_PORT}`, cloudOptions);

local.on('connect', () => {
  local.subscribe(localTelemetryTopic, { qos: 1 }, (error) => {
    if (error) console.error('Local MQTT subscribe failed:', error.message);
    else console.info(`Local MQTT ready: ${localTelemetryTopic}`);
  });
});

cloud.on('connect', () => {
  cloud.subscribe([cloudMessageDownTopic, cloudCommandsTopic], { qos: 1 }, (error) => {
    if (error) console.error('IoTDA subscribe failed:', error.message);
    else console.info(`IoTDA connected securely as ${config.IOTDA_DEVICE_ID}.`);
  });
});

local.on('message', (_topic, payload) => {
  let telemetry;
  try {
    telemetry = telemetrySchema.parse(JSON.parse(payload.toString('utf8')));
  } catch (error) {
    console.warn('Rejected invalid local telemetry:', error instanceof Error ? error.message : error);
    return;
  }
  const cloudPayload = JSON.stringify({
    object_device_id: config.IOTDA_DEVICE_ID,
    name: 'ut.telemetry.v1',
    content: telemetry,
  });
  cloud.publish(cloudMessageUpTopic, cloudPayload, { qos: 1 }, (error) => {
    if (error) console.error('IoTDA publish failed:', error.message);
    else console.info(`Forwarded ${telemetry.readings.length} reading(s) to IoTDA.`);
  });
});

cloud.on('message', (topic, payload) => {
  local.publish(localCloudCommandTopic, JSON.stringify({
    sourceTopic: topic,
    payload: payload.toString('utf8'),
  }), { qos: 1 });
});

for (const [name, client] of [['Local MQTT', local], ['IoTDA', cloud]]) {
  client.on('error', (error) => console.error(`${name} error:`, error.message));
}

const shutdown = () => {
  local.end(true);
  cloud.end(true);
};
process.once('SIGINT', shutdown);
process.once('SIGTERM', shutdown);

