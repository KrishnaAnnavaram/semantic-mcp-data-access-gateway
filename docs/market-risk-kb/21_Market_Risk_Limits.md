# 21 — The Market Risk Limit Framework

**Level:** 9 · **Prerequisites:** [04](04_Interest_Rate_Risk.md)–[13](13_Stress_Testing.md) · **Feeds:** [27](27_Controls_and_Governance.md), [28](28_Reporting_and_Dashboards.md), [42](42_Risk_Aggregation.md)

---

## 1. Plain English

**A limit is a pre-agreed maximum on how much risk a desk may take. Measurement tells you where you are; limits tell you where you may go.**

> The limit framework is where risk measurement becomes risk *management*. A bank that measures risk beautifully and constrains nothing has an expensive reporting function, not a risk function.

---

## 2. Banking example

A government bond desk holds:

| | |
|---|---|
| DV01 limit | **$500,000/bp** |
| Current DV01 | **$420,000/bp** |
| Utilisation | **84%** |

The trader wants to add $100m of 10-year, adding roughly $85,000/bp.

```
   420,000 + 85,000  =  505,000  >  500,000     →  BREACH
```

The trade cannot be done as proposed. Three legitimate responses: reduce the size; hedge elsewhere on the curve to offset; or request a temporary limit increase through the governance process — **before** trading, not after.

> **The value of the limit is entirely in the fact that the conversation happens beforehand.** A limit discovered to be breached at end of day has already failed at its primary job.

---

## 3. Why limits exist

| Purpose | Mechanism |
|---|---|
| **Bound the loss** | Cap risk so a bad outcome remains survivable |
| **Allocate risk appetite** | Distribute a finite firm-wide appetite across businesses |
| **Force a conversation** | Sizeable risk increases require someone senior to agree |
| **Detect change** | A sudden utilisation jump signals a strategy change or a booking error |
| **Constrain concentration** | Prevent risk piling into one name, tenor, country or factor |
| **Satisfy governance** | Boards set appetite; limits are how appetite becomes operational |

---

## 4. The limit hierarchy

```
   BOARD RISK APPETITE                        set annually, in the RAS
        │
        ▼
   BANK-WIDE LIMITS                           VaR, stress, capital
        │
        ▼
   DIVISION                                   e.g. Global Markets
        │
        ▼
   BUSINESS LINE                              e.g. Fixed Income
        │
        ▼
   TRADING DESK                               e.g. USD Rates          ◄── the binding level
        │
        ▼
   PORTFOLIO / BOOK
        │
        ▼
   TRADER / SUB-LIMIT
```

### 4.1 Sub-limits do not sum to the parent

**A parent limit is deliberately less than the sum of its children.** Two reasons, pulling in the same direction:

1. **Diversification is real** — desks do not all lose on the same day, so the parent's risk is genuinely less than the sum of the parts.
2. **Full simultaneous utilisation is not expected** — allocating 100% of a parent limit across children guarantees the parent is breached whenever every child is fully used.

The gap between `Σ children` and `parent` is the **management buffer**, and setting it is a judgement about how correlated the desks' positions actually are.

> **The corollary is a governance requirement, not an accident:** a firm-wide limit can be breached while **no** desk is in breach. The framework must monitor at every level independently, and a "no desk breaches" report is not evidence that the firm is within appetite.

---

## 5. The limit catalogue

### 5.1 Statistical limits

| Limit | Metric | Level | Frequency | Purpose |
|---|---|---|---|---|
| **VaR limit** | 99% or 95% 1-day VaR | All levels | Daily | Bound normal-conditions loss |
| **ES limit** | 97.5% ES | Desk, firm | Daily | Bound tail loss |
| **Stress loss limit** | Worst named scenario | Desk, firm | Daily/weekly | Bound crisis loss |
| **Economic capital limit** | Internal capital | Business, firm | Monthly | Bound capital consumption |

