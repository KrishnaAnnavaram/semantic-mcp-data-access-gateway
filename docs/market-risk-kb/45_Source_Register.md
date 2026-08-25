# 45 — Source Register

**Level:** Reference · **Purpose:** every source relied on, its tier, its status, and what it was used for

> **Verification date for every row: 25 August 2026.** Regulatory status changes. Re-verify before relying on any row, and note that four rows below are marked **superseded** or **proposed** precisely because material written before mid-2026 gets them wrong.

---

## 1. Source hierarchy applied

| Tier | Sources | Used for |
|---|---|---|
| **1 — Primary** | BIS/BCBS; Federal Reserve, OCC, FDIC; European Commission, EBA; PRA/Bank of England; EUR-Lex; ISDA official methodology | **All regulatory assertions** |
| **2 — Official market infrastructure** | CME, ICE, LCH, DTCC, benchmark administrators, central banks | Conventions, contract specifications, market events |
| **3 — Academic** | Peer-reviewed finance literature | Mathematical results |
| **4 — Secondary** | Risk publications, consultancies, financial institutions | Context only — **never** as authority for a regulatory claim |

**Rules applied throughout:**

- Every regulatory parameter is cited to a **paragraph** of the primary standard.
- Anything unverifiable against a primary source is marked **UNVERIFIED — requires authoritative confirmation.**
- Where sources disagree, the disagreement is stated rather than resolved silently.
- **Constructed data is labelled as constructed.** The portfolios, curves, correlation matrices and scenario vectors in the worked examples are for exposition; none is a market observation.

---

## 2. Tier 1 — Basel Committee on Banking Supervision

| # | Document | Ref | Date | Status | Used for | URL |
|---|---|---|---|---|---|---|
| 1 | **Minimum capital requirements for market risk** | **d457** | Jan 2019, rev. **Feb 2019** | **Current standard** | **The primary source for this library.** `RBC25`, `MAR10`–`MAR99`: boundary, SBM, DRC, RRAO, IMA, ES, liquidity horizons, RFET, NMRF, backtesting, PLA, capital aggregation | https://www.bis.org/bcbs/publ/d457.pdf |
| 2 | Consolidated Basel Framework | — | ongoing | Current | Authoritative current text of all chapters cited | https://www.bis.org/basel_framework/ |
| 3 | The market risk framework — In brief | — | Jan 2019 | Current | Framework intent | https://www.bis.org/bcbs/publ/d457_inbrief.pdf |
| 4 | Explanatory note on the minimum capital requirements for market risk | — | Jan 2019 | Current | Design rationale for ES, liquidity horizons, NMRF, SBM calibration | https://www.bis.org/bcbs/publ/d457_note.pdf |
| 5 | Press release: revised framework for market risk capital requirements | — | 14 Jan 2016 | Historical | Original 2016 standard; Dec 2017 extension to 2022 | https://www.bis.org/press/p160114.htm |
| 6 | FAQs on market risk capital requirements | d437 | 2018 | Supplementary | Interpretation | https://www.bis.org/bcbs/publ/d437.pdf |
| 7 | **Credit valuation adjustment framework** | **`MAR50`** | ongoing | Current | CVA risk framework; SA-CVA, BA-CVA | https://www.bis.org/basel_framework/chapter/MAR/50.htm |
| 8 | Targeted revisions to the CVA risk framework | **d507** | 2020 | Current, **effective 1 Jan 2023** | Recalibrated weights; client-cleared treatment | https://www.bis.org/bcbs/publ/d507.pdf |
| 9 | Credit Valuation Adjustment risk: targeted final revisions | d488 | 2019 | Superseded by d507 | Preceding revision | https://www.bis.org/bcbs/publ/d488.pdf |
| 10 | Review of the Credit Valuation Adjustment Risk Framework | d325 | 2015 | Historical | Original review | https://www.bis.org/bcbs/publ/d325.pdf |
| 11 | **Interest rate risk in the banking book** | **d368** | Apr 2016 | Current | IRRBB standard; six shock scenarios; outlier test | https://www.bis.org/bcbs/publ/d368.pdf |
| 12 | **Recalibration of shocks for IRRBB** | **d578** | **16 Jul 2024** | **Current — implement by 1 Jan 2026** | Four recalibration changes: time series to Dec 2023; local shock factors; 99.9th percentile; 25bp rounding | https://www.bis.org/bcbs/publ/d578.pdf |
| 13 | Interest rate risk in the banking book | `SRP31` | ongoing | Current | Consolidated IRRBB text | https://www.bis.org/basel_framework/chapter/SRP/31.htm |
| 14 | IRRBB: Pillar 2 standardised framework — Executive Summary (BIS FSI) | — | ongoing | Current | **15% of Tier 1** outlier threshold; supervisory additional tests | https://www.bis.org/fsi/fsisummaries/irrbb.htm |
| 15 | Counterparty credit risk in Basel III — Executive Summary (BIS FSI) | — | ongoing | Current | SA-CVA / BA-CVA / CCR-proxy approaches | https://www.bis.org/fsi/fsisummaries/ccr_in_b3.htm |
| 16 | **Principles for effective risk data aggregation and risk reporting** | **BCBS 239** | Jan 2013 | Current | Data aggregation, lineage, reporting principles | https://www.bis.org/publ/bcbs239.pdf |
| 17 | Amendment to the Capital Accord to incorporate market risks | bcbs24 | Jan 1996 | **Superseded** | Historical VaR framework | https://www.bis.org/publ/bcbs24.pdf |
| 18 | Supervisory framework for the use of backtesting | bcbs22 | Jan 1996 | Historical | Origin of the traffic-light framework | https://www.bis.org/publ/bcbs22.pdf |
| 19 | Revisions to the securitisation framework | d303 / d374 / **d442** | 2014 / 2016 / 2018 | Current | Referenced by `MAR22.20` | https://www.bis.org/bcbs/publ/d442.pdf |
| 20 | Supervisory framework for measuring and controlling large exposures | bcbs283 | Apr 2014 | Current | Covered bond definition referenced by `MAR21.51` | https://www.bis.org/publ/bcbs283.pdf |

