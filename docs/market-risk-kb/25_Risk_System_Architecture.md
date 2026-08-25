# 25 — Production Market Risk System Architecture

**Level:** 11 · **Prerequisites:** [23](23_Market_Data_and_Curves.md), [24](24_Risk_Data_Model.md) · **Feeds:** [43](43_Daily_Workflow.md)

> **This is a reference architecture, not a prescription.** No regulator specifies system design. What regulation *does* specify — daily ES per desk (`MAR33.2`), monthly SA reporting (`MAR20.2`), quarterly RFET/PLA/backtesting (`MAR33.44`), full lineage (BCBS 239) — imposes hard constraints on what any workable design must deliver. This document derives the architecture from those constraints.

---

## 1. The component map

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  SOURCE LAYER                                                           │
 │  ┌────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐   │
 │  │ 1. Trade   │ │ 3. Reference│ │ 4. Market    │ │ Collateral /     │   │
 │  │    Capture │ │    Data     │ │    Data      │ │ Margin           │   │
 │  └─────┬──────┘ └──────┬──────┘ └──────┬───────┘ └────────┬─────────┘   │
 └────────┼───────────────┼───────────────┼──────────────────┼─────────────┘
          ▼               ▼               ▼                  ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  FOUNDATION LAYER                                                       │
 │  ┌────────────┐                 ┌──────────────┐  ┌──────────────────┐  │
 │  │ 2. Position│                 │ 5. Curve     │  │ 17. Data Quality │  │
 │  │    Service │                 │    Builder   │  │     (gate)       │  │
 │  └─────┬──────┘                 └──────┬───────┘  └──────────────────┘  │
 └────────┼───────────────────────────────┼───────────────────────────────┘
          └───────────────┬───────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  CALCULATION LAYER                                                      │
 │  ┌────────────┐ ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐   │
 │  │ 6. Pricing │►│ 7.Sensitivity│►│ 8. Scenario │ │ 13. P&L Engine   │   │
 │  │    Engine  │ │    Engine    │ │    Engine   │ │ 14. P&L Attrib.  │   │
 │  └─────┬──────┘ └──────┬───────┘ └──────┬──────┘ └────────┬─────────┘   │
 └────────┼───────────────┼────────────────┼─────────────────┼─────────────┘
          └───────────────┴────────┬───────┴─────────────────┘
                                   ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  RISK MEASURE LAYER                                                     │
 │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐    │
 │  │ 9. VaR   │ │ 10. ES   │ │ 11.Stress│ │ 12. FRTB Engine          │    │
 │  │  Engine  │ │  Engine  │ │  Engine  │ │  (SBM / DRC / RRAO / IMA)│    │
 │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────────┬─────────────┘    │
 └───────┼────────────┼────────────┼───────────────────┼──────────────────┘
         └────────────┴─────┬──────┴───────────────────┘
                            ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  AGGREGATION & CONTROL LAYER                                            │
 │  ┌──────────────┐ ┌────────────┐ ┌───────────────┐ ┌─────────────────┐  │
 │  │ 16.Aggregation│ │ 15. Limit  │ │ 18. Model     │ │ 21. Audit /     │  │
 │  │    Engine     │ │     Engine │ │     Validation│ │     Lineage     │  │
 │  └──────┬────────┘ └─────┬──────┘ └───────────────┘ └─────────────────┘  │
 └─────────┼────────────────┼──────────────────────────────────────────────┘
           └────────┬───────┘
                    ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │  CONSUMPTION LAYER                                                      │
 │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────────┐ │
 │  │ 19.Regulatory│  │ 20.Dashboards│  │ Ad-hoc analytics / what-if     │ │
 │  │    Reporting │  │  & Reports   │  │                                │ │
 │  └──────────────┘  └──────────────┘  └────────────────────────────────┘ │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The components

