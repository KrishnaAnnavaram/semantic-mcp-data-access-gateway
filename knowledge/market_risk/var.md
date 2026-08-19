# Value at Risk (VaR)

## Definition
Value at Risk (VaR) estimates the loss on a portfolio that is not expected to be
exceeded over a given horizon at a given confidence level, under normal market
conditions. A "1-day 99% VaR of $1M" means: on 99% of days, the 1-day loss is
not expected to exceed $1M. Here VaR is an **interest-rate** measure — the
portfolio is revalued under historical moves of the **U.S. Treasury par curve**.

## When to use / when not to use
- **Use** for a portfolio of interest-rate instruments whose value depends on the
  Treasury curve (the demo book of fixed-rate bonds).
- **Do not use** as a forecast of unprecedented moves — historical simulation
  only reflects the curve changes that occurred in the observation window.
- **Cannot compute without a portfolio.** VaR is a portfolio measure; with no
  positions available it can be explained but not calculated.

## Required inputs (canonical concepts)
1. `portfolio.positions` — the instruments and notionals held.
2. `portfolio.instrument_terms` — each bond's coupon, maturity and conventions.
3. `us_treasury.observation.history` — the observed par-curve history whose daily
   changes drive the simulation.

Each concept resolves to a physical source in the *Mapping status* section below.

## Observation window — how many rows a VaR calculation reads
Historical simulation uses a lookback of **250 trading days** of observed curve
changes. The window is set when the history is **fetched** —
`get_curve_history_matrix(trading_days=250)` — and `compute_historical_risk_tool`
then consumes whatever aligned matrix it is given; it has no window parameter of
its own. Rows outside that window are not read: requesting more does not refine
the number, it computes a *different* VaR over a different sample; requesting
fewer is a *different* estimate, not a rougher one. State the window whenever a
VaR figure is reported.

## Calculation (deterministic)
Computed by the risk engine's `compute_historical_risk_tool`, not by the model:
1. Take the book's positions and instrument terms.
2. Over the 250-day window, form each day's observed change in the par curve. For
   an h-day horizon use **observed h-day changes** — never a 1-day figure scaled
   by sqrt(h).
3. Apply each historical curve change to today's curve and **fully revalue** the
   book (bootstrap a discount curve, reprice every bond), giving a hypothetical
   P&L per scenario. Full revaluation captures convexity.
4. VaR at confidence c = the (1 − c) percentile loss of that P&L distribution
   (1st percentile for 99%), reported as a positive loss. Expected Shortfall is
   the mean of losses beyond it (see `expected_shortfall.md`).

## Assumptions & conventions
- Nominal par curve; `quote_basis = par_coupon_semiannual`. Par yields are **not**
  used directly as discount rates — a discount curve is bootstrapped first.
- Full revaluation, not a delta/DV01 approximation.
- Results are in the book's base currency (USD).

## Output & interpretation
A VaR and an ES figure as positive loss amounts, always reported with the
confidence level, the horizon, and the 250-day window. Because the book is
synthetic and the curve is real, the answer states both: a real methodology over
a **SYNTHETIC_DEMO** portfolio priced off **REAL_MARKET_DATA**.

## Limitations & refusal cases
- No portfolio available → explain the method and state that positions are
  required; do not produce a number.
- No counterparty or credit data exists, so there is no credit/counterparty VaR
  here — this is market (rate) risk only.
- Reported VaR is an analytical demonstration, not a regulatory figure.

## Mapping status
| Required input | Mapping | Status |
|---|---|---|
| `portfolio.positions` | `demo.position` | Available — Synthetic |
| `portfolio.instrument_terms` | `demo.instrument` | Available — Synthetic |
| `us_treasury.observation.history` | `analytics.v_observation` | Available — Real |

**Mode: CALCULATE + EXPLAIN** — via `compute_historical_risk_tool`. All required
inputs resolve; the portfolio is synthetic, the curve is real, and the answer
must say so.
