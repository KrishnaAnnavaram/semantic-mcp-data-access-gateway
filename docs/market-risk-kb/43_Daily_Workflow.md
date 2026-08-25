# 43 — The End-to-End Daily Market Risk Workflow

**Level:** Practical · **Prerequisites:** [25](25_Risk_System_Architecture.md), [27](27_Controls_and_Governance.md) · **Feeds:** [44](44_Roles_and_Responsibilities.md)

> **Times below are indicative for a firm whose primary book closes in New York.** The *sequence* and the *gates* are not indicative — they are determined by the dependency structure of [37](37_Calculation_Dependency_Graph.md) and by regulatory frequency requirements.

---

## 1. The day at a glance

```
  T-1  17:00 ─┬─ Asia opens; intraday risk runs continuously
              │
  T+0  08:00 ─┼─ Europe opens
       14:30 ─┼─ US opens
              │  ◄── PRE-TRADE limit checks run all day
       16:00 ─┼─ US CLOSE ─────────────────── END OF TRADING
       16:15 ─┼─ Trade capture cut-off
       16:30 ─┼─ Market data snapshot
       16:45 ─┼─ ► DATA QUALITY GATE ◄            may HALT
       17:00 ─┼─ Curve and surface build
       17:15 ─┼─ ► POSITION RECONCILIATION ◄      may HALT
       17:30 ─┼─ Valuation (full)                 failures ESCALATE
       18:00 ─┼─ Sensitivities  │  P&L (APL/HPL/RTPL)
       18:30 ─┼─ Scenario revaluation │ P&L attribution
       19:00 ─┼─ VaR · ES · Stress
       19:30 ─┼─ FRTB engine
       20:00 ─┼─ Aggregation
       20:15 ─┼─ Limit checks → breach escalation
       20:30 ─┼─ Backtesting
       21:00 ─┴─ Reports published
  T+1  07:00 ─── Desk review · exception commentary · breach follow-up
```

---

## 2. Intraday — before the close

### 2.1 What runs continuously

| Activity | Owner | Purpose |
|---|---|---|
| **Real-time position and P&L** | Front office | Manage the book |
| **Cached sensitivities** | Front office / risk | Indicative Greeks |
| **Pre-trade limit checks** | Risk system, used by traders | **Prevent** breaches before they occur |
| **Intraday limit monitoring** | Market risk | Catch large intraday builds |
| **Market data feeds** | Data ops | Continuous validation |

### 2.2 The intraday/EOD gap

**Intraday numbers are indicative; end-of-day numbers are official.** The two will differ, and that difference must be **measured and trended**, not tolerated.

> A desk trading all day against an approximate DV01 and discovering a materially different official figure at 18:00 has been managing to a number that was not real. **A widening gap means the approximation has drifted out of its valid range** — typically because the book has become more optioned than the approximation assumes ([25 §3.1](25_Risk_System_Architecture.md)).

### 2.3 Pre-trade is where control actually happens

```
   Trader proposes a trade
        │
        ▼
   Recompute limits on the HYPOTHETICAL book
        │
        ├── within limits ────────────► execute
        │
        └── would breach ─────────────► reduce · hedge · or seek approval
                                        ◄── BEFORE trading, not after
```

**A limit discovered to be breached at end of day has already failed at its primary job** ([21 §2](21_Market_Risk_Limits.md)).

---

## 3. Market close and capture (16:00–16:30)

| Step | Detail | Failure mode |
|---|---|---|
| **Trading ceases** | Official close for the primary market | Late trades booked after cut-off |
| **Trade capture cut-off** | A hard time, published in advance | Trades missed from the risk run |
| **Market data snapshot** | Per the documented snapshot policy | Regional vs global timing inconsistency |

**The snapshot policy must be the same for pricing, P&L and risk** — and identical across APL, HPL and RTPL. `MAR32.29` requires APL and HPL to use the same market data as the reported daily P&L; a timing mismatch surfaces later as a **PLA failure that is a systems artefact rather than a model deficiency** ([15 §6.8](15_Backtesting.md)).

---

## 4. GATE 1 — Data quality (16:45)

