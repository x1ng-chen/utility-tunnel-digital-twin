/** Integration reference only. Not imported by the running frontend. */
export function resolveFanMotion(readings, assetCode, { nowMs, maxAgeMs, source, offline = false, allowedFutureSkewMs = 0 }) {
  if (!Number.isFinite(maxAgeMs) || maxAgeMs <= 0) throw new Error('Configure maxAgeMs from the real telemetry cadence');
  if (!Number.isFinite(allowedFutureSkewMs) || allowedFutureSkewMs < 0) throw new Error('Invalid clock skew tolerance');
  const unknown = (reason) => ({ state: 'unknown', measuredRpm: null, reason });
  if (!Number.isFinite(nowMs)) return unknown('invalid_clock');
  if (source !== 'api') return unknown('non_live_source');
  if (offline) return unknown('offline');
  const candidates = readings.filter((r) => r.assetCode === assetCode && r.metricKey === 'rotational.speed');
  if (!candidates.length) return unknown('missing');
  // An unorderable timestamp must never revive an older good reading.
  if (candidates.some((r) => !Number.isFinite(Date.parse(r.recordedAt)))) return unknown('invalid_timestamp');
  const newestTime = Math.max(...candidates.map((r) => Date.parse(r.recordedAt)));
  const latest = candidates.filter((r) => Date.parse(r.recordedAt) === newestTime);
  const reading = latest[0];
  if (latest.some((r) => !Object.is(r.value, reading.value) || r.quality !== reading.quality || r.unit !== reading.unit)) return unknown('conflicting_latest_readings');
  const age = nowMs - newestTime;
  if (age < -allowedFutureSkewMs) return unknown('future_timestamp');
  if (age > maxAgeMs) return unknown('stale');
  if (reading.quality !== 'good') return unknown('quality');
  if (typeof reading.unit !== 'string' || reading.unit.trim().toLowerCase() !== 'rpm') return unknown('unit');
  if (typeof reading.value !== 'number' || !Number.isFinite(reading.value) || reading.value < 0) return unknown('invalid_rpm');
  return { state: reading.value > 0 ? 'running' : 'stopped', measuredRpm: reading.value, reason: 'fresh_measured_rpm' };
}

export function createFanAnimator(root, contract, { maxAgeMs, visualRpmCap = 90, allowedFutureSkewMs = 0 }) {
  if (!Number.isFinite(maxAgeMs) || maxAgeMs <= 0) throw new Error('maxAgeMs is required');
  if (!Number.isFinite(visualRpmCap) || visualRpmCap <= 0) throw new Error('Invalid visual RPM cap');
  const bindings = contract.fans.map((fan) => {
    const matches = [];
    root.traverse((o) => { if (o.name === fan.rotorNode || o.userData?.name === fan.rotorNode) matches.push(o); });
    if (matches.length !== 1) throw new Error(`Expected exactly one rotor: ${fan.rotorNode}`);
    const rotor = matches[0];
    const axis = rotor.position.clone().fromArray(fan.axisGltfLocal).normalize();
    return { fan, rotor, axis };
  });
  let disposed = false;
  return {
    // Call once per rendered frame with elapsed seconds; read telemetry each time
    // so it expires even when no new payload arrives. Never start another RAF.
    update(readings, { nowMs, source, offline = false, offlineAssetCodes = [] }, deltaSeconds) {
      if (disposed) return [];
      const dt = Number.isFinite(deltaSeconds) ? Math.min(Math.max(deltaSeconds, 0), .1) : 0;
      return bindings.map(({ fan, rotor, axis }) => {
        const motion = resolveFanMotion(readings, fan.assetCode, { nowMs, source, offline: offline || offlineAssetCodes.includes(fan.assetCode), maxAgeMs, allowedFutureSkewMs });
        const visualRpm = motion.state === 'running' ? Math.min(motion.measuredRpm, visualRpmCap) : 0;
        if (visualRpm > 0 && dt > 0) rotor.rotateOnAxis(axis, visualRpm * 2 * Math.PI / 60 * dt);
        return { assetCode: fan.assetCode, ...motion, visualRpm, visualSpeedIsIllustrative: true };
      });
    },
    // Dispose on model replacement/unmount; geometry/material lifecycle stays
    // with TwinScene. Stop/freeze preserves phase and does not reset the blades.
    dispose() { disposed = true; bindings.length = 0; },
  };
}
