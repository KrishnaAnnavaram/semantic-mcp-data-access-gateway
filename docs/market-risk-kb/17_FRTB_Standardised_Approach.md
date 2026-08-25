# 17 — FRTB Standardised Approach

**Level:** 10 · **Prerequisites:** [16](16_FRTB_Overview.md) · **Feeds:** [19](19_Default_Risk_and_DRC.md), [30](30_Worked_Examples.md)

```
   SA capital  =  SBM  +  DRC  +  RRAO           (MAR20.4 — a SIMPLE SUM)
   RWA         =  SA capital × 12.5              (MAR20.1)
```

This document covers the **SBM** and the **RRAO** in full. The **DRC** has its own document, [19](19_Default_Risk_and_DRC.md).

---

## 1. The sensitivities-based method in outline

```
   1.  Compute sensitivities to the prescribed regulatory risk factors
                         │
   2.  NET sensitivities to the SAME risk factor across all instruments
                         │
   3.  Assign each net sensitivity to a BUCKET
                         │
   4.  Weight:   WS_k  =  s_k × RW_k
                         │
   5.  Aggregate WITHIN each bucket, using ρ_kl          →  K_b
                         │
   6.  Aggregate ACROSS buckets, using γ_bc              →  risk-class charge
                         │
   7.  Repeat 5–6 for DELTA, VEGA and CURVATURE, for each of 7 risk classes
                         │
   8.  Repeat ALL of the above under THREE correlation scenarios
                         │
   9.  Sum delta + vega + curvature across all risk classes, per scenario
                         │
  10.  SBM capital  =  the LARGEST of the three scenario totals   (MAR21.7)
```

**Step 2 is genuine and generous.** `MAR21.4(2)`: sensitivities to the same risk factor from instruments of opposite direction offset fully, *"irrespective of the instrument from which they derive."* Basel's own example: two interest rate swaps on three-month Euribor with the same fixed rate and notional but opposite direction produce **zero** GIRR.

---

## 2. The seven risk classes

`MAR21.39`–`MAR21.89` define seven risk classes, each charged for delta, vega and curvature:

| # | Risk class | Bucketed by |
|---|---|---|
| 1 | **GIRR** — general interest rate risk | Currency |
| 2 | **CSR non-securitisations** | Credit quality × sector (18 buckets) |
| 3 | **CSR securitisations (CTP)** | Index/sector |
| 4 | **CSR securitisations (non-CTP)** | Sector/tranche (25 buckets) |
| 5 | **Equity** | Market cap × economy × sector (13 buckets) |
| 6 | **Commodity** | Commodity type (11 buckets) |
| 7 | **FX** | Currency pair |

---

## 3. The aggregation formulas

### 3.1 Within a bucket — delta and vega (`MAR21.4(4)`)

```
   K_b  =  √  max( 0 ,   Σ WS_k²   +   Σ  Σ  ρ_kl · WS_k · WS_l  )
                          k          k  l≠k
```

**The quantity inside the square root is floored at zero.** With strongly offsetting positions and low correlations the quadratic form can go negative; the floor prevents an imaginary capital charge.

### 3.2 Across buckets — delta and vega (`MAR21.4(5)`)

```
   Risk class charge  =  √ (  Σ K_b²  +  Σ  Σ  γ_bc · S_b · S_c  )
                              b         b  c≠b

   where   S_b  =  Σ WS_k    for all risk factors in bucket b
                    k
```

**The fallback rule (`MAR21.4(5)(b)`) is frequently missed.** If those `S_b` values produce a **negative** overall sum under the square root, the bank must recalculate using:

```
   S_b  =  max[ min( Σ WS_k , K_b ) , −K_b ]
```

— that is, `S_b` **clamped to the interval [−K_b, +K_b]**. This is not optional and not a numerical convenience; it is a specified alternative that guarantees a real answer.

### 3.3 Curvature (`MAR21.5`)

Curvature is **not** an analytical second derivative. It is a prescribed up/down revaluation measuring the loss **beyond what delta already charged**:

