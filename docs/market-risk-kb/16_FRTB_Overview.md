# 16 — FRTB Overview

**Level:** 10 · **Prerequisites:** [11](11_VaR.md)–[15](15_Backtesting.md) · **Feeds:** [17](17_FRTB_Standardised_Approach.md)–[20](20_NMRF_and_Modellability.md), [29](29_Regulatory_Framework.md)

> **Terminology note used throughout this library.** "FRTB" is the market's name for the Basel Committee's revised market risk framework, published as *Minimum capital requirements for market risk* (BCBS d457, January 2019, rev. February 2019) and integrated into the consolidated Basel Framework as chapters `RBC25` and `MAR10`–`MAR99`. **FRTB is a Basel standard, not law anywhere.** It becomes binding only through each jurisdiction's own implementing rules, whose content and timing differ — see [29](29_Regulatory_Framework.md) and §9 below.

---

## 1. Why FRTB was created

The pre-crisis market risk framework — the 1996 Market Risk Amendment, patched in 2009 as "Basel 2.5" — failed in identifiable, specific ways during 2007–09. FRTB is a response to each of them, and the framework is much easier to understand as a list of answers to failures than as an abstract design.

| Pre-crisis failure | What went wrong | FRTB's answer |
|---|---|---|
| **A porous book boundary** | Instruments were moved between trading and banking book to obtain the more favourable capital treatment | `RBC25`: presumptive assignments, strict switching restrictions, supervisory powers |
| **VaR ignored the tail** | 99% VaR said nothing about severity beyond the threshold; and VaR is not sub-additive | **97.5% Expected Shortfall** (`MAR33.3`) |
| **A single 10-day horizon** | Assumed everything could be exited in ten days; in the crisis, much could not be exited at all | **Liquidity horizons** of 10–120 days by risk factor (`MAR33.4`, `MAR33.12`) |
| **Unmodellable factors got full diversification** | Thinly-observed factors sat in VaR models with no evidential basis and full offset | **RFET** and the **NMRF/SES** regime (`MAR31`) |
| **Bank-wide model approval** | One approval covered everything; a failing desk was invisible inside the aggregate | **Desk-level** approval, backtesting and PLA (`MAR12`, `MAR32`) |
| **A weak, non-risk-sensitive standardised approach** | Too crude to be a credible fallback, so supervisors could not withdraw model permission | **SBM**, a genuinely risk-sensitive SA (`MAR21`) |
| **Default risk understated** | Spread models could not represent a jump to default | **DRC**, calibrated to the banking book (`MAR22`) |
| **Exotic risks uncaptured** | Gap, correlation and behavioural risks fell through the sensitivity framework | **RRAO** (`MAR23`) |
| **Correlations assumed stable** | Diversification benefit evaporated exactly when needed | **Three correlation scenarios** (`MAR21.6`) |

> **The single organising idea:** make the standardised approach good enough that supervisors can credibly take a model away, and make model approval granular enough that they can take away *part* of it. Every other design choice follows from that.

---

## 2. The architecture

```
                         MARKET RISK CAPITAL
                                  │
             ┌────────────────────┴────────────────────┐
             ▼                                         ▼
   STANDARDISED APPROACH (SA)              INTERNAL MODELS APPROACH (IMA)
   MAR20 – MAR23                           MAR30 – MAR33
   Mandatory for ALL banks                 Optional, desk-by-desk, on approval
             │                                         │
   ┌─────────┼─────────┐               ┌───────────────┼───────────────┐
   ▼         ▼         ▼               ▼               ▼               ▼
  SBM       DRC      RRAO           IMCC            SES             DRC
 MAR21     MAR22    MAR23        (modellable      (non-modellable   (IMA)
   │                              factors, ES)     factors,
   │                                   │           stress scenario)
 ┌─┴──┬───────┐                        │
 ▼    ▼       ▼                   97.5% ES, stress-calibrated,
Delta Vega Curvature              liquidity-horizon adjusted
   │                                   │
   └──► × 3 correlation scenarios      └──► gated by: desk approval,
        (medium / high / low),                RFET, backtesting, PLA
        take the MAXIMUM
```

