# 12 — Expected Shortfall

**Level:** 7 · **Prerequisites:** [11](11_VaR.md) · **Feeds:** [18](18_FRTB_Internal_Models_Approach.md), [20](20_NMRF_and_Modellability.md)

---

## 1. Plain English

**VaR tells you where the bad days start. Expected Shortfall tells you how bad they are once you get there.**

> **Expected Shortfall is the average loss on the days when the loss exceeds VaR.**

Also called **Conditional VaR (CVaR)**, **Average VaR (AVaR)**, or **Expected Tail Loss (ETL)** — all the same quantity.

---

## 2. Banking example — why VaR alone is not enough

Two desks. Both report **99% 1-day VaR of exactly $10 million.**

| | Desk A | Desk B |
|---|---|---|
| 99% VaR | $10m | $10m |
| Losses on the 1% of days beyond VaR | $10m–$12m | $10m–$180m |
| **Expected Shortfall (97.5%)** | ~$9m | ~$55m |

**VaR says these desks are identical. They are not remotely identical.**

Desk A sells liquid, well-hedged flow. Desk B has sold deep out-of-the-money options — it makes a small premium on 99% of days and loses catastrophically on the rest. Its VaR is low precisely *because* the loss distribution has almost nothing between "small profit" and "disaster."

> **This is not a hypothetical pathology. It is a describable, repeatable trade that a VaR-based limit framework actively rewards.** Any risk measure that looks only at a threshold can be optimised against by pushing loss *past* the threshold. That single observation is the practical reason ES replaced VaR at the centre of the regulatory framework.

---

## 3. Why ES was introduced — the three arguments

### 3.1 Argument 1 — VaR ignores the tail's shape

By construction, VaR is a quantile. It is entirely insensitive to *how* the distribution behaves beyond it. Everything past the threshold is invisible.

ES integrates over that region, so it responds to tail severity.

### 3.2 Argument 2 — VaR is not sub-additive; ES is

A **coherent** risk measure (Artzner et al., 1999) must satisfy four axioms: monotonicity, translation invariance, positive homogeneity and **sub-additivity**:

```
   ρ(A + B)   ≤   ρ(A) + ρ(B)
```

Sub-additivity is the formal statement that **diversification cannot increase risk**.

**VaR violates it.** Consider two independent bonds, each with a 3% probability of defaulting and losing 100, otherwise losing 0.

- **Individually**, at 95% confidence: the loss exceeds 0 only 3% of the time, which is less than 5%. So `VaR₉₅ = 0` for each bond.
- **Combined**, the probability that *at least one* defaults is `1 − 0.97² = 5.91% > 5%`. So the 95th percentile of the combined loss is **100**.

```
   VaR₉₅(A)  +  VaR₉₅(B)   =   0  +  0   =   0
   VaR₉₅(A + B)            =   100
```

**Combining two portfolios increased measured risk from zero to 100.** That is not a paradox to be explained away — it means VaR cannot be safely used to allocate limits across a hierarchy, because sub-limits summing to a parent limit does not bound the parent's actual risk.

**ES satisfies sub-additivity for all distributions.** It is a coherent risk measure. This is the theoretical core of the regulatory change.

### 3.3 Argument 3 — statistical estimability at the tail

This argument cuts the *other* way and is why Basel lowered the confidence level when it switched measures.

| Measure | Observations used, from 250 scenarios |
|---|---|
| 99% VaR | **~2.5** — effectively 2 or 3 data points |
| 97.5% ES | **~6.25** — averaged, not selected |

Averaging six observations is more stable than picking the third-worst. **Moving from 99% VaR to 97.5% ES buys tail sensitivity *and* estimator stability at the same time** — which is the design that made the switch practical rather than merely theoretically attractive.

---

## 4. Formal definition

### 4.1 Continuous case

```
                    1        1
   ES_α   =   ───────────  ∫    VaR_u  du
                 1 − α      α
```

ES is the **average of all VaRs above level α** — which is why it is sometimes called Average VaR.

Equivalently, as a conditional expectation:

```
   ES_α   =   E[ L  |  L ≥ VaR_α ]
```

### 4.2 Discrete case (historical simulation)

```
                      1
   ES_α   =   ───────────────  ·  Σ  ( losses in the worst (1−α) fraction )
                (1−α) · N
```