```
   CVR_k⁺  =  − Σ [ V_i(x_k^(RW+)) − V_i(x_k) − RW_k^curv · s_ik ]
                i

   CVR_k⁻  =  − Σ [ V_i(x_k^(RW−)) − V_i(x_k) + RW_k^curv · s_ik ]
                i
```

| Symbol | Meaning (`MAR21.5(2)`) |
|---|---|
| `V_i(x_k)` | Price of instrument *i* at the current level of risk factor *k* |
| `V_i(x_k^(RW±))` | Price after *k* is shocked up / down by the curvature risk weight |
| `RW_k^curv` | Curvature risk weight for factor *k* |
| `s_ik` | **FX and equity:** the delta sensitivity of instrument *i*. **GIRR, CSR and commodity:** the **sum of delta sensitivities across all tenors** of the relevant curve |

**The `RW_k · s_ik` term removes the linear component already charged under delta.** Omitting it double-counts.

For GIRR, `MAR21.5(1)(a)`: **all tenors of all risk-free curves within a given currency** are shifted together (three-month Euribor, six-month Euribor, one-year Euribor, and so on for the euro).

**Curvature aggregation (`MAR21.5(3)`–`(4)`):**

```
   K_b⁺  =  √ max( 0,  Σ max(CVR_k⁺,0)² + Σ Σ ρ_kl·CVR_k⁺·CVR_l⁺·ψ(CVR_k⁺,CVR_l⁺) )
   K_b⁻  =  √ max( 0,  Σ max(CVR_k⁻,0)² + Σ Σ ρ_kl·CVR_k⁻·CVR_l⁻·ψ(CVR_k⁻,CVR_l⁻) )

   K_b   =  max( K_b⁺ , K_b⁻ )

   Curvature charge  =  √ max( 0,  Σ S_b² + Σ Σ γ_bc·S_b·S_c·ψ(S_b,S_c) )
```

where **ψ(x,y) = 0 if x and y both have negative signs, and 1 otherwise.**

Two subtleties in `MAR21.5(3)(a)`:

1. **The upward/downward scenario is selected per bucket, and the selection is not necessarily the same across the high, medium and low correlation scenarios.**
2. Where `K_b⁺ = K_b⁻` exactly, the upward scenario is deemed selected if `CVR_b⁺ > CVR_b⁻`; otherwise the downward scenario.

---

## 4. The three correlation scenarios (`MAR21.6`)

Everything above is computed **three times**:

| Scenario | ρ and γ treatment |
|---|---|
| **Medium** | As specified in `MAR21.39`–`MAR21.101` |
| **High** | Uniformly **× 1.25**, with ρ and γ **capped at 100%** |
| **Low** | Replaced by `max(2 × ρ − 100%, 75% × ρ)` and `max(2 × γ − 100%, 75% × γ)` |

`MAR21.7`: for each scenario, sum the separately calculated delta, vega and curvature requirements across all risk classes; **the SBM capital requirement is the largest of the three scenario totals.**

> **A common and costly misconception: "high correlation is the conservative scenario."** It is not, in general. For a **directional** book, high correlation is worst — everything moves together. For a **hedged** book, **low** correlation is worst, because it strips away the offset the hedge was supposed to provide. §6.4 below demonstrates this numerically. This is precisely why all three must be run.

`MAR21.7(2)(b)` adds a detail for desk-level SA calculations: capital requirements under each correlation scenario are compared **at each trading desk level**, and the maximum for each desk is taken.

---

## 5. GIRR — the reference risk class

### 5.1 Risk factors (`MAR21.8`)

- **Delta:** risk-free yield curves per currency at **ten vertices — 0.25, 0.5, 1, 2, 3, 5, 10, 15, 20 and 30 years** — plus a **flat inflation curve** and **cross-currency basis curves**
- **Vega:** implied volatilities of options on rates, by option maturity and underlying tenor
- **Curvature:** all tenors of all risk-free curves in a currency, shifted in parallel

`MAR21.41`: **each currency is a separate bucket.**

### 5.2 Delta risk weights (`MAR21.42`, Table 1)

| Vertex | 0.25y | 0.5y | 1y | 2y | 3y | 5y | 10y | 15y | 20y | 30y |
|---|---|---|---|---|---|---|---|---|---|---|
| **RW** | 1.7% | 1.7% | 1.6% | 1.3% | 1.2% | 1.1% | 1.1% | 1.1% | 1.1% | 1.1% |

