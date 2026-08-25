# 41 — Market Risk versus Related Risk Types

**Level:** 12 · **Prerequisites:** [01](01_Market_Risk_Fundamentals.md), [22](22_Counterparty_CVA_and_SIMM.md), [20A](20A_Trading_Book_Boundary_and_IRRBB.md)

> **The resolving question is always the same: what event causes the loss?**
>
> A *price* moving is market risk. A *borrower* failing is credit risk. A *derivative counterparty* failing is counterparty credit risk. The *value of the adjustment for counterparty failure* moving is CVA risk. All four can arise from the same trade on the same day, and each is capitalised once, in its own framework.

---

## 1. Why classification matters

**Not academic.** Misclassification produces two specific, opposite failures, and supervisors care about both:

| Failure | Mechanism |
|---|---|
| **Double-counting** | The same exposure capitalised in two frameworks — wasteful, and it distorts business decisions |
| **Gapping** | An exposure falling between frameworks and capitalised in neither — the dangerous one |

**The most common analytical error is treating everything with a price as market risk.** A defaulted loan's recovery uncertainty has a price; it is credit risk. A derivative counterparty's default has a market-driven exposure amount; it is counterparty credit risk.

---

## 2. The comparison

| Risk | Loss event | Framework | Primary metric | Book |
|---|---|---|---|---|
| **Market risk** | A **price or market variable** moves | FRTB (`MAR20`–`MAR33`) | ES, VaR, sensitivities, stress | Trading |
| **Credit risk** | A **borrower** fails to pay | Credit risk RWA (`CRE`) | PD, LGD, EAD, expected loss | Banking |
| **Counterparty credit risk** | A **derivative counterparty** defaults owing MTM | SA-CCR / IMM (`CRE52`) | EAD, EPE, PFE | Both |
| **CVA risk** | The **value of the counterparty adjustment** moves | `MAR50` | CVA sensitivities | Trading (derivatives) |
| **Default risk in the trading book** | An **issuer of a held instrument** defaults | **DRC** (`MAR22`, `MAR33`) | JTD | Trading |
| **IRRBB** | Rates move, affecting the **banking book** | `SRP31` (Pillar 2) | ΔEVE, ΔNII | Banking |
| **Liquidity risk (funding)** | Cannot fund or roll obligations | LCR / NSFR | LCR, NSFR, survival horizon | Firm-wide |
| **Liquidity risk (market)** | Cannot exit at the marked price | Internalised via **liquidity horizons** | Days-to-liquidate, bid-offer | Trading |
| **Operational risk** | Failed processes, people, systems | Operational risk framework | Loss events, scenarios | Firm-wide |
| **Model risk** | A model is wrong, or wrongly used | SR 26-2 / SS1/23 | Validation findings, model inventory | Firm-wide |
| **Settlement risk** | Delivered value, did not receive it | Settlement/CCR frameworks | Settlement exposure | Both |
| **Concentration risk** | Position too large relative to the market | Not a standalone Pillar 1 charge | Position vs ADV; top-N | Both |
| **Margin / collateral risk** | Margin calls exceed available liquidity | Liquidity frameworks | Collateral outflow under stress | Firm-wide |
| **ALM** | Structural balance-sheet mismatch | IRRBB, liquidity | EVE, NII, gap analysis | Banking |

---

## 3. Market risk versus credit risk

| | Market risk | Credit risk |
|---|---|---|
| Loss driver | **Price change** | **Counterparty failure** |
| Loss profile | Two-sided, continuous | One-sided, discrete |
| Distribution | Roughly symmetric, fat-tailed | **Highly skewed** — small gains, large rare losses |
| Horizon | 1–120 days | 1 year (typically) |
| Accounting | **Fair value through P&L** | Amortised cost, with impairment |
| Diversification | Correlation-based | Default correlation, concentration |
| Recovery | Not applicable | Central — LGD |
| Framework | FRTB | Credit risk RWA (`CRE`) |

**The overlap: credit *spread* risk.** A corporate bond's spread widening is **market risk** (CSR). The same bond's issuer defaulting is **default risk**, capitalised in the trading book through the **DRC** and in the banking book through credit risk RWA.

