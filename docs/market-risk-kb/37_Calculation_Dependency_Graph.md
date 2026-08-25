# 37 — The Calculation Dependency Graph

**Level:** Reference · **Prerequisites:** [31](31_Master_Calculation_Catalog.md) · **Feeds:** [25](25_Risk_System_Architecture.md), [43](43_Daily_Workflow.md)

> **The dependency graph determines the batch order, the failure blast radius, and the lineage chain.** Nothing in a market risk system is computed in isolation; everything is a function of something upstream, and a defect propagates downward silently unless a gate stops it.

---

## 1. The master chain

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │  REFERENCE DATA          instruments · issuers · ratings · sectors    │
   │  (no dependencies)       calendars · day counts · market cap · economy│
   └────────────┬─────────────────────────────────────────────────────────┘
                │
   ┌────────────▼─────────────────────────────────────────────────────────┐
   │  MARKET DATA             prices · rates · spreads · vols · dividends  │
   │  ◄── VALIDATION GATE ──► blocking failure HALTS everything below      │
   └────────────┬─────────────────────────────────────────────────────────┘
                │
   ┌────────────▼─────────────────────────────────────────────────────────┐
   │  CURVES & SURFACES       bootstrap → interpolate → calibrate          │
   │  ◄── must reprice its own inputs; forwards sane; no vol arbitrage     │
   └────────────┬─────────────────────────────────────────────────────────┘
                │
   ┌────────────▼─────────────────────────────────────────────────────────┐
   │  RISK FACTORS            the modelled observables                     │
   └────────────┬─────────────────────────────────────────────────────────┘
                │
        ┌───────┴────────┐
        │                │
   ┌────▼──────┐   ┌─────▼─────────────────────────────────────────────────┐
   │ POSITIONS │──►│  VALUATION (PV)                                        │
   │           │   │  ◄── a FAILED valuation escalates; it is NOT zero      │
   └───────────┘   └────┬──────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┬──────────────────┐
        │               │               │                  │
   ┌────▼─────┐  ┌──────▼──────┐  ┌─────▼──────┐   ┌───────▼────────┐
   │SENSITIV. │  │  SCENARIO   │  │    P&L     │   │  JTD           │
   │DV01·CS01 │  │  REVALUATION│  │ APL·HPL    │   │ (not a bump —  │
   │Greeks·KRD│  │             │  │            │   │  computed      │
   └────┬─────┘  └──────┬──────┘  └─────┬──────┘   │  directly)     │
        │               │               │          └───────┬────────┘
        │               │          ┌────▼─────┐            │
        │               │          │  RTPL    │            │
        │               │          │  ATTRIB. │            │
        │               │          └────┬─────┘            │
        │               │               │                  │
   ┌────▼───────────────▼───────────────▼──────────────────▼────────────┐
   │  RISK MEASURES                                                      │
   │  VaR · ES · Stress · SBM · Curvature · DRC · RRAO · IMCC · SES      │
   └────────────┬───────────────────────────────────────────────────────┘
                │
   ┌────────────▼───────────────────────────────────────────────────────┐
   │  AGGREGATION            desk → business → entity → firm            │
   └────────────┬───────────────────────────────────────────────────────┘
                │
        ┌───────┴────────┬──────────────────┬──────────────────┐
        ▼                ▼                  ▼                  ▼
    LIMITS          CAPITAL            BACKTESTING          REPORTING
