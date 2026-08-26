const baseUrl = process.env.API_BASE_URL ?? 'http://127.0.0.1:8080';
const email = process.env.SEED_ADMIN_EMAIL;
const password = process.env.SEED_ADMIN_PASSWORD;

if (!email || !password) throw new Error('SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD are required.');

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, options);
  const body = await response.json();
  if (!response.ok) throw new Error(`${options.method ?? 'GET'} ${path} failed: ${response.status} ${JSON.stringify(body)}`);
  return body;
}

const health = await request('/v1/health');
if (health.status !== 'ok') throw new Error('Health endpoint did not return ok.');
const ready = await request('/v1/ready');
if (ready.status !== 'ok') throw new Error('Readiness endpoint did not return ok.');

const login = await request('/v1/auth/login', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email, password }),
});

const headers = { authorization: `Bearer ${login.accessToken}`, 'content-type': 'application/json' };
const [assets, alerts, audit, thresholds, overview] = await Promise.all([
  request('/v1/assets', { headers }),
  request('/v1/alerts', { headers }),
  request('/v1/audit', { headers }),
  request('/v1/thresholds', { headers }),
  request('/v1/dashboard/overview', { headers }),
]);

if (!assets.items.length || !alerts.items.length || !audit.items.length) throw new Error('Expected seed data was not returned by protected endpoints.');
if (!thresholds.items.length) throw new Error('Expected seed thresholds to be returned by the protected endpoint.');
if (!overview.latestTelemetry.length) throw new Error('Expected dashboard telemetry to be returned.');

const temperatureThreshold = thresholds.items.find((threshold) => threshold.key === 'temperature');
if (!temperatureThreshold) throw new Error('Expected the temperature threshold seed data.');
const updatedThreshold = await request('/v1/thresholds/temperature', {
  method: 'PUT',
  headers,
  body: JSON.stringify({ ...temperatureThreshold, warning: 27, alarm: 31 }),
});
if (updatedThreshold.version !== temperatureThreshold.version + 1 || updatedThreshold.warning !== 27 || updatedThreshold.alarm !== 31) {
  throw new Error('Expected threshold update and version increment.');
}

const manualOrder = await request('/v1/work-orders', {
  method: 'POST',
  headers,
  body: JSON.stringify({ assetId: assets.items[0].id, title: 'Automated manual work order', priority: 'low' }),
});
if (!manualOrder.id) throw new Error('Expected a manual work order to be created.');

const reportExport = await request('/v1/report-exports', {
  method: 'POST',
  headers,
  body: JSON.stringify({ report: 'daily' }),
});
if (reportExport.status !== 'completed') throw new Error('Expected report export metadata to be completed.');

const openAlert = alerts.items.find((alert) => alert.status === 'open');
if (!openAlert) throw new Error('Expected an open seed alert.');

await request(`/v1/alerts/${openAlert.id}/acknowledge`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ note: 'Automated verification acknowledgement.' }),
});

const workOrder = await request(`/v1/alerts/${openAlert.id}/work-orders`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ title: 'Automated verification work order', priority: 'normal' }),
});

const duplicate = await fetch(`${baseUrl}/v1/alerts/${openAlert.id}/work-orders`, {
  method: 'POST',
  headers,
  body: JSON.stringify({ title: 'Duplicate work order', priority: 'normal' }),
});
if (duplicate.status !== 409) throw new Error(`Expected duplicate work order to be rejected with 409, received ${duplicate.status}.`);

for (const to of ['assigned', 'in_progress', 'pending_review', 'completed']) {
  await request(`/v1/work-orders/${workOrder.id}/transition`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ to, note: `Automated verification: ${to}` }),
  });
}

const finalAudit = await request('/v1/audit?pageSize=100', { headers });
if (!finalAudit.items.some((entry) => entry.action === 'work_order.transition')) {
  throw new Error('Expected work order transition in the audit trail.');
}
if (!finalAudit.items.some((entry) => entry.action === 'alert.resolve_from_work_order')) {
  throw new Error('Expected linked alert resolution in the audit trail.');
}
if (!finalAudit.items.some((entry) => entry.action === 'work_order.create_manual')) {
  throw new Error('Expected manual work order creation in the audit trail.');
}
if (!finalAudit.items.some((entry) => entry.action === 'setting.threshold.update')) {
  throw new Error('Expected threshold update in the audit trail.');
}
if (!finalAudit.items.some((entry) => entry.action === 'report.export')) {
  throw new Error('Expected report export in the audit trail.');
}

const finalAlerts = await request('/v1/alerts?pageSize=100', { headers });
if (finalAlerts.items.find((alert) => alert.id === openAlert.id)?.status !== 'resolved') {
  throw new Error('Expected the completed work order to resolve its source alert.');
}

const finalAssets = await request('/v1/assets?pageSize=100', { headers });
const sourceAsset = finalAssets.items.find((asset) => asset.code === openAlert.asset_code);
if (sourceAsset?.operational_status !== 'normal') {
  throw new Error('Expected the source asset to return to normal after the final active alert was resolved.');
}

console.log('API smoke test passed: database migration, authentication, configuration, export, manual work orders, alert-to-work-order closure and audit trail.');