| # | Component | Owns | Critical property |
|---|---|---|---|
| 1 | **Trade Capture** | Trade events, amendments, cancellations | Completeness; every trade reaches risk |
| 2 | **Position Service** | Position state per date, book, desk, entity | Reconciles to front office **and** to the ledger |
| 3 | **Reference Data** | Instruments, issuers, ratings, sectors, calendars | Drives FRTB bucketing — errors are silent |
| 4 | **Market Data** | Capture, validation, normalisation, storage | **Fail loudly; never substitute silently** |
| 5 | **Curve Builder** | Bootstrapping, interpolation, calibration | Must reprice its own inputs |
| 6 | **Pricing Engine** | PV per position | A failed price is escalated, never zeroed |
| 7 | **Sensitivity Engine** | Greeks, DV01, CS01, KRD, JTD, CVR | Carries method, bump size, sign convention |
| 8 | **Scenario Engine** | Applies shock vectors and revalues | **Full revaluation** for optioned books |
| 9 | **VaR Engine** | Historical / parametric / Monte Carlo VaR | Quantile convention recorded |
| 10 | **ES Engine** | 97.5% ES, liquidity-horizon adjusted | Direct at 10-day horizon, **no √T scaling** |
| 11 | **Stress Engine** | Historical, hypothetical, reverse, supervisory | Shocks traceable to data |
| 12 | **FRTB Engine** | SBM (×3 scenarios), DRC, RRAO, IMCC, SES | Stores all three correlation scenarios |
| 13 | **P&L Engine** | APL, HPL, RTPL | **Same pricers as the books** (`MAR32.29`) |
| 14 | **P&L Attribution** | Decomposition and residual | Fixed, versioned ordering |
| 15 | **Limit Engine** | Utilisation, breaches, escalation | **Pre-trade and post-trade** |
| 16 | **Aggregation Engine** | Roll-up across every hierarchy | Diversification handled correctly |
| 17 | **Data Quality** | Validation rules, exceptions, overrides | A **gate**, not a report |
| 18 | **Model Validation** | Independent testing, benchmarking | Organisationally separate (`MAR30.8`) |
| 19 | **Regulatory Reporting** | Capital returns, disclosures | Reproducible on demand |
| 20 | **Dashboards & Reports** | Human-facing views | Drill-down to position level |
| 21 | **Audit / Lineage** | Every number traceable | Bi-temporal, versioned |

---

## 3. The three processing tiers

A single architecture cannot serve all three latency profiles. Mature designs run **the same conceptual calculations at three tempos**.

| Tier | Latency | Method | Consumers | Accuracy |
|---|---|---|---|---|
| **Real-time / intraday** | Sub-second to minutes | Cached sensitivities; approximate revaluation | Traders, pre-trade checks | Indicative |
| **End-of-day batch** | Hours | **Full revaluation** | Official risk, P&L, limits | Authoritative |
| **Periodic / regulatory** | Days | Full, with quarterly gates | Capital, supervisors | Authoritative |

### 3.1 The reconciliation obligation

**Intraday and end-of-day numbers will differ, and that difference must be explained rather than tolerated.**

A desk that trades all day against an indicative intraday DV01 and discovers a materially different official number at 18:00 has been managing to a number that was not real. The gap should be measured, trended, and bounded — a widening gap is a signal that the approximation has drifted out of its valid range, typically because the book has become more optioned than the approximation assumes.

---

## 4. The end-of-day flow

