# 29 — The Regulatory Framework and Status Tracker

**Level:** 12 · **Prerequisites:** [16](16_FRTB_Overview.md) · **Feeds:** every document that cites a rule

> ### ⚠ How to read this document
>
> **A Basel standard is not law anywhere.** The Basel Committee has no legislative authority. Its standards become binding only when a jurisdiction transposes them into its own rules — and jurisdictions differ in **timing**, in **scope**, and in **calibration**.
>
> Three errors this document exists to prevent:
>
> 1. **Describing a proposed rule as effective.** The U.S. market risk framework is, as at this document's date, a **proposal with a closed comment period** — not a final rule.
> 2. **Assuming a jurisdiction applies the pure Basel calibration.** The EU is applying a **multiplier and operational relief measures** for three years from 2027, explicitly to neutralise capital impact.
> 3. **Assuming one date per jurisdiction.** The UK has split its standardised approach (**2027**) from its internal models approach (**2028**).
>
> **Everything below carries a "latest verification" date of 25 August 2026.** Regulatory status changes; re-verify before relying on any row.

---

## 1. The status tracker

### 1.1 Basel — the global standard

| Field | Value |
|---|---|
| **Framework** | Minimum capital requirements for market risk (**FRTB**) |
| **Jurisdiction** | Global (standard-setting only) |
| **Regulator** | Basel Committee on Banking Supervision |
| **Publication date** | **14 January 2019**, revised **February 2019** (BCBS **d457**) |
| **Predecessor** | January 2016 standard; extended from 1 Jan 2019 to 1 Jan 2022 by the Committee's governing body in **December 2017** |
| **Basel implementation date** | **1 January 2023** |
| **Current status** | **Final standard**, integrated into the consolidated Basel Framework |
| **Framework location** | `RBC25`; `MAR10`–`MAR99` |
| **Institutions affected** | Internationally active banks, as adopted by member jurisdictions |
| **Trading-book applicability** | Defines the boundary (`RBC25`) and capitalises everything inside it |
| **Calculations affected** | SBM, DRC, RRAO, ES, liquidity horizons, NMRF/SES, backtesting, PLA |
| **Primary source** | https://www.bis.org/bcbs/publ/d457.pdf |
| **Latest verification** | **25 August 2026** |

**Adjacent Basel standards:**

| Framework | Chapter | Key publication | Basel effective date |
|---|---|---|---|
| **CVA risk** | `MAR50` | *Targeted revisions to the CVA risk framework* (**d507**) | **1 January 2023** |
| **IRRBB** | `SRP31`, `SRP98` | *Interest rate risk in the banking book* (**d368**, Apr 2016) | 2018 |
| **IRRBB shock recalibration** | `SRP31` | *Recalibration of shocks for IRRBB* (**d578**, **16 July 2024**) | **implement by 1 January 2026** |
| **Risk data aggregation** | — | **BCBS 239** (Jan 2013) | 2016 for G-SIBs |

---

### 1.2 European Union

| Field | Value |
|---|---|
| **Framework** | **CRR3** — Regulation (EU) **2024/1623**, amending Regulation (EU) No 575/2013 as regards requirements for credit risk, **credit valuation adjustment risk**, operational risk, **market risk** and the **output floor** |
| **Jurisdiction** | European Union |
| **Regulator** | European Commission (legislation); **EBA** (standards); **ECB/SSM** and national competent authorities (supervision) |
| **Entry into force** | **9 July 2024** |
| **General application** | **1 January 2025** |
| **FRTB own-funds application** | **1 January 2027** — deferred twice from the original date |
| **Current status** | **In force**, with FRTB market risk own-funds requirements **deferred and subject to targeted adjustments** |
| **Institutions affected** | EU credit institutions and investment firms in scope of CRR |
| **Latest verification** | **25 August 2026** |

**The deferral chain — three delegated acts under the Article 461a CRR3 empowerment:**

