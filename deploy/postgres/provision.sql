-- Run once *after migrations* in the managed PostgreSQL console as the project
-- database owner. The application runtime account is intentionally separate
-- from the migration/release identity.
-- Replace the bracketed values outside of source control. Do not paste a real
-- password into this file or commit it after editing.
--
-- The migration/release identity must own schema changes. The API gets only
-- DML privileges after migrations have completed.

CREATE ROLE ut_runtime LOGIN PASSWORD '[GENERATE_A_UNIQUE_SECRET]'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
  CONNECTION LIMIT 20;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE utility_tunnel TO ut_runtime;
GRANT USAGE ON SCHEMA public TO ut_runtime;

-- Revoke broad inherited grants before applying the operation-specific policy.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ut_runtime;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ut_runtime;

-- Authentication and RBAC reads; runtime can only record the last login time.
GRANT SELECT (id, email, display_name, password_hash, is_active) ON app_user TO ut_runtime;
GRANT UPDATE (last_login_at) ON app_user TO ut_runtime;
GRANT SELECT ON app_role, permission, user_role, role_permission TO ut_runtime;

-- Operational reads and the exact columns written by API routes.
GRANT SELECT ON zone, telemetry_reading, asset, alert, work_order, system_setting, audit_log TO ut_runtime;
GRANT UPDATE (operational_status) ON asset TO ut_runtime;
GRANT UPDATE (status, acknowledged_at, acknowledged_by, resolved_at, version) ON alert TO ut_runtime;
GRANT INSERT ON alert_event, work_order_event, report_export, audit_log TO ut_runtime;
GRANT SELECT (id, report_type, status, file_name, created_at, completed_at) ON report_export TO ut_runtime;
GRANT INSERT (code, source_alert_id, asset_id, title, description, priority, status, created_by, due_at) ON work_order TO ut_runtime;
GRANT UPDATE (status, assigned_to, completed_at, reviewed_at, reviewed_by, version) ON work_order TO ut_runtime;
GRANT UPDATE (value, version, updated_by) ON system_setting TO ut_runtime;

-- New tables must receive an explicit, reviewed grant in their release SQL.
-- Do not use ALTER DEFAULT PRIVILEGES here: it would silently widen API access.

-- Verify before recording the connection string in the deployment secret store.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolconnlimit
FROM pg_roles
WHERE rolname = 'ut_runtime';
