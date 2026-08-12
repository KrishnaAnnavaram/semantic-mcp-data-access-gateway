-- V006 - Analytics read layer
--
-- Views only. This is the layer a consumer should query, and the reason it
-- exists is that querying treasury.observation directly requires you to
-- remember two traps: the BC_30YEARDISPLAY placeholder zeros, and the fact
-- that bill discount rates are not yields. Both are handled here once.
--
-- Every view filters excluded_from_analytics and value_status = 'observed',
-- so nothing that is not a genuine published rate can leak into a consumer.

-- Series catalogue -----------------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_series AS
SELECT s.series_id,
       s.data_key,
       d.title              AS dataset_title,
       s.series_code,
       s.display_name,
       s.rate_kind,
       s.quote_basis,
       s.tenor_label,
       s.tenor_years,
       s.is_composite,
       s.excluded_from_analytics,
       s.exclusion_reason,
       s.notes
FROM treasury.series s
JOIN treasury.dataset d USING (data_key);

COMMENT ON VIEW analytics.v_series IS
    'Every series, including the excluded ones - so a consumer can see what was '
    'withheld and why, rather than wondering where BC_30YEARDISPLAY went.';

-- Tidy observations ----------------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_observation AS
SELECT o.observation_date,
       o.data_key,
       d.title              AS dataset_title,
       s.series_code,
       s.display_name,
       s.rate_kind,
       s.quote_basis,
       s.tenor_label,
       s.tenor_years,
       o.rate_percent
FROM treasury.observation o
JOIN treasury.series  s USING (series_id)
JOIN treasury.dataset d ON d.data_key = o.data_key
WHERE o.value_status = 'observed'
  AND NOT s.excluded_from_analytics;

COMMENT ON VIEW analytics.v_observation IS
    'The tidy fact table: one row per series per day. Start here. rate_percent '
    'is in percent as published; a missing day is simply an absent row.';

-- Nominal par yield curve, pivoted ------------------------------------------

CREATE OR REPLACE VIEW analytics.v_par_yield_curve AS
SELECT o.observation_date,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_1MONTH')   AS m1,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_1_5MONTH') AS m1_5,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_2MONTH')   AS m2,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_3MONTH')   AS m3,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_4MONTH')   AS m4,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_6MONTH')   AS m6,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_1YEAR')    AS y1,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_2YEAR')    AS y2,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_3YEAR')    AS y3,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_5YEAR')    AS y5,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_7YEAR')    AS y7,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_10YEAR')   AS y10,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_20YEAR')   AS y20,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_30YEAR')   AS y30
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
WHERE o.data_key = 'daily_treasury_yield_curve'
  AND o.value_status = 'observed'
  AND NOT s.excluded_from_analytics
GROUP BY o.observation_date;

COMMENT ON VIEW analytics.v_par_yield_curve IS
    'The nominal par curve in wide form, one row per day. NULL means Treasury '
    'published no rate at that maturity that day - most often because the '
    'maturity did not yet exist. BC_30YEARDISPLAY is excluded by construction.';

-- Real (TIPS) par yield curve, pivoted --------------------------------------

CREATE OR REPLACE VIEW analytics.v_real_yield_curve AS
SELECT o.observation_date,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'TC_5YEAR')  AS y5,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'TC_7YEAR')  AS y7,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'TC_10YEAR') AS y10,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'TC_20YEAR') AS y20,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'TC_30YEAR') AS y30
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
WHERE o.data_key = 'daily_treasury_real_yield_curve'
  AND o.value_status = 'observed'
GROUP BY o.observation_date;

COMMENT ON VIEW analytics.v_real_yield_curve IS
    'TIPS-derived par REAL yields. Negative values are correct and expected.';

-- Bill rates, quoted issue, discount and coupon-equivalent side by side ------

CREATE OR REPLACE VIEW analytics.v_bill_rates_quoted AS
SELECT o.observation_date,
       s.tenor_label,
       s.tenor_years,
       max(o.rate_percent) FILTER (WHERE s.quote_basis = 'bank_discount_act360') AS discount_rate_act360,
       max(o.rate_percent) FILTER (WHERE s.quote_basis = 'coupon_equivalent')    AS coupon_equivalent_yield,
       b.cusip,
       b.maturity_date
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
LEFT JOIN treasury.bill_security b
       ON b.observation_date = o.observation_date
      AND b.tenor_code = replace(s.tenor_label, ' Week', 'WK')
