-- V013 - A curve has exactly one point per tenor
--
-- V010 defined v_mcp_curve as "par-quoted, non-composite series with a tenor".
-- That is true of BC_20YEAR in daily_treasury_yield_curve AND of BC_20year in
-- daily_treasury_long_term_rate, which republishes the same 20-year point under
-- different casing. The nominal curve therefore carried two nodes at 240 months.
--
-- Nothing would have failed. The curve would simply have had a duplicate node,
-- the bootstrap would have consumed whichever arrived first, and every price and
-- DV01 downstream would have been quietly built on a curve that was not the one
-- Treasury publishes.
--
-- The fix is to name the source datasets rather than infer curve membership
-- from column properties. A curve is a published object, not everything that
-- happens to look curve-shaped:
--
--   nominal -> daily_treasury_yield_curve
--   real    -> daily_treasury_real_yield_curve
--
-- The long-term and bill datasets remain fully available through
-- v_mcp_observation and get_rate_history; they are simply not curve nodes.

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
WHERE data_key IN ('daily_treasury_yield_curve', 'daily_treasury_real_yield_curve')
  AND tenor_years IS NOT NULL
  AND NOT is_composite;

COMMENT ON VIEW analytics.v_mcp_curve IS
    'Par yield curve nodes, one per tenor per date. Sourced explicitly from the '
    'two published curve datasets rather than inferred from quoting basis, so '
    'the 20-year point republished by the long-term feed cannot duplicate the '
    'node. Bill quotes are excluded: their bank-discount and coupon-equivalent '
    'bases do not belong on a par curve.';

GRANT SELECT ON analytics.v_mcp_curve TO mcp_reader;
