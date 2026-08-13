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

## 8. Limits of v1

- **Not executable prices.** Model-implied from a curve built on Treasury's
  indicative bid-side quotations.
- **No accrued-interest split**, so values are dirty.
- **Instruments**: fixed-rate, semiannual, ACT/ACT, USD. No floaters, TIPS
  instruments, options, credit, repo/funding or FX.
- **Long-only** demo book, so no sign conventions for shorts are exercised.
- **No backtesting** yet.
- **The portfolio is synthetic.** Market data is real, verified and checksummed;
  the book is invented and labelled `SYNTHETIC_DEMO` at every layer.
