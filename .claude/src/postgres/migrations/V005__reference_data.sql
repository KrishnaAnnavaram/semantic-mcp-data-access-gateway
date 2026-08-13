-- V005 - Reference data: the five datasets and the 52 series they publish
--
-- Idempotent. Re-running updates the descriptive columns in place and never
-- orphans an observation, because series_id is stable across runs.

INSERT INTO treasury.dataset (
    data_key, title, slug, source_url_pattern, documented_first_year,
    date_field, natural_key, shape, description, caveat
) VALUES
(
    'daily_treasury_yield_curve',
    'Daily Treasury Par Yield Curve Rates',
    'par_yield_curve',
    'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}',
    1990, 'NEW_DATE', ARRAY['NEW_DATE'], 'wide',
    'Par yields on the most recently auctioned Treasury securities, quoted on a bond-equivalent, semi-annual coupon basis, from Treasury''s monotone-convex par-yield curve methodology.',
    'PAR yields - not zero-coupon/spot rates, not forwards, not executable prices. BC_30YEAR is absent 2003-2005 (bond discontinued 2002, reintroduced 2006). BC_30YEARDISPLAY is published as a literal 0 before 2011-01-03; that 0 is a placeholder, not a yield.'
),
(
    'daily_treasury_bill_rates',
    'Daily Treasury Bill Rates',
    'bill_rates',
    'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_bill_rates&field_tdr_date_value={year}',
    2002, 'INDEX_DATE', ARRAY['INDEX_DATE'], 'wide',
    'Closing market bid quotes for the most recently auctioned bill at each benchmark tenor, with the CUSIP and maturity date of the bill actually quoted.',
    'CLOSE columns are DISCOUNT rates on a bank-discount actual/360 basis. YIELD columns are COUPON-EQUIVALENT yields. They are different quantities and must never share a curve with the par yields above.'
),
(
    'daily_treasury_long_term_rate',
    'Daily Treasury Long-Term Rates',
    'long_term_rates',
    'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_long_term_rate&field_tdr_date_value={year}',
    2000, 'QUOTE_DATE', ARRAY['QUOTE_DATE', 'RATE_TYPE'], 'long',
    'Long-term rate series in tall format: one row per quote date per RATE_TYPE (BC_20year, Over_10_Years, Real_Rate), with the extrapolation factor Treasury applied.',
    'The natural key is (QUOTE_DATE, RATE_TYPE) - a date legitimately carries three rows. The Real_Rate rows inside this otherwise nominal feed are the long-term real rate average and must not be merged with the nominal series.'
),
(
    'daily_treasury_real_yield_curve',
    'Daily Treasury Par Real Yield Curve Rates',
    'real_yield_curve',
    'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}',
    2003, 'NEW_DATE', ARRAY['NEW_DATE'], 'wide',
    'Par real yield curve rates derived from Treasury Inflation Protected Securities (TIPS) at the 5, 7, 10, 20 and 30 year points.',
    'REAL yields (TIPS-based), not nominal. Negative values are normal and correct and must never be clipped or treated as missing. Nominal minus real is a breakeven-inflation calculation and is deliberately not computed in this pipeline.'
),
(
    'daily_treasury_real_long_term',
    'Daily Treasury Real Long-Term Rates',
    'real_long_term_rates',
    'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_real_long_term&field_tdr_date_value={year}',
    2000, 'QUOTE_DATE', ARRAY['QUOTE_DATE'], 'wide',
    'Treasury''s long-term real rate average: the unweighted average of bid real yields on TIPS with more than 10 years remaining maturity.',
    'REAL (TIPS) rate. A single composite series with no meaningful point tenor.'
)
ON CONFLICT (data_key) DO UPDATE SET
    title = EXCLUDED.title,
    slug = EXCLUDED.slug,
    source_url_pattern = EXCLUDED.source_url_pattern,
    documented_first_year = EXCLUDED.documented_first_year,
    date_field = EXCLUDED.date_field,
    natural_key = EXCLUDED.natural_key,
    shape = EXCLUDED.shape,
    description = EXCLUDED.description,
    caveat = EXCLUDED.caveat;

-- Par yield curve: 14 maturities plus Treasury's display duplicate -----------

INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, tenor_value, tenor_unit, tenor_years,
    is_display_variant, excluded_from_analytics, exclusion_reason,
    placeholder_zero_before
)
SELECT 'daily_treasury_yield_curve', v.code, v.label || ' Par Yield',
       'nominal', 'par_coupon_semiannual',
       v.label, v.val, v.unit,
       CASE v.unit WHEN 'month' THEN v.val / 12.0 ELSE v.val END,
       v.display, v.display,
       CASE WHEN v.display THEN
            'Treasury display duplicate of BC_30YEAR. Published as a literal 0 on '
            'every date before 2011-01-03, which is a placeholder rather than a '
            '0.00% yield. Use BC_30YEAR instead.'
       END,
       CASE WHEN v.display THEN DATE '2011-01-03' END
