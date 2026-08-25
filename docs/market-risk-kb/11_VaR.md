# 11 — Value at Risk

**Level:** 6 · **Prerequisites:** [10](10_Portfolio_Risk_Mathematics.md) · **Feeds:** [12](12_Expected_Shortfall.md), [15](15_Backtesting.md), [18](18_FRTB_Internal_Models_Approach.md)

---

## 1. Plain English

> **VaR answers approximately: "How much could this portfolio lose over a selected horizon, at a selected confidence level, under the assumptions of the model?"**

Every clause in that sentence is doing work, and the last one is doing the most.

### 1.1 The precise statement

**VaR at confidence level α over horizon *h* is the loss that will not be exceeded with probability α, over *h*, assuming the model is right.**

Formally, for loss `L`:

```
   VaR_α  =  inf{ ℓ ∈ ℝ  :  P(L > ℓ)  ≤  1 − α }
```

Equivalently, VaR is the α-quantile of the loss distribution.

### 1.2 What VaR does *not* say

This is the more important list, and misunderstanding it has caused real institutional damage:

| VaR does **not** say | Because |
|---|---|
| The maximum you can lose | It is a quantile, not a bound. Losses beyond it are *expected* to occur (1−α) of the time |
| How bad the bad days are | It is the threshold, not the average beyond it. **This is ES's job** — [12](12_Expected_Shortfall.md) |
| Anything about tomorrow specifically | It is a statement about a distribution, not a forecast |
| That the model is right | Every VaR number is conditional on assumptions that are all, strictly, false |

> **"99% 1-day VaR is $10m" means: on roughly one day in a hundred we expect to lose more than $10m. It does not mean the most we can lose is $10m.** A bank whose management reads it the second way is a bank that will be surprised on schedule, about 2.5 times a year.

---

## 2. Banking example

A trading desk reports **99% 1-day VaR of $10 million**.

Interpretation: on about **one trading day in a hundred** — roughly 2.5 days per year — the desk expects to lose more than $10m. On the other 99 days it expects to lose less, or make money.

Six months in, the desk has had **four days** worse than −$10m. Is the model broken?

Under a correct model, the number of exceptions in 125 days is Binomial(125, 0.01), with mean 1.25. Four exceptions is unusual but not damning; it is roughly a 3.7% tail outcome. It warrants investigation, not immediate rejection. **That reasoning — treating exception counts as a statistical test rather than a verdict — is the whole content of backtesting** ([15](15_Backtesting.md)).

---

## 3. The three (four) methods

| Method | Distribution comes from | Revaluation | Fat tails | Cost |
|---|---|---|---|---|
| **Historical simulation** | Actual past factor changes | Full or approximate | **Captured, if in the window** | Moderate |
| **Parametric / variance-covariance** | Assumed (usually normal) | Linear approximation | **Not captured** | Very low |
| **Monte Carlo** | Assumed, then sampled | Full | Captured **if modelled** | **Very high** |
| **Delta-normal / delta-gamma** | Assumed normal | First / second order | Partially (delta-gamma) | Low |

---

## 4. Historical Simulation VaR

### 4.1 Plain English

Take what the market actually did on each of the last *N* days. Apply each of those days' moves to today's portfolio. Sort the resulting P&Ls. Read off the percentile.

### 4.2 Why it is the industry default

It makes **no distributional assumption**. Fat tails, skew, volatility clustering and non-linear factor dependence are all inherited from the data rather than modelled. Its assumptions are about *relevance* (the past window represents the future) rather than about *shape*.

### 4.3 Full algorithm

```
INPUT: current positions P
       current market data M₀
       historical factor observations M₋₁ … M₋N   (N = lookback, e.g. 250 or 500)
       confidence level α
       horizon h

STEP 1 — build the scenario set
FOR t = 1 TO N:
    FOR each risk factor f:
        IF f is a rate or spread:
            shock[f,t] = M[f, -t] - M[f, -(t+1)]              # absolute change
        ELSE:                                                  # price-like factor
            shock[f,t] = M[f, -t] / M[f, -(t+1)] - 1           # relative change

STEP 2 — apply each scenario to TODAY's portfolio
V₀ = value(P, M₀)
FOR t = 1 TO N:
    M_t   = apply_shock(M₀, shock[:,t])
    V_t   = value(P, M_t)                    # FULL REVALUATION preferred
    PnL_t = V_t - V₀

STEP 3 — order and select
sorted_PnL = sort_ascending(PnL)             # worst first
index      = (1 - α) * N
VaR        = -select_quantile(sorted_PnL, index)

RETURN VaR
```

### 4.4 The absolute-versus-relative shock decision

