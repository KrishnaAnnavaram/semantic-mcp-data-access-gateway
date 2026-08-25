# 22 — Counterparty Exposure, CVA and ISDA SIMM

**Level:** 10 · **Prerequisites:** [05](05_Credit_Spread_Risk.md), [17](17_FRTB_Standardised_Approach.md) · **Feeds:** [41](41_Market_Risk_vs_Related_Risk_Types.md)

> **Scope note.** This document sits at the boundary of market risk. **Counterparty credit risk is not market risk**, and **initial margin is not regulatory capital**. But derivative portfolios link all three, the exposure that drives CCR is itself market-driven, and CVA risk is capitalised under a framework adapted from the market risk SA. The purpose here is to establish the connections *and the boundaries* — not to reclassify everything as market risk.

---

## 1. Plain English

**When a bank has a derivative that is in the money, the counterparty owes it money. If that counterparty fails, the bank loses the amount owed.**

Three distinct questions follow, and they have three distinct answers:

| Question | Discipline | Framework |
|---|---|---|
| How much might they owe me in future? | **Counterparty credit risk** | SA-CCR / IMM (`CRE52`) |
| What is the value of that default risk, today, and how does it move? | **CVA risk** | **`MAR50`** |
| How much collateral must be posted up front against it? | **Initial margin** | **ISDA SIMM** (an industry methodology, not regulation) |

---

## 2. Banking example

A bank enters a 10-year interest rate swap with a corporate. The swap is currently worth **+$8 million** to the bank.

| Event | Consequence |
|---|---|
| Rates move; the swap is now worth **+$15m** | Counterparty exposure has **nearly doubled** without any new trade |
| The corporate's credit spread widens 100bp | The **CVA** rises — the bank's derivative is worth less on a fair-value basis, and that hits P&L today |
| The corporate defaults when owed $15m | The bank loses `(1 − Recovery) × $15m` |

> **Note what the first row means.** Counterparty exposure is a *market-driven* quantity. A CCR exposure profile is a function of rate volatility, curve shape and time — which is exactly why counterparty risk cannot be managed without market risk machinery, and exactly why the two are so often conflated.

---

## 3. The exposure vocabulary

| Term | Definition |
|---|---|
| **Mark-to-market (MtM)** | Current value of the derivative |
| **Positive exposure** | `max(MtM, 0)` — what you lose if they default **now** |
| **Negative exposure** | `min(MtM, 0)` — what **you** owe |
| **Current exposure (CE)** | Positive exposure after netting and collateral |
| **Expected exposure (EE)** | Expected positive exposure at a future date |
| **Expected positive exposure (EPE)** | Time-weighted average of EE over a horizon |
| **Effective EPE (EEPE)** | EPE with a non-decreasing floor, to handle rolling short-dated trades |
| **Potential future exposure (PFE)** | A high percentile (e.g. 95th or 99th) of exposure at a future date |
| **Peak PFE** | The maximum PFE across the profile |

### 3.1 The exposure profile

```
   Exposure
      │              ╭───────╮  ← PFE (high percentile)
      │           ╭──╯       ╰──╮
      │        ╭──╯   ╭────╮    ╰──╮
      │     ╭──╯   ╭──╯    ╰──╮    ╰──╮
      │  ╭──╯   ╭──╯          ╰──╮    ╰──╮   ← EE (expected)
      │──╯───╭──╯                ╰──╮    ╰────
      │      │                                 
      └──────┴─────────────────────────────────► time
             │                              maturity
        current exposure
```

**The characteristic hump** arises from two opposing forces:

1. **Diffusion** — the longer you wait, the further rates can have moved, so exposure grows.
2. **Amortisation** — as the swap approaches maturity, fewer cash flows remain, so exposure shrinks.

The peak sits where they cross — typically around **one-third to one-half** of the swap's life for a standard interest rate swap. **For an FX forward there is no amortisation**, so the profile grows monotonically to maturity — a structurally different and generally larger exposure per unit of notional.

---

## 4. Netting and collateral