### 4.3 The relationship that always holds

```
   ES_α   ≥   VaR_α           always, for any distribution
```

with equality only in the degenerate case where the tail is a single point mass.

---

## 5. Worked example — historical ES

Using the same 250-scenario set from [11 §4.5](11_VaR.md). The ten worst outcomes ($000s):

| Rank | P&L | Cumulative sum |
|---|---|---|
| 1 | −4,820 | 4,820 |
| 2 | −3,910 | 8,730 |
| 3 | −3,450 | 12,180 |
| 4 | −3,180 | 15,360 |
| 5 | −2,940 | 18,300 |
| 6 | −2,760 | **21,060** |
| 7 | −2,610 | 23,670 |
| 8 | −2,455 | |
| 9 | −2,320 | |
| 10 | −2,180 | |

### 5.1 ES at 97.5%

The tail fraction is `(1 − 0.975) × 250 = 6.25` observations.

```
   Sum of the worst 6           =  21,060
   Fractional 7th observation   =  0.25 × 2,610  =  652.5
   Total                        =  21,712.5

   ES₉₇.₅  =  21,712.5 / 6.25  =  $3,474.0k
```

### 5.2 ES at 99%

Tail fraction `(1 − 0.99) × 250 = 2.5` observations.

```
   Sum of worst 2               =  8,730
   Fractional 3rd               =  0.5 × 3,450  =  1,725
   Total                        =  10,455

   ES₉₉  =  10,455 / 2.5  =  $4,182.0k
```

### 5.3 The comparison that matters

| Measure | Value ($000s) |
|---|---|
| 99% VaR (3rd worst, conservative) | 3,450 |
| **97.5% ES** | **3,474** |
| 99% ES | 4,182 |

> **97.5% ES ($3,474k) sits almost exactly at 99% VaR ($3,450k)** for this book — within 0.7%. That correspondence is not an accident of these numbers; it is the deliberate design of the Basel calibration, as §6.3 shows analytically.

---

## 6. Parametric ES

### 6.1 Formula (normal distribution)

```
                    φ(z_α)
   ES_α  =  σ · ─────────────
                   1 − α
```

where `φ` is the standard normal **density** (not the CDF) and `z_α` is the VaR quantile.

### 6.2 The multipliers

| Confidence | `z_α` (VaR multiplier) | `φ(z_α)/(1−α)` (ES multiplier) | ES/VaR ratio |
|---|---|---|---|
| 95% | 1.644854 | **2.062712** | 1.254 |
| **97.5%** | 1.959964 | **2.337803** | 1.193 |
| 99% | 2.326348 | **2.665213** | 1.146 |

### 6.3 The Basel calibration — why 97.5%

Compare two numbers from the table above:

```
   VaR at 99%    multiplier  =  2.326348
   ES  at 97.5%  multiplier  =  2.337803
```

**They differ by 0.49%.** Under a normal distribution, **97.5% Expected Shortfall and 99% Value at Risk are essentially the same number.**

This is the design. Basel chose 97.5% ES so that, for a *normally distributed* portfolio, capital would be broadly unchanged from the old 99% VaR standard — while for a **fat-tailed** portfolio the ES measure picks up the tail severity that VaR ignored. Desk B in §2 sees its capital requirement rise dramatically; a plain, well-hedged flow desk sees very little change.

> **The switch was calibrated to be capital-neutral for well-behaved books and punitive for tail-heavy ones. That was the entire point.**

### 6.4 Worked example — our portfolio

Using [10](10_Portfolio_Risk_Mathematics.md)'s portfolio: `σ_daily = 0.72114%`, V = $100m.

```
   VaR₉₉    =  2.326348 × 0.0072114 × 100,000,000  =  $1,677,600
   ES₉₇.₅   =  2.337803 × 0.0072114 × 100,000,000  =  $1,685,900
   ES₉₉     =  2.665213 × 0.0072114 × 100,000,000  =  $1,922,000
```

The parametric ES₉₇.₅ ($1.69m) again sits fractionally above VaR₉₉ ($1.68m) — and both remain far below the historical-simulation figures of §5.3, which is the fat tail asserting itself exactly as in [11 §9.1](11_VaR.md).