### 2.1 The SA is not optional

`MAR20.3`: a bank must determine its SA capital requirement **at the demand of its supervisor**. In practice every bank computes the SA for every position, whether or not it has model approval, because:

- it is the **fallback** for any desk that loses or never had IMA approval;
- it is the basis of the **output floor** in the wider Basel III package;
- `MAR20.2` requires it to be **calculated and reported monthly** (quarterly, subject to supervisory approval, for market risks arising from non-banking subsidiaries).

### 2.2 RWA conversion

`MAR20.1`: **risk-weighted assets for market risk under the SA are the capital requirement multiplied by 12.5.** (The factor is `1/0.08`, converting a capital requirement into an RWA equivalent at the 8% minimum ratio.) The equivalent provision for the IMA is `MAR33.46`.

---

## 3. The Standardised Approach — structure

`MAR20.4` states it plainly:

> **The standardised approach capital requirement is the simple sum of three components: the capital requirement under the sensitivities-based method, the default risk capital (DRC) requirement and the residual risk add-on (RRAO).**

```
   SA capital  =  SBM  +  DRC  +  RRAO
```

**"Simple sum" is exact and important.** There is no diversification recognised *between* the three components. A bank cannot argue that its DRC exposure hedges its SBM exposure.

### 3.1 The three components

| Component | Chapter | Captures | Mechanism |
|---|---|---|---|
| **SBM** | `MAR21` | Sensitivity to market factor moves | Delta + vega + curvature, over 7 risk classes, bucketed and correlation-aggregated |
| **DRC** | `MAR22` | **Jump-to-default** risk | Gross/net JTD, default risk weights, hedge benefit ratio |
| **RRAO** | `MAR23` | Residual risks in exotic instruments | **Gross notional × 1.0% or 0.1%** |

### 3.2 Basel's own rationale for each

**SBM** (`MAR20.4(1)`): three risk measures — delta (sensitivities to regulatory delta risk factors), vega (sensitivities to regulatory vega risk factors), and **curvature** ("a risk measure which captures the incremental risk not captured by the delta risk measure for price changes in an option … based on two stress scenarios involving an upward shock and a downward shock to each regulatory risk factor").

Risk-weighted sensitivities are aggregated with specified correlations "to recognise diversification benefits between risk factors." And then, explicitly: *"In order to address the risk that correlations may increase or decrease in periods of financial stress, a bank must calculate three sensitivities-based method capital requirement values"* (`MAR21.6`, `MAR21.7`).

**DRC** (`MAR20.4(2)`): captures jump-to-default risk and *"is calibrated based on the credit risk treatment in the banking book in order to reduce the potential discrepancy in capital requirements for similar risk exposures across the bank."* Some hedging recognition is allowed within similar exposure types — corporates, sovereigns, and local governments/municipalities.

> **That calibration choice is the anti-arbitrage mechanism.** If trading-book default risk were charged materially less than banking-book credit risk on the same obligor, the boundary would be worth gaming. Aligning the DRC to the banking-book treatment removes most of the incentive.

**RRAO** (`MAR20.4(3)`): Basel is candid that *"not all market risks can be captured in the standardised approach, as this might necessitate an unduly complex regime."* The RRAO exists "to ensure sufficient coverage." It is deliberately crude — a notional-based charge — because the alternative was an unmanageably complex taxonomy of exotic risks.

### 3.3 The correlation trading portfolio

`MAR20.5` defines the CTP for the purposes of CSR under the SBM and of the DRC. A securitisation position qualifies only if, among other conditions:

- it is **not** a re-securitisation position, nor a derivative of securitisation exposures lacking a pro-rata share in a tranche's proceeds;
- **all reference entities are single-name products** — including single-name credit derivatives — **for which a liquid two-way market exists**, including traded indices on those entities;
- it does **not** reference an underlying treated as a retail, residential mortgage, or commercial mortgage exposure under the SA to credit risk.

The CTP receives its own CSR risk class and its own DRC treatment because hedging relationships within a genuine correlation book are real — and the framework grants limited recognition of them that it refuses to non-CTP securitisations.

