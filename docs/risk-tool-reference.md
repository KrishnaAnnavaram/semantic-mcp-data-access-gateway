# Risk MCP tool reference

The complete surface of **risk-engine-mcp**: 42 tools, 7 resources, 8 prompts.

This document is checked against the code. `tests/test_risk_tool_inventory.py`
derives the inventory from the registered tools and fails if a tool is missing
from this file, if a tool here is not registered, or if a stated count drifts.
The code is authoritative; when they disagree, this file is what changes.

---

## The boundary, restated

| Server | Owns | Never |
|---|---|---|
| **market-risk-data-mcp** | Market and reference data: curves, history, provenance, the demo book, scenario definitions | Arithmetic. No duration, no VaR, no stress P&L |
| **risk-engine-mcp** | Deterministic quantitative mathematics | A database, a model, a network socket |

The engine holds **no market data**. Every tool below takes the curve and the
portfolio as typed arguments; fetch them from the data server first. That is what
makes "was the input wrong, or the maths?" a question with a mechanical answer.

---

## Conventions that apply to every tool

| Quantity | Unit | Sign |
|---|---|---|
| Rates | percent (`4.25` means 4.25%) | — |
| Rate shocks | basis points, additive on the par yield | — |
| Tenors | **months on the wire**, years inside the engine | — |
| P&L | currency | `stressed − base`; **negative is a loss** |
| DV01 | currency per basis point | `base − PV(+1bp)`; **positive for a long book** |
| Curve spread | basis points | `long tenor − short tenor`; negative is inversion |
| Butterfly | basis points | `2 × belly − short wing − long wing` |
| VaR / ES | currency | reported as **positive loss** amounts |
| Duration | years | — |
| Convexity | years² | `ΔP/P ≈ −D_mod·Δy + ½·C·Δy²`, Δy in decimal |
| Quantile | — | nearest rank, `k = ceil(α·N)`, no interpolation |

Every result carries the model manifest, a reproducibility block with a run
fingerprint, the data classification, an `interpretation` sentence saying what
the number is *not*, and a `warnings` list.

---

## 1. Valuation and bond analytics

| Tool | Answers |
|---|---|
| `price_portfolio_tool` | What is this book worth? Dirty present value, bootstrapped from the par curve. |
| `compute_bond_analytics_tool` | Everything about each bond: dirty/clean/accrued, YTM, current yield, Macaulay and modified duration, dollar duration, convexity, effective duration and convexity, and the duration vs duration+convexity approximation error at chosen shocks. |
| `compute_carry_roll_tool` | What does holding this earn if the curve does not move? Carry and roll-down, separately. |

**`compute_bond_analytics_tool`** returns two families of duration and they are
not interchangeable:

* **Yield-based** (Macaulay, modified, convexity) — derived from the bond's own
  yield to maturity, a single-rate approximation.
* **Effective** — from bumping the *par curve* and repricing in full.

They differ on a sloped curve, and the difference is information about curve
shape. The approximation table pairs a *curve* shock with the *effective*
measures, because pairing a curve shock with a yield-based duration leaves a
first-order bias the convexity term then overshoots.

`clean price + accrued interest = dirty price` holds to floating-point exactly:
accrued is computed from the same `w` that places the cash flows.

A **matured instrument is refused** (`NO_REMAINING_CASH_FLOWS`), not reported as
zero — its yield and duration are undefined, not zero.

**`compute_carry_roll_tool`** measures carry against the *forward* curve, so
carry is what the market already promises and roll-down is the extra the curve's
slope provides. On a flat curve roll is exactly zero. Coupons received in the
period are counted at face and **not reinvested**; the result says so.

---

## 2. Curve analytics

| Tool | Answers |
|---|---|
| `compute_curve_analytics_tool` | What shape is this curve? Par yields, discount factors, zero rates (continuous and semiannual), implied forwards, named spreads, butterflies, inversion diagnostics, level/slope/curvature. |
| `compute_rate_volatility_tool` | How much do these rates move, and together? Per-tenor volatility, 20/60/250-day rolling windows, covariance and correlation, and the most and least volatile windows in the sample. |

Named spreads: `3m2s`, `2s5s`, `2s10s`, `5s10s`, `5s30s`, `10s30s`, `2s30s`.
Named butterflies: `2s5s10s`, `2s10s30s`, `5s10s30s`.

**No silent extrapolation.** A tenor outside the curve's node range is refused
unless `allow_extrapolation=true`, and is then listed in `warnings`.

