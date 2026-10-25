import { Vector3, type Object3D } from 'three';
import type { HardwareBinding, Telemetry } from '../types';

export interface FanFeedbackContext {
  telemetry: Telemetry[];
  bindings: HardwareBinding[];
  source: 'api' | 'demo';
  offline: boolean;
}
export type FanMotion = { assetCode: string; state: 'running' | 'stopped' | 'unknown'; measuredRpm: number | null; reason: string };
const unknown = (assetCode: string, reason: string): FanMotion => ({ assetCode, state: 'unknown', measuredRpm: null, reason });

export function resolveFanMotion(context: FanFeedbackContext, code: string, nowMs: number): FanMotion {
  if (!Number.isFinite(nowMs)) return unknown(code, 'invalid_clock');
  if (context.source !== 'api' || context.offline) return unknown(code, 'non_live_or_offline');
  const binding = context.bindings.find(b => b.assetCode === code);
  if (!binding || binding.status !== 'connected' || binding.connectivity !== 'online') return unknown(code, 'binding_offline');
  // Expire observations after the configured sampling period, even if polling stops.
  const maxAgeMs = binding.expectedIntervalSeconds * 1000;
  const heartbeatAge = nowMs - Date.parse(binding.lastHeartbeatAt || '');
  if (!Number.isFinite(maxAgeMs) || maxAgeMs <= 0 || !Number.isFinite(heartbeatAge) || heartbeatAge < 0 || heartbeatAge > maxAgeMs) return unknown(code, 'heartbeat_stale');
  const candidates = context.telemetry.filter(r => r.assetCode === code && r.metricKey === 'rotational.speed');
  if (!candidates.length) return unknown(code, 'missing');
  if (candidates.some(r => !Number.isFinite(Date.parse(r.recordedAt)))) return unknown(code, 'invalid_timestamp');
  const latestAt = Math.max(...candidates.map(r => Date.parse(r.recordedAt)));
  const latest = candidates.filter(r => Date.parse(r.recordedAt) === latestAt);
  const reading = latest[0];
  if (latest.some(r => r.value !== reading.value || r.quality !== reading.quality || r.unit !== reading.unit)) return unknown(code, 'conflicting_latest');
  if (latestAt > nowMs) return unknown(code, 'future_timestamp');
  if (nowMs - latestAt > maxAgeMs) return unknown(code, 'stale');
  if (latest.some(r => /^(demo|simulation|fixture):/i.test(r.eventId || ''))) return unknown(code, 'demo');
  if (reading.quality !== 'good') return unknown(code, 'quality');
  if (reading.unit.trim().toLowerCase() !== 'rpm') return unknown(code, 'unit');
  if (!Number.isFinite(reading.value) || reading.value < 0) return unknown(code, 'invalid_rpm');
  return { assetCode: code, state: reading.value > 0 ? 'running' : 'stopped', measuredRpm: reading.value, reason: 'fresh_measured_rpm' };
}

/** V17's glTF local axis; this never rotates fan housing or starts another RAF. */
export function createFanAnimator(root: Object3D) {
  const codes = ['FAN-01', 'FAN-02'];
  const rotors = codes.map(code => {
    const matches: Object3D[] = [];
    root.traverse(object => { if (object.name === `${code}_ROTOR`) matches.push(object); });
    return matches.length === 1 ? matches[0] : undefined;
  });
  const axis = new Vector3(0, 0, -1);
  let disposed = false;
  return {
    update(context: FanFeedbackContext, nowMs: number, deltaSeconds: number) {
      if (disposed) return [];
      const dt = Number.isFinite(deltaSeconds) ? Math.min(Math.max(deltaSeconds, 0), .1) : 0;
      return codes.map((code, index) => {
        const rotor = rotors[index];
        const motion = rotor ? resolveFanMotion(context, code, nowMs) : unknown(code, 'rotor_unavailable');
        if (rotor && motion.state === 'running') {
          // Visual speed cap only; display the uncapped measured RPM separately.
          rotor.rotateOnAxis(axis, Math.min(motion.measuredRpm!, 90) * 2 * Math.PI / 60 * dt);
        }
        return motion;
      });
    },
    dispose() { disposed = true; rotors.length = 0; },
  };
}
