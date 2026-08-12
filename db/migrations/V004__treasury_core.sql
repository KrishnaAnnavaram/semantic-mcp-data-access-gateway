-- V004 - Core model
--
-- Design rule: a new maturity must be a ROW, not a column.
--
-- Treasury has added six maturities to the par curve since 1990 and expects to
-- add more. A wide table would need DDL, a migration and an application change
-- every time. Here BC_1_5MONTH arriving in 2025 is one INSERT into
-- treasury.series and the loader picks it up on the next run.
--
-- Second design rule: every rate carries its quoting basis.
--
-- A bill discount rate and a par coupon yield are different quantities. Stored
-- as bare numbers in adjacent columns they look interchangeable, and eventually
-- someone plots them on one curve. quote_basis makes that mistake impossible to
-- make by accident and trivial to filter out.

-- Enumerations --------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'rate_kind' AND n.nspname = 'treasury') THEN
        CREATE TYPE treasury.rate_kind AS ENUM ('nominal', 'real');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'quote_basis' AND n.nspname = 'treasury') THEN
        CREATE TYPE treasury.quote_basis AS ENUM (
            'par_coupon_semiannual',   -- par yield, bond-equivalent, semi-annual coupon
            'bank_discount_act360',    -- bill discount rate, actual/360
            'coupon_equivalent',       -- bill yield restated on a coupon basis
            'average_real_yield'       -- unweighted average of TIPS bid real yields
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'value_status' AND n.nspname = 'treasury') THEN
        CREATE TYPE treasury.value_status AS ENUM (
            'observed',            -- Treasury published this rate
            'source_placeholder'   -- Treasury published a filler value that is not a rate
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
                   WHERE t.typname = 'dataset_shape' AND n.nspname = 'treasury') THEN
        CREATE TYPE treasury.dataset_shape AS ENUM ('wide', 'long');
    END IF;
END
$$;

-- Datasets ------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS treasury.dataset (
    data_key            text        PRIMARY KEY,
    title               text        NOT NULL,
    slug                text        NOT NULL UNIQUE,
    source_organisation text        NOT NULL DEFAULT 'U.S. Department of the Treasury',
    source_url_pattern  text        NOT NULL,
    documented_first_year integer   NOT NULL,
    date_field          text        NOT NULL,
    natural_key         text[]      NOT NULL,
    shape               treasury.dataset_shape NOT NULL,
    description         text        NOT NULL,
    caveat              text        NOT NULL
);

COMMENT ON TABLE treasury.dataset IS
    'The five Treasury daily interest-rate datasets. caveat is not decoration - '
    'it is the market-risk warning that belongs with the numbers, carried into '
    'the database so it survives being copied out of the README.';

-- Series --------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS treasury.series (
    series_id           integer     PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    data_key            text        NOT NULL REFERENCES treasury.dataset (data_key),
    series_code         text        NOT NULL,
    display_name        text        NOT NULL,
    rate_kind           treasury.rate_kind   NOT NULL,
    quote_basis         treasury.quote_basis NOT NULL,
    tenor_label         text,
    tenor_value         numeric(7,3),
    tenor_unit          text        CHECK (tenor_unit IN ('week', 'month', 'year')),
    tenor_years         numeric(9,6),
    is_composite        boolean     NOT NULL DEFAULT false,
    is_display_variant  boolean     NOT NULL DEFAULT false,
    excluded_from_analytics boolean NOT NULL DEFAULT false,
    exclusion_reason    text,
    placeholder_zero_before date,
    notes               text,
    UNIQUE (data_key, series_code),
    -- Lets treasury.observation carry data_key without it being able to drift.
    UNIQUE (series_id, data_key),
    CONSTRAINT series_exclusion_needs_reason
        CHECK (NOT excluded_from_analytics OR exclusion_reason IS NOT NULL),
    CONSTRAINT series_tenor_is_complete
        CHECK ((tenor_value IS NULL) = (tenor_unit IS NULL))
);

COMMENT ON TABLE treasury.series IS
    'One row per publishable rate series. series_code preserves Treasury''s own '
    'identifier exactly (BC_1MONTH, ROUND_B1_CLOSE_4WK_2, Real_Rate) so the '
    'database and the source feed can always be reconciled by name.';
COMMENT ON COLUMN treasury.series.tenor_years IS
    'Canonical ordering key. Months/12 or weeks*7/365, so a 4-week bill (0.0767) '
    'and a 1-month par point (0.0833) sort correctly against each other despite '
    'being quoted in different units.';
COMMENT ON COLUMN treasury.series.excluded_from_analytics IS
    'Series that exist in the source but must not reach a consumer unfiltered. '
    'They are still loaded in full - exclusion happens in the analytics views, '
    'never by dropping data.';
