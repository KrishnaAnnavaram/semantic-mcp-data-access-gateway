# 44 — Roles: Front Office, Risk, Control and Assurance

**Level:** Practical · **Prerequisites:** [27](27_Controls_and_Governance.md), [43](43_Daily_Workflow.md)

> **Who calculates, who consumes, who verifies, who approves.** These are four different verbs, and the separation between them is what makes a number credible. A figure calculated, consumed, verified and approved by the same function is an assertion, not a control.

---

## 1. The functions

| Function | Line | Owns | Reports to |
|---|---|---|---|
| **Trader** | 1 | The position and its P&L | Desk head |
| **Desk head** | 1 | The desk's strategy, risk and results | Business head |
| **Front-office quant** | 1 | Pricing models used by the desk | Desk / FO quant head |
| **Desk risk manager** | 1 (embedded) | Day-to-day risk analysis for the desk | **Market risk**, not the desk |
| **Independent market risk** | **2** | Risk measurement, limits, challenge | CRO |
| **Product control** | **2** | P&L production, IPV, reserves | CFO |
| **Model validation** | **2** | Independent challenge of models | CRO / head of model risk |
| **Regulatory capital team** | **2** | Capital calculation and returns | CFO / CRO |
| **Treasury** | 1/2 | Funding, liquidity, structural positions | CFO / Treasurer |
| **Internal audit** | **3** | Assurance over lines 1 and 2 | Audit committee |
| **Regulator** | External | Supervision | — |

### 1.1 The reporting line that matters most

**The desk risk manager sits *with* the desk and reports *to* market risk.** That structure gives proximity without capture. Where the reporting line runs into the business, independence ends at the shared P&L — and it fails precisely when the challenge is expensive ([27 §1](27_Controls_and_Governance.md)).

`MAR30.8` makes the structural requirement explicit for IMA banks: the risk control unit must be *"a distinct unit of the bank that is separate from the unit that designs and implements the internal model."*

---

## 2. Who does what to each metric

**C** = calculates · **U** = consumes · **V** = verifies · **A** = approves

| Metric | Trader | Desk head | FO quant | Desk risk | Market risk | Product control | Capital | Validation | Audit | Regulator |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Position** | C | U | | V | V | **V** | U | | V | |
| **PV / valuation** | C | U | C | V | V | **V** | U | V | | |
| **DV01 / KRD** | U | U | | C | **C** | | U | V | | U |
| **CS01 / JTD** | U | U | | C | **C** | | U | V | | U |
| **Greeks** | U | U | C | C | **C** | | U | V | | |
| **Daily P&L (APL)** | U | U | | U | U | **C·V** | | | V | |
| **HPL / RTPL** | | | | | **C** | V | | V | | U |
| **P&L attribution** | U | **U** | | C | C | **V·A** | | | V | |
| **VaR / ES** | U | U | | U | **C** | | U | V | V | **U** |
| **Stress** | U | **U** | | U | **C** | | U | V | | **U** |
| **Limits** | U | U | | U | **C·V** | | | | V | U |
| **Breaches** | U | **U·A** | | C | **C·V** | | | | V | U |
| **Backtesting** | | | | | **C** | V | | **V** | V | **U·A** |
| **PLA test** | | | | | **C** | V | | **V** | V | **U·A** |
| **FRTB SA / IMA** | | U | | | V | | **C** | V | V | **U·A** |
| **RFET / NMRF** | | | | | V | | **C** | V | | **U·A** |
| **Model approval** | | | | | U | | | **C·V** | V | **A** |
| **Reserves / IPV** | | U | | | U | **C·V·A** | | | V | |
| **Risk appetite** | | U | | | C | | | | | U |

### 2.1 Reading the table

**Three patterns are worth noting explicitly.**

**Market risk calculates the risk metrics; the desk consumes them.** The desk does not compute its own official VaR. That separation is why the number can be used to constrain the desk.

**Product control owns P&L, and the desk consumes it.** The trader knows what they think they made; product control determines what was made. The **attribution** is where the two are reconciled — which is why product control both verifies **and** approves it.

**The regulator approves model use, and nothing else.** It consumes the outputs and approves the *permission*, not the numbers.