`compute_rate_volatility_tool` measures **realised rate volatility** in basis
points. It is not option-implied volatility; this system has no options. Changes
are absolute rather than proportional because a proportional change against a
front end that genuinely printed 0.00% is undefined.

---

## 3. Sensitivities

| Tool | Answers |
|---|---|
| `compute_dv01_tool` | Parallel DV01 by full revaluation. |
| `compute_key_rate_dv01_tool` | Sensitivity to each par node bumped individually. |
| `compute_rate_sensitivities_tool` | The whole picture in one call, with reconciliation. |
| `compute_risk_contributions_tool` | Component, marginal and incremental VaR or ES per position. |

`compute_rate_sensitivities_tool` returns an explicit **reconciliation block**:

* position DV01s sum to the portfolio DV01 **exactly** — one revaluation pass;
* key-rate DV01s sum to the parallel DV01 **approximately**, and the difference
  is reported in basis points of the parallel figure rather than distributed.

Bumping every node at once is a different perturbation from bumping each in
turn: the bootstrap is non-linear in the par rates.

`compute_risk_contributions_tool` gives **exact Euler decompositions**. Under the
nearest-rank convention VaR *is* one scenario's loss, so the positions' losses in
that scenario sum to it; ES is a mean over tail scenarios, so their mean losses
over those scenarios sum to it. Incremental figures answer a different question
and sum to nothing.

---

## 4. Stress: single scenarios

| Tool | Answers |
|---|---|
| `run_stress_tool` | Revalue under an explicit tenor→basis-point vector. The engine underneath all of these. |
| `run_rate_stress_tool` | A parallel shift, or a named curve-shape template. |
| `run_key_rate_stress_tool` | Move named curve nodes and nothing else. |
| `run_curve_twist_stress_tool` | Rotate the curve about a pivot. |
| `run_curve_curvature_stress_tool` | Sell off or rally the belly against the wings. |
| `run_shock_ladder_tool` | A ladder of parallel shocks with the approximation errors beside each. |

**The shock vector is always returned.** A scenario whose shape cannot be
inspected is a number nobody can check.

### Named templates

Control points as multiples of `severity_bp`. At severity 100 they reproduce the
canonical desk shapes exactly:

| template | 2Y | 5Y | 10Y | 30Y |
|---|---|---|---|---|
| `BEAR_STEEPENER` | +25 | +50 | +100 | +150 |
| `BULL_STEEPENER` | −150 | −100 | −50 | −25 |
| `BEAR_FLATTENER` | +150 | +100 | +50 | +25 |
| `BULL_FLATTENER` | −25 | −50 | −100 | −150 |
| `BELLY_SELLOFF` | +25 | +100 | +100 | +25 |
| `BELLY_RALLY` | −25 | −100 | −100 | −25 |
| `WINGS_SELLOFF` | +100 | +25 | +25 | +100 |
| `WINGS_RALLY` | −100 | −25 | −25 | −100 |

Steepener and flattener are named for what happens to the **curve**, not to the
direction of rates. A bear steepener sells off with the long end leading; a bull
steepener rallies with the front end leading. Both steepen.

### Interpolation between control points

* `linear_years` (default) — linear in tenor measured in years, held flat beyond
  the outermost control point.
* `node_rank` — linear in the tenor's position within the curve's node list.
  Reproduces the textbook twist table (2Y −100, 5Y −50, 10Y 0, 20Y +50,
  30Y +100) exactly.

Neither is more correct. Which one ran is recorded in the result.

### Severity labels

`MILD` 25bp · `MODERATE` 100bp · `SEVERE` 200bp · `EXTREME` 300bp.

**Project-defined, not a regulatory classification.** No supervisor prescribes
them; every result that uses them says so.

### A note on large single-node shocks

A +100bp bump at the 20-year alone leaves the 20s30s segment inverted by most of
a percent on a normally shaped Treasury curve, and the bootstrap's
no-negative-forward guard refuses to build it. That scenario is genuinely not
arbitrage-consistent. The engine reports it as a scenario that **did not run**,
with the reason, rather than pricing it anyway or dropping it from the table.

---

## 5. Stress: suites and analysis

