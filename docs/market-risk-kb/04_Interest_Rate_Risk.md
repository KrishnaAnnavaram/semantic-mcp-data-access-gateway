# 04 — Interest Rate Risk

**Level:** 4 · **Prerequisites:** [03](03_Pricing_Fundamentals.md) · **Feeds:** [10](10_Portfolio_Risk_Mathematics.md), [11](11_VaR.md), [13](13_Stress_Testing.md), [17](17_FRTB_Standardised_Approach.md)

> This is the largest technical document in the library, because interest-rate risk is the largest market risk in most banks and because its sensitivity vocabulary — duration, DV01, key rates, convexity — is the template every other asset class copied.

**Running example used throughout:** a 5-year Treasury, 4.00% semiannual coupon, $100 face, valued on a flat 4.50% continuously-compounded curve. From [03 §3.3](03_Pricing_Fundamentals.md): **price = $97.560516**.

---

## PART A — THE DURATION FAMILY

## 1. Macaulay Duration

### 1.1 Plain English

The average time you wait to get your money back, weighting each cash flow by how much it is worth today.

### 1.2 Banking example

A 5-year bond does not pay you in 5 years. It pays coupons along the way. Macaulay duration says: *in present-value terms, the average payment arrives in 4.57 years.* A zero-coupon bond of the same maturity has Macaulay duration of exactly 5 — you wait the full term.

### 1.3 Technical explanation

Macaulay duration is the PV-weighted average time to cash flow. It is measured **in years** and is the historical ancestor of the whole family — Frederick Macaulay introduced it in 1938 to compare bonds of different coupon structures on a like-for-like basis.

### 1.4 Formula

```
              n
              Σ  tᵢ · PV(CFᵢ)
             i=1
D_mac  =  ─────────────────────
                    P
```

### 1.5 Inputs

| Input | Meaning | Unit |
|---|---|---|
| `tᵢ` | Time to cash flow *i* | years |
| `PV(CFᵢ)` | Present value of cash flow *i* | currency |
| `P` | Dirty price (Σ PV) | currency |

### 1.6 Step-by-step

1. Project every contractual cash flow with its date.
2. Discount each on the valuation curve.
3. Multiply each PV by its time.
4. Sum, and divide by total PV.

### 1.7 Numerical example

| *t* | CF | DF | PV | *t* × PV |
|---|---|---|---|---|
| 0.5 | 2.00 | 0.977751 | 1.955502 | 0.977751 |
| 1.0 | 2.00 | 0.955997 | 1.911994 | 1.911994 |
| 1.5 | 2.00 | 0.934730 | 1.869460 | 2.804190 |
| 2.0 | 2.00 | 0.913931 | 1.827862 | 3.655724 |
| 2.5 | 2.00 | 0.893587 | 1.787174 | 4.467935 |
| 3.0 | 2.00 | 0.873716 | 1.747432 | 5.242296 |
| 3.5 | 2.00 | 0.854274 | 1.708548 | 5.979918 |
| 4.0 | 2.00 | 0.835270 | 1.670540 | 6.682160 |
| 4.5 | 2.00 | 0.816686 | 1.633372 | 7.350174 |
| 5.0 | 102.00 | 0.798516 | 81.448632 | 407.243160 |
| | | | **97.560516** | **446.315302** |

```
D_mac  =  446.315302 / 97.560516  =  4.5748 years
```

### 1.8 Interpretation

4.57 years, against a 5-year maturity. The gap is entirely due to the coupons. A higher coupon pulls duration down; a zero coupon leaves it equal to maturity.

### 1.9 Banking usage

Rarely used directly on a modern trading floor. It survives as (a) the definitional root of modified duration, (b) an immunisation tool in ALM, where matching asset and liability duration protects surplus against parallel moves.

### 1.10 Regulatory relevance

Not used in FRTB. Appears in the **simplified standardised approach** (`MAR40`) duration-based method for interest-rate risk, which remains available to smaller banks in jurisdictions that permit it, and in IRRBB frameworks.

### 1.11 Limitations

Assumes a flat curve and parallel shifts. Meaningless for instruments whose cash flows are not fixed — floaters, MBS, callables.

### 1.12 Related

Modified duration (§2), effective duration (§3).

---

## 2. Modified Duration

### 2.1 Plain English

The percentage the price falls for a 1% (100bp) rise in yield.

### 2.2 Banking example

A bond with modified duration 4.57 loses about 4.57% of its value if yields rise 1%. On a $100m position, roughly $4.57m.

### 2.3 Technical explanation

The **negative of the price's proportional derivative** with respect to yield — the elasticity of price to yield. Modified duration converts Macaulay duration from "average time" into "price sensitivity."

### 2.4 Formula

```
                1     ∂P              D_mac
D_mod  =  −  ───── · ─────    =   ───────────────
                P     ∂y             1 + y/f
```

Under **continuous compounding**, `f → ∞` and the two coincide: `D_mod = D_mac`.

### 2.5 Inputs

