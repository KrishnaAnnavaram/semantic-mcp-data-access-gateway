-- V008 - Synthetic demo portfolio
--
-- Everything in this schema is INVENTED. It exists so the risk engine has a
-- book to price; it is not market data and never becomes market data.
--
-- The repository's standing rule is that financial data is never fabricated.
-- This schema does not break that rule, it quarantines the exception: a bank's
-- positions are private and no public dataset contains them, so a demo book has
-- to be defined rather than downloaded. The rule that replaces "don't fabricate"
-- here is "fabricate visibly, and make it impossible to relabel".
--
-- Hence data_classification is NOT NULL DEFAULT 'SYNTHETIC_DEMO' with a CHECK
-- pinning it to exactly that value on every table. No INSERT, anywhere, can
-- produce a row in this schema that claims to be real. The MCP layer reads that
-- column and stamps it onto every response.
--
-- Instruments are Treasury-LIKE, not Treasury. Identifiers are DEMO_* and never
-- CUSIP-shaped, so nothing here can be mistaken for an actual security.

CREATE SCHEMA IF NOT EXISTS demo;

COMMENT ON SCHEMA demo IS
    'SYNTHETIC demo data. Invented positions and scenarios for demonstrating '
    'pricing and market-risk analytics. Never real, never market data.';

-- Portfolios ----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS demo.portfolio (
    portfolio_id        text        PRIMARY KEY,
    name                text        NOT NULL,
    description         text,
    base_currency       text        NOT NULL DEFAULT 'USD',
    seed_version        text        NOT NULL,
    data_classification text        NOT NULL DEFAULT 'SYNTHETIC_DEMO',
    CONSTRAINT portfolio_is_synthetic
        CHECK (data_classification = 'SYNTHETIC_DEMO'),
    CONSTRAINT portfolio_id_is_marked_demo
        CHECK (portfolio_id LIKE 'DEMO%' OR portfolio_id LIKE 'TREASURY_DEMO%')
);

COMMENT ON TABLE demo.portfolio IS
    'SYNTHETIC. Demo books. seed_version identifies which seed produced the '
    'contents, so a changed book is visible rather than silent.';

-- Instruments ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS demo.instrument (
    instrument_id       text        PRIMARY KEY,
    instrument_type     text        NOT NULL,
    display_name        text        NOT NULL,
    currency            text        NOT NULL DEFAULT 'USD',
    face_value          numeric(20,2) NOT NULL CHECK (face_value > 0),
    coupon_rate_pct     numeric(9,6)  NOT NULL CHECK (coupon_rate_pct >= 0),
    issue_date          date        NOT NULL,
    maturity_date       date        NOT NULL,
    coupon_frequency    integer     NOT NULL DEFAULT 2,
    day_count           text        NOT NULL DEFAULT 'ACT_ACT',
    rate_kind           text        NOT NULL DEFAULT 'nominal',
    data_classification text        NOT NULL DEFAULT 'SYNTHETIC_DEMO',
    CONSTRAINT instrument_is_synthetic
        CHECK (data_classification = 'SYNTHETIC_DEMO'),
    CONSTRAINT instrument_id_is_marked_demo
        CHECK (instrument_id LIKE 'DEMO\_%'),
    -- v1 prices fixed-rate semiannual bonds on ACT/ACT and nothing else. An
    -- instrument whose conventions the engine cannot honour must be rejected
    -- at the database, not discovered halfway through a valuation.
    CONSTRAINT instrument_type_is_supported
        CHECK (instrument_type = 'FIXED_RATE_BOND'),
    CONSTRAINT instrument_frequency_is_supported
        CHECK (coupon_frequency = 2),
    CONSTRAINT instrument_day_count_is_supported
        CHECK (day_count = 'ACT_ACT'),
    CONSTRAINT instrument_matures_after_issue
        CHECK (maturity_date > issue_date)
);

