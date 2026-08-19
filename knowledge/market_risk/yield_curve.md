# Yield Curve & Interest-Rate Levels

## Definition
The yield curve is the set of interest rates across maturities (tenors) for a
single issuer on a single day — here, U.S. Treasury par yields from 1 month to
30 years. Its **level** (how high rates are), **slope** (short vs long) and
**changes over time** are the raw material for interest-rate market risk.

## When to use / when not to use
- **Use** to read the curve level at a tenor, the slope between two tenors, or how
  either has moved over time.
- **No portfolio is required** — this is a direct read of market data, unlike
  VaR/DV01/stress which revalue a book.
- **Do not** mix quoting bases on one curve (see Assumptions).

## Key measures
- **Level**: the rate at a given tenor (e.g. the 10-year yield).
- **Slope (steepness)**: long − short, in basis points. The classic gauge is
  **2s10s** = y10 − y2. A negative slope is an *inverted* curve.
- **Level or slope over time**: the same measures read across a history window.

## Required inputs (canonical concepts)
1. `us_treasury.par_yield.curve` — one day's rates across tenors (or the `real`
   kind for TIPS).
2. `us_treasury.observation.history` — a tenor's daily series, for over-time reads.
3. `us_treasury.series_catalogue` — available tenors and their quoting basis.

## Observation window — how many rows a curve task reads
A curve **snapshot** reads **1 observation date** (a cross-section across tenors).
A **slope** also reads **1 date** (two tenors on it). Reading level or slope
**over time** reads **250 trading days** — one trading year at daily frequency,
enough to read a trend without changing its shape.

## Calculation (deterministic)
A direct read, not a risk-engine call:
- Level / snapshot: `get_curve` (returns the whole curve for a date; pick a tenor
  from its points).
- Slope: **derived** from `get_curve` — `slope_bps = (long_rate − short_rate) × 100`
  (there is no dedicated slope tool; take two tenors off the curve).
- Over time: `get_rate_history` for named series, or `get_curve_history_matrix`
  for several tenors aligned by date.

**Tool identifiers.** The tools do not use `y10`/`2s10s`-style keys — those are
human labels. `get_rate_history` takes **`series_codes`** (e.g. `BC_10YEAR`);
`get_curve_history_matrix` and the risk tools take **`tenors_months`** (10Y =
`120.0`). Resolve a labelled tenor to a series code or a month value before
calling.

## Assumptions & conventions
- Rates are in **percent**; a basis point is 0.01 percentage points.
- Never mix quoting bases on one curve — a bill discount rate and a par coupon
  yield are different quantities (`quote_basis` distinguishes them).
- Par yields are not zero/discount rates; do not discount cashflows off them
  directly (that belongs to pricing, which bootstraps a discount curve).

## Output & interpretation
Rates in percent and slopes in basis points, for a stated date. A negative 2s10s
means an inverted curve. All values are **REAL_MARKET_DATA** from Treasury.

## Limitations & refusal cases
- Rate data only. This curve read cannot produce portfolio metrics (VaR, DV01,
  stress) on its own — those need the book and the risk engine.

## Mapping status
| Required input | Mapping | Status |
|---|---|---|
| `us_treasury.par_yield.curve` | `analytics.v_par_yield_curve` (`v_real_yield_curve` for TIPS) | Available — Real |
| `us_treasury.observation.history` | `analytics.v_observation` | Available — Real |
| `us_treasury.series_catalogue` | `analytics.v_series` | Available — Real |

**Mode: CALCULATE + EXPLAIN** — direct read (`get_curve`, `get_rate_history`,
`get_curve_history_matrix`); slope derived from `get_curve`; no portfolio, no
risk engine.