Macaulay duration; the yield *y*; the compounding frequency *f*.

### 2.6 Step-by-step

1. Compute Macaulay duration.
2. Divide by `(1 + y/f)`, using the bond's own quoting convention.

### 2.7 Numerical example

Our bond is priced on a **continuously compounded** curve, so:

```
D_mod  =  D_mac  =  4.5748
```

Had we quoted the same bond at a 4.55% semiannual yield, we would divide: `4.5748 / (1 + 0.0455/2) = 4.4731`. **The two answers differ by 2%, and neither is wrong — they are answers under different conventions.** This is a standard source of reconciliation breaks between systems.

### 2.8 Interpretation

`ΔP/P ≈ −D_mod × Δy`. A +100bp move gives −4.5748%.

### 2.9 Banking usage

The standard cross-market comparison metric. "This portfolio has duration 6.2" is instantly meaningful to any fixed-income professional; "this portfolio has DV01 $482,000" requires knowing the portfolio's size before it means anything.

### 2.10 Regulatory relevance

`MAR40` duration method; IRRBB.

### 2.11 Limitations

First-order only — see convexity (§6). Assumes parallel shifts and fixed cash flows.

### 2.12 Related

DV01 (§4) is modified duration multiplied by price and by one basis point.

---

## 3. Effective Duration

### 3.1 Plain English

Duration measured by actually moving rates and repricing, rather than by a formula — the only method that works when the cash flows themselves respond to rates.

### 3.2 Banking example

A callable bond. Rates fall; the issuer will call; the bond's life shortens. No formula built on *fixed* cash flows can see this. So: shift the whole curve down 25bp, reprice **with the call model running**; shift up 25bp, reprice; take the symmetric difference.

### 3.3 Formula

```
                 P(−Δy)  −  P(+Δy)
D_eff  =  ─────────────────────────────
                 2 · P₀ · Δy
```

### 3.4 Step-by-step

1. Price at the base curve → `P₀`.
2. Shift the **entire curve** up by Δy (typically 25bp or 50bp), reprice **with all embedded-option and prepayment models re-run** → `P(+Δy)`.
3. Shift down by Δy, reprice → `P(−Δy)`.
4. Apply the formula.

### 3.5 Numerical example

A callable bond: `P₀` = 101.50, `P(+50bp)` = 99.60, `P(−50bp)` = 102.85.

```
D_eff  =  (102.85 − 99.60) / (2 × 101.50 × 0.005)  =  3.25 / 1.015  =  3.20
```

Note the asymmetry: the bond gained 1.35 on a rally but lost 1.90 on a sell-off. That is **negative convexity**, and it is invisible in the duration number alone.

### 3.6 Banking usage

Mandatory for callables, putables, MBS, and any structured note. It is also the definitional basis of FRTB's **curvature** charge, which is a prescribed effective-duration-style up/down revaluation.

### 3.7 Limitations

Depends entirely on the embedded-option model. Effective duration for an MBS is really a statement about the prepayment model, and two banks will disagree.

**Bump size matters.** Too small and you amplify numerical noise in the pricer; too large and you contaminate the first derivative with second-order effects. 25bp–50bp is the usual compromise for optioned instruments; 1bp for linear ones.

---

## PART B — DV01 AND ITS RELATIVES

## 4. DV01 / PV01 / BPV

### 4.1 Plain English

**The money you make or lose if interest rates move one basis point.**

This is the single most-used number on a rates trading floor.

### 4.2 Banking example

A desk reports 10-year DV01 of **$85,000**. Rates rise 1bp overnight; the desk loses $85,000. Rates rise 40bp over a week; it loses roughly $3.4m. The desk head reads that one number and knows immediately how large the position is in the only unit that matters: dollars.

### 4.3 Technical explanation

DV01 is the **absolute** (currency) first derivative of value with respect to yield, scaled to one basis point. Modified duration is the *relative* version; DV01 is the *absolute* version, and absolutes aggregate.

> **Why the trading floor prefers DV01 to duration.** Duration is a percentage and cannot be added across positions of different size. DV01 is a currency amount and adds directly. A $10m position with duration 20 and a $200m position with duration 1 have the same DV01 and offset each other exactly.

### 4.4 The terminology question — DV01 vs PV01 vs BPV

These three terms are used **inconsistently across desks, vendors and textbooks.** The dominant conventions:

| Term | Most common meaning | Typical home |
|---|---|---|
| **DV01** (Dollar Value of an 01) | Change in value for 1bp shift in **yield** | Cash bonds, U.S. usage |
| **PV01** (Present Value of an 01) | Change in value for 1bp shift in the **par/zero curve**, often the fixed-leg annuity | Swaps, European usage |
| **BPV** (Basis Point Value) | Generic synonym; usually = DV01 | UK usage; futures |

For a bond priced off its own yield, DV01 and PV01 are numerically almost identical. For a swap they can differ: the fixed-leg **annuity** (the PV01 in one common usage) is not quite the swap's total sensitivity, because the floating leg has sensitivity too.