`MAR21.43`: inflation and cross-currency basis risk factors each carry **1.6%**.

`MAR21.44`: for **EUR, USD, GBP, AUD, JPY, SEK, CAD** and the bank's own reporting currency, these weights may at the bank's discretion be divided by **√2**.

### 5.3 Correlations

| Relationship | ρ | Source |
|---|---|---|
| Same tenor, **different curves**, same currency | **99.90%** | `MAR21.45` |
| **Different tenor**, same curve | `max( e^(−θ·|T_k−T_l|/min(T_k,T_l)) , 40% )`, **θ = 3%** | `MAR21.46` |
| Different tenor **and** different curve | The above **× 99.90%** | `MAR21.47` |
| Inflation ↔ any yield curve tenor | **40%** | `MAR21.49` |
| Cross-currency basis ↔ yield curve, inflation, or another XCCY basis | **0%** | `MAR21.50` |
| **Across buckets** (currencies), γ | **50%** | `MAR21.50` |

**Worked check of the correlation formula**, reproducing the standard's own footnote 13 — the 1-year and 5-year tenors of the same curve:

```
   ρ  =  max[ e^(−0.03 × |1−5| / min(1,5)) , 0.40 ]
      =  max[ e^(−0.12) , 0.40 ]  =  max[ 0.8869 , 0.40 ]  =  88.69%   ✓
```

And footnote 14, the 1-year Eonia against the 5-year three-month Euribor curve: `88.69% × 0.999 = 88.60%`. ✓

---

## 6. Worked example — GIRR delta, in full

### 6.1 The book

A USD swap desk. All positions in one currency, so **one GIRR bucket**.

| Vertex | DV01 ($/bp) | Position |
|---|---|---|
| 2y | **+40,000** | long duration |
| 5y | **+85,000** | long duration |
| 10y | **−30,000** | short duration |

### 6.2 Weighted sensitivities

`MAR21.16` defines the GIRR delta sensitivity as the value change for a 0.0001 move, divided by 0.0001 — i.e. a sensitivity *per unit* of rate. Equivalently and more intuitively for a practitioner, **`WS_k = DV01_k × RW_k` with the risk weight expressed in basis points**:

| Vertex | DV01 | RW | RW (bp) | **WS_k** |
|---|---|---|---|---|
| 2y | +40,000 | 1.3% | 130 | **+5,200,000** |
| 5y | +85,000 | 1.1% | 110 | **+9,350,000** |
| 10y | −30,000 | 1.1% | 110 | **−3,300,000** |
| | | | **S_b = ΣWS** | **+11,250,000** |

> **A note on sign.** Basel's convention is `∂V/∂r`, which is *negative* for a long fixed-rate position. Using the practitioner's DV01 sign (positive = long) flips every sensitivity in the bucket. **The capital charge is unchanged**, because both the within-bucket and across-bucket aggregations are quadratic forms that are invariant under a global sign flip. What must never happen is a *mixture* of conventions within one calculation.

### 6.3 Correlations

Using `ρ = max(e^(−0.03·|T_k−T_l|/min(T_k,T_l)), 0.40)`:

| Pair | Calculation | ρ |
|---|---|---|
| 2y–5y | `max(e^(−0.03×3/2), 0.40)` | **0.955997** |
| 2y–10y | `max(e^(−0.03×8/2), 0.40)` | **0.886920** |
| 5y–10y | `max(e^(−0.03×5/5), 0.40)` | **0.970446** |

### 6.4 The three scenarios

```
   K_b  =  √ ( Σ WS_k²  +  Σ Σ 2·ρ_kl·WS_k·WS_l )
```

**Medium correlations** — ρ as above:

```
   Σ WS²      =  5,200,000² + 9,350,000² + (−3,300,000)²   =  1.253530 × 10¹⁴
   cross      =  2(0.955997)(5.2e6)(9.35e6)
               + 2(0.886920)(5.2e6)(−3.3e6)
               + 2(0.970446)(9.35e6)(−3.3e6)               =  2.6316 × 10¹²
   K_b²       =  1.279846 × 10¹⁴
   K_b        =  $11,313,195
```

