# 03 — Pricing Fundamentals

**Level:** 3 · **Prerequisites:** [02](02_Financial_Instruments.md) · **Feeds:** everything from [04](04_Interest_Rate_Risk.md) onwards

> **You cannot measure risk without a pricing function.** Every sensitivity is a derivative of a price; every scenario P&L is a difference of two prices; every VaR is a distribution of price changes. This document establishes the valuation machinery the rest of the library differentiates, shocks and simulates.

---

## 1. Time value of money

### 1.1 Plain English

A dollar today is worth more than a dollar next year, because today's dollar can be invested. **Discounting** converts a future amount into its value today; **compounding** does the reverse.

### 1.2 Banking example

A bank is owed $1,000,000 in exactly one year. The one-year risk-free rate is 4%. What is that promise worth today?

```
PV  =  1,000,000 / 1.04  =  $961,538.46
```

If rates rise to 4.5% tomorrow, the same promise is worth $956,937.80. The bank has lost $4,600 without anything happening to the promise. **That is market risk, in its simplest possible form.**

### 1.3 Formulas and conventions

| Convention | Discount factor `DF(t)` | Where used |
|---|---|---|
| Simple | `1 / (1 + r·t)` | Money markets, < 1 year |
| Annual compounding | `1 / (1 + r)^t` | Bond quoting conventions |
| *f*-times compounding | `1 / (1 + r/f)^(f·t)` | Semiannual bond math (*f* = 2) |
| Continuous | `e^(−r·t)` | Derivatives pricing, curve mathematics |

**Conversion between them:**

```
r_continuous  =  f · ln(1 + r_f / f)
r_f           =  f · ( e^(r_cont / f) − 1 )
```

> **A rate without its compounding convention is not a number.** "4%" semiannual and "4%" continuous are different rates. Curve libraries store one convention internally and convert on the boundary; systems that skip the conversion produce errors of a few basis points that are invisible in a price and material in a DV01.

### 1.4 Day-count conventions

The fraction of a year `τ` between two dates depends on a market convention, and getting it wrong is a silent, systematic error.

| Convention | Rule | Typical market |
|---|---|---|
| ACT/360 | actual days / 360 | USD money markets, SOFR, EURIBOR |
| ACT/365F | actual days / 365 | GBP money markets, SONIA |
| 30/360 | assumes 30-day months | USD corporate bonds, fixed swap legs |
| ACT/ACT (ISDA) | actual/actual, period-aware | Government bonds (US Treasuries, gilts) |

**A worked contrast.** From 1 January to 1 July, ACT/360 gives 181/360 = 0.502778; 30/360 gives 180/360 = 0.500000. On a $500m notional at 5%, that is a difference of roughly **$69,000** on a single coupon.

Add to this the **business day conventions** (Following, Modified Following, Preceding), the **holiday calendars** (which differ by currency and by centre), and the **settlement lag**, and you have the reason that a large fraction of valuation discrepancies between two banks resolve to date arithmetic rather than to modelling.

---

## 2. Curves — the central object

### 2.1 The four faces of one curve

A single interest-rate curve can be expressed in four equivalent ways. They contain identical information; converting between them is mechanical; and different desks quote in different ones.

| Representation | Meaning | Relationship |
|---|---|---|
| **Discount factors** `DF(t)` | PV today of $1 at *t* | The primitive |
| **Zero (spot) rates** `z(t)` | Single rate for a payment at *t* | `DF(t) = e^(−z(t)·t)` |
| **Forward rates** `f(t₁,t₂)` | Rate contracted today for lending between *t₁* and *t₂* | `f = (1/(t₂−t₁))·ln(DF(t₁)/DF(t₂))` |
| **Par rates** `K(t)` | Coupon making a par instrument price at 100 | `K = (1 − DF(t_n)) / Σ τᵢ·DF(tᵢ)` |

**Which is "real"?** Discount factors are the primitive; everything else is derived. But **par rates are what the market quotes**, so a curve build starts from par rates and solves for discount factors. This inversion is bootstrapping.

### 2.2 The forward rate relationship

The single most important identity in curve mathematics:

```
DF(t₂)  =  DF(t₁) · e^(−f(t₁,t₂)·(t₂−t₁))
```

Rearranged, the forward rate is:

```
                    1            DF(t₁)
f(t₁,t₂)  =  ───────────── · ln ─────────
               t₂ − t₁           DF(t₂)
```

**Worked example.** `DF(1y) = 0.9615`, `DF(2y) = 0.9151`.

```
f(1,2)  =  (1/1) · ln(0.9615 / 0.9151)  =  ln(1.05070)  =  4.946%
```

The market is pricing 4.95% for one-year money starting in one year. If a trader believes the one-year rate in a year's time will be 4.5%, that forward is the number to trade against — not today's one-year spot rate.

### 2.3 Bootstrapping

**The problem.** The market quotes par instruments. You need discount factors. Each instrument's price is a function of *all* the discount factors up to its maturity, so you solve sequentially.

**Algorithm:**

```
INPUT: sorted market instruments (deposits, futures/FRAs, par swaps)
       day-count conventions, calendars, interpolation rule

DF[0] = 1.0

FOR each instrument i in increasing maturity:
    known_DFs  = all DF already solved
    unknown    = DF at instrument i's maturity
    SOLVE  price_model(instrument_i, known_DFs, unknown) = market_price_i
           for `unknown`
           (closed form for deposits/FRAs; 1-D root-find for swaps)
    STORE DF[maturity_i] = unknown

RETURN discount curve, with an interpolation rule for intermediate points
```

**Worked example — bootstrapping a 2-year point from a par swap.**

Given: 1y par swap rate 4.00%, 2y par swap rate 4.20%, annual payments, ACT/365, `DF(1y) = 1/1.04 = 0.961538`.

The 2y par swap prices to zero:

```
0.042 · [ DF(1) + DF(2) ]  +  DF(2)  −  1   =  0
0.042 · 0.961538 + 0.042·DF(2) + DF(2)      =  1
0.040385 + 1.042·DF(2)                       =  1
DF(2)                                        =  0.959615 / 1.042  =  0.920937
```

Zero rate: `z(2) = −ln(0.920937)/2 = 4.118%` continuous.
Implied 1y-forward-1y: `f(1,2) = ln(0.961538/0.920937) = 4.313%`.

### 2.4 Interpolation — a modelling choice with real consequences

Between quoted maturities the curve must be interpolated. **The choice is not cosmetic.**

| Method | Interpolates | Character |
|---|---|---|
| Linear on zero rates | `z(t)` | Simple; produces *discontinuous* forward rates |
| Linear on `log DF` | `ln DF(t)` | Equivalent to piecewise-constant forwards; stable, common |
| Cubic spline on zeros | `z(t)` | Smooth zeros; can produce oscillating, economically implausible forwards |
| Monotone convex | forwards | Designed to keep forwards positive and non-oscillating |

> **Forward rates are the diagnostic.** A curve can look perfectly smooth in zero-rate space and imply wildly oscillating — even negative — forward rates. Since forwards are what a swap's floating leg actually projects, an oscillating forward curve produces oscillating key-rate sensitivities and unstable hedge ratios. **Always plot the implied forwards when validating a curve build.**

**Consequence for risk.** Key-rate DV01 depends directly on the interpolation rule, because bumping one node redistributes value according to how the curve interpolates around it. Two banks with identical positions and identical market data will report different KRD ladders if they interpolate differently. Their *total* DV01 will agree; the *distribution* across buckets will not.

### 2.5 Multi-curve reality

Before 2008, one curve served as both discount and projection. The crisis destroyed that assumption: LIBOR embedded bank credit and liquidity premia, while collateralised derivatives were economically funded at the CSA rate.

The modern framework, now largely built on risk-free rates (SOFR, €STR, SONIA, TONA, SARON):

| Curve | Built from | Used for |
|---|---|---|
| **OIS / RFR discount curve** | OIS swaps on the CSA currency's RFR | Discounting collateralised trades |
| **Projection curves** | Basis swaps vs the RFR, per index and tenor | Forecasting floating coupons |
| **Cross-currency basis curves** | XCCY basis swaps | Discounting under a foreign-currency CSA |