### 4.1 Netting

Under an enforceable master netting agreement (typically an ISDA Master Agreement), exposures across all trades with a counterparty **net**:

```
   Exposure  =  max( Σ MtM_i , 0 )         with netting
   Exposure  =  Σ max( MtM_i , 0 )         without netting
```

**Worked example.** Three trades with one counterparty: +$20m, −$12m, +$5m.

```
   With netting     :  max(20 − 12 + 5, 0)  =  $13m
   Without netting  :  20 + 0 + 5           =  $25m
```

Netting nearly halves the exposure. **Its legal enforceability in the relevant jurisdiction is therefore a first-order capital question**, not a documentation detail, and jurisdictions where enforceability cannot be established are treated gross.

### 4.2 Collateral

| Type | Purpose | Timing |
|---|---|---|
| **Variation margin (VM)** | Covers the **current** MtM | Exchanged daily |
| **Initial margin (IM)** | Covers **potential future** exposure during the close-out period | Posted at inception, adjusted as risk changes |

**With daily VM, current exposure is close to zero.** What remains is the **margin period of risk (MPOR)** — the gap between the last successful margin call and completed close-out, during which the market keeps moving while no collateral arrives. IM exists to cover exactly that window.

> **The 2022 UK LDI episode was a collateral event, not a credit event.** Gilt yields rose, VM calls followed, and funds unable to meet them were forced to sell gilts, pushing yields higher and generating further calls. **Collateral converts credit risk into liquidity risk** — which is why margin is a market-risk topic and not merely an operational one.

---

## 5. CVA and the XVA family

### 5.1 CVA

**CVA is the market value of counterparty default risk on a derivative portfolio.**

```
              T
   CVA  =  −  ∫  LGD · EE(t) · dPD(t) · DF(t)
              0
```

In discretised form:

```
   CVA  ≈  LGD ·  Σ  EE(tᵢ) · [ PD(tᵢ₋₁, tᵢ) ] · DF(tᵢ)
                   i
```

**Worked example.** A netting set with EPE of $10m over 5 years, counterparty spread 200bp, recovery 40%.

Using the credit-triangle approximation `λ ≈ s/(1−R) = 0.02/0.6 = 3.33%` per annum:

```
   Cumulative 5y default probability  ≈  1 − e^(−0.0333 × 5)  =  15.35%
   CVA  ≈  0.60 × $10m × 0.1535  ≈  $0.92m
```

Roughly **$920,000** deducted from the fair value of a netting set with $10m of average exposure.

### 5.2 The family

| Adjustment | Reflects | Direction |
|---|---|---|
| **CVA** | Counterparty may default owing us | Reduces value |
| **DVA** | *We* may default owing them | Increases value (controversially — a bank books a gain as its own credit deteriorates) |
| **FVA** | Funding cost of uncollateralised exposure | Usually reduces |
| **MVA** | Cost of funding posted **initial margin** | Reduces |
| **ColVA** | Value of optionality in the CSA (currency, eligible collateral) | Either |
| **KVA** | Cost of regulatory capital held against the trade | Reduces |

### 5.3 Why CVA is a market risk problem

**CVA moves with market factors, not only with credit.**

```
   CVA  =  f( counterparty credit spread ,  EXPOSURE )
                                             │
                                             └── which is a function of
                                                 rates, FX, equity, commodity
                                                 levels and volatilities
```

A CVA desk therefore hedges **two** dimensions:

| Dimension | Hedged with |
|---|---|
| **Credit** — the counterparty's spread | Single-name CDS, index CDS |
| **Market** — the exposure driving the CVA | Rates, FX and other market instruments |

And it faces **cross-gamma**: the sensitivity of CVA to credit spread depends on the exposure level, and the sensitivity to market factors depends on the spread. **Wrong-way risk** — exposure rising *because* the counterparty's credit is deteriorating — is the extreme case, and it is genuinely hard to hedge.

---

## 6. Regulatory CVA capital — `MAR50`

**CVA risk is capitalised in its own framework, separate from trading-book market risk.**

