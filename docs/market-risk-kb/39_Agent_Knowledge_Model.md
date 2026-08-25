# 39 — Agent Knowledge Model

**Level:** Design · **Prerequisites:** [31](31_Master_Calculation_Catalog.md), [33](33_Master_Risk_Factor_Catalog.md), [37](37_Calculation_Dependency_Graph.md), [38](38_Question_to_Calculation_Catalog.md)

> **This document maps domain concepts, not software.** It describes the knowledge structure an AI market-risk system must hold in order to reason correctly: the intents, the resolution chain from question to answer, the parameters that must be elicited, and — most importantly — **the boundary between what can be computed and what must be refused.**
>
> Architecture, protocols and implementation belong elsewhere. If domain modelling is skipped and software is designed first, the result is a system that answers confidently and wrongly, which is worse than one that answers nothing.

---

## 1. The resolution chain

Every market-risk question resolves through the same seven stages. **A question that cannot complete all seven cannot be answered, and the correct response is to say which stage failed.**

```
   USER QUESTION
        │
   [1]  ▼  INTENT           what kind of question is this?
        │
   [2]  ▼  METRIC           which calculation answers it?
        │
   [3]  ▼  SCOPE            whose positions? which book, desk, entity, date?
        │
   [4]  ▼  PARAMETERS       confidence? horizon? tenor? scenario? currency?
        │
   [5]  ▼  DATA             which positions, curves, surfaces, histories?
        │
   [6]  ▼  COMPUTE          the calculation, with its stated conventions
        │
   [7]  ▼  EXPLAIN          the number, its units, its caveats, its provenance
```

**Stage 7 is not optional decoration.** A market-risk number without its confidence level, horizon, convention and caveat is not an answer — it is a number that will be misread. See §7.

---

## 2. The worked intent — the canonical example

> **User question:** *"What is my 10-year Treasury rate risk?"*

```
   [1] INTENT             Interest Rate Risk → point-on-curve exposure

   [2] METRIC             10Y Key-Rate DV01           (IR-07)
                          NOT total DV01 — the question names a curve point

   [3] SCOPE              which book? which legal entity? as of which date?
                          → ELICIT if not stated

   [4] PARAMETERS         key-rate node set (must match the curve build)
                          bump size (1bp), central difference
                          sign convention (positive = long duration)

   [5] DATA               positions:    Treasury holdings in scope
                          market data:  USD risk-free curve, all nodes
                          reference:    schedules, day counts, calendars

   [6] COMPUTE            tent bump ±1bp at the 10Y node, tapering to zero
                          at adjacent key rates
                          FULL revaluation of every position
                          KRD01(10Y) = [P(tent−1bp) − P(tent+1bp)] / 2
                          CHECK: Σ KRD01 over all nodes = parallel DV01

   [7] EXPLAIN            "$162,320 per basis point.
                           A 1bp rise around the 10-year part of the curve
                           costs the book $162,320.
                           This is 49% of total DV01 ($329,783/bp) — the
                           book's largest single concentration.
                           Caveat: the bucket split depends on the curve's
                           interpolation scheme; the total does not."
```

**Three things that example does that a naive implementation would not:**

1. **It distinguishes "10-year rate risk" from "total rate risk."** The question named a curve point; total DV01 would be a wrong answer to a right question.
2. **It runs the completeness check** before reporting.
3. **It states the interpolation caveat**, because that is what makes the number non-comparable across institutions.

---

## 3. The intent taxonomy

