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

const login = await request('/v1/auth/login', {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ email, password }),
});

const headers = { authorization: `Bearer ${login.accessToken}`, 'content-type': 'application/json' };
const [assets, alerts, audit] = await Promise.all([
  request('/v1/assets', { headers }),
  request('/v1/alerts', { headers }),
  request('/v1/audit', { headers }),
]);

if (!assets.items.length || !alerts.items.length || !audit.items.length) throw new Error('Expected seed data was not returned by protected endpoints.');

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

console.log('API smoke test passed: database migration, authentication, alert-to-work-order closure and audit trail.');
