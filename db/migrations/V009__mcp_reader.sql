-- V009 - The MCP server's database identity
--
-- This role is the real security boundary of the whole MCP layer. Tool
-- annotations like readOnlyHint are advisory - the spec explicitly tells
-- clients to treat them as untrusted. Privileges are not advisory.
--
-- Design: mcp_reader can SELECT from analytics views and demo tables, and
-- NOTHING else. It cannot write anywhere, and it cannot reach treasury.* at
-- all.
--
-- The reason revoking treasury.* still leaves the analytics views working is
-- that PostgreSQL views execute with the VIEW OWNER's privileges unless
-- security_invoker is set. It is not set here (verified), so mcp_reader reads
-- curated data through the views without ever holding a privilege on the base
-- tables. That is what stops a defect in the MCP server from reaching the
-- placeholder rows, the raw staging tables, or anything else uncurated.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_reader') THEN
        -- No password here: the loader/migrator connects as the owner, and the
        -- MCP server's credential is set from the environment by
        -- V009's companion step in .env. A password set in a migration would
        -- end up committed to git.
        CREATE ROLE mcp_reader
            LOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOREPLICATION
            NOBYPASSRLS
            CONNECTION LIMIT 5;
    END IF;
END
$$;

COMMENT ON ROLE mcp_reader IS
    'Database identity for market-risk-data-mcp. SELECT on analytics + demo '
    'only. Cannot write anything. Cannot reach treasury.* base tables.';

-- Read paths ----------------------------------------------------------------

GRANT CONNECT ON DATABASE gateway TO mcp_reader;

GRANT USAGE  ON SCHEMA analytics TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO mcp_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO mcp_reader;

GRANT USAGE  ON SCHEMA demo TO mcp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA demo TO mcp_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA demo GRANT SELECT ON TABLES TO mcp_reader;

-- meta is readable so `explain_number` can return provenance. Lineage is not
-- a secret; being unable to answer "where did this number come from" is worse
-- than exposing a checksum.
GRANT USAGE  ON SCHEMA meta TO mcp_reader;
GRANT SELECT ON meta.source_file TO mcp_reader;

-- Closed paths --------------------------------------------------------------
-- Explicit, even where the default would already deny. A future GRANT ... ON
-- ALL TABLES issued carelessly against these schemas should have to contend
-- with a REVOKE that is visibly on the record.

REVOKE ALL ON SCHEMA treasury FROM mcp_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA treasury FROM mcp_reader;
REVOKE ALL ON SCHEMA staging  FROM mcp_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA staging  FROM mcp_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA meta FROM mcp_reader;
GRANT  SELECT ON meta.source_file TO mcp_reader;   -- re-grant the one exception

-- Session limits ------------------------------------------------------------
-- Role-scoped rather than global: a runaway MCP query must not be able to
-- affect the loader or an analyst's psql session.

ALTER ROLE mcp_reader IN DATABASE gateway SET default_transaction_read_only = on;
ALTER ROLE mcp_reader IN DATABASE gateway SET statement_timeout = '5s';
ALTER ROLE mcp_reader IN DATABASE gateway SET lock_timeout = '1s';
ALTER ROLE mcp_reader IN DATABASE gateway SET idle_in_transaction_session_timeout = '10s';
