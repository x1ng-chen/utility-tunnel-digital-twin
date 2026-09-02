import { readFileSync } from 'node:fs';

const policy = readFileSync('deploy/postgres/provision.sql', 'utf8');
const normalized = policy.replace(/--.*$/gm, '').replace(/\s+/g, ' ').toLowerCase();
const requiredOperationalTables = [
  'operations_asset',
  'operations_alert',
  'operations_workorder',
  'operations_workorderevent',
  'operations_telemetry',
  'operations_threshold',
  'operations_auditlog',
  'operations_reportexport',
  'operations_registrationrequest',
  'operations_spatialfeature',
  'operations_hardwarebinding',
  'operations_twinmodelrelease',
];
const requiredInsertSequences = [
  'operations_profile_id_seq',
  'operations_asset_id_seq',
  'operations_alert_id_seq',
  'operations_telemetry_id_seq',
  'operations_workorder_id_seq',
  'operations_workorderevent_id_seq',
  'operations_auditlog_id_seq',
  'operations_reportexport_id_seq',
  'operations_registrationrequest_id_seq',
  'operations_spatialfeature_id_seq',
  'operations_hardwarebinding_id_seq',
  'operations_twinmodelrelease_id_seq',
];
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
  ['asset master-data insert access', /grant insert \(code, name, zone, asset_type, status, hardware_code, .*\) on operations_asset to ut_runtime/],
  ['asset lifecycle update access', /grant update \(code, name, zone, asset_type, status, hardware_code, .* last_seen_at, updated_at\) on operations_asset to ut_runtime/],
  ['automatic alert insert access', /grant insert \(code, asset_id, severity, category, status, title, detail, .*\) on operations_alert to ut_runtime/],
  ['alert rule update access', /grant update \(severity, status, detail, last_observed_value, acknowledged_at, acknowledged_by_id, resolved_at\) on operations_alert to ut_runtime/],
  ['telemetry insert access', /grant insert \(asset_id, event_id, metric_key, metric, value, unit, quality, recorded_at, ingested_at\) on operations_telemetry to ut_runtime/],
  ['work-order timeline insert access', /grant insert \(work_order_id, event_type, from_status, to_status, note, actor_id, created_at\) on operations_workorderevent to ut_runtime/],
  ['immutable report snapshot insert access', /grant insert \(report_type, status, file_name, idempotency_key, content, content_sha256, row_count, requested_by_id, created_at, completed_at\) on operations_reportexport to ut_runtime/],
  ['registration request insert access', /grant insert \(account, display_name, requested_role, setup_token_hash, setup_expires_at, password_set_at, status, review_note, reviewed_by_id, reviewed_at, created_user_id, created_at\) on operations_registrationrequest to ut_runtime/],
  ['registration request review access', /grant update \(status, review_note, reviewed_by_id, reviewed_at, created_user_id, setup_token_hash, setup_expires_at, password_set_at\) on operations_registrationrequest to ut_runtime/],
  ['spatial feature insert access', /grant insert \(code, name, layer_type, geometry, crs, source, source_reference, accuracy_m, captured_at, verified_at, status, description, version, created_at, updated_at\) on operations_spatialfeature to ut_runtime/],
  ['spatial feature limited updates', /grant update \(code, name, layer_type, geometry, crs, source, source_reference, accuracy_m, captured_at, verified_at, status, description, version, updated_at\) on operations_spatialfeature to ut_runtime/],
  ['hardware binding insert access', /grant insert \(asset_id, protocol, device_identifier, endpoint, expected_interval_seconds, status, last_heartbeat_at, version, created_at, updated_at\) on operations_hardwarebinding to ut_runtime/],
  ['hardware binding limited updates', /grant update \(asset_id, protocol, device_identifier, endpoint, expected_interval_seconds, status, last_heartbeat_at, version, updated_at\) on operations_hardwarebinding to ut_runtime/],
  ['twin model insert access', /grant insert \(version, model_file, original_name, sha256, size_bytes, notes, status, uploaded_by_id, activated_by_id, activated_at, created_at\) on operations_twinmodelrelease to ut_runtime/],
  ['twin model publication access', /grant update \(status, activated_by_id, activated_at\) on operations_twinmodelrelease to ut_runtime/],
  ['optional DatabaseCache least privilege', /if to_regclass\('public\.django_cache'\) is not null then grant select, insert, update, delete on django_cache to ut_runtime/],
  ['auth user sequence', /grant usage, select on sequence auth_user_id_seq to ut_runtime/],
  ['placeholder guard', /replace the ut_runtime password placeholder before executing/],
];
const failures = required.filter(([, pattern]) => !pattern.test(normalized)).map(([label]) => label);
for (const table of requiredOperationalTables) {
  if (!new RegExp(`grant select on [^;]*\\b${table}\\b[^;]* to ut_runtime`).test(normalized)) {
    failures.push(`runtime SELECT grant is missing for ${table}`);
  }
}
for (const sequence of requiredInsertSequences) {
  if (!new RegExp(`grant usage, select on sequence [^;]*\\b${sequence}\\b[^;]* to ut_runtime`).test(normalized)) {
    failures.push(`runtime sequence grant is missing for ${sequence}`);
  }
}
if (/grant all\s+on|alter default privileges/.test(normalized)) {
  failures.push('broad grants are forbidden');
}
if (/authtoken_token_id_seq/.test(normalized)) {
  failures.push('DRF token keys are strings; the nonexistent authtoken_token_id_seq must not be granted');
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