> **`MAR20.4(2)` states the design intent directly:** the DRC *"is calibrated based on the credit risk treatment in the banking book in order to reduce the potential discrepancy in capital requirements for similar risk exposures across the bank."* **That alignment is what removes the incentive to game the book boundary** — the same obligor default costs broadly the same capital wherever it sits.

---

## 4. Market risk versus counterparty credit risk

**The genuine intersection**, because a CCR exposure amount is a **market-risk quantity**.

```
   A 10-year swap, in the money by $8m
        │
        ├──► MARKET RISK    : rates move → the swap's value moves
        │                     Framework: FRTB
        │
        ├──► CCR            : the counterparty defaults owing $8m
        │                     Framework: CRE52 (SA-CCR / IMM)
        │                     But: the EXPOSURE is driven by rate volatility
        │
        └──► CVA RISK       : the value of that default risk changes as the
                              counterparty's spread AND the exposure move
                              Framework: MAR50
```

**Three distinct losses, three frameworks, one trade.**

| | Market risk | CCR |
|---|---|---|
| Question | What if the market moves? | What if they fail? |
| Exposure measure | Sensitivities, VaR, ES | EAD, EPE, PFE |
| Netting | Within the risk factor | Within the **legally enforceable netting set** |
| Collateral | Not a mitigant for price moves | **Central** — VM and IM |
| Horizon | 1–120 days | Life of the trade |
| Reduced by | Hedging the market factors | Netting, collateral, central clearing |

---

## 5. Market risk versus CVA risk

**CVA risk sits at the intersection and is capitalised separately.**

| | Trading book market risk | CVA risk |
|---|---|---|
| What is measured | Sensitivity of **positions** | Sensitivity of the **CVA** |
| Framework | `MAR20`–`MAR33` | **`MAR50`** |
| Approaches | SA (SBM/DRC/RRAO), IMA | **SA-CVA** (approval), **BA-CVA** (reduced/full), CCR proxy |
| Curvature charge | **Yes** | **No** — SA-CVA has delta and vega only |
| Hedge recognition | Framework correlations | **Eligible CVA hedges only**, strictly defined |
| Drivers | Market factors | **Counterparty spread AND market factors** |

> **CVA is genuinely two-dimensional, and this is what makes it hard.** It moves with the counterparty's credit spread *and* with the market factors that determine exposure — with cross-gamma between them. A CVA desk hedges both, and neither hedge is complete. **Wrong-way risk** — exposure rising *because* the counterparty is deteriorating — is the case where the whole structure fails together ([22 §9](22_Counterparty_CVA_and_SIMM.md)).

---

## 6. Market risk versus IRRBB

**The same underlying driver — interest rates — in a different book, under a different framework, with different consequences.**

| | Trading book market risk | IRRBB |
|---|---|---|
| Book | Trading | **Banking** |
| Chapters | `MAR10`–`MAR99` | **`SRP31`**, `SRP98` |
| Pillar | **Pillar 1** (minimum capital) | **Pillar 2** (supervisory review) |
| Accounting | Fair value through P&L | Amortised cost / OCI |
| Metrics | ES, VaR, sensitivities, stress | **ΔEVE**, **ΔNII** |
| Horizon | 1–120 days | Full run-off (EVE); 1–2 years (NII) |
| Shocks | Modelled, or prescribed weights | **Six prescribed scenarios**, recalibrated 2024 |
| Behavioural modelling | Minimal | **Central** — NMDs, prepayment |
| Threshold | n/a | **max ΔEVE > 15% of Tier 1** |
| Capital consequence | Direct RWA | Supervisory add-on if warranted |

**The March 2023 lesson:** a bank can be within trading-book market risk appetite and severely exposed to rates in the banking book. **The two frameworks measure different things and neither substitutes for the other.**

Full treatment: [20A](20A_Trading_Book_Boundary_and_IRRBB.md).

---

## 7. Market risk versus liquidity risk

**Two different things share the word, and they are worth separating explicitly.**

| | **Market** liquidity risk | **Funding** liquidity risk |
|---|---|---|
| Question | Can I **exit** at the marked price? | Can I **finance** myself? |
| Manifests as | Wider bid-offer; longer exit; market impact | Inability to roll funding; margin calls unmet |
| Framework | Internalised in FRTB via **liquidity horizons** (`MAR33.12`) and RRAO | **LCR / NSFR** |
| Metrics | Days-to-liquidate; position vs ADV | LCR, NSFR, survival horizon |
| Owner | Market risk | Treasury / liquidity risk |

