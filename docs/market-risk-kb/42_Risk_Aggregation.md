# 42 — Risk Aggregation

**Level:** 13 · **Prerequisites:** [10](10_Portfolio_Risk_Mathematics.md), [21](21_Market_Risk_Limits.md) · **Feeds:** [28](28_Reporting_and_Dashboards.md), [43](43_Daily_Workflow.md)

> **Aggregation is where a thousand desk-level numbers become one firm-level number — and where the most consequential assumption in market risk lives: how much diversification to believe in.**

---

## 1. The aggregation hierarchy

```
   TRADE
     └─► POSITION
           └─► RISK FACTOR            ◄── the only level where SUMMING is exact
                 └─► TENOR / BUCKET
                       └─► CURRENCY
                             └─► RISK CLASS
                                   └─► BOOK
                                         └─► TRADING DESK       ◄── MAR12 unit
                                               └─► BUSINESS LINE
                                                     └─► DIVISION
                                                           └─► LEGAL ENTITY  ◄── capital
                                                                 └─► REGION
                                                                       └─► GROUP
```

**Also aggregated across non-hierarchical dimensions:** issuer, sector, country, counterparty, product type. These **overlap** with the organisational hierarchy — the same position appears in both — which is why [37 §4.1](37_Calculation_Dependency_Graph.md) flags double-counting as an aggregation failure mode.

---

## 2. The four aggregation methods

| Method | Formula | When correct | Diversification |
|---|---|---|---|
| **Simple summation** | `Σ xᵢ` | Same risk factor, same units; or where the framework mandates it | **None** |
| **Netting** | `Σ xᵢ` with signs | Offsetting exposures to the **same** factor | Full, within the factor |
| **Correlation aggregation** | `√(Σx² + ΣΣρxᵢxⱼ)` | Different factors with an estimable correlation | Partial |
| **Prescribed aggregation** | Regulatory formula | Regulatory capital | **As prescribed, not as estimated** |

### 2.1 When each applies

```
   Same risk factor, same tenor, same currency   ──►  NET (exact)
   Different tenors, same curve                  ──►  CORRELATION (ρ from MAR21.46 or estimated)
   Different currencies                          ──►  CORRELATION (γ = 50% under SBM)
   Different risk classes                        ──►  CORRELATION (constrained under IMA at ρ = 0.5)
   SBM vs DRC vs RRAO                            ──►  SIMPLE SUM (MAR20.4 — mandated)
   DRC across buckets                            ──►  SIMPLE SUM (MAR22.26 — mandated)
   CSR bucket 16 within-bucket                   ──►  SUM OF ABSOLUTES (MAR21.56 — mandated)
   Non-CTP securitisation across buckets 1-24    ──►  γ = 0% (MAR21.70 — mandated)
```

> **The four mandated no-offset cases are the framework making a judgement, not a simplification.** Basel is declining to grant diversification precisely where it doubts the correlation would hold — between capital components, across default buckets, within unclassifiable exposures, and across securitisation buckets.

---

## 3. The netting rule

**Netting is exact only for the same risk factor.**

`MAR21.4(2)` is explicit: sensitivities to the same risk factor must be netted *"irrespective of the instrument from which they derive."* Basel's own example — two Euribor swaps with the same fixed rate and notional but opposite direction produce **zero** GIRR.

**What must never be netted:**

| Never net | Why |
|---|---|
| **DV01 across currencies** | USD and JPY rate risk are different risks; the sum has no meaning |
| **DV01 and CS01** | Different factors; hedged with different instruments |
| **Rate risk across different curves at the same tenor** | ρ = 99.90%, not 100% (`MAR21.45`) |
| **Cross-currency basis against the yield curve** | ρ = **0%** (`MAR21.50`) |
| **JTD across obligors** | Only same-obligor netting is permitted (`MAR22.9`) |
| **Vega across expiries** | Term-structure positions vanish |
| **Positions in different legal entities** | Capital is required at entity level |

---

## 4. Correlation aggregation — worked example

### 4.1 Desk-level VaRs

| Desk | 99% 1-day VaR ($m) |
|---|---|
| USD Rates | 8.20 |
| Credit Flow | 4.90 |
| EM Rates | 3.10 |
| FX | 2.40 |
| Equity | 1.80 |
| **Simple sum** | **20.40** |

