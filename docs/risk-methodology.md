# Risk methodology

What the risk engine computes, how, and what the numbers do not mean.

Every convention here is part of the model definition, not implementation
detail. Two engines can both honestly report "99% historical VaR" and disagree
because one interpolates the percentile and the other takes an order statistic.
Naming the convention is what makes such a disagreement visible instead of
mysterious.

The authoritative machine-readable version is `risk://model/manifest`.

---

## 1. The mistake this design exists to prevent

**Treasury publishes a par yield curve, not zero-coupon rates.**

A 10-year CMT of 4.25% is the coupon a ten-year bond would need in order to
trade at 100. It is *not* the rate at which a ten-year cash flow discounts.
Treasury states this explicitly and does not publish a daily zero curve.

Using par yields as discount rates is the most common way to get bond analytics
wrong, and it fails quietly: prices look plausible, DV01 has the right sign, and
everything is off by an amount that grows with maturity and curve slope.

So curve construction is a mandatory, named, versioned step:
**`par_bootstrap_logdf_interp_v1`**.

The golden test that guards it is `test_sloped_curve_par_bond_still_prices_to_par`.
A bond paying the 10-year par coupon must be worth exactly 100 on an
upward-sloping curve. On a flat curve, par-as-spot happens to give roughly the
right answer, which is why the test uses a sloped one.

---

## 2. Curve construction

At semiannual node *n* with annual par rate *c*, the par-bond identity

```
1 = (c/2) · Σ_{i=1..n} D_i  +  D_n
```

rearranges to the forward recurrence

```
D_n = (1 − (c/2) · Σ_{i=1..n−1} D_i) / (1 + c/2)
```

Treasury publishes fourteen tenors; the bootstrap needs sixty semiannual nodes,
so par rates are first **interpolated linearly against tenor**. Beyond the last
node, par rates are held **flat** rather than extrapolated — a linear
extrapolation of the long end can go negative or implausibly steep, and a curve
that invents a 40-year point is worse than one that repeats the 30.

Between bootstrapped nodes, discount factors interpolate **linearly in log D**.
Past the final node, the last observed forward rate is held flat.

### Guards

The build aborts if a discount factor is non-positive, or if it *rises* with
maturity (a negative forward rate). Both indicate an input curve the bootstrap
cannot price consistently, and continuing would produce plausible-looking
numbers from it.

### What it is not

A transparent, reproducible construction — not a reproduction of Treasury's
monotone-convex methodology, which Treasury does not publish in full. Values are
**model-implied**.

---

## 3. Pricing — `fixed_coupon_full_pv_v1`

Scope: semiannual fixed-rate bonds. An instrument whose conventions are not
implemented is **rejected**, not approximated — silently pricing a floating-rate
note with a fixed-coupon engine produces a number, and the number is wrong.

Cash flows are generated **backwards from maturity**. Rolling forward from issue
accumulates drift that leaves the final coupon on the wrong day.

### Time basis, and why it is not calendar days

Cash-flow times are measured in **coupon periods** (ACT/ACT ICMA, quasi-coupon):

```
t_i = (i + 1 − w) / frequency,   w = elapsed fraction of the current period
```

This is forced by the bootstrap. The curve places discount factors at exactly
0.5, 1.0, 1.5 years. If the pricer measured a coupon 184 days away as
t = 0.5041 in ACT/365 calendar time, it would discount at a point the curve was
not built for, and a bond paying exactly the par coupon would price to **99.96
instead of 100**.

That 3.6bp error is small, silent, systematic, and grows with maturity and
slope. Aligning the two conventions removes it by construction. This was caught
by the golden test, not by inspection.

### Dirty, not clean

The value returned is the full present value of remaining cash flows. Risk
figures are differences of that value, so the accrued component cancels.
Reporting it as a clean price without computing accrued would be a quiet lie.

---

## 4. Sensitivities — `full_revaluation_bump_v1`

**DV01** — bump the par curve in parallel, rebuild the discount curve, reprice.
`DV01 = V_base − V_bumped`, positive for a conventional long fixed-rate book.

Full revaluation rather than an analytic approximation, because convexity is
exactly what matters on a 30-year bond. The demo shows it: +100bp costs
1.94M while −100bp gains 2.21M, against a linear estimate of 2.07M either way.
That asymmetry is real and an analytic DV01 would hide it.

**Key-rate DV01** — one par node bumped at a time. No tent, no smoothing. A
triangular shape spread over neighbouring tenors is common but needs the shape
stated to be reproducible; a single-node bump is unambiguous. Bumping a
non-node is rejected, since it would perturb an interpolated value rather than
an input.