Step 1 contains a modelling choice that is **not a detail**:

| Factor type | Convention | Reason |
|---|---|---|
| Interest rates, credit spreads | **Absolute** (bp change) | A 2bp move from 0.5% and from 5% are comparable events; relative shocks explode near zero and cannot handle negative rates |
| Equity, FX, commodity prices | **Relative** (% change) | A $1 move in a $10 stock and a $500 stock are not comparable events |
| Implied volatilities | Either — institution-specific | Relative is common; absolute is used for normal-vol rate markets |

> Applying relative shocks to interest rates in a near-zero or negative rate environment is one of the classic ways to produce a VaR model that reports nonsense. The 2014–2021 negative-rate period in EUR and JPY forced the industry to absolute shocks for rates, and the choice should now be considered settled for rate and spread factors.

### 4.5 Worked example — 250-day historical simulation

A desk's 250 historical scenarios, revalued on today's book. The ten worst outcomes ($000s):

| Rank | Scenario date | P&L |
|---|---|---|
| 1 | (worst) | **−4,820** |
| 2 | | **−3,910** |
| 3 | | **−3,450** |
| 4 | | −3,180 |
| 5 | | −2,940 |
| 6 | | −2,760 |
| 7 | | −2,610 |
| 8 | | −2,455 |
| 9 | | −2,320 |
| 10 | | −2,180 |

**99% VaR: the quantile index is `(1 − 0.99) × 250 = 2.5`.** There is no 2.5th observation, so a convention is required — and the three in common use give three different answers:

| Convention | Rule | Result |
|---|---|---|
| **Conservative (round up)** | Take the 3rd worst | **$3,450k** |
| **Non-interpolated (round down)** | Take the 2nd worst | **$3,910k** |
| **Linear interpolation** | Midpoint of 2nd and 3rd | **$3,680k** |

**A spread of $460k — 13% of the VaR — arising entirely from a convention.** All three are defensible; none is "the" answer. The convention must be documented, applied consistently, and disclosed in any comparison. **This is the single most common cause of unexplained VaR differences between two institutions holding the same portfolio.**

### 4.6 Weighting schemes

| Scheme | Mechanism | Trade-off |
|---|---|---|
| **Equal weighting** | Every scenario weight `1/N` | Simple; suffers ghost features when large moves exit the window |
| **Age weighting** | Weight `∝ λ^t`, recent days heavier | Responsive; effectively shortens the sample and adds noise |
| **Volatility scaling** | Rescale each historic return by `σ_today/σ_then` | Adapts to regime; can amplify a stale volatility estimate |
| **Filtered historical simulation** | GARCH-filter returns, simulate, un-filter | Best of both; complex, and now a model with parameters |

### 4.7 Lookback window — the fundamental tension

| Window | Advantage | Disadvantage |
|---|---|---|
| **250 days (1y)** | Responsive to the current regime | Small tail sample; only ~2.5 observations beyond 99% |
| **500 days (2y)** | Better-populated tail | Slower to react; mixes regimes |
| **1,000+ days** | Rich tail, includes stress | May be dominated by an irrelevant regime |

**The arithmetic of the tail is the binding constraint.** At 99% with 250 observations, the VaR estimate rests on **two or three data points**. That is not a robust estimate of anything, and it is the strongest single argument for Expected Shortfall at a lower confidence level — 97.5% ES over 250 days averages over about six observations rather than selecting one. See [12](12_Expected_Shortfall.md).

Basel's IMA requires the ES measure to be calibrated to a **period of stress** rather than simply to a recent window (`MAR33.5`), and supervisors may require a shorter observation period during a volatility upsurge, though **no shorter than six months** (`MAR33.12`).

---

## 5. Parametric / Variance-Covariance VaR

### 5.1 Plain English

Assume returns are normally distributed. Compute the portfolio's standard deviation from a covariance matrix. Multiply by the appropriate number of standard deviations.

### 5.2 Formula

```
   VaR_α  =  −( μ_p  +  z_{1−α} · σ_p ) · V
```

and with the near-universal zero-drift assumption over one day:

```
   VaR_α  =  z_α · σ_p · V

   where   σ_p  =  √( wᵀ Σ w )
```

### 5.3 The z-multipliers

| Confidence | z |
|---|---|
| 90% | 1.28155 |
| 95% | 1.64485 |
| 97.5% | 1.95996 |
| **99%** | **2.32635** |
| 99.9% | 3.09023 |

### 5.4 Worked example — the [10](10_Portfolio_Risk_Mathematics.md) portfolio

From [10 §4.2](10_Portfolio_Risk_Mathematics.md): `σ_p = 11.4477%` annual on a $100m portfolio.