> **Practical rule:** never accept a "PV01" number without asking *what was bumped* — the yield, the par curve, or the zero curve — and *whether all legs were bumped*. Roughly half of all sensitivity reconciliation breaks between two institutions resolve to this question.

### 4.5 Formula

**Analytic:**

```
DV01  =  D_mod  ×  P  ×  0.0001
```

**Bump-and-revalue (the production method):**

```
DV01  =  P(y − 1bp)  −  P(y)               [one-sided]

         P(y − 1bp) − P(y + 1bp)
DV01  =  ────────────────────────           [central — preferred]
                    2
```

**Central differencing is preferred** because it cancels the second-order term. The one-sided version carries an error proportional to convexity; the central version's error is third-order and negligible.

### 4.6 Sign convention

**There is no universal sign convention, and this causes real incidents.**

| Convention | "DV01 = +$85,000" means |
|---|---|
| **Loss-on-rate-rise (most common)** | Long the bond; a rate *rise* loses $85,000 |
| **Signed derivative** | ∂P/∂y = +85,000; a rate rise *gains* — i.e. a short position |

**Always establish the house convention.** This document uses the first: **positive DV01 = long duration = loses money when rates rise.**

### 4.7 Units

Currency per basis point. Reported per position, per bucket, per desk, per currency.

### 4.8 Numerical example — our 5-year bond

```
DV01  =  D_mod × P × 0.0001
      =  4.5748 × 97.560516 × 0.0001
      =  $0.044633   per $100 face
```

**Scaled to $100m face:** `$0.044633 × 1,000,000 = $44,633 per basis point.`

**Verification by bump-and-revalue.** Reprice at 4.51% and 4.49% continuous:

| Curve | Price |
|---|---|
| 4.49% | 97.605161 |
| 4.50% | 97.560516 |
| 4.51% | 97.515893 |

```
Central DV01  =  (97.605161 − 97.515893) / 2  =  0.044634  per $100 face   ✓
```

The analytic and bumped figures agree to five decimal places. **This agreement is a mandatory production control** — see §17.

### 4.9 Aggregation

DV01 aggregates by **simple summation within a currency and tenor**:

```
DV01_portfolio  =  Σ  DV01ᵢ
```

Across **currencies** it does not: $1/bp of USD and $1/bp of JPY are different risks. A "total DV01" summed across currencies is a number without meaning. Report by currency, always.

### 4.10 Interpretation

| Sign | Position | Rates rise | Rates fall |
|---|---|---|---|
| Positive DV01 | Long duration (own bonds, receive fixed) | Lose | Gain |
| Negative DV01 | Short duration (short bonds, pay fixed) | Gain | Lose |
| Zero DV01 | Duration-neutral | — | — |

**Trader's reading:** "I am long $44,633 a basis point. If I think rates are going up, I need to sell something."

**Risk manager's reading:** "The desk's DV01 limit is $500,000. It is 8.9% utilised. But *where* on the curve is that risk?" — which is exactly why key-rate DV01 exists.

### 4.11 Assumptions and limitations

- **Parallel shift.** DV01 assumes the whole curve moves together. Curves twist. See §5.
- **Linearity.** Valid for small moves only. See §6.
- **Static portfolio and static cash flows.** Wrong for optioned instruments; use effective duration.
- **Zero DV01 ≠ no risk.** A duration-neutral steepener has zero total DV01 and substantial curve risk.

### 4.12 Common implementation errors

| Error | Consequence |
|---|---|
| One-sided bump on a convex instrument | DV01 biased by ½ × convexity × bump |
| Bumping yield when the book is curve-priced | Inconsistent with how P&L actually arises |
| Bumping only the projection curve on a swap | Discount-curve sensitivity missed |
| Summing DV01 across currencies | Meaningless aggregate |
| Bump too small (0.01bp) | Pricer numerical noise dominates |
| Not re-running option models on the bump | Optionality invisible |
| Clean rather than dirty price | Small systematic bias |

### 4.13 Regulatory relevance

DV01 is the direct input to **FRTB SBM GIRR delta**. `MAR21.8` defines the GIRR delta risk factors as the risk-free curve at **ten vertices: 0.25, 0.5, 1, 2, 3, 5, 10, 15, 20 and 30 years**, plus a flat inflation curve and cross-currency basis curves. The sensitivity to each vertex is a key-rate DV01 in all but name.

`MAR21.42` Table 1 then applies these risk weights:

| Vertex | 0.25y | 0.5y | 1y | 2y | 3y | 5y | 10y | 15y | 20y | 30y |
|---|---|---|---|---|---|---|---|---|---|---|
| **Risk weight** | 1.7% | 1.7% | 1.6% | 1.3% | 1.2% | 1.1% | 1.1% | 1.1% | 1.1% | 1.1% |

Inflation and cross-currency basis risk factors both carry **1.6%** (`MAR21.43`). For a Basel-specified currency list — **EUR, USD, GBP, AUD, JPY, SEK, CAD**, plus the bank's own reporting currency — these weights may, at the bank's discretion, be divided by **√2** (`MAR21.44`).

