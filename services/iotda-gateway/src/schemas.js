import { readFileSync } from 'node:fs';
import { z } from 'zod';

const catalog = JSON.parse(readFileSync(new URL('./four-controller-catalog.json', import.meta.url), 'utf8'));
const specifications = new Map();
const register = (assetCode, controllerId, metrics) => {
  specifications.set(assetCode, { controllerId, metrics: new Map(metrics.map(([metric, unit, min, max]) => [metric, { unit, min, max }])) });
};
for (const binding of catalog.bindings) {
  const tag = binding.physicalTag;
  let metrics;
  if (tag.startsWith('MQ2-')) metrics = [['smoke.alarm', 'bool', 0, 1]];
  else if (tag.startsWith('MQ4-')) metrics = [['methane.raw', 'adc', 0, 4095]];
  else if (tag.startsWith('CO-')) metrics = [['co.raw', 'adc', 0, 4095]];
  else if (tag.startsWith('FLAME-')) metrics = [['flame.alarm', 'bool', 0, 1]];
  else if (tag.startsWith('SHT-')) metrics = [['temperature', 'degC', -45, 130], ['humidity', '%RH', 0, 100]];
  else if (tag.startsWith('LEVEL-')) metrics = [['level.detected', 'bool', 0, 1]];
  else if (tag.startsWith('O2-')) metrics = [['oxygen.raw', 'adc', 0, 4095], ['oxygen.voltage', 'mV', 0, 3300]];
  else throw new Error('Unsupported physical sensor in the frozen inventory.');
  register(binding.assetCode, binding.controllerId, metrics);
}
for (const [fan, controller] of [['FAN-01', 'CTRL-04'], ['FAN-02', 'CTRL-02']]) {
  register(fan, controller, [
    ['rotational.speed', 'rpm', 0, 1e9], ['supply.voltage', 'V', 0, 1e9],
    ['motor.current', 'mA', -1e9, 1e9], ['power', 'W', -1e9, 1e9],
    ['pwm.duty', '%', 0, 100], ['relay.commanded', 'bool', 0, 1],
  ]);
}
for (let i = 1; i <= 4; i++) register('CTRL-0' + i, 'CTRL-0' + i, [['heartbeat', 'bool', 1, 1]]);
const expected = new Map();
for (const [asset, spec] of specifications) {
  if (!expected.has(spec.controllerId)) expected.set(spec.controllerId, new Set());
  for (const metric of spec.metrics.keys()) expected.get(spec.controllerId).add(asset + ':' + metric);
}

export const telemetrySchema = z.object({
  schema: z.literal('ut.telemetry.v1'),
  seq: z.number().int().nonnegative().optional(),
  ts: z.string().optional(),
  frameId: z.string().regex(/^[A-Za-z0-9._:-]{1,80}$/).optional(),
  source: z.string().optional(),
  controllerId: z.string().regex(/^CTRL-0[1-4]$/).optional(),
  layoutVersion: z.string().optional(),
  rawOnly: z.boolean().optional(),
  clockSource: z.enum(['gateway-ntp', 'receiver-estimated']).optional(),
  readings: z.array(z.object({
    assetCode: z.string(), metric: z.string(), value: z.number().finite(), unit: z.string(),
    quality: z.enum(['good', 'suspect', 'bad', 'missing']).default('good'),
    sampleAgeMs: z.number().int().min(0).max(700000).optional(),
    eventLatched: z.boolean().optional(),
  })).min(1).max(32),
}).superRefine((frame, ctx) => {
  if (frame.source !== 'four-controller-rtu-v2') return;
  if (!frame.frameId || !frame.controllerId || frame.layoutVersion !== catalog.revision || frame.rawOnly !== true
      || !frame.clockSource || (frame.clockSource === 'gateway-ntp' && (!frame.ts || !Number.isFinite(Date.parse(frame.ts))))
      || (frame.clockSource === 'receiver-estimated' && frame.ts != null)) {
    ctx.addIssue({ code: 'custom', message: 'Four-controller frame metadata is incomplete or contradicts its clock source.' });
  }
  const seen = new Set();
  for (const [i, r] of frame.readings.entries()) {
    const key = r.assetCode + ':' + r.metric;
    const spec = specifications.get(r.assetCode);
    const metric = spec?.metrics.get(r.metric);
    if (spec?.controllerId !== frame.controllerId || !metric || metric.unit !== r.unit
        || r.value < metric.min || r.value > metric.max
        || ((r.unit === 'bool' || r.unit === 'adc') && !Number.isInteger(r.value))
        || seen.has(key) || r.sampleAgeMs == null
        || (r.eventLatched && (!['smoke.alarm', 'flame.alarm', 'level.detected'].includes(r.metric) || r.value !== 1))) {
      ctx.addIssue({ code: 'custom', path: ['readings', i], message: 'Invalid owner, metric, unit, value, duplicate, age, or event latch.' });
    }
    seen.add(key);
  }
  const required = expected.get(frame.controllerId);
  if (!required || required.size !== seen.size || [...required].some((key) => !seen.has(key))) {
    ctx.addIssue({ code: 'custom', path: ['readings'], message: 'A four-controller snapshot must contain its complete sensor, actuator and heartbeat metrics.' });
  }
});

export function parseTelemetry(payload, deviceId) {
  const telemetry = telemetrySchema.parse(typeof payload === 'string' ? JSON.parse(payload) : payload);
  if (telemetry.source !== 'four-controller-rtu-v2') return telemetry;
  if (telemetry.controllerId !== deviceId) throw new Error('Topic controller and payload controller differ.');
  // Enforce structured quality facts even if a sender incorrectly labels them good.
  telemetry.readings = telemetry.readings.map((r) => {
    let quality = r.quality;
    if (r.sampleAgeMs > 5000 && quality !== 'missing') quality = 'bad';
    else if (quality === 'good' && (telemetry.clockSource !== 'gateway-ntp'
        || r.metric.startsWith('oxygen.')
        || (['methane.raw', 'co.raw'].includes(r.metric) && r.value === 4095))) quality = 'suspect';
    return { ...r, quality };
  });
  return telemetry;
}