| Date | Act | Effect |
|---|---|---|
| **24 July 2024** | Delegated act under Art. 461a | Postpones the alternative approaches for market risk own funds by one year, **to 1 January 2026** |
| **12 June 2025** | Delegated act | Postpones **by one additional year, to 1 January 2027** |
| **4 June 2026** | Delegated act | Introduces *"a targeted multiplier and targeted operational relief measures amending the fundamental review of the trading book (FRTB)"*, applying from **1 January 2027 for a three-year period** |

**On the 2026 act specifically:**

- Subject to a **three-month scrutiny period** with Parliament and Council. *"If no objection is raised, the measures will enter into application on 1 January 2027 and will be applicable for a three-year period."*
- The multiplier is *"designed to neutralise the capital impact on banks negatively impacted by the new FRTB rules."*
- The Commission's stated rationale: *"the EU has consistently considered that unilateral implementation of the FRTB would expose European banks to significant capital cost disadvantages in their cross-border trading activities."*

> **The practical consequence for anyone modelling EU capital: the EU is not applying the pure Basel calibration.** From 1 January 2027 for three years — to January 2030 — a multiplier and operational relief measures apply. Any EU FRTB capital figure computed on Basel parameters alone will be wrong for that period.

---

### 1.3 United Kingdom

| Field | Value |
|---|---|
| **Framework** | **Basel 3.1** — UK implementation |
| **Jurisdiction** | United Kingdom |
| **Regulator** | **Prudential Regulation Authority** (in consultation with HM Treasury) |
| **Key publications** | **PS9/24** — near-final rules part 2 (Sept 2024); **PS1/26 — *Implementation of Basel 3.1: Final rules*** (**January 2026**); **PS3/26** — Restatement of CRR requirements, 2027 implementation (Jan 2026); **CP9/26** — *Basel 3.1: Adjustments to the internal model approach (IMA) for market risk* (**June 2026**) |
| **Implementation date — general** | **1 January 2027** |
| **Implementation date — market risk IMA** | **1 January 2028** |
| **Reporting requirements** | From **1 January 2027** |
| **Current status** | **Final rules published**; IMA adjustments **under consultation** (CP9/26) |
| **Institutions affected** | PRA-authorised firms |
| **Latest verification** | **25 August 2026** |

**The timeline:**

| Date | Event |
|---|---|
| September 2024 | PRA publishes **PS9/24**, near-final Basel 3.1 rules part 2 |
| **January 2025** | PRA announces, in consultation with HM Treasury, a **one-year delay** to 1 January 2027 |
| **January 2026** | PRA publishes **PS1/26**, final rules and policy — including the IMA |
| **June 2026** | PRA publishes **CP9/26**, consulting on adjustments to the market risk IMA |
| **1 January 2027** | General Basel 3.1 implementation, including the market risk **standardised** approach |
| **1 January 2028** | Market risk **internal model approach** implementation |

**The PRA's stated reason for splitting the dates:** the IMA is *"predominantly used by major trading firms including international groups engaged in cross-border trading activity"*, and the additional year allows time for **international coordination**.

> **A UK bank therefore faces a year on the standardised approach before its models become available for capital purposes.** That is not a transitional inconvenience — it is a year of running the SA on a book designed to be capitalised under a model, with the capital consequence that implies for hedged portfolios ([17 §6.5](17_FRTB_Standardised_Approach.md)).

---

### 1.4 United States

| Field | Value |
|---|---|
| **Framework** | Regulatory Capital: Category I and II Banking Organizations, Banking Organizations With Significant Trading Activity, and Optional Adoption for Other Banking Organizations |
| **Jurisdiction** | United States |
| **Regulator** | **Federal Reserve Board**, **OCC**, **FDIC** — jointly |
| **Publication date** | **19 March 2026** (OCC Bulletin **2026-9**) |
| **Comment deadline** | **18 June 2026** — **closed** |
| **Effective date** | **NOT DETERMINED — the rule is not final** |
| **Current status** | ⚠ **PROPOSED. Not legally effective.** |
| **Predecessor status** | The **2023 Basel III endgame proposal** was **formally rescinded** by these proposals |
| **Latest verification** | **25 August 2026** |