### 5.2 Sensitivity limits

| Limit | Metric | Typical granularity |
|---|---|---|
| **DV01 / PV01** | Currency per bp | By currency **and** tenor bucket |
| **Key-rate DV01** | Per bp per bucket | Per vertex |
| **CS01** | Currency per bp | By rating, sector, issuer, tenor |
| **Vega** | Currency per vol point | By expiry, and often by strike |
| **Gamma** | Delta per unit | Especially near expiry |
| **Delta** | Currency or shares | By name and sector |
| **Theta** | Currency per day | Bounds the cost of long optionality |
| **Basis** | Currency per bp | Per basis pair |

### 5.3 Exposure and position limits

| Limit | Metric | Constrains |
|---|---|---|
| **Net exposure** | Long − short | Directional bet |
| **Gross exposure** | Long + short | **Leverage and operational scale** |
| **Notional** | Contract notional | Simple size cap; common for new products |
| **FX net open position** | Per currency and aggregate | Currency exposure |
| **Issuer limit** | Per obligor | Single-name concentration |
| **Sector / country limit** | Per grouping | Correlated concentration |
| **Tenor limit** | Per maturity bucket | Curve concentration |
| **Concentration** | Position vs ADV or market depth | **Liquidation risk** |

### 5.4 Loss limits

| Limit | Trigger | Consequence |
|---|---|---|
| **Daily stop-loss** | One-day loss threshold | Review; often forced reduction |
| **Cumulative / drawdown stop-loss** | Rolling or MTD/YTD loss | Escalating action, up to closing the book |
| **Management action trigger (MAT)** | An intermediate loss level | Mandatory review **before** the hard stop |

> **Stop-loss limits are different in kind from every other limit here.** All the others constrain *risk taken*. A stop-loss constrains *losses realised* — it is backward-looking, and it can force liquidation into precisely the market that caused the loss. Well-designed frameworks pair a hard stop-loss with an earlier MAT, so the first response is a conversation rather than a forced sale.

---

## 6. Hard, soft and advisory

| Type | Meaning | Breach response |
|---|---|---|
| **Hard limit** | Must not be exceeded | Immediate reduction; escalation; formal record |
| **Soft limit** | May be exceeded with pre-approval | Approval required before, or immediately after |
| **Advisory / trigger** | Early-warning level (e.g. 80% of hard) | Notification and review, no action required |

A mature framework uses all three. **Triggers set at 70–80% utilisation are what prevent a breach from being the first signal**, and a framework with hard limits and no triggers will generate breaches that could have been anticipated days earlier.

---

## 7. Setting limits

### 7.1 The three approaches

| Approach | Method | Strength | Weakness |
|---|---|---|---|
| **Top-down** | Cascade board appetite downward | Consistent with appetite | May ignore business reality |
| **Bottom-up** | Aggregate what desks need to run their business | Operationally realistic | May exceed appetite |
| **Risk-adjusted return** | Allocate to where risk earns most | Economically efficient | Rewards recent performance; procyclical |

**In practice all three run simultaneously**, and the limit framework is the negotiated result. The board sets the envelope; businesses bid for allocation; risk challenges.

### 7.2 Calibration inputs

| Input | Question |
|---|---|
| **Historical utilisation** | What has the desk actually used? |
| **Business plan** | What does the strategy require? |
| **Stress results** | What does the limit imply in a crisis? |
| **Capital consumption** | What does it cost in FRTB terms? |
| **Liquidity** | Can the position be exited within the assumed horizon? |
| **P&L volatility** | Is the limit consistent with observed earnings variability? |

> **The stress cross-check is the one most often skipped and most often decisive.** A DV01 limit of $500,000/bp implies a **$100m** loss under a 200bp parallel shock. If the board's stress appetite for that desk is $50m, the DV01 limit is inconsistent with the stress limit and one of them is wrong. **Limits must be calibrated as a coherent set, not instrument by instrument.**