**High correlations** — each ρ × 1.25, capped at 100%. All three exceed 1.0 and are capped, so every ρ = 1:

```
   K_b  =  |Σ WS_k|  =  $11,250,000
```

**Low correlations** — `ρ_low = max(2ρ − 1, 0.75ρ)`:

| Pair | `2ρ − 1` | `0.75ρ` | **ρ_low** |
|---|---|---|---|
| 2y–5y | 0.911994 | 0.716998 | **0.911994** |
| 2y–10y | 0.773840 | 0.665190 | **0.773840** |
| 5y–10y | 0.940892 | 0.727835 | **0.940892** |

```
   K_b  =  $11,376,040
```

### 6.5 The result

| Scenario | K_b |
|---|---|
| Medium | $11,313,195 |
| High | $11,250,000 |
| **Low** | **$11,376,040 ← the maximum** |

**GIRR delta capital = $11,376,040**, from the **low** correlation scenario.

> **This is the demonstration promised in §4.** The book contains a short 10-year position hedging two long positions. Under *high* correlation that hedge works perfectly and produces the **lowest** charge. Under *low* correlation the hedge is least effective and the charge is **highest**. A bank that computed only the "conservative-sounding" high-correlation scenario would have understated this desk's capital by $126,040 — and for a genuinely hedge-heavy book the gap is far larger.

---

## 7. The other risk classes — parameters

### 7.1 CSR non-securitisations

| Item | Specification | Source |
|---|---|---|
| Delta tenors | 0.5, 1, 3, 5, 10 years | `MAR21.9(1)` |
| Curvature | Bond and CDS curves of the same issuer count as **one** curve; all tenors shifted in parallel | `MAR21.9(3)` |
| Buckets | 18 — credit quality × sector | `MAR21.51` |
| Risk weights | 0.5%–12.0% by bucket (same for all tenors) | `MAR21.53` |
| Intra-bucket ρ | `ρ(name) × ρ(tenor) × ρ(basis)` = 35% × 65% × 99.90% for different name/tenor/curve (buckets 1–15); `ρ(name)` = 80% for index buckets 17–18 | `MAR21.54`–`MAR21.55` |
| Bucket 16 ("other sector") | **Simple sum of absolute values** — no offsetting at all | `MAR21.56` |
| Cross-bucket γ | `γ(rating) × γ(sector)`; γ(rating) = 50% across IG/HY | `MAR21.57` |

Full bucket and weight tables: [05 §8](05_Credit_Spread_Risk.md).

### 7.2 CSR securitisations (non-CTP)

| Item | Specification | Source |
|---|---|---|
| Cross-bucket γ, buckets 1–24 | **0%** | `MAR21.70` |
| Bucket 25 ("other sector") vs buckets 1–24 | γ = **1**; bucket-level charges **simply summed**, with **no diversification or hedging effect recognised with any bucket** | `MAR21.71` |

> `MAR21.70`–`MAR21.71` together are among the harshest provisions in the SBM: zero offset between securitisation buckets, and the residual bucket added on top with no recognition at all.

### 7.3 Equity

| Item | Specification | Source |
|---|---|---|
| Delta risk factors | Equity **spot prices** and **equity repo rates** | `MAR21` |
| Vega / curvature carve-out | **No vega and no curvature charge on equity repo rates** | `MAR21` |
| Buckets | 13 — market cap × economy × sector | `MAR21.72` |
| Large cap threshold | **≥ USD 2 billion**, per single listed legal entity, across all markets globally | `MAR21.74` |
| Advanced economies | Canada, US, Mexico, euro area, non-euro western Europe (UK, Norway, Sweden, Denmark, Switzerland), Japan, Oceania (Australia, NZ), Singapore, Hong Kong SAR | `MAR21.75` |
| Spot risk weights | 15%–70% | `MAR21.77` |
| Repo risk weights | **Spot RW ÷ 100** in every bucket | `MAR21.77` |
| Same-issuer spot↔repo ρ | **99.90%** | `MAR21.78` |

Full tables: [07 §8](07_Equity_Risk.md).