```
 T+0 16:00  MARKETS CLOSE
       │
 16:15 ├─ Trade capture cut-off ──────────► POSITION SERVICE
       │                                        │
 16:30 ├─ Market data snapshot                   │
       │        │                                │
 16:45 ├─ ► DATA QUALITY GATE ◄─────────────────┤
       │        │                                │
       │        ├─ FAIL (blocking) ──► ESCALATE ─┴──► HALT
       │        │                                     (do NOT proceed on
       │        └─ PASS                                substituted data)
       │           │
 17:00 ├─ CURVE BUILD ──► reprice inputs ──► forward sanity ──► surfaces
       │           │
 17:15 ├─ POSITION RECONCILIATION  (front office ↔ risk ↔ ledger)
       │           │
 17:30 ├─ PRICING  (full revaluation)
       │           ├─ any FAILED valuation ──► ESCALATE, never zero
       │           │
 18:00 ├─ SENSITIVITIES ──┬─► P&L ENGINE (APL, HPL, RTPL)
       │                  │        │
       │                  │  18:30 ├─ P&L ATTRIBUTION ──► residual test
       │                  │        │
 18:30 ├─ SCENARIO ENGINE ┘        │
       │        │                  │
 19:00 ├─ VaR · ES · STRESS ◄──────┘
       │        │
 19:30 ├─ FRTB ENGINE  (SBM ×3 scenarios · DRC · RRAO · IMCC · SES)
       │        │
 20:00 ├─ AGGREGATION  (desk → business → entity → firm)
       │        │
 20:15 ├─ LIMIT ENGINE ──► breaches ──► ESCALATION
       │        │
 20:30 ├─ BACKTESTING  (VaR vs APL and HPL)
       │        │
 21:00 └─ REPORTS PUBLISHED ──► dashboards · regulatory extracts

 T+1 07:00   Desk review · breach follow-up · exception commentary
```

### 4.1 The critical path

**Market data → curves → pricing → sensitivities → risk measures → limits.**

Everything else can run in parallel; nothing on that path can be skipped. A 30-minute delay at the data quality gate propagates directly to a 30-minute delay in breach escalation, and breach escalation has a governance deadline.

### 4.2 The gate is a gate

> **If the data quality gate fails on a blocking issue, the batch stops.** It does not proceed on substituted data and flag the substitution in a report nobody reads before the numbers are published.

This is the single most consequential architectural decision in the diagram, and it is the one most often compromised under time pressure. The alternative — proceed and annotate — produces a complete, timely, wrong set of numbers that look exactly like right ones ([23 §4.2](23_Market_Data_and_Curves.md)).

---

## 5. Compute — where the cost actually is

### 5.1 The scaling problem

| Calculation | Revaluations |
|---|---|
| Pricing | *P* |
| Sensitivities (central bump, *F* factors) | *P* × 2*F* |
| Historical VaR (*N* = 250 scenarios) | *P* × *N* |
| **FRTB curvature** (up/down per factor) | *P* × 2*F* |
| **FRTB SBM, three correlation scenarios** | Aggregation ×3 (not revaluation ×3) |
| Monte Carlo VaR (*K* = 50,000 paths) | ***P* × *K*** |
| Full stress suite (*S* scenarios) | *P* × *S* |

For *P* = 200,000 positions and *K* = 50,000 paths, Monte Carlo VaR alone is **10 billion revaluations**. This is why historical simulation, at 250 revaluations per position, remains the production default ([11 §6.2](11_VaR.md)).

### 5.2 What actually makes it tractable

| Technique | Mechanism | Caution |
|---|---|---|
| **Grid / cube pricing** | Price on a factor grid once; interpolate for scenarios | Interpolation error, especially near barriers |
| **Adjoint algorithmic differentiation (AAD)** | All sensitivities at ~a small multiple of one pricing | Large implementation effort; worth it for big derivative books |
| **Parallelism** | Positions and scenarios are embarrassingly parallel | Aggregation is the synchronisation point |
| **Incremental recalculation** | Reprice only what changed | Requires rigorous dependency tracking |
| **Netting before pricing** | Collapse offsetting positions | **Only where legally and economically valid** |
| **Variance reduction** | Antithetic, control variates, importance sampling | Importance sampling is especially effective for **ES** |
| **Hierarchical caching** | Cache curves, surfaces, intermediate PVs | Cache invalidation must follow lineage exactly |

> **AAD is the single highest-leverage optimisation for a large derivatives book**, because sensitivity computation — not pricing — dominates the batch. Bump-and-revalue costs `2F` pricings per position; AAD costs roughly a constant multiple of one, independent of the number of factors.