| Tool | Answers |
|---|---|
| `run_stress_matrix_tool` | The full 21-scenario standard pack in one call, ranked worst-first. |
| `compare_stress_scenarios_tool` | Rank a caller-supplied set and name what drives the extremes. |
| `compute_stress_contributions_tool` | Decompose one scenario's loss across positions and the curve. |
| `explain_stress_loss_tool` | The same facts, arranged as an explanation. **No language model.** |
| `compute_stress_thresholds_tool` | The stress magnitude needed to reach each of several loss levels. |
| `run_concentration_stress_tool` | Shock the tenors the book is *measurably* most exposed to. |
| `run_scenario_severity_pack_tool` | One shape at every project-defined severity. |

### The standard pack — `standard_pack_2026_08_v1`

Parallel ±50, ±100, ±200 · bear steepener 100/200 · bear flattener 100/200 ·
bull steepener 100 · bull flattener 100 · twist ±100 about 10Y · belly selloff
100 · wings selloff 100 · key rate +100 at 2Y, 5Y, 10Y, 20Y, 30Y.

One base valuation and one key-rate pass serve all 21, so the ranking rests on
consistent inputs. Ties break by scenario name, so the order is stable between
runs.

### Attribution

**Position contributions are exact** — same revaluation pass as the portfolio
number, so they sum to it by construction.

**Tenor contributions are not, and the residual is reported.** A curve shock is
not separable. Two methods:

* `first_order` — key-rate DV01 × shock. One pass per node, reusable across
  scenarios. The residual is convexity plus cross terms.
* `isolated_reval` — one full revaluation per shocked node. A node whose isolated
  bump the bootstrap refuses is marked unattributable and its share stays in the
  residual.

Scaling the parts to close the residual would destroy the only diagnostic that
says how non-linear the scenario was.

---

## 6. Historical stress

| Tool | Answers |
|---|---|
| `run_historical_stress_tool` | Replay an observed curve move against today's book. |
| `run_historical_crisis_stress_tool` | Replay a named crisis window. |
| `find_worst_historical_stresses_tool` | Which observed moves would have hurt this book most? |

**No shock in this engine was ever written down.** Every historical shock is the
difference between two curves Treasury actually published, measured at the moment
of use. The crisis catalogue contains **dates only** — a test asserts that no
field of it holds a number.

### The catalogue — `documented_windows_v1`

| id | window | what happened |
|---|---|---|
| `1994_BOND_SELLOFF` | 1994-01-31 → 1994-11-30 | Large, sustained, broadly parallel rise. |
| `2008_GFC_LEHMAN` | 2008-09-12 → 2008-12-31 | Flight to quality; yields collapsed. A long book *gains*. |
| `2013_TAPER_TANTRUM` | 2013-05-01 → 2013-09-05 | Sharp bear steepening. |
| `2020_COVID_SHOCK` | 2020-02-19 → 2020-03-09 | Fastest collapse on record; bull flattening. |
| `2022_FED_TIGHTENING` | 2022-01-03 → 2022-10-24 | Very large bear flattening; the curve inverted. |
| `2023_REGIONAL_BANK_STRESS` | 2023-03-08 → 2023-03-24 | Violent bull steepening. |

Supply published curves covering the window. A crisis the supplied history does
not cover is refused with the gap named — a "2020 COVID shock" measured from
dates three weeks away is a different scenario wearing the same name.

A tenor present on the valuation curve but missing on a historical date is
refused by default (`missing_tenor_policy="reject"`), because leaving it
unshocked understates the loss silently. `"intersection"` accepts that trade-off
and lists what it left alone.

---

## 7. Reverse stress

| Tool | Answers |
|---|---|
| `run_reverse_stress_tool` | What move costs me X? |
| `find_limit_breach_stress_tool` | At what severity does a stated limit go amber, then red? |

Takes a scenario **shape** — parallel, a template, or a custom vector — and
solves for the multiple whose full revaluation loses the target. Brent's method
inside an explicit bracket.

* A target unreachable inside the interval is **refused with the reachable loss
  range named**, never answered by silently widening the search.
* A bound that leaves the bootstrap's domain shrinks by halving and the
  reduction is reported, so "no solution below our limit" is distinguishable from
  "no solution before the curve stopped making sense".
* Monotonicity is **checked**, not assumed. A non-monotone P&L means more than
  one shock reaches the target, and the result says so.

Limits are **explicit inputs**. This engine holds no risk policy and will not
supply one.

---

## 8. Distribution risk

