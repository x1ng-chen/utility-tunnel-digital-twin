/** Explicit subscriptions only: never subscribe to a wildcard command/asset tree. */
export function createTelemetryRoutes(deviceIds = 'CTRL-01') {
  const ids = deviceIds.split(',').map(id => id.trim());
  if (!ids.length || ids.length > 4 || ids.some(id => !/^[a-z0-9-]{1,64}$/i.test(id)) || new Set(ids).size !== ids.length) {
    throw new Error('LOCAL_DEVICE_IDS must contain 1-4 distinct device identifiers, without wildcards.');
  }
  const byTopic = new Map(ids.map(id => [`ut/v1/${id}/telemetry`, id]));
  return { topics: [...byTopic.keys()], deviceForTopic: topic => byTopic.get(topic) ?? null };
}
