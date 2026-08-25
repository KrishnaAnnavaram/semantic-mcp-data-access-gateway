# 10 — Portfolio Risk Mathematics

**Level:** 5 · **Prerequisites:** [04](04_Interest_Rate_Risk.md)–[09](09_Options_and_Greeks.md) · **Feeds:** [11](11_VaR.md), [12](12_Expected_Shortfall.md), [42](42_Risk_Aggregation.md)

> **The running portfolio.** Every worked example in this document uses one portfolio, so the numbers connect:
>
> | Asset | Weight *w* | Volatility σ (annual) |
> |---|---|---|
> | A — government bonds | 60% | 10% |
> | B — corporate credit | 30% | 20% |
> | C — equity | 10% | 35% |
>
> Correlations: ρ(A,B) = 0.30, ρ(A,C) = 0.10, ρ(B,C) = 0.50. Portfolio value $100m.

---

## 1. Returns — three definitions, not interchangeable

| Type | Formula | Property | Use |
|---|---|---|---|
| **Arithmetic (simple)** | `r = (P₁ − P₀)/P₀` | Aggregates **across assets** | Portfolio returns at a point in time |
| **Logarithmic (continuous)** | `r = ln(P₁/P₀)` | Aggregates **across time** | Time-series modelling, VaR scaling |
| **P&L (absolute)** | `ΔV = V₁ − V₀` | Currency amount | Risk reporting, limits, backtesting |

### 1.1 Why the distinction is load-bearing

**Arithmetic returns are additive across assets:**

```
   r_portfolio  =  Σ  wᵢ · rᵢ           ← true for arithmetic, false for log
```

**Log returns are additive across time:**

```
   r(0→T)  =  r₁ + r₂ + … + r_T        ← true for log, false for arithmetic
```

**You cannot have both.** A weighted sum of log returns is not the portfolio's log return. This is why practical VaR systems typically model log returns *of risk factors* and then compute *arithmetic* P&L by full or approximate revaluation — the log return goes into the factor simulation, and the currency P&L comes out of the pricing function.

### 1.2 Numerical illustration

A price goes 100 → 110 → 100.

| | Period 1 | Period 2 | Sum | Actual total |
|---|---|---|---|---|
| Arithmetic | +10.00% | −9.09% | +0.91% | **0.00%** |
| Log | +9.531% | −9.531% | 0.000% | **0.00%** |

The arithmetic returns sum to a fictitious +0.91% gain. The log returns sum correctly to zero. **For any multi-period statement, use log returns.**

> **A market-risk consequence:** because banks report P&L in currency and measure risk over one day, the distinction is usually immaterial *within* a day and becomes material the moment anything is scaled or compounded across time — which is exactly what square-root-of-time scaling does. See [11 §8](11_VaR.md).

---

## 2. Volatility

### 2.1 Definition

```
                  ┌─────────────────────────┐
                  │   1     T               │
   σ   =   √      │ ───── · Σ  (rₜ − r̄)²   │
                  │  T−1   t=1              │
                  └─────────────────────────┘
```

### 2.2 Annualisation

```
   σ_annual  =  σ_daily × √252
```

**252 is the trading-day convention**, not a law of nature. Some institutions use 250, some 260. Whichever is chosen must be applied consistently, because a VaR number scaled with 252 and a limit calibrated on 250 will not reconcile.

The `√T` scaling assumes returns are **independent and identically distributed**. They are not — volatility clusters and returns exhibit mild autocorrelation — which is why the scaling is an approximation and why regulators increasingly require direct estimation at the target horizon. See [11 §8](11_VaR.md) and `MAR33.4`, which requires ES to be computed for changes over the base interval *"without scaling from a shorter horizon."*

### 2.3 The four kinds of volatility

| Kind | Source | Backward or forward looking | Where used |
|---|---|---|---|
| **Historical / realised** | Sample standard deviation of past returns | Backward | VaR, correlation estimation |
| **EWMA** | Exponentially weighted historical | Backward, recency-weighted | Fast-adapting VaR |
| **GARCH** | Fitted conditional-variance model | Backward-fitted, forward-projecting | Volatility forecasting |
| **Implied** | Backed out of option prices | **Forward** | Option pricing, vega risk |