---

## 8. Breach management

### 8.1 The workflow

```
   BREACH DETECTED
        │
        ▼
   CLASSIFY  ────────────────────────────────────────────┐
        │                                                │
   ┌────┴────┬──────────────┬──────────────┐             │
   ▼         ▼              ▼              ▼             │
 ACTIVE   PASSIVE      TECHNICAL      REPORTING          │
 (trade   (market      (data or       (a limit           │
  caused  moved)       system error)   error)            │
  it)                                                    │
   │         │              │              │             │
   └────┬────┴──────────────┴──────────────┘             │
        ▼                                                │
   NOTIFY  — desk head, market risk, and up the chain    │
        │       within a defined, short time             │
        ▼                                                │
   REMEDIATE                                             │
        ├─ reduce the position                           │
        ├─ hedge the excess                              │
        ├─ obtain a temporary increase (approved)        │
        └─ correct the data / limit                      │
        │                                                │
        ▼                                                │
   RECORD, REVIEW, and analyse for trends ◄──────────────┘
```

### 8.2 The classification matters

| Type | Cause | Typical severity |
|---|---|---|
| **Active** | The desk traded into it | **Most serious** — a control failure |
| **Passive** | The market moved; position unchanged | Less serious, but must still be remediated |
| **Technical** | Bad market data, system fault, mis-booking | A data-quality issue, not a risk-taking issue |
| **Reporting** | The limit itself was set or loaded wrongly | A governance issue |

> **An active breach and a passive breach are different events and must not be reported as one number.** A rise in *passive* breaches means the market got more volatile. A rise in *active* breaches means the pre-trade control is failing. Conflating them destroys the diagnostic value of the breach statistic entirely.

### 8.3 Escalation

Escalation should be defined by **severity and duration**, not left to judgement in the moment:

| Level | Typical trigger |
|---|---|
| Desk head + market risk officer | Any breach, immediately |
| Business head + head of market risk | Material breach, or unremediated beyond a set period |
| CRO | Significant breach, or a persistent pattern |
| Risk committee / board | Firm-level breach, or repeated significant breaches |

**Every breach must be recorded regardless of how quickly it is cured.** A breach cured within the hour is still a breach and still evidence about the control environment. Frameworks that permit same-day cures to go unrecorded lose exactly the data needed to detect a deteriorating desk.

---

## 9. Worked example — a desk limit pack

**USD Rates Trading Desk**

| Limit | Limit | Current | Util. | Status |
|---|---|---|---|---|
| **99% 1-day VaR** | $8,000,000 | $6,240,000 | 78% | 🟡 near trigger |
| **97.5% ES** | $10,000,000 | $7,850,000 | 79% | 🟡 |
| **Stress loss** (2022 rate shock) | $60,000,000 | $41,200,000 | 69% | 🟢 |
| **Total DV01** | $500,000/bp | $420,000/bp | 84% | 🟡 |
| — 0–2y bucket | $150,000/bp | $88,000/bp | 59% | 🟢 |
| — 2–10y bucket | $350,000/bp | $310,000/bp | 89% | 🟠 **approaching** |
| — 10y+ bucket | $200,000/bp | $22,000/bp | 11% | 🟢 |
| **Curve (2s10s)** | $120,000/bp | $95,000/bp | 79% | 🟡 |
| **Vega** | $250,000/vol pt | $310,000/vol pt | **124%** | 🔴 **BREACH** |
| **Daily stop-loss** | $12,000,000 | $3,100,000 | 26% | 🟢 |
| **MTD drawdown** | $35,000,000 | $9,400,000 | 27% | 🟢 |

### 9.1 Reading the pack

**The vega breach is the headline** — 124% utilisation. First questions, in order:

1. **Active or passive?** Did the desk sell more optionality, or did the vega grow because spot moved into a higher-vega region of the book? Both produce the same number and require different responses.
2. **Where is it concentrated?** Vega must be bucketed by expiry — a total vega breach concentrated in one expiry is a different problem from one spread evenly.
3. **What is the remediation and by when?**

