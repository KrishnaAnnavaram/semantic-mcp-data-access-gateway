# 32 — Master Market Risk Formula Handbook

**Level:** Reference · **Organised:** basic → advanced · **Companion to:** [31 — Calculation Catalog](31_Master_Calculation_Catalog.md)

> **Notation used throughout.** `P` price · `V` value · `S` spot · `K` strike · `F` forward · `r` risk-free rate · `q` dividend or foreign rate · `σ` volatility · `τ` time to maturity (years) · `t` time · `y` yield · `s` credit spread · `z(t)` zero rate · `DF(t)` discount factor · `N(·)` standard normal CDF · `φ(·)` standard normal density · `w` weight · `Σ` covariance matrix · `ρ` correlation · `γ` cross-bucket correlation.

---

# LEVEL 1 — Time Value of Money

### 1.1 Discount factor

```
   DF(t)  =  e^(−z(t)·t)                                    [continuous]
   DF(t)  =  1 / (1 + z/f)^(f·t)                            [f-times compounding]
   DF(t)  =  1 / (1 + z·t)                                  [simple, money markets]
```

**Variables:** `z` zero rate (decimal p.a.), `t` years, `f` compounding frequency.
**Units:** dimensionless ratio, ∈ (0, 1] for positive rates; **can exceed 1 for negative rates**.
**Intuition:** what $1 at time *t* is worth today.
**Example:** `z = 4.5%` continuous, `t = 5`: `DF = e^(−0.225) = 0.798516`.
**Related:** 1.2, 1.3.

### 1.2 Compounding conversion

```
   r_continuous  =  f · ln(1 + r_f / f)
   r_f           =  f · ( e^(r_cont/f) − 1 )
```

**Intuition:** a rate without its compounding convention is not a number.
**Example:** 4.50% semiannual → `2·ln(1.0225) = 4.4501%` continuous.

### 1.3 Present value

```
            n
   PV  =    Σ   CFᵢ · DF(tᵢ)
           i=1
```

**Units:** currency. **The primitive on which everything else rests.**

### 1.4 Day-count fraction

```
   τ  =  days / basis
```

| Convention | Basis | Market |
|---|---|---|
| ACT/360 | actual days / 360 | USD MM, SOFR, EURIBOR |
| ACT/365F | actual days / 365 | GBP MM, SONIA |
| 30/360 | 30-day months / 360 | USD corporates, fixed swap legs |
| ACT/ACT (ISDA) | period-aware | Government bonds |

**Example:** 1 Jan → 1 Jul: ACT/360 = 181/360 = 0.502778; 30/360 = 0.500000. On $500m at 5%, a **$69,000** difference on one coupon.

---

# LEVEL 2 — Curves

### 2.1 Forward rate

```
                     1              DF(t₁)
   f(t₁, t₂)  =  ─────────── · ln ──────────
                   t₂ − t₁          DF(t₂)
```

**Units:** % p.a. **Intuition:** the rate contracted today for lending between *t₁* and *t₂*.
**Example:** `DF(1)=0.9615`, `DF(2)=0.9151` → `ln(1.05070) = 4.946%`.

### 2.2 Par swap rate

```
                Σᵢ  Lᵢ^proj · τᵢ · DF(tᵢ)              (floating leg PV)
   K_par  =  ──────────────────────────────
                     Σⱼ  τⱼ · DF(tⱼ)                    (the ANNUITY, A)
```

**The denominator is the annuity**, and it is very nearly the swap's DV01 per unit notional.

### 2.3 Swap PV and DV01

```
   PV_receive_fixed  =  N · [ K · A  −  FloatLegPV ]

   DV01_swap         ≈  N · A · 0.0001
```

**Example:** $100m 10-year swap, annuity 8.10 → `DV01 = 100,000,000 × 8.10 × 0.0001 = $81,000/bp`.

### 2.4 Covered interest parity

```
              1 + r_quote · τ
   F  =  S · ─────────────────           or       F = S · e^((r_q − r_b)·τ)
              1 + r_base  · τ
```