**Scope of the market risk element:**

> *"The market risk aspect of the framework would apply only to banks with significant trading activity."*

Per OCC Bulletin 2026-9, the revised market risk rule would apply to *"national banks, federal savings associations, and other banking organizations with **$5 billion or more in trading assets plus trading liabilities**"* or where such assets exceed **10 percent of total assets**.

**Structural change:**

The proposals establish a single **expanded risk-based approach (ERBA)** for Category I and II banking organizations, under which *"the advanced approaches would be removed from the regulatory capital framework."* This replaces the previous dual-calculation structure — large banks would *"use one rather than two sets of calculations."*

**Community banks would have the option to use the proposed framework.**

**Capital impact:** the agencies anticipate that overall capital in the banking system *"would modestly decrease"* if the proposals are implemented, while remaining *"substantially higher than they were before the financial crisis."*

> ### ⚠ **Do not describe the U.S. market risk rules as effective.**
>
> As at 25 August 2026 they are a **proposal** whose comment period closed on 18 June 2026. Secondary commentary has suggested finalisation in Q4 2026 with implementation beginning 2027 — **that is an expectation, not a fact, and it must be labelled as such.**
>
> **UNVERIFIED — the U.S. finalisation and implementation dates require authoritative confirmation once a final rule is issued.**

---

### 1.5 Model risk management

| Jurisdiction | Framework | Status |
|---|---|---|
| **United States** | **SR 26-2**, *Revised Guidance on Model Risk Management* (Fed/OCC/FDIC, **17 April 2026**) | **Current.** **Supersedes and replaces SR 11-7 (2011) and SR 21-8 (2021).** Most relevant to organisations with **over $30 billion** in total assets. Not enforceable standards as such |
| **United Kingdom** | **SS1/23**, *Model risk management principles for banks* (PRA, May 2023) | **Current**, effective **17 May 2024**. Five principles |

See [26](26_Model_Risk_and_Validation.md) for substance. **A very large volume of published material still cites SR 11-7 as current. It is not.**

---

### 1.6 Industry methodology — ISDA SIMM

| Field | Value |
|---|---|
| **Methodology** | ISDA SIMM® |
| **Status** | **Industry methodology, not regulation** — used to meet regulatory margin requirements |
| **Publisher** | International Swaps and Derivatives Association |
| **Current version** | **2.8+2512** |
| **Published** | **12 June 2026** |
| **Effective** | **11 July 2026** |
| **Calibration** | Full recalibration on historical data to **31 December 2025** |
| **Preceding version** | 2.8+2506 — published 31 Oct 2025, effective 6 Dec 2025 |
| **Cycle** | **Semiannual**, introduced 2025 |
| **Latest verification** | **25 August 2026** |

---

## 2. The jurisdictional comparison

| Dimension | **Basel** | **EU** | **UK** | **US** |
|---|---|---|---|---|
| **Legal instrument** | Standard (non-binding) | Regulation (EU) 2024/1623 + delegated acts | PRA Rulebook / PS1/26 | Proposed rule (12 CFR) |
| **Status** | Final | **In force**, FRTB deferred | **Final rules** | ⚠ **Proposed** |
| **Market risk SA date** | 1 Jan 2023 | **1 Jan 2027** | **1 Jan 2027** | **Not determined** |
| **Market risk IMA date** | 1 Jan 2023 | 1 Jan 2027 | **1 Jan 2028** | Not determined |
| **Calibration** | Pure Basel | **Multiplier + operational relief, 2027–2030** | Per PS1/26; IMA adjustments consulted (CP9/26) | ERBA; not final |
| **Scope threshold** | Internationally active | CRR institutions | PRA-authorised firms | **≥$5bn trading assets + liabilities, or >10% of total assets** |
| **Advanced approaches** | n/a | n/a | n/a | **Removed** under ERBA |
| **Simplified SA** | `MAR40`, national discretion | Per CRR | Per PRA rules | Per proposal |