---

## 5. Key Rate Risk

### 5.1 Plain English

DV01 tells you your total rate risk. **Key-rate DV01 tells you where on the curve it lives.**

### 5.2 Banking example

Two portfolios, both with total DV01 of exactly $100,000/bp:

| | 2y | 5y | 10y | 30y | Total |
|---|---|---|---|---|---|
| **Portfolio A** | 25,000 | 25,000 | 25,000 | 25,000 | 100,000 |
| **Portfolio B** | 300,000 | 0 | 0 | −200,000 | 100,000 |

Under a parallel shift they behave identically. Under a **flattening** — 2y +20bp, 30y −20bp — A loses nothing on net; B loses 300,000 × 20 + (−200,000) × (−20) = **$10m**.

> **A single DV01 number can conceal an arbitrarily large curve position.** This is why every rates report is a *ladder*, never a scalar.

### 5.3 Technical explanation

Key-rate DV01 (equivalently key-rate duration, or bucketed PV01) decomposes total sensitivity across curve nodes. Each node is bumped **in isolation** while the others are held fixed, with the shock tapering to zero at the adjacent nodes.

### 5.4 Formula

For key rate *k* at tenor `T_k`:

```
KRD01(k)  =  P( curve with bump at T_k )  −  P( base curve )
```

with the standard **triangular (tent) shock**:

```
                ⎧ Δy · (t − T_{k−1}) / (T_k − T_{k−1})   for T_{k−1} ≤ t ≤ T_k
   bump(t)  =   ⎨ Δy · (T_{k+1} − t) / (T_{k+1} − T_k)   for T_k ≤ t ≤ T_{k+1}
                ⎩ 0                                       otherwise
```

**The completeness property:** the tents sum to a parallel shift, so

```
Σ  KRD01(k)   ≈   DV01_parallel
```

This identity is a mandatory reconciliation check. Failure means the bump scheme has a gap or an overlap.

### 5.5 Numerical example

A $500m swap book:

| Tenor | KRD01 ($/bp) | Reading |
|---|---|---|
| 3M | 1,200 | small front-end |
| 1Y | 4,500 | |
| 2Y | 18,000 | |
| 5Y | 42,000 | **belly concentration** |
| 10Y | 65,000 | **largest single bucket** |
| 20Y | −12,000 | **short the long end** |
| 30Y | −8,500 | |
| **Total** | **110,200** | matches parallel DV01 ✓ |

**What this book is.** Long the belly, short the long end — a flattener in the 10s30s sector. Under a parallel +10bp it loses $1.1m. Under a **steepening** (10y unchanged, 30y +25bp) it *gains* $212,500. The ladder tells you the position; the scalar does not.

### 5.6 Interpolation consequences

**KRD depends on the interpolation scheme.** Bumping the 10-year node changes the curve between 5 and 20 years, and *how much* it changes depends on the interpolation rule. Two banks with identical positions and identical market data will report different ladders — while agreeing on the total.

Practical consequences:
- Never reconcile KRD ladders between institutions bucket-by-bucket; reconcile totals.
- Keep the risk system's node set aligned with the curve-building node set. Bumping a node the curve does not have forces an interpolation that no one specified.
- **FRTB fixes the vertices** (`MAR21.8`), which removes the choice for regulatory purposes but not for internal ones.

### 5.7 Regulatory relevance

The ten `MAR21.8` vertices are, precisely, a prescribed key-rate bucketing. Within a GIRR bucket (= currency), `MAR21.46` sets the correlation between different tenors on the same curve as:

```
ρ(k,l)  =  max[ e^( −θ · |T_k − T_l| / min(T_k, T_l) ) ,  40% ]      with θ = 3%
```

**Worked example from the standard.** Between the 1-year and 5-year tenors of the same curve:

```
ρ  =  max[ e^(−0.03 · |1−5| / min(1,5)) , 0.40 ]
   =  max[ e^(−0.03 · 4 / 1) , 0.40 ]
   =  max[ e^(−0.12) , 0.40 ]
   =  max[ 0.8869 , 0.40 ]  =  88.69%
```

This matches the worked example in footnote 13 to `MAR21.46` exactly.

Two further parameters complete the GIRR correlation structure:
- Same tenor, **different curves** in the same currency: **99.90%** (`MAR21.45`), and different-tenor-different-curve correlations are the Table 2 value **× 99.90%** (`MAR21.47`).
- **Across buckets** (i.e. across currencies): γ = **50%** (`MAR21.50`).

---

## 6. Convexity

### 6.1 Plain English

Duration says price moves in a straight line with yield. It does not — it curves. **Convexity measures the curve.**

### 6.2 Banking example

Our bond has duration 4.5748. A +100bp move should cost 4.5748%. It actually costs 4.4642%. A −100bp move should gain 4.5748%; it actually gains 4.6864%.

**You lose less than predicted and gain more than predicted.** That asymmetry is worth money, and it is what positive convexity means.

