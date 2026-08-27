-- Run once *after Django migrations and seed_demo* in the managed PostgreSQL
-- console as the project database owner. The application runtime account is
-- intentionally separate from the migration/release identity.
-- Replace the bracketed values outside of source control. Do not paste a real
-- password into this file or commit it after editing.
--
-- The migration/release identity must own schema changes. The Django API gets
-- only the DML privileges required by backend/operations/views.py after
-- migrations have completed. This file targets the Vue 3 + Django stack;
-- the legacy services/api schema is not granted by this policy.

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
  operations_telemetry, operations_threshold, operations_auditlog,
  operations_reportexport TO ut_runtime;
GRANT UPDATE (status, updated_at) ON operations_asset TO ut_runtime;
GRANT UPDATE (status, acknowledged_at, acknowledged_by_id, resolved_at)
  ON operations_alert TO ut_runtime;
GRANT INSERT ON operations_workorder TO ut_runtime;
GRANT UPDATE (status, assignee_id, completed_at, reviewed_by_id, version, updated_at)
  ON operations_workorder TO ut_runtime;
GRANT UPDATE (warning, alarm, version, updated_at) ON operations_threshold TO ut_runtime;
GRANT INSERT ON operations_auditlog, operations_reportexport TO ut_runtime;

-- BigAutoField-backed inserts need sequence usage, but the API must not be
-- able to alter sequence ownership or create new schema objects.
GRANT USAGE, SELECT ON SEQUENCE operations_profile_id_seq,
  operations_workorder_id_seq, operations_auditlog_id_seq,
  operations_reportexport_id_seq TO ut_runtime;
GRANT USAGE, SELECT ON SEQUENCE auth_user_id_seq, authtoken_token_id_seq TO ut_runtime;

-- New tables must receive an explicit, reviewed grant in their release SQL.
-- Do not use ALTER DEFAULT PRIVILEGES here: it would silently widen API access.

-- Verify before recording the connection string in the deployment secret store.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolconnlimit
FROM pg_roles
WHERE rolname = 'ut_runtime';