---

## 3. Tier 1 — European Union

| # | Document | Ref | Date | Status | Used for | URL |
|---|---|---|---|---|---|---|
| 21 | **Regulation (EU) 2024/1623 (CRR3)** — amending Regulation (EU) No 575/2013 as regards credit risk, **CVA risk**, operational risk, **market risk** and the **output floor** | 2024/1623 | In force **9 Jul 2024**; general application **1 Jan 2025** | **In force** | EU implementation of final Basel III | https://eur-lex.europa.eu/eli/reg/2024/1623/oj |
| 22 | **EU temporarily amends prudential rules for banks' market risk** | Delegated act under Art. 461a | **4 Jun 2026** | **Adopted; 3-month scrutiny** | **Targeted multiplier and operational relief**, applying **1 Jan 2027 for three years** | https://finance.ec.europa.eu/news/eu-temporarily-amends-prudential-rules-banks-market-risk-2026-06-08_en |
| 23 | Commission proposes to postpone by one additional year the market risk requirements | Delegated act | **12 Jun 2025** | Applied | Deferral of FRTB own funds to **1 Jan 2027** | https://finance.ec.europa.eu/news/commission-proposes-postpone-one-additional-year-market-risk-prudential-requirements-under-basel-iii-2025-06-12_en |
| 24 | EBA responds to the Commission's Delegated Act postponing the market risk framework | — | 2024/2025 | Current | Art. 461a mechanism; first deferral (24 Jul 2024) to 1 Jan 2026 | https://www.eba.europa.eu/publications-and-media/press-releases/eba-responds-european-commissions-delegated-act-postponing-application-market-risk-framework-eu |

---

## 4. Tier 1 — United Kingdom

| # | Document | Ref | Date | Status | Used for | URL |
|---|---|---|---|---|---|---|
| 25 | **Implementation of Basel 3.1: Final rules** | **PS1/26** | **Jan 2026** | **Final** | UK implementation: general **1 Jan 2027**; **market risk IMA 1 Jan 2028** | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/january/implementation-of-the-basel-3-1-final-rules-policy-statement |
| 26 | Basel 3.1: Adjustments to the internal model approach (IMA) for market risk | **CP9/26** | **Jun 2026** | **Consultation** | Proposed IMA adjustments | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/june/basel-3-1-adjustments-to-the-internal-model-approach-for-market-risk-consultation-paper |
| 27 | Restatement of CRR requirements — 2027 implementation — final | PS3/26 | Jan 2026 | Final | UK rulebook restatement | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/january/restatement-of-crr-requirements-final-policy-statement |
| 28 | Implementation of the Basel 3.1 standards — near-final part 2 | PS9/24 | Sep 2024 | Superseded by PS1/26 | Near-final rules | https://www.bankofengland.co.uk/prudential-regulation/publication/2024/september/implementation-of-the-basel-3-1-standards-near-final-policy-statement-part-2 |
| 29 | The PRA announces a delay to the implementation of Basel 3.1 | — | **Jan 2025** | Applied | One-year delay to 1 Jan 2027 | https://www.bankofengland.co.uk/news/2025/january/the-pra-announces-a-delay-to-the-implementation-of-basel-3-1 |
| 30 | PRA sets out adjustments to its market risk IMA under Basel 3.1 | — | Jun 2026 | Current | CP9/26 announcement | https://www.bankofengland.co.uk/news/2026/june/pra-adjustments-market-risk-internal-model-approach-under-basel31 |
| 31 | **Model risk management principles for banks** | **SS1/23** | May 2023, **effective 17 May 2024** | **Current** | Five MRM principles | https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss |

