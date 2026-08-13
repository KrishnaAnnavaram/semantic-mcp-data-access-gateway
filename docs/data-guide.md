# The Data — a complete guide

Everything in this repository's data layer: what it is, where it comes from, what is
actually in it, what each number means, and where it will mislead you if you are not
careful.

Every figure below was measured from the loaded database on **2026-08-12**, not
estimated.

---

## Table of contents

1. [What this data is, in one paragraph](#1-what-this-data-is-in-one-paragraph)
2. [Where it comes from](#2-where-it-comes-from)
3. [How it gets here](#3-how-it-gets-here)
4. [The five datasets](#4-the-five-datasets)
   - [4.1 Daily Treasury Par Yield Curve Rates](#41-daily-treasury-par-yield-curve-rates)
   - [4.2 Daily Treasury Bill Rates](#42-daily-treasury-bill-rates)
   - [4.3 Daily Treasury Long-Term Rates](#43-daily-treasury-long-term-rates)
   - [4.4 Daily Treasury Par Real Yield Curve Rates](#44-daily-treasury-par-real-yield-curve-rates)
   - [4.5 Daily Treasury Real Long-Term Rates](#45-daily-treasury-real-long-term-rates)
5. [Complete series inventory — all 52](#5-complete-series-inventory--all-52)
6. [What the numbers actually mean](#6-what-the-numbers-actually-mean)
7. [What the history looks like](#7-what-the-history-looks-like)
8. [The traps](#8-the-traps)
9. [How missing data is represented](#9-how-missing-data-is-represented)
10. [Where the data physically lives](#10-where-the-data-physically-lives)
11. [How to query it](#11-how-to-query-it)
12. [How we know it is correct](#12-how-we-know-it-is-correct)
13. [What this data is not](#13-what-this-data-is-not)
14. [Refreshing, and how revisions behave](#14-refreshing-and-how-revisions-behave)
15. [Glossary](#15-glossary)

---

## 1. What this data is, in one paragraph

This is the **U.S. Treasury yield curve and its relatives, daily, since 1990** — the
interest rates the U.S. government pays to borrow money at every maturity from one month
to thirty years. It is the single most important reference dataset in fixed income:
essentially every bond, loan, mortgage and derivative in the dollar market is priced
relative to it, and it is the risk-free curve that discounting, valuation and market-risk
models start from. There are **267,517 daily observations** across **52 distinct rate
series** in **5 datasets**, running from **1990-01-02 to 2026-08-11**, all published by
the U.S. Department of the Treasury itself.

---

## 2. Where it comes from

| | |
|---|---|
| **Publisher** | U.S. Department of the Treasury |
| **Site** | <https://home.treasury.gov> |
| **Feed** | `/resource-center/data-chart-center/interest-rates/pages/xml` |
| **Parameters** | `?data=<data_key>&field_tdr_date_value=<yyyy>` |
| **Format** | Atom/OData XML, OData EDM primitive types |
| **Authentication** | None. It is public data. |
| **Cost** | Free |
| **Update cadence** | Every U.S. business day, around 4:15 PM ET |

Official documentation, verified before a line of code was written:

- [Treasury Daily Interest Rate XML Feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)
- [Daily Treasury Rate Archives](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives)

### This is the primary source, not a copy

The rates here come from Treasury and **nowhere else**. Not FRED, not Kaggle, not Yahoo
Finance, not a GitHub mirror, not a scraped copy — not even for a single missing day.

That matters more than it sounds. Aggregators re-publish Treasury data with their own
conventions: they rename fields, forward-fill gaps, silently drop maturities that did not
exist yet, and sometimes convert a discount rate into something labelled a yield. Each of
those is a small, invisible corruption. Taking it from the publisher means the numbers can
always be reconciled against an authoritative document, and each raw file's SHA-256 is
recorded so you can prove the bytes never changed.

### Who produces these numbers and how

Treasury's Office of Debt Management derives the par yield curve from **closing bid-side
market quotations** on the most recently auctioned securities, collected around 3:30 PM ET
by the Federal Reserve Bank of New York. A monotone-convex spline is fitted through those
observations to produce the published maturities. It is an official published curve, not a
trading feed.

---

## 3. How it gets here

```
  home.treasury.gov
        │  140 HTTP GETs, one per dataset-year
        ▼
  data/raw/us_treasury/<dataset>/<data_key>_<year>.xml     immutable, SHA-256 recorded
        │  parse XML, standardise dates, N/A → NULL, type numerics
        ▼
  data/processed/us_treasury/<dataset>.csv                 5 normalised tables
        │  COPY, then a generic unpivot
        ▼
  PostgreSQL: staging → treasury → analytics                267,517 observations
```

Nothing is invented at any step. The pipeline parses, types and reorganises — it never
calculates a rate, fills a gap, or smooths a series.

Full mechanics: [system-overview.md](system-overview.md) ·
[data-contract.md](data-contract.md) · [loading-contract.md](loading-contract.md)

---

## 4. The five datasets

| # | Dataset | Data key | From | Series | Observations |
|---|---|---|---|---|---|
| 1 | Par Yield Curve | `daily_treasury_yield_curve` | 1990 | 15 | 108,339 |
| 2 | Bill Rates | `daily_treasury_bill_rates` | 2002 | 28 | 105,204 |
| 3 | Long-Term Rates | `daily_treasury_long_term_rate` | 2000 | 3 | 19,965 |
| 4 | Par Real Yield Curve | `daily_treasury_real_yield_curve` | 2003 | 5 | 27,354 |
| 5 | Real Long-Term Rates | `daily_treasury_real_long_term` | 2000 | 1 | 6,655 |
| | **Total** | | | **52** | **267,517** |

---

### 4.1 Daily Treasury Par Yield Curve Rates

**`daily_treasury_yield_curve` · 1990-01-02 → 2026-08-11 · 9,159 days · 15 series**

The headline dataset, and the one most people mean when they say "the Treasury curve".

**What it is.** The yield at which a Treasury security of a given maturity would trade at
*par* — that is, the coupon rate that would make the bond worth exactly its face value
today. Quoted on a bond-equivalent, semi-annual coupon basis.

**Maturities and when each begins:**

| Series | Tenor | First observation | Days |
|---|---|---|---|
| `BC_1MONTH` | 1 month | 2001-07-31 | 6,259 |
| `BC_1_5MONTH` | 1.5 month | 2025-02-18 | 371 |
| `BC_2MONTH` | 2 month | 2018-10-16 | 1,954 |
| `BC_3MONTH` | 3 month | 1990-01-02 | 9,155 |
| `BC_4MONTH` | 4 month | 2022-10-19 | 952 |
| `BC_6MONTH` | 6 month | 1990-01-02 | 9,158 |
| `BC_1YEAR` | 1 year | 1990-01-02 | 9,158 |
| `BC_2YEAR` | 2 year | 1990-01-02 | 9,158 |
| `BC_3YEAR` | 3 year | 1990-01-02 | 9,158 |
| `BC_5YEAR` | 5 year | 1990-01-02 | 9,158 |
| `BC_7YEAR` | 7 year | 1990-01-02 | 9,158 |
| `BC_10YEAR` | 10 year | 1990-01-02 | 9,158 |
| `BC_20YEAR` | 20 year | 1993-10-01 | 8,219 |
| `BC_30YEAR` | 30 year | 1990-01-02 | 8,164 |
| `BC_30YEARDISPLAY` | 30 year | 1990-01-02 | 9,159 ⚠ **see [§8](#8-the-traps)** |

**Why the counts differ.** A maturity that did not exist has no rate. The 30-year has
8,164 observations rather than 9,158 because **Treasury discontinued the 30-year bond in
February 2002 and did not reintroduce it until February 2006** — a genuine ~4-year hole in
the long end of the curve, not a data defect. The 20-year began in 1993 and the short end
(1, 1.5, 2 and 4 month) was added progressively between 2001 and 2025 as Treasury started
issuing those bills.

**A latest observation, 2026-08-11:**

```
 1M     1.5M   2M     3M     4M     6M     1Y     2Y     3Y     5Y     7Y     10Y    20Y    30Y
 3.79   3.82   3.83   3.89   3.90   3.99   4.03   4.22   4.27   4.39   4.54   4.70   5.25   5.24
```

---

### 4.2 Daily Treasury Bill Rates

**`daily_treasury_bill_rates` · 2002-01-02 → 2026-08-11 · 6,157 days · 28 series**

Short-term government debt — bills, which pay no coupon and are sold at a discount to face
value.

**The structure is 7 tenors × 4 measures = 28 series:**

| Tenor | First observation | Note |
|---|---|---|
| 4 week | 2002-01-02 | |
| 6 week | 2025-02-18 | Newest tenor |
| 8 week | 2018-10-16 | |
| 13 week | 2002-01-02 | ≈ 3 month |
| 17 week | 2022-10-19 | |
| 26 week | 2002-01-02 | ≈ 6 month |
| 52 week | 2002-01-28 | **Only 5 days in 2002, then nothing until 2008.** The 1-year bill was discontinued in 2001 (those 5 days are the tail of the old issue) and reinstated in mid-2008 — 146 days that year, full years thereafter |

For each tenor, four numbers:

| Prefix | Measure | Basis |
|---|---|---|
| `ROUND_B1_CLOSE_<n>WK_2` | Closing discount rate of the specific quoted bill | bank discount, actual/360 |
| `ROUND_B1_YIELD_<n>WK_2` | The same bill, restated as a yield | coupon-equivalent |
| `CS_<n>WK_CLOSE_AVG` | Treasury's composite average discount rate | bank discount, actual/360 |
| `CS_<n>WK_YIELD_AVG` | The composite average, restated as a yield | coupon-equivalent |

**This dataset also carries reference data about the instrument itself** — the CUSIP and
maturity date of the bill actually quoted each day, stored in `treasury.bill_security`
(26,300 rows). That lets you tell a "4-week quote" apart from the specific security that
produced it.

> ⚠ **`CLOSE` and `YIELD` are not the same quantity.** See [§8](#8-the-traps).

---

### 4.3 Daily Treasury Long-Term Rates

**`daily_treasury_long_term_rate` · 2000-01-03 → 2026-08-11 · 6,655 days · 3 series**

Published in **tall format** — one row per date *per rate type*, so each date legitimately
carries three rows (6,655 × 3 = 19,965).

| `RATE_TYPE` | Kind | Meaning |
|---|---|---|
| `BC_20year` | nominal | The 20-year point, republished from the par curve |
| `Over_10_Years` | nominal | Average yield across all Treasuries with more than 10 years remaining |
| `Real_Rate` | **real** | Long-term real (inflation-adjusted) rate average |

> ⚠ A **real** rate sits inside an otherwise nominal feed. Averaging all three into one
> "long-term rate" is a mistake the tall format makes very easy.

**`EXTRAPOLATION_FACTOR`** appears on only 994 dates — **2002-02-19 to 2006-02-08**, exactly
the window when the 30-year bond did not exist and Treasury had to extrapolate the long end.
Stored per date in `treasury.long_term_extrapolation`. It is untyped in the source XML and
preserved as text.

---

### 4.4 Daily Treasury Par Real Yield Curve Rates

**`daily_treasury_real_yield_curve` · 2003-01-02 → 2026-08-11 · 5,906 days · 5 series**

The same idea as the par curve, but derived from **TIPS** — Treasury Inflation Protected
Securities, whose principal adjusts with CPI. These are yields *after* inflation.

| Series | Tenor | First observation | Days | % of days negative |
|---|---|---|---|---|
| `TC_5YEAR` | 5 year | 2003-01-02 | 5,906 | **29.8%** |
| `TC_7YEAR` | 7 year | 2003-01-02 | 5,906 | 20.7% |
| `TC_10YEAR` | 10 year | 2003-01-02 | 5,906 | 16.2% |
| `TC_20YEAR` | 20 year | 2004-07-27 | 5,515 | 10.5% |
| `TC_30YEAR` | 30 year | 2010-02-22 | 4,121 | 10.3% |

> **Negative values are normal, correct, and common.** The 5-year real yield was negative
> on nearly a third of all days in the sample, reaching **−1.91% on 2021-11-15**. A negative
> real yield means investors accepted a guaranteed loss of purchasing power for the safety
> of a Treasury. Any code that clips, floors, or treats these as errors is corrupting the
> data.

---

### 4.5 Daily Treasury Real Long-Term Rates

**`daily_treasury_real_long_term` · 2000-01-03 → 2026-08-11 · 6,655 days · 1 series**

A single composite: the unweighted average of bid real yields on all TIPS with more than 10
years remaining maturity. The source column is literally named `RATE`.

Its lowest point was **−0.64% on 2021-11-09**; it was negative on 574 days (8.6%).

This series is numerically identical to `Real_Rate` in dataset 4.3 — Treasury publishes the
same figure through two feeds. Both are loaded, under their own dataset, rather than one
being silently dropped.

---

## 5. Complete series inventory — all 52

| Dataset | Series | Kind | Quote basis | Tenor | Obs | First | Last |
|---|---|---|---|---|---|---|---|
| Bill | `ROUND_B1_CLOSE_4WK_2` | nominal | bank_discount_act360 | 4 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_4WK_2` | nominal | coupon_equivalent | 4 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_4WK_CLOSE_AVG` | nominal | bank_discount_act360 | 4 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_4WK_YIELD_AVG` | nominal | coupon_equivalent | 4 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_6WK_2` | nominal | bank_discount_act360 | 6 Week | 371 | 2025-02-18 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_6WK_2` | nominal | coupon_equivalent | 6 Week | 371 | 2025-02-18 | 2026-08-11 |
| Bill | `CS_6WK_CLOSE_AVG` | nominal | bank_discount_act360 | 6 Week | 371 | 2025-02-18 | 2026-08-11 |
| Bill | `CS_6WK_YIELD_AVG` | nominal | coupon_equivalent | 6 Week | 371 | 2025-02-18 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_8WK_2` | nominal | bank_discount_act360 | 8 Week | 1,954 | 2018-10-16 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_8WK_2` | nominal | coupon_equivalent | 8 Week | 1,954 | 2018-10-16 | 2026-08-11 |
| Bill | `CS_8WK_CLOSE_AVG` | nominal | bank_discount_act360 | 8 Week | 1,954 | 2018-10-16 | 2026-08-11 |
| Bill | `CS_8WK_YIELD_AVG` | nominal | coupon_equivalent | 8 Week | 1,954 | 2018-10-16 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_13WK_2` | nominal | bank_discount_act360 | 13 Week | 6,156 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_13WK_2` | nominal | coupon_equivalent | 13 Week | 6,156 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_13WK_CLOSE_AVG` | nominal | bank_discount_act360 | 13 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_13WK_YIELD_AVG` | nominal | coupon_equivalent | 13 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_17WK_2` | nominal | bank_discount_act360 | 17 Week | 952 | 2022-10-19 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_17WK_2` | nominal | coupon_equivalent | 17 Week | 952 | 2022-10-19 | 2026-08-11 |
| Bill | `CS_17WK_CLOSE_AVG` | nominal | bank_discount_act360 | 17 Week | 952 | 2022-10-19 | 2026-08-11 |
| Bill | `CS_17WK_YIELD_AVG` | nominal | coupon_equivalent | 17 Week | 952 | 2022-10-19 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_26WK_2` | nominal | bank_discount_act360 | 26 Week | 6,156 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_26WK_2` | nominal | coupon_equivalent | 26 Week | 6,156 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_26WK_CLOSE_AVG` | nominal | bank_discount_act360 | 26 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `CS_26WK_YIELD_AVG` | nominal | coupon_equivalent | 26 Week | 6,155 | 2002-01-02 | 2026-08-11 |
| Bill | `ROUND_B1_CLOSE_52WK_2` | nominal | bank_discount_act360 | 52 Week | 4,555 | 2002-01-30 | 2026-08-11 |
| Bill | `ROUND_B1_YIELD_52WK_2` | nominal | coupon_equivalent | 52 Week | 4,555 | 2002-01-30 | 2026-08-11 |
| Bill | `CS_52WK_CLOSE_AVG` | nominal | bank_discount_act360 | 52 Week | 4,561 | 2002-01-28 | 2026-08-11 |
| Bill | `CS_52WK_YIELD_AVG` | nominal | coupon_equivalent | 52 Week | 4,561 | 2002-01-28 | 2026-08-11 |
| Long-term | `BC_20year` | nominal | par_coupon_semiannual | 20 Year | 6,655 | 2000-01-03 | 2026-08-11 |
| Long-term | `Over_10_Years` | nominal | par_coupon_semiannual | Over 10 Years | 6,655 | 2000-01-03 | 2026-08-11 |
| Long-term | `Real_Rate` | **real** | average_real_yield | Over 10 Years | 6,655 | 2000-01-03 | 2026-08-11 |
| Real long-term | `RATE` | **real** | average_real_yield | Over 10 Years | 6,655 | 2000-01-03 | 2026-08-11 |
| Real curve | `TC_5YEAR` | **real** | par_coupon_semiannual | 5 Year | 5,906 | 2003-01-02 | 2026-08-11 |
| Real curve | `TC_7YEAR` | **real** | par_coupon_semiannual | 7 Year | 5,906 | 2003-01-02 | 2026-08-11 |
| Real curve | `TC_10YEAR` | **real** | par_coupon_semiannual | 10 Year | 5,906 | 2003-01-02 | 2026-08-11 |
| Real curve | `TC_20YEAR` | **real** | par_coupon_semiannual | 20 Year | 5,515 | 2004-07-27 | 2026-08-11 |
| Real curve | `TC_30YEAR` | **real** | par_coupon_semiannual | 30 Year | 4,121 | 2010-02-22 | 2026-08-11 |
| Par curve | `BC_1MONTH` | nominal | par_coupon_semiannual | 1 Month | 6,259 | 2001-07-31 | 2026-08-11 |
| Par curve | `BC_1_5MONTH` | nominal | par_coupon_semiannual | 1.5 Month | 371 | 2025-02-18 | 2026-08-11 |
| Par curve | `BC_2MONTH` | nominal | par_coupon_semiannual | 2 Month | 1,954 | 2018-10-16 | 2026-08-11 |
| Par curve | `BC_3MONTH` | nominal | par_coupon_semiannual | 3 Month | 9,155 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_4MONTH` | nominal | par_coupon_semiannual | 4 Month | 952 | 2022-10-19 | 2026-08-11 |
| Par curve | `BC_6MONTH` | nominal | par_coupon_semiannual | 6 Month | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_1YEAR` | nominal | par_coupon_semiannual | 1 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_2YEAR` | nominal | par_coupon_semiannual | 2 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_3YEAR` | nominal | par_coupon_semiannual | 3 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_5YEAR` | nominal | par_coupon_semiannual | 5 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_7YEAR` | nominal | par_coupon_semiannual | 7 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_10YEAR` | nominal | par_coupon_semiannual | 10 Year | 9,158 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_20YEAR` | nominal | par_coupon_semiannual | 20 Year | 8,219 | 1993-10-01 | 2026-08-11 |
| Par curve | `BC_30YEAR` | nominal | par_coupon_semiannual | 30 Year | 8,164 | 1990-01-02 | 2026-08-11 |
| Par curve | `BC_30YEARDISPLAY` ⚠ | nominal | par_coupon_semiannual | 30 Year | 9,159 | 1990-01-02 | 2026-08-11 |

---

## 6. What the numbers actually mean

### Units

**Every rate is in percent, exactly as Treasury published it.** `3.72` means 3.72%. It is
not a decimal fraction (0.0372) and not basis points (372). Nothing in this pipeline
rescales anything.

### The four quoting bases

This is the single most important concept in the dataset, and the schema forces you to
confront it — every series carries a non-null `quote_basis`.

| `quote_basis` | Used by | What it means |
|---|---|---|
| `par_coupon_semiannual` | Par curve, real curve, `BC_20year` | Bond-equivalent yield assuming semi-annual coupons. The standard "yield" quote. |
| `bank_discount_act360` | Bill `CLOSE` columns | Discount from face value, annualised on a 360-day year. **Systematically lower** than the equivalent yield. |
| `coupon_equivalent` | Bill `YIELD` columns | The same bill restated so it *is* comparable to a coupon yield. |
| `average_real_yield` | `Real_Rate`, `RATE` | Unweighted average of TIPS bid real yields, not a fitted curve point. |

### Nominal vs real

- **Nominal** (`rate_kind = 'nominal'`) — the actual rate paid, inflation included.
- **Real** (`rate_kind = 'real'`) — the rate after inflation, from TIPS.

The difference between a nominal yield and a real yield of the same maturity is
**breakeven inflation** — the market's implied inflation expectation. This pipeline
deliberately does **not** compute it; that is a derived analytic, and mixing derivations
into source data makes the source unauditable.

### Par yields are not spot rates

A par yield is the coupon rate that prices a bond at 100. A **zero-coupon (spot) rate** is
the rate for a single cash flow at one future date. They are different curves, and
discounting cash flows requires the second. Converting one to the other is *bootstrapping*
— a modelling step with its own assumptions, deliberately not performed here.

---

## 7. What the history looks like

### The 10-year Treasury by decade

| Decade | Days | Average | Low | High |
|---|---|---|---|---|
| 1990s | 2,503 | **6.66%** | 4.16% | 9.09% |
| 2000s | 2,501 | **4.46%** | 2.08% | 6.79% |
| 2010s | 2,501 | **2.40%** | 1.37% | 4.01% |
| 2020s (to date) | 1,653 | **3.09%** | 0.52% | 4.98% |

Thirty-six years of the great bond bull market and its reversal, in four rows.

### Extremes, nominal par curve

| Series | Minimum | On | Maximum | On | Mean |
|---|---|---|---|---|---|
| `BC_3MONTH` | **0.00%** | 2011-09-22 | 8.26% | 1990-03-09 | 2.81% |
| `BC_2YEAR` | 0.09% | 2021-02-05 | 9.05% | 1990-05-02 | 3.25% |
| `BC_10YEAR` | 0.52% | 2020-08-04 | 9.09% | 1990-05-02 | 4.25% |
| `BC_30YEAR` | 0.99% | 2020-03-09 | 9.18% | 1990-09-24 | 4.74% |

The 30-year low of 0.99% on 2020-03-09 is the COVID crash flight-to-quality; the 1990 highs
are the tail of the Volcker-era rate regime.

### Extremes, real (TIPS) curve

| Series | Minimum | On | Days negative |
|---|---|---|---|
| `TC_5YEAR` | **−1.91%** | 2021-11-15 | 1,759 (29.8%) |
| `TC_7YEAR` | −1.50% | 2021-11-09 | 1,223 (20.7%) |
| `TC_10YEAR` | −1.19% | 2021-08-03 | 955 (16.2%) |
| `TC_20YEAR` | −0.76% | 2021-11-09 | 579 (10.5%) |
| `TC_30YEAR` | −0.59% | 2021-12-03 | 424 (10.3%) |

### Curve inversion

The 2s10s spread (10-year minus 2-year) was **negative on 1,052 of 9,158 days — 11.5% of
the sample**, first on 1990-03-08 and most recently on 2024-09-05. An inverted curve, where
short money costs more than long money, has preceded every U.S. recession in this window.

As of 2026-08-11 the curve is positively sloped: 2Y 4.22%, 10Y 4.70%, **spread +0.48%**.

### The zero-rate era

Rates genuinely printed 0.00% during two episodes — post-financial-crisis (2008-12 through
2015) and COVID (2020–21):

| Series | Days at exactly 0.00% | First | Last |
|---|---|---|---|
| `BC_1MONTH` | 100 | 2008-12-10 | 2021-06-03 |
| `ROUND_B1_CLOSE_4WK_2` | 64 | 2008-12-10 | 2021-06-03 |
| `ROUND_B1_YIELD_4WK_2` | 64 | 2008-12-10 | 2021-06-03 |
| `CS_4WK_CLOSE_AVG` / `_YIELD_AVG` | 49 each | 2011-08-15 | 2021-05-21 |
| `BC_3MONTH` | 18 | 2011-09-22 | 2020-03-26 |

**These are real observations, not missing data.** Treating them as nulls would erase the
zero-rate era from the record.

---

## 8. The traps

Six ways this data will mislead you. Every one of them is handled in the database, but you
need to know they exist — especially if you ever read the CSVs directly.

### Trap 1 — `BC_30YEARDISPLAY` is a placeholder, not a yield

Treasury publishes this column as a **literal `0` on 5,256 dates**, from 1990-01-02 to
2010-12-31. It is not a 0.00% thirty-year yield; it is filler in a display field.

Loaded naively, it puts a 0% long bond into 21 years of history — and because every other
point on the curve is correct, the resulting curve looks entirely plausible. It would
silently destroy any duration, discounting or curve-shape calculation touching the long end.

**How it is handled:** stored with `value_status = 'source_placeholder'`,
`rate_percent = NULL`, and the published `0` retained in `source_value_percent` for audit.
Excluded from every `analytics` view. **Use `BC_30YEAR`.**

The rule lives in the data, not the code — `treasury.series.placeholder_zero_before`.

### Trap 2 — discount rate ≠ yield

On 2026-08-11:

| Tenor | Discount (act/360) | Coupon-equivalent | Gap |
|---|---|---|---|
| 4 week | 3.64% | 3.70% | 0.06% |
| 8 week | 3.68% | 3.75% | 0.07% |
| 13 week | 3.74% | 3.83% | 0.09% |
| 26 week | 3.83% | 3.96% | 0.13% |
| 52 week | 3.85% | **4.02%** | **0.17%** |

The gap widens with tenor and with the level of rates. Put a discount rate on a curve next
to par yields and the short end is understated by up to 17 basis points — enough to matter,
small enough that nobody notices.

**How it is handled:** `quote_basis` is mandatory on every series, and
`analytics.v_bill_rates_quoted` puts the two in separately named columns.

### Trap 3 — an exact `0` is not automatically missing

The mirror image of Trap 1. Short tenors really did print 0.00% (see §7). The distinguishing
test is a *leading unbroken run* of zeros over a column's entire early history — not the
mere presence of a zero.

### Trap 4 — nulls are mostly non-existence, not gaps

The par curve is ~19% null and bill rates ~36% null. Almost all of that is **maturities
that did not exist yet**: `BC_1_5MONTH` has 371 observations because it began in 2025, not
because 8,788 days are missing.

### Trap 5 — Treasury sometimes publishes an empty row

2010-10-11 (Columbus Day) exists in the feed with **every maturity NULL** and only the
placeholder zero. It counts as a date in the source but produces no rate observations,
which is why `analytics.v_par_yield_curve` has 9,158 rows against 9,159 source dates.

### Trap 6 — the `Id` columns are not keys

`Id`, `DailyTreasuryBillRateDataId` and `DailyTreasuryRealYieldCurveRateDataId` are Treasury
internal row identifiers. They are not ordered by date, they restart across years, and they
were **omitted entirely from the 2023 and 2024 responses** before returning in 2025. They
are kept in staging and never promoted to the core model.

---

## 9. How missing data is represented

> **A missing observation is NULL, and produces no row. Never zero, never the previous
> day's rate, never an interpolation.**

This is the rule the entire pipeline is built around. Absence of a rate and a rate of zero
are different facts about the world; collapse them and you get a curve that looks complete
and is wrong, with nothing downstream able to tell.

In practice:

| In the source | In the CSV | In the database |
|---|---|---|
| Value present | the number | one row, `value_status = 'observed'` |
| `N/A`, empty, or `m:null="true"` | empty cell | **no row at all** |
| Placeholder `0` (see Trap 1) | `0` preserved | one row, `value_status = 'source_placeholder'`, `rate_percent` NULL |

Of the 267,517 rows: **262,261 observed**, **5,256 placeholder**.

The database is therefore **sparse by design**. No row for a series on a date means Treasury
published nothing. If you need a dense grid, generate the date spine yourself — and
`analytics.v_series_coverage` tells you what to expect.

### Trading calendar

Treasury publishes on U.S. business days: weekdays excluding federal holidays **and Good
Friday** (the bond market closes, though it is not a federal holiday). Recorded ad-hoc
closures: 9/11 (Sep 11–14 2001), Reagan (2004-06-11), Hurricane Sandy (Oct 29–30 2012),
G.H.W. Bush (2018-12-05), Carter (2025-01-09), Nixon (1994-04-27).

With that calendar applied there are **zero unexplained business-day gaps** in any of the
five datasets.

---

## 10. Where the data physically lives

### On disk

```
data/
├── raw/us_treasury/           140 immutable XML files, ~55 MB
│   ├── par_yield_curve/         37 files, 1990–2026, 11.8 MB
│   ├── bill_rates/              25 files, 2002–2026, 16.0 MB
│   ├── long_term_rates/         27 files, 2000–2026, 15.8 MB
│   ├── real_yield_curve/        24 files, 2003–2026,  5.8 MB
│   └── real_long_term_rates/    27 files, 2000–2026,  5.1 MB
├── processed/us_treasury/     5 CSVs, ~5 MB
└── metadata/us_treasury/      manifest, schema report, validation, load verification
```

**`raw/` is immutable.** Once written, a file is never edited or patched — only replaced
wholesale by an explicit `--refresh`. Every file's SHA-256 is recorded in
`download_manifest.json` and re-verified before each load.

### In PostgreSQL

| Schema | Contents |
|---|---|
| `meta` | Lineage: 140 source files with checksums, load runs, 290 reconciliation results |
| `staging` | One table per CSV, Treasury's own column names — the arbiter when a number is disputed |
| `treasury` | The core model: `dataset` (5), `series` (52), `observation` (267,517), `bill_security` (26,300), `long_term_extrapolation` (994), `market_note` (1) |
| `analytics` | 9 views — **query these** |

Total database size: **64 MB**.

---

## 11. How to query it

Query `analytics`. It is the layer where the traps above are already excluded.

```sql
-- The curve today, wide
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;

-- One full curve, tidy and correctly ordered by tenor
SELECT series_code, tenor_label, rate_percent
FROM analytics.v_observation
WHERE data_key = 'daily_treasury_yield_curve'
  AND observation_date = '2026-08-11'
ORDER BY tenor_years;

-- 2s10s slope over the last year
SELECT observation_date, y2, y10, round(y10 - y2, 2) AS slope_2s10s
FROM analytics.v_par_yield_curve
WHERE observation_date >= CURRENT_DATE - 365
ORDER BY observation_date DESC;

-- Every day the curve was inverted
SELECT observation_date, y2, y10, round(y10 - y2, 2) AS spread
FROM analytics.v_par_yield_curve
WHERE y10 < y2 ORDER BY observation_date;

-- Bills with the two quoting bases kept apart
SELECT observation_date, tenor_label, discount_rate_act360, coupon_equivalent_yield, cusip
FROM analytics.v_bill_rates_quoted
WHERE tenor_label = '13 Week' ORDER BY observation_date DESC LIMIT 10;

-- Nominal and real 10-year side by side (two facts, NOT a breakeven calculation)
SELECT n.observation_date, n.y10 AS nominal_10y, r.y10 AS real_10y
FROM analytics.v_par_yield_curve n
JOIN analytics.v_real_yield_curve r USING (observation_date)
ORDER BY 1 DESC LIMIT 20;

-- What does each series contain, and when did it start?
SELECT * FROM analytics.v_series_coverage ORDER BY data_key, tenor_years;

-- Provenance: where did this exact number come from?
SELECT o.observation_date, o.rate_percent, o.source_file, f.source_url, f.sha256
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
JOIN meta.source_file f ON f.file_name = o.source_file
WHERE s.series_code = 'BC_10YEAR' AND o.observation_date = '2026-08-11';
```

Full view reference: [database-schema.md](database-schema.md).

---

## 12. How we know it is correct

The data is not trusted because it loaded without error. It is trusted because **58 checks
pass, and the checks are proven capable of failing**.

Every expected value is **recounted from the processed CSVs** — the database is never asked
what it should contain. A check that compares a database count to a database count passes on
a database that is entirely wrong. When the report says 108,339 observations for the par
curve, that number was derived twice, by two independent routes.

What is checked: every manifest file registered and checksum-verified; staging row counts
against the CSV; core counts against a fresh count of non-null cells; first date, last date
and distinct dates; a random sample of individual values byte-compared; placeholder handling;
duplicate keys; future dates; orphan rows; series that loaded nothing; plausibility bands;
bills maturing before their quote date; every view queryable; and the presence of the primary
keys, foreign keys and check constraints themselves.

```
self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
Verification PASS: 58/58 checks passed
```

The self-test adds 1.25 to one stored rate inside a transaction, requires the value check to
**fail**, then rolls back. A suite that has only ever reported PASS is equally consistent
with a suite that cannot detect anything.

Reports: `data/metadata/us_treasury/validation_report.md` (source data) and
`load_verification.md` (database), plus the queryable `meta.reconciliation`.

---

## 13. What this data is not

**It is not tradable prices.** These are official end-of-day indicative quotes. No bid/ask,
no size, not executable. You cannot backtest a trading strategy against them and claim
realistic fills.

**It is not a zero-coupon curve.** Par yields. Discounting cash flows needs bootstrapped
spot rates, which is a modelling step this pipeline does not perform.

**It contains no derived analytics.** No returns, duration, DV01, convexity, VaR, expected
shortfall, spreads, breakevens, PCA factors or stress scenarios. That is deliberate — mixing
modelling into acquisition makes source data unauditable. Those calculations belong to the
layer above this one.

**It is not the whole risk picture.** This is the risk-free curve. It has no credit spreads,
no swap rates, no corporate bonds, no positions, no counterparties.

**It is not real-time.** One observation per business day, published in the late afternoon
Eastern time.

---

## 14. Refreshing, and how revisions behave

Treasury publishes each business day around 4:15 PM ET.

```bash
python -m acquisition.download_us_treasury    # current year is always re-fetched
python -m treasury_db.load            # delete-and-reload, so reruns are safe
python tools/verify_load.py --self-test
```

Cached prior years are **not** re-fetched. That is a deliberate trade-off: it makes a daily
refresh take seconds rather than minutes, but it means **a Treasury restatement of a closed
year will not be picked up** unless you run with `--refresh`.

When a revision *is* loaded, `meta.source_file` is keyed on `(data_key, year, sha256)`, so
the revised file appears as a **new row** rather than overwriting the old one. The change
stays visible and auditable rather than silently replacing history.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **Par yield** | The coupon rate at which a bond of that maturity would trade at exactly face value. Treasury's headline curve. |
| **Spot / zero-coupon rate** | The rate for a single cash flow at one future date. Derived from par yields by bootstrapping. Not in this dataset. |
| **Bank discount basis** | Bill convention: discount from face value, annualised over 360 days. Systematically understates the true return. |
| **Coupon-equivalent yield** | A bill's discount restated so it is comparable to a coupon-bearing bond's yield. |
| **Bill** | Treasury debt of one year or less. No coupon; sold at a discount. |
| **Note** | Treasury debt of 2–10 years, pays semi-annual coupons. |
| **Bond** | Treasury debt over 10 years (20 and 30 year). |
| **TIPS** | Treasury Inflation Protected Securities — principal adjusts with CPI, so the yield is *real*. |
| **Nominal rate** | The rate as paid, inflation included. |
| **Real rate** | The rate after inflation. Can be, and often is, negative. |
| **Breakeven inflation** | Nominal minus real of the same maturity — the market's implied inflation expectation. Not computed here. |
| **Basis point (bp)** | One hundredth of a percent. 0.17% = 17 bp. |
| **2s10s** | The 10-year yield minus the 2-year yield. Negative = inverted curve. |
| **Inverted curve** | Short rates above long rates. Historically precedes recessions. |
| **CUSIP** | The 9-character identifier of a specific security. |
| **Tenor / maturity** | Time until the security repays principal. |
| **On-the-run** | The most recently auctioned security at a given maturity — what Treasury quotes. |

---

## Related documents

| Question | Document |
|---|---|
| How does the pipeline work end to end? | [system-overview.md](system-overview.md) |
| What are the precise source semantics and contracts? | [data-contract.md](data-contract.md) |
| What do the tables and views look like? | [database-schema.md](database-schema.md) |
| How do I get PostgreSQL running? | [postgres-setup.md](postgres-setup.md) |
| How do I add a maturity or a dataset? | [loading-contract.md](loading-contract.md) |
| Why is it built this way? | [architecture-decisions.md](architecture-decisions.md) |
| How was the source data acquired and validated? | [../data/README.md](../data/README.md) |