With the post-2008 residual:

```
   F_observed  =  S · (1 + r_q τ) / (1 + (r_b + basis)·τ)
```

**Example:** S = 1.0850, USD 4.50%, EUR 3.00%, τ = 1 → `F = 1.0850 × 1.014563 = 1.1008`; forward points = **158 pips**.

### 2.5 Cost of carry forwards

```
   Equity     :  F  =  S · e^((r − q)·τ)                      q = dividend yield
   Commodity  :  F  =  S · e^((r + u − y)·τ)                  u = storage, y = convenience yield
```

---

# LEVEL 3 — Bond Mathematics

### 3.1 Price

```
                n                              n         c·F/f              F
   P_dirty  =   Σ  CFᵢ · DF(tᵢ)      or        Σ   ─────────────  +  ─────────────
               i=1                            i=1   (1+y/f)^i        (1+y/f)^n
```

The first is how a risk system prices; the second is how a trader quotes. **They agree only on a flat curve.**

```
   P_clean  =  P_dirty  −  Accrued Interest
   AI       =  Coupon × (days since last coupon / days in period)
```

### 3.2 Macaulay duration

```
                Σ tᵢ · PV(CFᵢ)
   D_mac  =  ──────────────────
                     P
```

**Units:** years. **Example** ([04 §1.7](04_Interest_Rate_Risk.md)): 5-year 4% bond on a flat 4.5% continuous curve → **4.5748 years**.

### 3.3 Modified duration

```
                 1     ∂P             D_mac
   D_mod  =  − ───── · ────    =    ──────────
                 P     ∂y            1 + y/f
```

Under **continuous compounding**, `D_mod = D_mac`.
**Units:** % per 100bp.

### 3.4 DV01

```
   DV01  =  D_mod × P × 0.0001                                [analytic]

            P(y − 1bp) − P(y + 1bp)
   DV01  =  ────────────────────────                          [central bump — PREFERRED]
                       2
```

**Units:** currency per basis point. **Aggregates by simple sum within a currency; never across currencies.**
**Example:** `4.5748 × 97.560516 × 0.0001 = $0.044633` per $100 face = **$44,633/bp per $100m**.

### 3.5 Convexity

```
              1    ∂²P             1
   C   =    ───── ─────   =      ───── · Σ tᵢ² · PV(CFᵢ)      [continuous]
              P    ∂y²             P

   ΔP/P  ≈  − D_mod·Δy  +  ½·C·(Δy)²
```

**Example:** same bond → `C = 22.1173`. At +100bp: first order alone errs by 0.106; adding convexity leaves **+0.0018** — a 98.3% error reduction.

### 3.6 Effective duration and convexity

```
                P(−Δy) − P(+Δy)                       P(+Δy) + P(−Δy) − 2P₀
   D_eff  =  ─────────────────────       C_eff  =  ──────────────────────────
                  2 · P₀ · Δy                              P₀ · (Δy)²
```

**Mandatory** for callables, MBS and anything whose cash flows respond to rates. Both revaluations must **re-run the embedded-option model**.

### 3.7 Key-rate DV01

```
   KRD01(k)  =  P(curve with tent bump at T_k)  −  P(base curve)

                ⎧ Δy·(t − T_{k−1})/(T_k − T_{k−1})     T_{k−1} ≤ t ≤ T_k
   bump(t)  =   ⎨ Δy·(T_{k+1} − t)/(T_{k+1} − T_k)     T_k ≤ t ≤ T_{k+1}
                ⎩ 0                                     otherwise
```

**Completeness identity** — a mandatory check:

```
   Σ  KRD01(k)   =   DV01_parallel
   k
```

The outermost tents must be **flat beyond the outer key rates**, or the identity fails ([30 §3.1](30_Worked_Examples.md)).

### 3.8 Z-spread

```
                 n            CFᵢ
   P_market  =   Σ   ────────────────────       solve for s
                i=1   e^((z(tᵢ) + s)·tᵢ)
```

