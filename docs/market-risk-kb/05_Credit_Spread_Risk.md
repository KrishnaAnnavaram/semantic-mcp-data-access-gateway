# 05 — Credit Spread Risk

**Level:** 4 · **Prerequisites:** [04](04_Interest_Rate_Risk.md) · **Feeds:** [17](17_FRTB_Standardised_Approach.md), [19](19_Default_Risk_and_DRC.md), [22](22_Counterparty_CVA_and_SIMM.md)

---

## 1. Plain English

**Credit spread risk is the risk that the market charges more to lend to an issuer — without that issuer defaulting.**

The distinction from default risk is the whole subject. A bond can lose 15% of its value because sentiment turned, and then pay every coupon and redeem at par. The holder still lost 15% *at the time*, in mark-to-market, in P&L, and in regulatory capital.

---

## 2. Banking example

A bank owns $50m of a BBB-rated industrial bond, 5-year maturity, trading at a Z-spread of 120bp over the risk-free curve.

The sector falls out of favour. Spreads widen to 160bp. Treasury yields are **unchanged**.

With spread duration of roughly 4.5:

```
Loss  ≈  50,000,000 × 4.5 × 40bp  =  50,000,000 × 4.5 × 0.0040  =  $900,000
```

The issuer has not missed a payment, has not been downgraded, and may well repay in full. The bank is nonetheless $900,000 poorer today.

---

## 3. Technical explanation

### 3.1 The decomposition

A credit-risky bond's yield decomposes as:

```
y_corporate   =   y_risk-free   +   credit spread
```

and the *spread* itself compensates for several distinct things at once:

| Component | What it pays for |
|---|---|
| Expected loss | PD × LGD over the horizon |
| Credit risk premium | Compensation for bearing *uncertainty* about that loss |
| Liquidity premium | Compensation for the cost of exiting |
| Structural/technical | Supply, indexation, regulatory demand, balance-sheet cost |

**None of these is directly observable, and their relative shares change.** This is why spread moves are only loosely related to changes in default probability, and why spread models and default models are separate objects.

### 3.2 The three spread measures

| Measure | Definition | Handles curve shape? | Handles optionality? | Correct use |
|---|---|---|---|---|
| **G-spread / yield spread** | Bond YTM − interpolated government yield at matched maturity | No | No | Quick quoting |
| **Z-spread** | Constant spread added to **every zero rate** such that PV = market price | **Yes** | No | Comparing bullet bonds |
| **OAS** | Z-spread with embedded option value removed, via a term-structure model | Yes | **Yes** | The **only** valid comparison for callables/MBS |

**Z-spread definition:**

```
                 n         CFᵢ
   P_market  =   Σ   ───────────────────
                i=1   e^( (z(tᵢ) + s) · tᵢ )
```

Solve for *s*. There is no closed form; it is a one-dimensional root-find, and it converges quickly because *P* is monotone decreasing in *s*.

**Why OAS matters.** A callable bond's Z-spread is inflated by the value of the call the investor has sold. Ranking callables by Z-spread systematically selects the bonds with the most sold optionality, dressed up as the cheapest bonds. OAS strips that out. **Comparing a callable's Z-spread to a bullet's Z-spread is not a comparison; it is a category error.**

---

## 4. CS01 — the central sensitivity

### 4.1 Plain English

The money made or lost if the issuer's credit spread moves one basis point.

### 4.2 Formula

**Analytic:**

```
CS01  ≈  Spread Duration  ×  Price  ×  0.0001
```

**Bump and revalue (production method, central difference):**

```
           P(s − 1bp)  −  P(s + 1bp)
CS01  =   ─────────────────────────────
                       2
```

The bump is applied to the **spread curve**, holding the risk-free curve fixed. That separation is the entire point.

### 4.3 Units

Currency per basis point. Also called **SDV01** (spread DV01), **CR01**, or **spread delta** depending on desk.

### 4.4 Numerical example

$50m of a 5-year BBB bond, price 98.20, spread duration 4.48.

```
CS01  =  50,000,000 × 0.9820 × 4.48 × 0.0001  =  $21,996 per bp
```

Spreads widen 40bp: `21,996 × 40 = $879,840` — reconciling with the §2 approximation.

### 4.5 Bucketed CS01

