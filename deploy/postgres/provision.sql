-- Run once in the managed PostgreSQL console as the project database owner.
-- Replace the bracketed values outside of source control. Do not paste a real
-- password into this file or commit it after editing.
--
-- The migration/release identity must own schema changes. The API gets only
-- DML privileges after migrations have completed.

CREATE ROLE ut_runtime LOGIN PASSWORD '[GENERATE_A_UNIQUE_SECRET]'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION
  CONNECTION LIMIT 20;

GRANT CONNECT ON DATABASE utility_tunnel TO ut_runtime;
GRANT USAGE ON SCHEMA public TO ut_runtime;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO ut_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ut_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO ut_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ut_runtime;

-- Verify before recording the connection string in the deployment secret store.
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolconnlimit
FROM pg_roles
WHERE rolname = 'ut_runtime';
