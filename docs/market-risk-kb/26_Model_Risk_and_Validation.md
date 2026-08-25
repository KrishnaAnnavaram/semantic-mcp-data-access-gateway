# 26 — Model Risk and Model Validation

**Level:** 13 · **Prerequisites:** [11](11_VaR.md)–[20](20_NMRF_and_Modellability.md) · **Feeds:** [27](27_Controls_and_Governance.md), [44](44_Roles_and_Responsibilities.md)

> ### ⚠ Regulatory status alert — the US guidance changed in 2026
>
> **SR 11-7 has been superseded.** On **17 April 2026** the Federal Reserve, OCC and FDIC jointly issued **SR 26-2, *Revised Guidance on Model Risk Management***, which *"supersedes and replaces SR letter 11-7, Guidance on Model Risk Management (issued April 4, 2011) and SR letter 21-8, Interagency Statement on Model Risk Management for Bank Systems Supporting Bank Secrecy Act/Anti-Money Laundering Compliance (issued April 9, 2021)."*
>
> A great deal of published material — including most training decks, vendor documentation and internal policy written before mid-2026 — still cites SR 11-7 as current. **It is not.** The substance is broadly continuous, but the scope, the definition of "model", the tailoring and the AI carve-out are all materially different, and those differences are set out in §3 below.

---

## 1. Plain English

**Model risk is the risk of loss from using a wrong model, or from using a right model wrongly.**

Both halves matter, and the second is the one institutions underestimate. A perfectly sound VaR model applied to a portfolio it was never designed for, or relied upon by a decision-maker who does not understand its assumptions, produces model risk despite being a good model.

SR 26-2 makes the point explicitly:

> *"even a fundamentally sound model producing accurate outputs consistent with the model's design objective can exhibit high model risk if it is misapplied or misused."*

---

## 2. Banking example

A bank's VaR model uses a 250-day lookback with equal weighting.

Markets have been calm for eighteen months. The model's window contains no stress, so:

| | |
|---|---|
| Reported 99% 1-day VaR | $4m |
| VaR under a window including the last crisis | $19m |
| Backtesting result | **Zero exceptions in 250 days** — apparently excellent |

**The model is passing every test it is being given and is describing a world that no longer applies.** Nothing in the backtest can reveal this, because backtesting compares the model to the same calm period that calibrated it.

This is the case for which independent validation exists. **The failure is not statistical; it is conceptual** — a lookback window choice that embeds an assumption nobody re-examined.

---

## 3. The current US guidance — SR 26-2

### 3.1 Status

| Field | Value |
|---|---|
| **Guidance** | *Supervisory Guidance on Model Risk Management* |
| **SR letter** | **SR 26-2** |
| **Jurisdiction** | United States |
| **Issued by** | Board of Governors of the Federal Reserve System, **OCC**, **FDIC** — jointly |
| **Date** | **17 April 2026** |
| **Status** | **Current** |
| **Supersedes** | SR 11-7 (4 April 2011); SR 21-8 (9 April 2021) |
| **Applicability** | *"expected to be most relevant to banking organizations with over $30 billion in total assets"* |
| **Enforceability** | *"This guidance does not set forth enforceable standards or prescriptive requirements; accordingly, non-compliance with this guidance will not result in supervisory criticism"* — **but** *"supervisory action may result for any violations of law or unsafe or unsound practices stemming from insufficient management of model risk"* |
| **Latest verification** | 25 August 2026 |

### 3.2 The $30 billion threshold

**This is new and material.** Models used by banking organizations with **$30 billion or less** in total assets *"typically are subject to internal risk management and governance practices appropriate for the size and risk profile of these banking organizations, and generally excluding them from this guidance is consistent with a tailored supervisory approach."*

The guidance notes it *may* still be relevant to smaller organisations with significant model risk exposure *"because of the prevalence and complexity of their models or because of activities outside the scope of traditional community banking."*

### 3.3 The definition of "model" — narrowed