As with rates, a single number hides the curve. FRTB fixes the tenors at **0.5, 1, 3, 5 and 10 years** (`MAR21.9`).

| Tenor | CS01 ($/bp) | Reading |
|---|---|---|
| 0.5Y | 800 | |
| 1Y | 2,100 | |
| 3Y | 9,400 | |
| 5Y | 21,996 | main exposure |
| 10Y | −6,200 | short the long end |
| **Total** | **28,096** | |

This is a **credit curve flattener**: long 5-year risk, short 10-year risk. Total CS01 understates the position's exposure to a *steepening* of the credit curve entirely.

### 4.6 The dimensions of CS01

CS01 is reported along several axes simultaneously, because credit risk concentrates along all of them:

| Axis | Question it answers | Typical limit |
|---|---|---|
| **Issuer** | How exposed to one name? | Single-name CS01 cap |
| **Tenor** | Where on the credit curve? | Bucketed cap |
| **Sector** | Concentrated in one industry? | Sector cap |
| **Rating** | IG vs HY split | Rating-band cap |
| **Country** | Sovereign concentration | Country cap |
| **Curve type** | Bond vs CDS (the basis) | Basis cap |

### 4.7 Interpretation

| Sign | Position | Spreads widen | Spreads tighten |
|---|---|---|---|
| Positive CS01 | Long credit (own bonds, sold protection) | Lose | Gain |
| Negative CS01 | Short credit (bought protection) | Gain | Lose |

**Trader:** "I'm long $28,000 a basis point of credit. iTraxx is 5 wider this morning — that's $140,000 against me before I've done anything."

**Risk manager:** "Total CS01 is within limit, but 78% of it is in one sector, and the single-name concentration in the top three obligors is 40%. The limit isn't binding but the concentration is the actual risk."

---

## 5. FRN — the case that proves the concept

An FRN's coupon resets to the reference rate plus a fixed quoted margin. Consequences:

| | 5-year fixed bond | 5-year FRN |
|---|---|---|
| **DV01** (rate) | Full, ≈ 4.5 duration | ≈ 0 — only to the next reset |
| **CS01** (spread) | Full, ≈ 4.5 spread duration | **Full, ≈ 4.5** |

Why? The *reference rate* portion of the coupon resets, so rate risk is extinguished at each fixing. The *quoted margin* is contractually fixed for the bond's life, so if the market's required margin widens, the price must fall to compensate — over the full remaining maturity.

> **This asymmetry is the single cleanest demonstration that DV01 and CS01 are different quantities measuring different things.** A risk system that computes one "duration" and applies it to both is wrong by roughly a factor of 50 on the rate side for a quarterly-resetting FRN.

---

## 6. CDS mechanics and CS01

### 6.1 Structure

The protection buyer pays a **standardised running coupon** (100bp for IG, 500bp for HY in the main markets), with an **upfront payment** reconciling that fixed coupon to the market's par spread. On a credit event, settlement is by auction, with the seller paying `(1 − Recovery) × Notional`.

### 6.2 Pricing identity

```
   PV_protection_leg   =   PV_premium_leg          at the par spread
```

Expanding, with survival probabilities `Q(t)` and recovery *R*:

```
                        T
   PV_prot   =  (1−R) · ∫  DF(t) · ( −dQ(t) )
                        0

   PV_prem   =  s · Σ  τᵢ · DF(tᵢ) · Q(tᵢ)        (+ accrual on default)
                    i
```

Setting them equal and solving gives the **credit triangle** approximation, valid for flat curves and small spreads:

```
   s   ≈   λ · (1 − R)                    where λ is the hazard rate
```

**This approximation carries a warning.** It implies that a spread and a recovery assumption jointly determine an implied default probability — which means **you cannot infer PD from spread without assuming recovery**, and the market convention (typically 40% for senior unsecured corporates) is an assumption, not an observation.

### 6.3 CS01 vs JTD — the critical pairing

| | CS01 | JTD |
|---|---|---|
| Measures | Response to a **1bp** spread move | Loss on **immediate default** |
| Nature | Derivative (continuous) | Discrete event outcome |
| Obtained by | Bumping | Direct calculation — **cannot** be bumped into existence |
| Scales with | Spread duration | `(1 − R) × Notional` |
| Largest for | Long-dated, wide-spread names | **High-quality, long-dated, tight-spread names** |