**Units:** basis points. **Related:** OAS = Z-spread with embedded option value removed.

### 3.9 CS01

```
              P(s − 1bp) − P(s + 1bp)
   CS01  =  ──────────────────────────          bump the SPREAD curve only
                        2
```

**The rate curve is held fixed.** That separation is the entire point ([05 §4](05_Credit_Spread_Risk.md)).

### 3.10 Credit triangle

```
   s  ≈  λ · (1 − R)
```

`λ` hazard rate, `R` recovery. **You cannot infer PD from spread without assuming recovery.**

### 3.11 Carry and roll

```
   Carry      =  Face·c·(n/365)  −  DirtyPrice·r_repo·(n/360)

   Roll-down  =  P(maturity − Δt, at the curve's yield for that shorter maturity)
               − P(maturity, at today's yield)

   Total static return  =  Carry + Roll-down
```

**Note the two different day-count bases in the carry formula** — a common and quiet source of error.

---

# LEVEL 4 — Options

### 4.1 Black-Scholes-Merton

```
   C  =  S·e^(−qτ)·N(d₁)  −  K·e^(−rτ)·N(d₂)
   P  =  K·e^(−rτ)·N(−d₂) −  S·e^(−qτ)·N(−d₁)

           ln(S/K) + (r − q + σ²/2)·τ
   d₁  =  ──────────────────────────────          d₂  =  d₁ − σ√τ
                     σ√τ
```

**Example** ([03 §4.4](03_Pricing_Fundamentals.md)): S=K=100, r=4%, σ=20%, τ=1 → `d₁=0.30`, `d₂=0.10`, **C = $9.925**, **P = $6.004**.

### 4.2 Black model (option on a forward)

```
   C  =  e^(−rτ) · [ F·N(d₁) − K·N(d₂) ]

           ln(F/K) + (σ²/2)·τ
   d₁  =  ──────────────────────          d₂  =  d₁ − σ√τ
                  σ√τ
```

### 4.3 Bachelier (normal) model

```
   C  =  e^(−rτ) · [ (F − K)·N(d)  +  σ_N·√τ · φ(d) ]

           F − K
   d  =  ──────────
          σ_N · √τ
```

`σ_N` is **normal (absolute) volatility**, quoted in bp p.a. **Required where the underlying can go negative.** Confusing normal with lognormal volatility produces order-of-magnitude errors.

### 4.4 Put-call parity

```
   C − P  =  S·e^(−qτ)  −  K·e^(−rτ)
```

**Verification on the §4.1 example:** `9.925 − 6.004 = 3.921`; `100 − 96.0789 = 3.9211`. ✓

### 4.5 The Greeks

```
   Δ_call  =  e^(−qτ)·N(d₁)                       Δ_put  =  e^(−qτ)·[N(d₁) − 1]

               e^(−qτ)·φ(d₁)
   Γ       =  ────────────────                    (identical for call and put)
                 S·σ·√τ

   ν       =  S·e^(−qτ)·φ(d₁)·√τ                  (identical for call and put)

                 S·φ(d₁)·σ
   Θ_call  =  − ───────────── − r·K·e^(−rτ)·N(d₂) + q·S·e^(−qτ)·N(d₁)
                    2√τ

   ρ_call  =  K·τ·e^(−rτ)·N(d₂)

                        d₂                                    d₁·d₂
   Vanna   =  −e^(−qτ)·φ(d₁)·──          Volga  =  ν · ─────────────
                         σ                                     σ
```

**Worked values** for the §4.1 example: `Δ = 0.6179`, `Γ = 0.019070`, `ν = 38.139` (per 1.00 = $0.3814 per vol point), `Θ = −5.8885`/yr = **−$0.01613/day**, `ρ = 51.87` (per 1.00 = $0.5187 per 1%), `Vanna = −0.190694`, `Volga = 5.7209`.

### 4.6 Taylor expansion of P&L

```
   ΔV  ≈  Δ·ΔS  +  ½Γ(ΔS)²  +  ν·Δσ  +  Θ·Δt  +  ρ·Δr
          +  Vanna·ΔS·Δσ  +  ½·Volga·(Δσ)²  +  …
```