---

## 5. Tier 1 — United States

| # | Document | Ref | Date | Status | Used for | URL |
|---|---|---|---|---|---|---|
| 32 | Agencies request comment on proposals to modernize the regulatory capital framework | — | **19 Mar 2026** | ⚠ **PROPOSED — NOT EFFECTIVE** | US capital re-proposal; market risk scope; comments closed **18 Jun 2026** | https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260319a.htm |
| 33 | **Regulatory Capital: Category I and II Banking Organizations, Banking Organizations With Significant Trading Activity…** | **OCC Bulletin 2026-9** | **19 Mar 2026** | ⚠ **PROPOSED** | Market risk applies at **≥$5bn trading assets + liabilities**, or **>10% of total assets**; **ERBA** replaces the advanced approaches | https://www.occ.gov/news-issuances/bulletins/2026/bulletin-2026-9.html |
| 34 | **SR 26-2 — Revised Guidance on Model Risk Management** | **SR 26-2** | **17 Apr 2026** | **CURRENT** | **Supersedes and replaces SR 11-7 and SR 21-8.** Model definition; $30bn applicability; AI scope; effective challenge; validation components | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf |
| 35 | SR 11-7 — Guidance on Model Risk Management | SR 11-7 | 4 Apr 2011 | ⚠ **SUPERSEDED** (17 Apr 2026) | Historical reference only | https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm |
| 36 | **2026 Stress Test Scenarios** | — | **4 Feb 2026** | **Current** | Scenario horizon Q1 2026–Q1 2029; **GMS as-of date 17 Oct 2025**; calibration changes | https://www.federalreserve.gov/publications/2026-stress-test-scenarios.htm |
| 37 | Supervisory Stress Test Documentation: Final 2026 Global Market Shock Component | — | 2026 | Current | GMS construction and scope | https://www.federalreserve.gov/supervisionreg/files/2026-final-gms-model.pdf |
| 38 | Board finalizes hypothetical scenarios for its annual stress test | — | 4 Feb 2026 | Current | Finalisation date | https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260204a.htm |

---

## 6. Tier 1 — Industry standard-setter

| # | Document | Ref | Date | Status | Used for | URL |
|---|---|---|---|---|---|---|
| 39 | **ISDA SIMM Methodology, version 2.8+2512** | v2.8+2512 | Published **12 Jun 2026**, effective **11 Jul 2026** | **Current** | Current SIMM version; calibration to 31 Dec 2025 | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ |
| 40 | ISDA SIMM Methodology, version 2.8+2506 | v2.8+2506 | 31 Oct 2025, effective 6 Dec 2025 | Superseded | Preceding version; semiannual cycle introduced 2025 | https://www.isda.org/2025/10/31/isda-publishes-isda-simm-methodology-version-2-8-2506/ |
| 41 | ISDA CDS Standard Model | — | ongoing | Current | CDS pricing and upfront conventions | https://www.isda.org/ |
| 42 | 2021 ISDA Interest Rate Derivatives Definitions | — | 2021 | Current | Day counts, business day conventions, fixings | https://www.isda.org/ |

---

## 7. Tier 2 — Market infrastructure and central banks

| # | Source | Used for | URL |
|---|---|---|---|
| 43 | **CME Group** | WTI crude contract specifications; the **20 April 2020 negative settlement**; Treasury futures conversion factors and delivery mechanics | https://www.cmegroup.com/ |
| 44 | **London Metal Exchange** | **March 2022 nickel events**, including trade cancellation | https://www.lme.com/ |
| 45 | **Swiss National Bank** | **15 January 2015** discontinuation of the EUR/CHF minimum exchange rate | https://www.snb.ch/ |
| 46 | **U.S. Treasury** | Daily Treasury Par Yield Curve Rates; discount vs coupon-equivalent quoting bases | https://home.treasury.gov/ |
| 47 | **ARRC / New York Fed** | SOFR conventions; RFR transition and multi-curve construction | https://www.newyorkfed.org/arrc |
| 48 | **BIS Quarterly Review** | Covered interest parity deviations; mortgage convexity hedging analyses | https://www.bis.org/publ/qtrpdf/ |

---

## 8. Tier 3 — Academic

