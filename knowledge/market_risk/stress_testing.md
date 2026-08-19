# Stress Testing & Scenario Analysis

## Definition
Stress testing estimates portfolio loss under severe but plausible curve moves,
independent of historical probability. Where VaR/ES describe normal-distribution
tails, a stress test applies a **specific shock** — hypothetical (e.g. "+100bp
parallel", a steepener) or a historical replay (e.g. the 1994 bond sell-off) — and
revalues the book to see what it loses if that scenario occurs.

## When to use / when not to use
- **Use** to size loss under a named shock, or to replay a real historical episode.
- **Do not** read a stress number as a percentile — it is a deterministic what-if,
  not a probability.
- **Cannot compute without a portfolio.**

## Two forms of shock
- **Hypothetical (`TENOR_VECTOR_BP`)**: an explicit tenor→basis-point vector —
  parallel ±100bp, steepener, flattener.
- **Historical replay (`HISTORICAL_REPLAY`)**: two real observation dates; the
  shock is the *difference between the two observed curves*, so nothing is invented.

## Required inputs (canonical concepts)
1. `portfolio.positions`
2. `portfolio.instrument_terms`
3. `scenario.definitions` — the shock vector or the replay date-pair.
4. `us_treasury.observation.history` — for a replay, the two dated curves.

## Observation window — how many rows a stress test reads
A **historical replay** reads exactly **2 observation dates** (start and end of
the episode); the dates between are never read. A **hypothetical** scenario reads
**1 observation date** — the base curve the shock is applied to. Neither form
consumes a time series.

## Calculation (deterministic)
Computed by the risk engine's `run_stress_tool`: revalue the book on the base curve,
again on the shocked curve, and take the difference —
`stress P&L = shocked value − current value` — per position and total. Full
revaluation, so convexity under the shock is captured.

`run_stress_tool` accepts **only an explicit tenor→basis-point vector**
(`shocks_bp_by_tenor_months`, keyed by tenor in months). Both forms are resolved
to that vector first: a defined scenario is fetched with `get_scenario`; a
historical replay fetches the two dated curves and differences them upstream. The
risk engine does not fetch market data or look up a scenario by id.

## Assumptions & conventions
- Nominal par curve, `par_coupon_semiannual`; discount curve bootstrapped first.
- A shock is a tenor→bp vector or a pair of real dates — never prose.
- Deterministic: no probability is attached to a scenario.

## Output & interpretation
A stress P&L (a loss or gain) per position and for the book, in USD, named against
the scenario. Replays are labelled with their real dates; the book is
**SYNTHETIC_DEMO**, the curve and replay dates are **REAL_MARKET_DATA**.

## Limitations & refusal cases
- No portfolio available → explain the method, do not produce a number.
- A what-if, not a percentile — do not report it as VaR.
- Only the defined scenarios and explicit tenor→bp vectors are supported; a shock
  that cannot be expressed either way is refused.

## Mapping status
| Required input | Mapping | Status |
|---|---|---|
| `portfolio.positions` | `demo.position` | Available — Synthetic |
| `portfolio.instrument_terms` | `demo.instrument` | Available — Synthetic |
| `scenario.definitions` | `demo.scenario` | Available — Synthetic |
| `us_treasury.observation.history` | `analytics.v_observation` | Available — Real |

**Mode: CALCULATE + EXPLAIN** — via `run_stress_tool`.