COMMENT ON TABLE demo.instrument IS
    'SYNTHETIC. Treasury-LIKE fixed-rate bonds. Identifiers are DEMO_* and '
    'deliberately not CUSIP-shaped so they cannot be mistaken for real '
    'securities. CHECK constraints restrict the set to what the v1 pricer '
    'actually implements.';
COMMENT ON COLUMN demo.instrument.coupon_rate_pct IS
    'Annual coupon in percent (4.25 means 4.25%), paid semiannually.';

-- Positions -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS demo.position (
    portfolio_id        text        NOT NULL REFERENCES demo.portfolio (portfolio_id),
    instrument_id       text        NOT NULL REFERENCES demo.instrument (instrument_id),
    face_notional       numeric(20,2) NOT NULL CHECK (face_notional > 0),
    PRIMARY KEY (portfolio_id, instrument_id)
);

COMMENT ON TABLE demo.position IS
    'SYNTHETIC. Long-only face notionals. v1 has no short positions, so the '
    'sign convention never has to be guessed.';

-- Scenarios -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS demo.scenario (
    scenario_id         text        PRIMARY KEY,
    name                text        NOT NULL,
    description         text,
    scenario_type       text        NOT NULL,
    shock_definition    jsonb       NOT NULL,
    data_classification text        NOT NULL DEFAULT 'SYNTHETIC_DEMO',
    CONSTRAINT scenario_is_synthetic
        CHECK (data_classification = 'SYNTHETIC_DEMO'),
    CONSTRAINT scenario_type_is_supported
        CHECK (scenario_type IN ('TENOR_VECTOR_BP', 'HISTORICAL_REPLAY'))
);

COMMENT ON TABLE demo.scenario IS
    'Scenario definitions. TENOR_VECTOR_BP carries an explicit tenor->basis-point '
    'vector. HISTORICAL_REPLAY names two real observation dates; the risk engine '
    'differences the two curves itself, so this server never calculates anything.';
COMMENT ON COLUMN demo.scenario.shock_definition IS
    'TENOR_VECTOR_BP: {"tenor_months": {"24": 100, ...}}. '
    'HISTORICAL_REPLAY: {"from_date": "1994-04-01", "to_date": "1994-04-04"}. '
    'Prose scenarios are not supported - a shock is a vector or a pair of dates.';

-- Seed ----------------------------------------------------------------------
-- Idempotent so a re-run of the migration suite is a no-op.

