# Market Risk Knowledge Base — Master Index

**A complete, source-backed reference for banking market risk: from "why does a bond fall when rates rise" to FRTB internal-model capital.**

| | |
|---|---|
| **Documents** | **47** |
| **Lines** | ~19,600 |
| **Words** | ~164,000 |
| **Calculations catalogued** | **180** |
| **Risk factors catalogued** | ~**100** |
| **Instruments mapped** | **32** |
| **Formulas** | **53 blocks**, organised basic → advanced |
| **Sources** | **55**, tiered and status-flagged |
| **Compiled** | 25 August 2026 |
| **All regulatory rows verified** | **25 August 2026** |

---

## Start here

| If you are… | Begin at |
|---|---|
| **New to market risk** | [01 — Market Risk Fundamentals](01_Market_Risk_Fundamentals.md), then follow [35 — Learning Path](35_Beginner_to_Expert_Learning_Path.md) |
| **Looking for a specific calculation** | [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) |
| **Looking for a formula** | [32 — Master Formula Handbook](32_Master_Formula_Handbook.md) |
| **Looking for a term** | [34 — Glossary](34_Glossary.md) |
| **Answering a business question** | [38 — Question-to-Calculation Catalog](38_Question_to_Calculation_Catalog.md) |
| **Checking a regulatory status** | [29 — Regulatory Framework](29_Regulatory_Framework.md) — **read this before citing any rule** |
| **Implementing something** | [40 — Pseudocode and Data Contracts](40_Implementation_Pseudocode_and_Contracts.md) |
| **Designing an AI risk system** | [39 — Agent Knowledge Model](39_Agent_Knowledge_Model.md) |

---

## The document map

### Foundation

| # | Document | Level | Major calculations | Regulatory coverage |
|---|---|---|---|---|
| [01](01_Market_Risk_Fundamentals.md) | **Market Risk Fundamentals** | 1 | — (conceptual) | `RBC25`, `MAR10`–`MAR12` |
| [01A](01A_Master_Market_Risk_Taxonomy.md) | **The Master Market-Risk Taxonomy** | 1 | Taxonomy table; 6 drivers × 34 modes | 7 SBM classes; 5 IMA classes |
| [02](02_Financial_Instruments.md) | **Financial Instruments** | 2 | Instrument × risk factor × calculation matrices | `MAR21`–`MAR23` scope |
| [03](03_Pricing_Fundamentals.md) | **Pricing Fundamentals** | 3 | PV, DF, forwards, bootstrap, BSM, Black, Bachelier | `MAR21.8`, `MAR33.12` |

### Sensitivities by asset class

| # | Document | Level | Major calculations | Regulatory coverage |
|---|---|---|---|---|
| [04](04_Interest_Rate_Risk.md) | **Interest Rate Risk** | 4 | Duration family, **DV01**, key-rate DV01, convexity, carry/roll | `MAR21.42`–`21.50` GIRR; `MAR40` |
| [05](05_Credit_Spread_Risk.md) | **Credit Spread Risk** | 4 | **CS01**, bucketed CS01, Z-spread, OAS, credit triangle | `MAR21.9`, `MAR21.51`–`21.57` CSR |
| [06](06_FX_Risk.md) | **FX Risk** | 4 | NOP, FX delta, CIP, vanna/volga, RR/BF | `MAR21.14`, `MAR21.87`–`21.89` |
| [07](07_Equity_Risk.md) | **Equity Risk** | 4 | Exposures, beta, dividend and repo sensitivity | `MAR21.72`–`21.78` |
| [08](08_Commodity_Risk.md) | **Commodity Risk** | 4 | Delta by month, roll yield, basis | `MAR21.82`–`21.85` |
| [09](09_Options_and_Greeks.md) | **Options and the Greeks** | 5 | Delta, gamma, vega, theta, rho, vanna, volga; **curvature** | `MAR21.5`, `MAR21.92` |

### Portfolio and risk measures