### 7.4 Commodity

| Item | Specification | Source |
|---|---|---|
| Buckets | 11 | `MAR21.82` |
| Risk weights | 30%, 35%, 60%, **80% (freight — the highest)**, 40%, 45%, **20% (precious metals — the lowest)**, 35%, 25%, 35%, 50% | `MAR21.82` |
| Intra-bucket ρ | `ρ(commodity) × ρ(tenor) × ρ(basis)` = Table 12 value × **99.00%** × **99.90%** | `MAR21.83` |
| Electricity granularity | Each delivery time interval is a **distinct commodity** (peak vs off-peak) | `MAR21.84` |

Full tables: [08 §6](08_Commodity_Risk.md).

### 7.5 FX

| Item | Specification | Source |
|---|---|---|
| Risk factors | All exchange rates between the currency of denomination and the **reporting currency** | `MAR21.14` |
| Risk weight | **A unique relative risk weight of 15%** on all FX sensitivities | `MAR21.87` |
| √2 discount | For a specified list of pairs and their first-order crosses | `MAR21.88` |
| Cross-bucket γ | **60%**, uniformly | `MAR21.89` |

Full detail: [06 §8](06_FX_Risk.md).

---

## 8. Vega across all risk classes (`MAR21.90`–`MAR21.95`)

`MAR21.91`: **the same bucket definitions are used for vega as for delta**, and the corresponding delta correlation parameters are reused for vega aggregation (e.g. γ = 50% across GIRR buckets).

`MAR21.92`, Table 13 — the regulatory liquidity horizon per risk class, which drives the vega risk weight (with **σ set at 55%** in the weight formula):

| Risk class | LH |
|---|---|
| GIRR | **60** |
| CSR non-securitisations | **120** |
| CSR securitisations (CTP) | **120** |
| CSR securitisations (non-CTP) | **120** |
| Equity (large cap and indices) | **20** |
| Equity (small cap and other sector) | **60** |
| Commodity | **120** |
| FX | **40** |

`MAR21.25`: option-level vega sensitivity to a given risk factor is measured by multiplying vega by the implied volatility.

---

## 9. The Residual Risk Add-On (`MAR23`)

### 9.1 What it charges

```
   RRAO  =  Σ ( gross notional × risk weight )
```

| Instrument category | Risk weight | Source |
|---|---|---|
| **Exotic underlying** | **1.0%** | `MAR23.8(2)(a)` |
| **Other residual risks** | **0.1%** | `MAR23.8(2)(b)` |

### 9.2 What is in scope (`MAR23.5`)

A non-exhaustive list of "other residual risk" types:

| Risk type | Basel's definition | Named instruments |
|---|---|---|
| **Gap risk** | *"risk of a significant change in vega parameters in options due to small movements in the underlying, which results in hedge slippage"* | **All path-dependent options** — barriers, Asians — and **all digital options** |
| **Correlation risk** | *"risk of a change in a correlation parameter necessary for determining the value of an instrument with multiple underlyings"* | Basket, best-of, spread, basis, **Bermudan** and **quanto** options |
| **Behavioural risk** | *"risk of a change in exercise/prepayment outcomes"* driven by non-financial motives | Fixed-rate mortgage products where retail clients decide. **A callable bond only has behavioural risk if the right to call lies with a retail client** |

### 9.3 What is explicitly *out* of scope (`MAR23.6`)

The following do **not**, by themselves, bring an instrument into the RRAO:

1. **Cheapest-to-deliver optionality**
2. **Smile risk** — a change in implied volatility relative to other options on the same underlying and maturity but different moneyness
3. **Correlation risk arising from multi-underlying European or American plain vanilla options**

### 9.4 Exclusions (`MAR23.7`)

- **Back-to-back transactions** that exactly match a third-party transaction — the instruments used in *both* transactions are excluded
- **Any instrument that is listed and/or eligible for central clearing**

### 9.5 The scope constraint (`MAR23.8(1)`)

> The scope of instruments subject to the RRAO **must not** increase or decrease the scope of risk factors subject to the delta, vega, curvature or DRC treatments.

The RRAO is **additive on top**, not a substitute. An exotic option is charged under SBM delta/vega/curvature **and** under the RRAO.