```
   σ_daily  =  0.114477 / √252  =  0.0072114   =  0.72114%

   VaR₉₉    =  2.32635 × 0.0072114 × $100,000,000  =  $1,677,600

   VaR₉₅    =  1.64485 × 0.0072114 × $100,000,000  =  $1,186,200

   VaR₉₇.₅  =  1.95996 × 0.0072114 × $100,000,000  =  $1,413,400
```

### 5.5 Why the drift is set to zero

Over one day the expected return is tiny relative to the standard deviation, and **estimating it introduces more error than it removes**. Expected returns are notoriously hard to estimate; volatilities are comparatively easy. Setting μ = 0 is a deliberate, conservative simplification and is standard practice. Over longer horizons — a 10-day or 1-year measure — the drift can matter and should be considered explicitly.

### 5.6 Delta-normal and delta-gamma

**Delta-normal** is parametric VaR where the portfolio is represented by its first-order sensitivities:

```
   σ_p  =  √( δᵀ Σ δ )               δ = vector of factor sensitivities
```

**Delta-gamma** adds the second-order term, which makes the P&L distribution non-normal (a quadratic form in normals) and requires either a Cornish-Fisher expansion or a partial simulation to obtain the quantile.

| | Delta-normal | Delta-gamma |
|---|---|---|
| Handles linear books | Yes | Yes |
| Handles options | **No** | Partially |
| Distribution of P&L | Normal | Quadratic in normals (skewed) |
| Quantile obtained by | Closed form | Cornish-Fisher / simulation |
| Cost | Trivial | Low |

> **Delta-normal VaR on a short-gamma options book can be badly wrong in the direction that matters.** The book looks flat on delta, so the estimated variance is small, while the actual loss under a large move in *either* direction is severe. See [09 §10.2](09_Options_and_Greeks.md) for the numerical demonstration.

---

## 6. Monte Carlo VaR

### 6.1 Algorithm

```
INPUT: positions P, current market M₀, covariance Σ (or a full factor model),
       number of paths K (typically 10,000 – 100,000), confidence α

STEP 1 — factorise
    L = cholesky(Σ)                     # fails if Σ is not positive definite

STEP 2 — simulate
    FOR k = 1 TO K:
        z_k     = draw n independent N(0,1)
        shock_k = L · z_k               # or a fat-tailed / copula draw
        M_k     = apply_shock(M₀, shock_k)
        PnL_k   = value(P, M_k) - value(P, M₀)     # FULL revaluation

STEP 3 — read the quantile
    sorted = sort_ascending(PnL)
    VaR    = -sorted[ floor((1-α) * K) ]
```

### 6.2 Advantages and the cost that dominates everything

| Advantage | Cost |
|---|---|
| Any distributional assumption — Student-t, jump-diffusion, copulas | **K × number of positions** full revaluations |
| Full revaluation, so all non-linearity captured | For a large bank: millions of pricings per day |
| Path-dependent products handled correctly | Convergence error `∝ 1/√K` |
| Arbitrary horizon | Simulation noise can exceed the effect being measured |

**The computational cost is not incidental.** A bank with 200,000 positions and 50,000 paths faces 10 billion revaluations. This is why production Monte Carlo VaR relies on variance reduction (antithetic variates, control variates, importance sampling), on grid-based pricing approximations, and on hardware — and why historical simulation, at 250–500 revaluations, remains the industry default.

### 6.3 The assumption trap

> **Monte Carlo does not remove distributional assumptions. It relocates them.** Simulating from a multivariate normal produces a normal-tailed answer with far more computation than the closed-form parametric method and no more accuracy in the tail. The value of Monte Carlo is realised only when the simulated distribution is genuinely richer than normal — fat-tailed marginals, a copula dependence structure, stochastic volatility, jumps.

---

## 7. Confidence levels

| Level | Exceptions/year (250 days) | Where used |
|---|---|---|
| **95%** | 12.5 | Internal management; more frequent exceptions make backtesting statistically powerful |
| **97.5%** | 6.25 | **FRTB ES confidence level** (`MAR33.3`); desk backtesting (`MAR32.18`) |
| **99%** | 2.5 | Basel 2.5 VaR; desk backtesting (`MAR32.18`); most internal limits |
| **99.9%** | 0.25 | Economic capital; too rare to backtest meaningfully |

**The trade-off is fundamental.** Higher confidence sounds more prudent but is *less verifiable*: 99.9% VaR produces one exception every four years, so a decade of data yields two or three observations — nothing can be concluded from that. This tension is exactly why FRTB pairs a **97.5% ES** for capital with backtesting at **both 97.5% and 99% VaR**: capital from the measure that describes the tail, validation from the measures that generate enough exceptions to test.

