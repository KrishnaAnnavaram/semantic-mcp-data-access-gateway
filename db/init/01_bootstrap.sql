-- Runs ONCE, on the first start of an empty data volume
-- (docker-entrypoint-initdb.d). It must stay small and boring: anything that
-- belongs to the data model belongs in db/migrations, which is re-runnable and
-- version-tracked. Editing this file has no effect on an existing volume.

-- Session defaults that make the database behave predictably for a
-- market-risk workload regardless of the client's locale. Observation dates
-- are calendar dates with no timezone, but audit timestamps are timestamptz
-- and must not be rendered in whatever zone the client happens to sit in.
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO %L',
                   current_database(), 'UTC');
    EXECUTE format('ALTER DATABASE %I SET datestyle TO %L',
                   current_database(), 'ISO, YMD');
END
$$;

-- A read-only role for consumers (dashboards, the future MCP gateway, an
-- analyst with psql). It owns nothing and creates nothing; per-schema grants
-- are issued by V007__grants.sql so they stay with the objects they describe.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gateway_readonly') THEN
        CREATE ROLE gateway_readonly NOLOGIN;
    END IF;
END
$$;
