import { readFileSync } from 'node:fs';

const policy = readFileSync('deploy/postgres/provision.sql', 'utf8');
const normalized = policy.replace(/--.*$/gm, '').replace(/\s+/g, ' ').toLowerCase();
const required = [
  ['runtime role is non-superuser', /create role ut_runtime login password .* nosuperuser/],
  ['runtime role cannot create databases', /nocreatedb/],
  ['runtime role cannot create roles', /nocreaterole/],
  ['auth user read and create access', /grant select, insert on auth_user to ut_runtime/],
  ['auth user limited updates', /grant update \(last_login, is_active, password\) on auth_user to ut_runtime/],
  ['migration state read access', /grant select on django_migrations to ut_runtime/],
  ['profile read access', /grant select on operations_profile to ut_runtime/],
  ['profile lifecycle updates', /grant update \(display_name, role\) on operations_profile to ut_runtime/],
  ['token lifecycle access', /grant select, insert, delete on authtoken_token to ut_runtime/],
  ['user and token sequences', /grant usage, select on sequence auth_user_id_seq, authtoken_token_id_seq to ut_runtime/],
  ['placeholder guard', /replace the ut_runtime password placeholder before executing/],
];
const failures = required.filter(([, pattern]) => !pattern.test(normalized)).map(([label]) => label);
if (/grant all\s+on|alter default privileges/.test(normalized)) {
  failures.push('broad grants are forbidden');
}
if (!policy.includes("'[GENERATE_A_UNIQUE_SECRET]'")) {
  failures.push('password placeholder is missing');
}
if (failures.length) {
  console.error('PostgreSQL policy check failed:');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exitCode = 1;
} else {
  console.log(`PostgreSQL policy check passed: ${required.length} least-privilege rules verified.`);
}