```
   Validate: completeness · staleness · outliers · cross-source · bounds
             arbitrage (rates and vol) · triangular (FX)
        │
        ├── BLOCKING failure ──► ESCALATE ──► HALT
        │                        (do NOT proceed on substituted data)
        │
        └── PASS or documented, approved, dated proxy ──► continue
```

**This is the most consequential decision in the entire day, and the one most often compromised under time pressure.**

| Response | Acceptable? |
|---|---|
| Escalate to a named owner | **Always** |
| Apply a documented, flagged, **expiring** proxy | Yes, with an audit record |
| Silently carry forward yesterday's value | **No** |
| Silently interpolate | **No** |
| Default a failed price to zero | **Never** |

> **Why carry-forward is worse than it looks.** A stale price produces a **zero return**. Zero returns entering the VaR history **reduce measured volatility** — so a data failure makes the risk number look *better*. **The failure is self-concealing and biased in the dangerous direction** ([23 §4.2](23_Market_Data_and_Curves.md)).

---

## 5. Curve and surface build (17:00)

```
   Bootstrap discount curves (OIS/RFR, per currency)
        │
   Bootstrap projection curves (per index and tenor, vs the RFR)
        │
   Build cross-currency basis curves
        │
   Calibrate volatility surfaces and cubes
        │
   ► POST-BUILD GATES:
        ├─ every bootstrapping instrument reprices to its quote
        ├─ implied forwards positive and non-oscillating
        └─ surfaces free of calendar and butterfly arbitrage
```

**Plot the implied forwards.** A curve can look perfectly smooth in zero-rate space and imply oscillating or negative forwards — which produces unstable key-rate sensitivities and hedge ratios ([23 §6.4](23_Market_Data_and_Curves.md)).

---

## 6. GATE 2 — Position reconciliation (17:15)

**Three-way: front office ↔ risk system ↔ general ledger.**

| Break | Meaning |
|---|---|
| FO vs risk | **Risk is being measured on the wrong book** |
| Risk vs ledger | P&L and risk describe different portfolios |
| FO vs ledger | Accounting is wrong |

Tolerances must be **absolute and relative**, and both defended. **Break ageing matters more than break count**: ten breaks opened and closed the same day is a functioning process; two open for ninety days is a broken one — and the second reports as the better number.

> **Every major unauthorised trading loss has involved a break that was visible and tolerated** — usually because it was small relative to the desk's revenue and the explanation was plausible ([27 §3.2](27_Controls_and_Governance.md)).

---

## 7. Valuation (17:30)

```
   FOR each position:  price with the CSA-appropriate curves
        │
        ├── SUCCESS ──► store PV with model version and curve ids
        │
        └── FAILED ──► ESCALATE
                       status = FAILED, NOT zero
                       if material: HALT
```

> **A position that fails to price is not worth zero. It is unknown.** Silently defaulting it removes both the value *and* the risk from every downstream report, and nothing looks broken. This is the single most dangerous defect a risk system can contain.

---

## 8. Sensitivities and P&L (18:00–18:30) — parallel

### 8.1 Sensitivities

DV01, key-rate ladders, CS01, Greeks, JTD, curvature CVRs — each stored with **method, bump size and sign convention**.

**Run the checks:** analytic vs bumped agreement; `Σ KRD01 = parallel DV01`; completeness across positions.

### 8.2 The three P&L measures

| Measure | Construction | Regulatory use |
|---|---|---|
| **APL** | Booked P&L, fees excluded | Backtesting |
| **HPL** | Prior-day positions, today's market, **same pricers as reported P&L** | Backtesting **and** PLA |
| **RTPL** | Same static book, **only the risk model's factors** | PLA |

### 8.3 P&L attribution

Decompose into carry/roll/theta, each market factor in a **fixed, versioned order**, then trading activity and fees. Compute the residual **on a gross basis**.

**A residual above threshold requires written commentary before the report is published**, not after.

> Watch for **sign persistence**. A small residual that is always the same sign is worse than a larger random one — it means something is structurally missing ([14 §6](14_PnL_and_PnL_Explain.md)).

---

## 9. Risk measures (19:00–19:30)