### 6.3 Formula

```
              1     ∂²P                  1     n
   C   =   ─────· ──────      =        ───── · Σ  tᵢ² · PV(CFᵢ)      [continuous compounding]
              P     ∂y²                   P    i=1
```

**Second-order price approximation:**

```
   ΔP/P   ≈   −D_mod · Δy   +   ½ · C · (Δy)²
```

**Dollar convexity** = `C × P`, which aggregates across positions the way DV01 does.

### 6.4 Numerical example — our 5-year bond

| *t* | PV | *t*² × PV |
|---|---|---|
| 0.5 | 1.955502 | 0.488876 |
| 1.0 | 1.911994 | 1.911994 |
| 1.5 | 1.869460 | 4.206285 |
| 2.0 | 1.827862 | 7.311448 |
| 2.5 | 1.787174 | 11.169838 |
| 3.0 | 1.747432 | 15.726888 |
| 3.5 | 1.708548 | 20.929713 |
| 4.0 | 1.670540 | 26.728640 |
| 4.5 | 1.633372 | 33.075783 |
| 5.0 | 81.448632 | 2036.215800 |
| | | **2157.765265** |

```
C  =  2157.765265 / 97.560516  =  22.1173
```

### 6.5 Verification — does the second-order term actually help?

Shift the curve +100bp, to 5.50% continuous.

| Method | Price | Error vs exact |
|---|---|---|
| **Exact full revaluation** | **93.203538** | — |
| First order only (duration) | 93.097520 | −0.106018 |
| Second order (duration + convexity) | 93.205332 | **+0.001794** |

The convexity term removes **98.3%** of the first-order error. This is the empirical case for carrying second-order sensitivities, and equally the case for full revaluation when the moves get large — at +300bp the second-order approximation itself begins to break down.

### 6.6 Positive vs negative convexity

| | Positive convexity | Negative convexity |
|---|---|---|
| Held by | Plain bonds, long options | MBS, callable bonds, short options |
| Rally | Gains **more** than duration predicts | Gains **less** |
| Sell-off | Loses **less** | Loses **more** |
| Owner | Is paid to hold it via lower yield | Is compensated by higher yield |
| Hedging | Hedge ratio changes benignly | Hedge ratio moves **against** you — you must buy high and sell low to stay hedged |

> **Negative convexity is the mechanism behind mortgage convexity hedging events.** As rates rise, MBS duration *extends*, forcing holders to sell duration into a falling market, which pushes rates higher, which extends duration further. The 1994 and 2003 U.S. rate episodes both contained this feedback loop. It is a structural, well-documented amplifier and a standard stress scenario.

### 6.7 Regulatory relevance

FRTB does not use analytical convexity. It uses **curvature**, which is an effective, prescribed-shock version of the same idea: revalue up and down by the delta risk weight, and take the worse outcome net of the delta already charged. See [17](17_FRTB_Standardised_Approach.md) for the full formula.

---

## PART C — CURVE RISK

## 7. The shapes a curve moves in

Empirically — and this is one of the most robust results in fixed income — principal component analysis of yield curve changes across markets and decades consistently produces three dominant factors explaining the large majority of variance:

| PC | Name | Shape | Typical share of variance |
|---|---|---|---|
| 1 | **Level** | All tenors move together | Dominant |
| 2 | **Slope** | Short and long move oppositely | Second |
| 3 | **Curvature** | Belly moves against the wings | Third |

> The precise percentages vary by market, period and estimation window, and any specific figure should be recomputed on the relevant data rather than quoted from memory. The *ordering* and the *shapes*, however, are extremely stable. **UNVERIFIED — specific variance shares require estimation on the relevant sample; do not quote fixed percentages as fact.**

### 7.1 The named curve trades

| Trade | Construction | Profits when |
|---|---|---|
| **Outright long duration** | Buy bonds / receive fixed | Rates fall |
| **Steepener** | Long short-end, short long-end (DV01-neutral) | Curve steepens |
| **Flattener** | Short short-end, long long-end (DV01-neutral) | Curve flattens |
| **Butterfly** | Long belly, short both wings (DV01-neutral) | Belly richens |
| **Condor** | Four-point generalisation of a butterfly | Complex relative value |

**Constructing a DV01-neutral steepener.** Long $X of 2-year (DV01 $19/$10k face), short $Y of 10-year (DV01 $85/$10k face). For neutrality:

```
X × 19  =  Y × 85     ⟹     X / Y  =  85 / 19  =  4.47
```

Buy $447m of 2-year against $100m short of 10-year. Total DV01 ≈ 0. The position has **no parallel-shift risk and full slope risk**, which is precisely the intent.

### 7.2 Scenario P&L for curve moves

```
ΔP  ≈  −  Σ  KRD01(k) × Δy_k × 10000
          k
```

**Worked example** on the §5.5 ladder, under a flattening (front +25bp, long end −25bp):