| # | Document | Level | Major calculations | Regulatory coverage |
|---|---|---|---|---|
| [10](10_Portfolio_Risk_Mathematics.md) | **Portfolio Risk Mathematics** | 5 | Variance, correlation, PSD, Cholesky, MCR/CCR | `MAR21.6`, `MAR33.14` |
| [11](11_VaR.md) | **Value at Risk** | 6 | Historical, parametric, Monte Carlo, delta-normal VaR | `MAR32.18`; Basel history |
| [12](12_Expected_Shortfall.md) | **Expected Shortfall** | 7 | ES; **liquidity-horizon scaling**; coherence | `MAR33.2`–`33.5`, `33.12`–`33.17` |
| [13](13_Stress_Testing.md) | **Stress Testing** | 8 | Historical, hypothetical, reverse stress; spot×vol grids | `MAR21.6`, `MAR30`, `MAR33.5`; Fed GMS |
| [14](14_PnL_and_PnL_Explain.md) | **P&L and P&L Explain** | 6 | **APL, HPL, RTPL**; attribution; residual | `MAR32.22`–`32.31` |
| [15](15_Backtesting.md) | **Backtesting and PLA** | 8 | Exception counting; **Spearman**; **KS** | `MAR32` in full; `MAR99` |

### FRTB

| # | Document | Level | Major calculations | Regulatory coverage |
|---|---|---|---|---|
| [16](16_FRTB_Overview.md) | **FRTB Overview** | 10 | Framework architecture | `RBC25`, `MAR20`–`MAR40`; jurisdictional status |
| [17](17_FRTB_Standardised_Approach.md) | **FRTB Standardised Approach** | 10 | **SBM**, curvature, correlation scenarios, **RRAO** | `MAR20`–`MAR21`, `MAR23` |
| [18](18_FRTB_Internal_Models_Approach.md) | **FRTB Internal Models Approach** | 11 | **IMCC**, **SES**, liquidity horizons, capital aggregation | `MAR30`–`MAR33` |
| [19](19_Default_Risk_and_DRC.md) | **Default Risk and DRC** | 10 | **JTD**, net JTD, **HBR**, DRC | `MAR22`; `MAR33.18`–`33.39` |
| [20](20_NMRF_and_Modellability.md) | **NMRF and Modellability** | 11 | **RFET**, real price observations, **SES** | `MAR31.12`–`31.26`, `MAR33.16`–`33.17` |
| [20A](20A_Trading_Book_Boundary_and_IRRBB.md) | **Trading Book Boundary and IRRBB** | 10 | EVE, NII, six shock scenarios | `RBC25`; **`SRP31`**; BCBS d368, **d578** |

### Control, systems and governance

| # | Document | Level | Major calculations | Regulatory coverage |
|---|---|---|---|---|
| [21](21_Market_Risk_Limits.md) | **Market Risk Limits** | 9 | Utilisation; breach classification | `MAR30`; BCBS 239 |
| [22](22_Counterparty_CVA_and_SIMM.md) | **Counterparty, CVA and SIMM** | 10 | EE/EPE/PFE, **CVA**, netting, SA-CCR, SIMM | **`MAR50`**, `CRE52`; ISDA SIMM |
| [23](23_Market_Data_and_Curves.md) | **Market Data, Curves and Surfaces** | 7 | Bootstrap, interpolation, surface calibration | `MAR21.8`, `MAR31.12`; BCBS 239 |
| [24](24_Risk_Data_Model.md) | **The Market Risk Data Model** | 11 | — (conceptual schema) | `RBC25`, `MAR12`, `MAR32`; BCBS 239 |
| [25](25_Risk_System_Architecture.md) | **Risk System Architecture** | 11 | — (design) | Frequency requirements; `MAR30.8`, `MAR33.44` |
| [26](26_Model_Risk_and_Validation.md) | **Model Risk and Validation** | 13 | Validation components; effective challenge | **SR 26-2**; **SS1/23**; `MAR30` |
| [27](27_Controls_and_Governance.md) | **Controls and Governance** | 12 | 26 controls; KRIs | `RBC25.13`, `MAR30`; BCBS 239 |
| [28](28_Reporting_and_Dashboards.md) | **Reporting and Dashboards** | 9 | Report and dashboard design | BCBS 239; all reporting frequencies |
| [29](29_Regulatory_Framework.md) | **Regulatory Framework and Status Tracker** | 12 | — | **Basel · EU · UK · US**, with full status fields |

### Reference