> **The 2022 UK LDI episode connected them.** Gilt yields rose → variation margin calls → funds sold gilts to meet them → yields rose further. **A market move became a liquidity event became a forced market move.** Collateral is the transmission channel, which is why margin is a market-risk topic and not merely an operational one ([22 §4.2](22_Counterparty_CVA_and_SIMM.md)).

---

## 8. Market risk versus model risk

**Model risk is orthogonal — it applies *to* market risk, not alongside it.**

| | Market risk | Model risk |
|---|---|---|
| Loss event | A price moved | A **model was wrong or wrongly used** |
| Scope | Trading book positions | **Every model**, including the market risk models |
| Framework | FRTB | SR 26-2 (US, 17 Apr 2026); SS1/23 (UK) |
| Managed by | Market risk function | Model risk management / validation |
| Metric | ES, VaR, sensitivities | Validation findings; model inventory; effective challenge |

**The market risk models are themselves subject to model risk**, which is why [26](26_Model_Risk_and_Validation.md) sits inside this library rather than outside it. SR 26-2's *aggregate* model risk concept applies directly: if the VaR engine, stress engine, CVA model and FRTB engine all draw on the same curve builder, a defect there affects all four simultaneously.

---

## 9. Where exposures can slip between frameworks

The gaps supervisors actually probe:

| Potential gap | Where it sits | How it is closed |
|---|---|---|
| Net short credit/equity in the **banking book** | Economically a trading position in an accrual book | `RBC25.6(2)` — **presumptively trading book** |
| Instruments switched between books | Neither framework, during the switch | `RBC25.15` — **capital benefit disallowed**, surcharge imposed |
| **Internal risk transfers** | Risk moved but not left the bank | Recognition requires an **external hedge** or a dedicated IRT desk |
| Default risk of trading-book issuers | Not credit risk (wrong book); a spread model misses jumps | **DRC** (`MAR22`) |
| Thinly-observed risk factors | Modelled with unearned diversification | **NMRF / SES** (`MAR31`, `MAR33.16`–`33.17`) |
| Exotic risks not captured by sensitivities | Fall through delta/vega/curvature | **RRAO** (`MAR23`) |
| CVA on derivatives | Market-driven but not a position | **`MAR50`**, separate framework |
| Banking-book rate risk | Not Pillar 1 market risk | **IRRBB**, Pillar 2 |
| Market illiquidity | Not represented in daily returns | **Liquidity horizons** (`MAR33.12`) |
| Concentration | Not in historical factor volatility | Liquidity horizons; limits; SIMM concentration component |

> **Read that table as a design commentary on FRTB.** Almost every mechanism in the framework — presumptive lists, switching surcharge, DRC, NMRF, RRAO, liquidity horizons — exists to close a specific gap that was demonstrated during 2007–09.

---

## 10. The classification decision tree

```
   What EVENT causes the loss?
        │
        ├── A market price or rate moved
        │      │
        │      ├── The position is in the TRADING book
        │      │      │
        │      │      ├── It is a position value change  ──► MARKET RISK (FRTB)
        │      │      ├── It is the value of a counterparty
        │      │      │   credit adjustment              ──► CVA RISK (MAR50)
        │      │      └── It is a residual/exotic risk   ──► RRAO (still FRTB)
        │      │
        │      └── The position is in the BANKING book   ──► IRRBB (SRP31, Pillar 2)
        │
        ├── An obligor DEFAULTED
        │      │
        │      ├── It is an issuer of a trading-book instrument ──► DRC (MAR22/33)
        │      ├── It is a derivative counterparty              ──► CCR (CRE52)
        │      └── It is a banking-book borrower                ──► CREDIT RISK (CRE)
        │
        ├── We could not EXIT or FUND
        │      ├── Could not exit at the marked price    ──► market liquidity
        │      │                                             (LH, RRAO, reserves)
        │      └── Could not fund ourselves              ──► FUNDING LIQUIDITY (LCR/NSFR)
        │
        ├── A PROCESS, SYSTEM or PERSON failed           ──► OPERATIONAL RISK
        │
        └── A MODEL was wrong or wrongly used            ──► MODEL RISK
                                                              (SR 26-2 / SS1/23)
```