**Every Greek is a term in this one expansion**, and delta-hedging is the act of removing the first term.

### 4.7 The Black-Scholes PDE and the gamma-theta identity

```
   Θ  +  ½σ²S²Γ  +  rSΔ  −  rV  =  0
```

From which a delta-hedged book's daily P&L is:

```
   P&L  ≈  ½ · Γ · S² · ( σ²_realised − σ²_implied ) · Δt
```

> **A delta-hedged option book is a pure bet on realised versus implied volatility.** That single line is the entire economic content of a volatility trading desk.

---

# LEVEL 5 — Portfolio Mathematics

### 5.1 Returns

```
   Arithmetic  :  r = (P₁ − P₀)/P₀           aggregates ACROSS ASSETS
   Logarithmic :  r = ln(P₁/P₀)              aggregates ACROSS TIME
```

**You cannot have both.** A weighted sum of log returns is not the portfolio's log return.

### 5.2 Volatility and annualisation

```
              ┌──────────────────────────┐
   σ  =  √    │  (1/(T−1)) · Σ (rₜ − r̄)² │              σ_annual = σ_daily · √252
              └──────────────────────────┘
```

**252 is a convention**, not a law. Apply it consistently across VaR, limits and reporting.

### 5.3 EWMA

```
   σ²ₜ  =  λ·σ²ₜ₋₁  +  (1 − λ)·r²ₜ₋₁                    effective window ≈ 1/(1−λ)
```

λ = 0.94 → ≈ 17 days.

### 5.4 Covariance and correlation

```
                    Cov(X,Y)
   ρ(X,Y)  =  ──────────────────                     Σ  =  D · R · D
                  σ_X · σ_Y
```

**Validity requirement:** Σ must be **positive semi-definite** — `xᵀΣx ≥ 0` for all `x`, because `xᵀΣx` *is* a portfolio variance.

### 5.5 Portfolio variance

```
   σ²_p  =  wᵀ Σ w   =   Σ wᵢ²σᵢ²  +  Σ Σ wᵢwⱼσᵢσⱼρᵢⱼ
                          i          i  j≠i
```

**Worked example** ([10 §4.2](10_Portfolio_Risk_Mathematics.md)): w = (0.6, 0.3, 0.1), σ = (10%, 20%, 35%), ρ = (0.30, 0.10, 0.50) → **σ_p = 11.4477%** against an undiversified 15.50%.

### 5.6 Risk decomposition

```
                 ∂σ_p        Cov(rᵢ, r_p)         (Σw)ᵢ
   MCRᵢ  =  ───────────  =  ───────────────  =  ─────────
                 ∂wᵢ              σ_p               σ_p

   CCRᵢ  =  wᵢ · MCRᵢ                    and         Σ CCRᵢ  =  σ_p
```

**The additive identity is Euler's theorem** applied to a homogeneous-of-degree-one risk measure, and it is what makes **component** contribution — not marginal — the right basis for limit allocation.

### 5.7 Beta

```
             Cov(rᵢ, r_m)          σᵢ
   βᵢ  =  ────────────────  =  ρ ────
              Var(r_m)             σ_m

   σᵢ²  =  β²σ_m²  +  σ_ε²                    systematic + idiosyncratic
```

### 5.8 Cholesky simulation

```
   Σ = L·Lᵀ        z ~ N(0, I)        x = L·z  has covariance Σ
```

**Cholesky exists iff Σ is positive definite.** A failure is the algorithm correctly refusing to simulate an impossible market.

---

# LEVEL 6 — Risk Measures

### 6.1 Value at Risk

```
   VaR_α  =  inf{ ℓ ∈ ℝ : P(L > ℓ) ≤ 1 − α }               [definition — a quantile]

   VaR_α  =  z_α · σ_p · V                                  [parametric, zero drift]
```