| Tenor | KRD01 | Δy (bp) | P&L ($) |
|---|---|---|---|
| 3M | 1,200 | +25 | −30,000 |
| 1Y | 4,500 | +25 | −112,500 |
| 2Y | 18,000 | +20 | −360,000 |
| 5Y | 42,000 | +5 | −210,000 |
| 10Y | 65,000 | −10 | +650,000 |
| 20Y | −12,000 | −20 | −240,000 |
| 30Y | −8,500 | −25 | +212,500 |
| | | **Net** | **−$90,000** |

Total DV01 is +110,200, so a naive "+2bp average parallel move" estimate would have given −$220,400. The ladder gives −$90,000. **The scalar estimate is wrong by a factor of 2.4, in a scenario that is entirely ordinary.**

---

## 8. Basis risk in rates

| Basis | The two things that should track | Why they don't |
|---|---|---|
| **Swap spread** | Swap rate vs government yield | Balance-sheet cost, repo specialness, sovereign supply |
| **Tenor basis** | 3M vs 6M index projection | Term liquidity and credit premia in the index |
| **Cross-currency basis** | Covered interest parity | Post-2008 funding frictions; balance-sheet scarcity |
| **Futures/cash basis** | Future vs CTD | Delivery optionality, financing, index effects |
| **RFR transition basis** | Legacy IBOR vs RFR + spread | Fallback conventions, liquidity migration |

**Regulatory treatment of cross-currency basis is instructive.** `MAR21.50` sets its correlation with the yield curve, with inflation, and with *other* cross-currency basis curves at **0%**. Basel is declining to recognise any offset at all — a deliberate statement that basis risk is a distinct exposure, not a residual.

---

## PART D — CARRY, ROLL AND FORWARDS

## 9. Carry

### 9.1 Plain English

What you earn just for holding the position, if nothing in the market changes.

### 9.2 Formula

```
Carry  =  Coupon income  −  Financing cost      (over the holding period)
```

For a repo-financed bond over *n* days:

```
Carry  =  Face × c × (n/365)   −   Dirty Price × r_repo × (n/360)
```

Note the two different day-count bases — a real and common source of small errors.

### 9.3 Numerical example

$100m of a 4% bond, dirty price 98.50, financed at 4.30% repo, held 30 days:

```
Coupon accrual  =  100,000,000 × 0.04  × 30/365  =  $328,767
Repo cost       =   98,500,000 × 0.043 × 30/360  =  $352,958
Carry           =  328,767 − 352,958             =  −$24,191
```

**Negative carry.** The position costs $24,191 a month to hold. The trader is paying to be long — a bet on price appreciation that must overcome a running cost. In an inverted curve environment this is the normal state of affairs for long positions, and it is a first-order input to position sizing.

---

## 10. Roll-down

### 10.1 Plain English

If the curve stays *exactly* where it is, a bond gets shorter as time passes, and on an upward-sloping curve a shorter bond yields less — so its price rises. You earn money from the passage of time alone.

### 10.2 Formula

```
Roll-down  =  P( maturity − Δt , at the curve's yield for that shorter maturity )
            − P( maturity      , at today's yield )
```

### 10.3 Numerical example

A 5-year bond yields 4.50%; the 4-year point yields 4.30%. Hold for one year, curve unchanged.

The bond is now a 4-year bond, and re-prices at 4.30%. With approximate duration 3.7 at that point:

```
Roll-down gain  ≈  3.7 × 20bp  =  0.74%   of face
```

On $100m, roughly **$740,000** — earned purely from time passing on a sloped curve.

### 10.4 Carry + Roll

```
Total expected return (no curve change)  =  Carry  +  Roll-down
```

**This is the trader's hurdle.** A position with +$740,000 roll and −$290,000 carry earns +$450,000 a year if the trader is completely wrong about direction and nothing moves. That number determines whether the trade is worth doing.

> A flat curve gives no roll. An inverted curve gives **negative** roll — bonds roll *up* the curve into higher yields and lose money with the passage of time. Carry-and-roll analysis is therefore highly regime-dependent, and strategies calibrated in a steep-curve era stop working silently when the curve inverts.

---

## 11. Forward rates and swap mathematics

### 11.1 Forward rate

```
                     1            DF(t₁)
f(t₁, t₂)  =  ───────────── · ln ─────────
                 t₂ − t₁          DF(t₂)
```

### 11.2 Par swap rate

```
                Σᵢ  Lᵢ^proj · τᵢ · DF(tᵢ)             (floating leg PV)
   K_par  =  ────────────────────────────────
                    Σⱼ  τⱼ · DF(tⱼ)                    (the annuity, A)
```

### 11.3 Swap PV

```
   PV_receive_fixed  =  N · [ K · A  −  FloatingLegPV ]
```

### 11.4 Swap DV01

```
   DV01_swap  ≈  N · A · 0.0001
```

The **annuity is the swap's DV01**, to a very good approximation. This is the single most useful shortcut in swap risk management: a 10-year USD swap with an annuity of about 8.1 has a DV01 of roughly `N × 0.00081` — about **$81,000 per $100m notional**.