| Field | Value |
|---|---|
| **Framework** | Credit valuation adjustment risk framework |
| **Jurisdiction** | Global (Basel standard) |
| **Regulator** | Basel Committee on Banking Supervision |
| **Consolidated Framework location** | **`MAR50`** |
| **Key publications** | *Review of the Credit Valuation Adjustment Risk Framework* (d325); *Credit Valuation Adjustment risk: targeted final revisions* (d488); *Targeted revisions to the credit valuation adjustment risk framework* (**d507**) |
| **Basel effective date** | **1 January 2023** |
| **Trading-book applicability** | Applies to CVA risk on derivatives and SFTs — **not** to trading-book positions themselves |
| **Latest verification** | 25 August 2026 |

### 6.1 The three approaches

| Approach | Who uses it | Character |
|---|---|---|
| **SA-CVA** | Banks with supervisory **approval** | **An adaptation of the market risk SA** — sensitivity-based, bucketed, correlation-aggregated |
| **BA-CVA** | Banks without SA-CVA approval | Simpler, formula-driven |
| **CCR proxy** | Banks with **less engagement in derivatives activities** | May choose to use their **CCR capital requirements as a proxy** for the CVA charge |

**BA-CVA has two variants:**

- a **reduced** version, for banks that do **not** actively hedge CVA risk;
- a **full** version, intended for banks that **do** actively hedge CVA risk.

> **Banks are free to choose their approach, but all banks must calculate the capital requirement under the reduced version of the BA-CVA.** The reduced figure functions as a common reference point — and, in the full BA-CVA, as a component of the calculation.

### 6.2 The targeted revisions (d507)

Compared with the earlier standard, the revisions include:

- **recalibrated risk weights**;
- a **different treatment for certain client-cleared derivatives**; and
- an **overall recalibration of both SA-CVA and BA-CVA**.

### 6.3 SA-CVA versus the market risk SBM

SA-CVA is *adapted from* the market risk SA, and the family resemblance is strong — but they are not the same calculation:

| | Market risk SBM (`MAR21`) | SA-CVA (`MAR50`) |
|---|---|---|
| What is measured | Sensitivity of **positions** | Sensitivity of **CVA** |
| Risk classes | Seven | Adapted set, including counterparty credit spread |
| Curvature | **Yes** | **No** — SA-CVA has delta and vega only |
| Hedges recognised | Within the framework's correlations | **Eligible CVA hedges only**, and the eligibility conditions are strict |
| Multiplier | None | A prescribed multiplier applies |
| Approval | None needed | **Supervisory approval required** |

> **The absence of curvature in SA-CVA is the structural difference worth remembering**, and the eligible-hedge restriction is the operationally painful one: a bank may hedge its CVA economically with instruments the framework does not recognise, and receive no capital relief for doing so.

---

## 7. Counterparty exposure measurement — SA-CCR

The exposure that CVA is computed on, and that CCR capital is held against, is itself a regulated calculation: **SA-CCR** (`CRE52` in the consolidated framework).

```
   EAD  =  alpha  ×  ( RC  +  PFE )
```

| Term | Meaning |
|---|---|
| **alpha** | A prescribed scaling factor |
| **RC** | Replacement cost — current exposure after netting and collateral |
| **PFE** | An add-on for potential future exposure, built from asset-class-specific add-ons with prescribed supervisory factors and a netting-set-level multiplier |

The **multiplier** recognises over-collateralisation and negative mark-to-market, reducing the add-on where the netting set is deeply out of the money or heavily collateralised.

**Internal Model Method (IMM)** remains available with supervisory approval, computing EEPE by simulation.

> **The point for a market risk reader:** whichever method is used, **the exposure input is a market-risk quantity.** It depends on rate volatility, curve shape, FX volatility and time to maturity. A CCR number is only as good as the market model beneath it.

---

## 8. Initial margin and ISDA SIMM

### 8.1 What SIMM is — and what it is not

