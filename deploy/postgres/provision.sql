-- Run once after Django migrations in the managed PostgreSQL console as the
-- project database owner. Production must not run seed_demo; create the first
-- administrator through the controlled production-account process instead.
-- The application runtime account is intentionally separate from the
-- migration/release identity.
-- Replace the bracketed values outside of source control. Do not paste a real
-- password into this file or commit it after editing.
--
-- The migration/release identity must own schema changes. The Django API gets
-- only the DML privileges required by backend/operations/views.py after
-- migrations have completed. This file targets the Vue 3 + Django stack;
-- No legacy application schema is granted by this policy.

-- Replace the placeholder in this guard and in CREATE ROLE below before
-- executing the script. Leaving either occurrence unchanged aborts safely.
DO $$
BEGIN
  IF '[GENERATE_A_UNIQUE_SECRET]' LIKE '[%' THEN
    RAISE EXCEPTION 'Replace the ut_runtime password placeholder before executing provision.sql';
  END IF;
END
$$;

CREATE ROLE ut_runtime LOGIN PASSWORD '[GENERATE_A_UNIQUE_SECRET]'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
  CONNECTION LIMIT 20;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE utility_tunnel TO ut_runtime;
GRANT USAGE ON SCHEMA public TO ut_runtime;

-- Revoke broad inherited grants before applying the operation-specific policy.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ut_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ut_runtime;

-- Authentication and RBAC reads; the API may only mutate the user lifecycle
-- fields exposed by /api/admin/users/.
GRANT SELECT, INSERT ON auth_user TO ut_runtime;
GRANT UPDATE (last_login, is_active, password) ON auth_user TO ut_runtime;
GRANT SELECT ON django_migrations TO ut_runtime;
GRANT SELECT ON operations_profile TO ut_runtime;
GRANT INSERT (display_name, role, user_id) ON operations_profile TO ut_runtime;
GRANT UPDATE (display_name, role) ON operations_profile TO ut_runtime;
GRANT SELECT, INSERT, DELETE ON authtoken_token TO ut_runtime;

-- Operational reads and the exact columns written by the Django API routes.
GRANT SELECT ON operations_asset, operations_alert, operations_workorder,
  operations_workorderevent,
  operations_telemetry, operations_threshold, operations_auditlog,
  operations_reportexport, operations_registrationrequest,
  operations_spatialfeature, operations_hardwarebinding,
  operations_twinmodelrelease TO ut_runtime;
GRANT INSERT (code, name, zone, asset_type, status, hardware_code,
  integration_status, interface, capabilities, mesh, position, latitude,
  longitude, location_source, installation_note, is_active, version,
  last_seen_at, created_at, updated_at) ON operations_asset TO ut_runtime;
GRANT UPDATE (code, name, zone, asset_type, status, hardware_code,
  integration_status, interface, capabilities, mesh, position, latitude,
  longitude, location_source, installation_note, is_active, version,
  last_seen_at, updated_at) ON operations_asset TO ut_runtime;
GRANT INSERT (code, asset_id, severity, category, status, title, detail,
  rule_key, last_observed_value, opened_at, acknowledged_at,
  acknowledged_by_id, resolved_at, created_at) ON operations_alert TO ut_runtime;
GRANT UPDATE (severity, status, detail, last_observed_value,
  acknowledged_at, acknowledged_by_id, resolved_at)
  ON operations_alert TO ut_runtime;
GRANT INSERT (asset_id, event_id, metric_key, metric, value, unit, quality,
  recorded_at, ingested_at) ON operations_telemetry TO ut_runtime;
GRANT INSERT ON operations_workorder TO ut_runtime;
GRANT INSERT (work_order_id, event_type, from_status, to_status, note, actor_id, created_at)
  ON operations_workorderevent TO ut_runtime;
GRANT UPDATE (status, assignee_id, completed_at, reviewed_by_id, version, updated_at)
  ON operations_workorder TO ut_runtime;