### 2.1 Why the dates diverged

The divergence is not administrative drift; it is a stated policy position in at least two jurisdictions.

- **The EU** has said explicitly that *"unilateral implementation of the FRTB would expose European banks to significant capital cost disadvantages in their cross-border trading activities"* — and has used its Article 461a empowerment three times.
- **The UK PRA** delayed the IMA specifically to allow *"international coordination"*, recognising that IMA users are cross-border trading groups.
- **The US** rescinded its 2023 proposal and re-proposed in 2026 with a stated expectation of *decreasing* overall capital.

> **The common thread is competitive concern about first-mover disadvantage in trading capital.** Understanding that is what makes the timeline predictable: **each jurisdiction is waiting, at least in part, on the others.**

---

## 3. Historical evolution — and what is superseded

**Never present a superseded requirement as current.** The evolution:

```
   1996   Market Risk Amendment (BCBS 24)
          99% 10-day VaR × multiplier (3 + plus)
          Traffic-light backtesting zones introduced
                    │
                    ▼   2007-09 crisis exposes the failures
   2009   BASEL 2.5
          VaR + STRESSED VaR + IRC + CRM
          Bank-wide model approval
                    │
                    ▼   FRTB designed as a full replacement
   2016   FRTB first standard (Jan 2016)
   2017   Implementation extended to 1 Jan 2022 (Dec 2017)
   2019   FRTB revised standard (d457, Jan 2019 rev Feb 2019)
   2023   Basel implementation date (1 Jan 2023)
                    │
                    ▼   jurisdictional implementation, still incomplete
   2025   EU CRR3 applies generally; FRTB deferred
   2026   EU delegated act: multiplier + relief, 2027-2030
          UK PS1/26 final rules: SA 2027, IMA 2028
          US re-proposal (Mar 2026), comments closed Jun 2026
   2027   EU and UK SA go-live
   2028   UK IMA go-live
```

### 3.1 What is superseded, and what survives

| Concept | Status under FRTB |
|---|---|
| 99% 10-day VaR for capital | **Superseded** by 97.5% ES |
| Stressed VaR | **Superseded** by stress-calibrated ES (`MAR33.5`) |
| IRC (Incremental Risk Charge) | **Superseded** by DRC (`MAR22`, `MAR33`) |
| CRM (Comprehensive Risk Measure) | **Superseded** by CTP treatment |
| Bank-wide model approval | **Superseded** by desk-level approval |
| Multiplier of 3 + plus | **Superseded** — `m_c` is **1.5** + add-on 0–0.5 (`MAR33.42`) |
| **Traffic-light zones** | **RETAINED** for bank-wide backtesting (`MAR32.8`–`MAR32.9`) |
| **VaR itself** | **RETAINED** as the backtesting measure at 97.5% and 99% (`MAR32.18`) |
| Uniform 10-day horizon | **Superseded** by liquidity horizons 10–120 days |
| Full diversification for illiquid factors | **Superseded** by the NMRF/SES regime |

> **The two "RETAINED" rows are the ones most often got wrong.** A common misstatement is that FRTB "replaced VaR" and "abolished the traffic lights." It replaced VaR **for capital** and retained it **for validation**; it retained the traffic-light zones and **changed the multiplier scale attached to them**. See [11 §10](11_VaR.md) and [15 §4.3](15_Backtesting.md).

---

## 4. Where the frameworks meet

A single derivative can engage four separate capital frameworks simultaneously. Each captures a different loss event; none is a substitute for another.