**The second observation is subtler and is what a good reviewer catches.** Total DV01 is at 84%, but the **2–10y bucket is at 89%** while the 10y+ bucket is at 11%. The aggregate looks comfortable; the risk is concentrated in the belly. **This is [04 §5.2](04_Interest_Rate_Risk.md)'s point realised in a limit pack: the scalar conceals the ladder.**

**The third is the coherence check.** Stress loss is at 69% of a $60m limit, with a DV01 of $420,000/bp. A 200bp parallel shock on that DV01 alone is **$84m** — above the stress limit. The stress figure is lower because the scenario is not a pure parallel shock and the book has offsetting curve positions. **That is fine, but it should be understood rather than assumed**: if the desk flattened its curve position, its stress utilisation would jump sharply without any change in DV01.

---

## 10. Pseudocode

```
FUNCTION check_limits(positions, limits, market_data, as_of):
    results = []

    FOR limit IN limits:
        current = compute_metric(limit.metric, positions, market_data,
                                 scope = limit.scope)      # desk / book / firm
        util    = current / limit.value

        status = ( "BREACH"     IF util > 1.00
              ELSE "APPROACHING" IF util > limit.trigger_level   # e.g. 0.80
              ELSE "OK" )

        IF status == "BREACH":
            prior     = get_prior_value(limit, as_of - 1)
            traded    = position_changed_since(limit.scope, as_of - 1)
            breach_type = ( "ACTIVE"  IF traded
                       ELSE "PASSIVE" IF prior <= limit.value
                       ELSE "PERSISTENT" )

            raise_breach(limit, current, breach_type,
                         escalate_to = escalation_path(limit, util))

        results.append({ "limit": limit.id, "value": current,
                         "limit_value": limit.value, "utilisation": util,
                         "status": status })

    # A parent can breach with NO child in breach — check every level
    FOR level IN hierarchy_levels:
        check_aggregate_limits(level, positions, market_data)

    RETURN results


FUNCTION pre_trade_check(proposed_trade, positions, limits, market_data):
    hypothetical = positions + proposed_trade
    after  = check_limits(hypothetical, limits, market_data, today)
    breaches = [r for r in after if r.status == "BREACH"]
    IF breaches:
        RETURN { "allowed": FALSE, "breaches": breaches,
                 "action": "reduce size, hedge, or seek approval BEFORE trading" }
    RETURN { "allowed": TRUE }
```

---

## 11. Data contract

**Limit definition**

```
limit:
    limit_id              string
    scope_type            enum {TRADER, BOOK, DESK, BUSINESS, DIVISION, ENTITY, FIRM}
    scope_id              string
    metric                enum {VAR, ES, STRESS, DV01, KRD01, CS01, VEGA, GAMMA,
                                DELTA, THETA, NET_EXP, GROSS_EXP, NOTIONAL, NOP,
                                ISSUER, SECTOR, COUNTRY, CONCENTRATION,
                                STOP_LOSS, DRAWDOWN}
    dimension             string | null      # currency, tenor bucket, rating, name
    limit_value           decimal
    unit                  enum
    limit_type            enum {HARD, SOFT, ADVISORY}
    trigger_level         decimal            # e.g. 0.80
    approver              string
    effective_from        date
    effective_to          date | null
    review_date           date
    rationale             text               # REQUIRED
```

**Breach record**

```
breach:
    breach_id             string
    limit_id              string
    business_date         date
    measured_value        decimal
    limit_value           decimal
    utilisation           decimal
    breach_type           enum {ACTIVE, PASSIVE, TECHNICAL, REPORTING, PERSISTENT}
    detected_at           timestamp
    notified_at           timestamp
    root_cause            text               # REQUIRED
    remediation_plan      text               # REQUIRED
    remediated_at         timestamp | null
    days_in_breach        int
    escalated_to          list<string>
    approved_excess       boolean
    approval_reference    string | null
```

