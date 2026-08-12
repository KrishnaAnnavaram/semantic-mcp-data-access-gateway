# Data contract — what Treasury publishes, and what it means

The market-risk semantics of the source. Read this before writing anything that
consumes the numbers; several of these distinctions are the difference between
a correct curve and a plausible-looking wrong one.

## Source

| | |
|---|---|
| Organisation | U.S. Department of the Treasury |
| Endpoint | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml` |
| Parameters | `?data=<data_key>&field_tdr_date_value=<yyyy>` |
| Format | Atom/OData XML, OData EDM primitive types |
| Auth | none |
| Docs | [XML feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) · [archives](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives) |

Documentation verified 2026-08-11. No other source is permitted — not FRED, not
Kaggle, not a mirror, not for a single missing day.

## Units

**All rates are in percent, exactly as published.** `3.72` means 3.72%. Not a
decimal fraction, not basis points. Nothing in this pipeline rescales.

## The five datasets

### `daily_treasury_yield_curve` — Par Yield Curve, from 1990

Par yields on the most recently auctioned securities, bond-equivalent,
semi-annual coupon basis, from Treasury's monotone-convex methodology.

> **Par, not spot.** These are par yields — not zero-coupon rates, not forwards,
> not executable prices. Bootstrapping a zero curve is a downstream modelling
> decision with its own assumptions.

Maturities and when each starts:

| Series | From | Notes |
|---|---|---|
| `BC_3MONTH` `BC_6MONTH` `BC_1YEAR` `BC_2YEAR` `BC_3YEAR` `BC_5YEAR` `BC_7YEAR` `BC_10YEAR` | 1990-01-02 | The original curve |
| `BC_30YEAR` | 1990-01-02 | **Absent 2003-2005** — bond discontinued 2002, reintroduced 2006 |
| `BC_20YEAR` | 1993-10-01 | |
| `BC_1MONTH` | 2001-07-31 | |
| `BC_2MONTH` | 2018-10-16 | |
| `BC_4MONTH` | 2022-10-19 | |
| `BC_1_5MONTH` | 2025-02-18 | Most recent addition |
| `BC_30YEARDISPLAY` | 1990-01-02 | **Placeholder — see below** |

### `daily_treasury_bill_rates` — Bill Rates, from 2002

Closing market bid quotes for the most recently auctioned bill at each tenor,
plus the CUSIP and maturity of the bill actually quoted.

> **Discount rate ≠ yield.** `ROUND_B1_CLOSE_*` and `CS_*_CLOSE_AVG` are
> **discount rates** on a bank-discount, actual/360 basis. `ROUND_B1_YIELD_*`
> and `CS_*_YIELD_AVG` are **coupon-equivalent yields**. Only the second kind is
> comparable to a par coupon yield. On 2026-08-11 the 4-week bill quotes 3.64
> discount and 3.70 coupon-equivalent — a 6 bp difference that grows with tenor
> and with the level of rates.

`ROUND_B1_*` is the quoted issue; `CS_*_AVG` is Treasury's composite average.
Tenors 4, 13, 26 weeks from 2002; 52 weeks present 2002, absent 2003-2007, back
2008; 8 weeks from 2018; 17 weeks from 2022; 6 weeks from 2025.

### `daily_treasury_long_term_rate` — Long-Term Rates, from 2000

**Tall format.** Natural key `(QUOTE_DATE, RATE_TYPE)` — one date legitimately
carries three rows:

| `RATE_TYPE` | Kind | Meaning |
|---|---|---|
| `BC_20year` | nominal | The 20-year point, republished here |
| `Over_10_Years` | nominal | Average yield on securities with >10y remaining |
| `Real_Rate` | **real** | Long-term real rate average |

> A **real** rate sits inside an otherwise nominal feed. Merging all three into
> one "long-term rate" series is a mistake the tall format makes easy.

`EXTRAPOLATION_FACTOR` is populated only 2002-02-19 → 2006-02-08, the window in
which the 30-year bond was unavailable. It is untyped in the source, identical
across all three rate types on any given date, and therefore modelled per date.

### `daily_treasury_real_yield_curve` — Par Real Yield Curve, from 2003

TIPS-derived par real yields: `TC_5YEAR`, `TC_7YEAR`, `TC_10YEAR` (all from
2003), `TC_20YEAR` (2004), `TC_30YEAR` (2010).

> **Negative values are normal and correct.** Real yields were negative for
> much of 2011-2022. Clipping, flooring or treating them as missing corrupts
> the data. Nominal minus real is a *breakeven inflation* calculation — a
> derived analytic, deliberately not computed here.

### `daily_treasury_real_long_term` — Real Long-Term Rates, from 2000

One composite series: the unweighted average of bid real yields on TIPS with
more than 10 years remaining maturity. The source column is literally named
`RATE`.

## The traps

### 1. `BC_30YEARDISPLAY` is a placeholder before 2011-01-03

Treasury publishes a literal `0` in this column on **5,256 dates** from
1990-01-02 to 2010-12-31. It is not a 0.00% thirty-year yield. Loaded naively,
it puts a 0% long bond into 21 years of history — and because the rest of the
curve is correct, the result looks entirely plausible.

Handling: stored with `value_status = 'source_placeholder'`,
`rate_percent = NULL`, and the published `0` retained in
`source_value_percent`. Excluded from every analytics view. **Use `BC_30YEAR`.**

### 2. A genuine 0.00% is not missing

`BC_1MONTH` (100 rows), `BC_3MONTH` (18), `BC_2MONTH` (2) and several bill and
TIPS columns printed exactly 0.00 during 2008-12, 2011, 2015 and 2020-21. These
are real observations from the zero-rate era. The distinguishing test is a
*leading unbroken run* of zeros over a column's entire early history, not the
presence of a zero.

### 3. Nulls are mostly non-existence, not gaps

The par curve is 19% null and bill rates 36% null. Almost all of it is
maturities that did not exist yet. `analytics.v_series_coverage` shows exactly
when each series starts and stops.

### 4. Treasury sometimes publishes an empty row

2010-10-11 (Columbus Day) has a row in the feed with every maturity NULL and
only the placeholder zero. It counts as a date in the source, produces no rate
observations, and correctly does not appear in `analytics.v_par_yield_curve`.
That is why the curve view has 9,158 rows against 9,159 source dates.

### 5. The `Id` columns are not keys

`Id`, `DailyTreasuryBillRateDataId` and `DailyTreasuryRealYieldCurveRateDataId`
are Treasury internal row identifiers. They are not ordered by date, they
restart across years, and they were **omitted entirely from the 2023 and 2024
responses** before returning in 2025. They are kept in staging and never
promoted.

### 6. Published curve, not tradable prices

End-of-day indicative quotes. No bid/ask, no size, not executable. A risk
number derived from them inherits that.

## Calendar

Treasury publishes on U.S. business days: weekdays excluding federal holidays
**and Good Friday** (bond market closed, not a federal holiday). Recorded ad-hoc
closures: 9/11 (Sep 11-14 2001), Reagan (2004-06-11), Hurricane Sandy (Oct
29-30 2012), G.H.W. Bush (2018-12-05), Carter (2025-01-09), Nixon (1994-04-27).

With that calendar applied there are **zero unexplained business-day gaps** in
any of the five datasets.

## Revisions

Treasury can restate prior days. Raw files are replaced only by an explicit
`--refresh`, so a routine rerun will not pick up a revision to a closed year.
`meta.source_file` is keyed on `(data_key, year, sha256)`, so when a revision is
loaded it appears as a **new row** rather than overwriting the old one — the
change stays visible.
