-- V007 - Grants
--
-- Consumers read analytics. They do not read staging, and they do not read
-- treasury directly - not to hide anything, but because analytics is the only
-- layer where the source traps are already excluded. A consumer who queries
-- treasury.observation unfiltered can pick up BC_30YEARDISPLAY placeholder
-- rows; one who queries analytics cannot.
--
-- meta is readable: lineage is not a secret, and "where did this number come
-- from" should be answerable without elevated rights.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gateway_readonly') THEN
        CREATE ROLE gateway_readonly NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA analytics, meta, treasury TO gateway_readonly;

GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO gateway_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA meta       TO gateway_readonly;

-- Reference data is safe to read directly; the fact tables are not, for the
-- reason above.
GRANT SELECT ON treasury.dataset, treasury.series TO gateway_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA analytics
    GRANT SELECT ON TABLES TO gateway_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA meta
    GRANT SELECT ON TABLES TO gateway_readonly;