Key-rate DV01s sum to approximately the parallel DV01 — approximately, because
bumping five nodes is not the same perturbation as shifting all fourteen.

---

## 5. Historical VaR and Expected Shortfall

`absolute_par_shock_full_revaluation_v1`

1. Observed **h-day absolute changes** in par yields, per tenor.
2. Add each change vector to today's curve.
3. Rebuild the discount curve and reprice the book under each scenario.
4. `VaR` = nearest-rank quantile of the loss distribution.
5. `ES` = mean of losses at or beyond VaR.

### Both from one pass

VaR and ES come from a single revaluation of the same scenario set. Computing
them separately would double the work and risk them disagreeing about one
distribution.

### The quantile convention — `nearest_rank_v1`

```
k = ceil(α · N),  1-indexed;  VaR = max(0, L_(k))
```

Pinned and named because implementations genuinely differ: NumPy offers nine
interpolation methods and its default is not this one. Leaving it to a library
default would make the number depend on which version happened to be installed.

### Horizons

An h-day VaR uses changes **observed over h days**. Never a 1-day figure scaled
by √h. That shortcut assumes independent, identically distributed returns, which
rate moves are not — it understates precisely the clustered, trending episodes a
risk number exists to capture. `test_ten_day_horizon_uses_observed_changes_not_sqrt_scaling`
asserts the two differ.

### Not a regulatory figure

99% / 1-day / 250-observation VaR is an **analytical demonstration**. Basel's
revised market-risk framework moved the internal-model approach from VaR toward
Expected Shortfall, and older VaR-based requirements specify a 10-day horizon.
Returning both measures is deliberate; claiming regulatory equivalence would not
be.

---

## 6. Stress

Scenarios are **vectors, not prose**. `{"120": 100}` is a scenario;
`{"scenario": "bad recession"}` is not.

`TENOR_VECTOR_BP` carries an explicit tenor→basis-point map.

`HISTORICAL_REPLAY` names two real observation dates. The data server returns
both curves; the **host** differences them; the risk engine receives an ordinary
shock vector and neither knows nor cares that it came from history. The data
server performs no arithmetic, and the engine needs no market access.

Replays currently defined, with the moves the data actually contains:

| Scenario | Date | 10-year move |
|---|---|---|
| Bond massacre | 1994-04-04 | **+39 bp** |
| Fed announces Treasury QE | 2009-03-18 | **−51 bp** |
| COVID dash for cash | 2020-03-17 | **+29 bp** |

---

## 7. Reproducibility

```
run_fingerprint = SHA256( canonical_json(inputs) ‖ canonical_json(model_manifest) )
```

Both halves are required. The same inputs under a changed quantile convention is
a different calculation and must not collide with the original — asserted by
`test_fingerprint_changes_when_the_model_manifest_changes`.

Canonicalisation sorts keys and renders decimals as strings, so the same logical
input always produces the same bytes.

Every result also carries `portfolio_snapshot_sha256`, `market_snapshot_sha256`
and the `dataset_snapshot_id` from the data layer — enough to reconstruct which
book, which rates and which code produced a number months later.

---

## 8. Bond analytics — `icma_quasi_period_analytics_v1`

### The clean/dirty split

`pricing.py` returns the **dirty** value: the full present value of remaining
cash flows. `bond_analytics.py` is where the accrued half is actually computed,
from the same `w` that places the cash flows, so

```
clean price + accrued interest = dirty price
```

holds to floating point rather than approximately. Accrued interest is
`coupon × w` on the ACT/ACT ICMA quasi-coupon basis: elapsed days over the days
in the current quasi-coupon period.

### Yield to maturity

Solved, not approximated. `price_from_yield` discounts every remaining flow at a
single rate on the **same period basis the pricer uses**, and Brent's method
finds the rate that reproduces the dirty value. Convergence is reported, and a
price that has no yield inside the search interval is refused rather than
answered with the interval's edge.

### Two families of duration, and why both

| measure | perturbation | when to use |
|---|---|---|
| Macaulay, modified, convexity | the bond's **own yield** | comparing bonds; the number a desk quotes |
| effective duration, effective convexity | a parallel shift of the **par curve**, repriced in full | measuring what a curve move actually does |

In period units with `z = 1 + y/f` and `n` the period exponent:

```
P         = Σ CF_n · z^-n
Macaulay  = Σ (n/f) · CF_n · z^-n / P
Modified  = Macaulay / z
Convexity = Σ n(n+1) · CF_n · z^-n / (P · z² · f²)      [years²]
```

Effective measures use a central difference at `effective_bump_bp` (25bp by
default), rebootstrapping each side.

