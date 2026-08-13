-- V010 - Read views shaped for the MCP wire contract
--
-- Two jobs:
--
--   1. Attach provenance. analytics.v_observation is curated but anonymous -
--      it does not say which Treasury file a number came from. `explain_number`
--      and the response envelope both need that, so this view carries the
--      source file, its URL and its SHA-256 alongside every rate.
--
--   2. Speak the wire contract's units. The core model stores tenor_years
--      (canonical for ordering across weeks/months/years). The MCP contract
--      speaks in months because that is how a curve is conventionally indexed.
--      tenor_months is derived here, once, rather than in every tool.
--
-- tenor_months is NUMERIC, not integer. BC_1_5MONTH is genuinely 1.5 months and
-- bill tenors are weeks (a 4-week bill is 0.92 months). Rounding to integer
-- would silently merge distinct points on the curve.
--
-- v_mcp_observation is deliberately rebuilt from the base tables rather than
-- layered on v_observation, because it needs observation.source_file which the
-- curated view does not expose. That duplicates two filter predicates, so
-- tools/verify_load.py asserts the two views return identical row counts - if
-- they ever drift, that fails rather than quietly exposing a placeholder.

-- Latest known source file per filename. meta.source_file is keyed on
-- (data_key, requested_year, sha256), so a Treasury restatement creates a
-- second row with the same file_name. The most recently seen one wins.
CREATE OR REPLACE VIEW analytics.v_source_file_current AS
SELECT DISTINCT ON (file_name)
       file_name,
       data_key,
       requested_year,
       source_url,
       sha256          AS source_sha256,
       downloaded_at_utc,
       records,
       checksum_verified
FROM meta.source_file
ORDER BY file_name, last_seen_run_id DESC;

COMMENT ON VIEW analytics.v_source_file_current IS
    'One row per raw Treasury file, resolved to the most recently loaded '
    'vintage. Revisions remain visible in meta.source_file; this view picks '
    'the one currently in force.';

-- The MCP layer's single read path for rate observations.
CREATE OR REPLACE VIEW analytics.v_mcp_observation AS
SELECT o.observation_date,
       o.data_key,
       d.title                                   AS dataset_title,
       s.series_code,
       s.display_name,
       s.rate_kind::text                         AS rate_kind,
       s.quote_basis::text                       AS quote_basis,
       s.tenor_label,
       s.tenor_years,
       round(s.tenor_years * 12, 4)              AS tenor_months,
       s.is_composite,
       o.rate_percent,
       'percent'::text                           AS unit,
       'REAL_MARKET_DATA'::text                  AS data_classification,
       o.source_file,
       f.source_url,
       f.source_sha256,
       f.downloaded_at_utc
FROM treasury.observation o
JOIN treasury.series  s USING (series_id)
JOIN treasury.dataset d ON d.data_key = o.data_key
LEFT JOIN analytics.v_source_file_current f ON f.file_name = o.source_file
-- These two predicates MUST match analytics.v_observation. verify_load.py
-- asserts the row counts agree so the duplication cannot drift.
WHERE o.value_status = 'observed'
  AND NOT s.excluded_from_analytics;

COMMENT ON VIEW analytics.v_mcp_observation IS
    'The MCP data server''s only rate read path. Carries the full semantic '
    'envelope - rate_kind, quote_basis, unit, classification - plus source '
    'file provenance. Placeholder rows and display-variant series are excluded '
    'by construction, so no tool can return one by accident.';

-- Curve access by date. Splitting this out keeps the tool SQL trivial and
-- gives the planner an obvious shape to optimise.
CREATE OR REPLACE VIEW analytics.v_mcp_curve AS
SELECT observation_date,
       rate_kind      AS curve_family,
       data_key,
       series_code,
       display_name,
       tenor_label,
       tenor_months,
       tenor_years,
       rate_percent,
       unit,
       quote_basis,
       data_classification,
       source_file,
       source_url,
       source_sha256
FROM analytics.v_mcp_observation
-- A curve is a set of point tenors. Composite series (Over_10_Years, the
-- long-term real average) are real observations but have no position on a
-- curve, so they are reachable through v_mcp_observation and not here.
WHERE tenor_years IS NOT NULL
  AND NOT is_composite
  AND quote_basis = 'par_coupon_semiannual';

COMMENT ON VIEW analytics.v_mcp_curve IS
    'Par yield curve points only - nominal and real - indexed by tenor_months. '
    'Excludes composites without a point tenor, and excludes bill quotes, whose '
    'bank-discount and coupon-equivalent bases do not belong on a par curve.';

-- Demo book, flattened for a single read.
CREATE OR REPLACE VIEW analytics.v_mcp_portfolio_position AS
SELECT p.portfolio_id,
       p.name                AS portfolio_name,
       p.description         AS portfolio_description,
       p.base_currency,
       p.seed_version,
       p.data_classification,
       i.instrument_id,
       i.instrument_type,
       i.display_name        AS instrument_name,
       i.currency,
       i.face_value,
       i.coupon_rate_pct,
       i.issue_date,
       i.maturity_date,
       i.coupon_frequency,
       i.day_count,
       i.rate_kind,
       pos.face_notional
FROM demo.portfolio p
JOIN demo.position   pos USING (portfolio_id)
JOIN demo.instrument i   USING (instrument_id);

COMMENT ON VIEW analytics.v_mcp_portfolio_position IS
    'SYNTHETIC demo positions joined to their instrument economics. '
    'data_classification travels with every row so the MCP layer cannot '
    'return a demo position without labelling it.';

GRANT SELECT ON analytics.v_source_file_current,
                analytics.v_mcp_observation,
                analytics.v_mcp_curve,
                analytics.v_mcp_portfolio_position
    TO mcp_reader;