```

---

## 2. Dependency table

`⟵` reads as "depends on".

| Calculation | Depends on |
|---|---|
| **Discount factor** | Zero rate ⟵ curve build ⟵ market data ⟵ validation |
| **PV** | Discount factors + cash flow schedule ⟵ reference data |
| **Clean price** | Dirty price + accrued interest ⟵ calendars, day count |
| **YTM** | Price + cash flows (a *derived quoting convention*, not an input) |
| **DV01** | PV (× 2 or 3 revaluations) |
| **Key-rate DV01** | PV (× 2*n*) + **the curve's node set** |
| **Convexity** | PV (× 3 revaluations) |
| **Effective duration** | PV + **the embedded-option/prepayment model** |
| **CS01** | PV + a **separate** spread curve |
| **Z-spread / OAS** | Market price + curve (+ option model for OAS) |
| **JTD** | Notional + market value + **LGD** — **not** a bump of anything |
| **Net JTD** | Gross JTD + obligor mapping + maturities |
| **HBR** | Net JTD (unweighted) |
| **DRC bucket charge** | Net JTD + risk weights + HBR |
| **Greeks** | PV + volatility surface + underlying |
| **Vega (bucketed)** | Surface in **two dimensions** — strike and tenor |
| **Scenario P&L** | PV under a shocked market (**full revaluation**) |
| **Historical VaR** | Scenario P&L × N + quantile convention |
| **Parametric VaR** | Covariance matrix + sensitivities |
| **Monte Carlo VaR** | Cholesky ⟵ **PSD** covariance matrix + full revaluation per path |
| **ES** | The same scenario P&L set as VaR |
| **FRTB ES (IMCC)** | ES at 10-day horizon × nested factor subsets + liquidity horizons |
| **SES** | Per-NMRF stress scenarios ⟵ **RFET outcome** |
| **RFET** | **Real price observations** tagged to risk factors ⟵ market data capture |
| **SBM WS** | Net sensitivity × risk weight ⟵ **bucket assignment** ⟵ reference data |
| **SBM K_b** | WS + intra-bucket correlations + correlation scenario |
| **Curvature CVR** | PV under prescribed shocks **+ the delta already charged** |
| **APL** | The general ledger |
| **HPL** | Prior-day positions + today's market + **the same pricers as APL** |
| **RTPL** | Prior-day positions + today's market + **only the risk model's factors** |
| **P&L attribution** | APL + sensitivities + market moves + a **fixed decomposition order** |
| **Backtesting** | VaR series + APL + HPL, 250 days |
| **PLA** | RTPL + HPL, exactly 250 days |
| **Limit utilisation** | Any risk measure + limit definitions |
| **Capital** | Everything above |

---

## 3. Asset-class dependency maps

### 3.1 Interest rate

```
   OIS/RFR quotes ──► DISCOUNT CURVE ──┐
   Basis quotes ────► PROJECTION CURVE ─┼──► SWAP/BOND PV ──► DV01 ──► KRD ladder
   XCCY quotes ─────► BASIS CURVE ──────┘         │             │
   CSA terms ───────────────────────────┘         │             ├──► Convexity
                                                  │             ├──► Carry / Roll
   Swaption vols ──► VOL CUBE ──────────────────► │             └──► Curve scenarios
                                                  ▼                        │
                                             OPTION GREEKS                 ▼
                                                  │              SCENARIO P&L ──► VaR/ES
                                                  └──────────────────────► SBM GIRR
                                                                            (δ, ν, curvature)
```

**The CSA is an input to curve *selection*, not just to pricing.** A foreign-currency CSA makes the cross-currency basis a dependency of a pure rates book.

### 3.2 Credit

```
   CDS quotes ─────┐
   Bond prices ────┼──► ISSUER SPREAD CURVE ──► CS01 ──► bucketed CS01 ──► SBM CSR
   Index levels ───┘            │                              │
                                │                              ├──► issuer/sector CS01
   Ratings ────────► BUCKET ────┤                              └──► spread VaR
   Sectors ────────► ASSIGNMENT ┘
                                │
   Notional ───┐                │
   Market value├──► GROSS JTD ──┴──► NET JTD ──► HBR ──► DRC
   LGD ────────┘                       ▲
   Maturity ───────────────────────────┘  (sub-1yr scaling)
```

> **Note the two independent paths.** The spread path (CS01 → CSR) and the default path (JTD → DRC) share only the position record. **JTD does not depend on the spread curve at all** — which is exactly why a spread-based limit framework cannot constrain default exposure.

### 3.3 FX

```
   Spot ──────────┬──► NOP ──► FX delta ──► SBM FX (RW 15%, γ 60%)
                  │
   Both curves ───┼──► FORWARD (CIP) ──► forward delta
                  │         │
   XCCY basis ────┘         └──► BOTH LEGS' DV01 ──► SBM GIRR
                                        ▲
   FX vol surface ──► FX GREEKS ─────────┘
   (ATM, RR, BF)      Δ, ν, vanna, volga ──► SBM FX vega
