import { existsSync, readFileSync } from 'node:fs';

const requirements = ['.dockerignore', 'deploy/containers/Dockerfile.api', 'deploy/containers/Dockerfile.web', 'deploy/containers/nginx.web.conf', 'deploy/containers/docker-compose.production.yml', 'deploy/containers/README.md', 'deploy/postgres/provision.sql'];
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
const combined = `${api}\n${web}\n${nginx}\n${compose}\n${grants}`;
const checks = [
  ['API uses a non-root runtime user', /USER utilitytunnel/],
  ['API exposes a health probe', /HEALTHCHECK[\s\S]*\/api\/health\//],
  ['API uses production Gunicorn', /gunicorn config\.wsgi:application/],
  ['web build is configured for relative API routing', /VITE_API_BASE_URL=\/api/],
  ['Nginx forwards the API route', /location \/api\/[\s\S]*proxy_pass http:\/\/api:8000\/api\//],
  ['Nginx provides SPA fallback', /try_files \$uri \$uri\/ \/index\.html/],
  ['Nginx supplies a restrictive browser content security policy', /Content-Security-Policy[\s\S]*default-src 'self';[\s\S]*object-src 'none';[\s\S]*script-src 'self'/],
  ['Nginx applies response headers to SPA and API responses', /add_header Cache-Control "no-store" always;[\s\S]*location \/ \{[\s\S]*try_files \$uri \$uri\/ \/index\.html;[\s\S]*\}/],
  ['Compose uses a read-only API filesystem', /api:[\s\S]*read_only: true/],
  ['Compose supervises application child processes', /api:[\s\S]*init: true/],
  ['Compose requires production secrets at runtime', /DJANGO_SECRET_KEY: \$\{DJANGO_SECRET_KEY:\?set-in-secret-store\}/],
  ['Compose keeps the API internal', /api:[\s\S]*expose:[\s\S]*"8000"/],
  ['Compose binds the web service to loopback only', /127\.0\.0\.1:8080:8080/],
  ['Compose probes the web service health endpoint', /web:[\s\S]*healthcheck:[\s\S]*\/healthz/],
  ['Compose persists validated twin model releases', /twin_model_media:\/app\/media[\s\S]*volumes:[\s\S]*twin_model_media:/],
  ['Nginx permits the governed GLB upload size', /client_max_body_size 34m/],
  ['PostgreSQL runtime role can read and publish twin releases', /operations_twinmodelrelease[\s\S]*GRANT UPDATE \(status, activated_by_id, activated_at\)/],
];
const failures = checks.filter(([, pattern]) => !pattern.test(combined)).map(([label]) => label);
if (/postgres(?:ql)?:\/\/[^$\s]*:[^$\s]*@/i.test(combined) || /BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY/.test(combined)) {
  failures.push('deployment artifacts contain credential-like material');
}
if (failures.length) {
  console.error('Deployment artifact check failed:');
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}
console.log(`Deployment artifact check passed: ${checks.length} production safeguards verified.`);