### 2.4 EWMA

Equally-weighted historical volatility has a well-known pathology: a large return enters the window and raises volatility, then **drops out of the window** on an arbitrary date and causes a discontinuous fall. This is the "ghost feature," and it produces VaR jumps that correspond to nothing in the market.

EWMA fixes it by letting old observations decay smoothly:

```
   σ²ₜ  =  λ · σ²ₜ₋₁  +  (1 − λ) · r²ₜ₋₁
```

with λ typically 0.94 for daily data (the classic RiskMetrics parameter) or 0.97 for monthly.

**Effective window length** ≈ `1/(1−λ)`. For λ = 0.94 that is about 17 days — very responsive, and correspondingly noisy.

**The trade-off is unavoidable.** Low λ adapts fast to regime change and is unstable. High λ is stable and slow. Neither is right; the choice must be made deliberately and disclosed.

### 2.5 Volatility clustering

Large moves follow large moves. This single empirical regularity — present in essentially every financial time series ever examined — is why:

- historical simulation with a short window is highly regime-dependent;
- EWMA and GARCH exist at all;
- **stressed calibration periods** are required by FRTB (`MAR33.5`) rather than left to the bank's choice of window.

---

## 3. Covariance and correlation

### 3.1 Definitions

```
   Cov(X,Y)  =  E[(X − μ_X)(Y − μ_Y)]

                    Cov(X,Y)
   ρ(X,Y)   =   ─────────────────           ∈ [−1, +1]
                     σ_X · σ_Y
```

Correlation is covariance normalised by the two volatilities — dimensionless, bounded, and comparable across pairs. Covariance is not comparable across pairs, because its scale depends on the units of both variables.

### 3.2 The covariance matrix

```
   Σ  =  D · R · D
```

where `D = diag(σ₁, …, σₙ)` and `R` is the correlation matrix.

**Our portfolio's correlation matrix:**

```
        A      B      C
   A [ 1.00   0.30   0.10 ]
   B [ 0.30   1.00   0.50 ]
   C [ 0.10   0.50   1.00 ]
```

**Covariance matrix** (`σᵢσⱼρᵢⱼ`):

```
             A          B          C
   A [  0.010000   0.006000   0.003500 ]
   B [  0.006000   0.040000   0.035000 ]
   C [  0.003500   0.035000   0.122500 ]
```

### 3.3 Positive semi-definiteness — a hard requirement

A valid covariance matrix must be **positive semi-definite (PSD)**: `xᵀΣx ≥ 0` for all `x`. Equivalently, all eigenvalues ≥ 0.

**Why it matters.** `xᵀΣx` *is* the variance of the portfolio with weights `x`. A non-PSD matrix implies **a portfolio with negative variance** — mathematically impossible, and it will surface as a negative VaR, a failed Cholesky decomposition, or a Monte Carlo simulation that will not run.

**Why non-PSD matrices arise in practice — all four causes are common:**

| Cause | Mechanism |
|---|---|
| **Pairwise estimation on unequal histories** | Each ρᵢⱼ estimated on whatever overlapping data exists; the result need not be jointly consistent |
| **More factors than observations** | *n* > *T* guarantees a singular (rank-deficient) sample matrix |
| **Manual overrides** | A risk manager "adjusts" one correlation to a judgemental value |
| **Stress adjustments** | Correlations shocked toward 1 for a stress scenario, inconsistently |

**Repair methods:** eigenvalue clipping (set negative eigenvalues to zero or a small floor and renormalise), shrinkage toward a structured target (Ledoit-Wolf), or nearest-correlation-matrix algorithms (Higham). **Any repair changes the risk numbers and must be logged, quantified and disclosed** — a silent repair is a silent model change.

### 3.4 Cholesky decomposition

To simulate correlated normal variables:

```
   Σ  =  L · Lᵀ            (L lower triangular)
   z  ~  N(0, I)           (independent standard normals)
   x  =  L · z             (has covariance Σ)
```