> **The two are largest in opposite places.** Selling 5-year protection on a AAA sovereign generates tiny CS01 and enormous JTD. A book optimised to a CS01 limit can accumulate catastrophic default exposure while showing minimal spread risk. This is precisely why Basel capitalises **DRC separately** from CSR — see [19](19_Default_Risk_and_DRC.md).

---

## 7. Credit basis risks

| Basis | The two legs | Why it moves |
|---|---|---|
| **CDS-bond basis** | Cash bond spread vs CDS spread, same issuer/tenor | Funding cost, repo, deliverability, counterparty risk, balance-sheet cost |
| **Index skew** | Index spread vs weighted constituents | Liquidity premium in the index; roll dynamics |
| **Curve basis** | Front vs back of the credit curve | Term structure of default risk; jump-to-default demand |
| **Quanto basis** | Same name, protection in different currencies | FX-credit correlation, redenomination risk |
| **Senior/sub basis** | Different seniorities, same issuer | Implied recovery differential |

**The 2008 lesson.** The CDS-bond basis, historically small and mean-reverting, went to several hundred basis points negative in 2008–09 as balance sheet became scarce and cash bonds could not be financed. Positions constructed as "riskless" basis arbitrage — long bond, long protection — sustained severe mark-to-market losses and, critically, **margin calls** that forced liquidation at the worst point. A basis position is not riskless; it is a leveraged bet on a spread that has historically been small, which is a different thing entirely.

---

## 8. Regulatory treatment — FRTB CSR

### 8.1 The three CSR risk classes

`MAR21` splits credit spread risk into three of the seven SBM classes:

1. **CSR non-securitisations** — corporate and sovereign bonds, CDS, credit options
2. **CSR securitisations (CTP)** — the correlation trading portfolio
3. **CSR securitisations (non-CTP)** — everything else securitised

### 8.2 Risk factors (`MAR21.9`)

- **Delta:** issuer credit spread curves (bond *and* CDS) at tenors **0.5, 1, 3, 5, 10 years**
- **Vega:** implied volatilities of options referencing credit names, along one dimension — option maturity, at the same five tenors
- **Curvature:** the issuer's spread curve as a single object — **the bond-inferred and CDS-inferred curves of the same issuer count as one curve**, and all tenors are shifted in parallel

### 8.3 Buckets (`MAR21.51`, Table 3)

Buckets are set along **two dimensions — credit quality × sector**:

| Bucket | Credit quality | Sector |
|---|---|---|
| 1 | IG | Sovereigns, central banks, multilateral development banks |
| 2 | IG | Local government, government-backed non-financials, education, public administration |
| 3 | IG | Financials including government-backed financials |
| 4 | IG | Basic materials, energy, industrials, agriculture, manufacturing, mining and quarrying |
| 5 | IG | Consumer goods and services, transportation and storage, administrative and support services |
| 6 | IG | Technology, telecommunications |
| 7 | IG | Health care, utilities, professional and technical activities |
| 8 | — | Covered bonds |
| 9–15 | HY & non-rated | Same sector ordering as buckets 1–7 |
| 16 | — | Other sector |
| 17 | — | IG indices |
| 18 | — | HY indices |

An issuer that cannot be assigned to a sector **must** go to bucket 16 (`MAR21.52`), which receives punitive treatment (see §8.5).

### 8.4 Risk weights (`MAR21.53`, Table 4)

Risk weights are **the same for all five tenors within a bucket**:

| Bucket | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|
| **RW** | 0.5% | 1.0% | 5.0% | 3.0% | 3.0% | 2.0% | 1.5% | 2.5% | 2.0% |

| Bucket | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 |
|---|---|---|---|---|---|---|---|---|---|
| **RW** | 4.0% | 12.0% | 7.0% | 8.5% | 5.5% | 5.0% | 12.0% | 1.5% | 5.0% |

Footnote to Table 4: for **covered bonds rated AA− or higher**, the applicable risk weight may at the bank's discretion be **1.5%** rather than 2.5%.

