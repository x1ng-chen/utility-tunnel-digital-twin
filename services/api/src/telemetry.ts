import { z } from 'zod';
import { inTransaction } from './db.js';
import { realtimeHub, type RealtimeTelemetryReading } from './realtime.js';

const topicPattern = /^ut\/v1\/([a-z0-9-]+)\/telemetry$/i;
const readingSchema = z.object({
  assetCode: z.string().regex(/^[A-Z][A-Z0-9-]*[A-Z0-9]$/).max(64),
  metric: z.string().regex(/^[a-z][a-z0-9_.-]*$/).max(96),
  value: z.number().finite(),
  unit: z.string().trim().min(1).max(32),
  quality: z.enum(['good', 'suspect', 'bad', 'missing']).default('good'),
});
const telemetrySchema = z.object({
  schema: z.literal('ut.telemetry.v1'),
  ts: z.string().datetime({ offset: true }).optional(),
  readings: z.array(readingSchema).min(1).max(32),
});

export type IncomingTelemetry = z.infer<typeof telemetrySchema> & { deviceId: string; recordedAt: string };

function parseTelemetryPayload(payload: Buffer | string | unknown) {
  let input: unknown;
  if (Buffer.isBuffer(payload) || typeof payload === 'string') {
    try {
      input = JSON.parse(String(payload));
    } catch {
      throw new Error('Telemetry payload is not valid JSON.');
    }
  } else {
    input = payload;
  }
  const parsed = telemetrySchema.safeParse(input);
  if (!parsed.success) throw new Error(`Invalid telemetry payload: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
  return parsed.data;
}

export function parseDeviceTelemetry(deviceId: string, payload: Buffer | string | unknown): IncomingTelemetry {
  if (!/^[a-z0-9-]{1,64}$/i.test(deviceId)) throw new Error('Invalid device identifier.');
  const telemetry = parseTelemetryPayload(payload);
  return { ...telemetry, deviceId: deviceId.toUpperCase(), recordedAt: telemetry.ts ?? new Date().toISOString() };
}

export function parseTelemetry(topic: string, payload: Buffer | string): IncomingTelemetry {
  const topicMatch = topicPattern.exec(topic);
  if (!topicMatch?.[1]) throw new Error('Unexpected telemetry topic.');
  return parseDeviceTelemetry(topicMatch[1], payload);
}

export async function persistTelemetry(input: IncomingTelemetry): Promise<RealtimeTelemetryReading[]> {
  const persisted = await inTransaction(async (client) => {
    const assetCodes = [...new Set(input.readings.map((reading) => reading.assetCode))];
    const result = await client.query<{ id: string; code: string }>('SELECT id, code FROM asset WHERE code = ANY($1::varchar[])', [assetCodes]);
    const assets = new Map(result.rows.map((asset) => [asset.code, asset.id]));
    const missing = assetCodes.filter((assetCode) => !assets.has(assetCode));
    if (missing.length) throw new Error(`Unknown asset code: ${missing.join(', ')}`);

    const readings: RealtimeTelemetryReading[] = [];
    for (const reading of input.readings) {
      const assetId = assets.get(reading.assetCode);
      if (!assetId) throw new Error(`Unknown asset code: ${reading.assetCode}`);
      const inserted = await client.query<RealtimeTelemetryReading>(
        `INSERT INTO telemetry_reading (recorded_at, asset_id, metric_code, numeric_value, unit, quality, source)
         VALUES ($1, $2, $3, $4, $5, $6, 'device')
         RETURNING id, metric_code, numeric_value, unit, quality, recorded_at`,
        [input.recordedAt, assetId, reading.metric, reading.value, reading.unit, reading.quality],
      );
      const row = inserted.rows[0];
      if (!row) throw new Error('Telemetry insert did not return a row.');
      readings.push({ ...row, asset_code: reading.assetCode, numeric_value: Number(row.numeric_value) });
      await client.query("UPDATE asset SET updated_at = now(), operational_status = CASE WHEN operational_status = 'offline' THEN 'normal' ELSE operational_status END WHERE id = $1", [assetId]);
    }
    return readings;
  });
  realtimeHub.publish(persisted);
  return persisted;
}