```
   [parallel]
     ├─ Scenario revaluation (250 historical scenarios, FULL reval)
     ├─ VaR   — quantile convention stated; missing scenarios counted
     ├─ ES    — 97.5%, computed DIRECTLY at the 10-day base horizon
     ├─ Stress — full revaluation; unmapped factors REPORTED
     └─ FRTB  — SBM (× 3 correlation scenarios) · DRC · RRAO · IMCC · SES
```

**Three things that must not be shortcut here:**

1. **Full revaluation for scenarios and stress**, especially for optioned books. At +250bp the sensitivity estimate errs by 14% on a plain Treasury portfolio ([30 §4.2](30_Worked_Examples.md)).
2. **No √T scaling of ES to the base horizon** — `MAR33.4(5)` requires direct computation at *T*.
3. **All three SBM correlation scenarios computed and stored**, with capital set to the maximum. Which scenario binds is itself informative ([17 §6.5](17_FRTB_Standardised_Approach.md)).

---

## 10. Aggregation and limits (20:00–20:15)

```
   Roll up: desk → business → division → legal entity → group
            plus issuer, sector, country, counterparty
        │
   Check limits at EVERY level independently
        │  ◄── a parent can breach with NO child in breach
        │
   FOR each breach:
        classify   ACTIVE / PASSIVE / TECHNICAL / REPORTING
        notify     within the defined window
        record     root cause and remediation plan — MANDATORY
        escalate   by severity and duration
```

**Every breach is recorded, including same-day cures.** A framework that lets quick cures go unrecorded loses exactly the data needed to detect a deteriorating desk ([21 §8](21_Market_Risk_Limits.md)).

---

## 11. Backtesting (20:30)

| Level | Comparison | Consequence |
|---|---|---|
| **Bank-wide** | 99% VaR vs APL **and** HPL | Traffic-light zone → multiplier 1.50–2.00 |
| **Desk** | **97.5% and 99%** VaR vs APL and HPL | >12 @99% or >30 @97.5% → **standardised approach** |

**Exceptions for APL and HPL are counted separately; the overall count is the greater** (`MAR32.5(1)`). Missing P&L or missing VaR **counts as an outlier** (`MAR32.5(2)`).

**Every exception must be documented with a written explanation** (`MAR32.12`) — that day, not at quarter end.

---

## 12. Publication (21:00)

```
   Daily market risk report ──► exceptions FIRST, with owners and dates
   Desk risk reports ────────► sensitivities, utilisation, P&L attribution
   Dashboards ───────────────► refreshed, drillable to position level
   Regulatory extracts ──────► per the applicable frequency
   Immutable persistence ────► bi-temporal, versioned, full lineage
```

---

## 13. T+1 morning (07:00)

| Activity | Owner |
|---|---|
| Desk review of overnight risk and P&L | Desk head |
| **Exception commentary** on breaches and backtest exceptions | Desk + market risk |
| Reconciliation break follow-up | Product control |
| Data quality exception follow-up; **proxy expiry enforcement** | Data ops |
| Escalation of unremediated items | Market risk |

---

## 14. The non-daily cycle

| Frequency | Activity | Source |
|---|---|---|
| **Weekly** | DRC under IMA | `MAR33.20(5)` |
| **Monthly** | SA calculated and reported | `MAR20.2` |
| **Monthly** | RFET 24/4 criterion monitoring | `MAR31.13(1)` |
| **Monthly** | Independent price verification | Practice |
| **Monthly** | Valuation reserves | Practice |
| **Quarterly** | **RFET assessment** | `MAR31.13` |
| **Quarterly** | **PLA test** (250 days RTPL/HPL) | `MAR32.35`, `MAR33.44` |
| **Quarterly** | Desk backtesting assessment; bank-wide scope update | `MAR32.7` |
| **Quarterly** | **10% IMA-qualifying capital floor** | `MAR32.2` |
| **Quarterly** | Stressed period and reduced risk-factor set refresh | `MAR33.44` |
| **Annually** | Supervisory stress test submission | Jurisdictional |
| **Annually** | **Internal audit of book designations** | `RBC25.13` |
| **Annually+** | Limit review; model validation by materiality | Practice |

> **`MAR33.44` requires the quarterly reference dates to be *consistent* with one another.** RFET, PLA, desk backtesting, the stressed period and the reduced factor set are not five independent quarterly jobs — they are one coordinated re-assessment that changes the capital basis.

