# 24 — The Market Risk Data Model

**Level:** 11 · **Prerequisites:** [23](23_Market_Data_and_Curves.md) · **Feeds:** [25](25_Risk_System_Architecture.md), [28](28_Reporting_and_Dashboards.md), [40](40_Implementation_Pseudocode_and_Contracts.md)

> **This is a conceptual data model, not a physical schema.** It states what must be represented, what the keys are, and which relationships carry the load. Physical design — normalisation, partitioning, storage engine — is an implementation decision that follows from volume and latency requirements, not from this document.

---

## 1. The entity map

```
   REFERENCE DATA ──────────┐
   (issuers, instruments,   │
    calendars, ratings)     │
                            ▼
   TRADE  ──────────►  POSITION  ──────────►  VALUATION
     │                     │                      │
     │                     │                      ├──►  SENSITIVITY
     │                     │                      │
   MARKET DATA ──► CURVE/SURFACE ──► RISK FACTOR ─┤
                                          │       ├──►  SCENARIO P&L
                                          │       │
                                          │       └──►  P&L (APL/HPL/RTPL)
                                          │
                                          ▼
                            ┌──────────────────────────┐
                            │   AGGREGATION            │
                            │   (desk → entity → firm) │
                            └──────────────────────────┘
                                          │
              ┌───────────────┬───────────┼───────────┬──────────────┐
              ▼               ▼           ▼           ▼              ▼
            VaR / ES       STRESS      LIMITS    FRTB CAPITAL    REPORTING
```

**Every arrow is a dependency.** The model's central design requirement is that each arrow be **traceable in both directions** — from a reported number down to its inputs, and from an input up to everything it affected. That bidirectional traceability is what makes a challenged number defensible.

---

## 2. Reference data

**The most under-invested and most damaging layer.** Reference errors do not produce error messages; they produce plausible wrong answers.

### 2.1 Instrument

```
instrument:
    instrument_id           string       PK
    instrument_type         enum {BOND, FRN, LINKER, MBS, ABS, BILL, CP, REPO,
                                  IR_SWAP, OIS, FRA, FUTURE, SWAPTION, CAP_FLOOR,
                                  FX_SPOT, FX_FORWARD, FX_SWAP, NDF, FX_OPTION,
                                  XCCY_SWAP, EQUITY, ETF, EQ_FUTURE, EQ_OPTION,
                                  EQ_SWAP, CDS, CDS_INDEX, TRANCHE, CMDTY_FUTURE,
                                  CMDTY_OPTION, CONVERTIBLE, STRUCTURED_NOTE}
    identifiers             map<enum, string>   -- ISIN, CUSIP, SEDOL, RIC, internal
    currency                ISO-4217
    issuer_id               string       FK -> issuer
    issue_date              date
    maturity_date           date | null
    coupon_rate             decimal | null
    coupon_frequency        int | null
    day_count               enum
    business_day_convention enum
    calendar_ids            list<string>
    seniority               enum {SENIOR, SUBORDINATED, SECURED, COVERED} | null
    is_listed               boolean      -- RRAO exclusion (MAR23.7)
    is_ccp_eligible         boolean      -- RRAO exclusion (MAR23.7)
    embedded_options        list<option_terms> | null
    underlying_ids          list<string> | null
    contract_size           decimal | null
    delivery_location       string | null   -- commodity basis
    quality_grade           string | null   -- commodity basis
```

### 2.2 Issuer

```
issuer:
    issuer_id               string       PK
    legal_name              string
    lei                     string | null
    parent_issuer_id        string | null   -- for market-cap aggregation rules
    issuer_type             enum {SOVEREIGN, CENTRAL_BANK, MDB, LOCAL_GOVERNMENT,
                                  PSE, FINANCIAL, CORPORATE, SPV, FUND}
    country_of_incorporation ISO-3166
    country_of_risk         ISO-3166       -- NOT always the same
    sector_classification   string          -- must be a market-standard scheme
    sector_scheme           string          -- MAR21.52 requires a common scheme
    rating_internal         string | null
    rating_external         map<agency, string>
    credit_quality_category enum {AAA, AA, A, BBB, BB, B, CCC, UNRATED, DEFAULTED}
    market_capitalisation   decimal | null  -- single listed entity, all markets
    market_cap_band         enum {LARGE, SMALL}    -- >= USD 2bn per MAR21.74
    economy_classification  enum {ADVANCED, EMERGING}   -- MAR21.75 exhaustive list
    is_defaulted            boolean
```