---

## 11. What belongs in this knowledge base

| In scope — core market risk | Adjacent — covered for the connection | Out of scope |
|---|---|---|
| Sensitivities (all asset classes) | CVA and exposure ([22](22_Counterparty_CVA_and_SIMM.md)) | Banking-book credit risk RWA |
| VaR, ES, stress | SA-CCR ([22 §7](22_Counterparty_CVA_and_SIMM.md)) | PD/LGD/EAD modelling |
| P&L and attribution | ISDA SIMM ([22 §8](22_Counterparty_CVA_and_SIMM.md)) | LCR / NSFR mechanics |
| Backtesting and PLA | IRRBB ([20A](20A_Trading_Book_Boundary_and_IRRBB.md)) | Operational risk |
| FRTB SA and IMA | Model risk ([26](26_Model_Risk_and_Validation.md)) | Accounting standards |
| DRC, NMRF, RRAO | Book boundary ([20A](20A_Trading_Book_Boundary_and_IRRBB.md)) | Tax, legal |
| Limits, controls, reporting | | Settlement operations |

> **The adjacent column is covered deliberately and labelled deliberately.** Derivative portfolios link market risk to counterparty and CVA risk; the trading book is defined by its boundary with the banking book. **Covering the connection is not the same as reclassifying the neighbour as market risk** — [22](22_Counterparty_CVA_and_SIMM.md) opens by saying so explicitly.

---

## 12. Common misclassifications

| Misclassification | Correction |
|---|---|
| "Anything with a price is market risk" | A defaulted loan's recovery has a price and is **credit risk** |
| "CVA is market risk" | Market-driven, **separately capitalised** under `MAR50` |
| "CCR is market risk because the exposure is market-driven" | The **loss event** is a default. CCR, `CRE52` |
| "IRRBB is market risk in the banking book" | Same driver, different framework, **Pillar 2** |
| "Default risk is credit risk" | In the **trading book** it is **DRC**, inside the market risk framework |
| "SIMM is capital" | It is **initial margin** — collateral, not capital |
| "Liquidity risk is one thing" | **Market** liquidity ≠ **funding** liquidity |
| "Model risk is part of operational risk" | A **separate discipline** with its own guidance and, under SS1/23, its own risk-type status |
| "Concentration is captured in VaR" | VaR uses historical volumes; a 10× ADV position is not represented |
| "The RRAO covers our exotics, so SBM doesn't apply" | RRAO is **additive**; `MAR23.8(1)` says it must not change SBM/DRC scope |

---

## 13. Limitations

- **Boundaries are defined by regulation, and regulation differs by jurisdiction.** The Basel positions are stated here; local implementations can and do vary ([29](29_Regulatory_Framework.md)).
- **Some exposures genuinely span frameworks.** A CVA hedge is a trading-book position hedging a CVA-framework exposure; both treatments apply, and the interaction is complex.
- **The decision tree resolves the common cases.** Novel products routinely raise classification questions that require supervisory dialogue rather than a flowchart — which is what new-product approval exists for ([27 §10.1](27_Controls_and_Governance.md)).
- **"Not double-counted" and "not gapped" are both assertions requiring evidence.** Neither is guaranteed by having a classification scheme.

---

## 14. Related Concepts

- [01 §12 — Market risk in the taxonomy of bank risks](01_Market_Risk_Fundamentals.md)
- [20A — Trading Book Boundary and IRRBB](20A_Trading_Book_Boundary_and_IRRBB.md) · [22 — Counterparty, CVA and SIMM](22_Counterparty_CVA_and_SIMM.md)
- [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md) · [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md)
- [29 — Regulatory Framework](29_Regulatory_Framework.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25` boundary; `MAR20.4(2)` DRC calibration rationale; `MAR23.8(1)` |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | `MAR50` CVA; `CRE52` SA-CCR; `SRP31` IRRBB |
| BCBS | *Interest rate risk in the banking book* (d368) | Apr 2016 | https://www.bis.org/bcbs/publ/d368.pdf | IRRBB scope |
| Federal Reserve / OCC / FDIC | SR 26-2 | 17 Apr 2026 | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | Model risk as a distinct discipline |

*Accessed 25 August 2026.*