---

## 6. Where the architecture usually breaks

| Failure mode | Symptom | Root cause |
|---|---|---|
| **Silent substitution** | Numbers look fine; VaR drifts down | Data gate reports rather than blocks |
| **Failed price → zero** | Position vanishes from risk | No `FAILED` status in the model |
| **Reconciliation breaks tolerated** | Risk and ledger diverge slowly | No hard reconciliation gate |
| **Intraday/EOD divergence unmeasured** | Desk manages to an unreal number | No reconciliation obligation |
| **Batch overruns** | Breaches escalated next morning | Critical path not protected |
| **Cache invalidation gaps** | Yesterday's curve used today | Cache keyed on the wrong dependencies |
| **Model version drift** | Numbers irreproducible | Versions not pinned per business date |
| **Aggregation double-count** | Firm risk overstated | Positions counted in two hierarchies |
| **Sensitivity metadata lost** | Reconciliations unresolvable | Method / bump / sign not carried |

---

## 7. Non-functional requirements

| Requirement | Driver |
|---|---|
| **Reproducibility** | Any historical number reproducible exactly, from stored inputs and pinned versions |
| **Bi-temporality** | Both as-of and knowledge dates ([24 §10.1](24_Risk_Data_Model.md)) |
| **Auditability** | Full lineage, capital number to source tick (BCBS 239) |
| **Recoverability** | Batch restartable from any stage without a full rerun |
| **Segregation of duties** | Model development separate from validation (`MAR30.8`); limits set by risk, not the desk |
| **Change control** | Model and configuration changes tested, approved, versioned, dated |
| **Capacity headroom** | Batch completes on the busiest day of the year, not the average |
| **Quarterly gate support** | RFET, PLA and desk backtesting runnable and reproducible quarterly (`MAR33.44`) |

---

## 8. The regulatory cadence the architecture must serve

| Frequency | Requirement | Source |
|---|---|---|
| **Daily** | ES bank-wide **and per IMA desk** | `MAR33.2` |
| **Daily** | Desk-level backtesting | `MAR32.16` |
| **Daily** | VaR vs APL and HPL | `MAR32.4` |
| **Monthly** | Standardised approach calculated and reported | `MAR20.2` |
| **Monthly** | RFET 24/4 criterion monitoring | `MAR31.13(1)` |
| **Quarterly** | RFET, PLA, desk backtesting, stressed period, reduced risk-factor set | `MAR33.44` |
| **Quarterly** | Bank-wide backtesting scope update | `MAR32.7` |
| **Quarterly** | 10% IMA-qualifying capital floor | `MAR32.2` |
| **Weekly** | DRC under IMA | `MAR33.20(5)` |
| **On demand** | SA at supervisory request | `MAR20.3` |
| **At least yearly** | Internal audit of book designations | `RBC25.13` |

> **The quarterly gates are architecturally significant and frequently underestimated.** They are not reports — they are **recalculations that change the capital basis**, and `MAR33.44` requires their reference dates to be *consistent* with one another. A design that treats them as quarter-end extracts from a daily system will struggle to reproduce a quarter-old RFET assessment when a supervisor asks.

---

## 9. Build, buy, or both

| Component | Typical choice | Reasoning |
|---|---|---|
| Trade capture | Buy / existing | Commodity; front-office owned |
| Reference data | Buy (vendor) + internal mastering | Vendor breadth, internal control |
| Market data | Buy + internal validation | **Validation stays internal** |
| Curve builder | Either | Highly conventional but institution-specific |
| Pricing library | **Buy or build; must be one library** | Consistency between front office and risk is non-negotiable |
| Sensitivity engine | Follows the pricing library | |
| VaR / ES engine | Either | Well-defined; performance-sensitive |
| **FRTB engine** | **Buy, increasingly** | Prescriptive, complex, and it changes with the rules |
| Limit engine | Build | Institution-specific structure |
| Aggregation | Build | Institution-specific hierarchy |
| Reporting | Buy platform, build content | |