```

**An FX forward has three dependency paths.** A system that only implements the first reports a third of the risk.

### 3.4 Equity

```
   Spot ─────────┬──► MV ──► net/gross exposure
                 │      └──► delta ──────────────► SBM Equity delta
   Borrow rate ──┼──► repo sensitivity ──────────► SBM Equity delta (RW = spot/100)
   Dividends ────┼──► dividend delta ────────────► SBM Equity
   Vol surface ──┴──► vega, gamma ───────────────► SBM Equity vega + curvature
                                                    (curvature on SPOT only)
   Return history ──► BETA ──► beta-adjusted exposure
   Market cap ──┐
   Economy ─────┼──► BUCKET (1-13)
   Sector ──────┘
```

### 3.5 Commodity

```
   Futures by month ──► FORWARD CURVE ──┬──► delta ──────► SBM Commodity
                                        ├──► calendar spread sensitivity
                                        └──► roll yield
   Location prices ──► LOCATION BASIS ──────► basis delta
   Grade quotes ─────► GRADE BASIS ─────────► basis delta
   Vol surface ──────► vega ────────────────► SBM Commodity vega (LH 120)
```

### 3.6 FRTB capital

```
   Sensitivities ──► NET by factor ──► × RW ──► WS
                                                │
                          ┌─────────────────────┤
                          ▼                     ▼
                   WITHIN-BUCKET (ρ)     ACROSS-BUCKET (γ)
                          │                     │
                          └──────► × 3 SCENARIOS (med/high/low)
                                          │
   PV under shocks ──► CVR ──► curvature ─┤
                                          │
   JTD ──► net JTD ──► HBR ──► DRC ───────┤
                                          │
   Gross notional ──► RRAO ───────────────┤
                                          ▼
                                  SA = SBM + DRC + RRAO   (simple sum)
                                          │
                                          ▼
                                    RWA = × 12.5

   ─────────────────────── IMA path ───────────────────────
   RFET ──► modellable? ──┬── YES ──► ES(97.5, stress-cal, LH-adj) ──► IMCC (ρ=0.5)
                          └── NO  ──► stress scenario ──► SES (ρ=0.6)
                                                              │
   Backtesting ──► m_c (1.5 + 0-0.5) ─────────────────────────┤
   PLA ──► zone ──► eligibility / surcharge ──────────────────┤
                                                              ▼
                                        C_A = max(latest, m_c·avg60)  + DRC + C_U
```

---

## 4. Critical paths and blast radius

### 4.1 What a failure at each level costs

| Failure point | Blast radius | Detectable by |
|---|---|---|
| **Reference data** (sector, rating, market cap) | **Wrong FRTB bucket and risk weight** — capital wrong, nothing else looks wrong | Bucket population review; four-eyes on FRTB-relevant fields |
| **Market data** (stale, missing, wrong convention) | **Everything downstream** — and a stale price *lowers* measured risk | Validation gate; staleness detection |
| **Curve build** (interpolation, missing node) | All rate sensitivities and scenarios | Input repricing; forward sanity |
| **Pricing model** | Values, all sensitivities, P&L, capital | IPV; benchmark model; P&L residual |
| **Failed valuation → zero** | **Value AND risk both silently removed** | Explicit `FAILED` status; escalation |
| **Sensitivity metadata lost** | Reconciliations become unresolvable | Mandatory method/bump/sign fields |
| **Bucket assignment** | SBM capital only | Bucket 16/11 population challenge |
| **Scenario missing** | VaR/ES understated with no visible symptom | `scenarios_missing` counter |
| **Unmapped stress factor** | Stress loss understated; result looks complete | `unmapped_factor_count` reported |
| **RFET evidence not captured** | Factor becomes NMRF → **higher capital** | Real-price tagging at capture |

> **The pattern across this table: the most damaging failures produce numbers that look normal.** That is why the architecture places **gates** at market data, curve build, reconciliation and valuation ([25 §4.2](25_Risk_System_Architecture.md)) rather than relying on downstream detection.

### 4.2 The batch critical path

```
   market data ──► validation gate ──► curves ──► pricing ──► sensitivities
                                                                    │
                                                                    ▼
                                                          risk measures ──► limits