> *"the term 'model' refers to a **complex quantitative method, system, or approach that applies statistical, economic, or financial theories to process input data into quantitative estimates**."*

**Explicitly excluded:**

- **simple arithmetic calculations, such as those found within spreadsheets**
- **deterministic rule-based processes**
- **software where there are no statistical, economic, or financial theories underpinning their design or use**

> **This is a meaningful narrowing.** A great deal of effort under the SR 11-7 regime went into inventorying spreadsheets and rule engines as "models." SR 26-2 draws the line at whether a statistical, economic or financial *theory* underpins the tool. **This does not mean such tools are unmanaged** — it means they are managed under general risk management and controls rather than the model risk framework.

### 3.4 The AI carve-out

Footnote 3 is important and specific:

> *"**Generative AI and agentic AI models are novel and rapidly evolving. As such, they are not within the scope of this guidance.** Nonetheless, a banking organization's risk management and governance practices should guide the determination of appropriate governance and controls for any tools, processes, or systems not covered in this document. However, the principles described in this guidance apply to traditional statistical and quantitative models and **non-generative, non-agentic AI models**."*

**Read that carefully.** Traditional statistical models: in scope. Non-generative, non-agentic AI/ML models: **in scope**. Generative and agentic AI: **out of scope of this guidance**, but not out of scope of risk management generally.

### 3.5 The four drivers of model risk

SR 26-2 decomposes model risk into components, which is a more structured framing than its predecessor:

| Driver | Definition |
|---|---|
| **Inherent risk** | *"the assumptions made in developing the model, the model's complexity, the quality of inputs for the model, and data constraints."* Increases with complexity and with the criticality or number of assumptions |
| **Model exposure** | *"the significance of the model output to a banking organization's business decisions"* — greater for larger portfolios or larger business impact. **Quantitatively measurable** (e.g. by portfolio size) |
| **Model purpose** | A **qualitative** consideration. Models *"developed to help meet regulatory requirements or manage a banking organization's financial risk exposures are generally considered to be of greater risk"* |
| **Model use** | Whether it is applied as designed |

And the composition rule:

```
   Model purpose  +  Model exposure   =   MODEL MATERIALITY

   Inherent risk  in the context of   MATERIALITY   =   MODEL RISK
```

**Consequence for practice:** models deemed immaterial *"may consist of identifying those models and monitoring model performance and conditions under which the use of those models may become material."* Models of higher materiality *"warrant more comprehensive and rigorous oversight."*

> **Note where a market risk model lands.** A VaR or ES model is used both to meet regulatory requirements *and* to manage financial risk exposures, and it typically has very large exposure. On SR 26-2's own logic it sits at the top of the materiality scale — which is why market risk models attract the most rigorous validation in most institutions.

### 3.6 Aggregate model risk

> *"Sound practice involves assessing model risk both individually and in aggregate. Aggregate risk reflects interactions and dependencies among models; reliance on common assumptions, data, or methodologies; and any other factors that could adversely affect several models and their outputs simultaneously."*

**This is the concentration problem applied to models.** If the VaR model, the stress engine, the CVA model and the FRTB engine all draw on the same curve builder and the same volatility surfaces, a defect in that shared foundation affects every one of them at once. Validating each model in isolation cannot detect it.

### 3.7 Effective challenge

> *"'effective challenge' … refers to the critical analysis conducted by objective experts who evaluate model risk and effect appropriate changes throughout the model lifecycle, from model development to ongoing monitoring."*

Three requirements, all of which must be present:

| Requirement | Meaning |
|---|---|
| **Appropriate expertise** | The challenger must be technically capable of the critique |
| **Sufficient independence** | To maintain objectivity |
| **Organizational standing and influence** | **To effect any change** |

> **The third is the one that fails in practice.** A validation function that is expert and independent but cannot compel remediation produces well-written reports and no change. Effective challenge that cannot effect anything is not effective challenge.

---

## 4. Validation under SR 26-2

### 4.1 What validation is for

> *"Model validation evaluates whether models perform as expected and includes an assessment of a model's reliability and its limitations."*