> **One rule dominates the table: front office and risk must use the same pricing library.** `MAR32.29` requires APL and HPL to be *"computed based on the same pricing models (eg same pricing functions, pricing configurations, model parametrisation, market data and systems) as the ones used to produce the reported daily P&L."* Two libraries guarantee a PLA divergence that is a systems artefact, and it will be indistinguishable from a genuine model deficiency ([15 §6.8](15_Backtesting.md)).

---

## 10. Pseudocode — the batch orchestrator

```
FUNCTION end_of_day_batch(business_date, config):
    ctx = BatchContext(business_date, config.version, restartable = TRUE)

    # ---- 1. Positions -------------------------------------------------
    positions = position_service.snapshot(business_date)
    recon = reconcile(positions, front_office_blotter(), general_ledger())
    IF recon.breaks_exceed(config.recon_tolerance):
        ESCALATE(recon);  HALT                     # hard gate

    # ---- 2. Market data + THE GATE ------------------------------------
    raw    = market_data.capture(business_date, config.snapshot_policy)
    issues = data_quality.validate(raw, config.rules)
    IF issues.has_blocking():
        ESCALATE(issues);  HALT                    # do NOT substitute silently

    # ---- 3. Curves and surfaces --------------------------------------
    curves, surfaces = curve_builder.build(raw, config.build_version)
    ASSERT curves.all_reprice_inputs(config.tolerance)
    ASSERT curves.forwards_are_sane()
    ASSERT surfaces.no_calendar_or_butterfly_arbitrage()

    # ---- 4. Valuation -------------------------------------------------
    valuations = pricing.value_all(positions, curves, surfaces)
    failed = valuations.where(status == "FAILED")
    IF failed.any():
        ESCALATE(failed)                           # NEVER default to zero
        IF failed.material(config):  HALT

    # ---- 5. Sensitivities and scenarios (parallel) --------------------
    PARALLEL:
        sens      = sensitivity_engine.compute(positions, curves, surfaces)
        scen_pnl  = scenario_engine.run(positions, curves, surfaces,
                                        config.historical_scenarios,
                                        method = "FULL_REVALUATION")
        pnl       = pnl_engine.compute(positions_prev, positions, curves_prev,
                                       curves, config.pricing_model_set)
                    # SAME pricing model set as the reported daily P&L

    attribution = pnl_attribution.decompose(pnl, sens,
                                            config.decomposition_order,
                                            config.decomposition_version)
    IF attribution.residual_ratio_gross > config.threshold:
        RAISE_EXCEPTION(attribution)               # requires commentary

    # ---- 6. Risk measures (parallel) ---------------------------------
    PARALLEL:
        var_res    = var_engine.compute(scen_pnl, config.confidence,
                                        config.quantile_convention)
        es_res     = es_engine.compute(scen_pnl, 0.975,
                                       liquidity_horizons = config.lh_map,
                                       scale_from_shorter = FALSE)   # MAR33.4(5)
        stress_res = stress_engine.run(positions, curves, surfaces,
                                       config.stress_library)
        frtb       = frtb_engine.compute(positions, sens, curves,
                                         scenarios = ["MEDIUM","HIGH","LOW"])
                     # store ALL THREE; capital is the max (MAR21.7)

    # ---- 7. Aggregate, check limits, backtest ------------------------
    agg      = aggregation.roll_up(var_res, es_res, stress_res, frtb, sens,
                                   config.hierarchy)
    breaches = limit_engine.check(agg, config.limits)
    FOR b IN breaches:
        classify_and_escalate(b)                   # ACTIVE / PASSIVE / TECHNICAL

    bt = backtest_engine.run(var_res, pnl.apl, pnl.hpl,
                             levels = [0.975, 0.99])

    # ---- 8. Persist with full lineage --------------------------------
    persist_immutable(ctx, positions, raw, curves, surfaces, valuations,
                      sens, scen_pnl, pnl, attribution, var_res, es_res,
                      stress_res, frtb, agg, breaches, bt)

    publish(agg, breaches, bt, attribution)
    RETURN ctx.summary()
```

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Data gate blocks** | Blocking issues halt the batch, not annotate it |
| 2 | **Position reconciliation** | Front office ↔ risk ↔ ledger, within tolerance, as a gate |
| 3 | **Failed valuations escalate** | Never defaulted to zero |
| 4 | **Curve self-reprice** | Inputs reprice within tolerance |
| 5 | **Forward sanity** | Checked automatically, not by eye |
| 6 | **Surface arbitrage** | Calendar and butterfly tests automated |
| 7 | **Full revaluation** | Used for stress and for optioned books |
| 8 | **No √T scaling of ES** | Direct 10-day computation (`MAR33.4(5)`) |
| 9 | **All three SBM scenarios** | Computed and stored |
| 10 | **Same pricing library** | Front office and risk (`MAR32.29`) |
| 11 | **Batch restartable** | From any stage, without a full rerun |
| 12 | **Versions pinned** | Model, curve build, decomposition, per date |
| 13 | **Reproducibility test** | A historical date rerun reproduces the published numbers |
| 14 | **Capacity** | Batch completes on peak-volume days |
| 15 | **Intraday/EOD gap** | Measured and trended |
| 16 | **Quarterly gates** | RFET, PLA, backtesting reproducible, with consistent reference dates |
| 17 | **Segregation** | Validation independent of development (`MAR30.8`) |
| 18 | **Lineage complete** | Capital number traces to source data |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Data gate that reports instead of blocking | Complete, timely, wrong numbers |
| Two pricing libraries (front office and risk) | PLA divergence that is a systems artefact |
| Sensitivity-based stress on optioned books | Tail loss materially understated |
| Monte Carlo VaR from a multivariate normal | Parametric answer at 10,000× the cost |
| No restart capability | A late failure costs the whole batch window |
| Cache keyed on the wrong dependencies | Stale curve silently reused |
| Model versions unpinned | Historical numbers irreproducible |
| Intraday approximation never reconciled to EOD | Desk manages to a number that is not real |
| Quarterly gates treated as extracts | Cannot reproduce a prior assessment on request |
| Aggregation over overlapping hierarchies | Double-counting at firm level |
| Capacity sized to the average day | Batch overruns exactly when volume matters |