**The Cholesky decomposition exists if and only if Σ is positive definite.** A failure is therefore not a numerical inconvenience — it is the algorithm correctly refusing to simulate an impossible market. Treat it as a data-quality alarm, never as something to work around by adding a fudge to the diagonal without recording it.

---

## 4. Portfolio variance — the central formula

### 4.1 Formula

```
                n                n    n
   σ²_p   =     Σ  wᵢ² σᵢ²   +   Σ    Σ   wᵢ wⱼ σᵢ σⱼ ρᵢⱼ
               i=1              i=1  j≠i
             └── standalone ──┘  └──── interaction ────┘
```

In matrix form, which is how it is actually computed:

```
   σ²_p  =  wᵀ Σ w
```

### 4.2 Worked example — our portfolio

**Standalone terms:**

```
   w_A² σ_A²  =  0.36 × 0.0100  =  0.003600
   w_B² σ_B²  =  0.09 × 0.0400  =  0.003600
   w_C² σ_C²  =  0.01 × 0.1225  =  0.001225
                                    ─────────
                                     0.008425
```

**Cross terms:**

```
   2 w_A w_B σ_A σ_B ρ_AB  =  2 × 0.6 × 0.3 × 0.10 × 0.20 × 0.30  =  0.002160
   2 w_A w_C σ_A σ_C ρ_AC  =  2 × 0.6 × 0.1 × 0.10 × 0.35 × 0.10  =  0.000420
   2 w_B w_C σ_B σ_C ρ_BC  =  2 × 0.3 × 0.1 × 0.20 × 0.35 × 0.50  =  0.002100
                                                                     ─────────
                                                                      0.004680
```

**Result:**

```
   σ²_p  =  0.008425 + 0.004680  =  0.013105
   σ_p   =  √0.013105            =  0.114477   =  11.4477%
```

**In currency:** on $100m, one annual standard deviation is **$11.45m**.

---

## 5. Diversification

### 5.1 The measure

```
   Undiversified risk  =  Σ wᵢ σᵢ  =  0.6(0.10) + 0.3(0.20) + 0.1(0.35)
                       =  0.060 + 0.060 + 0.035  =  0.1550  =  15.50%

   Diversified risk    =  σ_p  =  11.4477%

   Diversification benefit  =  15.50% − 11.4477%  =  4.05 percentage points

   Diversification ratio    =  11.4477 / 15.50    =  0.7386
```

The portfolio carries **26.1% less risk** than the sum of its parts. On $100m that is $4.05m of annual standard deviation not borne.

### 5.2 The critical caveat

> **Diversification is a statement about correlations, and correlations are not constants.**

In a systemic crisis correlations converge toward 1, and the benefit computed above shrinks toward zero **precisely when the loss is largest**. A portfolio sized to its diversified risk in calm conditions is over-sized for a crisis.

This is not a theoretical concern; it is the observed behaviour of every major crisis. It is why:

- FRTB's SBM runs **three correlation scenarios** and takes the worst (`MAR21.6`, `MAR21.7`);
- FRTB's IMA constrains cross-risk-class correlations by a supervisory aggregation scheme rather than letting banks use empirical estimates freely (`MAR33.14`);
- internal frameworks run explicit **correlation-breakdown stress scenarios** ([13](13_Stress_Testing.md)).

### 5.3 Worked — what happens when correlations go to 1

Set all ρ = 1:

```
   σ_p  =  Σ wᵢ σᵢ  =  15.50%
```

Risk rises from 11.45% to 15.50% — a **35% increase** — with no change in any position and no change in any volatility. The entire move comes from the correlation assumption.

---

## 6. Risk decomposition — marginal, component, incremental

Three related but distinct questions. Confusing them is common and consequential.

| Measure | Question | Sums to total? |
|---|---|---|
| **Marginal (MCR)** | If I add a *small* amount of *i*, how much does risk change? | No |
| **Component (CCR)** | How much of the *current* total risk is attributable to *i*? | **Yes** |
| **Incremental (IVaR)** | If I removed position *i* entirely, how much would risk fall? | No |

### 6.1 Marginal contribution to risk

