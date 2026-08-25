# 09 — Options and the Greeks

**Level:** 5 · **Prerequisites:** [03](03_Pricing_Fundamentals.md) · **Feeds:** [11](11_VaR.md), [13](13_Stress_Testing.md), [17](17_FRTB_Standardised_Approach.md)

> **Running example used throughout.** A European call: *S* = 100, *K* = 100, *r* = 4%, *σ* = 20%, *τ* = 1 year, no dividends. From [03 §4.4](03_Pricing_Fundamentals.md): `d₁ = 0.30`, `d₂ = 0.10`, `N(d₁) = 0.617911`, `N(d₂) = 0.539828`, `φ(d₁) = 0.381388`, **C = $9.925**, **P = $6.004**.

---

## 1. Options from fundamentals

### 1.1 Plain English

An option is the **right, but not the obligation**, to buy (call) or sell (put) something at a fixed price by a fixed date.

The buyer pays a premium for that right. The seller receives the premium and takes on the obligation.

### 1.2 The asymmetry that changes everything

| | Buyer | Seller |
|---|---|---|
| Best case | Unlimited (call) / large (put) | The premium, and nothing more |
| Worst case | The premium | **Unlimited (call) / large (put)** |
| Position character | Long optionality, long gamma, long vega | Short optionality, **short gamma**, short vega |

> **This asymmetry is why options risk cannot be managed with linear tools.** A linear position's risk is proportional to its size. A short option position's risk is proportional to something that grows as the market moves against it. The exposure is not merely large — it is *state-dependent*, and it grows fastest exactly when it is hurting you.

### 1.3 Payoff and value

At expiry, a call is worth `max(S_T − K, 0)`. Before expiry it is worth more, because there is still time for the underlying to move. That excess is **time value**, and it is what all the machinery below is really about.

```
   Option value  =  Intrinsic value  +  Time value
   Call intrinsic = max(S − K, 0)
```

Our example call is exactly at the money: intrinsic = 0, so the entire $9.925 is time value.

---

## 2. The Taylor expansion — the organising idea

Every Greek is a term in one expansion. This is the single most useful frame for the whole document:

```
   ΔV  ≈   Δ·ΔS                      delta      first order in spot
         + ½·Γ·(ΔS)²                 gamma      second order in spot
         + ν·Δσ                      vega       first order in vol
         + Θ·Δt                      theta      first order in time
         + ρ·Δr                      rho        first order in rate
         + Vanna·ΔS·Δσ               vanna      spot-vol cross term
         + ½·Volga·(Δσ)²             volga      second order in vol
         + …
```

**Reading the expansion tells you the whole risk-management strategy.** Delta-hedging kills the first term. What remains — gamma, vega, theta — is the actual position. A delta-hedged option book is a bet on realised versus implied volatility, and nothing else.

---

## 3. Delta

### 3.1 Plain English

How much the option's value changes when the underlying moves one unit.

### 3.2 Formula

```
   Δ_call  =  e^(−qτ) · N(d₁)
   Δ_put   =  e^(−qτ) · [ N(d₁) − 1 ]
```

### 3.3 Worked example

```
   Δ_call  =  N(0.30)  =  0.6179
   Δ_put   =  0.6179 − 1  =  −0.3821
```

On 1,000 contracts of 100 shares each: `0.6179 × 100,000 = 61,790` shares equivalent. To be delta-neutral the desk sells 61,790 shares.

### 3.4 Interpretation

| Δ | Meaning |
|---|---|
| ≈ 1.00 | Deep in the money — behaves like the underlying |
| ≈ 0.50 | At the money |
| ≈ 0.00 | Deep out of the money — nearly worthless, nearly insensitive |

`N(d₂)` (here 0.5398) is the **risk-neutral probability of finishing in the money**. `N(d₁)` is *not* that probability, though it is often loosely described as such — it is the delta, and the two differ by `σ√τ` in the argument.

### 3.5 The stickiness caveat

Delta as computed above assumes the volatility surface does not move when spot moves. On a skewed surface that assumption is wrong, and the **actual** delta a desk hedges with is adjusted for how the surface travels. See [07 §7.2](07_Equity_Risk.md) — sticky strike, sticky delta and local volatility give three different deltas for the same option.

### 3.6 Units and aggregation

Currency per unit of underlying, or equivalently a share/contract equivalent. **Delta aggregates by simple summation across options on the same underlying.**

---

## 4. Gamma

### 4.1 Plain English

