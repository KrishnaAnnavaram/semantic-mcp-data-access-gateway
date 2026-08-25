# 27 — Market Risk Controls and Governance

**Level:** 12 · **Prerequisites:** [21](21_Market_Risk_Limits.md), [23](23_Market_Data_and_Curves.md) · **Feeds:** [43](43_Daily_Workflow.md), [44](44_Roles_and_Responsibilities.md)

> **A control is a step that can stop something.** A step that observes, records and reports but cannot halt anything is *monitoring*. Both are necessary; conflating them is how an institution comes to believe it is controlled when it is only informed.

---

## 1. The three lines

| Line | Who | Role |
|---|---|---|
| **First** | Trading desks, desk-aligned support | **Owns** the risk; operates day-to-day controls |
| **Second** | Independent market risk, product control, compliance | **Challenges** the first line; sets limits; validates |
| **Third** | Internal audit | **Assures** that lines one and two work as designed |

**The independence requirements are not organisational preference.** `MAR30.8` requires *"a distinct unit of the bank that is separate from the unit that designs and implements the internal model."* `MAR30.12` requires the board and senior management to be **actively involved** in the risk control process. `RBC25.13` requires internal control functions to conduct an **ongoing evaluation** of book designations, with **at least yearly internal audit**.

> **The most common structural failure is a second line that reports, through some path, to the business it challenges.** Independence that ends at a shared P&L is not independence, and it fails precisely when the challenge is expensive.

---

## 2. The control map, by stage

```
   TRADE CAPTURE       ─► completeness · authorisation · product permission
        │
   POSITION            ─► three-way reconciliation (FO ↔ risk ↔ ledger)
        │
   MARKET DATA         ─► validation gate · override control · source hierarchy
        │
   CURVE / SURFACE     ─► reprice inputs · forward sanity · arbitrage tests
        │
   VALUATION           ─► IPV · model approval · reserves · failed-price escalation
        │
   SENSITIVITY         ─► analytic vs bumped · completeness · reconciliation
        │
   P&L                 ─► attribution · residual threshold · sign-off
        │
   RISK MEASURES       ─► scenario completeness · backtesting · PLA
        │
   LIMITS              ─► pre-trade · post-trade · breach escalation
        │
   CAPITAL             ─► SA/IMA determination · quarterly gates · reporting
        │
   REPORTING           ─► accuracy · timeliness · distribution · attestation
```

---

## 3. Position and trade controls

### 3.1 The three-way reconciliation

**Front office ↔ risk system ↔ general ledger.** All three must agree, and disagreement is a gate, not a report.

| Break type | Typical cause | Why it matters |
|---|---|---|
| FO vs risk | Late booking; feed failure; mapping error | **Risk is being measured on the wrong book** |
| Risk vs ledger | Valuation difference; timing | P&L and risk describe different portfolios |
| FO vs ledger | Booking error; product setup | Accounting is wrong |

**Tolerances must be absolute and relative**, and both must be defended. A 0.01% tolerance on a $50bn book is $5m — which is not a rounding difference.

### 3.2 Unauthorised and off-system trading

The classic control set, each of which has failed somewhere:

| Control | What it catches |
|---|---|
| **Product permissions** per desk and trader | Trading outside mandate |
| **Counterparty confirmations**, independently matched | Fictitious or mis-booked trades |
| **Cancel-and-amend monitoring** | Repeated amendments used to defer recognition |
| **Off-market rate detection** | Trades booked away from market to move P&L |
| **Mandatory leave** | Positions that require daily manual intervention to conceal |
| **Nostro / cash breaks** | Trades whose cash does not settle as booked |
| **Internal trade matching** | Both sides of an internal transfer agree |

> **Every major unauthorised trading loss has involved a break that was visible and tolerated.** Not undetected — *tolerated*, usually because the break was small relative to the desk's revenue and the explanation was plausible. **An aged break with a recurring explanation is a finding, not a nuisance.**

---

## 4. Market data controls

Covered in depth at [23 §4](23_Market_Data_and_Curves.md). The control-specific points:

| Control | Requirement |
|---|---|
| **Validation is a gate** | Blocking failures **halt the batch** rather than annotate the output |
| **Source hierarchy** | Defined in advance, not chosen per point per day |
| **Override authorisation** | Four-eyes; value, reason, approver, timestamp, **expiry** |
| **Override ageing** | Aggregate count and age trended; expired overrides enforced |
| **Proxy register** | Every proxied point visible, with the reason and a review date |
| **Stale detection** | Unchanged values flagged — **staleness reduces measured risk** |

> **The staleness point is the one to internalise.** A carried-forward price produces a zero return. Zero returns entering a VaR history *reduce* measured volatility. **A market data failure therefore makes the risk number look better**, which means the failure is self-concealing and biased in the dangerous direction.