| # | Document | Level | Contents |
|---|---|---|---|
| [30](30_Worked_Examples.md) | **Worked Examples** | 9 | A Treasury portfolio computed end to end + 26 cross-referenced examples |
| [31](31_Master_Calculation_Catalog.md) | **Master Calculation Catalog** | Ref | **180 calculations** across 14 categories |
| [32](32_Master_Formula_Handbook.md) | **Master Formula Handbook** | Ref | **53 formula blocks**, basic → advanced; quick-reference identities |
| [33](33_Master_Risk_Factor_Catalog.md) | **Master Risk Factor Catalog** | Ref | ~**100 risk factors** with shocks, horizons, instruments |
| [34](34_Glossary.md) | **Glossary** | Ref | Full definitions + **67 abbreviations** + contested terms |
| [35](35_Beginner_to_Expert_Learning_Path.md) | **Learning Path** | Meta | 17 levels; four role-based reading routes |

### Applied

| # | Document | Level | Contents |
|---|---|---|---|
| [37](37_Calculation_Dependency_Graph.md) | **Calculation Dependency Graph** | Ref | What must be computed before what; blast radius |
| [38](38_Question_to_Calculation_Catalog.md) | **Question-to-Calculation Catalog** | Ref | Business questions → calculations → **caveats** |
| [39](39_Agent_Knowledge_Model.md) | **Agent Knowledge Model** | Design | Intent taxonomy; resolution chain; **refusal boundaries** |
| [40](40_Implementation_Pseudocode_and_Contracts.md) | **Pseudocode and Data Contracts** | Impl. | Consolidated algorithms; schemas; **40-test suite** |
| [41](41_Market_Risk_vs_Related_Risk_Types.md) | **Market Risk vs Related Risk Types** | 12 | Boundaries; classification decision tree |
| [42](42_Risk_Aggregation.md) | **Risk Aggregation** | 13 | Netting, correlation aggregation, contributions |
| [43](43_Daily_Workflow.md) | **The Daily Workflow** | Practical | Market close → published report, with the gates |
| [44](44_Roles_and_Responsibilities.md) | **Roles and Responsibilities** | Practical | Who calculates, consumes, verifies, approves |
| [45](45_Source_Register.md) | **Source Register** | Ref | **55 sources**, tiered, status-flagged |

---

## Counts, per the taxonomy actually used

**Not manufactured.** Section 1 of [01A](01A_Master_Market_Risk_Taxonomy.md) establishes that there is no universal count of market-risk categories, because different schemes classify for different purposes. These counts are stated against the specific schemes named.

