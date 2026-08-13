-- V011 - Series catalogue for the MCP layer
--
-- `list_series`, `search_series` and `get_series_coverage` all want the same
-- thing: series metadata joined to its actual coverage. Computing that in three
-- places invites three subtly different answers, so it is computed once here.
--
-- Coverage is derived from analytics.v_mcp_observation, which already excludes
-- placeholder rows and display variants. A series therefore reports the history
-- a caller can actually retrieve, not the history that exists in the raw table.
-- BC_30YEAR shows 8,164 observations rather than 9,159 because the 30-year bond
-- genuinely did not exist between 2002 and 2006 - the catalogue should say so.

CREATE OR REPLACE VIEW analytics.v_mcp_series_catalogue AS
SELECT s.series_code,
       s.display_name,
       s.data_key,
       d.title                          AS dataset_title,
       s.rate_kind::text                AS rate_kind,
       s.quote_basis::text              AS quote_basis,
       s.tenor_label,
       round(s.tenor_years * 12, 4)     AS tenor_months,
       s.tenor_years,
       s.is_composite,
       s.notes,
       o.first_observation,
       o.last_observation,
       COALESCE(o.observation_count, 0) AS observation_count
FROM treasury.series s
JOIN treasury.dataset d USING (data_key)
LEFT JOIN (
    SELECT series_code,
           min(observation_date) AS first_observation,
           max(observation_date) AS last_observation,
           count(*)              AS observation_count
    FROM analytics.v_mcp_observation
    GROUP BY series_code
) o ON o.series_code = s.series_code
-- Excluded series are absent entirely. BC_30YEARDISPLAY is a Treasury display
-- duplicate whose pre-2011 history is a literal 0 placeholder; it must not be
-- reachable, searchable, or nameable through this server.
WHERE NOT s.excluded_from_analytics;

COMMENT ON VIEW analytics.v_mcp_series_catalogue IS
    'Series metadata joined to real retrievable coverage. Single source of '
    'truth for list_series, search_series and get_series_coverage. Excludes '
    'display-variant series entirely.';

GRANT SELECT ON analytics.v_mcp_series_catalogue TO mcp_reader;
