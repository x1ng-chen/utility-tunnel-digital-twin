import { existsSync, readFileSync } from 'node:fs';

const requirements = ['.dockerignore', 'deploy/containers/Dockerfile.api', 'deploy/containers/Dockerfile.web', 'deploy/containers/nginx.web.conf', 'deploy/containers/docker-compose.production.yml', 'deploy/containers/README.md', 'deploy/postgres/provision.sql', 'deploy/postgres/backup-django.ps1', 'deploy/postgres/restore-verify-django.ps1'];
const missing = requirements.filter((file) => !existsSync(file));
if (missing.length) {
  console.error(`Deployment artifact check failed: missing ${missing.join(', ')}`);
  process.exit(1);
}

const api = readFileSync('deploy/containers/Dockerfile.api', 'utf8');
const web = readFileSync('deploy/containers/Dockerfile.web', 'utf8');
const nginx = readFileSync('deploy/containers/nginx.web.conf', 'utf8');
const compose = readFileSync('deploy/containers/docker-compose.production.yml', 'utf8');
const grants = readFileSync('deploy/postgres/provision.sql', 'utf8');
const backup = readFileSync('deploy/postgres/backup-django.ps1', 'utf8');
const restore = readFileSync('deploy/postgres/restore-verify-django.ps1', 'utf8');
const runbook = readFileSync('docs/deployment-runbook.md', 'utf8');
const containerReadme = readFileSync('deploy/containers/README.md', 'utf8');
const combined = `${api}\n${web}\n${nginx}\n${compose}\n${grants}\n${backup}\n${restore}`;
const checks = [
  ['API uses a non-root runtime user', /USER utilitytunnel/],
  ['API exposes a database-aware readiness probe', /HEALTHCHECK[\s\S]*\/api\/ready\//],
  ['API readiness probe presents an explicitly allowed host and secure scheme', /HEALTHCHECK[\s\S]*os\.environ\['DJANGO_ALLOWED_HOSTS'\][\s\S]*headers=\{'Host': host, 'X-Forwarded-Proto': 'https'\}/],
  ['API serves HTTP and WebSocket using ASGI', /exec daphne .*config\.asgi:application/],
  ['Nginx upgrades WebSocket connections', /location \/ws\/[\s\S]*proxy_set_header Upgrade \$http_upgrade;[\s\S]*proxy_set_header Connection \$connection_upgrade;/],
  ['Nginx explicitly allows same-host secure WebSocket', /connect-src 'self' https: wss:\/\/\$http_host;/],
  ['web build is configured for relative API routing', /VITE_API_BASE_URL=\/api/],
  ['Nginx forwards the API route', /location \/api\/[\s\S]*proxy_pass http:\/\/api:8000\/api\//],
  ['Nginx creates a fixed HTTPS scheme for Django', /location \/api\/[\s\S]*proxy_set_header X-Forwarded-Proto https;/],
  ['Nginx provides SPA fallback', /try_files \$uri \$uri\/ \/index\.html/],
  ['Nginx supplies a restrictive browser content security policy', /Content-Security-Policy[\s\S]*default-src 'self';[\s\S]*object-src 'none';[\s\S]*script-src 'self'/],
  ['Nginx applies response headers to SPA and API responses', /add_header Cache-Control "no-store" always;[\s\S]*location \/ \{[\s\S]*try_files \$uri \$uri\/ \/index\.html;[\s\S]*\}/],
  ['Compose uses a read-only API filesystem', /api:[\s\S]*read_only: true/],
  ['Compose supervises application child processes', /api:[\s\S]*init: true/],
  ['Compose requires production secrets at runtime', /DJANGO_SECRET_KEY: \$\{DJANGO_SECRET_KEY:\?set-in-secret-store\}/],
  ['Compose keeps forwarded client-address headers untrusted', /api:[\s\S]*DJANGO_TRUST_PROXY_HEADERS: "false"/],
  ['Compose requires a dedicated monitor credential', /CONNECTIVITY_MONITOR_TOKEN: \$\{CONNECTIVITY_MONITOR_TOKEN:\?set-monitor-token-in-secret-store\}/],
  ['Connectivity monitor calls the API-owned reconciliation route', /connectivity-monitor:[\s\S]*CONNECTIVITY_MONITOR_URL: http:\/\/api:8000\/api\/internal\/connectivity\/reconcile\/[\s\S]*run_connectivity_monitor/],
  ['Compose keeps the API internal', /api:[\s\S]*expose:[\s\S]*"8000"/],
  ['Compose binds the web service to loopback only', /127\.0\.0\.1:8080:8080/],
  ['Compose probes the web service health endpoint', /web:[\s\S]*healthcheck:[\s\S]*\/healthz/],
  ['Compose persists validated twin model releases', /twin_model_media:\/app\/media[\s\S]*volumes:[\s\S]*twin_model_media:/],
  ['Nginx permits the governed GLB upload size', /client_max_body_size 34m/],
  ['PostgreSQL runtime role can read and publish validated twin releases', /operations_twinmodelrelease[\s\S]*GRANT UPDATE \(status, missing_asset_codes, is_compatible, activated_by_id,[\s\S]*activated_at\)/],
  ['Database backups use a portable custom format and SHA-256 sidecar', /pg_dump --format=custom --no-owner --no-privileges[\s\S]*Get-FileHash -Algorithm SHA256/],
  ['Database restores require explicit destructive-action confirmation', /if \(-not \$ConfirmRestore\)[\s\S]*Restore is destructive/],
  ['Database restores verify checksums and application tables', /Backup SHA-256 checksum[\s\S]*operations_asset[\s\S]*django_migrations/],
  ['Production runbook pins PostgreSQL 16', /PostgreSQL 16/, runbook],
  ['Production runbook documents that current GIS storage does not require PostGIS', /不依赖 PostGIS/, runbook],
  ['Production runbook forbids production demo seeding', /生产环境严禁执行 `python manage\.py seed_demo`/, runbook],
  ['Container release guide forbids production demo seeding', /生产环境严禁执行 `seed_demo`/, containerReadme],
  ['Runtime-role provision script rejects production demo seeding', /Production must not run seed_demo/, grants],
  ['Production runbook documents the monitor secret boundary', /CONNECTIVITY_MONITOR_TOKEN/, runbook],
];
const failures = checks.filter(([, pattern, source = combined]) => !pattern.test(source)).map(([label]) => label);
const secureSchemeHeaders = nginx.match(/proxy_set_header X-Forwarded-Proto https;/g) || [];
if (secureSchemeHeaders.length !== 2) {
  failures.push('Nginx must create exactly one fixed HTTPS scheme header for each API and WebSocket proxy route');
}
if (/proxy_set_header X-Forwarded-Proto\s+\$(?:scheme|http_x_forwarded_proto)\s*;/.test(nginx)) {
  failures.push('Nginx must not relay an unverified X-Forwarded-Proto header to Django');
}
if (!/location = \/api\/internal\/connectivity\/reconcile\/ \{[\s\S]*return 404;/.test(nginx)) {
  failures.push('public Nginx must reject the token-bearing connectivity monitor route');
}
if (/PostgreSQL\s+18/.test(`${runbook}\n${containerReadme}`)) {
  failures.push('production deployment documentation must not reference PostgreSQL 18');
}
if (/postgres(?:ql)?:\/\/[^$\s]*:[^$\s]*@/i.test(combined) || /BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY/.test(combined)) {
  failures.push('deployment artifacts contain credential-like material');
}
if (failures.length) {
  console.error('Deployment artifact check failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log(`Deployment artifact check passed: ${checks.length} production safeguards verified.`);