| Measure | Count | Basis |
|---|---|---|
| **Basel SBM risk classes** | **7** | `MAR21.39`–`MAR21.89` — **regulatory** |
| **Basel IMA broad risk classes** | **5** | `MAR33.14` — **regulatory** |
| **Basel SA capital components** | **3** | `MAR20.4` — **regulatory** |
| Level 1 drivers (this library's scheme) | 6 | [01A §2](01A_Master_Market_Risk_Taxonomy.md) |
| Level 2 modes | 34 | [01A §2](01A_Master_Market_Risk_Taxonomy.md) |
| Level 3 exposures | 34 | [01A §2](01A_Master_Market_Risk_Taxonomy.md) |
| Named cross-cutting risks | 8 | [01A §6](01A_Master_Market_Risk_Taxonomy.md) |
| **Calculations documented** | **180** | [31](31_Master_Calculation_Catalog.md), 14 categories |
| **Risk factors documented** | ~**100** | [33](33_Master_Risk_Factor_Catalog.md) |
| **Instruments mapped** | **32** | [02 §9](02_Financial_Instruments.md) matrix |
| **Formula blocks** | **53** | [32](32_Master_Formula_Handbook.md), 8 levels |
| **Worked examples** | **27** | [30](30_Worked_Examples.md): 1 full portfolio + 26 cross-referenced |
| **Regulatory frameworks tracked** | **4 jurisdictions** + 5 adjacent standards | [29](29_Regulatory_Framework.md), [45](45_Source_Register.md) |
| **Sources** | **55** | [45](45_Source_Register.md) |

---

## Research methodology

| Principle | Application |
|---|---|
| **Primary sources only for regulatory claims** | Every Basel parameter is taken from BCBS d457 (extracted and read directly) and **cited to paragraph** |
| **Status before substance** | Each framework carries jurisdiction, regulator, publication date, effective date, current status and verification date ([29](29_Regulatory_Framework.md)) |
| **Standard ≠ law** | FRTB is a Basel standard. Jurisdictional implementation is tracked separately, with dates and calibration differences |
| **Nothing invented** | No risk weight, correlation, threshold, liquidity horizon or shock magnitude is stated without a citation |
| **Constructed data is labelled** | Every worked-example portfolio, curve and scenario set is flagged as constructed ([45 §11](45_Source_Register.md)) |
| **Arithmetic is computed** | Every numerical result was calculated and cross-checked, not asserted |
| **Unverifiable is marked** | **UNVERIFIED — requires authoritative confirmation**, e.g. specific PCA variance shares ([04 §7](04_Interest_Rate_Risk.md)) and US finalisation dates ([29 §1.4](29_Regulatory_Framework.md)) |

---

## ⚠ Regulatory status alerts

**Four items where material written before mid-2026 is now wrong.**

| Item | Status as at 25 August 2026 |
|---|---|
| **US market risk framework** | ⚠ **PROPOSED, not effective.** Re-proposed 19 March 2026; comments closed 18 June 2026. The 2023 endgame proposal was **rescinded**. Scope: **≥$5bn trading assets + liabilities**, or >10% of total assets |
| **SR 11-7** | ⚠ **SUPERSEDED** by **SR 26-2** on **17 April 2026**. The model definition, the $30bn applicability threshold and the AI scope all changed |
| **EU FRTB** | ⚠ Deferred to **1 January 2027**, and then subject to a **targeted multiplier and operational relief** for **three years** — **the EU is not applying the pure Basel calibration** |
| **IRRBB shocks** | ⚠ **Recalibrated** by BCBS **d578** (16 July 2024), implemented by **1 January 2026**. Pre-2024 shock magnitudes are out of date. The outlier test is **15% of Tier 1**, not 20% of total capital |

**Two things widely believed to have been abolished by FRTB, which were not:**

- **The traffic-light backtesting zones** — retained for bank-wide backtesting (`MAR32.8`–`MAR32.9`); what changed is the multiplier scale, from 3+ to **1.50–2.00**.
- **VaR** — replaced for *capital*, retained for *backtesting*, at **both 97.5% and 99%** at desk level (`MAR32.18`).

---

## The ten ideas this library is built around

1. **A missing observation is not zero.** A failed valuation, an unmapped factor, a stale price and a missing scenario are each *unknown*. Treating any of them as zero removes both the value and the risk, and nothing downstream can tell.
2. **A number without its convention is not a number.** Confidence, horizon, currency, sign, quantile rule, volatility basis, day count.
3. **A scalar conceals a ladder.** One DV01 can hide an arbitrarily large curve position; one vega can hide a term-structure position; one net exposure can hide catastrophic single-name risk.
4. **Sensitivities are local; stress is global.** Using the first where you need the second is the most common cause of understated tail risk.
5. **Hedged is not flat.** What remains after a hedge is smaller, less monitored, and where a disproportionate share of trading disasters originate.
6. **The dangerous failures are self-concealing.** A stale price *lowers* measured volatility. A complete-looking stress result can have forty unmapped factors.
7. **Diversification is a statement about correlations, and correlations converge in crises.** Which is why FRTB runs three correlation scenarios and takes the worst, and weights the bank's own view at exactly one half.
8. **Regulatory capital and economic risk answer different questions.** Both are needed; neither substitutes for the other.
9. **A standard is not a law.** FRTB is binding nowhere until a jurisdiction transposes it — with its own dates and its own calibration.
10. **What you do not know is part of the answer.** The tenth question in [01 §13](01_Market_Risk_Fundamentals.md), the final table in [38 §9](38_Question_to_Calculation_Catalog.md), and the refusal boundaries in [39 §6](39_Agent_Knowledge_Model.md) are all the same point.

---

## Coverage audit

| Question | Covered in |
|---|---|
| Every major market-risk category? | ✅ [01A](01A_Master_Market_Risk_Taxonomy.md) |
| Every major asset class? | ✅ [04](04_Interest_Rate_Risk.md)–[08](08_Commodity_Risk.md) |
| Linear **and** non-linear products? | ✅ [02](02_Financial_Instruments.md), [09](09_Options_and_Greeks.md) |
| Pricing prerequisites? | ✅ [03](03_Pricing_Fundamentals.md), [23](23_Market_Data_and_Curves.md) |
| Sensitivities? | ✅ [04](04_Interest_Rate_Risk.md)–[09](09_Options_and_Greeks.md) |
| Portfolio statistics? | ✅ [10](10_Portfolio_Risk_Mathematics.md) |
| VaR? ES? Stress? | ✅ [11](11_VaR.md), [12](12_Expected_Shortfall.md), [13](13_Stress_Testing.md) |
| P&L and backtesting? | ✅ [14](14_PnL_and_PnL_Explain.md), [15](15_Backtesting.md) |
| FRTB SA? IMA? DRC? RRAO? NMRF? | ✅ [17](17_FRTB_Standardised_Approach.md), [18](18_FRTB_Internal_Models_Approach.md), [19](19_Default_Risk_and_DRC.md), [17 §9](17_FRTB_Standardised_Approach.md), [20](20_NMRF_and_Modellability.md) |
| Trading-book boundary? | ✅ [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| Limits? Aggregation? | ✅ [21](21_Market_Risk_Limits.md), [42](42_Risk_Aggregation.md) |
| Market data? Yield curves? | ✅ [23](23_Market_Data_and_Curves.md) |
| Model validation? Controls? | ✅ [26](26_Model_Risk_and_Validation.md), [27](27_Controls_and_Governance.md) |
| Reporting? Architecture? Data model? | ✅ [28](28_Reporting_and_Dashboards.md), [25](25_Risk_System_Architecture.md), [24](24_Risk_Data_Model.md) |
| Calculation dependencies? | ✅ [37](37_Calculation_Dependency_Graph.md) |
| Jurisdictional differences? | ✅ [29](29_Regulatory_Framework.md) |
| Every material calculation has a worked example? | ✅ [30 §8](30_Worked_Examples.md) maps all 27 |
| Every regulatory assertion has a source? | ✅ Cited to paragraph; [45](45_Source_Register.md) |

---

## Known gaps and deliberate exclusions

**Stated explicitly, because a reference that hides its boundaries is misleading.**

| Not covered | Why |
|---|---|
| Banking-book **credit risk RWA** (PD/LGD/EAD modelling) | Different framework; [41](41_Market_Risk_vs_Related_Risk_Types.md) marks the boundary |
| **LCR / NSFR** mechanics | Funding liquidity is a separate discipline |
| **Operational risk** framework | Out of scope |
| Accounting standards (IFRS 9, ASC 820) | Referenced where they bear on the book boundary; not covered |
| **Full FRTB bucket tables** for CSR securitisations and commodities | Bucket *structure* and *risk weights* are given; the full constituent lists are in `MAR21` and are too long to reproduce |
| **Jurisdiction-specific reporting templates** | Change frequently; consult the current rulebook |
| **Vendor implementations** | Deliberately excluded — [45 §10](45_Source_Register.md) |
| **Specific PCA variance shares** | Marked **UNVERIFIED**; must be estimated on the relevant sample |
| **US final rule content** | Does not exist yet |

---

## Maintenance

| Item | Re-verify | Why |
|---|---|---|
| **US final rule** | On publication | Currently proposed |
| **EU delegated act** | After the scrutiny period from 4 Jun 2026 | Parliament/Council may object |
| **UK CP9/26** | On final policy | IMA adjustments not final |
| **ISDA SIMM** | **Semiannually** | Two versions a year, each with a hard effective date |
| **Basel FAQs and technical amendments** | Periodically | Clarifications change interpretation |
| **National discretions** | Per jurisdiction | Sovereign DRC weights, `MAR40` availability, LH increases |

---

*Compiled 25 August 2026. All regulatory rows verified 25 August 2026.*
*Primary source for the FRTB framework: BCBS **d457**, *Minimum capital requirements for market risk*, January 2019 (revised February 2019) — read directly and cited to paragraph throughout.*