| Loss event | Framework | Chapter |
|---|---|---|
| The **price** moves | Market risk | `MAR20`–`MAR33` |
| The **counterparty defaults** | Counterparty credit risk | `CRE52` |
| The **value of the counterparty adjustment** moves | CVA risk | `MAR50` |
| The **issuer of the underlying defaults** | DRC (trading book) | `MAR22` / `MAR33` |
| The same rate risk, in the **banking book** | IRRBB | `SRP31` (Pillar 2) |

**Double-counting and gapping between these are both genuine supervisory concerns.** The resolving question is always: **what event causes the loss?** ([22 §10](22_Counterparty_CVA_and_SIMM.md))

---

## 5. Source hierarchy for regulatory claims

| Tier | Sources | Use for |
|---|---|---|
| **1 — Primary** | BIS/BCBS; Federal Reserve, OCC, FDIC; Federal Register; European Commission, EBA, ECB; PRA, Bank of England; EUR-Lex; ISDA official methodology | **All regulatory assertions** |
| **2 — Official market infrastructure** | CME, ICE, LCH, DTCC, benchmark administrators, central banks | Conventions, contract specifications, market events |
| **3 — Academic** | Peer-reviewed finance literature | Mathematical and model explanations |
| **4 — Secondary** | Major risk publications, consultancies, financial institutions, data providers | Context and interpretation **only** |

**Rules applied throughout this knowledge base:**

- Every regulatory parameter is cited to a **paragraph** of the primary standard.
- Where a figure could not be verified against a primary source, it is marked **UNVERIFIED — requires authoritative confirmation.**
- **Vendor and consultancy material is never used as authority for a regulatory claim.**
- Where sources disagree, the disagreement is stated rather than resolved silently.

---

## 6. What to re-verify, and when

| Item | Re-verify | Because |
|---|---|---|
| **US final rule** | On publication | Currently proposed; dates and calibration unknown |
| **EU delegated act scrutiny** | After the three-month period from 4 June 2026 | Parliament/Council may object |
| **EU multiplier parameters** | Before computing EU capital | Not the Basel calibration |
| **UK CP9/26 outcome** | On final policy | IMA adjustments not yet final |
| **ISDA SIMM version** | **Semiannually** | Two version changes per year, each with a hard effective date |
| **IRRBB shocks** | On any BCBS recalibration | Recalibrated by d578; implemented 1 Jan 2026 |
| **Basel FAQs and technical amendments** | Periodically | The Committee issues clarifications that change interpretation |
| **National discretions** | Per jurisdiction | Sovereign DRC weights (`MAR22.7`), `MAR40` availability, LH increases |

---

## 7. Common errors in regulatory statements

| Error | Correction |
|---|---|
| "FRTB is in force" | It is a **Basel standard**; jurisdictions implement separately with different dates and calibrations |
| "The US has implemented FRTB" | **Proposed only**, as at 25 August 2026 |
| "The EU applies FRTB from 2025" | CRR3 applies generally from 2025; **FRTB own-funds requirements from 2027** |
| "The UK implements Basel 3.1 in 2027" | General rules 2027; **market risk IMA 2028** |
| "The EU applies the Basel calibration" | **Multiplier and operational relief, 2027–2030** |
| "FRTB replaced VaR" | Replaced it **for capital**; retained **for backtesting** |
| "The traffic lights were abolished" | **Retained** (`MAR32.8`–`MAR32.9`); the multiplier scale changed |
| "The multiplier is 3" | **1.5** + add-on 0–0.5 (`MAR33.42`) |
| "SR 11-7 is the US model risk guidance" | **Superseded by SR 26-2 on 17 April 2026** |
| "IRRBB outlier test is 20% of total capital" | **15% of Tier 1 capital** |
| "SIMM is a capital framework" | It is an **initial margin methodology** |
| "Sovereign exposures get a zero DRC weight" | **National discretion** (`MAR22.7`), not an entitlement |

---

## 8. Related Concepts