| Confidence | `z_α` |
|---|---|
| 95% | 1.644854 |
| 97.5% | 1.959964 |
| **99%** | **2.326348** |
| 99.9% | 3.090232 |

**Historical simulation:** rank the revalued scenario P&Ls; take the `(1−α)·N` quantile — **stating the convention** (round up / round down / interpolate).

### 6.2 Expected Shortfall

```
                    1        1
   ES_α   =   ───────────  ∫    VaR_u  du    =    E[ L | L ≥ VaR_α ]
                 1 − α      α

                            φ(z_α)
   ES_α   =   σ ·  ─────────────────                       [normal]
                            1 − α
```

| Confidence | `z_α` (VaR) | `φ(z_α)/(1−α)` (ES) | ES/VaR |
|---|---|---|---|
| 95% | 1.644854 | 2.062712 | 1.254 |
| **97.5%** | 1.959964 | **2.337803** | 1.193 |
| 99% | 2.326348 | 2.665213 | 1.146 |

> **The Basel calibration identity.** `ES(97.5%) multiplier = 2.337803` and `VaR(99%) z = 2.326348` differ by **0.49%**. Under normality the two measures are essentially the same number — which is why the switch was capital-neutral for well-behaved books and punitive for fat-tailed ones.

**Discrete ES**, handling the fractional tail observation:

```
                   1
   ES_α  =  ──────────────  ·  [  Σ (worst full observations)  +  frac × next  ]
              (1−α)·N
```

### 6.3 Square-root-of-time scaling

```
   VaR_h  =  VaR₁ · √h
```

**Assumes i.i.d. returns.** Volatility clustering means this **tends to understate** risk. `MAR33.4(5)` **prohibits** it for the ES base horizon: ES at horizon *T* must be computed for changes over *T* directly.

### 6.4 FRTB liquidity-adjusted ES

```
              ┌                                                        ┐ ½
              │                        ⎛              ⎛ LH_j − LH_{j−1} ⎞ ⎞² │
   ES  =      │  (ES_T(P))²  +   Σ    ⎜ ES_T(P, j)·√⎜ ──────────────── ⎟ ⎟  │
              │                 j≥2    ⎝              ⎝        T         ⎠ ⎠   │
              └                                                        ┘
```

`T` = 10 days; `LH = (10, 20, 40, 60, 120)`; `Q(pᵢ, j)` = risk factors whose horizon is **at least** `LH_j`, so **`Q(pᵢ,j) ⊆ Q(pᵢ,j−1)`**.

### 6.5 Reverse stress

```
   minimise   xᵀΣ⁻¹x            subject to    PnL(P, x) = −L*

                          L* · Σδ
   Linear solution:  x* = ─────────           implausibility = √(x*ᵀΣ⁻¹x*)
                          δᵀΣδ
```

**The least-unlikely path to any given loss is proportional to `Σδ`** — the covariance matrix applied to the sensitivity vector.

---

# LEVEL 7 — FRTB

### 7.1 SA total

```
   SA capital  =  SBM  +  DRC  +  RRAO                      [a SIMPLE SUM — MAR20.4]

   RWA         =  capital × 12.5                            [MAR20.1, MAR33.46]
```

### 7.2 SBM aggregation

```
   WS_k   =  s_k · RW_k                                     [MAR21.4(3)]

   K_b    =  √ max( 0 ,  Σ WS_k²  +  Σ Σ  ρ_kl·WS_k·WS_l )  [MAR21.4(4)]
                          k          k  l≠k

   Charge =  √ ( Σ K_b²  +  Σ Σ  γ_bc·S_b·S_c )             [MAR21.4(5)]
                  b        b  c≠b

   where  S_b = Σ WS_k ;  and if the sum under the root is NEGATIVE:
          S_b = max[ min( Σ WS_k , K_b ) , −K_b ]           [MAR21.4(5)(b)]
```

### 7.3 Curvature