Validation *"can reveal performance deterioration over time and inform judgments about acceptable performance ranges."* Where performance deviates meaningfully, organisations *"generally consider whether model adjustments, recalibration, or redevelopment are warranted."*

### 4.2 Timing

**Validation generally occurs before first use.** But the guidance is pragmatic about exceptions:

> *"certain circumstances (e.g., an urgent business need) may necessitate using the model before validation is completed. In those cases, sound practice involves greater attention to the model's limitations when considering the appropriateness of its use, informing relevant stakeholders of those limitations, and determining appropriate controls (e.g., placing limits on model use or more closely monitoring its performance)."*

**Pre-validation use is permitted, conditionally, and the conditions are specific:** heightened attention to limitations, stakeholder notification, and compensating controls such as usage limits or intensified monitoring.

### 4.3 A notable shift on organisational structure

> *"The quality of validation process depends on the **rigor and effectiveness of the review rather than on organizational structure** of the banking organization's risk management function."*

This is a substantive change in emphasis. Independence remains essential to effective challenge, but SR 26-2 is explicit that **outcome quality, not reporting lines, is the test.** A rigorous review by a technically strong team matters more than an org chart that satisfies a structural template.

Note this is US guidance. **Basel's `MAR30.8` remains structural and is not relaxed by it:** for IMA banks, the risk control unit must be *"a distinct unit of the bank that is separate from the unit that designs and implements the internal model."* Both apply.

### 4.4 The components of validation

**Conceptual soundness**

> *"Validating conceptual soundness involves assessing and documenting model design (including key modeling choices, assumptions, qualitative judgments, and data selection), construction, and developmental testing."*

The guidance is flexible about method: *"While evaluating theoretical construction may be important for some models, other assessments — such as interpretability measures or benchmarking to other models — may be more practical for other models."*

**Outcomes analysis**

> *"Outcomes analysis compares model outputs to corresponding real-world outcomes to assess model performance relative to model objectives and business use."*

For market risk models, **backtesting is outcomes analysis** ([15](15_Backtesting.md)). Where a model's design *"relies substantially on expert judgment, quantitative outcomes analysis helps to evaluate"* it — the more judgement in the model, the more the empirical test carries the weight.

**Ongoing monitoring**

Continuous performance tracking, plus *"regularly assessing any model"* against changing conditions. This is where the §2 example should have been caught: a monitoring plan that tracks the *relevance of the calibration window*, not only the exception count.

### 4.5 Residual risk is expected

> *"Even with sound modeling practices and rigorous validation, material model risk can remain. Users of model output benefit from understanding and communicating limitations, monitoring performance, periodically reviewing relevance, and supplementing model output with complementary analysis and information."*

**Validation does not eliminate model risk; it characterises and communicates it.** A validation report whose conclusion is "no issues" has almost certainly not looked hard enough.

### 4.6 Vendor and third-party models

Section VII requires the same substance for bought models as for built ones: understanding *"its conceptual soundness, design, development data, and performance"*, and *"conducting ongoing monitoring and outcome analysis"*.

> **A vendor FRTB engine or pricing library does not transfer accountability.** The bank owns the numbers. This is a live issue given the trend toward buying FRTB engines ([25 §9](25_Risk_System_Architecture.md)) — vendor selection reduces implementation risk and increases dependency risk, and the validation obligation is unchanged.

---

## 5. The UK framework — PRA SS1/23

| Field | Value |
|---|---|
| **Framework** | *Model risk management principles for banks* |
| **Reference** | **SS1/23**, published with policy statement **PS6/23** |
| **Jurisdiction** | United Kingdom |
| **Regulator** | Prudential Regulation Authority |
| **Published** | **May 2023** |
| **Effective** | **17 May 2024** |
| **Status** | **Current** |
| **Latest verification** | 25 August 2026 |

SS1/23 sets out the PRA's expectations *"with the aim of encouraging banks to take a strategic approach to model risk management as a risk discipline in its own right."* It is structured around **five principles**:

| Principle | Theme |
|---|---|
| **1** | **Model identification and model risk classification** |
| **2** | **Governance** |
| **3** | **Model development, implementation and use** |
| **4** | **Independent model validation** |
| **5** | **Model risk mitigants** |

> **The framing — "a risk discipline in its own right" — is the distinctive feature.** SS1/23 treats model risk as a first-class risk type with its own appetite, governance and reporting, rather than as a control activity attached to other risk types.

**Note the divergence in emphasis between the two jurisdictions.** SS1/23 dedicates a principle to **independent** validation. SR 26-2 states that validation quality depends on *"rigor and effectiveness of the review rather than on organizational structure."* Both aim at effective challenge; a global bank subject to both must satisfy the structural expectation as well as the outcome expectation.

---

## 6. The model lifecycle

```
   IDENTIFICATION  ──► is it a model under the applicable definition?
        │                (SR 26-2: statistical/economic/financial theory?
        │                 NOT a spreadsheet calculation or a rule engine)
        ▼
   CLASSIFICATION  ──► inherent risk × (purpose + exposure) = materiality
        │                tiering drives the rigour of everything below
        ▼
   DEVELOPMENT     ──► design · assumptions · data · developmental testing
        │                documentation is a deliverable, not an afterthought
        ▼
   VALIDATION      ──► conceptual soundness · outcomes analysis · monitoring plan
        │                normally BEFORE first use; conditional exceptions
        ▼
   APPROVAL        ──► governance body; approved use; stated limitations
        │
        ▼
   IMPLEMENTATION  ──► code · controls · change management · version pinning
        │
        ▼
   ONGOING USE     ──► monitoring · backtesting · benchmarking · overrides
        │              ▲
        ▼              │
   PERIODIC REVIEW ────┘   frequency by materiality; triggered by
        │                   performance deterioration or changed conditions
        ▼
   CHANGE / REDEVELOPMENT  or
   RETIREMENT      ──► decommission; ensure nothing still depends on it
```

---

## 7. Market risk models — the specific validation agenda

| Model | Conceptual soundness questions | Outcomes analysis |
|---|---|---|
| **VaR** | Lookback window; weighting; shock convention (absolute vs relative); quantile convention; factor coverage | **Backtesting** (`MAR32`); benchmark against a challenger method |
| **ES** | All of the above, plus liquidity horizon mapping and the stress-period calibration | Indirect — via VaR backtesting and PLA ([12 §9.1](12_Expected_Shortfall.md)) |
| **Curve builder** | Instrument selection; interpolation; convexity adjustment; multi-curve/CSA handling | Reprices its own inputs; forward-curve sanity |
| **Pricing models** | Model choice vs product; calibration; numerical convergence | Independent price verification; put-call parity; benchmark models |
| **Volatility surface** | Parameterisation; extrapolation policy | Arbitrage tests; repricing of quoted instruments |
| **Stress scenarios** | Severity sourcing; coherence; completeness | Compare to realised episodes; reverse stress plausibility |
| **DRC / default model** | Correlation calibration; PD sourcing; LGD assumptions | Historical default experience; concentration analysis |
| **Proxy / mapping models** | Proxy selection; idiosyncratic residual treatment | **RFET evidence**; NMRF classification ([20](20_NMRF_and_Modellability.md)) |
| **Prepayment / behavioural** | Driver specification; regime dependence | Actual vs predicted prepayment; NMD behaviour |

### 7.1 The validation questions that catch real problems

1. **What is the model's calibration window, and does it contain a stress period?** (§2)
2. **What happens at the boundaries** — zero rates, negative prices, expiry, barriers?
3. **What is proxied, and what does the proxy exclude?** Usually the idiosyncratic risk.
4. **Which assumptions are shared with other models?** SR 26-2's aggregate model risk.
5. **What does the model do when an input is missing?** If the answer is "assumes zero", that is a finding.
6. **Who uses the output, and do they know the limitations?** Model *use* is a driver of model risk.
7. **When did the assumptions last get re-examined, as opposed to the code being re-tested?**