---

## 5. Valuation controls

### 5.1 Independent price verification (IPV)

**IPV is the second line independently verifying the front office's marks against external evidence.**

| Element | Requirement |
|---|---|
| **Frequency** | Typically month-end; more often for volatile or material books |
| **Independence** | Sources obtained by product control, not supplied by the desk |
| **Coverage** | Risk-based; material and illiquid positions prioritised |
| **Thresholds** | Differences above tolerance escalated and adjusted |
| **Documentation** | Sources, method and conclusion retained |

**The hierarchy of evidence:**

```
   1. Executed trades (the bank's own, and observable third-party)
   2. Committed quotes from independent market makers
   3. Consensus pricing services
   4. Indicative quotes / broker marks
   5. Model price with observable inputs
   6. Model price with unobservable inputs      ← weakest; largest reserve
```

> **The evidence hierarchy is the same one the RFET uses** ([20 §3.1](20_NMRF_and_Modellability.md)), for the same reason: a price is only as good as the market behind it. A position valued at level 6 that cannot be verified independently is also, very likely, a position whose risk factors will fail the RFET — the valuation and capital consequences arrive together.

### 5.2 Valuation adjustments and reserves

| Reserve | Addresses |
|---|---|
| **Bid-offer** | Exit cost from mid |
| **Model** | Uncertainty in model choice |
| **Concentration** | Position size relative to market depth |
| **Day-one P&L** | Profit recognised at inception on unobservable inputs |
| **Funding / XVA** | Funding and counterparty adjustments |

**Prudent valuation** requirements in some jurisdictions impose additional value adjustments (AVAs) above accounting fair value. These are a *capital* deduction, not an accounting adjustment, and the two are computed differently.

### 5.3 The failed-valuation rule

> **A position that fails to price is not worth zero. It is unknown, it must be escalated, and it must not be silently defaulted.**

This is stated in [03 §6](03_Pricing_Fundamentals.md), [24 §5](24_Risk_Data_Model.md) and [25 §4](25_Risk_System_Architecture.md), and it is repeated here because it is the single most dangerous defect a risk system can contain: it removes the value **and** the risk from every downstream report simultaneously, and nothing looks broken.

---

## 6. Sensitivity and risk-measure controls

| Control | Test |
|---|---|
| **Analytic vs bumped** | Closed-form and finite-difference sensitivities agree |
| **Completeness** | Every position produces every applicable sensitivity |
| **KRD reconciliation** | `Σ` bucketed ≈ parallel ([04 §5.4](04_Interest_Rate_Risk.md)) |
| **Metadata carried** | Method, bump size, sign convention on every row |
| **Scenario completeness** | Full lookback available; missing days **reported, not dropped** |
| **Unmapped factors** | Counted and reported on every stress result |
| **Sub-portfolio reconciliation** | `Σ` standalone VaR ≥ portfolio VaR |
| **Ghost-feature detection** | VaR jumps traced to window entry/exit, not reported as market moves |

---

## 7. P&L controls

| Control | Requirement | Source |
|---|---|---|
| **APL ties to the ledger** | Exact reconciliation | — |
| **Same pricing models** | APL and HPL use the same pricers, config, data and systems as the reported P&L | `MAR32.29` |
| **HPL static** | No intraday trading, no new or modified deals | `MAR32.25` |
| **Fees excluded** | From both APL and HPL | `MAR32.26` |
| **VA frequency** | All in APL; daily-updated only in HPL; **no smoothing** | `MAR32.27` |
| **Time effects consistent** | Same treatment across APL, HPL and RTPL | `MAR32.28` |
| **Attribution residual** | Threshold on a **gross** basis; commentary mandatory on breach | [14 §3.2](14_PnL_and_PnL_Explain.md) |
| **Every exception documented** | With a written explanation | `MAR32.12` |
| **Sign-off** | Desk head and product control, daily | — |

### 7.1 The sign-off is a control, not a formality

A desk head who signs off P&L is attesting that the number reflects the positions they believe they hold. **A signature obtained by circulating a spreadsheet nobody opens is monitoring dressed as control.** The test is whether a wrong number would be caught by the signer — which requires that the signer receive the attribution, not only the total.

---

## 8. Limit controls

Covered in [21 §8](21_Market_Risk_Limits.md). The governance essentials:

| Control | Requirement |
|---|---|
| **Independence** | Limits set and monitored by risk, **never** by the desk |
| **Pre-trade check** | Available and used before execution |
| **Breach classification** | ACTIVE / PASSIVE / TECHNICAL / REPORTING distinguished |
| **All breaches recorded** | **Including same-day cures** |
| **Escalation by severity and duration** | Defined in advance |
| **Root cause mandatory** | On every breach |
| **Temporary increases** | Approved, logged, with an **enforced expiry** |
| **Trend analysis** | Breach counts by type and desk, trended |