How fast delta itself changes. Gamma is the curvature of the option's value.

### 4.2 Banking example

A desk is short 1,000 at-the-money calls and delta-hedged. Overnight the stock jumps 8%.

Delta was 0.50 and is now roughly 0.70. The desk is short 20 more deltas per contract than its hedge covers — it is now short 20,000 shares into a rising market, and must buy them back higher. Tomorrow the stock falls; now it is long too many, and must sell lower.

> **Short gamma means you buy high and sell low, mechanically, forever.** That is what the premium was compensation for. The trade is profitable if realised volatility stays below implied, and loses if it does not.

### 4.3 Formula

```
                 e^(−qτ) · φ(d₁)
   Γ  =  ─────────────────────────────
                 S · σ · √τ
```

Gamma is **identical for calls and puts** on the same strike and expiry.

### 4.4 Worked example

```
   Γ  =  0.381388 / (100 × 0.20 × 1)  =  0.019070   per $1 move
```

If spot moves from 100 to 101, delta moves from 0.6179 to approximately `0.6179 + 0.01907 = 0.6370`.

**Dollar gamma** — the P&L from the gamma term for a 1% move:

```
   ½ · Γ · (ΔS)²  =  0.5 × 0.019070 × 1²  =  $0.0095 per share per $1 move
```

Over 100,000 shares equivalent and a $5 move: `0.5 × 0.019070 × 25 × 100,000 = $23,838` of gamma P&L — positive if long gamma, negative if short.

### 4.5 The gamma-theta trade-off

```
   Long gamma   ⟹   Θ < 0   —  you gain from movement, and pay for the privilege daily
   Short gamma  ⟹   Θ > 0   —  you collect daily, and lose from movement
```

**This is not a coincidence; it is the structure of option pricing.** In the Black-Scholes PDE, theta and gamma are tied together:

```
   Θ  +  ½ σ² S² Γ  +  r S Δ  −  r V  =  0
```

A delta-hedged position's daily P&L is approximately:

```
   P&L  ≈  ½ · Γ · S² · ( σ_realised²·Δt − σ_implied²·Δt )
```

**A delta-hedged option book is a pure bet on realised versus implied volatility.** That single equation is the entire economic content of a volatility trading desk.

### 4.6 Where gamma is most dangerous

Gamma is largest **at the money, close to expiry**. As `τ → 0` for an at-the-money option, gamma → ∞. A book of short at-the-money options in the final days before expiry has effectively unbounded convexity, and hedging it requires trading that itself moves the market — the mechanism behind expiry-day "pinning" effects.

---

## 5. Vega

### 5.1 Plain English

How much the option's value changes when implied volatility changes by one point.

### 5.2 Banking example

A desk is short a straddle. The underlying does not move at all. Implied volatility rises from 18% to 24%. The desk loses money on a position whose underlying never budged — **volatility is a traded price in its own right.**

### 5.3 Formula

```
   ν  =  S · e^(−qτ) · φ(d₁) · √τ
```

Vega, like gamma, is **the same for calls and puts** on the same strike and expiry.

### 5.4 Worked example

```
   ν  =  100 × 0.381388 × 1  =  38.139     per 1.00 (i.e. 100 vol points)
```

Market convention quotes vega **per one vol point (1%)**:

```
   ν  =  38.139 / 100  =  $0.3814  per 1% change in σ
```

A 3-point rise in implied vol (20% → 23%) gains a long position roughly `0.3814 × 3 = $1.14` per share.

### 5.5 Vega is not additive across expiries in any meaningful sense

Total vega is a seductive and misleading number. A book long 100,000 of 1-month vega and short 100,000 of 5-year vega has **zero total vega** and a very large position — the front end and back end of a volatility term structure move quite differently.

Vega must be **bucketed**, by expiry at minimum and usually by strike as well:

| Expiry | Vega ($/vol pt) | |
|---|---|---|
| 1M | +180,000 | long front vol |
| 3M | +95,000 | |
| 6M | −40,000 | |
| 1Y | −210,000 | short belly |
| 5Y | +65,000 | |
| **Total** | **+90,000** | **conceals a large term-structure position** |

`MAR33.12` makes the same point in regulatory language: banks with material options books *"must have detailed specifications of the relevant volatilities"* and *"must model the volatility surface across both strike price and vertex (ie tenor)."*

---

## 6. Theta

### 6.1 Plain English

What the position earns or loses purely from one day passing.