---

## 8. Horizon and square-root-of-time scaling

### 8.1 The scaling rule

```
   VaR_h  =  VaR_1 · √h
```

**Worked example:** 1-day VaR of $1,677,600 scaled to 10 days:

```
   VaR₁₀  =  1,677,600 × √10  =  1,677,600 × 3.16228  =  $5,305,400
```

### 8.2 The assumptions — all three are violated

| Assumption | Reality | Direction of error |
|---|---|---|
| Returns are i.i.d. | Volatility clusters | **Understates** — bad days cluster together |
| Zero autocorrelation | Mild autocorrelation, momentum and reversal | Either direction |
| Static portfolio | Positions are traded during the horizon | Usually overstates for a liquid book |
| Constant volatility | Volatility itself is stochastic | **Understates** |

> On balance, `√T` scaling from one day to ten **tends to understate risk**, because the dominant violated assumption is volatility clustering, and clustering means a bad day is more likely to be followed by another bad day than independence would imply.

Basel takes this seriously. `MAR33.4(5)` requires that the expected shortfall at horizon *T* be *"calculated for changes in the risk factors … over the time interval T **without scaling from a shorter horizon**."* The liquidity-horizon scaling that FRTB does perform (`MAR33.4`) operates on a **10-day base horizon** and applies a specific formula across nested risk-factor subsets — it is not a naive `√T` extension of a 1-day number.

### 8.3 Liquidity horizons

The deeper problem with a fixed horizon is that **different positions take different times to exit.** A G7 government bond can be liquidated in a day; a bespoke structured note cannot be liquidated at all in any reasonable period.

FRTB's answer is risk-factor-specific liquidity horizons of **10, 20, 40, 60 or 120 days** (`MAR33.4`, Table 1), assigned per risk-factor category by `MAR33.12` Table 2. This is the single largest conceptual advance of FRTB's IMA over the Basel 2.5 framework it replaced. See [18](18_FRTB_Internal_Models_Approach.md).

---

## 9. Method comparison

| | Historical simulation | Parametric | Monte Carlo |
|---|---|---|---|
| Distributional assumption | **None** | Normal (usually) | Whatever you choose |
| Fat tails | Captured if in window | **Not captured** | If modelled |
| Non-linearity | **Yes** (full reval) | No (delta-normal) | **Yes** |
| Path dependence | No | No | **Yes** |
| Computation | Moderate (N revals) | Trivial | **Very high** |
| Data requirement | Long clean factor history | Covariance matrix | Full model specification |
| Transparency | **High** — every number traces to a date | High | **Low** — a black box to most users |
| Main weakness | **The future resembles the window** | Normality is false | Cost, and assumptions in disguise |
| Typical use | **Production default** | Quick estimates, limits | Exotic books, economic capital |

### 9.1 Reconciling the methods on our portfolio

| Method | 99% 1-day VaR | Comment |
|---|---|---|
| Parametric (normal) | $1,677,600 | From §5.4 |
| Historical simulation | $3,450,000 | From §4.5 (conservative convention) |

**The historical figure is more than double the parametric figure.** That is not an error in either — it is the fat tail. The normal distribution assigns far too little probability to the large moves that actually occurred in the window. A bank that reports only the parametric number is systematically understating its tail risk, and the size of the gap is a useful diagnostic in its own right.

---

## 10. Regulatory history — do not conflate the eras

Market-risk methodology has evolved, and presenting a superseded requirement as current is a specific error this knowledge base guards against.

| Era | Framework | Measure | Status |
|---|---|---|---|
| 1996–2008 | Basel Market Risk Amendment | 99% 10-day VaR × multiplier | **Superseded** |
| 2009–~2022 | Basel 2.5 | VaR + **Stressed VaR** + IRC + CRM | **Superseded** by FRTB as jurisdictions implement |
| FRTB | Basel III market risk framework | **97.5% ES**, liquidity-horizon-adjusted, + SES for NMRFs + DRC | **Current Basel standard**; jurisdictional implementation dates vary — see [29](29_Regulatory_Framework.md) |

**A point where the "everything changed" narrative is wrong, and worth getting right.** The **traffic-light backtesting zones were not retired by FRTB.** `MAR32.8`–`MAR32.9` retain green / amber / red zones for **bank-wide** backtesting against a 99th-percentile VaR measure, on a 250-observation sample.

