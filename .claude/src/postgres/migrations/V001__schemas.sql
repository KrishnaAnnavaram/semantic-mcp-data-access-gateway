-- V001 - Schemas
--
-- Four layers, each with one job. Data only ever moves downward:
--
--   staging  ->  treasury  ->  analytics
--      ^            ^
--      +---- meta ---+   (lineage and audit, written at every step)
--
-- The separation exists so that "what Treasury published" and "what we
-- modelled" are never the same object. When a number looks wrong, staging
-- settles the argument.

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS treasury;
CREATE SCHEMA IF NOT EXISTS analytics;

COMMENT ON SCHEMA meta IS
    'Lineage and audit. Which file, which checksum, which run, which row count. '
    'Every fact in treasury traces back to a row here.';

COMMENT ON SCHEMA staging IS
    'Landing zone. One table per processed CSV, column-for-column, using '
    'Treasury''s own column names. Truncated and reloaded on every run. '
    'Never queried by applications - it is the arbiter of record, not a model.';

COMMENT ON SCHEMA treasury IS
    'Core model. Datasets, series and observations, normalised so that a new '
    'maturity is a row rather than a schema change. Rates carry their quoting '
    'basis so that discount rates can never be silently mixed with par yields.';

COMMENT ON SCHEMA analytics IS
    'Read layer. Views only - no storage. This is what a consumer should query; '
    'it is where the source traps (placeholder zeros, display duplicates) are '
    'already excluded.';