```
   CVR_k⁺  =  − Σ [ V_i(x_k^(RW+)) − V_i(x_k) − RW_k^curv·s_ik ]
   CVR_k⁻  =  − Σ [ V_i(x_k^(RW−)) − V_i(x_k) + RW_k^curv·s_ik ]

   K_b⁺ = √max(0, Σ max(CVR_k⁺,0)² + ΣΣ ρ_kl·CVR_k⁺·CVR_l⁺·ψ(·,·) )
   K_b  = max(K_b⁺, K_b⁻)

   ψ(x,y) = 0  if x AND y are both negative;  1 otherwise
```

**The `RW·s` term removes the linear component already charged under delta.**

### 7.4 The three correlation scenarios

```
   Medium :  ρ, γ as specified
   High   :  ρ, γ × 1.25,  capped at 100%
   Low    :  max( 2ρ − 100% , 75% × ρ )

   SBM capital  =  MAXIMUM of the three scenario totals      [MAR21.7]
```

### 7.5 GIRR cross-tenor correlation

```
   ρ(k,l)  =  max [ e^( −θ · |T_k − T_l| / min(T_k, T_l) ) ,  40% ]      θ = 3%
```

**Worked (standard's own footnote 13):** 1y vs 5y → `max(e^(−0.12), 0.40) = 88.69%`.
Different curves: **× 99.90%**. Across currencies: **γ = 50%**.

### 7.6 DRC

```
   JTD (long)   =  max( LGD·notional + P&L , 0 )
   JTD (short)  =  min( LGD·notional + P&L , 0 )            [MAR22.11]

                      Σ net JTD_long
   HBR  =  ──────────────────────────────────────           [MAR22.23]
             Σ net JTD_long + | Σ net JTD_short |

   DRC_b  =  max(  Σ RW_i·net JTD_i  −  HBR · Σ RW_i·|net JTD_i| , 0 )
               i∈Long                        i∈Short         [MAR22.25]
```

**LGD:** equity and non-senior debt 100%; senior debt 75%; covered bonds 25%.
**Sub-one-year exposures are maturity-scaled** by `maturity / capital horizon` (`MAR22.20(b)`).

### 7.7 RRAO

```
   RRAO  =  Σ ( gross notional × RW )         RW = 1.0% exotic underlying
                                              RW = 0.1% other residual risks
```

### 7.8 IMA capital

```
   IMCC  =  ρ·IMCC(C)  +  (1 − ρ)·Σ IMCC(Cᵢ)                 ρ = 0.5    [MAR33.15]

              ┌   I            J             ⎛    K        ⎞²        K         ┐ ½
   SES  =     │   Σ ISES²ᵢ  +  Σ ISES²ⱼ  +  ⎜ ρ·Σ SES_k  ⎟  + (1−ρ²)·Σ SES²_k │   ρ = 0.6
              └  i=1          j=1            ⎝   k=1       ⎠        k=1        ┘   [MAR33.17]

   C_A   =  max(  IMCC_{t−1} + SES_{t−1} ,  m_c·IMCC_avg60 + SES_avg60 )   [MAR33.41]

   m_c   =  1.5  +  backtesting add-on (0 to 0.5)  +  qualitative add-on   [MAR33.42]
```

> **ρ = 0.5 for IMCC and ρ = 0.6 for SES are different parameters in different formulas.** Confusing them is a common and costly implementation error.

### 7.9 PLA metrics

```
   Spearman  :  correlation of the RANK series of RTPL and HPL   [MAR32.36-38]

   KS        :  max | ECDF_RTPL(x) − ECDF_HPL(x) |               [MAR32.39-41]
                where each ECDF step = 0.004  (= 1/250)

   GREEN  :  ρ_s > 0.80  AND  KS < 0.09
   RED    :  ρ_s < 0.70  OR   KS > 0.12
   AMBER  :  neither                                             [MAR32.42]
```

**Green requires BOTH; red triggers on EITHER.**

---

# LEVEL 8 — Counterparty and XVA

### 8.1 Exposure

```
   Current exposure  =  max( Σ MTMᵢ − collateral , 0 )         [with netting]
   EE(t)             =  E[ max(V(t), 0) ]
   PFE(t)            =  quantile_α [ max(V(t), 0) ]
   EPE               =  time-weighted average of EE
```

### 8.2 Netting benefit

```
   Gross  =  Σ max(MTMᵢ, 0)              Net  =  max( Σ MTMᵢ , 0 )
```

**Valid only where the master netting agreement is legally enforceable.**

### 8.3 CVA

```
                T
   CVA  =  LGD ∫  EE(t) · dPD(t) · DF(t)     ≈   LGD · Σ EE(tᵢ)·ΔPD(tᵢ)·DF(tᵢ)
                0                                        i
```

**Example** ([22 §5.1](22_Counterparty_CVA_and_SIMM.md)): EPE $10m, spread 200bp, R = 40% → λ ≈ 3.33%, 5y cumulative PD ≈ 15.35%, **CVA ≈ $0.92m**.

### 8.4 SA-CCR

```
   EAD  =  alpha × ( RC  +  PFE )
```

---

# Quick-reference identities

These are the checks worth committing to memory, because each catches a whole class of error.

| Identity | Catches |
|---|---|
| `Σ KRD01(k) = DV01_parallel` | Gaps or overlaps in the bump scheme |
| `C − P = S·e^(−qτ) − K·e^(−rτ)` | Surface or discounting inconsistency |
| `Θ + ½σ²S²Γ + rSΔ − rV = 0` | Greek computation errors |
| `Σ CCRᵢ = σ_p` | Risk decomposition errors |
| `σ_p ≤ Σ wᵢσᵢ` | Correlation or matrix errors |
| `all ρ = 1  ⟹  σ_p = Σ wᵢσᵢ` | Aggregation logic |
| `ES_α ≥ VaR_α` | Tail computation errors |
| `ES(97.5%) ≈ VaR(99%)` under normality | Fat tails, when the gap is large |
| Zero-coupon bond: `D_mac = maturity` | Duration computation |
| Coupon > yield ⟹ price > par | Pricing sign errors |
| `Cholesky(Σ)` succeeds | Non-PSD covariance matrix |
| Curve reprices its own inputs | Bootstrap or interpolation defects |
| Par swap at inception: `PV = 0` | Curve/pricer disagreement |
| FRN: near-zero DV01, full CS01 | Rate/spread separation failure |

---

## Units reference

| Quantity | Unit | Note |
|---|---|---|
| PV, market value | currency | |
| DV01, PV01, BPV, CS01 | **currency per basis point** | Never sum across currencies |
| Duration | years | Macaulay and effective |
| Modified duration | % per 100bp | A *relative* measure |
| Convexity | dimensionless | Or currency for dollar convexity |
| Delta | currency per unit, or shares | State which |
| Gamma | delta per unit of underlying | |
| Vega | **currency per vol point (1%)** | Market convention divides the raw formula by 100 |
| Theta | **currency per day** | Raw formula is per year; divide by 365 |
| Rho | currency per 1% rate move | Divide raw formula by 100 |
| VaR, ES | currency | State confidence **and** horizon |
| Spread, yield | basis points or % p.a. | State compounding |
| Normal volatility | **bp p.a.** | Never interchangeable with lognormal |
| Lognormal volatility | **% p.a.** | |
| Risk weight (FRTB) | decimal or % | `MAR21` tables are in % |
| JTD | currency | |
| Correlation | dimensionless ∈ [−1, 1] | |

---

## Related Concepts

- [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) · [33 — Master Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md)
- [30 — Worked Examples](30_Worked_Examples.md) — every formula above, computed
- [34 — Glossary](34_Glossary.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | All Level 7 formulas, cited to paragraph |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | `MAR50`, `CRE52` for Level 8 |
| Artzner, Delbaen, Eber, Heath | *Coherent Measures of Risk* | 1999 | — | ES coherence |

> **Note on sourcing.** Levels 1–6 and 8 are standard quantitative finance and are stated here in the conventions used throughout this library. Level 7 formulas are reproduced from the Basel standard and cited to paragraph.

*Accessed 25 August 2026.*