---

## 3. The four verbs, and why they must separate

| Verb | Meaning | Failure if merged |
|---|---|---|
| **Calculates** | Produces the number | — |
| **Consumes** | Makes decisions on it | If also calculates: no independent view |
| **Verifies** | Independently checks it | If also calculates: **no control at all** |
| **Approves** | Accepts it and its consequences | If also calculates: self-certification |

**The most common real-world merge is calculate + verify**, usually justified by "only the team that built it understands it." That justification is exactly the problem SR 26-2's **effective challenge** requirement addresses: the challenger must have *expertise*, *independence* **and the organisational standing to effect change** ([26 §3.7](26_Model_Risk_and_Validation.md)).

---

## 4. Where the functions collide

Four recurring tensions. **They are structural, not personal**, and a framework that pretends they do not exist handles them badly.

| Tension | Front office view | Second line view | Resolution mechanism |
|---|---|---|---|
| **The mark** | "The model price is right; the market is illiquid" | "It cannot be verified independently" | **IPV** + evidence hierarchy + valuation reserve ([27 §5](27_Controls_and_Governance.md)) |
| **The limit** | "The limit is too tight for the business plan" | "The limit reflects appetite" | Governance forum; **stress cross-check** ([21 §7.2](21_Market_Risk_Limits.md)) |
| **The model** | "The risk model overstates my risk" | "The model is what capital rests on" | **PLA test** — an objective, quantitative arbiter |
| **The breach** | "The market moved; not our doing" | "It is a breach either way" | **Active vs passive classification** — both recorded, treated differently |

> **The PLA test deserves particular credit as an institutional design.** It replaces an unwinnable argument about whether a risk model is "right" with a quantitative test on 250 days of data, with defined thresholds and a defined consequence. **Neither side gets to be persuasive.**

---

## 5. Escalation

```
   ISSUE DETECTED
        │
   ┌────┴─────────────────────────────────────────────────────────┐
   │  Level 1  Desk risk manager + trader                          │
   │           Same day. Most items resolve here.                  │
   ├───────────────────────────────────────────────────────────────┤
   │  Level 2  Desk head + market risk officer                     │
   │           Any breach; any material data or valuation issue.   │
   ├───────────────────────────────────────────────────────────────┤
   │  Level 3  Business head + head of market risk                 │
   │           Material breach; unremediated beyond a set period.  │
   ├───────────────────────────────────────────────────────────────┤
   │  Level 4  CRO                                                 │
   │           Significant breach; a persistent pattern;           │
   │           backtesting or PLA deterioration.                   │
   ├───────────────────────────────────────────────────────────────┤
   │  Level 5  Risk committee / Board                              │
   │           Firm-level breach; repeated significant breaches;   │
   │           model approval at risk.                             │
   └───────────────────────────────────────────────────────────────┘
```

**Escalation is defined by severity and duration in advance**, not judged in the moment. A path that depends on someone deciding whether to escalate will fail under exactly the pressure it exists for.

---

## 6. Responsibility for the regulatory obligations

| Obligation | Primary owner | Independent check |
|---|---|---|
| Book designation at inception (`RBC25.5`) | Front office | Product control; **annual internal audit** (`RBC25.13`) |
| Daily fair valuation (`RBC25.4`) | Front office | Product control |
| Trading desk definition (`MAR12`) | Business | Market risk |
| Daily ES per desk (`MAR33.2`) | **Market risk** | Validation |
| SA calculation and monthly reporting (`MAR20.2`) | **Capital team** | Market risk |
| Backtesting (`MAR32`) | **Market risk** | Validation; internal audit |
| Every exception documented (`MAR32.12`) | Market risk + desk | Internal audit |
| PLA test (`MAR32.35`+) | **Market risk** | Validation |
| RFET (`MAR31.13`) | **Capital team + data** | Validation |
| Real price observation capture (`MAR31.12`) | **Data / market data** | Capital team |
| Model validation (`MAR30`, SR 26-2, SS1/23) | **Model validation** | Internal audit |
| Independent risk control unit (`MAR30.8`) | Organisational design | Internal audit |
| Board involvement (`MAR30.12`) | Board | Internal audit |
| 10% IMA floor (`MAR32.2`) | Capital team | Market risk |