```
                ∂σ_p         Cov(rᵢ, r_p)         (Σw)ᵢ
   MCRᵢ  =  ─────────  =  ────────────────  =  ─────────
                ∂wᵢ              σ_p              σ_p
```

### 6.2 Component contribution to risk

```
   CCRᵢ  =  wᵢ · MCRᵢ                    and        Σ CCRᵢ  =  σ_p
```

**This additive property is Euler's theorem applied to a homogeneous-of-degree-one risk measure**, and it is the reason component contribution — not marginal — is the right basis for limit allocation and risk-adjusted performance.

### 6.3 Worked example — the full decomposition

**Covariance of each asset with the portfolio:**

```
   Cov(A, p) = w_A σ_A² + w_B σ_Aσ_Bρ_AB + w_C σ_Aσ_Cρ_AC
             = 0.6(0.0100) + 0.3(0.0060) + 0.1(0.0035)  =  0.008150

   Cov(B, p) = 0.6(0.0060) + 0.3(0.0400) + 0.1(0.0350)  =  0.019100

   Cov(C, p) = 0.6(0.0035) + 0.3(0.0350) + 0.1(0.1225)  =  0.024850
```

**Marginal and component contributions:**

| Asset | Weight | σᵢ | Cov(i,p) | MCRᵢ | CCRᵢ | **% of risk** | % of capital |
|---|---|---|---|---|---|---|---|
| A | 60% | 10% | 0.008150 | 0.071193 | 0.042716 | **37.31%** | 60% |
| B | 30% | 20% | 0.019100 | 0.166846 | 0.050054 | **43.72%** | 30% |
| C | 10% | 35% | 0.024850 | 0.217074 | 0.021707 | **18.96%** | 10% |
| | | | | **Σ** | **0.114477** | **100.00%** | 100% |

The component contributions sum **exactly** to σ_p = 11.4477%. ✓

### 6.4 Interpretation — the whole point of the exercise

> **Asset A is 60% of the capital and 37% of the risk. Asset C is 10% of the capital and 19% of the risk.**

Capital allocation and risk allocation are different things, and it is risk allocation that should drive limits, hedging priority and risk-adjusted return measurement. A desk reviewing only notional or market-value exposure would conclude that A is the position to worry about. The decomposition says B is, with C punching nearly twice its weight.

Note also that **C's marginal contribution (0.217) is the highest of the three** — adding a dollar to C raises portfolio risk more than adding a dollar to A or B. Marginal answers "what should I trim at the margin?"; component answers "where is my risk today?". Both are useful; they are not the same question.

---

## 7. From portfolio statistics to VaR

The bridge to the next document:

```
   VaR_α  =  −  z_α · σ_p · V                    (parametric, zero mean)
```

**For our portfolio**, at 99% one-day, using `σ_daily = 11.4477% / √252 = 0.72118%`:

```
   VaR₉₉  =  2.32635 × 0.0072118 × $100,000,000  =  $1,677,800
```

*(z₉₉ = 2.326348, the 99th percentile of the standard normal.)*

Every assumption in that one line is contestable, and [11](11_VaR.md) contests them all: normality, zero drift, stable covariance, √T scaling, and the adequacy of a single quantile.

---

## 8. Pseudocode

