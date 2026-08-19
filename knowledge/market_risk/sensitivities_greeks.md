# Sensitivities & DV01

## Definition
A sensitivity measures how much a position's value changes for a small move in a
risk factor. Where VaR/ES give a loss distribution, a sensitivity gives the
*slope* — the day-to-day number a rates desk watches to know its directional
exposure and to hedge it. For an interest-rate book the governing measure is
**DV01**.

## When to use / when not to use
- **Use** DV01 to size interest-rate exposure and to hedge — per position, per
  key tenor, or for the whole book.
- **Do not use** it for large moves — DV01 is a local (first-order) measure;
  VaR/ES and stress cover large moves.
- **Cannot compute without a portfolio.**

## The measures that apply here
- **DV01 / PV01**: change in value for a **1 basis-point** move in rates. The
  primary interest-rate sensitivity.
- **Key-rate DV01**: DV01 attributed to each curve node (2/5/10/20/30Y), showing
  *where* on the curve the exposure sits.
- Delta, vega, gamma, theta are equity/FX/option Greeks. **The demo book holds
  only fixed-rate bonds, so these do not apply** — the agent should say so rather
  than report them.

## Required inputs (canonical concepts)
1. `portfolio.positions`
2. `portfolio.instrument_terms`
3. `us_treasury.par_yield.curve` — one dated curve to bump and revalue against.

## Observation window — how many rows a DV01 calculation reads
DV01 is a bump-and-revalue on a **single curve**, so it reads exactly **1
observation date**. No time series is consumed: the sensitivity is a property of
the position against today's curve, not of how the curve has moved. Requesting
history for a DV01 returns data the calculation never reads.

## Calculation (deterministic)
Computed by the risk engine's `compute_dv01_tool` by **full revaluation** (not an
analytic approximation, so convexity is captured): revalue the book on the base
curve, again on the curve shifted 1bp, and difference. Use
`compute_key_rate_dv01_tool` to attribute DV01 to each curve node — key tenors are
supplied as `key_tenors_months` (2/5/10/20/30Y = 24/60/120/240/360).

## Assumptions & conventions
- Nominal par curve, `par_coupon_semiannual`; a discount curve is bootstrapped
  first — par yields are not used directly as discount rates.
- 1bp shift; result in currency per basis point (USD/bp).

## Output & interpretation
DV01 per position and for the total book, optionally per key tenor. A DV01 of
$10,000 means roughly $10,000 of P&L per 1bp parallel move. Reported for a
**SYNTHETIC_DEMO** book priced off the **REAL** curve.

## Limitations & refusal cases
- No portfolio available → explain the method, do not produce a number.
- Local first-order measure — not valid for large moves.
- No options/equities in the book → no vega/gamma/theta/delta to report.

## Mapping status
| Required input | Mapping | Status |
|---|---|---|
| `portfolio.positions` | `demo.position` | Available — Synthetic |
| `portfolio.instrument_terms` | `demo.instrument` | Available — Synthetic |
| `us_treasury.par_yield.curve` | `analytics.v_par_yield_curve` | Available — Real |

**Mode: CALCULATE + EXPLAIN** — via `compute_dv01_tool` (and
`compute_key_rate_dv01_tool` for per-node key-rate DV01).