| # | Source | Used for |
|---|---|---|
| 49 | **Artzner, Delbaen, Eber & Heath, *Coherent Measures of Risk*, Mathematical Finance 9(3), 1999** | The coherence axioms; VaR's failure of sub-additivity; ES's coherence — [12 §3.2](12_Expected_Shortfall.md) |
| 50 | Macaulay, F. (1938) — duration | Historical origin of the duration concept |
| 51 | Black & Scholes (1973); Merton (1973) | Option pricing formulas |
| 52 | Bachelier (1900) | The normal option pricing model |
| 53 | Higham (2002) — nearest correlation matrix | PSD repair methods — [10 §3.3](10_Portfolio_Risk_Mathematics.md) |
| 54 | Ledoit & Wolf — shrinkage estimation | Covariance matrix conditioning |
| 55 | Kupiec (1995); Christoffersen (1998) | Backtesting coverage and independence tests — [15 §3.3](15_Backtesting.md) |

> **Academic citations 50–55 are given by author and result rather than by URL**, as the results are standard and available in any graduate text. They are used only for mathematical exposition, never for regulatory claims.

---

## 9. Status flags — what to re-verify and why

| ⚠ | Item | Issue |
|---|---|---|
| **PROPOSED** | US market risk framework (#32, #33) | **Not legally effective.** Comments closed 18 Jun 2026. Any finalisation date is an expectation, not a fact — **UNVERIFIED** |
| **SUPERSEDED** | SR 11-7 (#35) | Replaced by SR 26-2 on 17 Apr 2026. Most pre-2026 material still cites it as current |
| **SUPERSEDED** | PS9/24 (#28) | Replaced by PS1/26, Jan 2026 |
| **UNDER SCRUTINY** | EU delegated act (#22) | Three-month Parliament/Council scrutiny from 4 Jun 2026; applies 1 Jan 2027 **if no objection** |
| **CONSULTATION** | CP9/26 (#26) | UK IMA adjustments not final |
| **RECALIBRATED** | IRRBB shocks (#12) | Pre-2024 shock magnitudes are **out of date**; d578 implemented by 1 Jan 2026 |
| **SEMIANNUAL** | ISDA SIMM (#39) | Two version changes per year, each with a hard effective date |

---

## 10. What this library does **not** rely on

**Stated explicitly, because the absence is deliberate.**

| Excluded | Why |
|---|---|
| **Vendor documentation** | Used nowhere as authority for a regulatory claim. Where a vendor convention is described, it is labelled as market practice |
| **Consultancy publications** | Useful for orientation; not evidence |
| **Secondary summaries of regulations** | Every regulatory parameter is taken from the primary text and cited to paragraph |
| **Undated market "facts"** | Any figure without a source and a date is not stated |
| **Invented shock magnitudes** | [13 §4.1](13_Stress_Testing.md) — shock vectors must be extracted from data, and this library's stress examples are **labelled as constructed** |
| **Specific PCA variance shares** | [04 §7](04_Interest_Rate_Risk.md) marks these **UNVERIFIED**; they must be estimated on the relevant sample |

---

## 11. Constructed data used in worked examples

**Every one of these is for exposition and is not a market observation.**

| Where | What is constructed |
|---|---|
| [30 §1.2](30_Worked_Examples.md) | The nine-node zero curve and four-bond portfolio |
| [30 §5](30_Worked_Examples.md) | 250 VaR scenarios, from a stated three-factor Student-t(5) process |
| [30 §6](30_Worked_Examples.md) | Stress shock vectors — *shaped to resemble* named episodes, **not** the observed moves |
| [10 §](10_Portfolio_Risk_Mathematics.md) | The three-asset portfolio, volatilities and correlations |
| [42 §4](42_Risk_Aggregation.md) | Desk VaRs and the five-desk correlation matrix |
| [11 §4.5](11_VaR.md), [12 §5](12_Expected_Shortfall.md) | The ten-worst-scenario tail |
| [21 §9](21_Market_Risk_Limits.md) | The desk limit pack |
| [28 §3.2](28_Reporting_and_Dashboards.md) | The daily market risk report |
| [17 §6](17_FRTB_Standardised_Approach.md), [19 §7](19_Default_Risk_and_DRC.md), [20 §7.6](20_NMRF_and_Modellability.md) | Position sets — **the regulatory parameters applied to them are real and cited** |

> **The distinction that matters:** in every FRTB worked example the *positions* are constructed and the *risk weights, correlations and formulas* are taken from the Basel text and cited to paragraph. A reader can substitute their own positions and the calculation remains correct.

---

## 12. Related Concepts

- [29 — Regulatory Framework](29_Regulatory_Framework.md) — the full status tracker
- [00 — Master Index](00_Master_Index.md)

---

*All rows verified 25 August 2026.*