---

## 9. Change control

| Change type | Requirement |
|---|---|
| **Model change** | Validation review; approval; version pinned; impact quantified |
| **Curve build change** | Parallel run; impact on sensitivities and capital measured |
| **Limit change** | Approval at the appropriate level; effective date recorded |
| **Reference data change** | Four-eyes on FRTB-relevant fields (sector, rating, market cap) |
| **System change** | Test evidence; back-out plan; post-implementation review |
| **Methodology change** | Version recorded; historical series annotated |

> **Every change must be datable and reversible in reporting.** A P&L attribution residual that trends upward from a specific date, coinciding with a decomposition version change, is a methodology artefact rather than a model failure ([14 §8](14_PnL_and_PnL_Explain.md)) — and the only way to know that is a change log tied to business dates.

---

## 10. Governance forums

| Forum | Typical membership | Decides |
|---|---|---|
| **Board risk committee** | Non-executive directors | Risk appetite; escalated matters |
| **Executive risk committee** | CRO, CFO, business heads | Firm limits; material policy |
| **Market risk committee** | Head of market risk, desk heads, product control | Desk limits; breach resolution; methodology |
| **Model risk / validation committee** | Validation, model owners, risk | Model approval; findings; conditions |
| **Valuation committee** | Product control, finance, risk, front office | Reserves; IPV escalations; hierarchy classification |
| **New product approval** | Risk, legal, ops, finance, tax, front office | Whether the firm can support a product **before** it trades |

### 10.1 New product approval is a market risk control

**A product the risk system cannot represent is a product the bank cannot measure.** NPA is where that is caught, and the market risk sign-off should be a genuine gate covering:

- Can we **price** it, with a validated model?
- Can we compute its **sensitivities**?
- Do its risk factors **exist** in the factor set — and will they **pass the RFET**?
- Does it fall in the **RRAO** population?
- Which **regulatory book** does it belong in, and why?
- Can we **stress** it and **revalue** it fully?
- Which **limits** will constrain it?

> **The RFET question at NPA time is a recent and underused addition.** A product whose risk factors will be non-modellable carries an SES capital cost that is far easier to price into the approval decision than to discover a quarter later ([20](20_NMRF_and_Modellability.md)).

---

## 11. The control catalogue

| # | Control | Line | Frequency | Type |
|---|---|---|---|---|
| 1 | Trade capture completeness | 1 | Continuous | Preventive |
| 2 | Product permissions | 1 | Pre-trade | **Preventive** |
| 3 | Pre-trade limit check | 1 | Pre-trade | **Preventive** |
| 4 | Trade confirmation matching | 1/2 | Daily | Detective |
| 5 | Three-way position reconciliation | 2 | Daily | **Gate** |
| 6 | Market data validation | 2 | Daily | **Gate** |
| 7 | Override authorisation | 2 | On use | Preventive |
| 8 | Curve input repricing | 2 | Daily | **Gate** |
| 9 | Surface arbitrage tests | 2 | Daily | Detective |
| 10 | Failed valuation escalation | 2 | Daily | **Gate** |
| 11 | Independent price verification | 2 | Monthly+ | Detective |
| 12 | Valuation reserve calculation | 2 | Monthly | Detective |
| 13 | Analytic vs bumped sensitivities | 2 | Daily | Detective |
| 14 | KRD completeness reconciliation | 2 | Daily | Detective |
| 15 | P&L attribution residual | 2 | Daily | Detective |
| 16 | P&L sign-off | 1/2 | Daily | Detective |
| 17 | Post-trade limit monitoring | 2 | Daily/intraday | Detective |
| 18 | Breach escalation | 2 | On breach | Corrective |
| 19 | Backtesting | 2 | Daily | Detective |
| 20 | PLA test | 2 | Quarterly | **Gate** |
| 21 | RFET assessment | 2 | Quarterly (monitored monthly) | **Gate** |
| 22 | Model validation | 2 | By materiality | **Gate** |
| 23 | Book designation review | 2/3 | **At least yearly** | Detective |
| 24 | New product approval | 2 | Per product | **Gate** |
| 25 | Change control | 1/2 | Per change | Preventive |
| 26 | Internal audit review | 3 | Cyclical | Assurance |

**Nine of these are gates.** A framework in which every control is detective produces excellent post-mortems.

---

## 12. Key risk indicators

Governance needs leading indicators, not only outcome counts:

| KRI | Signals |
|---|---|
| **Active** breach count and trend | Pre-trade control effectiveness |
| Aged unresolved breaches | Remediation discipline |
| Reconciliation break count and **age** | Data and booking integrity |
| Manual override count and **age** | Data quality deterioration |
| P&L unexplained residual, trend and **sign persistence** | Model completeness |
| Backtesting exceptions vs expectation | Model calibration |
| PLA zone migrations | Model-to-portfolio fit |
| **NMRF count and SES trend** | Data sourcing effectiveness |
| Failed valuation count | Pricing coverage |
| Level 3 / unobservable position share | Valuation uncertainty |
| Open validation findings, by age and severity | Model risk posture |
| Stale market data points | Feed reliability |

> **Age matters more than count on almost every line.** Ten breaks opened and closed the same day is a functioning process. Two breaks open for ninety days is a broken one — and the second reports as the better number.

---

## 13. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Independence** | Second line does not report into the business it challenges |
| 2 | **`MAR30.8` separation** | Risk control unit distinct from model design/implementation |
| 3 | **Board involvement** | Evidenced, per `MAR30.12` |
| 4 | **Gates are gates** | Blocking failures halt processing |
| 5 | **Three-way reconciliation** | Daily, with absolute and relative tolerances |
| 6 | **Break ageing** | Tracked; aged breaks escalated |
| 7 | **Override expiry** | Enforced, not merely recorded |
| 8 | **IPV coverage** | Risk-based; material and illiquid prioritised |
| 9 | **Evidence hierarchy** | Applied and documented |
| 10 | **Failed valuations** | Escalated, never zeroed |
| 11 | **P&L pricing consistency** | Same models as reported P&L (`MAR32.29`) |
| 12 | **Every exception explained** | `MAR32.12` |
| 13 | **Breach classification** | Active vs passive distinguished |
| 14 | **Book designation audit** | At least yearly (`RBC25.13`) |
| 15 | **NPA gate** | Includes pricing, sensitivities, RFET, RRAO, book, limits |
| 16 | **Change control** | Every change dated, approved, quantified, reversible in reporting |
| 17 | **KRIs trended** | Age tracked, not only count |
| 18 | **Third line** | Audit coverage of both first and second line |

---

## 14. Common implementation errors

| Error | Consequence |
|---|---|
| Monitoring described as control | The institution believes it can stop things it cannot |
| Data validation that reports instead of blocking | Complete, timely, wrong numbers |
| Tolerating aged reconciliation breaks | The precondition of every major unauthorised trading loss |
| Overrides with no enforced expiry | Undocumented permanent model changes |
| Failed valuations defaulted to zero | Value and risk silently removed |
| IPV sources supplied by the desk | Not independent verification |
| P&L sign-off without attribution | A signature that cannot catch anything |
| Same-day breach cures unrecorded | Deterioration undetectable |
| Second line reporting into the business | Independence fails when challenge gets expensive |
| NPA without an RFET question | Unexpected NMRF capital a quarter later |
| KRIs reported as counts only | Aged items look better than fresh ones |
| Change log not tied to business dates | Methodology artefacts mistaken for model failures |

---

## 15. Limitations

- **Controls are only as good as the tolerance they enforce.** A tolerance set wide enough never to fail is not a control.
- **Detective controls find problems after they have happened.** The nine gates in §11 are where prevention actually occurs; everything else is remediation.
- **Independence is structural but also cultural.** A second line with the right reporting line and no appetite for confrontation is independent on paper only.
- **Control frameworks are institution-specific.** Basel prescribes governance *outcomes* (`MAR30`, `RBC25.13`) and BCBS 239 prescribes data principles; the control set here is industry practice derived from them, not a standard.
- **No control set anticipates every failure.** The point of KRIs and trend analysis is to detect deterioration in conditions the framework was not designed for.

---

## 16. Related Concepts

- [21 — Market Risk Limits](21_Market_Risk_Limits.md) · [23 — Market Data and Curves](23_Market_Data_and_Curves.md)
- [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md) · [43 — The Daily Workflow](43_Daily_Workflow.md)
- [44 — Roles and Responsibilities](44_Roles_and_Responsibilities.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25.13` designation audit; `MAR30.8` independence; `MAR30.12` board involvement; `MAR32.12`, `MAR32.25`–`MAR32.29` |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Governance, data architecture, accuracy, timeliness |
| Federal Reserve / OCC / FDIC | SR 26-2, *Revised Guidance on Model Risk Management* | 17 Apr 2026 | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | Effective challenge; governance and controls |
| Bank of England / PRA | SS1/23 – *Model risk management principles for banks* | May 2023, effective 17 May 2024 | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss | Governance principle |

> **Note on sourcing.** Basel and the agencies prescribe governance outcomes and specific requirements; the control catalogue, KRI set and forum structure here reflect common industry practice derived from them and are a design reference, not a standard.

*Accessed 25 August 2026.*