What *did* change is the multiplier scale attached to them. Under the 1996 Amendment and Basel 2.5 the multiplication factor was 3 plus an add-on; under FRTB `m_c` is **fixed at 1.5** plus a backtesting add-on ranging from **0 to 0.5** (`MAR33.42`), giving the `MAR32.9` Table 1 schedule of 1.50 (green) through 1.70–1.92 (amber) to 2.00 (red).

FRTB then **adds** a second, harder regime that did not previously exist: **desk-level** backtesting at *two* confidence levels, with a bright-line consequence rather than a capital surcharge — a desk exceeding the thresholds loses the IMA entirely. See [15](15_Backtesting.md).

**VaR has not disappeared under FRTB.** It remains:
- the **backtesting** measure at desk level, at 97.5% and 99% (`MAR32.18`);
- the basis of the bank-wide backtesting add-on to the multiplier `m_c` (`MAR33.42`);
- the near-universal internal management and limit metric.

---

## 11. Assumptions, limitations and the honest caveats

1. **A quantile is not a bound.** Losses beyond VaR are expected, by construction.
2. **VaR is silent about the tail's shape.** Two portfolios with identical VaR can have wildly different losses beyond it. This is ES's entire reason for existing.
3. **VaR is not sub-additive in general.** It can happen that `VaR(A+B) > VaR(A) + VaR(B)` — combining two portfolios *increases* measured risk, which contradicts the intuition that diversification cannot hurt. This failure of coherence is the formal argument that drove the regulatory move to ES ([12 §3](12_Expected_Shortfall.md)).
4. **Historical simulation assumes the window represents the future.** It cannot produce a scenario that never happened.
5. **Parametric VaR assumes normality**, which is false in every financial market ever studied.
6. **Estimation error is large**, particularly in the tail, and particularly for correlations.
7. **VaR is a static, single-period measure.** It says nothing about liquidation over multiple days, feedback effects, or the market impact of the bank's own unwinding.
8. **It can be gamed.** A position with a small loss 99% of the time and a catastrophic loss 1% of the time has low VaR by construction. Selling deep out-of-the-money options is exactly this trade, and VaR-based limits actively reward it. **Stress testing and ES exist partly as a defence against this incentive.**

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Backtesting** | Exception count consistent with the confidence level; see [15](15_Backtesting.md) |
| 2 | **Input completeness** | Every position included; failures escalated, **never defaulted to zero** |
| 3 | **Factor coverage** | Every material risk factor mapped; proxies documented |
| 4 | **Scenario count** | Full lookback available; missing days investigated, not silently dropped |
| 5 | **Shock convention** | Absolute for rates/spreads; relative for prices — verified per factor |
| 6 | **Quantile convention** | Documented and consistently applied (§4.5) |
| 7 | **Method benchmark** | Parametric vs historical compared; large gaps explained, not ignored |
| 8 | **Scaling** | `√T` use disclosed; direct-horizon estimation where required |
| 9 | **Sub-portfolio reconciliation** | Sum of standalone VaRs ≥ portfolio VaR (diversification is non-negative) |
| 10 | **Non-linearity** | Full revaluation for optioned books; delta-normal not used for them |
| 11 | **P&L distribution review** | Histogram inspected for bimodality, gaps, and outliers |
| 12 | **Stale data** | Unchanged factor values across scenarios detected and flagged |
| 13 | **Ghost features** | VaR jumps traced to scenario window entry/exit, not reported as market events |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Relative shocks on interest rates | Breaks at zero and negative rates |
| Undocumented quantile convention | 13% VaR differences that cannot be reconciled (§4.5) |
| Failed valuations defaulted to zero | Position's value *and* risk silently removed |
| Delta-normal on an options book | Tail understated in the direction that matters |
| Monte Carlo from a normal, at great cost | Parametric answer, 10,000× the computation |
| Sub-portfolio VaRs summed to a total | Ignores diversification; wrong by construction |
| Ghost features reported as market moves | Misleading commentary; wasted investigation |
| Backtesting against **actual** P&L only | Fees and intraday trading contaminate the test |
| Mixing Basel 2.5 and FRTB language | Superseded requirements presented as current |

---

## 14. Related Concepts

- [10 — Portfolio Risk Mathematics](10_Portfolio_Risk_Mathematics.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [13 — Stress Testing](13_Stress_Testing.md) · [15 — Backtesting](15_Backtesting.md)
- [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR32.18` backtesting levels; `MAR33.3`–`MAR33.5`, `MAR33.12` ES, horizons, stress calibration |
| BCBS | *Amendment to the Capital Accord to incorporate market risks* | Jan 1996 | https://www.bis.org/publ/bcbs24.pdf | Historical VaR-based framework (superseded) |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR text |

*Accessed 25 August 2026.*