INSERT INTO demo.portfolio (portfolio_id, name, description, seed_version)
VALUES (
    'TREASURY_DEMO_001',
    'Synthetic Treasury Curve-Risk Portfolio',
    'SYNTHETIC demo book of five fixed-rate Treasury-like bonds spanning the '
    'curve. Chosen so every risk factor it depends on is a Treasury par yield '
    'this database already holds - the book has no exposure to anything we '
    'cannot source and verify.',
    'demo-book-v1'
)
ON CONFLICT (portfolio_id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    seed_version = EXCLUDED.seed_version;

INSERT INTO demo.instrument (
    instrument_id, instrument_type, display_name, face_value,
    coupon_rate_pct, issue_date, maturity_date
) VALUES
    ('DEMO_NOTE_2Y',  'FIXED_RATE_BOND', 'Demo 2-Year Note',   1000, 3.750000, DATE '2026-08-15', DATE '2028-08-15'),
    ('DEMO_NOTE_5Y',  'FIXED_RATE_BOND', 'Demo 5-Year Note',   1000, 4.000000, DATE '2026-08-15', DATE '2031-08-15'),
    ('DEMO_NOTE_10Y', 'FIXED_RATE_BOND', 'Demo 10-Year Note',  1000, 4.250000, DATE '2026-08-15', DATE '2036-08-15'),
    ('DEMO_BOND_20Y', 'FIXED_RATE_BOND', 'Demo 20-Year Bond',  1000, 4.500000, DATE '2026-08-15', DATE '2046-08-15'),
    ('DEMO_BOND_30Y', 'FIXED_RATE_BOND', 'Demo 30-Year Bond',  1000, 4.750000, DATE '2026-08-15', DATE '2056-08-15')
ON CONFLICT (instrument_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    coupon_rate_pct = EXCLUDED.coupon_rate_pct,
    maturity_date = EXCLUDED.maturity_date;

INSERT INTO demo.position (portfolio_id, instrument_id, face_notional) VALUES
    ('TREASURY_DEMO_001', 'DEMO_NOTE_2Y',   5000000),
    ('TREASURY_DEMO_001', 'DEMO_NOTE_5Y',  10000000),
    ('TREASURY_DEMO_001', 'DEMO_NOTE_10Y',  8000000),
    ('TREASURY_DEMO_001', 'DEMO_BOND_20Y',  4000000),
    ('TREASURY_DEMO_001', 'DEMO_BOND_30Y',  3000000)
ON CONFLICT (portfolio_id, instrument_id) DO UPDATE SET
    face_notional = EXCLUDED.face_notional;

-- Hypothetical scenarios: explicit tenor -> basis-point vectors.
INSERT INTO demo.scenario (scenario_id, name, description, scenario_type, shock_definition) VALUES
(
    'PARALLEL_UP_100BP', 'Parallel +100 bp',
    'Every tenor rises 100 basis points.',
    'TENOR_VECTOR_BP',
    '{"tenor_months": {"1":100,"3":100,"6":100,"12":100,"24":100,"36":100,"60":100,"84":100,"120":100,"240":100,"360":100}}'::jsonb
),
(
    'PARALLEL_DOWN_100BP', 'Parallel -100 bp',
    'Every tenor falls 100 basis points.',
    'TENOR_VECTOR_BP',
    '{"tenor_months": {"1":-100,"3":-100,"6":-100,"12":-100,"24":-100,"36":-100,"60":-100,"84":-100,"120":-100,"240":-100,"360":-100}}'::jsonb
),
(
    'STEEPENER_50BP', 'Bear steepener',
    'Front end anchored, long end sells off: 0 bp at 1 month rising to +50 bp at 30 years.',
    'TENOR_VECTOR_BP',
    '{"tenor_months": {"1":0,"3":2,"6":4,"12":8,"24":14,"36":20,"60":28,"84":34,"120":40,"240":47,"360":50}}'::jsonb
),
(
    'FLATTENER_50BP', 'Bear flattener',
    'Front end sells off, long end anchored: +50 bp at 1 month falling to 0 bp at 30 years.',
    'TENOR_VECTOR_BP',
    '{"tenor_months": {"1":50,"3":48,"6":45,"12":40,"24":33,"36":27,"60":19,"84":13,"120":8,"240":2,"360":0}}'::jsonb
),
-- Historical replays. These reference REAL observation dates already in the
-- database; the shock is whatever actually happened, not something invented.
(
    'REPLAY_1994_BOND_MASSACRE', '1994 bond massacre (1994-04-04)',
    'The largest one-day 10-year sell-off in this dataset: +39 bp on 1994-04-04.',
    'HISTORICAL_REPLAY',
    '{"from_date": "1994-04-01", "to_date": "1994-04-04"}'::jsonb
),
(
    'REPLAY_2009_QE_ANNOUNCEMENT', 'Fed announces Treasury QE (2009-03-18)',
    'The largest one-day 10-year rally in this dataset: -51 bp on 2009-03-18.',
    'HISTORICAL_REPLAY',
    '{"from_date": "2009-03-17", "to_date": "2009-03-18"}'::jsonb
),
(
    'REPLAY_2020_COVID_DASH_FOR_CASH', 'COVID dash for cash (2020-03-17)',
    'Yields rose sharply despite a risk-off shock as investors liquidated for cash: +29 bp on 2020-03-17.',
    'HISTORICAL_REPLAY',
    '{"from_date": "2020-03-16", "to_date": "2020-03-17"}'::jsonb
)
ON CONFLICT (scenario_id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    scenario_type = EXCLUDED.scenario_type,
    shock_definition = EXCLUDED.shock_definition;