**The CSA determines the discount curve.** A USD swap collateralised in EUR is discounted off a EUR-collateral-adjusted USD curve, which embeds the EUR/USD cross-currency basis. This makes the basis a risk factor on a swap book that contains no FX product at all.

---

## 3. Bond pricing

### 3.1 Formula

```
        n
P_dirty =  Σ  CFᵢ · DF(tᵢ)
          i=1

P_clean =  P_dirty − Accrued Interest
```

**Accrued interest** compensates the seller for coupon earned but not yet paid:

```
AI  =  Coupon × (days since last coupon / days in coupon period)
```

with both counts on the bond's day-count convention.

> **Clean vs dirty is a quoting convention, not an economic distinction.** The buyer always pays dirty. Prices are quoted clean so that the quote does not saw-tooth downward on each coupon date. Every risk calculation uses dirty price; every screen shows clean. A system that computes DV01 from clean price is wrong by the sensitivity of accrued interest — small, but systematically so.

### 3.2 Yield to maturity

The single rate *y* satisfying:

```
         n     CFᵢ
P  =     Σ  ───────────
        i=1  (1+y/f)^(f·tᵢ)
```

**YTM has no closed-form solution** and is found by Newton-Raphson:

```
y_{k+1}  =  y_k  −  ( P(y_k) − P_market ) / P'(y_k)
```

where `P'(y)` is the analytic derivative (dollar duration), which converges in three or four iterations from a sensible start.

**What YTM actually assumes.** That every cash flow is discounted at the same rate, and — if interpreted as a realised return — that all coupons are reinvested at *y* until maturity. Neither is true. YTM is a **quoting convention that compresses a curve into one number**, useful for comparison and dangerous for valuation.

### 3.3 Worked example — full bond valuation

**Instrument:** 5-year Treasury, 4.00% semiannual coupon, $100 face, priced on a flat 4.50% continuously-compounded curve.

| Period | *t* (yrs) | CF ($) | `DF = e^(−0.045t)` | PV ($) |
|---|---|---|---|---|
| 1 | 0.5 | 2.00 | 0.977751 | 1.955502 |
| 2 | 1.0 | 2.00 | 0.955997 | 1.911994 |
| 3 | 1.5 | 2.00 | 0.934730 | 1.869460 |
| 4 | 2.0 | 2.00 | 0.913931 | 1.827862 |
| 5 | 2.5 | 2.00 | 0.893587 | 1.787174 |
| 6 | 3.0 | 2.00 | 0.873716 | 1.747432 |
| 7 | 3.5 | 2.00 | 0.854274 | 1.708548 |
| 8 | 4.0 | 2.00 | 0.835270 | 1.670540 |
| 9 | 4.5 | 2.00 | 0.816686 | 1.633372 |
| 10 | 5.0 | 102.00 | 0.798516 | 81.448632 |
| | | | **Total** | **97.560516** |

**Price = $97.5605** per $100 face. The bond trades at a discount because its 4.00% coupon is below the 4.50% market rate.

Sanity check: coupon < market rate ⟹ price < par. ✓

---

## 4. Derivative pricing

### 4.1 The two families

| Family | Method | Applies to |
|---|---|---|
| **Replication / no-arbitrage** | Value = cost of the replicating portfolio | Forwards, futures, swaps — all linear products |
| **Risk-neutral expectation** | Value = discounted expected payoff under the risk-neutral measure | Options — all contingent claims |

### 4.2 Linear products: forwards

A forward's value is fixed by the impossibility of arbitrage, and needs no volatility, no distribution and no model:

```
F  =  S · e^((r − q)·τ)
```

where *q* is the continuous yield on the underlying (dividend yield for equity, foreign rate for FX, convenience yield less storage for commodities).

**Why no model is needed.** To deliver an asset at *T*, borrow `S·e^(−qτ)` today, buy the asset, carry it, deliver it. The cost is entirely determined by observable rates. **Any forward price other than *F* is an arbitrage.**

### 4.3 Contingent claims: Black-Scholes-Merton

For a European call on a non-dividend-paying asset:

```
C  =  S·N(d₁)  −  K·e^(−rτ)·N(d₂)

           ln(S/K) + (r + σ²/2)·τ
d₁  =  ───────────────────────────────
                  σ·√τ

d₂  =  d₁ − σ·√τ
```

| Symbol | Meaning | Unit |
|---|---|---|
| *S* | Spot price of underlying | price |
| *K* | Strike | price |
| *r* | Continuous risk-free rate | decimal p.a. |
| *σ* | Volatility of log returns | decimal p.a. |
| *τ* | Time to expiry | years |
| `N(·)` | Standard normal CDF | — |

**Interpretation of the two terms.** `S·N(d₁)` is the present value of receiving the asset if exercised; `K·e^(−rτ)·N(d₂)` is the PV of paying the strike if exercised. `N(d₂)` is the risk-neutral probability of finishing in the money.

### 4.4 Worked example — European call

*S* = 100, *K* = 100, *r* = 4%, *σ* = 20%, *τ* = 1 year.

```
d₁ = [ln(1) + (0.04 + 0.02)·1] / (0.20·1)  =  0.06/0.20  =  0.30
d₂ = 0.30 − 0.20                           =  0.10

N(0.30) = 0.617911      N(0.10) = 0.539828

C = 100·0.617911 − 100·e^(−0.04)·0.539828
  = 61.7911 − 100·0.960789·0.539828
  = 61.7911 − 51.8663
  = $9.925
```

Put by parity: `P = C − S + K·e^(−rτ) = 9.925 − 100 + 96.079 = $6.004`.

### 4.5 Black's model — the rates and commodities variant

For options on a **forward** rather than a spot (swaptions, caps/floors, commodity options), substitute the forward and discount separately:

```
C  =  e^(−rτ) · [ F·N(d₁) − K·N(d₂) ]

           ln(F/K) + (σ²/2)·τ
d₁  =  ─────────────────────────
              σ·√τ
```

### 4.6 The Bachelier (normal) model

When the underlying can go negative — EUR and JPY rates after 2014, WTI crude in April 2020 — a lognormal model is not merely inaccurate, it is **impossible**: it assigns probability zero to observed events.

```
C  =  e^(−rτ) · [ (F−K)·N(d) + σ_N·√τ · φ(d) ]

              F − K
d  =  ────────────────────
          σ_N · √τ
```

where `σ_N` is **normal** (absolute) volatility, quoted in basis points per annum, and `φ` is the standard normal density.

> The interest-rate options market now quotes predominantly in normal volatility. Confusing normal with lognormal volatility produces errors of orders of magnitude, not percentages. **Always confirm the volatility convention before using a quote.**

### 4.7 The assumptions, and where they fail

Black-Scholes assumes: constant volatility, lognormal prices, continuous frictionless hedging, constant rates, no jumps.

| Assumption | Reality | Market response |
|---|---|---|
| Constant σ | Volatility varies by strike and expiry | The **volatility surface**; local/stochastic vol models |
| Lognormal | Fat tails; negative rates and prices | Bachelier; jump-diffusion; SABR |
| Continuous hedging | Discrete, costly rebalancing | Gamma P&L; bid-offer reserves |
| Constant rates | Stochastic rates | Multi-factor models for long-dated |
| No jumps | Gaps happen | Stress testing; RRAO gap risk |

**The volatility surface is the market's correction to the model.** Practitioners do not believe Black-Scholes; they use it as a *quoting device* — a bijective map between price and a single number, σ. The surface is then the record of exactly how wrong the model is at each strike and expiry.

---

## 5. Valuation adjustments (XVA) — first pass

The theoretical price is not the fair value a bank carries. A sequence of adjustments intervenes:

| Adjustment | Reflects | Sign to the bank |
|---|---|---|
| **CVA** | Counterparty may default while owing us | Reduces value |
| **DVA** | *We* may default while owing them | Increases value (controversially) |
| **FVA** | Funding cost of uncollateralised positions | Usually reduces |
| **MVA** | Cost of posting initial margin | Reduces |
| **ColVA** | Value of collateral optionality in the CSA | Either |