### 6.5 Student-t ES

For a t-distribution with ν degrees of freedom (a common fat-tailed choice):

```
                  ν + t_ν(α)²         φ_ν( t_ν(α) )
   ES_α  =  σ ·  ─────────────  ·  ──────────────────
                    ν − 1                1 − α
```

The `(ν + t²)/(ν − 1)` factor is what makes t-ES exceed normal-ES, and it grows as ν falls (fatter tails). **The formula is undefined for ν ≤ 1** — a distribution with infinite mean has no expected shortfall, which is a genuine mathematical fact and not a numerical inconvenience.

---

## 7. Monte Carlo ES

Identical to Monte Carlo VaR ([11 §6](11_VaR.md)) up to the final step:

```
STEP 3′ — average the tail rather than selecting from it
    sorted    = sort_ascending(PnL)
    tail_size = ceil((1 - α) * K)
    ES        = -mean( sorted[0 : tail_size] )
```

**ES converges more slowly than VaR** in Monte Carlo, because it depends on the whole tail rather than one order statistic — more draws are needed for the same standard error. Importance sampling, which oversamples the tail and reweights, is the standard remedy and delivers large efficiency gains for exactly this measure.

---

## 8. FRTB Expected Shortfall

### 8.1 The core specification

| Parameter | Value | Source |
|---|---|---|
| Confidence level | **97.5th percentile, one-tailed** | `MAR33.3` |
| Frequency | **Daily**, bank-wide *and* per IMA desk | `MAR33.2` |
| Calibration | To a **period of stress** | `MAR33.5` |
| Base horizon | **10 days** | `MAR33.4(2)` |
| Liquidity horizons | 10, 20, 40, 60, 120 days | `MAR33.4(8)`, Table 1 |
| Model type | **Not prescribed** — historical, Monte Carlo or other analytical methods | `MAR33.12` |

### 8.2 The liquidity-horizon scaling formula

This is the mechanism that distinguishes FRTB's ES from a plain 10-day ES, and it is frequently mis-implemented.

`MAR33.4` requires the liquidity-adjusted ES to be built from an ES computed at a **10-day base horizon**, combined across nested subsets of risk factors:

```
                ┌                                                        ┐ ½
                │                              ⎛  LH_j − LH_{j−1}  ⎞²    │
   ES  =        │  (ES_T(P))²  +   Σ   ⎛ ES_T(P, j) · √⎜ ───────────── ⎟ ⎞²│
                │                 j≥2                   ⎝        T        ⎠  │
                └                                                        ┘
```

where:

| Symbol | Meaning (`MAR33.4`) |
|---|---|
| `T` | The base horizon, **10 days** |
| `ES_T(P)` | ES at horizon T with respect to shocks to **all** risk factors the positions are exposed to |
| `ES_T(P, j)` | ES at horizon T with respect to shocks only to the subset `Q(pᵢ, j)` |
| `Q(pᵢ, j)` | The subset of risk factors whose liquidity horizons are **at least as long as** `LH_j` |
| `LH_j` | The liquidity horizon: `LH₁ = 10`, `LH₂ = 20`, `LH₃ = 40`, `LH₄ = 60`, `LH₅ = 120` |

**Two properties of `Q` that implementations get wrong:**

1. `Q(pᵢ, j)` is a **subset of** `Q(pᵢ, j−1)` — the sets are nested and shrinking. `Q(pᵢ,4)` contains the risk factors with 60-day *and* 120-day horizons, not only the 60-day ones (the standard gives exactly this example).
2. `ES_T(P)` and each `ES_T(P, j)` must be **calculated for changes over the interval T directly, without scaling from a shorter horizon** (`MAR33.4(5)`). Overlapping observations *are* permitted for determining the time series of changes (`MAR33.4(7)`).

### 8.3 The reduced-set stress calibration

`MAR33.5` requires the ES measure to replicate what would be generated **if the relevant risk factors were experiencing a period of stress** — a joint assessment across all risk factors, capturing stressed correlations.

Because a long history is not available for every risk factor, the calibration uses an **indirect approach with a reduced set of risk factors**:

- The reduced set is subject to supervisory approval and must meet the modellability data-quality requirements of `MAR31.12`–`MAR31.24`.
- It **must explain a minimum of 75% of the variation of the full ES model** — specifically, the reduced-set ES must be at least 75% of the fully specified ES model *on average, measured over the preceding 12-week period* (`MAR33.5(2)(b)`).

The stressed period and the reduced set must both be **updated quarterly** (`MAR33.44`).

### 8.4 Constrained cross-class correlation

`MAR33.13`–`MAR33.15`: the bank calculates `IMCC(C)` at bank-wide level with **no supervisory constraints on cross-risk-class correlations**, and separately a series of **partial ES** figures for each of the five broad regulatory risk classes — interest rate, equity, foreign exchange, commodity and credit spread — holding all other factors constant. The aggregate `IMCC` is a **weighted average** of the unconstrained and the summed-partial figures (`MAR33.15`).

> **This is the framework refusing to take a bank's word for cross-asset diversification.** Empirical correlations *within* a broad risk class may be recognised; correlations *across* classes are constrained by the supervisory aggregation scheme, because those are precisely the correlations that converge in a crisis ([10 §5.2](10_Portfolio_Risk_Mathematics.md)).

### 8.5 Where ES sits in the IMA capital calculation

```
   IMA capital (non-DRC)  =  max( IMCC_{t−1} + SES_{t−1} ,
                                  m_c · IMCC_avg60  +  SES_avg60 )
```

with `m_c` fixed at **1.5** unless increased by the supervisor for a qualitative add-on and/or a backtesting add-on ranging from **0 to 0.5** (`MAR33.41`–`MAR33.42`). `SES` is the aggregate stress-scenario capital for non-modellable risk factors ([20](20_NMRF_and_Modellability.md)).

---

## 9. VaR versus Expected Shortfall — the comparison table

| | **VaR** | **Expected Shortfall** |
|---|---|---|
| Question answered | Where does the tail begin? | How bad is the tail? |
| Definition | The α-quantile of loss | The mean loss beyond that quantile |
| Sub-additive (coherent) | **No** | **Yes** |
| Sensitive to tail shape | **No** | **Yes** |
| Backtestable directly | **Yes** — count exceptions | **Harder** — not elicitable in the same simple sense |
| Estimator stability at fixed N | Poor (one order statistic) | Better (averaged) |
| Gameable by pushing loss past the threshold | **Yes** | Much less so |
| Basel role today | **Backtesting** (97.5% & 99%, `MAR32.18`) | **Capital** (97.5%, `MAR33.3`) |
| Basel role pre-FRTB | Capital (99% 10-day + Stressed VaR) | Not used |

### 9.1 The one genuine advantage VaR retains — and how FRTB resolves it

**VaR is directly backtestable.** You count the days the loss exceeded it, and compare that count to a binomial expectation. It is simple, non-parametric and hard to argue with.

ES is not backtestable in that clean way. Formally, VaR is **elicitable** (it minimises an expected scoring function) and ES is not, on its own — a technical result with a very practical consequence: there is no equally simple "count the exceptions" test for ES.

**Basel's resolution is pragmatic and worth understanding as a design pattern:**

> **Capital is set with the measure that describes risk properly (97.5% ES). Model validation is done with the measures that can actually be tested (97.5% and 99% VaR).**

`MAR32.18` requires desk-level backtesting against **one-day VaR at both the 97.5th and 99th percentiles**, calibrated to the most recent 12 months of equally-weighted data, using at least one year of current P&L observations. The ES model is validated *indirectly*, through the VaR backtest and through the P&L Attribution test. See [15](15_Backtesting.md).

---

## 10. Pseudocode