FROM (VALUES
    ('BC_1MONTH',        '1 Month',   1.0,  'month', false),
    ('BC_1_5MONTH',      '1.5 Month', 1.5,  'month', false),
    ('BC_2MONTH',        '2 Month',   2.0,  'month', false),
    ('BC_3MONTH',        '3 Month',   3.0,  'month', false),
    ('BC_4MONTH',        '4 Month',   4.0,  'month', false),
    ('BC_6MONTH',        '6 Month',   6.0,  'month', false),
    ('BC_1YEAR',         '1 Year',    1.0,  'year',  false),
    ('BC_2YEAR',         '2 Year',    2.0,  'year',  false),
    ('BC_3YEAR',         '3 Year',    3.0,  'year',  false),
    ('BC_5YEAR',         '5 Year',    5.0,  'year',  false),
    ('BC_7YEAR',         '7 Year',    7.0,  'year',  false),
    ('BC_10YEAR',        '10 Year',   10.0, 'year',  false),
    ('BC_20YEAR',        '20 Year',   20.0, 'year',  false),
    ('BC_30YEAR',        '30 Year',   30.0, 'year',  false),
    ('BC_30YEARDISPLAY', '30 Year',   30.0, 'year',  true)
) AS v(code, label, val, unit, display)
ON CONFLICT (data_key, series_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    tenor_years = EXCLUDED.tenor_years,
    is_display_variant = EXCLUDED.is_display_variant,
    excluded_from_analytics = EXCLUDED.excluded_from_analytics,
    exclusion_reason = EXCLUDED.exclusion_reason,
    placeholder_zero_before = EXCLUDED.placeholder_zero_before;

-- Bill rates: 7 tenors x 4 measures = 28 series ------------------------------
-- Generated rather than written out, so the discount/coupon-equivalent
-- distinction is applied identically to every tenor and cannot be mistyped on
-- one row out of twenty-eight.

INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, tenor_value, tenor_unit, tenor_years, notes
)
SELECT 'daily_treasury_bill_rates',
       format(m.code_tpl, t.wk),
       format('%s-Week Bill %s', t.wk, m.measure),
       'nominal',
       m.basis::treasury.quote_basis,
       t.wk || ' Week', t.wk, 'week', round(t.wk * 7 / 365.0, 6),
       m.note
FROM (VALUES (4), (6), (8), (13), (17), (26), (52)) AS t(wk)
CROSS JOIN (VALUES
    ('ROUND_B1_CLOSE_%sWK_2', 'Discount Rate (quoted issue)',
     'bank_discount_act360',
     'Closing market bid discount rate on the most recently auctioned bill at this tenor. Bank-discount basis, actual/360.'),
    ('ROUND_B1_YIELD_%sWK_2', 'Coupon-Equivalent Yield (quoted issue)',
     'coupon_equivalent',
     'The same quote restated as a coupon-equivalent yield. This is the figure comparable to a par coupon yield.'),
    ('CS_%sWK_CLOSE_AVG', 'Composite Average Discount Rate',
     'bank_discount_act360',
     'Treasury composite average closing discount rate. Bank-discount basis, actual/360.'),
    ('CS_%sWK_YIELD_AVG', 'Composite Average Coupon-Equivalent Yield',
     'coupon_equivalent',
     'Treasury composite average restated as a coupon-equivalent yield.')
) AS m(code_tpl, measure, basis, note)
ON CONFLICT (data_key, series_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    quote_basis = EXCLUDED.quote_basis,
    tenor_years = EXCLUDED.tenor_years,
    notes = EXCLUDED.notes;

-- Long-term rates: series identity comes from RATE_TYPE ----------------------

INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, tenor_value, tenor_unit, tenor_years, is_composite, notes
) VALUES
('daily_treasury_long_term_rate', 'BC_20year', '20 Year Par Yield (long-term feed)',
 'nominal', 'par_coupon_semiannual', '20 Year', 20.0, 'year', 20.0, false,
 'The 20-year point as republished in the long-term feed.'),
('daily_treasury_long_term_rate', 'Over_10_Years', 'Long-Term Composite (over 10 years)',
 'nominal', 'par_coupon_semiannual', 'Over 10 Years', NULL, NULL, NULL, true,
 'Average of nominal yields on Treasury securities with more than 10 years remaining maturity. No single point tenor.'),
('daily_treasury_long_term_rate', 'Real_Rate', 'Long-Term Real Rate Average',
 'real', 'average_real_yield', 'Over 10 Years', NULL, NULL, NULL, true,
 'REAL rate carried inside the nominal long-term feed. Must not be merged with BC_20year or Over_10_Years.')
ON CONFLICT (data_key, series_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    rate_kind = EXCLUDED.rate_kind,
    quote_basis = EXCLUDED.quote_basis,
    is_composite = EXCLUDED.is_composite,
    notes = EXCLUDED.notes;

-- Par real yield curve (TIPS) ------------------------------------------------

INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, tenor_value, tenor_unit, tenor_years
)
SELECT 'daily_treasury_real_yield_curve', v.code, v.label || ' Par Real Yield',
       'real', 'par_coupon_semiannual', v.label, v.val, 'year', v.val
FROM (VALUES
    ('TC_5YEAR',  '5 Year',  5.0),
    ('TC_7YEAR',  '7 Year',  7.0),
    ('TC_10YEAR', '10 Year', 10.0),
    ('TC_20YEAR', '20 Year', 20.0),
    ('TC_30YEAR', '30 Year', 30.0)
) AS v(code, label, val)
ON CONFLICT (data_key, series_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    tenor_years = EXCLUDED.tenor_years;

-- Real long-term rates -------------------------------------------------------

INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, is_composite, notes
) VALUES
('daily_treasury_real_long_term', 'RATE', 'Long-Term Real Rate Average',
 'real', 'average_real_yield', 'Over 10 Years', true,
 'Unweighted average of bid real yields on TIPS with more than 10 years remaining maturity. The source column is literally named RATE; the code is kept as published since series codes are unique per dataset.')
ON CONFLICT (data_key, series_code) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    notes = EXCLUDED.notes;