> **Three fields on this entity carry disproportionate capital consequences.**
>
> - `sector_classification` drives the FRTB CSR and equity bucket. An unclassifiable issuer lands in CSR bucket 16 (**12% risk weight, no offsetting at all**) or equity bucket 11 (**70%**).
> - `market_capitalisation` must be *"the sum of the market capitalisations based on the market value of the total outstanding shares issued by the same listed legal entity"* across all markets globally. `MAR21.74` is explicit: *"Under no circumstances should the sum of the market capitalisations of multiple related listed entities be used."* The `parent_issuer_id` relationship exists to make that rule enforceable rather than merely stated.
> - `economy_classification` must follow the `MAR21.75` **exhaustive** list. It is not a judgement.

### 2.3 Calendars, and why they are reference data

```
calendar:
    calendar_id             string       PK
    jurisdiction            string
    holiday_dates           list<date>
    weekend_days            list<int>
    valid_from, valid_to    date
```

A missing holiday shifts a cash flow by a day, changes an accrual, and produces a small persistent P&L residual that is extremely difficult to diagnose from the top down.

---

## 3. Trade and position

### 3.1 The distinction

**A trade is an event; a position is a state.** Risk is measured on positions. P&L attribution needs trades ([14 §4.3](14_PnL_and_PnL_Explain.md)). Both must be retained.

```
trade:
    trade_id                string       PK
    trade_version           int          PK   -- amendments create versions
    instrument_id           string       FK
    trade_date              date
    execution_timestamp     timestamp
    settlement_date         date
    direction               enum {BUY, SELL}
    quantity                decimal
    notional                decimal
    price                   decimal
    currency                ISO-4217
    counterparty_id         string       FK
    netting_set_id          string | null FK
    csa_id                  string | null FK   -- determines the discount curve
    book_id                 string       FK
    trader_id               string
    status                  enum {NEW, AMENDED, CANCELLED, MATURED, EXERCISED}
    regulatory_book         enum {TRADING, BANKING}      -- RBC25 designation
    designation_rationale   text                          -- RBC25.13 requires it
    designation_timestamp   timestamp                     -- at INCEPTION
    is_internal_risk_transfer boolean
    irt_external_hedge_id   string | null
```

> `regulatory_book`, `designation_rationale` and `designation_timestamp` are not audit decoration. `RBC25.5` requires designation **when the instrument is first recognised**; `RBC25.13` requires documented policies and **at least yearly internal audit** of designations. A model that cannot show *when* and *why* an instrument was designated cannot evidence compliance.

### 3.2 Position

```
position:
    position_id             string       PK
    business_date           date         PK
    instrument_id           string       FK
    book_id                 string       FK
    desk_id                 string       FK      -- MAR12 regulatory desk
    legal_entity_id         string       FK
    quantity                decimal
    notional                decimal
    market_value            decimal
    accrued_interest        decimal
    currency                ISO-4217
    source_trade_ids        list<string>          -- lineage back to trades
```

### 3.3 The organisational hierarchy

```
book        →  desk        →  business_line  →  division  →  legal_entity
                 │
                 └─ desk is the MAR12 REGULATORY unit:
                    - single head
                    - defined business strategy
                    - documented risk management structure
                    - clear reporting lines
                    - the unit at which IMA approval is granted and WITHDRAWN
```

```
trading_desk:
    desk_id                 string       PK
    desk_name               string
    desk_head               string                -- MAR12 requires ONE
    business_strategy       text                  -- documented
    reporting_lines         text
    ima_approval_status     enum {APPROVED, NOT_APPROVED, WITHDRAWN, PENDING}
    ima_approval_date       date | null
    drc_model_approval      boolean               -- SECOND-STAGE, MAR32.19 fn 1
    current_pla_zone        enum {GREEN, AMBER, RED} | null
    pla_zone_effective_from date | null
    backtest_exceptions_99  int
    backtest_exceptions_975 int
    capital_approach        enum {SA, IMA}        -- derived, quarterly
```

