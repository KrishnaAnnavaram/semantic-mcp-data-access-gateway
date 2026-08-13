# Yield Curve & Interest-Rate Risk

## Definition
The yield curve is the set of interest rates across maturities (tenors) for a
single issuer on a single day — here, U.S. Treasury par yields from 1 month to
30 years. Its **level** (how high rates are), **slope** (short vs long) and
**changes over time** are the raw material for interest-rate market risk.

## Observation window — how many rows a curve task reads
A curve **snapshot** reads exactly **1 observation date**: one day's rates across
every tenor. It is a cross-section, not a time series, so no history is read.

A curve **slope** (e.g. 2s10s) also reads **1 observation date** — two tenors on
that single date.

Reading a curve's **level or slope over time** is a different task: it reads
**250 trading days**, roughly one trading year of daily observations, which is
enough to read a trend at daily frequency without changing its shape.

## Key measures
- **Level**: the rate at a given tenor (e.g. the 10-year yield).
- **Slope (steepness)**: long minus short, in basis points. The classic gauge is
  **2s10s** = y10 − y2. A negative slope is an *inverted* curve.
- **DV01 / PV01**: change in value of a rate position for a 1 basis-point move
  (see `sensitivities_greeks.md`).
- **Rate VaR / ES**: the VaR/ES measures applied to the distribution of daily
  *rate changes* at a tenor, rather than to asset-price returns.

## Method (dry)
- Slope: `slope_bps = (long_rate − short_rate) × 100`.
- Rate VaR (historical, single tenor): take the tenor's rate history, compute
  daily changes Δr = r_t − r_{t-1}, and take the (1 − c) percentile of the loss
  distribution for the position's DV01 exposure. See `var.md` for the percentile
  step and `expected_shortfall.md` for the tail average.
- Parallel-shift stress: reprice under a curve where every tenor moves by the
  same shock (e.g. +100 bp), per `stress_testing.md`.

## Data required
1. **Yield curve** — one day's rates across tenors (`analytics.v_par_yield_curve`,
   via `get_yield_curve`); use the `real` kind for TIPS.
2. **Rate history** — a tenor's daily series for change-based VaR/ES/volatility
   (`analytics.v_observation`, via `get_rate_history`).
3. **Series catalogue** — available tenors and their quoting basis
   (`analytics.v_series`, via `list_series`).

## Notes
- Rates are quoted in **percent**; a "basis point" is 0.01 percentage points.
- Never mix quoting bases on one curve — a bill discount rate and a par coupon
  yield are different quantities (`quote_basis` distinguishes them).
- This agent has rate data only: it can compute curve level/slope and rate-based
  VaR/ES/DV01, but not CVA/RWA/PD-LGD-EAD, which need portfolio and counterparty
  data it does not have.
