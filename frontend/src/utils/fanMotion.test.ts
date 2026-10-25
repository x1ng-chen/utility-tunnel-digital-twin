import { Group } from 'three';
import { describe, expect, it } from 'vitest';
import { createFanAnimator, resolveFanMotion, type FanFeedbackContext } from './fanMotion';
import type { HardwareBinding, Telemetry } from '../types';
import { readFileSync } from 'node:fs';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const now = Date.parse('2026-10-25T04:00:00Z');
const reading = (code = 'FAN-01', overrides: Partial<Telemetry> = {}): Telemetry => ({
  id: 1, assetCode: code, metricKey: 'rotational.speed', metric: '转速', value: 720, unit: 'rpm',
  quality: 'good', recordedAt: new Date(now).toISOString(), ...overrides,
});
const binding = (code: string): HardwareBinding => ({ id: 1, assetCode: code, protocol: 'mqtt',
  deviceIdentifier: code, endpoint: 'test', expectedIntervalSeconds: 2, status: 'connected', connectivity: 'online',
  lastHeartbeatAt: new Date(now).toISOString(), heartbeatAgeSeconds: 0, heartbeatDueAt: null, version: 1 });
const context = (telemetry = [reading()]): FanFeedbackContext => ({
  source: 'api', offline: false, telemetry, bindings: [binding('FAN-01'), binding('FAN-02')],
});

describe('per-fan measured motion', () => {
  it('separates fan identity and zero-speed feedback', () => {
    expect(resolveFanMotion(context(), 'FAN-01', now)).toMatchObject({ state: 'running', measuredRpm: 720 });
    expect(resolveFanMotion(context(), 'FAN-02', now).state).toBe('unknown');
    expect(resolveFanMotion(context([reading('FAN-01', { value: 0 })]), 'FAN-01', now).state).toBe('stopped');
  });

  it.each([
    { quality: 'bad' }, { quality: 'suspect' }, { quality: 'missing' }, { unit: 'mA' },
    { value: -1 }, { value: Number.NaN }, { recordedAt: 'invalid' },
    { recordedAt: new Date(now + 1).toISOString() },
    { recordedAt: new Date(now - 2001).toISOString() }, { eventId: 'demo:rotor' },
  ] as Partial<Telemetry>[])('freezes invalid feedback %j', (overrides) => {
    expect(resolveFanMotion(context([reading('FAN-01', overrides)]), 'FAN-01', now).state).toBe('unknown');
  });

  it('does not revive an old good sample after a newer bad sample', () => {
    const data = [reading('FAN-01', { recordedAt: new Date(now - 100).toISOString() }), reading('FAN-01', { quality: 'bad' })];
    expect(resolveFanMotion(context(data), 'FAN-01', now).state).toBe('unknown');
  });

  it('rejects conflicting newest values and invalid timestamp history', () => {
    expect(resolveFanMotion(context([reading(), reading('FAN-01', { value: 0 })]), 'FAN-01', now).state).toBe('unknown');
    expect(resolveFanMotion(context([reading(), reading('FAN-01', { recordedAt: 'bad' })]), 'FAN-01', now).state).toBe('unknown');
  });

  it('expires without new polling and never animates demo or offline state', () => {
    expect(resolveFanMotion(context(), 'FAN-01', now + 2001).state).toBe('unknown');
    for (const extra of [{ source: 'demo' as const }, { offline: true }, { bindings: [] }]) {
      expect(resolveFanMotion({ ...context(), ...extra }, 'FAN-01', now).state).toBe('unknown');
    }
    const offline = context(); offline.bindings[0].connectivity = 'offline';
    expect(resolveFanMotion(offline, 'FAN-01', now).state).toBe('unknown');
  });

  it('ignores command intent and PWM metrics as motion evidence', () => {
    expect(resolveFanMotion(context([reading('FAN-01', { metricKey: 'control.fan_pwm', value: 100 })]), 'FAN-01', now).state).toBe('unknown');
  });

  it('moves only the matching rotor, preserves phase on stop and releases on dispose', () => {
    const root = new Group();
    const housing1 = new Group(); housing1.name = 'FAN-01'; root.add(housing1);
    const rotor1 = new Group(); rotor1.name = 'FAN-01_ROTOR'; housing1.add(rotor1);
    const rotor2 = new Group(); rotor2.name = 'FAN-02_ROTOR'; root.add(rotor2);
    const animator = createFanAnimator(root);
    animator.update(context(), now, .1);
    expect(rotor1.quaternion.z).not.toBe(0);
    expect(rotor2.quaternion.z).toBe(0);
    expect(housing1.quaternion.z).toBe(0);
    const stopped = rotor1.quaternion.clone();
    animator.update(context([reading('FAN-01', { value: 0 })]), now, .1);
    expect(rotor1.quaternion.equals(stopped)).toBe(true);
    // A stop command has no input here; a fresh positive RPM continues the coast.
    animator.update(context(), now, .1);
    expect(rotor1.quaternion.equals(stopped)).toBe(false);
    animator.dispose();
    expect(animator.update(context(), now, .1)).toEqual([]);
  });

  it('freezes older models and duplicate rotor names', () => {
    const root = new Group();
    expect(createFanAnimator(root).update(context(), now, .1).every(s => s.state === 'unknown')).toBe(true);
    for (let i = 0; i < 2; i++) { const rotor = new Group(); rotor.name = 'FAN-01_ROTOR'; root.add(rotor); }
    expect(createFanAnimator(root).update(context(), now, .1)[0].reason).toBe('rotor_unavailable');
  });

  it.skipIf(!process.env.FAN_MODEL_GLB)('drives independent rotors after loading an actual supplied GLB', async () => {
    const raw = readFileSync(process.env.FAN_MODEL_GLB!);
    const gltf = await new GLTFLoader().parseAsync(Uint8Array.from(raw).buffer, '');
    const first = gltf.scene.getObjectByName('FAN-01_ROTOR')!;
    const second = gltf.scene.getObjectByName('FAN-02_ROTOR')!;
    const housing = gltf.scene.getObjectByName('FAN-01')!;
    expect(first).toBeDefined(); expect(second).toBeDefined(); expect(housing).toBeDefined();
    const before = [first.quaternion.clone(), second.quaternion.clone(), housing.quaternion.clone()];
    const animator = createFanAnimator(gltf.scene);
    const states = animator.update(context(), now, .1);
    expect(states[0].state).toBe('running'); expect(states[1].state).toBe('unknown');
    expect(first.quaternion.equals(before[0])).toBe(false);
    expect(second.quaternion.equals(before[1])).toBe(true);
    expect(housing.quaternion.equals(before[2])).toBe(true);
    animator.dispose();
  });
});