| Intent | Trigger phrasing | Primary metric | Elicit if missing |
|---|---|---|---|
| **RATE_EXPOSURE** | "rate risk", "if rates rise", "duration" | DV01, KRD01 | scope, curve point, currency |
| **CURVE_SHAPE** | "steepener", "flattener", "2s10s", "butterfly" | KRD ladder + curve scenario | tenor pair, shock size |
| **CREDIT_EXPOSURE** | "spread risk", "if spreads widen" | CS01, bucketed CS01 | scope, issuer/sector, tenor |
| **DEFAULT_EXPOSURE** | "if X defaults", "jump to default" | JTD, DRC | obligor, recovery assumption |
| **FX_EXPOSURE** | "currency exposure", "if the dollar strengthens" | NOP, FX delta | currency, structural inclusion |
| **EQUITY_EXPOSURE** | "equity risk", "net long" | Delta, net/gross, beta-adjusted | index vs single name |
| **COMMODITY_EXPOSURE** | "oil exposure", "curve position" | Delta by month, basis | commodity, delivery month, location |
| **VOLATILITY_EXPOSURE** | "if vol rises", "vega" | Vega bucketed | expiry, strike/moneyness |
| **CONVEXITY** | "large moves", "gamma", "convexity" | Gamma, convexity, spot×vol grid | shock range |
| **TAIL_LOSS** | "how much could we lose", "worst case" | VaR **and** ES | confidence, horizon |
| **TAIL_SEVERITY** | "beyond VaR", "in the tail" | **ES** | confidence |
| **CRISIS_LOSS** | "if 2008 happened", "in a crisis" | Stress (named, dated scenario) | which scenario |
| **REVERSE_STRESS** | "what would it take to lose X" | Reverse stress | target loss |
| **PNL_EXPLAIN** | "why did we lose money" | P&L attribution | date, desk |
| **MODEL_QUALITY** | "is the model working" | Backtesting, PLA | desk, period |
| **CAPITAL** | "what capital", "RWA", "FRTB" | SA and/or IMA | approach, scope, date |
| **LIMIT_STATUS** | "are we within limits", "headroom" | Utilisation, breaches | scope |
| **PRE_TRADE** | "can I do this trade" | Pre-trade limit check | full trade terms |
| **CONCENTRATION** | "biggest exposure", "concentrated" | Top-N by contribution | dimension (issuer/factor/country) |
| **COMPARISON** | "why is X different from Y" | Convention reconciliation | both conventions |
| **DEFINITION** | "what is", "explain" | — (knowledge retrieval) | — |

---

## 4. Intent → data requirement map

```
   INTENT               POSITIONS   MARKET DATA        HISTORY   REFERENCE
   ─────────────────────────────────────────────────────────────────────────
   RATE_EXPOSURE           ●        curve                —        schedules
   CURVE_SHAPE             ●        curve (all nodes)    —        schedules
   CREDIT_EXPOSURE         ●        spread curve         —        issuer, rating
   DEFAULT_EXPOSURE        ●        MV, recovery         —        seniority, LGD
   FX_EXPOSURE             ●        spot, both curves    —        currency
   EQUITY_EXPOSURE         ●        spot, dividend, repo   β       sector, cap
   VOLATILITY_EXPOSURE     ●        vol surface (2-D)    —        expiry schedule
   CONVEXITY               ●        curve/surface        —        —
   TAIL_LOSS               ●        current levels       ●●●      factor mapping
   CRISIS_LOSS             ●        current + shock      ●●●      factor mapping
   REVERSE_STRESS          ●        covariance           ●●       factor mapping
   PNL_EXPLAIN             ● (t-1 and t)  two snapshots  —        trade activity
   MODEL_QUALITY           —        —                    ●●●      desk definition
   CAPITAL                 ●        curves, surfaces     ● (ES)   buckets, weights
   LIMIT_STATUS            ●        as per metric        —        limit definitions
   PRE_TRADE               ● + proposed  current         —        limits
   ─────────────────────────────────────────────────────────────────────────
   ●●● = long history required   ●● = moderate   ● = required   — = not required
```

> **The `HISTORY` column is the one that determines feasibility.** An agent with live positions and current market data can answer every exposure question. It **cannot** answer a VaR, ES or stress question without a factor history, and it must say so rather than approximate.

---

## 5. Parameters that must be elicited, never assumed

**Every one of these changes the answer materially.** An agent that silently defaults them produces a number the user will misinterpret.

| Parameter | Why it cannot be defaulted | Example of the consequence |
|---|---|---|
| **Confidence level** | 97.5% and 99% ES differ by ~20% | A limit comparison becomes meaningless |
| **Horizon** | 1-day and 10-day differ by ~3.2× | Off by a factor of three |
| **Scope** | Desk, book, entity, firm are different portfolios | Answering about the wrong book |
| **As-of date** | Positions and markets change daily | Yesterday's answer to today's question |
| **Currency** | DV01 must never be summed across currencies | A meaningless aggregate |
| **Tenor / curve point** | "Rate risk" vs "10-year rate risk" | Total DV01 answered instead of KRD |
| **Scenario** | "A crisis" is not a scenario | Unreproducible, uncomparable |
| **Sign convention** | Positive DV01 means opposite things in two houses | Hedge in the wrong direction |
| **Quantile convention** | Round up / down / interpolate | Up to 13% VaR difference ([11 §4.5](11_VaR.md)) |
| **Vol convention** | Normal (bp) vs lognormal (%) | **Order-of-magnitude** error |
| **Which "duration"** | Macaulay, modified or effective | Wrong by the compounding factor, or wrong entirely for callables |
| **SA or IMA** | Different frameworks, different numbers | Comparing incomparable capital |

**Elicitation should be one question with real options**, not an open prompt:

> *"Which confidence level — 97.5% (the FRTB ES basis) or 99% (the common internal VaR basis)?"*

rather than *"What confidence level?"* — because the options carry the context that makes the choice meaningful.

---

## 6. The boundary — what must be refused

> **This is the most important section in the document.** An agent that computes when it should refuse is more dangerous than one that refuses too often, because a fabricated number carries the same authority as a real one.

### 6.1 Refuse and explain — data absent

| Situation | Correct response |
|---|---|
| No position data for the requested scope | *"I don't have positions for that book."* — **never** compute on a proxy portfolio |
| No factor history | *"I can compute exposure but not VaR — that needs a factor history I don't have."* |
| Valuation failed | *"That position did not price; I've escalated it. The reported figure excludes it and is therefore incomplete."* — **never** default it to zero |
| Factor unmapped in a stress scenario | Report the result **with the unmapped count**, explicitly |
| Market data stale or proxied | Report **with the proxy flagged**, not silently |

### 6.2 Refuse — outside the domain

| Request | Why refused |
|---|---|
| Compute CVA with no counterparty exposure data | It is a different framework requiring data the market-risk domain does not hold |
| Compute IRRBB EVE from trading-book data | Different book, different framework ([20A](20A_Trading_Book_Boundary_and_IRRBB.md)) |
| Compute regulatory capital for a jurisdiction whose rules are **proposed** | The US market risk rules are **not final** ([29 §1.4](29_Regulatory_Framework.md)) |
| Produce a stress shock magnitude not traceable to data | **Fabrication.** [13 §4.1](13_Stress_Testing.md) |

### 6.3 Answer, but caveat hard

| Situation | Required caveat |
|---|---|
| Sensitivity-based estimate for a large shock | *"This is a first-order estimate; at this shock size the error can exceed 14%"* ([30 §4.2](30_Worked_Examples.md)) |
| VaR on a book with material optionality | *"Delta-normal VaR understates non-linear risk; a full-revaluation figure would differ"* |
| Any figure on a proxy-mapped issuer | *"This issuer is mapped to a sector proxy; idiosyncratic risk is not represented"* |
| Historical VaR where the window contains no stress | *"The lookback contains no stress period; this understates crisis risk"* |
| A pegged-currency exposure | *"Historical volatility is near zero because the rate is managed; this is scenario territory, not simulation"* |
| A number derived from a model price | *"Model-implied, not an executable price"* |

### 6.4 The three rules

```
   1.  ABSENCE IS NOT ZERO.
       A missing position, a failed valuation, an unmapped factor and a
       stale price are each UNKNOWN. Reporting them as zero removes both
       the value and the risk, and nothing downstream can tell.

   2.  A NUMBER WITHOUT ITS CONVENTION IS NOT A NUMBER.
       Confidence, horizon, currency, sign, quantile rule, vol basis.
       State them or do not state the number.

   3.  NEVER FABRICATE A MARKET OBSERVATION.
       A stress shock, a historical move, a risk weight, a correlation —
       if it cannot be traced to data or to a cited paragraph of the
       standard, it must not be produced.
```

---

## 7. The answer contract

An agent's response should carry six elements. Anything less will be misread.

```
   ANSWER
     value              the number
     unit               currency/bp · currency · % · years · ratio
     scope              which book, desk, entity
     as_of              business date
     conventions        confidence · horizon · sign · quantile rule · method
     provenance         which curves, which model version, which scenario set
     caveats            what this number does NOT say
     completeness       positions included/excluded; proxies; unmapped factors
```

**Worked example of a complete answer:**

> **$4,058,486.**
> 99% one-day Value at Risk, USD Rates desk, as of 24 August 2026.
> Historical simulation, 250 scenarios, full revaluation, **round-up quantile convention** (3rd worst observation).
> Curve: `USD.SOFR.OIS`, build version BOOT-2026.3. All 250 scenarios present.
> **Caveats:** VaR is a quantile, not a maximum — losses exceed it on roughly 2.5 days a year by design. It says nothing about how bad those days are; **97.5% ES for the same book is $4,861,741**, a ratio of 1.198, which indicates a materially fat tail. The worst single scenario (−$9.86m) is 2.4× the second worst.

**Compare with what a naive agent would say:** *"Your VaR is $4.06 million."* Same number; a fraction of the information; and every one of the ways it can be misused is left open.

---

## 8. Knowledge the agent must hold