- [16 — FRTB Overview](16_FRTB_Overview.md) · [17](17_FRTB_Standardised_Approach.md)–[20](20_NMRF_and_Modellability.md)
- [20A — Trading Book Boundary and IRRBB](20A_Trading_Book_Boundary_and_IRRBB.md) · [22 — Counterparty, CVA and SIMM](22_Counterparty_CVA_and_SIMM.md)
- [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md) · [45 — Source Register](45_Source_Register.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | The FRTB standard |
| BCBS | Press release: revised market risk framework | 14 Jan 2016 | https://www.bis.org/press/p160114.htm | Original 2016 standard |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current text of all chapters cited |
| BCBS | *Targeted revisions to the CVA risk framework* (d507) | 2020 | https://www.bis.org/bcbs/publ/d507.pdf | CVA, effective 1 Jan 2023 |
| BCBS | *Interest rate risk in the banking book* (d368) | Apr 2016 | https://www.bis.org/bcbs/publ/d368.pdf | IRRBB standard |
| BCBS | *Recalibration of shocks for IRRBB* (d578) | 16 Jul 2024 | https://www.bis.org/bcbs/publ/d578.pdf | Shock recalibration, implement by 1 Jan 2026 |
| European Union | **Regulation (EU) 2024/1623 (CRR3)** | In force 9 Jul 2024; applies 1 Jan 2025 | https://eur-lex.europa.eu/eli/reg/2024/1623/oj | EU implementation of final Basel III |
| European Commission | EU temporarily amends prudential rules for banks' market risk | **4 Jun 2026** | https://finance.ec.europa.eu/news/eu-temporarily-amends-prudential-rules-banks-market-risk-2026-06-08_en | Multiplier and operational relief, 2027–2030 |
| European Commission | Commission proposes to postpone by one additional year the market risk requirements | 12 Jun 2025 | https://finance.ec.europa.eu/news/commission-proposes-postpone-one-additional-year-market-risk-prudential-requirements-under-basel-iii-2025-06-12_en | Deferral to 1 Jan 2027 |
| EBA | EBA responds to the Commission's Delegated Act postponing the market risk framework | 2024/2025 | https://www.eba.europa.eu/publications-and-media/press-releases/eba-responds-european-commissions-delegated-act-postponing-application-market-risk-framework-eu | Art. 461a delegated act context |
| Bank of England / PRA | **PS1/26 – Implementation of Basel 3.1: Final rules** | Jan 2026 | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/january/implementation-of-the-basel-3-1-final-rules-policy-statement | UK final rules; SA 2027, IMA 2028 |
| Bank of England / PRA | CP9/26 – Basel 3.1: Adjustments to the IMA for market risk | Jun 2026 | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/june/basel-3-1-adjustments-to-the-internal-model-approach-for-market-risk-consultation-paper | UK IMA adjustments consultation |
| Bank of England / PRA | The PRA announces a delay to the implementation of Basel 3.1 | Jan 2025 | https://www.bankofengland.co.uk/news/2025/january/the-pra-announces-a-delay-to-the-implementation-of-basel-3-1 | One-year delay to 2027 |
| Federal Reserve | Agencies request comment on proposals to modernize the regulatory capital framework | **19 Mar 2026** | https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260319a.htm | US proposal; scope; comment deadline |
| OCC | **Bulletin 2026-9** — Regulatory Capital: Category I and II Banking Organizations… | **19 Mar 2026** | https://www.occ.gov/news-issuances/bulletins/2026/bulletin-2026-9.html | US market risk scope thresholds; ERBA |
| Federal Reserve / OCC / FDIC | SR 26-2, *Revised Guidance on Model Risk Management* | **17 Apr 2026** | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | Supersedes SR 11-7 and SR 21-8 |
| Bank of England / PRA | SS1/23 – *Model risk management principles for banks* | May 2023, effective 17 May 2024 | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss | UK model risk expectations |
| ISDA | ISDA SIMM Methodology, version 2.8+2512 | 12 Jun 2026, effective 11 Jul 2026 | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ | Current SIMM version |

*All rows verified 25 August 2026.*