---

## 13. Limitations

- **No architecture compensates for bad data.** Every component downstream of the market data layer inherits its quality, and the most sophisticated engine cannot detect an error it has no independent information about.
- **Latency and accuracy trade against each other**, permanently. The three-tier design manages the trade-off; it does not remove it.
- **Vendor FRTB engines reduce implementation risk and increase dependency risk.** The rules change by jurisdiction and over time, and the bank remains accountable for numbers a vendor computed.
- **The architecture described is batch-centric**, which reflects how regulatory measures are defined. Genuinely real-time firm-wide risk remains an approximation for any large institution.
- **Cost is dominated by sensitivities, not pricing** — a fact that surprises teams sizing infrastructure from position counts alone.

---

## 14. Related Concepts

- [23 — Market Data and Curves](23_Market_Data_and_Curves.md) · [24 — Risk Data Model](24_Risk_Data_Model.md)
- [27 — Controls and Governance](27_Controls_and_Governance.md) · [43 — The Daily Workflow](43_Daily_Workflow.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | Calculation frequencies; `MAR30.8` segregation; `MAR32.29` pricing consistency; `MAR33.44` quarterly cycle |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Governance, architecture, accuracy, timeliness, adaptability |

> **Note on sourcing.** Basel prescribes outputs and frequencies, not architecture. The component decomposition, tiering and orchestration here are a design reference derived from those obligations.

*Accessed 25 August 2026.*