> `rationale` and `root_cause` are mandatory fields, not optional commentary. A limit with no recorded rationale cannot be reviewed intelligently at its review date, and a breach with no recorded root cause contributes nothing to trend analysis.

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Coverage** | Every material risk in every desk has a limit |
| 2 | **Coherence** | Sensitivity limits imply losses consistent with stress limits (§7.2) |
| 3 | **Hierarchy** | Every level monitored independently; parent breaches detected with no child breach |
| 4 | **Buffer** | `Σ children > parent`, deliberately and documented |
| 5 | **Granularity** | Bucketed limits exist where a scalar would conceal the ladder |
| 6 | **Pre-trade check** | Available and used before execution, not only end of day |
| 7 | **Triggers** | Advisory levels set below hard limits |
| 8 | **Independence** | Limits set and monitored by risk, **not** by the desk |
| 9 | **Breach classification** | Active / passive / technical / reporting distinguished |
| 10 | **All breaches recorded** | Including same-day cures |
| 11 | **Escalation defined** | By severity and duration, in advance |
| 12 | **Root cause captured** | Mandatory on every breach |
| 13 | **Review cycle** | Every limit has a review date; stale limits flagged |
| 14 | **Approved excesses tracked** | Temporary increases logged with expiry |
| 15 | **Trend analysis** | Breach counts by type and desk trended, not just reported |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Sub-limits summing exactly to the parent | Parent breaches whenever children are fully used |
| Only aggregate limits, no buckets | Curve, tenor and name concentration invisible (§9.1) |
| End-of-day monitoring only | Intraday risk uncontrolled; breaches found after the fact |
| No pre-trade check | The limit conversation happens after the trade |
| Conflating active and passive breaches | Destroys the diagnostic value of the statistic |
| Same-day cures unrecorded | Control-environment deterioration undetectable |
| Limits set by the business | No independence; limits drift to accommodate positions |
| Never reviewing limits | Stale limits that no longer reflect strategy or appetite |
| Sensitivity limits set without a stress cross-check | Mutually inconsistent limit set |
| Stop-loss with no earlier MAT | Forced liquidation with no intermediate conversation |
| No expiry on temporary increases | Temporary becomes permanent without a decision |

---

## 14. Limitations

- **Limits constrain measured risk.** Anything the measurement misses — an unmapped factor, an NMRF, a basis nobody modelled — is unconstrained by construction.
- **A limit framework is only as good as the data feeding it.** A stale price produces an understated utilisation and a false sense of compliance.
- **Limits can be gamed.** A VaR limit rewards positions with small losses 99% of the time and catastrophic losses in the remainder — see [12 §2](12_Expected_Shortfall.md). A framework with a VaR limit and no stress or ES limit invites exactly that trade.
- **Stop-losses can be pro-cyclical**, forcing sales into a falling market.
- **Utilisation is not risk.** A desk at 30% of every limit may be running a large basis position that no limit captures.

---

## 15. Related Concepts

- [11 — VaR](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md) · [13 — Stress Testing](13_Stress_Testing.md)
- [27 — Controls and Governance](27_Controls_and_Governance.md) · [28 — Reporting and Dashboards](28_Reporting_and_Dashboards.md)
- [42 — Risk Aggregation](42_Risk_Aggregation.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR30` qualitative standards, including limit-related governance |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Aggregation and reporting principles underlying limit monitoring |

> **Note on sourcing.** Limit *structures* are institution-specific and are not prescribed by Basel. The catalogue, hierarchy and breach workflow in this document reflect common industry practice, not a regulatory requirement, and should be treated as a design reference rather than a standard. The governance expectations around them (independence, documentation, escalation) *are* supervisory expectations under `MAR30` and BCBS 239.

*Accessed 25 August 2026.*