WHERE o.data_key = 'daily_treasury_bill_rates'
  AND o.value_status = 'observed'
  AND s.series_code LIKE 'ROUND\_B1\_%'
GROUP BY o.observation_date, s.tenor_label, s.tenor_years, b.cusip, b.maturity_date;

COMMENT ON VIEW analytics.v_bill_rates_quoted IS
    'The quoted bill at each tenor, with its discount rate and its '
    'coupon-equivalent yield in separate, explicitly named columns. Only the '
    'coupon-equivalent column is comparable to a par yield.';

-- Long-term rates ------------------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_long_term_rates AS
SELECT o.observation_date,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'BC_20year')     AS nominal_20y,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'Over_10_Years') AS nominal_over_10y,
       max(o.rate_percent) FILTER (WHERE s.series_code = 'Real_Rate')     AS real_over_10y,
       e.extrapolation_factor
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
LEFT JOIN treasury.long_term_extrapolation e ON e.quote_date = o.observation_date
WHERE o.data_key = 'daily_treasury_long_term_rate'
  AND o.value_status = 'observed'
GROUP BY o.observation_date, e.extrapolation_factor;

COMMENT ON VIEW analytics.v_long_term_rates IS
    'The three long-term series pivoted. real_over_10y is a REAL rate sharing a '
    'row with two nominal ones - the column names keep them apart.';

-- Latest published curve -----------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_latest_rates AS
SELECT DISTINCT ON (o.series_id)
       o.series_id,
       o.data_key,
       s.series_code,
       s.display_name,
       s.rate_kind,
       s.quote_basis,
       s.tenor_years,
       o.observation_date,
       o.rate_percent
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
WHERE o.value_status = 'observed'
  AND NOT s.excluded_from_analytics
ORDER BY o.series_id, o.observation_date DESC;

COMMENT ON VIEW analytics.v_latest_rates IS
    'Most recent published value per series. Note observation_date can differ '
    'between series - a discontinued maturity keeps its last real date rather '
    'than being carried forward.';

-- Coverage / data-quality ----------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_series_coverage AS
SELECT s.data_key,
       s.series_code,
       s.display_name,
       s.tenor_years,
       s.excluded_from_analytics,
       count(o.*)                                          AS observations,
       count(*) FILTER (WHERE o.value_status = 'source_placeholder') AS placeholder_rows,
       min(o.observation_date)                             AS first_observation,
       max(o.observation_date)                             AS last_observation,
       count(*) FILTER (WHERE o.rate_percent = 0)          AS zero_valued_observations,
       min(o.rate_percent)                                 AS min_rate_percent,
       max(o.rate_percent)                                 AS max_rate_percent
FROM treasury.series s
LEFT JOIN treasury.observation o USING (series_id)
GROUP BY s.series_id, s.data_key, s.series_code, s.display_name,
         s.tenor_years, s.excluded_from_analytics;

COMMENT ON VIEW analytics.v_series_coverage IS
    'What each series actually contains. The first thing to read after a load, '
    'and the fastest way to spot a maturity that stopped or started.';

CREATE OR REPLACE VIEW analytics.v_dataset_summary AS
SELECT d.data_key,
       d.title,
       d.shape,
       count(DISTINCT s.series_id)      AS series,
       count(o.*)                       AS observations,
       min(o.observation_date)          AS first_observation,
       max(o.observation_date)          AS last_observation,
       count(DISTINCT o.observation_date) AS distinct_dates,
       d.caveat
FROM treasury.dataset d
LEFT JOIN treasury.series s USING (data_key)
LEFT JOIN treasury.observation o USING (series_id)
GROUP BY d.data_key, d.title, d.shape, d.caveat;

COMMENT ON VIEW analytics.v_dataset_summary IS
    'One row per dataset. The caveat travels with the summary on purpose.';
