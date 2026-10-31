import { Mesh, MeshStandardMaterial, Vector3, type Material, type Object3D } from 'three';
import type { HardwareBinding, Telemetry } from '../types';

export interface FanFeedbackContext {
  telemetry: Telemetry[];
  bindings: HardwareBinding[];
  source: 'api' | 'demo';
  offline: boolean;
}
export type FanMotion = { assetCode: string; state: 'running' | 'stopped' | 'unknown'; measuredRpm: number | null; reason: string };
export type FanLighting = { state: 'on' | 'off' | 'unknown'; supplyVolts: number | null; reason: string };
export type FanVisualFeedback = FanMotion & { lighting: FanLighting };
const unknown = (assetCode: string, reason: string): FanMotion => ({ assetCode, state: 'unknown', measuredRpm: null, reason });

function measuredMetric(context: FanFeedbackContext, code: string, nowMs: number, metricKey: string, unit: string): FanMotion {
  if (!Number.isFinite(nowMs)) return unknown(code, 'invalid_clock');
  if (context.source !== 'api' || context.offline) return unknown(code, 'non_live_or_offline');
  const binding = context.bindings.find(b => b.assetCode === code);
  if (!binding || binding.status !== 'connected' || binding.connectivity !== 'online') return unknown(code, 'binding_offline');
  // Expire observations after the configured sampling period, even if polling stops.
  const maxAgeMs = binding.expectedIntervalSeconds * 1000;
  const heartbeatAge = nowMs - Date.parse(binding.lastHeartbeatAt || '');
  if (!Number.isFinite(maxAgeMs) || maxAgeMs <= 0 || !Number.isFinite(heartbeatAge) || heartbeatAge < 0 || heartbeatAge > maxAgeMs) return unknown(code, 'heartbeat_stale');
  const candidates = context.telemetry.filter(r => r.assetCode === code && r.metricKey === metricKey);
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
  if (reading.unit.trim().toLowerCase() !== unit) return unknown(code, 'unit');
  if (!Number.isFinite(reading.value) || reading.value < 0) return unknown(code, 'invalid_rpm');
  return { assetCode: code, state: reading.value > 0 ? 'running' : 'stopped', measuredRpm: reading.value, reason: 'fresh_measured_rpm' };
}

export function resolveFanMotion(context: FanFeedbackContext, code: string, nowMs: number): FanMotion {
  return measuredMetric(context, code, nowMs, 'rotational.speed', 'rpm');
}

/** Fixed-colour RGB is powered by the fan supply, independently of the rotor. */
export function resolveFanLighting(context: FanFeedbackContext, code: string, nowMs: number): FanLighting {
  // The display rule is measured V > 0, not an unverified LED operating threshold.
  // Missing voltage stays unknown even when the fan is spinning.
  const checked = measuredMetric(context, code, nowMs, 'supply.voltage', 'v');
  if (checked.state === 'unknown') return { state: 'unknown', supplyVolts: null, reason: `supply_${checked.reason}` };
  return { state: checked.measuredRpm! > 0 ? 'on' : 'off', supplyVolts: checked.measuredRpm, reason: 'fresh_measured_supply_voltage' };
}

function spinAxis(rotor: Object3D) {
  const value: unknown = rotor.userData.spinAxisLocal;
  if (Array.isArray(value) && value.length === 3 && value.every(v => typeof v === 'number' && Number.isFinite(v))) {
    const axis = new Vector3(value[0], value[1], value[2]);
    if (axis.lengthSq() > 0) return axis.normalize();
  }
  return new Vector3(0, 0, -1); // Legacy V17–V23 axis.
}

/** Update from the existing scene RAF; own only cloned RGB materials. */
export function createFanAnimator(root: Object3D) {
  const codes = ['FAN-01', 'FAN-02'];
  const rotors = codes.map(code => {
    const matches: Object3D[] = [];
    root.traverse(object => { if (object.name === `${code}_ROTOR`) matches.push(object); });
    return matches.length === 1 ? matches[0] : undefined;
  });
  const axes = rotors.map(rotor => rotor ? spinAxis(rotor) : new Vector3());
  const rgb: { code: string; mesh: Mesh; original: Material | Material[]; clones: Material[] }[] = [];
  root.traverse(object => {
    if (!(object instanceof Mesh) || object.userData.fanRgb !== true || !codes.includes(object.userData.fanAssetCode)) return;
    const original = object.material;
    const clones = (Array.isArray(original) ? original : [original]).map(material => {
      const clone = material.clone();
      if (clone instanceof MeshStandardMaterial) {
        const color: unknown = object.userData.fanRgbColor;
        if (Array.isArray(color) && color.length === 3 && color.every(v => typeof v === 'number' && Number.isFinite(v))) clone.emissive.setRGB(color[0], color[1], color[2]);
        clone.emissiveIntensity = 0;
      }
      return clone;
    });
    object.material = Array.isArray(original) ? clones : clones[0];
    rgb.push({ code: object.userData.fanAssetCode, mesh: object, original, clones });
  });
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
          rotor.rotateOnAxis(axes[index], Math.min(motion.measuredRpm!, 90) * 2 * Math.PI / 60 * dt);
        }
        const lighting = resolveFanLighting(context, code, nowMs);
        rgb.filter(entry => entry.code === code).forEach(entry => entry.clones.forEach(material => {
          if (material instanceof MeshStandardMaterial) {
            const requested = entry.mesh.userData.fanRgbOnIntensity;
            const intensity = typeof requested === 'number' && Number.isFinite(requested) ? Math.min(Math.max(requested, 0), 5) : 3;
            material.emissiveIntensity = lighting.state === 'on' ? intensity : 0;
          }
        }));
        return { ...motion, lighting } satisfies FanVisualFeedback;
      });
    },
    dispose() {
      if (disposed) return;
      disposed = true; rotors.length = 0;
      rgb.forEach(entry => { entry.mesh.material = entry.original; entry.clones.forEach(material => material.dispose()); });
      rgb.length = 0;
    },
  };
}