| Tool | Method | Distribution | Revaluation |
|---|---|---|---|
| `compute_historical_risk_tool` | historical simulation | the empirical distribution of observed moves | full |
| `compute_parametric_risk_tool` | delta-normal | multivariate normal | none — linear key-rate approximation |
| `compute_monte_carlo_risk_tool` | Cholesky + Box-Muller | multivariate normal | full |
| `run_extreme_tail_simulation_tool` | four labelled tail models | scaled normal / stressed covariance / Student-t / empirical bootstrap | full |
| `run_volatility_regime_stress_tool` | stressed covariance | normal, estimated on the most volatile window | full |
| `run_rate_correlation_stress_tool` | correlation stress | normal, volatilities held, correlation replaced | full |
| `compare_risk_methods_tool` | all three side by side | — | — |

### The horizon rule

**Historical h-day risk uses observed h-day moves and never scales a one-day
figure by √h.** The shortcut assumes i.i.d. returns, which rate moves are not: it
understates exactly the clustered, trending episodes a risk number exists to
capture.

The parametric path *may* scale by √h if asked, because its own model already
assumes independent normal increments. The result names which path ran.

### Reproducibility

Monte Carlo draws come from explicit Box-Muller over a seeded uniform stream,
consumed factor by factor, scenario by scenario. Same inputs + same manifest +
same seed = same numbers, and the seed travels into the run fingerprint. A test
asserts both that the same seed reproduces and that a *different* seed does not —
a "deterministic" simulation that ignores its seed is also perfectly
reproducible.

A covariance that is not positive semidefinite is repaired by eigenvalue
clipping, and the repair — including how far the largest element moved — is
reported. It is never used as given.

`compare_risk_methods_tool` is a model-validation tool. The three methods are
**not expected to agree**: parametric far below historical means fat tails;
Monte Carlo far from parametric on a linear book means the simulation has not
converged.

---

## 9. Backtesting and attribution

| Tool | Answers |
|---|---|
| `backtest_var_tool` | Was the VaR any good? |
| `compute_pnl_attribution_tool` | Where did the money actually come from? |

### Backtesting

An exception is a loss **strictly greater** than the forecast; a loss exactly
equal to it is not.

`pnl_kind` is a required label and travels with the result:

* `ACTUAL` — realised P&L including intraday trading. What the business earned.
* `HYPOTHETICAL` — start-of-day book at end-of-day prices. What the *model*
  forecast, and what a coverage test is about.
* `MODEL_REVALUATION` — this engine's own repricing.

Tests: **Kupiec** unconditional coverage (χ²₁), **Christoffersen** Markov
independence (χ²₁), and their sum as **conditional coverage** (χ²₂). Tail
probabilities are exact closed forms, not table lookups.

Degenerate cases are reported as **not computable**, not as a pass — with zero
exceptions there are no transitions for the independence test to learn from, and
a p-value of 1.0 there would read as "independence confirmed".

The Basel traffic light is reported **only** at 250 observations and 99%, the
conditions it was calibrated for. Outside them the zone is null.

### P&L attribution

```
total P&L = carry + roll-down + rate move + position change + residual
```

Two residuals, and they mean different things:

* `residual` compares the four revalued effects with the total. It should be at
  **machine precision**; a non-zero value means the decomposition disagrees with
  itself.
* `rate_unexplained` is the first-order tenor split's shortfall against the rate
  effect. It is the book's **convexity**, it grows with the size of the move, and
  it is never scaled away.

`position_change` is `null` when no end-of-period snapshot is supplied. "Nothing
traded" and "we were not told" are different claims.

---

## 10. Portfolio level

| Tool | Answers |
|---|---|
| `compute_concentration_tool` | Where is the risk bunched up? |
| `evaluate_risk_limits_tool` | How close are we to our limits? |
| `compare_portfolio_risk_tool` | How do two books differ? |
| `analyze_hypothetical_trade_tool` | What does this trade do to my risk? |
| `analyze_rate_hedge_tool` | What notional neutralises this key-rate exposure? |

Concentration is measured on **absolute magnitudes**: a long and an offsetting
short are two concentrations, not an absence of risk. Reported as top share, top
three, Herfindahl index and effective position count (1/HHI).

Limit status boundaries, closed from below:

```
utilisation < amber          → GREEN
amber ≤ utilisation < 100    → AMBER
utilisation ≥ 100            → RED
```

A book sitting exactly on its limit has no headroom left, so it is RED.
Utilisation uses the absolute value, so a large short breaches a DV01 limit too.