> **The two rows most often left unowned are `MAR31.12` real price capture and `MAR32.12` exception documentation.** Both are unglamorous, both are continuous, and both have direct consequences — the first drives NMRF capital, the second is the evidence base a supervisor reviews after a run of exceptions.

---

## 7. Skills by role

| Role | Must be fluent in | Learning path ([35](35_Beginner_to_Expert_Learning_Path.md)) |
|---|---|---|
| **Trader** | Instruments, sensitivities, carry/roll, Greeks, limits | L1–L5, L13 |
| **Desk risk manager** | All of the above + VaR, ES, stress, attribution | L1–L10, L13 |
| **Market risk analyst** | Sensitivities, VaR, ES, stress, limits, aggregation | L1–L13 |
| **Quant developer** | Pricing, Greeks, portfolio maths, data contracts, architecture | L1–L7, L14 |
| **Product control** | Valuation, P&L, attribution, IPV, reserves | L1–L5, L10 |
| **Capital specialist** | FRTB SA and IMA, DRC, NMRF, regulatory status | L1–L4, L11–L12, L16 |
| **Model validator** | Everything quantitative + validation frameworks | L1–L12, L15 |
| **Internal auditor** | Control design; governance; enough quantitative fluency to challenge | L1–L4, L13, L15 |

---

## 8. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Second line independent | No reporting line into the business it challenges |
| 2 | Desk risk manager reporting | Into market risk, not the desk |
| 3 | `MAR30.8` separation | Risk control unit distinct from model design |
| 4 | Limits set by risk | Never by the business |
| 5 | Model validation independent | Validator ≠ developer, enforced in the inventory |
| 6 | IPV sources independent | Obtained by product control, not supplied by the desk |
| 7 | Effective challenge | Expertise, independence **and standing to effect change** |
| 8 | Escalation predefined | By severity and duration |
| 9 | Every obligation owned | No unowned regulatory requirement |
| 10 | Board involvement evidenced | `MAR30.12` |
| 11 | Audit coverage | Both first and second line |
| 12 | Four verbs separated | No metric calculated and verified by the same function |

---

## 9. Common structural failures

| Failure | Consequence |
|---|---|
| Second line reporting into the business | Independence fails when challenge is expensive |
| Desk risk manager reporting to the desk | Proximity becomes capture |
| Validation by the model builders | No effective challenge; contradicts `MAR30.8` |
| Validation with no authority to compel change | Reports without remediation |
| Limits set by the business | Limits drift to accommodate positions |
| IPV using desk-supplied sources | Not independent verification |
| P&L sign-off without attribution | A signature that cannot catch anything |
| No named owner for real price capture | Avoidable NMRF capital |
| Escalation decided case by case | Fails under pressure |
| Internal audit covering only the first line | The second line is unassured |

---

## 10. Limitations

- **Organisational structures vary widely.** The functions here are near-universal; their names, groupings and reporting lines are not. Match by *responsibility*, not by title.
- **Independence is structural and cultural.** Correct reporting lines with no appetite for confrontation produce independence on paper only.
- **The RACI in §2 is a design reference**, not a regulatory requirement. Basel prescribes governance *outcomes* (`MAR30`, `RBC25.13`) and specific ownership only where it says so.
- **Small institutions cannot staff every role separately.** Where roles combine, the combination should be a documented, risk-assessed decision with compensating controls — not an accident of headcount.

---

## 11. Related Concepts

- [27 — Controls and Governance](27_Controls_and_Governance.md) · [43 — The Daily Workflow](43_Daily_Workflow.md)
- [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md) · [21 — Market Risk Limits](21_Market_Risk_Limits.md)
- [35 — Learning Path](35_Beginner_to_Expert_Learning_Path.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR30.8` independent risk control unit; `MAR30.12` board involvement; `RBC25.13` audit |
| Federal Reserve / OCC / FDIC | SR 26-2 | 17 Apr 2026 | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | Effective challenge; validation independence |
| Bank of England / PRA | SS1/23 | May 2023, effective 17 May 2024 | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss | Governance and independent validation principles |

*Accessed 25 August 2026.*