**ISDA SIMM is an industry-standard methodology for calculating initial margin on non-cleared derivatives.** It exists so that two counterparties, computing IM independently, arrive at the same number and do not spend their time in dispute resolution.

> **SIMM is not a capital framework. It is not a regulatory requirement in itself. It is a methodology used to meet regulatory margin requirements.** Conflating SIMM with FRTB is one of the most common category errors in this area — they look alike and answer different questions for different purposes with different governance.

### 8.2 Current version

| Field | Value |
|---|---|
| **Current version** | **ISDA SIMM Methodology, version 2.8+2512** |
| **Published** | **12 June 2026** |
| **Effective date** | **11 July 2026** |
| **Calibration** | Full recalibration using historical data up to **31 December 2025** |
| **Preceding version** | v2.8+2506 — published 31 October 2025, effective 6 December 2025, calibrated to 30 June 2025 |
| **Cycle** | **Semiannual calibration**, introduced in 2025 |
| **Latest verification** | 25 August 2026 |

> **The move to semiannual recalibration in 2025 is a material operational change.** Version changes now arrive twice a year, each with a hard effective date on which every SIMM user must switch simultaneously. A firm that does not upgrade on the effective date will disagree with every counterparty that did.

### 8.3 Structure

SIMM uses a risk-based approach incorporating:

- **Delta risk**
- **Vega risk**
- **Curvature risk**
- **Inter-curve basis risk**
- **Credit base correlation risk**
- **Concentration risk**

> The margin for each risk class is **the sum of the Delta Margin, the Vega Margin, the Curvature Margin and the Base Correlation Margin** (where applicable) for that risk class.

Note that **concentration risk is an explicit component of SIMM** — it scales margin up where a position is large relative to defined concentration thresholds. **FRTB has no direct equivalent**; it addresses concentration indirectly through liquidity horizons. This is a genuine methodological difference, not a presentational one.

### 8.4 FRTB SBM versus ISDA SIMM

| | **FRTB SBM** | **ISDA SIMM** |
|---|---|---|
| **Purpose** | **Regulatory capital** | **Initial margin** on non-cleared derivatives |
| Who holds the number | The bank, as capital | Posted to a counterparty as collateral |
| Set by | Basel Committee | **ISDA** (industry body) |
| Legal status | Standard, implemented in law by jurisdictions | Methodology used to meet margin rules |
| Scope | The whole trading book | **Per netting set / counterparty** |
| Horizon | Liquidity horizons 10–120 days | **10-day** margin period of risk |
| Confidence | ES at 97.5% | Broadly 99%, per the margin rules' calibration |
| Components | Delta, vega, **curvature** | Delta, vega, **curvature**, base correlation |
| **Concentration** | **Not a separate component** | **Explicit component with thresholds** |
| Recalibration | On Basel revision | **Semiannual** |
| Correlation scenarios | **Three** (medium/high/low) | Single prescribed set |
| Default risk | **DRC, separate charge** | Not covered — SIMM is margin, not capital |

**The similarities are real** — both are sensitivity-based, bucketed and correlation-aggregated, and both were designed in the same post-crisis period from a common intellectual starting point. **The differences are what matter operationally:** they are calibrated differently, governed differently, updated on different cycles, and answer different questions. A sensitivity computed for one is not automatically fit for the other.

---

## 9. Wrong-way risk

**Wrong-way risk is exposure that increases as the counterparty's creditworthiness deteriorates.**

| Type | Definition | Example |
|---|---|---|
| **General** | Exposure correlates with general credit conditions | A receive-fixed swap with a corporate: rates fall in a recession, exposure rises, defaults rise |
| **Specific** | Exposure is **directly linked** to the counterparty's own credit | Buying protection on entity X **from** an entity closely tied to X; a repo collateralised by the counterparty's own bonds |

**Specific wrong-way risk is the dangerous one and receives punitive regulatory treatment** — the hedge fails precisely when it is needed, because the collateral and the counterparty fail together.