COMMENT ON COLUMN treasury.series.placeholder_zero_before IS
    'Date before which a published 0 in this series is a filler, not a rate. '
    'The rule lives here rather than in the loader so that recognising a '
    'placeholder is a property of the series, and adding another one is an '
    'UPDATE rather than a code change. NULL means every 0 is a genuine 0.00%.';

CREATE INDEX IF NOT EXISTS series_data_key_idx ON treasury.series (data_key);
CREATE INDEX IF NOT EXISTS series_tenor_idx ON treasury.series (tenor_years);

-- Observations --------------------------------------------------------------

CREATE TABLE IF NOT EXISTS treasury.observation (
    series_id           integer     NOT NULL,
    observation_date    date        NOT NULL,
    data_key            text        NOT NULL,
    rate_percent        numeric(9,4),
    value_status        treasury.value_status NOT NULL DEFAULT 'observed',
    source_value_percent numeric(9,4),
    source_file         text        NOT NULL,
    load_run_id         bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    PRIMARY KEY (series_id, observation_date),
    FOREIGN KEY (series_id, data_key)
        REFERENCES treasury.series (series_id, data_key),
    -- A plausibility guard wide enough that it can only fire on corruption.
    -- Negative rates are legitimate and deliberately permitted.
    CONSTRAINT observation_rate_is_plausible
        CHECK (rate_percent IS NULL OR rate_percent BETWEEN -25 AND 100),
    -- An observed row has a rate. A placeholder row has none, and keeps what
    -- the source actually printed so the trap stays auditable.
    CONSTRAINT observation_status_matches_value
        CHECK (
            (value_status = 'observed'           AND rate_percent IS NOT NULL)
         OR (value_status = 'source_placeholder' AND rate_percent IS NULL
                                                 AND source_value_percent IS NOT NULL)
        )
);

COMMENT ON TABLE treasury.observation IS
    'One row per series per day THAT TREASURY PUBLISHED. Absence of a row means '
    'Treasury published nothing - it is never a zero and never a carried-forward '
    'value. Nothing in this pipeline writes a row Treasury did not publish.';
COMMENT ON COLUMN treasury.observation.rate_percent IS
    'In percent, as published: 3.72 means 3.72%. Not a decimal fraction, not '
    'basis points.';
COMMENT ON COLUMN treasury.observation.data_key IS
    'Denormalised from series for query locality; the composite foreign key to '
    'series (series_id, data_key) makes it impossible for it to disagree.';

CREATE INDEX IF NOT EXISTS observation_date_idx
    ON treasury.observation (observation_date);
CREATE INDEX IF NOT EXISTS observation_dataset_date_idx
    ON treasury.observation (data_key, observation_date);
CREATE INDEX IF NOT EXISTS observation_date_brin_idx
    ON treasury.observation USING brin (observation_date);

-- Bill securities -----------------------------------------------------------
-- The bill feed identifies which security was actually quoted. That is
-- reference data about an instrument, not a rate, so it does not belong in
-- observation.

CREATE TABLE IF NOT EXISTS treasury.bill_security (
    observation_date    date        NOT NULL,
    tenor_code          text        NOT NULL,
    cusip               text,
    maturity_date       date,
    load_run_id         bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    PRIMARY KEY (observation_date, tenor_code),
    CONSTRAINT bill_security_matures_after_quote
        CHECK (maturity_date IS NULL OR maturity_date > observation_date)
);

COMMENT ON TABLE treasury.bill_security IS
    'The specific bill (CUSIP and maturity) behind each quoted tenor on each '
    'day. Needed to tell a 4-week quote apart from the bill that produced it.';

-- Long-term extrapolation factor --------------------------------------------

CREATE TABLE IF NOT EXISTS treasury.long_term_extrapolation (
    quote_date              date    PRIMARY KEY,
    extrapolation_factor    numeric(9,4) NOT NULL,
    source_text             text    NOT NULL,
    load_run_id             bigint  NOT NULL REFERENCES meta.load_run (load_run_id)
);

COMMENT ON TABLE treasury.long_term_extrapolation IS
    'Treasury''s extrapolation factor for the long-term rate, published only '
    'between 2002-02-19 and 2006-02-08 while the 30-year bond was unavailable. '
    'Verified identical across all three rate types on any given date, so it is '
    'modelled per date rather than per series.';

-- Market notes --------------------------------------------------------------

CREATE TABLE IF NOT EXISTS treasury.market_note (
    data_key            text        NOT NULL REFERENCES treasury.dataset (data_key),
    observation_date    date        NOT NULL,
    note                text        NOT NULL,
    load_run_id         bigint      NOT NULL REFERENCES meta.load_run (load_run_id),
    PRIMARY KEY (data_key, observation_date)
);

COMMENT ON TABLE treasury.market_note IS
    'Free-text market-unavailability reasons Treasury attaches to a day '
    '(BOND_MKT_UNAVAIL_REASON). Rare, but the explanation for a gap is worth '
    'more than the gap.';