> **`capital_approach` is derived, never asserted.** It is a function of IMA approval, backtesting exception counts against the `MAR32.19` thresholds (>12 at 99%, >30 at 97.5%) and the PLA zone. Storing it as an independently-editable field is how a desk ends up capitalised on a model it has lost.

---

## 4. Market data and risk factors

Covered in full in [23](23_Market_Data_and_Curves.md). The entities the risk model depends on:

```
market_data_point:      -- see 23 §11 for the full contract
    point_id, business_date, knowledge_date, value, unit,
    quote_basis, compounding, day_count, vol_convention,
    source, validation_status, is_real_price, real_price_criterion

curve / surface:
    curve_id, currency, curve_type, csa_currency, node_tenors, node_values,
    interpolation, build_version, input_point_ids, max_repricing_error

risk_factor:
    risk_factor_id          string       PK      -- e.g. "USD.SOFR.ZERO.10Y"
    risk_class              enum {GIRR, CSR_NS, CSR_SEC_CTP, CSR_SEC_NONCTP,
                                  EQUITY, COMMODITY, FX}
    factor_type             enum {ZERO_RATE, INFLATION, XCCY_BASIS, SPREAD,
                                  SPOT, REPO_RATE, DIVIDEND, VOLATILITY,
                                  CORRELATION}
    currency                ISO-4217 | null
    tenor                   decimal | null
    strike_or_delta         decimal | null
    issuer_id               string | null
    delivery_location       string | null
    sbm_bucket              int | null            -- MAR21 bucket
    liquidity_horizon_days  int                   -- MAR33.12 Table 2
    modellability_status    enum {MODELLABLE, NON_MODELLABLE}
    rfet_assessment_date    date
    rfet_observation_count  int
    rfet_worst_90day_gap    int                   -- MAR31.13(1)
    is_idiosyncratic        boolean               -- MAR33.16(2) treatment
```

> **`modellability_status` must be derived from evidence, quarterly, and must be versioned.** A factor that was modellable last quarter and is not this quarter changes the capital calculation. If the field is overwritten in place, the previous quarter's capital number becomes irreproducible.

---

## 5. Valuation and sensitivity

```
valuation:
    valuation_id            string       PK
    business_date           date         PK
    position_id             string       FK
    pv                      decimal
    currency                ISO-4217
    pv_reporting_ccy        decimal
    fx_rate_used            decimal
    pricing_model_id        string       FK
    pricing_model_version   string
    curve_ids               list<string>          -- CSA-aware selection
    surface_ids             list<string> | null
    valuation_status        enum {SUCCESS, FAILED, PROXY}
    failure_reason          text | null
```

> **`valuation_status` must exist and `FAILED` must be a first-class outcome.** A position that fails to price is not worth zero; it is **unknown**, and it must be escalated. Silently defaulting a failed valuation to zero removes both the value *and* the risk from every downstream report — the single most dangerous defect a risk system can contain ([03 §6](03_Pricing_Fundamentals.md)).

```
sensitivity:
    sensitivity_id          string       PK
    business_date           date         PK
    position_id             string       FK
    risk_factor_id          string       FK
    measure                 enum {PV, DV01, KRD01, CS01, DELTA, GAMMA, VEGA,
                                  THETA, RHO, VANNA, VOLGA, CONVEXITY,
                                  CVR_UP, CVR_DOWN, JTD}
    value                   decimal
    currency                ISO-4217
    unit                    enum {CCY, CCY_PER_BP, CCY_PER_VOL_PT, CCY_PER_DAY,
                                  SHARES, YEARS, DIMENSIONLESS}
    computation_method      enum {ANALYTIC, BUMP_1SIDED, BUMP_CENTRAL,
                                  FULL_REVAL}
    bump_size               decimal | null
    sign_convention         enum {LOSS_ON_RISE, SIGNED_DERIVATIVE}
```

> **`computation_method`, `bump_size` and `sign_convention` are mandatory.** Two DV01s computed with different bump sizes or opposite sign conventions are different numbers, and a reconciliation that does not carry these three fields cannot be resolved. This is the single most common cause of unresolvable sensitivity breaks between two institutions ([04 §4.6](04_Interest_Rate_Risk.md), [04 §13](04_Interest_Rate_Risk.md)).

