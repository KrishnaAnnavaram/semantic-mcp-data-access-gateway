# Expected Shortfall (ES / CVaR)

## Definition
Expected Shortfall (ES), also called Conditional VaR (CVaR), is the average loss
*given that* the loss has exceeded the VaR threshold. Where VaR answers "how bad
on a normal day", ES answers "if it goes past that, how bad on average". It is
the Basel/FRTB market-risk measure because it captures tail severity VaR ignores.
Here it is computed on the same interest-rate revaluation as VaR (see `var.md`).

## When to use / when not to use
- **Use** alongside VaR to describe the *severity* of the tail, not just its edge.
- **Do not use** as a forecast of unprecedented moves — like VaR it only reflects
  the curve changes in the observation window.
- **Cannot compute without a portfolio** — it is a portfolio measure.

## Required inputs (canonical concepts)
Identical to VaR — ES is read off the same P&L distribution:
1. `portfolio.positions`
2. `portfolio.instrument_terms`
3. `us_treasury.observation.history`

## Observation window — how many rows an ES calculation reads
The same **250 trading days** as VaR: ES re-reads the tail of the *same* P&L
sample, so it consumes no additional history. Requesting more rows than the
window does not deepen the tail estimate; it substitutes a different sample.

## Calculation (deterministic)
Returned by the risk engine's `compute_historical_risk_tool` in the same pass as VaR:
1. Build the P&L distribution exactly as for VaR (full revaluation of the book
   under each observed curve change over the window).
2. Find VaR at confidence c = the (1 − c) percentile loss.
3. **ES = the mean of all losses beyond VaR_c**  →  `ES_c = average(loss | loss > VaR_c)`.

## Assumptions & conventions
- Same inputs and conventions as VaR: nominal par curve, `par_coupon_semiannual`,
  full revaluation off a bootstrapped discount curve.
- FRTB references **97.5% ES** (calibrated near 99% VaR); confidence is a parameter.
- Result in the book's base currency (USD).

## Output & interpretation
An ES figure as a positive loss amount, reported with confidence, horizon and the
250-day window. ES ≥ VaR at the same confidence, always. As with VaR, the answer
states that the book is **SYNTHETIC_DEMO** and the curve is **REAL_MARKET_DATA**.

## Limitations & refusal cases
- No portfolio available → explain the method, do not produce a number.
- ES is a *coherent* measure (sub-additive: diversification never increases it),
  unlike VaR — a modelling property, not a data one.
- Analytical demonstration, not a regulatory figure.

## Mapping status
| Required input | Mapping | Status |
|---|---|---|
| `portfolio.positions` | `demo.position` | Available — Synthetic |
| `portfolio.instrument_terms` | `demo.instrument` | Available — Synthetic |
| `us_treasury.observation.history` | `analytics.v_observation` | Available — Real |

**Mode: CALCULATE + EXPLAIN** — via `compute_historical_risk_tool` (returns VaR and ES together).