### 4.2 Correlation matrix

| | Rates | Credit | EM | FX | Equity |
|---|---|---|---|---|---|
| **USD Rates** | 1.00 | 0.45 | 0.55 | 0.20 | 0.25 |
| **Credit Flow** | 0.45 | 1.00 | 0.50 | 0.15 | 0.40 |
| **EM Rates** | 0.55 | 0.50 | 1.00 | 0.35 | 0.30 |
| **FX** | 0.20 | 0.15 | 0.35 | 1.00 | 0.20 |
| **Equity** | 0.25 | 0.40 | 0.30 | 0.20 | 1.00 |

### 4.3 The aggregate

```
   Firm VaR  =  √( xᵀ R x )  =  $15.010m

   Simple sum                =  $20.400m
   Diversification benefit   =   $5.390m   (26.4%)
   Diversification ratio     =    0.7358
```

### 4.4 Risk contribution

| Desk | VaR ($m) | MCR | **Component ($m)** | **% of firm risk** | % of standalone sum |
|---|---|---|---|---|---|
| USD Rates | 8.20 | 0.8688 | **7.124** | **47.5%** | 40.2% |
| Credit Flow | 4.90 | 0.7475 | **3.663** | **24.4%** | 24.0% |
| EM Rates | 3.10 | 0.7622 | **2.363** | **15.7%** | 15.2% |
| FX | 2.40 | 0.4144 | **0.995** | **6.6%** | 11.8% |
| Equity | 1.80 | 0.4810 | **0.866** | **5.8%** | 8.8% |
| | **20.40** | | **15.010** ✓ | **100.0%** | 100% |

**Components sum exactly to the firm VaR** — the Euler identity of [10 §6.2](10_Portfolio_Risk_Mathematics.md). ✓

### 4.5 What the contributions reveal

**USD Rates is 40% of the standalone sum and 47.5% of the actual risk.** It is *more* important than its size suggests, because it is highly correlated with the two next-largest desks (0.45 with Credit, 0.55 with EM). Its risk barely diversifies away.

**FX is 11.8% of the standalone sum and 6.6% of the actual risk.** It is *less* important than its size suggests, because its correlations are low (0.15–0.35). **FX is doing genuine diversification work for this firm.**

> **This is the number that should drive limit allocation, not standalone VaR.** A framework allocating limits by standalone size would over-constrain FX and under-constrain rates — precisely inverted relative to their contribution to firm risk.

### 4.6 Incremental VaR — a different question

| Desk | **Incremental** VaR ($m) | Component ($m) |
|---|---|---|
| USD Rates | 6.140 | 7.124 |
| Credit Flow | 3.205 | 3.663 |
| EM Rates | 2.204 | 2.363 |
| FX | 0.825 | 0.995 |
| Equity | 0.778 | 0.866 |
| **Sum** | **13.152** | **15.010** |

**Incremental VaR is what firm VaR would fall by if the desk were removed entirely.** It is systematically **smaller** than component contribution, and **the incrementals do not sum to the total** ($13.152m vs $15.010m).

| Measure | Question it answers | Sums to total? |
|---|---|---|
| **Marginal** | What if I add a *little* more? | No |
| **Component** | What share of *current* risk is this? | **Yes** |
| **Incremental** | What if I removed it *entirely*? | No |

**Use component for allocation. Use incremental for "should we exit this business?" Use marginal for "where should we trim at the edge?"** Three questions, three answers, routinely confused.

---

## 5. The correlation assumption is the whole game

### 5.1 The sensitivity

| Correlation assumption | Firm VaR | vs base |
|---|---|---|
| All ρ = 0 (independent) | **$10.481m** | **−30.2%** |
| **As estimated (§4.2)** | **$15.010m** | — |
| All ρ = 1 (perfectly correlated) | **$20.400m** | **+35.9%** |

**Firm VaR ranges from $10.48m to $20.40m — a factor of 1.95 — with no change in any position and no change in any desk's VaR.** The entire spread comes from the correlation assumption.

### 5.2 Why the upper case matters

**In a systemic crisis, correlations converge toward 1** — and the diversification benefit computed in calm conditions evaporates precisely when the loss is largest. A portfolio sized to its diversified risk in normal times is over-sized for a crisis.

This is not a theoretical caveat; it is the observed behaviour of every major crisis, and it is why:

| Mechanism | What it does |
|---|---|
| **SBM three correlation scenarios** (`MAR21.6`–`21.7`) | Runs medium, high and low; **takes the worst** |
| **IMA constrained aggregation** (`MAR33.14`–`33.15`) | Weights unconstrained ES against summed partial ES at **ρ = 0.5** |
| **SBM/DRC/RRAO simple sum** (`MAR20.4`) | No cross-component diversification at all |
| **DRC cross-bucket simple sum** (`MAR22.26`) | No offset between corporates, sovereigns and municipals |
| **SES ρ = 0.6** (`MAR33.17`) | NMRFs never receive the diversification modellable factors do |
| **Correlation-breakdown stress** | Explicit internal scenario |

> **`MAR33.15`'s ρ = 0.5 is the most direct statement of the regulatory position: the framework takes a bank's cross-asset diversification claim at exactly half face value.** Half the capital is computed as the model says; half as though no cross-class diversification existed.

---

## 6. Aggregation across legal entities

**Legal entity aggregation is not the same as economic aggregation.**

| Issue | Consequence |
|---|---|
| **Capital is required at entity level** | Diversification across entities is not available for entity capital |
| **Different rulebooks** | An EU subsidiary and a US branch face different calibrations ([29](29_Regulatory_Framework.md)) |
| **Ring-fencing** | Capital in one entity may not be fungible to another |
| **Different reporting dates** | Entity and group returns may not align |

**The same position is therefore frequently capitalised more than once** — at entity level under local rules, and at group level under consolidated rules. That is not double-counting in the error sense; it is the intended consequence of entity-level supervision.

---

## 7. Aggregating different measures

**Some things cannot be aggregated at all.**

| Combination | Aggregable? | Why |
|---|---|---|
| VaR + VaR (same confidence, same horizon) | **Yes**, with correlation | Same measure |
| VaR (99%) + VaR (97.5%) | **No** | Different measures — rescale first |
| VaR (1-day) + VaR (10-day) | **No** | Different horizons |
| VaR + ES | **No** | Different measures entirely |
| VaR + stress loss | **No** | One has a probability; the other does not |
| DV01 (USD) + DV01 (JPY) | **No** | Different risk factors |
| DV01 + CS01 | **No** | Different factors, different hedges |
| SBM + DRC + RRAO | **Yes — by simple sum only** | `MAR20.4` mandates it |
| Sensitivities across desks, same factor | **Yes**, by netting | Exact |

> **The VaR + stress row is the one most often violated in management reporting.** A firm VaR of $15m and a stress loss of $88m cannot be added, averaged, or presented as a range. They answer different questions with different epistemic status ([13 §2](13_Stress_Testing.md)), and presenting them together requires saying so.

---

## 8. Pseudocode

```
FUNCTION aggregate(measures, correlation_matrix, method):
    IF method == "SIMPLE_SUM":
        RETURN sum(measures.values())

    IF method == "NET":
        # Valid ONLY within the same risk factor, tenor and currency
        ASSERT all_same_factor(measures)
        RETURN sum(measures.values())          # signed

    IF method == "CORRELATION":
        ASSERT is_positive_semidefinite(correlation_matrix)
        x = list(measures.values())
        q = sum(x[i]*x[j]*correlation_matrix[i][j]
                for i in range(len(x)) for j in range(len(x)))
        RETURN sqrt(max(q, 0))


FUNCTION risk_contributions(measures, correlation_matrix):
    x     = list(measures.values())
    total = aggregate(measures, correlation_matrix, "CORRELATION")
    out   = {}
    FOR i IN range(len(x)):
        cov_ip = sum(x[j]*correlation_matrix[i][j] for j in range(len(x)))
        mcr    = cov_ip / total
        out[i] = { "marginal": mcr,
                   "component": x[i]*mcr,
                   "pct": x[i]*mcr/total }
    ASSERT abs(sum(o["component"] for o in out.values()) - total) < tolerance
    RETURN out


FUNCTION roll_up(positions, hierarchy, measure_fn):
    results = {}
    FOR level IN hierarchy.levels_bottom_up():
        FOR node IN level.nodes:
            children = node.children
            IF node.is_leaf:
                results[node] = measure_fn(positions_in(node))
            ELSE:
                # Recompute from POSITIONS where possible; correlation-aggregate
                # child results only where full revaluation is infeasible.
                results[node] = ( measure_fn(positions_in(node))
                                  IF can_recompute(node)
                                  ELSE aggregate({c: results[c] for c in children},
                                                 correlation_for(node),
                                                 "CORRELATION") )
            # Diversification can never be negative
            ASSERT results[node] <= sum(results[c] for c in children) + tolerance
    ASSERT no_position_counted_twice(hierarchy, positions)
    RETURN results
```