---

## 6. P&L

The three regulatory measures must be **separate, first-class entities** — not one field with a type flag, because their exclusion rules differ ([14 §2.2](14_PnL_and_PnL_Explain.md)).

```
pnl:
    business_date           date         PK
    desk_id                 string       PK
    pnl_type                enum {APL, HPL, RTPL, CLEAN}   PK
    value                   decimal
    currency                ISO-4217
    includes_new_trades     boolean       -- FALSE for HPL and RTPL (MAR32.25)
    includes_fees           boolean       -- FALSE for APL and HPL (MAR32.26)
    includes_intraday       boolean       -- FALSE for HPL (MAR32.25)
    va_treatment            enum {ALL, DAILY_UPDATED_ONLY, NONE}  -- MAR32.27
    time_effect_treatment   enum          -- must MATCH across the three (MAR32.28)
    pricing_model_set_id    string        -- must MATCH APL/HPL (MAR32.29)
    risk_model_id           string | null -- RTPL only

pnl_attribution:
    business_date, desk_id                PK
    component               enum {CARRY, ROLL, THETA, RATES_DELTA, RATES_CURVE,
                                  CONVEXITY, CREDIT_SPREAD, FX, EQUITY, VEGA,
                                  CROSS_TERMS, NEW_TRADES, AMENDMENTS, FEES,
                                  RESERVES, UNEXPLAINED}
    value                   decimal
    decomposition_version   string        -- ordering is path-dependent (14 §5)
    decomposition_order     int
```

---

## 7. Risk results

```
var_result:
    business_date, scope_type, scope_id      PK
    measure                 enum {VAR, ES}
    confidence_level        decimal          -- 0.975, 0.99
    horizon_days            int
    method                  enum {HISTORICAL, PARAMETRIC, MONTE_CARLO,
                                  DELTA_NORMAL, DELTA_GAMMA}
    value                   decimal
    lookback_days           int
    quantile_convention     enum {ROUND_UP, ROUND_DOWN, INTERPOLATED}
    weighting_scheme        enum {EQUAL, AGE_WEIGHTED, VOL_SCALED, FILTERED}
    scenario_count          int
    scenarios_missing       int              -- NOT silently dropped

scenario_pnl:
    business_date, scope_id, scenario_id     PK
    scenario_date           date | null      -- historical simulation
    pnl                     decimal
    rank                    int

stress_result:
    business_date, scope_id, scenario_id     PK
    scenario_name           string
    scenario_type           enum {HISTORICAL, HYPOTHETICAL, SENSITIVITY,
                                  REVERSE, SUPERVISORY}
    pnl                     decimal
    revaluation_method      enum {FULL, SENSITIVITY_BASED}
    unmapped_factor_count   int              -- ALWAYS reported (13 §11)
    top_drivers             list<(risk_factor_id, contribution)>
```

> **`quantile_convention` on a VaR result is not pedantry.** [11 §4.5](11_VaR.md) shows a 13% spread in reported VaR arising purely from this choice. Storing it makes cross-institution and cross-time comparisons interpretable; omitting it makes them meaningless.
>
> **`scenarios_missing` and `unmapped_factor_count` exist to make silence visible.** A stress result computed with 40 unmapped factors is not the same result as one computed with none, and the difference must not be invisible in the output.

---

## 8. Capital

```
frtb_sa_capital:
    business_date, scope_id                  PK
    component               enum {SBM_DELTA, SBM_VEGA, SBM_CURVATURE,
                                  DRC, RRAO}
    risk_class              enum | null
    correlation_scenario    enum {MEDIUM, HIGH, LOW} | null
    value                   decimal
    is_binding_scenario     boolean          -- the MAX, per MAR21.7

frtb_ima_capital:
    business_date, scope_id                  PK
    component               enum {IMCC_UNCONSTRAINED, IMCC_CONSTRAINED, IMCC,
                                  SES, DRC_IMA, C_U, PLA_SURCHARGE}
    value                   decimal
    multiplier_mc           decimal | null   -- 1.5 + add-on (MAR33.42)
    backtest_addon          decimal | null   -- 0 to 0.5
    qualitative_addon       decimal | null
    imcc_rho                decimal          -- 0.5 (MAR33.15)
    ses_rho                 decimal          -- 0.6 (MAR33.17)
    avg_window_days         int | null       -- 60 for IMCC/SES; 12wk for DRC
```