### 9.6 Worked example

| Instrument | Gross notional | Category | RW | RRAO |
|---|---|---|---|---|
| Barrier options (cleared) | $400m | — | **excluded** (`MAR23.7`) | $0 |
| Barrier options (OTC, uncleared) | $250m | Gap risk | 0.1% | $250,000 |
| Digital options (OTC) | $120m | Gap risk | 0.1% | $120,000 |
| Quanto options | $80m | Correlation risk | 0.1% | $80,000 |
| Longevity-linked notes | $60m | **Exotic underlying** | **1.0%** | **$600,000** |
| Back-to-back basket options | $200m | Exactly matched | **excluded** | $0 |
| | | | **RRAO** | **$1,050,000** |

**$60m of exotic-underlying notional generates more RRAO than $450m of gap-risk notional.** The 10× weight differential is the framework's judgement that an exotic *underlying* — one with no market-standard risk representation at all — is a categorically different problem from a path-dependency in a standard underlying.

---

## 10. Pseudocode — the full SBM

```
FUNCTION sbm_capital(portfolio):
    scenario_totals = {}

    FOR scenario IN ["medium", "high", "low"]:
        total = 0
        FOR risk_class IN SEVEN_RISK_CLASSES:
            total += delta_charge(portfolio, risk_class, scenario)
            total += vega_charge(portfolio, risk_class, scenario)
            total += curvature_charge(portfolio, risk_class, scenario)
        scenario_totals[scenario] = total

    RETURN max(scenario_totals.values())          # MAR21.7(2)


FUNCTION delta_charge(portfolio, risk_class, scenario):
    K, S = {}, {}
    FOR b IN buckets(risk_class):
        # MAR21.4(2): NET first, across all instruments
        net = net_sensitivities_by_factor(portfolio, risk_class, b)
        WS  = { k: net[k] * risk_weight(risk_class, b, k) for k in net }

        IF is_no_offset_bucket(risk_class, b):     # e.g. CSR bucket 16
            K[b] = sum(abs(w) for w in WS.values())
        ELSE:
            q = sum(w*w for w in WS.values())
            FOR each pair (k, l), k != l:
                rho = adjust(correlation(risk_class, b, k, l), scenario)
                q += rho * WS[k] * WS[l]           # each unordered pair twice
            K[b] = sqrt(max(q, 0))                 # MAR21.4(4): floored at zero

        S[b] = sum(WS.values())

    # across buckets — MAR21.4(5)
    q = sum(K[b]**2 for b in K)
    FOR each pair (b, c), b != c:
        gamma = adjust(cross_bucket_gamma(risk_class, b, c), scenario)
        q += gamma * S[b] * S[c]

    IF q < 0:                                      # MAR21.4(5)(b) fallback
        S = { b: max(min(S[b], K[b]), -K[b]) for b in S }
        q = sum(K[b]**2 for b in K)
        FOR each pair (b, c), b != c:
            gamma = adjust(cross_bucket_gamma(risk_class, b, c), scenario)
            q += gamma * S[b] * S[c]

    RETURN sqrt(max(q, 0))


FUNCTION adjust(rho, scenario):
    IF scenario == "medium":  RETURN rho
    IF scenario == "high":    RETURN min(rho * 1.25, 1.0)          # MAR21.6(2)
    IF scenario == "low":     RETURN max(2*rho - 1.0, 0.75*rho)    # MAR21.6(3)


FUNCTION rrao(portfolio):
    charge = 0
    FOR i IN portfolio.instruments:
        IF i.is_listed OR i.is_cch_eligible:      CONTINUE   # MAR23.7
        IF i.is_exactly_matched_back_to_back:     CONTINUE   # MAR23.7
        IF i.has_exotic_underlying:               charge += i.gross_notional * 0.010
        ELIF i.bears_other_residual_risk:         charge += i.gross_notional * 0.001
    RETURN charge
```

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Netting before weighting** | Same-factor sensitivities netted across instruments (`MAR21.4(2)`) |
| 2 | **Prescribed vertices** | GIRR at the ten `MAR21.8` tenors; CSR at the five `MAR21.9` tenors |
| 3 | **Floor at zero** | Within-bucket quadratic floored (`MAR21.4(4)`) |
| 4 | **S_b fallback** | Clamping to [−K_b, +K_b] implemented (`MAR21.4(5)(b)`) |
| 5 | **All three scenarios** | Medium, high **and** low computed; maximum taken |
| 6 | **High capped** | ρ, γ capped at 100% after ×1.25 |
| 7 | **Low formula** | `max(2ρ−1, 0.75ρ)` — not `2ρ−1` alone |
| 8 | **Curvature offset** | `RW·s` subtracted; tenors summed for GIRR/CSR/commodity |
| 9 | **Curvature scenario selection** | Per bucket, re-selected under each correlation scenario |
| 10 | **ψ function** | Returns 0 **only** when both arguments are negative |
| 11 | **No-offset buckets** | CSR 16, CSR-sec 25 handled by simple sum |
| 12 | **Zero-γ securitisation** | γ = 0% across non-CTP buckets 1–24 (`MAR21.70`) |
| 13 | **Equity repo carve-outs** | No vega, no curvature on repo rates |
| 14 | **RRAO scope neutrality** | RRAO does not alter SBM/DRC risk factor scope (`MAR23.8(1)`) |
| 15 | **RRAO exclusions** | Listed/cleared and exactly-matched back-to-back excluded |
| 16 | **Sign convention** | One convention throughout; never mixed within a calculation |
| 17 | **Simple sum** | SBM + DRC + RRAO added, never diversified (`MAR20.4`) |
| 18 | **RWA factor** | × 12.5 (`MAR20.1`) |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Weighting before netting | Overstates charge; loses legitimate offsets |
| Running only the high-correlation scenario | **Understates capital for hedged books** (§6.5) |
| Omitting the `S_b` clamping fallback | NaN or a crash on strongly offsetting portfolios |
| Curvature without the `RW·s` term | Double-counts delta |
| Fixing the curvature up/down choice across scenarios | Contradicts `MAR21.5(3)(a)` |
| ψ returning 0 when only one argument is negative | Wrong curvature aggregation |
| Netting within CSR bucket 16 | Contradicts `MAR21.56` |
| Recognising offset across non-CTP securitisation buckets | γ is 0% (`MAR21.70`) |
| Summing related listed entities for the equity market-cap test | Wrong bucket, wrong weight |
| Charging vega/curvature on equity repo rates | Overstates capital |
| Applying RRAO to listed or cleared instruments | Overstates capital |
| Treating RRAO as a substitute for SBM on exotics | Understates capital |
| Diversifying SBM against DRC | Contradicts `MAR20.4` |

