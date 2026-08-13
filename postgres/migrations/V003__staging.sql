-- V003 - Staging
--
-- One table per processed CSV, column for column, in Treasury's own names
-- (lower-cased by PostgreSQL's identifier folding - the original casing is
-- restored when the loader maps a column to a series code).
--
-- Columns are typed rather than text. The acquisition layer has already proven
-- every value parses to its declared OData type, so a COPY failure here is a
-- genuine breach of that contract and should stop the run loudly instead of
-- being absorbed by a text column and discovered three layers later.
--
-- These tables are truncated and reloaded in full on every run. They hold no
-- history; meta.source_file does.

-- Daily Treasury Par Yield Curve Rates -------------------------------------
CREATE TABLE IF NOT EXISTS staging.par_yield_curve (
    new_date            date,
    id                  integer,
    bc_3month           numeric(9,4),
    bc_6month           numeric(9,4),
    bc_1year            numeric(9,4),
    bc_2year            numeric(9,4),
    bc_3year            numeric(9,4),
    bc_5year            numeric(9,4),
    bc_7year            numeric(9,4),
    bc_10year           numeric(9,4),
    bc_30year           numeric(9,4),
    bc_30yeardisplay    numeric(9,4),
    bc_20year           numeric(9,4),
    bc_1month           numeric(9,4),
    bc_2month           numeric(9,4),
    bc_4month           numeric(9,4),
    bc_1_5month         numeric(9,4),
    _source_year        integer,
    _source_file        text
);

-- Daily Treasury Bill Rates -------------------------------------------------
-- CLOSE = bank-discount basis (act/360). YIELD = coupon-equivalent.
-- ROUND_B1_* = the quoted bill. CS_*_AVG = Treasury's composite average.
CREATE TABLE IF NOT EXISTS staging.bill_rates (
    index_date                      date,
    dailytreasurybillratedataid     integer,
    round_b1_close_4wk_2            numeric(9,4),
    round_b1_yield_4wk_2            numeric(9,4),
    round_b1_close_13wk_2           numeric(9,4),
    round_b1_yield_13wk_2           numeric(9,4),
    round_b1_close_26wk_2           numeric(9,4),
    round_b1_yield_26wk_2           numeric(9,4),
    bond_mkt_unavail_reason         text,
    maturity_date_4wk               date,
    maturity_date_13wk              date,
    maturity_date_26wk              date,
    cusip_4wk                       text,
    cusip_13wk                      text,
    cusip_26wk                      text,
    quote_date                      date,
    cf_new_date                     date,
    cs_4wk_close_avg                numeric(9,4),
    cs_4wk_yield_avg                numeric(9,4),
    cs_13wk_close_avg               numeric(9,4),
    cs_13wk_yield_avg               numeric(9,4),
    cs_26wk_close_avg               numeric(9,4),
    cs_26wk_yield_avg               numeric(9,4),
    cf_week                         integer,
    cs_52wk_close_avg               numeric(9,4),
    cs_52wk_yield_avg               numeric(9,4),
    round_b1_close_52wk_2           numeric(9,4),
    round_b1_yield_52wk_2           numeric(9,4),
    maturity_date_52wk              date,
    cusip_52wk                      text,
    round_b1_close_8wk_2            numeric(9,4),
    round_b1_yield_8wk_2            numeric(9,4),
    maturity_date_8wk               date,
    cusip_8wk                       text,
    cs_8wk_close_avg                numeric(9,4),
    cs_8wk_yield_avg                numeric(9,4),
    round_b1_close_17wk_2           numeric(9,4),
    round_b1_yield_17wk_2           numeric(9,4),
    maturity_date_17wk              date,
    cusip_17wk                      text,
    cs_17wk_close_avg               numeric(9,4),
    cs_17wk_yield_avg               numeric(9,4),
    round_b1_close_6wk_2            numeric(9,4),
    round_b1_yield_6wk_2            numeric(9,4),
    maturity_date_6wk               date,
    cusip_6wk                       text,
    cs_6wk_close_avg                numeric(9,4),
    cs_6wk_yield_avg                numeric(9,4),
    _source_year                    integer,
    _source_file                    text
);

-- Daily Treasury Long-Term Rates (tall: one row per date per rate type) -----
CREATE TABLE IF NOT EXISTS staging.long_term_rates (
    quote_date              date,
    id                      integer,
    extrapolation_factor    text,
    rate_type               text,
    rate                    numeric(9,4),
    _source_year            integer,
    _source_file            text
);

-- Daily Treasury Par Real Yield Curve Rates (TIPS) --------------------------
CREATE TABLE IF NOT EXISTS staging.real_yield_curve (
    new_date                                date,
    dailytreasuryrealyieldcurveratedataid    integer,
    tc_5year                                numeric(9,4),
    tc_7year                                numeric(9,4),
    tc_10year                               numeric(9,4),
    tc_20year                               numeric(9,4),
    tc_30year                               numeric(9,4),
    _source_year                            integer,
    _source_file                            text
);

-- Daily Treasury Real Long-Term Rates ---------------------------------------
CREATE TABLE IF NOT EXISTS staging.real_long_term_rates (
    quote_date          date,
    rate                numeric(9,4),
    _source_year        integer,
    _source_file        text
);

COMMENT ON TABLE staging.par_yield_curve IS
    'Mirror of data/processed/us_treasury/par_yield_curve.csv. bc_30yeardisplay '
    'is retained here exactly as Treasury publishes it, including the literal 0 '
    'on every date before 2011-01-03.';
COMMENT ON TABLE staging.bill_rates IS
    'Mirror of bill_rates.csv. quote_date and cf_new_date are redundant '
    'representations of index_date (verified identical on all rows) and are not '
    'promoted to the core model.';
COMMENT ON TABLE staging.long_term_rates IS
    'Mirror of long_term_rates.csv. Tall format - series identity comes from '
    'rate_type, not from the column name.';