> **Storing all three correlation-scenario results, not only the binding one, is a deliberate design choice.** `MAR21.7` sets capital to the maximum of medium, high and low. Which scenario binds is itself informative: a book where **low** binds is hedge-heavy, and a shift in which scenario binds is a real change in portfolio character that the single capital number conceals entirely ([17 §6.5](17_FRTB_Standardised_Approach.md)).

---

## 9. Limits

Full contract in [21 §11](21_Market_Risk_Limits.md).

```
limit:      limit_id, scope_type, scope_id, metric, dimension, limit_value,
            unit, limit_type {HARD, SOFT, ADVISORY}, trigger_level,
            approver, effective_from, effective_to, review_date, rationale

limit_utilisation:
            business_date, limit_id, measured_value, utilisation, status

breach:     breach_id, limit_id, business_date, measured_value, limit_value,
            breach_type {ACTIVE, PASSIVE, TECHNICAL, REPORTING, PERSISTENT},
            root_cause, remediation_plan, escalated_to, approved_excess
```

---

## 10. The cross-cutting requirements

These four apply to **every** entity above, and they are what separate a risk data model from a reporting database.

### 10.1 Bi-temporality

Every fact carries **two** dates:

| Date | Meaning |
|---|---|
| `business_date` | The date the fact is *about* |
| `knowledge_date` | The date the fact was *known* |

**Why both are required.** A price is corrected three days later. *"What did we report that day?"* needs the data as it was known then. *"What was actually true?"* needs the correction. A single-temporal store answers exactly one of those, and the other question is the one a supervisor asks when reviewing a backtesting exception.

### 10.2 Lineage

Every derived number stores the identifiers of its inputs. The chain must run unbroken:

```
   capital number → risk result → sensitivity → valuation
                  → curve → market data point → source
```

BCBS 239's principles on **accuracy and integrity**, **completeness** and **adaptability** are, in practice, a requirement for exactly this.

### 10.3 Versioning

Model versions, curve build versions, decomposition versions and limit versions must all be **pinned per business date**. A number that cannot be reproduced because the code changed is not auditable, and a residual trend that coincides with a version change is a methodology artefact rather than a finding ([14 §8](14_PnL_and_PnL_Explain.md)).

### 10.4 Status is explicit, never implied by absence

| Field | Why it must exist |
|---|---|
| `valuation_status` | A failed valuation is not a zero valuation |
| `validation_status` | A proxied price is not an observed price |
| `scenarios_missing` | A short scenario set is not a full one |
| `unmapped_factor_count` | An incomplete stress is not a complete one |
| `modellability_status` | An NMRF is not a modellable factor |

> **The single unifying principle of this model: absence must never be silently equivalent to zero.** Every one of the "common implementation errors" tables throughout this library reduces, at root, to some system treating a missing thing as a zero thing.

---

## 11. Worked lineage trace

A reported figure and the chain beneath it:

```
   FRTB SBM GIRR delta capital, USD Rates desk, 2026-08-24 = $11,376,040
     │
     ├─ binding scenario: LOW  (medium $11,313,195; high $11,250,000)
     │
     ├─ bucket: USD (MAR21.41 — one bucket per currency)
     │    ├─ WS(2y)  = +5,200,000   ← DV01 +40,000/bp × RW 1.3% (MAR21.42)
     │    ├─ WS(5y)  = +9,350,000   ← DV01 +85,000/bp × RW 1.1%
     │    └─ WS(10y) = −3,300,000   ← DV01 −30,000/bp × RW 1.1%
     │
     ├─ each DV01 ← sensitivity rows
     │       computation_method = BUMP_CENTRAL, bump_size = 1bp,
     │       sign_convention = LOSS_ON_RISE
     │
     ├─ each sensitivity ← valuation (pricing_model_version = "SWAP-4.2.1")
     │
     ├─ each valuation ← curve USD.SOFR.OIS (build_version = "BOOT-2026.3")
     │
     └─ curve ← 47 market_data_points, all validation_status = PASS,
                knowledge_date = 2026-08-24, snapshot = 16:00 NY
```