GRANT UPDATE (warning, alarm, version, updated_at) ON operations_threshold TO ut_runtime;
GRANT INSERT ON operations_auditlog TO ut_runtime;
GRANT INSERT (report_type, status, file_name, idempotency_key, content,
  content_sha256, row_count, requested_by_id, created_at, completed_at)
  ON operations_reportexport TO ut_runtime;
GRANT INSERT (account, display_name, requested_role, setup_token_hash,
  setup_expires_at, password_set_at, status, review_note, reviewed_by_id,
  reviewed_at, created_user_id, created_at)
  ON operations_registrationrequest TO ut_runtime;
GRANT UPDATE (status, review_note, reviewed_by_id, reviewed_at, created_user_id,
  setup_token_hash, setup_expires_at, password_set_at)
  ON operations_registrationrequest TO ut_runtime;
GRANT INSERT (code, name, layer_type, geometry, crs, source, source_reference,
  accuracy_m, captured_at, verified_at, status, description, version, created_at,
  updated_at) ON operations_spatialfeature TO ut_runtime;
GRANT UPDATE (code, name, layer_type, geometry, crs, source, source_reference,
  accuracy_m, captured_at, verified_at, status, description, version, updated_at)
  ON operations_spatialfeature TO ut_runtime;
GRANT INSERT (asset_id, protocol, device_identifier, endpoint,
  expected_interval_seconds, status, last_heartbeat_at, version, created_at,
  updated_at) ON operations_hardwarebinding TO ut_runtime;
GRANT UPDATE (asset_id, protocol, device_identifier, endpoint,
  expected_interval_seconds, status, last_heartbeat_at, version, updated_at)
  ON operations_hardwarebinding TO ut_runtime;
GRANT INSERT (version, model_file, original_name, sha256, size_bytes,
  node_count, mesh_count, named_node_count, node_names,
  node_inventory_available, duplicate_node_names, missing_asset_codes,
  is_compatible, notes, status, uploaded_by_id, activated_by_id, activated_at,
  created_at)
  ON operations_twinmodelrelease TO ut_runtime;
GRANT UPDATE (status, missing_asset_codes, is_compatible, activated_by_id,
  activated_at)
  ON operations_twinmodelrelease TO ut_runtime;

-- BigAutoField-backed inserts need sequence usage, but the API must not be
-- able to alter sequence ownership or create new schema objects.
GRANT USAGE, SELECT ON SEQUENCE operations_profile_id_seq,
  operations_asset_id_seq, operations_alert_id_seq, operations_telemetry_id_seq,
  operations_workorder_id_seq, operations_workorderevent_id_seq, operations_auditlog_id_seq,
  operations_reportexport_id_seq, operations_registrationrequest_id_seq,
  operations_spatialfeature_id_seq, operations_hardwarebinding_id_seq,
  operations_twinmodelrelease_id_seq
  TO ut_runtime;
GRANT USAGE, SELECT ON SEQUENCE auth_user_id_seq TO ut_runtime;

-- DatabaseCache is optional. When DJANGO_CACHE_LOCATION points at the default
-- django_cache table, grant only the row operations required by Django. The
-- conditional keeps Redis/Memcached deployments valid when no cache table was
-- created. Deployments using a custom cache table must grant that exact table
-- explicitly in their release SQL.
DO $$
BEGIN
  IF to_regclass('public.django_cache') IS NOT NULL THEN
    GRANT SELECT, INSERT, UPDATE, DELETE ON django_cache TO ut_runtime;
  END IF;
END
$$;

-- New tables must receive an explicit, reviewed grant in their release SQL.
-- Do not use ALTER DEFAULT PRIVILEGES here: it would silently widen API access.

-- Verify before recording the connection string in the deployment secret store.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolconnlimit
FROM pg_roles
WHERE rolname = 'ut_runtime';