> The 2008 monoline experience is the reference case: banks held protection on structured credit written by insurers whose own solvency depended on that same structured credit performing. When the underlying deteriorated, the exposure rose and the protection writer's ability to pay fell — simultaneously, and for the same reason.

---

## 10. Where the boundaries actually lie

| Risk | Is it market risk? | Framework | Why |
|---|---|---|---|
| Trading book price moves | **Yes** | FRTB (`MAR20`–`MAR33`) | Loss from a price move |
| Counterparty default on a derivative | **No** — CCR | SA-CCR / IMM (`CRE52`) | Loss from a counterparty failing |
| **Change in the value of CVA** | **Market-driven, separately capitalised** | **`MAR50`** | Fair-value change from spread and exposure moves |
| Initial margin requirement | **No** — collateral | ISDA SIMM / margin rules | Not a loss; a collateral obligation |
| Funding cost of margin (MVA) | Valuation adjustment | Accounting / internal | Not separately capitalised as market risk |
| Banking book rate risk | **No** — IRRBB | `SRP31` (Pillar 2) | Different book, different framework |

> **The rule that resolves most classification disputes:** ask **what event causes the loss**. A *price* moving is market risk. A *counterparty failing* is credit risk. The *value of the adjustment for counterparty failure* moving is CVA risk. All three can arise from the same trade on the same day, and each is capitalised once, in its own framework. **Double-counting and gapping between frameworks are both real supervisory concerns.**

---

## 11. Pseudocode

```
FUNCTION exposure_profile(netting_set, market_model, time_grid, n_paths):
    profile = {}
    FOR t IN time_grid:
        values = []
        FOR p IN 1..n_paths:
            m_t = market_model.simulate(t, path = p)
            v   = sum(price(trade, m_t) for trade in netting_set.trades)
            v   = v - collateral_held(netting_set, t, m_t)      # VM
            values.append(max(v, 0))                            # POSITIVE exposure
        profile[t] = { "EE":  mean(values),
                       "PFE": percentile(values, 95) }
    epe  = time_weighted_average(profile, "EE")
    peak = max(profile[t]["PFE"] for t in time_grid)
    RETURN profile, epe, peak


FUNCTION cva(netting_set, exposure_profile, credit_curve, recovery, disc):
    lgd = 1 - recovery
    total = 0
    FOR i IN 1..len(time_grid):
        t0, t1 = time_grid[i-1], time_grid[i]
        pd_inc = survival(credit_curve, t0) - survival(credit_curve, t1)
        ee_mid = 0.5 * (exposure_profile[t0]["EE"] + exposure_profile[t1]["EE"])
        total += lgd * ee_mid * pd_inc * disc(t1)
    RETURN total


FUNCTION netting_benefit(trades):
    gross = sum(max(t.mtm, 0) for t in trades)
    net   = max(sum(t.mtm for t in trades), 0)
    RETURN { "gross": gross, "net": net, "benefit": gross - net }
    # NOTE: 'net' is only valid where the master netting agreement is
    # legally enforceable in the relevant jurisdiction.
```

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Netting enforceability** | Legal opinion held for every jurisdiction where netting is applied |
| 2 | **Collateral in the profile** | VM and IM correctly reflected in exposure |
| 3 | **MPOR** | Margin period of risk appropriate to the counterparty and product |
| 4 | **Profile shape** | Hump for amortising products; monotone growth for FX forwards |
| 5 | **CVA reconciles** | Front-office CVA and risk CVA agree to tolerance |
| 6 | **CVA sensitivities** | **Both** credit and market sensitivities computed |
| 7 | **Cross-gamma** | Credit × market cross-sensitivity captured |
| 8 | **Wrong-way risk** | Identified, flagged, and specifically treated |
| 9 | **BA-CVA reduced computed** | **Required of all banks**, whichever approach is used |
| 10 | **SA-CVA approval** | Supervisory approval in place if SA-CVA is used |
| 11 | **SA-CVA hedge eligibility** | Only eligible hedges recognised |
| 12 | **No curvature in SA-CVA** | Delta and vega only |
| 13 | **SIMM version current** | v2.8+2512 as at this document's date; effective **11 July 2026** |
| 14 | **SIMM upgrade discipline** | Version switched on the effective date, in step with counterparties |
| 15 | **SIMM concentration** | Concentration component implemented — it has no FRTB analogue |
| 16 | **No SIMM/FRTB conflation** | Sensitivities computed to each methodology's own specification |
| 17 | **Framework boundaries** | Each loss event capitalised once, in the correct framework |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Applying netting without an enforceable agreement | Exposure understated, sometimes by half (§4.1) |
| Ignoring the margin period of risk | IM requirement understated |
| Hedging CVA credit but not CVA market sensitivity | The larger sensitivity frequently left unhedged |
| Ignoring wrong-way risk | The hedge fails exactly when needed |
| Treating SIMM as a capital number | Category error — it is collateral, not capital |
| Reusing FRTB sensitivities for SIMM (or vice versa) | Different specifications; disputes with counterparties |
| Running a stale SIMM version | Disagreement with every counterparty on the current version |
| Skipping the reduced BA-CVA | It is required of all banks |
| Computing curvature under SA-CVA | Not part of the framework |
| Recognising ineligible CVA hedges | Overstates capital relief |
| Classifying CVA risk as trading-book market risk | Wrong framework; potential double-count |
| Assuming an FX forward profile humps | It does not amortise; exposure grows to maturity |