**Any number in that chain can be challenged, and every one of them can be answered.** That is the deliverable.

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Bi-temporal** | Every fact carries business and knowledge dates |
| 2 | **Lineage unbroken** | Capital traces to source market data |
| 3 | **Versions pinned** | Model, curve, decomposition versions stored per date |
| 4 | **Failed valuations visible** | `FAILED` is a status, never a zero PV |
| 5 | **Sensitivity metadata** | Method, bump size and sign convention on every row |
| 6 | **P&L types separate** | APL, HPL, RTPL as distinct records with their own flags |
| 7 | **Time-effect consistency** | Same treatment across APL, HPL, RTPL (`MAR32.28`) |
| 8 | **Pricing model set** | Identical for APL and HPL (`MAR32.29`) |
| 9 | **Desk definition** | One head, documented strategy, reporting lines (`MAR12`) |
| 10 | **Capital approach derived** | Never an independently-editable field |
| 11 | **All three SBM scenarios stored** | Not only the binding one |
| 12 | **Modellability versioned** | Quarterly status changes retained |
| 13 | **Issuer parent linkage** | Enforces the `MAR21.74` market-cap rule |
| 14 | **Sector scheme recorded** | A market-standard scheme, per `MAR21.52` |
| 15 | **Book designation** | Rationale and inception timestamp stored (`RBC25.5`, `RBC25.13`) |
| 16 | **Real price tagging** | Observations linked to risk factors for the RFET |
| 17 | **Missing counts surfaced** | `scenarios_missing`, `unmapped_factor_count` reported |
| 18 | **Quantile convention** | Stored on every VaR/ES result |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Single-temporal storage | Cannot reconstruct what was reported on the day |
| Overwriting modellability status | Prior-quarter capital irreproducible |
| Failed valuations stored as zero | Value **and** risk silently removed |
| Sensitivity without method/bump/sign | Reconciliation breaks become unresolvable |
| One P&L table with a type flag | Different exclusion rules collapse into one; PLA becomes invalid |
| `capital_approach` as an editable field | A desk capitalised on a model it has lost |
| Only the binding SBM scenario stored | The portfolio-character signal is lost |
| Reference data treated as static | Wrong FRTB buckets, wrong risk weights |
| Summing related entities for market cap | Contradicts `MAR21.74` |
| Local sector scheme | Contradicts `MAR21.52`'s market-standard requirement |
| No book-designation timestamp | Cannot evidence `RBC25.5` compliance |
| Position without trade lineage | P&L attribution to new trades impossible |
| Curve without `input_point_ids` | Lineage chain broken at the most-challenged link |

---

## 14. Limitations

- **This is conceptual.** Physical design — normalisation depth, partitioning, columnar vs row storage, in-memory caching — depends on volume, latency and the query mix, and none of that is prescribed here.
- **Bi-temporality is expensive** in storage and in query complexity. The cost is real; so is the cost of not having it during a supervisory review.
- **Full lineage at position × risk-factor × scenario granularity generates very large volumes.** Most institutions retain full granularity for a bounded window and aggregate beyond it — which is a defensible trade-off provided the retention period is a documented decision rather than an accident.
- **The model says nothing about latency.** Intraday risk requires a different physical architecture from end-of-day batch, over the same conceptual entities — see [25](25_Risk_System_Architecture.md).

---

## 15. Related Concepts

- [23 — Market Data and Curves](23_Market_Data_and_Curves.md) · [25 — Risk System Architecture](25_Risk_System_Architecture.md)
- [14 — P&L and P&L Explain](14_PnL_and_PnL_Explain.md) · [21 — Market Risk Limits](21_Market_Risk_Limits.md)
- [40 — Implementation Pseudocode and Data Contracts](40_Implementation_Pseudocode_and_Contracts.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25`, `MAR12`, `MAR21`, `MAR31`–`MAR33` entity and field requirements |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Accuracy, completeness, timeliness, adaptability, lineage |

> **Note on sourcing.** Basel prescribes *what must be calculated and evidenced*, not a data model. The entities, keys and relationships here are a design reference derived from those requirements, not a regulatory schema.

*Accessed 25 August 2026.*