Two observations worth internalising:
- **Bucket 3 (IG financials) at 5.0% is weighted higher than bucket 4–7 IG corporates.** This is deliberate: financial-sector spread risk is treated as more severe, reflecting crisis experience.
- **Bucket 16 (other sector) at 12.0% equals the highest HY bucket.** Failing to classify an issuer is charged as though it were the worst thing it could be.

### 8.5 Correlations within a bucket (`MAR21.54`–`MAR21.56`)

For **buckets 1–15**, the correlation between two weighted sensitivities is the product of three factors:

```
   ρ_kl   =   ρ(name)  ×  ρ(tenor)  ×  ρ(basis)
```

| Factor | Value if same | Value if different |
|---|---|---|
| `ρ(name)` | 1 | **35%** |
| `ρ(tenor)` | 1 | **65%** |
| `ρ(basis)` — same curve (bond vs CDS) | 1 | **99.90%** |

**Worked example from the standard's own footnote 18:** a sensitivity to the 5-year Apple *bond* curve and a sensitivity to the 10-year Google *CDS* curve:

```
   ρ  =  0.35 × 0.65 × 0.9990  =  22.73%
```

For **buckets 17 and 18 (indices)**, `ρ(name)` is **80%** rather than 35% — index constituents are treated as far more correlated with one another than two arbitrary single names.

For **bucket 16 (other sector)** the correlations do not apply at all. Delta and vega aggregate as the **simple sum of absolute values** of the net weighted sensitivities:

```
   K_b  =  Σ  | WS_k |
```

**No offsetting whatsoever, in either direction.** A long and a short in bucket 16 add rather than net. This is the framework's strongest available penalty short of exclusion, and it is a powerful incentive to classify issuers correctly.

### 8.6 Correlations across buckets (`MAR21.57`)

```
   γ_bc   =   γ(rating)  ×  γ(sector)
```

- `γ(rating)` = **50%** where two buckets in 1–15 have different rating categories (IG vs HY/NR); 1 otherwise.
- `γ(sector)` = 1 if the same sector; otherwise the value from Table 5 of the standard (e.g. 75% between buckets 1/9 and 2/10; **0%** between any of buckets 1–15 and bucket 16; 45% between buckets 1/9 and the index buckets 17 and 18).

### 8.7 The three correlation scenarios

As with every SBM risk class, all of the above is computed **three times** under `MAR21.6`:

| Scenario | Treatment of ρ and γ |
|---|---|
| **Medium** | As specified above |
| **High** | Uniformly × **1.25**, capped at 100% |
| **Low** | `max(2 × ρ − 100%, 0.75 × ρ)` |

and the capital requirement is the **largest of the three** (`MAR21.7`).

---

## 9. Stress scenarios for credit

| Scenario | Character | Typical calibration source |
|---|---|---|
| **2008 GFC** | Broad, severe, correlated widening; financials worst | Observed spread moves, Sep 2008 – Mar 2009 |
| **2011 euro sovereign** | Sovereign-led, peripheral concentration, redenomination risk | Observed 2011–12 |
| **March 2020** | Very fast, all sectors, then policy-reversed | Observed Feb–Apr 2020 |
| **Idiosyncratic gap** | One name gaps several hundred bp on news | Historical single-name events |
| **Sector shock** | One industry widens; others unaffected | Historical sector episodes |
| **Rating migration** | Mass downgrade across a bucket, incl. IG→HY "fallen angel" | Rating agency transition matrices |
| **Basis dislocation** | CDS-bond basis to a historical extreme | 2008–09 observed basis |

> Scenario severities must be sourced from **observed history**, not invented. See [13](13_Stress_Testing.md) for calibration methodology and the rule against fabricated shock magnitudes.

---

## 10. Pseudocode

### 10.1 CS01

```
FUNCTION cs01(position, rf_curve, spread_curve, bump_bp = 1.0):
    up   = price(position, rf_curve, shift(spread_curve, +bump_bp))
    down = price(position, rf_curve, shift(spread_curve, -bump_bp))
    RETURN (down - up) / (2 * bump_bp)      # positive = long credit
```

### 10.2 Bucketed CS01