---

## 13. Limitations

- The SBM is **calibrated, not modelled.** `MAR21.40` notes the weights and correlations were calibrated to a stress period; they are fixed parameters, not estimates of any particular bank's risk.
- **Prescribed vertices force interpolation.** A book with material exposure between the fixed tenors must map onto them, and the mapping is itself an approximation.
- **Curvature is a two-point approximation** to a whole surface of convexity. It captures the direction of the problem, not its magnitude precisely.
- **The RRAO is deliberately crude.** A notional-based charge bears no proportionality to actual risk within its scope — Basel says as much in `MAR20.4(3)`.
- **The SA cannot recognise a genuine hedge that crosses buckets** where γ is low or zero, so economically hedged books can attract substantial capital.
- **Jurisdictional calibrations differ.** The EU is applying a multiplier and operational relief measures from 1 January 2027 for three years — see [29](29_Regulatory_Framework.md).

---

## 14. Related Concepts

- [16 — FRTB Overview](16_FRTB_Overview.md) · [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)
- [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md) · [09 — Options and Greeks](09_Options_and_Greeks.md)
- [05](05_Credit_Spread_Risk.md), [06](06_FX_Risk.md), [07](07_Equity_Risk.md), [08](08_Commodity_Risk.md) — per-class parameter tables

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR20`–`MAR23` in full |
| BCBS | *Explanatory note on the minimum capital requirements for market risk* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_note.pdf | SBM calibration rationale |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR20–MAR23 text |

*Accessed 25 August 2026.*