| Knowledge type | Content | Source in this library |
|---|---|---|
| **Calculation definitions** | What each metric is, its formula, its units | [31](31_Master_Calculation_Catalog.md), [32](32_Master_Formula_Handbook.md) |
| **Risk factor ontology** | What each factor is; shock convention; instrument mapping | [33](33_Master_Risk_Factor_Catalog.md) |
| **Dependency structure** | What must be computed before what | [37](37_Calculation_Dependency_Graph.md) |
| **Intent mappings** | Question → calculation | [38](38_Question_to_Calculation_Catalog.md) |
| **Conventions** | Sign, quantile, vol basis, day count, compounding | [32](32_Master_Formula_Handbook.md), [34](34_Glossary.md) |
| **Caveats** | What each metric does not say | Every document's Limitations section |
| **Regulatory parameters** | Risk weights, correlations, thresholds — **cited to paragraph** | [17](17_FRTB_Standardised_Approach.md)–[20](20_NMRF_and_Modellability.md) |
| **Regulatory status** | What is in force where, and what is only proposed | [29](29_Regulatory_Framework.md) |
| **Refusal boundaries** | What it must not compute | §6 above |

> **Every regulatory parameter must carry its citation.** An agent that states "the GIRR 10-year risk weight is 1.1%" without `MAR21.42` cannot be audited, and cannot be corrected when the calibration changes — which it does, by jurisdiction ([29 §1.2](29_Regulatory_Framework.md)).

---

## 9. Failure modes specific to automated reasoning

| Failure mode | Mechanism | Mitigation |
|---|---|---|
| **Confident fabrication** | Producing a plausible risk weight or shock magnitude from pattern rather than source | Every regulatory number cites a paragraph; every shock traces to data |
| **Silent default** | Filling an unelicited parameter with a convention the user does not share | §5 — elicit, never assume |
| **Wrong-granularity answer** | Answering "rate risk" with total DV01 when a curve point was named | Intent taxonomy distinguishes RATE_EXPOSURE from CURVE_SHAPE |
| **Stale-parameter recall** | Citing SR 11-7, or a pre-2024 IRRBB shock, or an old SIMM version | Status tracker with verification dates ([29](29_Regulatory_Framework.md)) |
| **Framework confusion** | Treating SIMM as capital, or CVA as trading-book market risk | Boundary table ([22 §10](22_Counterparty_CVA_and_SIMM.md)) |
| **Aggregating incomparables** | Summing DV01 across currencies; summing sub-portfolio VaRs | Unit and scope checks before aggregation |
| **Caveat omission** | Correct number, no context, predictable misreading | §7 answer contract |
| **Zero-for-unknown** | Missing data treated as zero exposure | §6.4 rule 1, enforced at the data layer |

---

## 10. Design principles

```
   1.  MAP THE DOMAIN BEFORE THE SOFTWARE.
       Intents, metrics, parameters, conventions and refusal boundaries
       are domain facts. They do not change when the architecture does.

   2.  MAKE THE CHAIN EXPLICIT.
       Intent → metric → scope → parameters → data → compute → explain.
       A question that cannot complete the chain gets told WHICH STAGE FAILED.

   3.  ELICIT WITH REAL OPTIONS.
       "97.5% (FRTB ES basis) or 99% (internal VaR basis)?" — not
       "what confidence level?"

   4.  CARRY PROVENANCE THROUGH EVERY ANSWER.
       Curve version, model version, scenario set, as-of date.
       An unreproducible number is not an auditable number.

   5.  THE CAVEAT IS PART OF THE ANSWER.
       Not an appendix, not a disclaimer — the sentence that stops the
       number being misused.

   6.  REFUSE CLEANLY AND SAY WHY.
       "I don't have a factor history for that book, so I can compute
       exposure but not VaR" is a good answer. A plausible number is not.
```

---

## 11. Limitations

- **This is a knowledge model, not a specification.** It says what must be represented and what must be refused; it does not prescribe how.
- **The intent taxonomy in §3 is not exhaustive.** Real questions arrive compound ("what's my rate risk and what would 2008 do to it") and require decomposition into multiple chains.
- **Elicitation has a cost.** A system that asks four questions before every answer is unusable; the discipline is to elicit only parameters that would **materially** change the answer, and to default the rest **visibly** rather than silently.
- **No knowledge model prevents a wrong number from a wrong input.** The refusal boundaries in §6 protect against fabrication and silent defaulting; they do not protect against a validated-but-incorrect market data point.

---

## 12. Related Concepts

- [38 — Question-to-Calculation Catalog](38_Question_to_Calculation_Catalog.md) — the human-readable form of §3–§4
- [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md) — stage [5]–[6] of the chain
- [40 — Implementation Pseudocode and Data Contracts](40_Implementation_Pseudocode_and_Contracts.md)
- [29 — Regulatory Framework](29_Regulatory_Framework.md) — the status an agent must not misstate

---

*Accessed 25 August 2026.*