---

## 8. Benchmarking and challenger models

A **challenger model** is an independent alternative implementation used to test the champion.

| Champion | Typical challenger |
|---|---|
| Historical simulation VaR | Parametric VaR; filtered historical simulation |
| Full revaluation | Delta-gamma approximation (to bound approximation error) |
| Vendor pricing library | Independent implementation, or a second vendor |
| Internal curve build | Vendor curve |
| Proprietary prepayment model | Vendor model or a simple rate-driven benchmark |

> **A material, unexplained divergence between champion and challenger is a finding regardless of which is "right."** The purpose is not to determine the true answer — often unknowable — but to establish the *magnitude of model uncertainty*, which is exactly what SR 26-2 means by characterising the source and extent of model risk.

The parametric-versus-historical VaR gap in [11 §9.1](11_VaR.md) — $1.68m against $3.45m on the same book — is a worked example of this. Neither is wrong; the gap **is the finding**, and it quantifies how much the normality assumption is worth.

---

## 9. Overrides and model limitations

| Mechanism | Legitimate use | Requirement |
|---|---|---|
| **Parameter override** | Known data issue; documented judgement | Value, reason, approver, **expiry** |
| **Output adjustment / overlay** | Known model limitation not yet remediated | Quantified, disclosed, tracked, time-bound |
| **Usage restriction** | Model valid only within a stated range | Enforced in code, not policy alone |
| **Model reserve** | Valuation uncertainty from model choice | Calculated, reported |

**Overrides without expiry become permanent, and a permanent override is an undocumented model change.** Track them in aggregate: a rising override count is a leading indicator of model deterioration that no individual override reveals.

---

## 10. The model inventory

Every institution needs one, and it must be complete.

```
model_inventory_entry:
    model_id                string       PK
    model_name              string
    model_version           string
    is_in_scope             boolean       -- against the applicable definition
    scope_rationale         text          -- SR 26-2: theory-based? or excluded?
    risk_type               enum {MARKET, CREDIT, LIQUIDITY, OPERATIONAL,
                                  CAPITAL, VALUATION, BEHAVIOURAL}
    inherent_risk_rating    enum {HIGH, MEDIUM, LOW}
    model_exposure          decimal       -- quantitative, e.g. portfolio size
    model_purpose_rating    enum {HIGH, MEDIUM, LOW}   -- qualitative
    materiality_tier        enum          -- derived: purpose + exposure
    owner                   string
    developer               string
    validator               string        -- MUST differ from developer
    approved_use            text
    stated_limitations      text          -- REQUIRED
    shared_dependencies     list<string>  -- for AGGREGATE model risk
    last_validation_date    date
    next_review_date        date
    validation_status       enum {APPROVED, APPROVED_WITH_CONDITIONS,
                                  PRE_VALIDATION_USE, REMEDIATION_REQUIRED,
                                  NOT_APPROVED, RETIRED}
    open_findings           list<finding_id>
    active_overrides        list<override_id>
    is_vendor_model         boolean
    vendor_name             string | null
```