```
FUNCTION portfolio_risk(weights, vols, corr_matrix):
    n     = len(weights)
    cov   = [[vols[i]*vols[j]*corr_matrix[i][j] for j in range(n)]
                                                 for i in range(n)]
    ASSERT is_positive_semidefinite(cov)          # hard gate, never bypass

    var_p = sum(weights[i]*weights[j]*cov[i][j]
                for i in range(n) for j in range(n))
    sd_p  = sqrt(var_p)

    mcr, ccr = [], []
    FOR i IN range(n):
        cov_ip = sum(weights[j]*cov[i][j] for j in range(n))
        m      = cov_ip / sd_p
        mcr.append(m)
        ccr.append(weights[i] * m)

    ASSERT abs(sum(ccr) - sd_p) < tolerance       # Euler identity

    undiv = sum(weights[i]*vols[i] for i in range(n))
    RETURN {
        "volatility": sd_p,
        "undiversified": undiv,
        "diversification_ratio": sd_p / undiv,
        "marginal": mcr,
        "component": ccr,
        "pct_contribution": [c/sd_p for c in ccr]
    }


FUNCTION ewma_volatility(returns, lam = 0.94, seed_window = 100):
    var = variance(returns[0:seed_window])
    FOR r IN returns[seed_window:]:
        var = lam*var + (1-lam)*r*r
    RETURN sqrt(var)


FUNCTION nearest_psd(matrix):
    eigenvalues, eigenvectors = eigen_decompose(matrix)
    clipped = [max(e, 0.0) for e in eigenvalues]
    IF clipped != eigenvalues:
        LOG_MODEL_ADJUSTMENT(                     # never silent
            "correlation matrix repaired",
            negative_eigenvalues = [e for e in eigenvalues if e < 0])
    rebuilt = eigenvectors @ diag(clipped) @ transpose(eigenvectors)
    RETURN renormalise_to_unit_diagonal(rebuilt)
```

---

## 9. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **PSD** | All eigenvalues of Σ ≥ 0 |
| 2 | **Cholesky** | Decomposition succeeds |
| 3 | **Correlation bounds** | Every ρ ∈ [−1, 1]; diagonal exactly 1 |
| 4 | **Symmetry** | `Σᵢⱼ = Σⱼᵢ` exactly |
| 5 | **Euler identity** | `Σ CCRᵢ = σ_p` to tolerance |
| 6 | **Diversification bound** | `σ_p ≤ Σ wᵢσᵢ`, always |
| 7 | **Perfect-correlation limit** | Setting all ρ = 1 reproduces `Σ wᵢσᵢ` |
| 8 | **Single-asset limit** | `n = 1` gives `σ_p = σ₁` |
| 9 | **Annualisation** | Trading-day count consistent across VaR, limits and reporting |
| 10 | **Estimation window** | Documented; identical across all pairs, or the inconsistency disclosed |
| 11 | **Matrix repairs** | Logged, quantified and reported — never silent |
| 12 | **Return type** | Log for time aggregation; arithmetic for cross-sectional |

---

## 10. Common implementation errors

| Error | Consequence |
|---|---|
| Summing arithmetic returns across time | Fictitious gains (see §1.2) |
| Weighted-averaging log returns across assets | Wrong portfolio return |
| Pairwise correlations on differing histories | Non-PSD matrix, failed simulation |
| Silently repairing a non-PSD matrix | Undisclosed model change |
| Mixing 250/252/260 trading days | Reconciliation breaks between VaR and limits |
| Using marginal where component is needed | Contributions do not sum; allocation is arbitrary |
| Equally-weighted volatility with a fixed window | Ghost features — VaR jumps on arbitrary dates |
| Assuming stable correlations | Diversification benefit evaporates in stress |
| `√T` scaling a 1-day figure to 10 days without testing | Understates risk under volatility clustering |

---

## 11. Limitations

1. **Normality is assumed nowhere in this document and everywhere in its usual application.** The formulas for variance and contribution hold for any distribution with finite second moments. The *interpretation* of σ as a risk measure implicitly assumes something close to normality, and financial returns are not normal.
2. **Second moments are not enough.** Skew and kurtosis carry the tail, and variance is blind to both.
3. **Correlation captures only linear dependence.** Two variables can be strongly dependent with correlation near zero — and tail dependence, which is what matters in a crisis, is not measured by ρ at all.
4. **Estimation error is large**, especially for correlations, and grows as `n²` while data grows as `T`. For a realistic factor count the sample covariance matrix is badly conditioned and often singular.
5. **All of this is static.** Volatilities and correlations are time-varying, regime-dependent, and change fastest in exactly the conditions the risk measure is meant to describe.

---

## 12. Related Concepts

- [11 — Value at Risk](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [13 — Stress Testing](13_Stress_Testing.md) · [42 — Risk Aggregation](42_Risk_Aggregation.md)
- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.6`–`MAR21.7` correlation scenarios; `MAR33.4`, `MAR33.5`, `MAR33.14` |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR text |

*Accessed 25 August 2026.*