---

## 14. Limitations

- **Exposure modelling is simulation-heavy** and inherits every weakness of the market model beneath it.
- **CVA is model-dependent** to an unusual degree: two banks facing the same counterparty on the same portfolio will report different CVAs, driven by recovery assumptions, spread proxying and exposure modelling.
- **Most counterparties have no liquid CDS**, so the credit curve is a proxy — and the proxying problem of [05 §13](05_Credit_Spread_Risk.md) applies with full force.
- **Wrong-way risk is easier to describe than to model**, and the correlations involved are unstable and rarely well-evidenced.
- **DVA remains contested.** Booking a gain because one's own credit deteriorated is economically real and prudentially unhelpful, which is why the DVA component of fair value is deducted from CET1 and excluded from APL and HPL (`MAR32.26`).
- **SIMM parameters change semiannually**, so any SIMM figure quoted without a version and calibration date is not reproducible.

---

## 15. Related Concepts

- [05 — Credit Spread Risk](05_Credit_Spread_Risk.md) · [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [41 — Market Risk vs Related Risk Types](41_Market_Risk_vs_Related_Risk_Types.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | Consolidated Basel Framework — `MAR50` Credit valuation adjustment framework | ongoing | https://www.bis.org/basel_framework/chapter/MAR/50.htm | The CVA risk framework |
| BCBS | *Targeted revisions to the credit valuation adjustment risk framework* (d507) | 2020 | https://www.bis.org/bcbs/publ/d507.pdf | Recalibrated weights; client-cleared treatment; effective 1 Jan 2023 |
| BCBS | *Credit Valuation Adjustment risk: targeted final revisions* (d488) | 2019 | https://www.bis.org/bcbs/publ/d488.pdf | Preceding revision |
| BCBS | *Review of the Credit Valuation Adjustment Risk Framework* (d325) | 2015 | https://www.bis.org/bcbs/publ/d325.pdf | Original review |
| BIS FSI | *Counterparty credit risk in Basel III — Executive Summary* | ongoing | https://www.bis.org/fsi/fsisummaries/ccr_in_b3.htm | SA-CVA / BA-CVA / CCR-proxy approaches |
| ISDA | ISDA SIMM Methodology, version 2.8+2512 | **12 Jun 2026**, effective **11 Jul 2026** | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ | Current SIMM version and calibration |
| ISDA | ISDA SIMM Methodology, version 2.8+2506 | 31 Oct 2025, effective 6 Dec 2025 | https://www.isda.org/2025/10/31/isda-publishes-isda-simm-methodology-version-2-8-2506/ | Preceding version; semiannual cycle |

*Accessed 25 August 2026.*