> **Prefer recomputation from positions over aggregating children.** Correlation-aggregating desk VaRs is an approximation; revaluing the combined portfolio against the same scenario set is exact. Use the approximation only where full revaluation is genuinely infeasible, and say which was used.

---

## 9. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Netting scope** | Only within the same factor, tenor and currency |
| 2 | **No cross-currency DV01 sum** | Anywhere in the reporting chain |
| 3 | **Diversification bound** | Aggregate ≤ sum of children, always |
| 4 | **Euler identity** | `Σ` components = total |
| 5 | **PSD** | Correlation matrix valid; repairs logged |
| 6 | **No double-counting** | Overlapping hierarchies reconciled |
| 7 | **Measure compatibility** | Same confidence, horizon and measure before aggregating |
| 8 | **VaR and stress kept separate** | Never summed or averaged |
| 9 | **Mandated no-offset cases** | SBM+DRC+RRAO; DRC buckets; CSR 16; non-CTP γ=0% |
| 10 | **SBM three scenarios** | Maximum taken |
| 11 | **IMCC ρ = 0.5** | Constrained/unconstrained weighting correct |
| 12 | **SES ρ = 0.6** | Not confused with the IMCC weight |
| 13 | **Recompute vs aggregate** | Method recorded per node |
| 14 | **Entity-level capital** | No cross-entity diversification claimed |
| 15 | **Correlation sensitivity reported** | The ρ=0 / ρ=1 range shown to management |

---

## 10. Common errors

| Error | Consequence |
|---|---|
| Summing DV01 across currencies | A meaningless aggregate presented as a risk number |
| Netting DV01 against CS01 | Both risks disappear from the report |
| Aggregating VaR at different confidence levels | Numerically wrong; conceptually meaningless |
| Adding VaR and stress loss | Combines a probabilistic and a non-probabilistic quantity |
| Using **marginal** contribution for allocation | Contributions do not sum; allocation is arbitrary |
| Using **incremental** where component is meant | Systematically understates, and does not sum |
| Overlapping hierarchies not reconciled | Firm risk overstated by double-counting |
| Diversifying across legal entities for entity capital | Capital is not fungible |
| Silently repairing a non-PSD matrix | Undisclosed model change |
| Applying diversification where Basel mandates a simple sum | Understates capital; non-compliant |
| Reporting only the base correlation case | Management never sees the ρ→1 outcome |

---

## 11. Limitations

- **Correlation aggregation of child VaRs is an approximation.** It assumes the aggregate distribution is adequately described by pairwise linear correlation, which is false in the tail — exactly where the number is used.
- **Correlation captures only linear dependence.** Tail dependence — the tendency to move together *in extremes* — is not measured by ρ and is what actually matters in a crisis.
- **Estimation error grows as n².** For a realistic desk count the correlation matrix is poorly conditioned and often requires repair.
- **Diversification is a statement about a past sample.** It is not a property of the portfolio, and it is least reliable when most needed.
- **Regulatory aggregation is prescribed, not estimated.** A bank's own diversification analysis has no effect on SBM correlations, DRC bucket summation, or the IMCC weighting.

---

## 12. Related Concepts

- [10 — Portfolio Risk Mathematics](10_Portfolio_Risk_Mathematics.md) — the underlying mathematics
- [21 — Market Risk Limits](21_Market_Risk_Limits.md) — how contributions drive limit allocation
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)
- [28 — Reporting and Dashboards](28_Reporting_and_Dashboards.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR20.4`, `MAR21.4`–`21.7`, `MAR21.56`, `MAR21.70`, `MAR22.26`, `MAR33.14`–`33.17` |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Aggregation accuracy and completeness |

> **Note on sourcing.** The correlation matrix and desk VaRs in §4 are constructed for exposition and are not market data. The mandated aggregation rules are regulatory and cited to paragraph.

*Accessed 25 August 2026.*