They differ on a sloped curve and that difference is information, not error. The
price-approximation table therefore pairs a **curve** shock with the
**effective** measures: pairing it with modified duration leaves a first-order
bias that the convexity term then overshoots, making the "improved"
approximation worse than the plain one at small shocks.

### The zero bound

A 25bp down-shift of a curve trading at 10bp lands below zero, where the
bootstrap's no-negative-forward guard refuses to build. The engine reports that
by name and suggests a smaller bump. A genuinely negative par curve is likewise
refused: it implies discount factors above one that rise with maturity, which is
correct economics in a negative-rate regime and indistinguishable to this guard
from an arbitrage-inconsistent input. That is a stated scope limit, not a silent
one.

---

## 9. Carry and roll — `forward_value_carry_static_curve_roll_v1`

```
carry = V_forward(t1) + cash received − V(t0)
roll  = V_static(t1)  − V_forward(t1)
```

Carry is measured against the **forward** curve — the no-arbitrage benchmark, so
a position earning exactly its carry has earned nothing the market did not
already promise. Roll-down is the extra the curve's slope provides, and is
exactly zero on a flat curve.

For a remaining flow at `τ_j` from `t0` and `t_j` from `t1`, the difference
`τ_j − t_j` is the same constant for every remaining flow of that instrument.
Call it `Δt`; then `V_forward(t1) = Σ CF_j · D0(τ_j) / D0(Δt)`, exactly. Each
instrument carries its own `Δt`, because each has its own coupon dates.

**Coupons received are counted at face, not reinvested.** Over a coupon-free
window that makes carry exactly `V(t0) · (1/D(Δt) − 1)`, which is what the golden
test asserts to twelve decimal places.

---

## 10. Curve analytics — `bootstrapped_zero_forward_v1`

Four numbers get called "the rate", and confusing any two is the defining error
of this subject: par yield, discount factor, zero rate, forward rate. Zero and
forward rates here are derived from the **bootstrapped** discount curve, never
from the par yields directly.

```
zero (semiannual)    z(t) : D(t) = (1 + z/2)^(-2t)
forward (continuous) f    = (ln D(t1) − ln D(t2)) / (t2 − t1)
spread                    = long-tenor yield − short-tenor yield        [bp]
butterfly                 = 2 × belly − short wing − long wing          [bp]
```

Both sign conventions have a defensible opposite, so both are in the manifest.
No tenor outside the curve's node range is answered without explicit permission.

---

## 11. Scenario generation — `control_point_templates_linear_in_years_v1`

Named shapes are **control points as multiples of a severity**, and the resolved
vector always travels with the result. Between control points, `linear_years`
(default) interpolates in tenor measured in years; `node_rank` interpolates in
the tenor's position in the node list and reproduces the textbook twist table
exactly. Neither is more correct; which one ran is recorded.

`MILD`/`MODERATE`/`SEVERE`/`EXTREME` (25/100/200/300bp) are **project-defined**
magnitudes, not a regulatory classification.

### Tenor attribution and its residual

A curve shock is not separable, so the tenor split of a stress P&L does not add
up and the residual is reported rather than distributed:

* `first_order` — key-rate DV01 × shock; the residual is convexity plus cross
  terms.
* `isolated_reval` — one revaluation per shocked node; a node whose isolated bump
  the bootstrap refuses is marked unattributable and stays in the residual.

Scaling the parts to close the residual would destroy the only diagnostic that
says how non-linear the scenario was.

---

## 12. Historical stress — `observed_curve_difference_full_reval_v1`

**No historical shock is stored anywhere in this engine.** Every one is the
difference between two curves Treasury published, measured at the moment of use.
The named crisis catalogue holds **dates only**, and a test asserts that no field
of it holds a number.

A tenor present on the valuation curve but absent on a historical date is refused
by default: leaving it unshocked understates the loss on every position that
discounts off it, and the result would not say so.

---

## 13. Reverse stress — `bracketed_bisection_secant_v1`

A scenario *shape* is scaled by one multiplier and Brent's method solves for the
multiple whose full revaluation loses the target.

* A target unreachable inside the bracket is refused with the reachable loss
  range named — silently widening would answer a question nobody asked.
* A bound outside the bootstrap's domain shrinks by halving, and the reduction is
  reported, so "no solution below our limit" is distinguishable from "no solution
  before the curve stopped making sense".
* Monotonicity is sampled and reported. A non-monotone P&L means the returned
  root is *a* root, not *the* root.

---

## 14. Parametric and simulated risk