### 6.2 Formula (call, no dividends)

```
              S · φ(d₁) · σ
   Θ  =  −  ─────────────────   −   r · K · e^(−rτ) · N(d₂)
                  2·√τ
```

### 6.3 Worked example

```
   Term 1  =  −(100 × 0.381388 × 0.20) / 2       =  −3.81388
   Term 2  =  −0.04 × 100 × 0.960789 × 0.539828  =  −2.07465
   Θ       =  −5.88853   per year
   Θ/day   =  −5.88853 / 365  =  −$0.01613  per share per day
```

A long position in 100,000 shares-equivalent of this option loses about **$1,613 per day** to time decay, if nothing else changes.

### 6.4 Interpretation

Theta is the **rent paid for gamma**. Long options: negative theta, positive gamma. Short options: positive theta, negative gamma. There is no position that is long gamma and positive carry.

**Theta is not a risk factor.** Time passes with certainty. It belongs in P&L attribution ([14](14_PnL_and_PnL_Explain.md)) and is deliberately excluded from VaR — including it would mean forecasting a known quantity.

---

## 7. Rho

```
   ρ_call  =  K · τ · e^(−rτ) · N(d₂)
   ρ_put   =  −K · τ · e^(−rτ) · N(−d₂)
```

**Worked example:**

```
   ρ_call  =  100 × 1 × 0.960789 × 0.539828  =  51.8663   per 1.00 (100%)
           =  $0.5187  per 1% change in r
```

Rho is small for short-dated equity and FX options and **large for long-dated ones**. For interest-rate options it is not a separate Greek at all — the rate *is* the underlying, and rho is subsumed into delta/DV01.

---

## 8. Second-order and cross Greeks

| Greek | Definition | Formula | Why it matters |
|---|---|---|---|
| **Vanna** | `∂²V/∂S∂σ` | `−e^(−qτ)·φ(d₁)·d₂/σ` | Exposure to **skew**; how vega moves with spot |
| **Volga (vomma)** | `∂²V/∂σ²` | `ν · d₁·d₂/σ` | Exposure to **smile**; vega convexity |
| **Charm** | `∂²V/∂S∂t` | — | Delta decay; matters over weekends and holidays |
| **Speed** | `∂³V/∂S³` | — | Gamma's rate of change; barriers, large moves |
| **Colour** | `∂³V/∂S²∂t` | — | Gamma decay near expiry |
| **Cross-gamma** | `∂²V/∂S₁∂S₂` | — | Multi-underlying products; convertibles, quantos |

### 8.1 Worked example — vanna and volga

```
   Vanna  =  −0.381388 × 0.10 / 0.20  =  −0.190694
   Volga  =  38.139 × (0.30 × 0.10) / 0.20  =  38.139 × 0.15  =  5.7209
```

Vanna is negative: as spot rises, vega falls. Volga is positive: the position is long vol-of-vol.

### 8.2 Where the second-order Greeks are first-order concerns

| Market | Which matter | Why |
|---|---|---|
| **FX** | **Vanna, volga** | The skew (risk reversal) is deeply liquid and separately traded; the market-standard vanna-volga approach exists for exactly this reason |
| **Equity** | Vanna, cross-gamma | Persistent downside skew; multi-underlying structured products |
| **Rates** | Cross-gamma | Discount and projection curve interaction |
| **Convertibles** | **Cross-gamma** | Equity delta depends on credit spread; credit sensitivity depends on equity level |

---

## 9. The volatility surface

### 9.1 What it is

Implied volatility is not a constant. Plot it against strike and expiry and you get a **surface**. Its shape is the market's systematic correction to Black-Scholes.

| Feature | Description | Typical market |
|---|---|---|
| **Skew** | Monotone tilt across strikes | Equity (puts bid), commodity |
| **Smile** | U-shape — both wings above ATM | FX |
| **Term structure** | ATM vol varies by expiry | All; usually upward-sloping in calm, inverted in stress |

### 9.2 Why the skew exists in equities

- Markets fall faster than they rise (leverage effect)
- Correlations converge in falls, so index downside vol exceeds constituent-implied
- Structural institutional demand for downside protection
- Post-1987 repricing of crash risk — **the equity skew has been persistent since October 1987**

### 9.3 Surface arbitrage constraints

A fitted surface must be free of arbitrage, and the constraints are testable:

| Constraint | Test | Violation means |
|---|---|---|
| **Calendar spread** | Total variance `σ²τ` non-decreasing in τ at fixed moneyness | Free money across expiries |
| **Butterfly** | Implied risk-neutral density non-negative | Free money across strikes |
| **Monotonicity** | `∂C/∂K ≤ 0`, `C` increasing in σ | Basic no-arbitrage |
| **Put-call parity** | `C − P = S·e^(−qτ) − K·e^(−rτ)` | Inconsistent call/put surfaces |

**Verification on our example:** `C − P = 9.925 − 6.004 = 3.921`, and `S − K·e^(−rτ) = 100 − 96.0789 = 3.9211`. ✓

---

## 10. Approximation versus full revaluation

### 10.1 The comparison

| | Sensitivity-based (Taylor) | Full revaluation |
|---|---|---|
| Cost | 1 pricing + stored Greeks | *n* pricings per scenario |
| Accuracy for small moves | Excellent | Exact |
| Accuracy for large moves | **Degrades badly** | Exact |
| Path-dependent products | **Fails** | Correct |
| Barriers/digitals | **Fails near the barrier** | Correct |
| Use for | Intraday risk, limits, quick scenarios | Stress, regulatory capital, exotic books |

### 10.2 Where the approximation breaks — worked

Our call, with spot moving from 100:

| ΔS | Delta only | Delta+gamma | **Exact BSM** | Error (Δ only) | Error (Δ+Γ) |
|---|---|---|---|---|---|
| +1 | 10.5430 | 10.5525 | **10.5524** | −0.0095 | +0.0001 |
| +5 | 13.0146 | 13.2530 | **13.2423** | −0.2277 | +0.0106 |
| +10 | 16.1042 | 17.0576 | **16.9687** | −0.8645 | +0.0890 |
| +20 | 22.2833 | 26.0972 | **25.3564** | −3.0732 | +0.7407 |
| −20 | −2.4332 | 1.3807 | **1.7056** | −4.1387 | −0.3249 |

*(Exact values recomputed from the Black-Scholes formula at each spot. Delta and gamma are held at their base-case values — which is exactly what a sensitivity-based risk system does.)*

**Three things to read from this table.**

1. **At ±1 the linear estimate is fine.** −0.0095 on a $9.93 option is immaterial. This is why delta hedging works intraday.

2. **The delta-only error grows super-linearly and becomes absurd.** At −20 the linear estimate is **−2.43** — a *negative* value for a long call, which can never be worth less than zero. The error, −4.14, is more than double the option's actual value of 1.71.

3. **Adding gamma helps enormously but has a sign pattern worth understanding.** Delta+gamma *overshoots* on the upside (+0.74 at +20) and *undershoots* on the downside (−0.32 at −20). The reason is that gamma is not constant: for a call it declines as spot rises past the money, so a second-order expansion holding gamma fixed at its at-the-money value over-credits the convexity on the way up. That residual is the third-order term (**speed**), and it is why even a delta-gamma approximation is not a substitute for revaluation at stress magnitudes.

> **Sensitivities are a local tool. Stress testing is a global one. Using the first where you need the second is the single most common cause of understated tail risk in an options book.**

### 10.3 Linear versus non-linear portfolios

| | Linear portfolio | Non-linear portfolio |
|---|---|---|
| Value is | Approximately affine in factors | Curved |
| Delta-normal VaR | Reasonable | **Can be badly wrong** |
| Risk when delta-hedged | ≈ zero | Gamma, vega, theta remain |
| Loss under a large move | Proportional | Can be quadratic or discontinuous |
| Correct VaR approach | Parametric acceptable | **Full-revaluation historical or Monte Carlo** |

---

## 11. FRTB treatment — vega and curvature

### 11.1 Vega risk weights (`MAR21.92`, Table 13)

The vega risk weight for risk factor *k* is determined by a formula in which **σ is set at 55%**, and `LH_risk class` is the regulatory liquidity horizon per risk class:

| Risk class | Regulatory liquidity horizon (`LH`) |
|---|---|
| GIRR | **60** |
| CSR non-securitisations | **120** |
| CSR securitisations (CTP) | **120** |
| CSR securitisations (non-CTP) | **120** |
| Equity (large cap and indices) | **20** |
| Equity (small cap and other sector) | **60** |
| Commodity | **120** |
| FX | **40** |

Two notes: the same bucket definitions are used for vega as for delta (`MAR21.91`); and the corresponding delta correlation parameters are reused for vega aggregation (e.g. γ = 50% across GIRR buckets).