```
FUNCTION expected_shortfall_historical(pnl_scenarios, alpha):
    sorted_pnl = sort_ascending(pnl_scenarios)      # worst first
    N          = len(sorted_pnl)
    tail_exact = (1 - alpha) * N                    # may be fractional

    full       = floor(tail_exact)
    frac       = tail_exact - full

    total = sum( -sorted_pnl[0 : full] )
    IF frac > 0 AND full < N:
        total += frac * ( -sorted_pnl[full] )       # fractional observation

    RETURN total / tail_exact


FUNCTION expected_shortfall_parametric(sigma, alpha, value):
    z = normal_inverse_cdf(alpha)
    RETURN sigma * normal_pdf(z) / (1 - alpha) * value


FUNCTION frtb_liquidity_adjusted_es(positions, factors, horizons, T = 10):
    # ES over ALL risk factors, at the 10-day base horizon, computed directly
    es_all = es_97_5(positions, factors, horizon = T, scale_from_shorter = FALSE)

    total_sq = es_all ** 2
    LH = {1: 10, 2: 20, 3: 40, 4: 60, 5: 120}

    FOR j IN [2, 3, 4, 5]:
        # NESTED subset: factors whose horizon is AT LEAST LH[j]
        Q_j    = [ f for f in factors if horizons[f] >= LH[j] ]
        es_j   = es_97_5(positions, Q_j, horizon = T, scale_from_shorter = FALSE)
        weight = sqrt( (LH[j] - LH[j-1]) / T )
        total_sq += ( es_j * weight ) ** 2

    RETURN sqrt(total_sq)
```

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **ES ≥ VaR** | Always, at the same confidence level |
| 2 | **Sub-additivity** | `ES(A+B) ≤ ES(A) + ES(B)` on test portfolios |
| 3 | **Monotonicity** | ES increases with confidence level |
| 4 | **Fractional observation** | Handled correctly, not truncated (§10) |
| 5 | **Tail population** | Enough observations for a stable average; documented |
| 6 | **Normal benchmark** | Parametric ES reproduces the §6.2 multipliers |
| 7 | **97.5% ES ≈ 99% VaR** | Holds for near-normal books; large divergence flagged as a fat-tail indicator |
| 8 | **Nested subsets** | `Q(pᵢ, j) ⊆ Q(pᵢ, j−1)` verified in code |
| 9 | **No shorter-horizon scaling** | `ES_T` computed directly at T = 10 days |
| 10 | **Reduced-set 75% test** | Measured over the preceding 12-week period |
| 11 | **Quarterly updates** | Stressed period and reduced set refreshed (`MAR33.44`) |
| 12 | **Indirect validation** | VaR backtesting and PLA in place, since ES is not directly backtestable |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Truncating instead of interpolating the fractional tail observation | Systematic bias in ES |
| Averaging losses **beyond** VaR but excluding the VaR observation itself | Small, systematic understatement |
| Treating `Q(pᵢ, j)` as factors with **exactly** horizon `LH_j` | Nesting broken; ES materially wrong |
| Scaling a 1-day ES by √10 for the base horizon | Contradicts `MAR33.4(5)` |
| Using the same normal multiplier for VaR and ES | Understates ES by ~15–25% |
| Applying the t-ES formula with ν ≤ 1 | Undefined quantity returned as a number |
| Expecting to backtest ES by counting exceptions | Not directly backtestable; use the `MAR32` VaR tests |
| Reporting ES without stating the confidence level | 97.5% and 99% ES differ by ~20% |

---

## 13. Limitations

1. **ES is not elicitable in isolation**, which is why direct backtesting is hard and why FRTB validates through VaR instead.
2. **ES is more sensitive to outliers** than VaR — one extreme scenario moves the average, whereas a quantile is robust to it. That sensitivity is the intent, but it means a single bad data point has more effect and data quality matters more.
3. **The tail sample is still small.** 97.5% ES on 250 scenarios averages roughly six observations. Better than 2.5, not remotely "many."
4. **ES inherits every weakness of the underlying distribution model.** A historical ES cannot see a scenario absent from the window; a normal ES understates fat tails just as normal VaR does.
5. **ES says nothing about the worst case.** It is an average over the tail, not a maximum. Stress testing remains necessary — [13](13_Stress_Testing.md).

---

## 14. Related Concepts

- [11 — Value at Risk](11_VaR.md) · [13 — Stress Testing](13_Stress_Testing.md)
- [15 — Backtesting](15_Backtesting.md) · [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)
- [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR33.2`–`MAR33.5`, `MAR33.12`–`MAR33.15`, `MAR33.41`–`MAR33.44`; `MAR32.18` |
| Artzner, Delbaen, Eber, Heath | *Coherent Measures of Risk*, Mathematical Finance 9(3) | 1999 | — | The coherence axioms and VaR's sub-additivity failure |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR33 text |

*Accessed 25 August 2026.*