### 11.5 Worked example

$100m 10-year receive-fixed swap. Annuity A = 8.10.

```
DV01  =  100,000,000 × 8.10 × 0.0001  =  $81,000 per bp
```

Rates rise 15bp: the receiver loses `81,000 × 15 = $1,215,000`.

---

## PART E — IMPLEMENTATION

## 12. Pseudocode

### 12.1 DV01

```
FUNCTION dv01(position, curve, bump_bp = 1.0):
    base    = price(position, curve)
    up      = price(position, shift_parallel(curve, +bump_bp))
    down    = price(position, shift_parallel(curve, -bump_bp))
    RETURN (down - up) / (2 * bump_bp)        # positive = long duration
```

### 12.2 Key-rate DV01

```
FUNCTION key_rate_dv01(position, curve, key_tenors, bump_bp = 1.0):
    base   = price(position, curve)
    ladder = {}
    FOR k IN key_tenors:
        up   = price(position, apply_tent_bump(curve, k, +bump_bp))
        down = price(position, apply_tent_bump(curve, k, -bump_bp))
        ladder[k] = (down - up) / (2 * bump_bp)

    # MANDATORY completeness check
    ASSERT abs(sum(ladder.values()) - dv01(position, curve)) < tolerance
    RETURN ladder
```

### 12.3 Convexity

```
FUNCTION convexity(position, curve, bump_bp = 25.0):
    b  = bump_bp / 10000.0
    P0 = price(position, curve)
    Pu = price(position, shift_parallel(curve, +bump_bp))
    Pd = price(position, shift_parallel(curve, -bump_bp))
    RETURN (Pu + Pd - 2*P0) / (P0 * b * b)
```

### 12.4 Curve scenario P&L

```
FUNCTION curve_scenario_pnl(portfolio, curve, shock_vector, mode):
    IF mode == "full_revaluation":
        RETURN price(portfolio, apply_shock(curve, shock_vector))
             - price(portfolio, curve)

    IF mode == "sensitivity_based":
        ladder = key_rate_dv01(portfolio, curve, shock_vector.tenors)
        pnl    = 0
        FOR k IN shock_vector.tenors:
            pnl -= ladder[k] * shock_vector[k]      # shock in bp
        RETURN pnl                                   # first order only
```

**Use full revaluation for large shocks and for any book with optionality.** The sensitivity path is for speed, not for accuracy.

---

## 13. Data contract

**Input schema**

```
position:
    position_id           string
    instrument_type       enum
    currency              ISO-4217
    notional              decimal
    direction             {long, short}
    maturity_date         date
    coupon_rate           decimal | null
    coupon_frequency      int
    day_count             enum
    calendar              string
    embedded_options      list | null
    discount_curve_id     string        # CSA-determined
    projection_curve_id   string | null

curve:
    curve_id              string
    currency              ISO-4217
    valuation_date        date
    node_tenors           list<decimal>          # in years
    node_rates            list<decimal>
    compounding           enum
    interpolation         enum
```

**Output schema**

```
sensitivity:
    position_id           string
    valuation_date        date
    risk_factor           string          # e.g. "USD.SOFR.ZERO"
    tenor                 decimal | null  # null for parallel
    measure               enum {PV, DV01, KRD01, CONVEXITY, CARRY, ROLL}
    value                 decimal
    currency              ISO-4217
    unit                  enum {CCY, CCY_PER_BP, YEARS, DIMENSIONLESS}
    computation_method    enum {ANALYTIC, BUMP_1SIDED, BUMP_CENTRAL}
    bump_size_bp          decimal | null
```

> `computation_method` and `bump_size_bp` are **not optional metadata.** Two DV01s computed with different bump sizes are different numbers, and a reconciliation that does not carry the method cannot be resolved.

---

## 14. Comparison tables

### 14.1 Duration vs DV01 vs Convexity

| | Modified Duration | DV01 | Convexity |
|---|---|---|---|
| Order | First | First | Second |
| Unit | % per 100bp | currency per bp | dimensionless (or currency per bp²) |
| Relative or absolute | Relative | Absolute | Relative |
| Aggregates by | Value-weighted average | Simple sum | Value-weighted average |
| Answers | "How volatile per unit of value?" | "How many dollars per bp?" | "How wrong is the linear estimate?" |
| Primary user | Portfolio manager, ALM | Trader, risk manager | Options/MBS desk |
| FRTB analogue | — | GIRR delta | Curvature |

### 14.2 DV01 vs PV01 vs BPV

| | DV01 | PV01 | BPV |
|---|---|---|---|
| What is bumped | Yield | Par or zero curve | Either (usage varies) |
| Home market | Cash bonds, US | Swaps, Europe | UK, futures |
| Typical convention | Bond's own yield | Fixed-leg annuity | Generic |
| Equal to the others? | Approximately, for a bond | Can differ on a swap | Usually = DV01 |
| **Rule** | **Always ask what was bumped** | | |

### 14.3 DV01 vs Key-Rate DV01