```

**Nothing on this path can be parallelised away.** A delay at the gate propagates directly into delayed breach escalation, which has a governance deadline.

Everything *off* the path — P&L attribution, backtesting, capital reporting, dashboards — can run in parallel or later.

---

## 5. Circular dependencies, and why they are not

Three relationships look circular and are not:

| Apparent loop | Resolution |
|---|---|
| **Price → implied volatility → price** | Implied vol is *derived* from price, then used to price *other* strikes. Not a loop — a calibration |
| **Curve → swap PV → curve** | The curve is built to reprice its inputs; other swaps are then priced *on* it. The bootstrap is the fixed point |
| **Backtesting → multiplier → capital → ...** | The multiplier feeds capital, not the model. One-directional |

**A genuine circularity does exist in one place:** the **PLA test** requires that RTPL use only the risk model's factors, and the *choice* of risk factors is influenced by wanting to pass PLA. `MAR31.26(1)(a)` closes this by requiring that RFET interpolation *"be consistent with mappings used for PLA testing"* — the two must be aligned rather than each optimised against the other.

---

## 6. Computation order

```
PHASE 0  reference data                              (prerequisite, cached)
PHASE 1  market data capture → VALIDATION GATE       ◄── may HALT
PHASE 2  curve and surface build → self-reprice checks
PHASE 3  position snapshot → three-way reconciliation ◄── may HALT
PHASE 4  valuation (full)                             ◄── failures escalate
PHASE 5  [parallel] sensitivities │ scenario revaluation │ P&L (APL/HPL/RTPL)
PHASE 6  P&L attribution → residual test
PHASE 7  [parallel] VaR │ ES │ stress │ SBM │ DRC │ RRAO │ IMCC │ SES
PHASE 8  aggregation across the hierarchy
PHASE 9  [parallel] limits → breaches │ backtesting │ capital
PHASE 10 reporting and publication
```

**Phases 5, 7 and 9 are internally parallel; the phase boundaries are synchronisation points.** The two hard gates are Phase 1 and Phase 3.

---

## 7. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Gates halt** | Phase 1 and Phase 3 stop the batch on blocking failures |
| 2 | **Curve self-reprice** | Every bootstrapping instrument reprices within tolerance |
| 3 | **Failed valuations escalate** | Never defaulted to zero |
| 4 | **JTD independent** | Computed directly, never derived from CS01 |
| 5 | **Both FX legs** | Forwards produce spot delta **and** two rate DV01s |
| 6 | **CSA-aware curve selection** | Discount curve follows the collateral agreement |
| 7 | **Node alignment** | KRD bump nodes match the curve build's nodes |
| 8 | **Full revaluation** | For scenarios, stress and all optioned books |
| 9 | **Same pricers** | APL and HPL use the reported-P&L pricing set |
| 10 | **RTPL factor restriction** | Only the risk model's factors |
| 11 | **All three SBM scenarios** | Computed, stored, maximum taken |
| 12 | **Curvature offsets delta** | `RW·s` subtracted |
| 13 | **Lineage complete** | Every capital number traces to source market data |
| 14 | **Missing counts surfaced** | Scenarios and unmapped factors reported |
| 15 | **Restart capability** | Batch resumable from any phase |

---

## 8. Limitations

- **This graph is the common case.** Exotic products introduce dependencies not shown — a quanto depends on an FX-equity correlation; an autocallable depends on the full skew surface and a correlation parameter.
- **Intraday systems compress the graph deliberately**, using cached sensitivities instead of full revaluation. That is a legitimate speed/accuracy trade-off provided the gap to end-of-day is measured ([25 §3.1](25_Risk_System_Architecture.md)).
- **The order in Phase 5 is not unique.** P&L attribution is path-dependent, so the *decomposition order* within it must be fixed and versioned even though the phase order is not ([14 §5](14_PnL_and_PnL_Explain.md)).
- **Dependency completeness cannot be proven from the graph.** A factor nobody mapped has no edge in the diagram and no representation in the risk system — the absence is invisible by construction.

---

## 9. Related Concepts

- [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) · [33 — Master Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md)
- [24 — Risk Data Model](24_Risk_Data_Model.md) · [25 — Risk System Architecture](25_Risk_System_Architecture.md)
- [43 — The Daily Workflow](43_Daily_Workflow.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21`–`MAR33` calculation definitions and ordering constraints; `MAR31.26(1)(a)` PLA/RFET alignment |
| BCBS | BCBS 239 | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Lineage and data aggregation |

*Accessed 25 August 2026.*