### 11.2 Curvature — the mechanism

Curvature is FRTB's answer to gamma, and it is **not** an analytical second derivative. It is a prescribed up/down revaluation that measures **the loss beyond what delta already charged**.

Per `MAR21.5(2)`, for each curvature risk factor *k*:

```
   CVR_k⁺  =  − Σ_i [ V_i(x_k^(RW+)) − V_i(x_k) − RW_k^curv · s_ik ]

   CVR_k⁻  =  − Σ_i [ V_i(x_k^(RW−)) − V_i(x_k) + RW_k^curv · s_ik ]
```

where:
- `V_i(x_k)` is the price of instrument *i* at the current level of risk factor *k*
- `V_i(x_k^(RW±))` is its price after *k* is shocked up / down by the curvature risk weight
- `RW_k^curv` is the curvature risk weight for factor *k*
- `s_ik` is the delta sensitivity of instrument *i* to the corresponding delta risk factor — **for FX and equity, the instrument's delta sensitivity; for GIRR, CSR and commodity, the sum of delta sensitivities across all tenors of the relevant curve** (`MAR21.5(2)(f)`)

**The subtraction of `RW · s` is the whole point.** It removes the linear component already captured in the delta charge, leaving only the incremental, convexity-driven loss. For GIRR, `MAR21.5(1)(a)` specifies that *all* tenors of *all* risk-free curves in a currency are shifted together.

### 11.3 Curvature aggregation (`MAR21.5(3)`–`(4)`)

```
   K_b⁺  =  max( 0,  Σ_k max(CVR_k⁺, 0)²  +  Σ_{k≠l} ρ_kl · CVR_k⁺ · CVR_l⁺ · ψ(CVR_k⁺, CVR_l⁺) )^½

   K_b⁻  =  max( 0,  Σ_k max(CVR_k⁻, 0)²  +  Σ_{k≠l} ρ_kl · CVR_k⁻ · CVR_l⁻ · ψ(CVR_k⁻, CVR_l⁻) )^½

   K_b   =  max( K_b⁺ , K_b⁻ )
```

where **ψ(x,y) = 0 if x and y both have negative signs, and 1 otherwise.**

Then across buckets:

```
   Curvature risk charge  =  max( 0,  Σ_b S_b²  +  Σ_{b≠c} γ_bc · S_b · S_c · ψ(S_b, S_c) )^½
```

with `S_b = CVR_b⁺` if the upward scenario was selected for bucket *b*, and `CVR_b⁻` otherwise.

Two subtleties the standard makes explicit and implementations frequently miss:

1. **The choice of upward vs downward scenario is made per bucket, and is not necessarily the same across the high, medium and low correlation scenarios** (`MAR21.5(3)(a)`).
2. In the tie case `K_b⁺ = K_b⁻`, the upward scenario is deemed selected if `CVR_b⁺ > CVR_b⁻`; otherwise the downward scenario (`MAR21.5(3)(a)(iii)`).

### 11.4 Carve-outs

There is **no curvature risk capital requirement for equity repo rates**, and no vega requirement on them either. Curvature for equity applies to spot prices only.

### 11.5 The three correlation scenarios apply here too

Everything above is computed three times under `MAR21.6` — medium, high (ρ, γ × **1.25**, capped at 100%) and low (`max(2ρ − 100%, 75% × ρ)`) — and the SBM capital requirement is the **largest of the three** (`MAR21.7`).

---

## 12. Pseudocode