| | DV01 | Key-Rate DV01 |
|---|---|---|
| Shock | Parallel | One node, tent-shaped |
| Output | Scalar | Vector (ladder) |
| Detects curve risk | **No** | Yes |
| Interpolation-dependent | No | **Yes** |
| Cost | 2 revaluations | 2 × *n* revaluations |
| Reconciles to | — | Σ KRD01 ≈ DV01 |

### 14.4 DV01 vs CS01

| | DV01 | CS01 |
|---|---|---|
| Factor bumped | Risk-free rate | Credit spread |
| Present in | All dated cash flows | Credit-risky instruments only |
| FRN | ~Zero (resets) | **Full maturity** |
| FRTB class | GIRR | CSR |
| Hedged with | Govvies, futures, swaps | CDS, index CDS |
| Captures default? | No | **No** — that is DRC's job |

---

## 15. Data frequency

| Calculation | Real-time | Intraday | EOD | Historical | Positions | Sensitivities |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| PV | ● | ● | ● | | ● | |
| DV01 | ● | ● | ● | | ● | |
| Key-rate DV01 | ○ | ● | ● | | ● | |
| Convexity | | ○ | ● | | ● | |
| Carry / Roll | | | ● | | ● | |
| Curve scenario P&L | | ○ | ● | | ● | ● |
| VaR / ES | | | ● | ● | ● | ● |
| FRTB GIRR delta | | | ● | | ● | ● |

`●` typical · `○` where the desk's activity warrants it

---

## 16. Who uses what

| Metric | Trader | Desk head | Market risk | Product control | Capital team | Validation | Regulator |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| PV | ● | ● | ● | ● | ● | ● | ○ |
| DV01 | ● | ● | ● | ○ | ● | ● | ○ |
| Key-rate DV01 | ● | ● | ● | | ● | ● | ○ |
| Convexity | ● | ○ | ● | | ○ | ● | |
| Carry / Roll | ● | ● | ○ | ● | | | |
| Curve scenarios | ● | ● | ● | | | ● | ● |
| GIRR delta (SBM) | | ○ | ● | | ● | ● | ● |

---

## 17. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Analytic vs bumped DV01** | Agree within tolerance (see §4.8) |
| 2 | **Bump-size stability** | DV01 at 0.5 / 1 / 2 bp bumps stable to tolerance |
| 3 | **Sign check** | Long a fixed-rate bond ⟹ positive DV01 under the house convention |
| 4 | **KRD completeness** | `Σ KRD01 ≈ DV01_parallel` |
| 5 | **Zero-coupon identity** | `D_mac = maturity` exactly |
| 6 | **Par identity** | A bond priced at par has `D_mod` matching the closed form |
| 7 | **Second-order accuracy** | Duration+convexity estimate within tolerance of full reval at ±100bp |
| 8 | **Currency separation** | No aggregate DV01 summed across currencies anywhere in the reporting chain |
| 9 | **Optionality** | Effective (not analytical) duration used for every callable/MBS |
| 10 | **Dirty price** | Sensitivities computed on dirty, not clean, price |
| 11 | **Curve reprice** | Bootstrapping instruments reprice to their market quotes |
| 12 | **Forward sanity** | Implied forwards plotted and free of oscillation |
| 13 | **Both curves bumped** | Swap DV01 includes discount *and* projection sensitivity |
| 14 | **Regulatory vertices** | GIRR sensitivities computed at exactly the `MAR21.8` ten vertices |

---

## 18. Limitations of the whole sensitivity approach

1. **Local approximation.** Everything in Parts A and B is a Taylor expansion around today's curve. It degrades as moves grow, and it degrades fastest exactly where losses are largest.
2. **Parallel-shift bias.** DV01 and modified duration assume a shape of move that empirically explains most, but by no means all, of curve variance.
3. **Static cash flows.** Any instrument whose cash flows respond to rates requires effective measures and a model, and then the risk number is really a statement about the model.
4. **No probability content.** DV01 says what happens per basis point. It says nothing about how many basis points are likely. That is what VaR, ES and stress testing exist to supply — [11](11_VaR.md), [12](12_Expected_Shortfall.md), [13](13_Stress_Testing.md).
5. **Interpolation dependence** of the key-rate ladder means bucket-level figures are not comparable across institutions.

---

## 19. Related Concepts

- [03 — Pricing Fundamentals](03_Pricing_Fundamentals.md) · [05 — Credit Spread Risk](05_Credit_Spread_Risk.md)
- [09 — Options and Greeks](09_Options_and_Greeks.md) · [13 — Stress Testing](13_Stress_Testing.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [23 — Market Data and Curves](23_Market_Data_and_Curves.md)
- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.8` vertices; `MAR21.42`–`MAR21.50` GIRR weights and correlations; `MAR40` duration method |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR21 text |
| BIS | Quarterly Review — mortgage convexity hedging analyses | various | https://www.bis.org/publ/qtrpdf/ | Convexity feedback mechanics |

*Accessed 25 August 2026.*