---

## 4. The Internal Models Approach — structure

```
   IMA capital (non-DRC)  =  max( IMCC_{t−1} + SES_{t−1} ,
                                  m_c · IMCC_avg60  +  SES_avg60 )     (MAR33.41)

   IMA_{G,A}              =  above  +  DRC                              (MAR33.43)

   Total market risk capital  =  IMA_{G,A}  +  C_U  (+ PLA surcharge)   (MAR33.43)
```

where `C_U` is the SA capital for desks that are out of scope for model approval or have been deemed ineligible (`MAR33.40`).

| Term | Meaning |
|---|---|
| **IMCC** | Internally modelled capital charge for **modellable** risk factors — the liquidity-adjusted, stress-calibrated 97.5% ES, weighted between unconstrained and risk-class-constrained versions (`MAR33.13`–`MAR33.15`) |
| **SES** | Stress scenario capital for **non-modellable** risk factors ([20](20_NMRF_and_Modellability.md)) |
| **m_c** | Multiplication factor, **fixed at 1.5** unless raised by the supervisor for a qualitative add-on and/or a backtesting add-on of **0 to 0.5** (`MAR33.42`) |
| **DRC** | Default risk capital under the IMA (`MAR33`) |
| **C_U** | SA capital for out-of-scope and ineligible desks (`MAR33.40`) |

### 4.1 The four gates a desk must pass

The IMA is not granted once. A desk must continuously satisfy:

| Gate | Test | Failure consequence |
|---|---|---|
| **1. Desk definition** | Meets `MAR12` — one head, defined strategy, documented risk structure | Not eligible to apply |
| **2. Risk factor eligibility** | RFET: enough **real price observations** per factor (`MAR31.12`–`MAR31.24`) | Factor becomes an **NMRF** → capitalised via SES |
| **3. Backtesting** | ≤12 exceptions @99% **and** ≤30 @97.5% over 12 months (`MAR32.19`) | Desk moves to the **standardised approach** |
| **4. PLA test** | Spearman >0.80 **and** KS <0.09 for green (`MAR32.42`) | Red → SA; amber → **capital surcharge** |

Plus a firm-wide condition: **`MAR32.2` requires at least 10% of the bank's aggregated market risk capital requirement to come from IMA-qualifying desks**, assessed quarterly — an anti-cherry-picking floor.

All of these are re-assessed on a **quarterly** cycle (`MAR32.7`, `MAR33.44`).

---

## 5. The trading book boundary

`RBC25` governs which instruments are in scope at all, and it is the foundation everything else rests on. Treated in full in [20 — Trading Book Boundary and IRRBB](20A_Trading_Book_Boundary_and_IRRBB.md); the essentials:

| Mechanism | Purpose |
|---|---|
| **Presumptive assignment lists** | Certain instruments are presumed trading book (or banking book) unless the bank rebuts and the supervisor agrees |
| **Documentation of designation** | Every instrument's assignment must be documented at inception |
| **Restrictions on moving instruments** | Switching requires supervisory approval; any capital benefit from a switch is **disallowed** |
| **Supervisory powers** | The supervisor may require re-designation |
| **Internal risk transfer rules** | Strict conditions on recognising transfers between banking and trading book |

> **The switching rule is the sharpest instrument in the chapter.** The capital benefit from a re-designation is removed, which means an instrument can be moved for genuine business reasons but never for capital advantage. That single provision closes the arbitrage that motivated much of the boundary work.

---

## 6. Which approach applies to what

```
   FOR each trading desk:

       IF desk has supervisory IMA approval
          AND passes backtesting (MAR32.19)
          AND PLA zone is GREEN or AMBER (MAR32.42):

              modellable risk factors  → IMCC (97.5% ES)
              non-modellable factors   → SES
              issuer default risk      → DRC under IMA
                                          (requires the SECOND-STAGE approval,
                                           MAR32.19 footnote 1)
              IF PLA zone is AMBER     → add the MAR33.43 surcharge

       ELSE:
              ALL positions on this desk  →  STANDARDISED APPROACH
              i.e. SBM + DRC + RRAO, included in C_U

   ALSO, for every bank regardless of the above:
       compute and report the full SA (MAR20.2, MAR20.3)
```