`analyze_hypothetical_trade_tool` builds its "after" book by appending to a copy.
**Nothing stored is mutated.** `analyze_rate_hedge_tool` reports the effect on
*every* tenor, because a hedge that flattens one node and moves three others is
not a hedge — and a single-number answer would conceal exactly that. It is
deterministic risk analytics, not trading advice.

---

## 11. Regulatory

| Tool | Answers |
|---|---|
| `compute_frtb_girr_tool` | FRTB standardised-approach GIRR delta and curvature. |

Source: BCBS, *Minimum capital requirements for market risk*, chapter MAR21.

* **Sensitivities** — MAR21.19 PV01: the 1bp value change divided by 0.0001.
  This engine's key-rate DV01 is `base − bumped`, so the Basel sensitivity is its
  negative over 0.0001.
* **Vertices** — MAR21.8: 0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30 years. Curve
  nodes that are not vertices are allocated linearly between neighbours; the
  total sensitivity is preserved exactly, and the allocation is reported.
* **Risk weights** — MAR21.42: 1.7% / 1.7% / 1.6% / 1.3% / 1.2% / 1.1% / 1.1% /
  1.1% / 1.1% / 1.1%.
* **Correlation** — MAR21.46: `ρ = max(40%, exp(−3%·|Tₖ−Tₗ|/min(Tₖ,Tₗ)))`.
* **Scenarios** — MAR21.6: medium as given; high ×1.25 capped at 100%; low
  `max(2ρ−100%, 75%ρ)`. Capital is the largest of the three.
* **Curvature** — MAR21.99: a parallel shift at the bucket's highest delta risk
  weight (1.7%), with full revaluation.

**A positively convex long bond book scores zero curvature, and that is
correct.** Both CVR values come out negative and the charge floors at zero; Basel
does not credit the convexity benefit. The result says which case it was rather
than just reporting a zero.

**Vega is `null`, not `0.0`.** The book contains no optionality, so a vega charge
is not a number this system is entitled to produce. Every other risk class is
listed in `unsupported_risk_classes`. See
[capability-gaps.md](capability-gaps.md).

---

## Resources

| URI | Contents |
|---|---|
| `risk://model/manifest` | Every model version and numerical convention. |
| `risk://methodology/curve-construction` | Why par yields are bootstrapped. |
| `risk://scenarios/templates` | Every named shape as control points, plus the interpolation and severity rules. |
| `risk://scenarios/historical-crises` | The crisis catalogue — dates only. |
| `risk://methodology/risk-measures` | The four loss-distribution methodologies and why they disagree. |
| `risk://methodology/regulatory-girr` | Basel parameters, their source, and the unsupported classes. |
| `risk://capability-gaps` | What this engine cannot compute, and why. |

## Prompts

`risk_summary` · `stress_review` · `var_methodology` · `stress_matrix_review` ·
`reverse_stress_review` · `model_validation_review` · `pnl_attribution_review` ·
`regulatory_scope`

Each names the **order** the tools must run in, because the ordering is where the
mistakes live: pricing before the curve is bootstrapped, or a stress applied to a
portfolio nobody fetched.

---

## Errors

Well-formed requests that cannot be satisfied return structured JSON with an
error code, a category, a retryable flag, a message, and a suggested action.

`UNSUPPORTED_INSTRUMENT` · `UNSUPPORTED_DAY_COUNT` ·
`UNSUPPORTED_COUPON_FREQUENCY` · `NO_REMAINING_CASH_FLOWS` · `INVALID_CURVE` ·
`MISSING_CURVE_TENOR` · `INVALID_STRESS_VECTOR` · `UNKNOWN_SCENARIO_TEMPLATE` ·
`INSUFFICIENT_HISTORY` · `INVALID_CONFIDENCE_LEVEL` · `INVALID_HORIZON` ·
`INVALID_COVARIANCE_MATRIX` · `MONTE_CARLO_FAILURE` ·
`NO_REVERSE_STRESS_SOLUTION` · `SOLVER_DID_NOT_CONVERGE` ·
`INSUFFICIENT_BACKTEST_DATA` · `MISSING_PNL_SERIES` · `INVALID_VAR_FORECAST` ·
`INVALID_LIMIT` · `UNSUPPORTED_REGULATORY_SCOPE` ·
`MISSING_REQUIRED_MARKET_DATA` · `UNSUPPORTED_CRISIS_SCENARIO` ·
`INCONSISTENT_PORTFOLIOS`

**Nothing is silently approximated.** A convention this engine does not implement
is refused by name.
