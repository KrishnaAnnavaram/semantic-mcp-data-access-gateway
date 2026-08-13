-- V012 - Dataset catalogue for the MCP layer
--
-- Added because the privilege boundary did its job: `list_datasets` was written
-- against treasury.dataset and mcp_reader was refused. That is the intended
-- behaviour - the server should not be able to reach base tables even by
-- accident - so the fix is a curated view, not a wider grant.
--
-- The caveat column is the point of this view. It carries the market-risk
-- warning that belongs with each dataset ("CLOSE columns are DISCOUNT rates",
-- "BC_30YEARDISPLAY is a placeholder") into every response, so the warning
-- cannot be separated from the data it applies to.

CREATE OR REPLACE VIEW analytics.v_mcp_dataset AS
SELECT d.data_key,
       d.title,
       d.shape::text                     AS shape,
       d.documented_first_year,
       d.description,
       d.caveat,
       COALESCE(c.series_count, 0)       AS series_count,
       o.first_observation,
       o.last_observation,
       COALESCE(o.observation_count, 0)  AS observation_count
FROM treasury.dataset d
LEFT JOIN (
    SELECT data_key, count(*) AS series_count
    FROM analytics.v_mcp_series_catalogue
    GROUP BY data_key
) c ON c.data_key = d.data_key
LEFT JOIN (
    SELECT data_key,
           min(observation_date) AS first_observation,
           max(observation_date) AS last_observation,
           count(*)              AS observation_count
    FROM analytics.v_mcp_observation
    GROUP BY data_key
) o ON o.data_key = d.data_key;

COMMENT ON VIEW analytics.v_mcp_dataset IS
    'Dataset catalogue for the MCP layer, with the market-risk caveat attached. '
    'Counts reflect what is actually retrievable, so a dataset whose series are '
    'partly excluded reports the reachable total rather than the raw one.';

GRANT SELECT ON analytics.v_mcp_dataset TO mcp_reader;