**The RRAO deserves a note here:** it is an SA component. A bank whose desks are all on the IMA still computes the RRAO for instruments in scope, because the IMA does not capture the residual risks the RRAO exists to cover.

---

## 7. The simplified standardised approach

`MAR40` retains a **simplified standardised approach** — essentially the pre-FRTB framework, with interest rate risk (including a duration-based method), equity risk, FX risk, commodities risk and a treatment of options.

It is intended for banks with small, simple trading operations, and its availability is a **national discretion**. A bank of any size or trading complexity should not expect it to be available. Do not confuse `MAR40` with `MAR20`–`MAR23`: **the "standardised approach" in every FRTB discussion means the SBM/DRC/RRAO framework, not `MAR40`.**

---

## 8. What FRTB changed, in one table

| Dimension | Pre-FRTB (1996 / Basel 2.5) | FRTB |
|---|---|---|
| Risk measure | 99% VaR + Stressed VaR + IRC + CRM | **97.5% Expected Shortfall** |
| Horizon | 10 days, uniform | **10–120 days**, by risk factor |
| Model approval | Bank-wide | **Desk-by-desk** |
| Model validation | Backtesting | Backtesting **+ PLA test** |
| Backtesting levels | 99% | 99% bank-wide; **97.5% and 99%** at desk |
| Multiplier | 3 + add-on | **1.5 + add-on (0–0.5)** |
| Traffic-light zones | Yes | **Yes — retained** (`MAR32.8`–`MAR32.9`) |
| Illiquid factors | In VaR, fully diversified | **NMRF → SES**, limited diversification |
| Standardised approach | Crude building-block | **Risk-sensitive SBM + DRC + RRAO** |
| Correlation stress | None | **Three scenarios, take the worst** |
| Book boundary | Intent-based, porous | Presumptive lists, switching restrictions |
| Default risk | IRC (models) | **DRC**, calibrated to the banking book |

---

## 9. Implementation status — Basel standard versus local law

**The Basel standard is complete and stable. Its adoption is neither uniform nor finished.** As at the date of this document:

| Jurisdiction | Status | Key dates |
|---|---|---|
| **Basel (global)** | Standard finalised | Published Jan 2019 (rev. Feb 2019); Basel implementation date was 1 Jan 2023 |
| **European Union** | CRR3 applied generally from 1 Jan 2025, but the **FRTB own-funds requirements were deferred**. The Commission adopted a delegated act on **4 June 2026** under the Article 461a CRR empowerment introducing a **targeted multiplier and targeted operational relief measures**, applying from **1 January 2027 for a three-year period**, subject to the three-month Parliament/Council scrutiny period | FRTB application **1 Jan 2027** |
| **United Kingdom** | PRA published **PS1/26 – Implementation of Basel 3.1: Final rules** in January 2026. General implementation **1 January 2027**; the **market risk IMA is delayed to 1 January 2028**, for international coordination. The PRA consulted further on IMA adjustments in **CP9/26** (June 2026) | SA **1 Jan 2027**; IMA **1 Jan 2028** |
| **United States** | The 2023 Basel III endgame proposal was **formally rescinded**. On **19 March 2026** the Federal Reserve, OCC and FDIC issued new proposals, including one to modernise capital requirements for Category I and II banking organizations **and the market risk capital framework for banking organizations with significant trading activity**. The agencies state the market risk aspect *"would apply only to banks with significant trading activity."* Comments were due **18 June 2026** | **Proposed, not final** |

> **Three cautions that follow directly.**
>
> 1. **Never describe the U.S. market risk rules as effective.** As at this document's date they are a proposal with a closed comment period, not a final rule.
> 2. **Never assume the EU is applying the pure Basel calibration.** The EU is applying a multiplier and operational relief for three years from 2027 explicitly to neutralise capital impact, citing competitive disadvantage from unilateral implementation.
> 3. **Never assume one date per jurisdiction.** The UK has split SA (2027) from IMA (2028). A single "UK FRTB go-live" date does not exist.