---

## 15. What can go wrong, and when it is caught

| Failure | Introduced at | Caught at | If not caught |
|---|---|---|---|
| Missed trade | Capture | Position reconciliation | Risk measured on the wrong book |
| Stale price | Data capture | Data quality gate | **Understated VaR** — self-concealing |
| Bad curve node | Curve build | Input repricing check | Every rate sensitivity wrong |
| Failed valuation | Valuation | Explicit `FAILED` status | Value and risk silently removed |
| Wrong sensitivity method | Sensitivity engine | Analytic vs bumped check | Unreconcilable breaks |
| Incomplete KRD ladder | Sensitivity engine | Completeness identity | Curve risk misattributed |
| Missing scenario | Scenario engine | `scenarios_missing` counter | VaR understated |
| Unmapped stress factor | Stress engine | `unmapped_factor_count` | Stress understated; result looks complete |
| Wrong bucket assignment | Reference data | Bucket population review | **Wrong capital, nothing else looks wrong** |
| Model deterioration | Over weeks | Backtesting, PLA, residual trend | Capital based on a model that no longer fits |

**The pattern:** the most damaging failures produce numbers that look normal. That is why the day contains **two hard gates and one mandatory escalation path**, rather than relying on downstream detection.

---

## 16. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Trade capture cut-off enforced | Published, hard |
| 2 | Snapshot policy consistent | Pricing, P&L and risk identical |
| 3 | **Gate 1 halts** | Blocking data failures stop the batch |
| 4 | Curve self-reprice | Within tolerance |
| 5 | Forwards plotted and sane | Automated check |
| 6 | **Gate 2 halts** | Reconciliation breaks beyond tolerance stop the batch |
| 7 | Break ageing tracked | Not only counts |
| 8 | Failed valuations escalate | Never zeroed |
| 9 | Sensitivity metadata | Method, bump, sign on every row |
| 10 | KRD completeness | `Σ KRD01 = DV01` |
| 11 | Same pricers for APL/HPL | `MAR32.29` |
| 12 | RTPL factor restriction | Only the risk model's factors |
| 13 | Residual on gross basis | With commentary on breach |
| 14 | Full revaluation | Scenarios, stress, optioned books |
| 15 | No √T scaling of ES | Direct at 10 days |
| 16 | Three SBM scenarios | Maximum taken |
| 17 | Limits checked at every level | Independently |
| 18 | All breaches recorded | Including same-day cures |
| 19 | Backtest count | **max**(APL, HPL) + unavailable |
| 20 | Every exception documented | Same day |
| 21 | Batch restartable | From any phase |
| 22 | Immutable persistence | Bi-temporal, versioned, with lineage |
| 23 | Quarterly gates coordinated | Consistent reference dates |

---

## 17. Limitations

- **Timings are indicative.** A firm with a different primary market, or with material Asian activity, has a different clock. The sequence does not change.
- **The workflow is batch-centric**, reflecting how regulatory measures are defined. Genuinely real-time firm-wide risk remains an approximation at scale.
- **The two gates create a tension with the publication deadline.** That tension is deliberate: publishing on time with substituted data is worse than publishing late with an explanation.
- **A clean daily run proves the process ran, not that the numbers are right.** Model quality is [26](26_Model_Risk_and_Validation.md)'s question, on a quarterly cycle.

---

## 18. Related Concepts

- [25 — Risk System Architecture](25_Risk_System_Architecture.md) · [27 — Controls and Governance](27_Controls_and_Governance.md)
- [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md) · [44 — Roles and Responsibilities](44_Roles_and_Responsibilities.md)
- [28 — Reporting and Dashboards](28_Reporting_and_Dashboards.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | All frequency requirements; `MAR32.5`, `MAR32.12`, `MAR32.29`, `MAR33.4(5)`, `MAR33.44`; `RBC25.13` |
| BCBS | BCBS 239 | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Timeliness, accuracy, distribution |

> **Note on sourcing.** The clock times and the ordering of non-mandated steps reflect common industry practice. The frequencies in §14 and the gate requirements are regulatory and cited to paragraph.

*Accessed 25 August 2026.*