```
FUNCTION bucketed_cs01(position, rf_curve, spread_curve,
                       tenors = [0.5, 1, 3, 5, 10]):
    ladder = {}
    FOR t IN tenors:
        up   = price(position, rf_curve, tent_bump(spread_curve, t, +1bp))
        down = price(position, rf_curve, tent_bump(spread_curve, t, -1bp))
        ladder[t] = (down - up) / 2
    ASSERT abs(sum(ladder.values()) - cs01(...)) < tolerance
    RETURN ladder
```

### 10.3 Z-spread solve

```
FUNCTION z_spread(position, market_price, zero_curve):
    f = LAMBDA s: sum( CF_i * exp(-(z(t_i) + s) * t_i) for i ) - market_price
    RETURN brent_solve(f, lo = -0.05, hi = 0.50, tol = 1e-10)
```

### 10.4 SBM CSR delta capital (single bucket)

```
FUNCTION csr_bucket_capital(sensitivities, bucket, scenario):
    WS = [ s.value * risk_weight(bucket) for s in sensitivities ]

    IF bucket == 16:
        RETURN sum(abs(ws) for ws in WS)          # no offsetting at all

    K_sq = sum(ws*ws for ws in WS)
    FOR each pair (k, l), k != l:
        rho = rho_name(k,l) * rho_tenor(k,l) * rho_basis(k,l)
        rho = apply_scenario(rho, scenario)        # medium / high / low
        K_sq += 2 * rho * WS[k] * WS[l]

    RETURN sqrt(max(K_sq, 0))
```

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Analytic vs bumped CS01 | Agree within tolerance |
| 2 | Rate/spread separation | Bumping the spread curve leaves the risk-free curve untouched, and vice versa |
| 3 | FRN signature | Near-zero DV01, full CS01 |
| 4 | Bucketed completeness | `Σ` bucketed CS01 ≈ parallel CS01 |
| 5 | Z-spread reprices | Applying the solved Z-spread reproduces the market price |
| 6 | OAS ≤ Z-spread | For a callable (issuer holds the option) |
| 7 | CDS reprices | Upfront reconciles to the ISDA standard model at the quoted par spread |
| 8 | Credit triangle | `s ≈ λ(1−R)` to expected accuracy on a flat curve |
| 9 | JTD computed independently | Never derived from CS01 |
| 10 | Bucket assignment | Every issuer mapped; **bucket 16 population reviewed and challenged** |
| 11 | Correlation scenarios | All three run; capital is the maximum |
| 12 | Recovery assumption | Documented, consistent between pricing and DRC |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Blended rate+spread "DV01" | Cannot hedge either risk |
| Applying rate maturity to FRN spread duration (or vice versa) | Order-of-magnitude error |
| Comparing callables on Z-spread | Systematically buys the most sold optionality |
| Deriving JTD from CS01 | Default exposure unmeasured |
| Proxying an issuer to a sector curve without flagging it | Idiosyncratic risk invisible; likely an NMRF issue too |
| Letting unclassified issuers accumulate in bucket 16 | 12% risk weight and zero offsetting — very expensive |
| Netting bond and CDS as one curve for *delta* | Curvature treats them as one curve (`MAR21.9(3)`); delta does **not** — `ρ(basis)` = 99.90%, not 100% |
| Ignoring recovery assumption consistency | Pricing and DRC disagree on the same position |

---

## 13. Limitations

- **Spread is not default probability.** Extracting PD from spread requires a recovery assumption and a risk-premium assumption; neither is observable.
- **Proxy mapping dominates.** Most issuers have no liquid CDS. The spread history used in VaR is usually a sector-rating proxy, which by construction contains no idiosyncratic risk.
- **Spread distributions are strongly non-normal** — heavily skewed, fat-tailed, and with volatility that clusters. Parametric approaches based on normality understate credit tail risk substantially.
- **Liquidity and credit are entangled** in observed spreads and cannot be cleanly separated.

---

## 14. Related Concepts

- [04 — Interest Rate Risk](04_Interest_Rate_Risk.md) · [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)
- [22 — Counterparty, CVA and SIMM](22_Counterparty_CVA_and_SIMM.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.9` risk factors; `MAR21.51`–`MAR21.57` buckets, weights, correlations; `MAR22` DRC |
| ISDA | ISDA CDS Standard Model | ongoing | https://www.isda.org/ | CDS pricing and upfront conventions |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR21/MAR22 text |

*Accessed 25 August 2026.*