Full detail, with the regulatory status fields required for each framework, is in [29 — Regulatory Framework](29_Regulatory_Framework.md).

---

## 10. Reading order for the rest of the FRTB material

| Document | Covers |
|---|---|
| [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) | SBM in full: risk classes, buckets, weights, correlations, aggregation, curvature; RRAO |
| [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md) | Desk eligibility, ES, liquidity horizons, backtesting, PLA, capital aggregation |
| [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md) | JTD, gross/net, hedge benefit ratio, buckets, DRC under SA and IMA |
| [20 — NMRF and Modellability](20_NMRF_and_Modellability.md) | RFET, real price observations, SES |
| [20 — Trading Book Boundary and IRRBB](20A_Trading_Book_Boundary_and_IRRBB.md) | `RBC25`, presumptive lists, internal risk transfers, IRRBB comparison |
| [29 — Regulatory Framework](29_Regulatory_Framework.md) | Jurisdictional status tracker with full status fields |

---

## 11. Common misconceptions

| Misconception | Correction |
|---|---|
| "FRTB replaced VaR with ES" | ES replaced VaR **for capital**. VaR remains the **backtesting** measure at both bank-wide and desk level (`MAR32.5`, `MAR32.18`) |
| "The traffic lights are gone" | **Retained** for bank-wide backtesting (`MAR32.8`–`MAR32.9`); the multiplier scale changed from 3+ to 1.5–2.0 |
| "SA is only for small banks" | Every bank computes it; it is the fallback, the reporting requirement, and the floor basis (`MAR20.2`, `MAR20.3`) |
| "SA = `MAR40`" | No — `MAR40` is the **simplified** SA, a national discretion. The SA is `MAR20`–`MAR23` |
| "IMA approval is firm-wide" | It is **desk by desk**, reassessed quarterly |
| "SBM + DRC + RRAO are diversified together" | `MAR20.4`: **simple sum**, no diversification between components |
| "FRTB is in force" | It is a **Basel standard**; each jurisdiction implements separately, with different dates and calibrations (§9) |
| "A model, once approved, stays approved" | Backtesting, PLA and the RFET are quarterly gates with real consequences |

---

## 12. Related Concepts

- [01A — Master Market Risk Taxonomy](01A_Master_Market_Risk_Taxonomy.md) — the seven SBM risk classes in context
- [12 — Expected Shortfall](12_Expected_Shortfall.md) · [15 — Backtesting](15_Backtesting.md)
- [17](17_FRTB_Standardised_Approach.md)–[20](20_NMRF_and_Modellability.md) · [29](29_Regulatory_Framework.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25`, `MAR10`–`MAR40` — the entire framework |
| BCBS | *The market risk framework — In brief* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_inbrief.pdf | Framework intent and rationale |
| BCBS | *Explanatory note on the minimum capital requirements for market risk* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_note.pdf | Design rationale for ES, liquidity horizons, NMRF |
| European Commission | EU temporarily amends prudential rules for banks' market risk | 4 Jun 2026 | https://finance.ec.europa.eu/news/eu-temporarily-amends-prudential-rules-banks-market-risk-2026-06-08_en | EU delegated act, multiplier, 1 Jan 2027 application |
| Bank of England / PRA | PS1/26 – Implementation of Basel 3.1: Final rules | Jan 2026 | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/january/implementation-of-the-basel-3-1-final-rules-policy-statement | UK dates: SA 2027, IMA 2028 |
| Bank of England / PRA | CP9/26 – Basel 3.1: Adjustments to the IMA for market risk | Jun 2026 | https://www.bankofengland.co.uk/prudential-regulation/publication/2026/june/basel-3-1-adjustments-to-the-internal-model-approach-for-market-risk-consultation-paper | UK IMA adjustments consultation |
| Federal Reserve | Agencies request comment on proposals to modernize the regulatory capital framework | 19 Mar 2026 | https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260319a.htm | US proposal status, scope, comment deadline |

*Accessed 25 August 2026.*