| method | distribution | revaluation | horizon |
|---|---|---|---|
| historical | empirical, observed moves | full | observed h-day moves |
| parametric | multivariate normal | none — linear key-rate | observed, or √h if asked |
| Monte Carlo | multivariate normal | full | observed h-day covariance |
| extreme tail | scaled normal / stressed covariance / Student-t / empirical bootstrap | full | observed h-day covariance |

**Historical risk never uses √h scaling.** The parametric path may, because its
own model assumes independent normal increments — there the scaling follows from
the assumptions rather than contradicting them. The result names which ran.

Parametric: `σ_P = sqrt(e' Σ e)` with `e = −KRD`, `VaR = z_α σ_P`,
`ES = φ(z_α)/(1−α) · σ_P`. Component VaR is the exact Euler decomposition and
reconciles to machine precision.

Monte Carlo: Cholesky where the covariance is positive definite, eigenvalue
clipping where it is not — with the repair reported, never applied silently.
Normal draws come from explicit Box-Muller over a seeded uniform stream, so the
same seed reproduces the same numbers on any Python that keeps the Mersenne
Twister.

Each extreme-tail methodology carries its **own** manifest version. None may be
presented as historical VaR.

---

## 15. Backtesting — `exception_counting_strict_exceedance_v1`

An exception is a loss **strictly greater** than the forecast. The `pnl_kind`
label — `ACTUAL`, `HYPOTHETICAL` or `MODEL_REVALUATION` — travels with the
result, because labelling a hypothetical series as actual flatters the model:
intraday risk reduction removes exceptions the model should have been charged
for.

* Kupiec unconditional coverage, `LR_uc ~ χ²(1)`
* Christoffersen Markov independence, `LR_ind ~ χ²(1)`
* Conditional coverage, `LR_cc = LR_uc + LR_ind ~ χ²(2)`

Tail probabilities are exact closed forms: `2(1 − Φ(√x))` for one degree of
freedom, `exp(−x/2)` for two.

Degenerate cases are **not computable**, not a pass. With zero exceptions the
independence test has no transitions to learn from, and a p-value of 1.0 there
would read as "independence confirmed".

The Basel traffic light is reported only at 250 observations and 99%, the
conditions it was calibrated for.

---

## 16. P&L attribution — `carry_roll_rate_residual_v1`

```
total P&L = carry + roll-down + rate move + position change + residual
```

Ordering is stated: time on the old curve, then rates on the aged book, then
positions on the new curve. Every effect is a full revaluation.

**Two residuals, and they mean different things.** `residual` compares the four
effects with the total and should be at machine precision; a non-zero value means
the decomposition disagrees with itself. `rate_unexplained` is the first-order
tenor split's shortfall — the book's convexity — and it grows with the size of
the move. Neither is ever forced to zero.

`position_change` is `null` without an end-of-period snapshot: "nothing traded"
and "we were not told" are different claims.

---

## 17. FRTB GIRR — `bcbs_mar21_girr_delta_curvature_v1`

Delta and curvature for one USD bucket, from BCBS *Minimum capital requirements
for market risk*, MAR21. Constants live in `regulatory/constants.py` with their
paragraph references; the tests assert them against the published values written
out in the test rather than against the module.

Basel's PV01 is the 1bp value change over 0.0001, so the Basel sensitivity is the
**negative** of this engine's key-rate DV01 over 0.0001. Curve nodes that are not
prescribed vertices are allocated linearly between neighbours, preserving the
total exactly.

A positively convex long bond book scores **zero** curvature: both CVR values
come out negative and the charge floors at zero. That is correct — Basel does not
credit the convexity benefit — and the result says which case it was.

**Vega is `null`, not `0.0`.** Every other risk class is listed as unsupported.
See [capability-gaps.md](capability-gaps.md).

---

## 18. Limits

- **Not executable prices.** Model-implied from a curve built on Treasury's
  indicative bid-side quotations.
- **Instruments**: fixed-rate, semiannual, ACT/ACT, USD. No floaters, TIPS,
  options, credit, repo/funding or FX. A convention this engine does not
  implement is refused by name, never approximated.
- **One curve does both jobs.** There is no separate discounting and projection
  curve, so swaps and floaters are out of reach until that generalisation
  happens.
- **Negative par curves are refused** by the bootstrap's no-negative-forward
  guard, and so are single-node bumps large enough to invert a segment. Both are
  reported by name.
- **The portfolio is synthetic.** Market data is real, verified and checksummed;
  the book is invented and labelled `SYNTHETIC_DEMO` at every layer.
- **No regulatory figure here is a reported capital requirement.** Full scope,
  and everything absent from it, in [capability-gaps.md](capability-gaps.md).

Complete tool surface and conventions:
[risk-tool-reference.md](risk-tool-reference.md).