```
FUNCTION greeks_bsm(S, K, r, q, sigma, tau, is_call):
    d1 = (ln(S/K) + (r - q + 0.5*sigma^2)*tau) / (sigma*sqrt(tau))
    d2 = d1 - sigma*sqrt(tau)
    Nd1, Nd2 = normcdf(d1), normcdf(d2)
    pdf1     = normpdf(d1)
    disc_q, disc_r = exp(-q*tau), exp(-r*tau)

    IF is_call:
        price = S*disc_q*Nd1 - K*disc_r*Nd2
        delta = disc_q*Nd1
        theta = (-S*disc_q*pdf1*sigma/(2*sqrt(tau))
                 - r*K*disc_r*Nd2 + q*S*disc_q*Nd1)
        rho   = K*tau*disc_r*Nd2
    ELSE:
        price = K*disc_r*normcdf(-d2) - S*disc_q*normcdf(-d1)
        delta = disc_q*(Nd1 - 1)
        theta = (-S*disc_q*pdf1*sigma/(2*sqrt(tau))
                 + r*K*disc_r*normcdf(-d2) - q*S*disc_q*normcdf(-d1))
        rho   = -K*tau*disc_r*normcdf(-d2)

    gamma = disc_q*pdf1 / (S*sigma*sqrt(tau))
    vega  = S*disc_q*pdf1*sqrt(tau)
    vanna = -disc_q*pdf1*d2/sigma
    volga = vega*d1*d2/sigma

    RETURN { price, delta, gamma, vega:vega/100, theta:theta/365,
             rho:rho/100, vanna, volga }
    # vega and rho scaled to per-1%; theta to per-day


FUNCTION frtb_curvature(instruments, risk_factor_k, rw_curv, deltas):
    base = sum(price(i, base_market) for i in instruments)
    up   = sum(price(i, shock(base_market, k, +rw_curv)) for i in instruments)
    dn   = sum(price(i, shock(base_market, k, -rw_curv)) for i in instruments)
    s_k  = sum(deltas[i][k] for i in instruments)   # summed across tenors for
                                                    # GIRR / CSR / commodity
    CVR_up   = -( up - base - rw_curv * s_k )
    CVR_down = -( dn - base + rw_curv * s_k )
    RETURN CVR_up, CVR_down
```

---

## 13. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Put-call parity | `C − P = S·e^(−qτ) − K·e^(−rτ)` |
| 2 | Analytic vs bumped Greeks | Agree within tolerance |
| 3 | Gamma/vega symmetry | Identical for call and put, same strike/expiry |
| 4 | Delta bounds | Call delta ∈ [0,1]; put delta ∈ [−1,0] |
| 5 | Gamma non-negative | For any long vanilla |
| 6 | Deep-ITM/OTM limits | Δ → 1 / 0; Γ, ν → 0 |
| 7 | Theta–gamma consistency | Black-Scholes PDE satisfied |
| 8 | Surface arbitrage | Calendar and butterfly tests pass |
| 9 | Vega bucketed | Never reported as a single scalar |
| 10 | Curvature delta offset | `RW · s` subtracted; tenors summed for GIRR/CSR/commodity |
| 11 | Curvature scenario selection | Per bucket, re-selected under each correlation scenario |
| 12 | ψ function | Returns 0 only when **both** arguments are negative |
| 13 | Repo carve-outs | No vega or curvature on equity repo rates |
| 14 | Full revaluation | Used for barriers, digitals and all path-dependent products |

---

## 14. Common implementation errors

| Error | Consequence |
|---|---|
| Reporting a single total vega | Term-structure position invisible |
| Using sensitivities for large stress shocks | Loss materially understated (see §10.2) |
| Delta from a stickiness regime never stated | Hedge ratios inconsistent and non-comparable |
| Sensitivity-based risk near a barrier | Delta/gamma discontinuity → hedge failure at the worst moment |
| Confusing `N(d₁)` with probability of exercise | Misstated risk narrative |
| Normal vs lognormal vol confused | Order-of-magnitude pricing errors |
| Curvature without the `RW · s` term | Double-counts delta |
| Curvature scenario fixed across correlation scenarios | Contradicts `MAR21.5(3)(a)` |
| Ignoring vanna/volga in FX | Skew and smile exposure unreported |
| Theta included in VaR | Forecasting a known quantity |

---

## 15. Limitations

- Every Greek above is a **Black-Scholes** derivative. If the pricing model differs, the Greeks differ.
- Greeks are **local**. They describe today's position at today's market, and degrade as the market moves — fastest for the most convex books.
- Discrete hedging means realised gamma P&L differs from the theoretical, in a way that depends on rebalancing frequency and transaction costs.
- Barriers and digitals have **discontinuous** Greeks; no expansion converges near the discontinuity.
- Higher-order Greeks proliferate combinatorially in multi-underlying products; full revaluation is the only tractable answer.

---

## 16. Related Concepts

- [03 — Pricing Fundamentals](03_Pricing_Fundamentals.md) · [07 — Equity Risk](07_Equity_Risk.md) · [06 — FX Risk](06_FX_Risk.md)
- [11 — VaR](11_VaR.md) · [13 — Stress Testing](13_Stress_Testing.md) · [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.4`–`MAR21.7` aggregation; `MAR21.5` curvature; `MAR21.92` vega; `MAR33.12` options modelling |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR21 text |

*Accessed 25 August 2026.*