These are **market-risk-sensitive**: CVA moves with credit spreads *and* with the underlying market factors that determine exposure. Regulatory CVA risk is capitalised in a framework of its own, separate from trading-book market risk — see [22](22_Counterparty_CVA_and_SIMM.md).

---

## 6. Pseudocode — the pricing pipeline

```
FUNCTION value_portfolio(positions, market_data, valuation_date):

    # 1 — validate inputs before anything else
    validated = validate(market_data)          # staleness, outliers, completeness
    IF validated.has_blocking_errors: HALT and escalate

    # 2 — build curves (order matters: discount before projection)
    discount_curves = {}
    FOR each ccy IN currencies(positions):
        discount_curves[ccy] = bootstrap_ois(validated.ois_quotes[ccy])

    projection_curves = {}
    FOR each (ccy, index) IN indices(positions):
        projection_curves[ccy,index] = bootstrap_projection(
            validated.basis_quotes[ccy,index],
            discount_curves[ccy])

    # 3 — build surfaces
    vol_surfaces = {}
    FOR each underlying IN option_underlyings(positions):
        vol_surfaces[underlying] = calibrate_surface(validated.vol_quotes[underlying])

    # 4 — price each position with the model its product type requires
    results = []
    FOR each p IN positions:
        curves = select_curves(p, discount_curves, projection_curves)   # CSA-aware
        model  = model_for(p.product_type)
        pv     = model.price(p, curves, vol_surfaces, valuation_date)
        results.append((p.id, pv))

    # 5 — apply valuation adjustments at the netting-set level
    results = apply_xva(results, positions, curves, vol_surfaces)

    RETURN results
```

**Invariant:** every position must price. A position that fails to price is not worth zero — it is unknown, and must be escalated, never silently defaulted. Silently zeroing a failed valuation is one of the most dangerous defects a risk system can contain, because it removes both the value *and* the risk from every downstream report.

---

## 7. Validation checks

| Check | Test | Detects |
|---|---|---|
| **Curve reprices inputs** | Reprice each bootstrapping instrument on its own curve → 0 (to tolerance) | Bootstrap or interpolation defects |
| **Forwards are sane** | Plot implied forwards; check positivity/oscillation | Bad interpolation |
| **Put-call parity** | `C − P − S·e^(−qτ) + K·e^(−rτ) = 0` | Surface or discounting inconsistency |
| **Monotonicity** | Call price decreasing in *K*; increasing in σ, τ | Surface arbitrage |
| **No calendar arbitrage** | Total variance `σ²τ` non-decreasing in τ at fixed moneyness | Surface arbitrage |
| **No butterfly arbitrage** | Implied density non-negative | Surface arbitrage |
| **Analytic vs bumped Greeks** | Compare closed-form to finite difference | Pricer bugs |
| **Par instrument prices to par** | New at-market swap PV ≈ 0 | Curve/pricer disagreement |
| **Day-count independence** | Same trade, two date engines | Calendar/convention defects |

---

## 8. Limitations

- Closed-form solutions exist only for a small set of products. Everything path-dependent, callable or multi-underlying requires numerical methods — trees, PDE solvers, or Monte Carlo — and those bring their own convergence and stability questions.
- Model choice is itself a risk. Two banks with identical market data and identical positions will report different values for an exotic. See [26](26_Model_Risk_and_Validation.md).
- The prices produced here are **model-implied**. For an illiquid instrument the model price and the achievable price can differ substantially, which is what valuation reserves and prudent valuation exist to address.

---

## 9. Related Concepts

- [04 — Interest Rate Risk](04_Interest_Rate_Risk.md) — differentiating these prices
- [09 — Options and Greeks](09_Options_and_Greeks.md) — differentiating the option formulas
- [23 — Market Data and Curves](23_Market_Data_and_Curves.md) — the full curve construction treatment
- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.8` curve vertices; `MAR33.12` options modelling requirements |
| ISDA | 2021 ISDA Interest Rate Derivatives Definitions | 2021 | https://www.isda.org/ | Day-count and business-day conventions |
| ARRC | SOFR conventions and transition materials | ongoing | https://www.newyorkfed.org/arrc | RFR compounding and multi-curve conventions |

*Accessed 25 August 2026.*