> **`shared_dependencies` is the field that makes aggregate model risk assessable.** Without it, the question *"which models would be affected if the curve builder is wrong?"* can only be answered by asking people.

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Current guidance cited** | **SR 26-2**, not SR 11-7; SS1/23 for the UK |
| 2 | **Scope definition applied** | SR 26-2's theory-based definition; spreadsheets and rule engines correctly excluded — and separately controlled |
| 3 | **AI scope** | Generative/agentic AI out of scope of the guidance; non-generative AI/ML **in** scope |
| 4 | **Inventory complete** | Every in-scope model recorded |
| 5 | **Materiality tiering** | Purpose **and** exposure both assessed |
| 6 | **Aggregate model risk** | Shared assumptions, data and methodologies mapped |
| 7 | **Effective challenge** | Expertise, independence **and standing to effect change** all present |
| 8 | **Validator ≠ developer** | Enforced in the inventory |
| 9 | **`MAR30.8` separation** | For IMA banks, risk control unit distinct from model design/implementation |
| 10 | **Validation before use** | Or documented conditions, stakeholder notification and compensating controls |
| 11 | **Conceptual soundness** | Design, assumptions, judgements, data selection assessed and documented |
| 12 | **Outcomes analysis** | Backtesting for market risk models |
| 13 | **Ongoing monitoring** | Includes assessing continued **relevance**, not just performance |
| 14 | **Limitations stated** | Every model; communicated to users |
| 15 | **Benchmark/challenger** | Run for material models; divergences investigated |
| 16 | **Overrides tracked** | With expiry; aggregate trend monitored |
| 17 | **Vendor models validated** | Same substance as internal models |
| 18 | **Change control** | Versions pinned per business date; changes tested and approved |
| 19 | **Findings tracked to closure** | With owners and dates |
| 20 | **Retirement** | Decommissioned models have no remaining dependencies |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| **Citing SR 11-7 as current** | Policy references a superseded letter; scope and tailoring wrong |
| Applying SR 11-7's broad model definition unchanged | Effort spent inventorying spreadsheets the current definition excludes |
| Assuming AI models are all in scope | Generative and agentic AI are explicitly **out** of scope of SR 26-2 |
| Assuming AI models are all out of scope | Non-generative, non-agentic AI/ML **are** in scope |
| Validation by the model builders | No effective challenge; contradicts `MAR30.8` for IMA banks |
| Validation with no authority to compel change | Reports without remediation |
| Validating models only in isolation | Aggregate model risk from shared dependencies undetected |
| Backtesting treated as the whole of validation | Conceptual failures like §2 pass every statistical test |
| No stated limitations | Users cannot know where the model does not apply |
| Overrides without expiry | Undocumented permanent model changes |
| Vendor models exempted | Accountability does not transfer with procurement |
| Model versions unpinned | Historical numbers irreproducible |
| Materiality assessed on exposure alone | Purpose is the other half of the SR 26-2 formula |

---

## 13. Limitations

- **Validation cannot prove a model correct.** It can find errors, characterise uncertainty and bound applicability. SR 26-2 is explicit that material model risk remains after rigorous validation.
- **Outcomes analysis has low statistical power** at the horizons and confidence levels market risk uses — 250 observations cannot distinguish a 99% model from a 98% one ([15 §11](15_Backtesting.md)).
- **Conceptual soundness is a judgement**, and reasonable experts disagree. The mitigant is documentation of the reasoning, not the illusion of a single right answer.
- **Guidance is principles-based and not enforceable as such.** SR 26-2 says so directly — while noting that supervisory action can follow from violations of law or unsafe and unsound practices arising from insufficient model risk management.
- **Jurisdictional expectations differ**, notably on the structural independence of validation. A global bank meets the stricter of the applicable expectations.

---

## 14. Related Concepts

- [15 — Backtesting](15_Backtesting.md) · [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)
- [20 — NMRF and Modellability](20_NMRF_and_Modellability.md) · [27 — Controls and Governance](27_Controls_and_Governance.md)
- [44 — Roles and Responsibilities](44_Roles_and_Responsibilities.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| **Federal Reserve / OCC / FDIC** | **SR 26-2, *Revised Guidance on Model Risk Management*** | **17 Apr 2026** | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | **Current US guidance**; supersedes SR 11-7 and SR 21-8; definitions, tailoring, AI scope, validation components |
| Federal Reserve / OCC | SR 11-7, *Guidance on Model Risk Management* | 4 Apr 2011 | https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm | **Superseded** — historical reference only |
| Bank of England / PRA | **SS1/23 – *Model risk management principles for banks*** | May 2023, effective **17 May 2024** | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss | Current UK expectations; five principles |
| Bank of England / PRA | PS6/23 – *Model risk management principles for banks* | May 2023 | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss | Policy statement accompanying SS1/23 |
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR30.5`–`MAR30.16` qualitative standards; `MAR30.8` independent risk control unit |

*Accessed 25 August 2026.*
