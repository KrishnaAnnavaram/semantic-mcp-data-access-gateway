# 35 — Beginner-to-Expert Learning Path

**Level:** Meta · **Purpose:** the order in which to read this library, and what "understood" means at each stage

> **The prerequisite structure is real, not advisory.** You cannot understand VaR without understanding sensitivities; you cannot understand sensitivities without understanding pricing; you cannot understand pricing without discounting. Skipping a level produces someone who can operate a system and cannot tell when it is wrong.

---

## The map

```
  L1  Banking & market risk fundamentals        01 · 01A
       │
  L2  Financial instruments                     02
       │
  L3  Pricing                                   03 · 23
       │
  L4  Risk sensitivities                        04 · 05 · 06 · 07 · 08
       │
  L5  Derivatives & Greeks                      09
       │
  L6  Portfolio mathematics                     10
       │
  L7  Value at Risk                             11
       │
  L8  Expected Shortfall                        12
       │
  L9  Stress testing                            13
       │
  L10 P&L and backtesting                       14 · 15
       │
  L11 FRTB — overview & standardised            16 · 17 · 19
       │
  L12 FRTB — internal models & NMRF             18 · 20 · 20A
       │
  L13 Limits, aggregation & controls            21 · 42 · 27
       │
  L14 Systems & data                            24 · 25 · 40
       │
  L15 Model risk & validation                   26
       │
  L16 Regulatory landscape & adjacent risks     29 · 22 · 41
       │
  L17 Practice                                  43 · 44 · 28 · 30 · 38
```

---

## Level 1 — Banking and market risk fundamentals

**Read:** [01](01_Market_Risk_Fundamentals.md), [01A](01A_Master_Market_Risk_Taxonomy.md)
**Prerequisites:** none

| You understand this level when you can... |
|---|
| Explain why a bank loses money when rates rise, without using the word "duration" |
| Distinguish market risk from credit, counterparty, operational and model risk |
| Explain what a **risk factor** is and why banks model factors rather than instruments |
| State the difference between the trading book and the banking book, and why it is policed |
| Explain why "hedged" is not the same as "flat" |
| Name the **seven** FRTB SBM risk classes and the **five** IMA broad classes — and say why they differ |

**The concept most often skipped:** that market risk is a risk to *reported earnings and regulatory capital on a daily cycle*, because the trading book is fair valued daily. Everything else follows from that.

---

## Level 2 — Financial instruments

**Read:** [02](02_Financial_Instruments.md)
**Prerequisites:** L1

| You understand this level when you can... |
|---|
| Say what cash flows each major instrument produces |
| Explain why an **FRN** has near-zero DV01 and full CS01 |
| Explain why an FX forward is *three* risks, not one |
| Explain why a bond future's DV01 is unstable near a **CTD** switch |
| Decompose a convertible bond into its components — and say why the decomposition is inadequate |
| Read the Instrument × Risk Factor matrix and predict what a new instrument loads onto |

**The trap at this level:** classifying by product name rather than by risk factor. A cross-currency swap is called an FX product and is mostly an interest-rate product.

---

## Level 3 — Pricing

**Read:** [03](03_Pricing_Fundamentals.md), then [23](23_Market_Data_and_Curves.md)
**Prerequisites:** L2

| You understand this level when you can... |
|---|
| Convert between compounding conventions and explain why a rate without one is not a number |
| Bootstrap a discount factor from a par swap rate, by hand |
| Explain why **forward rates** are the diagnostic for a curve build, not zero rates |
| Explain why the **CSA determines the discount curve** |
| Price a European option and verify it with put-call parity |
| Explain when **Bachelier** must be used instead of Black-Scholes |
| Say what happens when a valuation fails — and why "zero" is the wrong answer |

**The habit to build here:** always ask what convention a number is quoted in. Day count, compounding, quoting basis, vol convention. Most reconciliation breaks live in these four fields.

---

## Level 4 — Risk sensitivities

**Read:** [04](04_Interest_Rate_Risk.md) thoroughly, then [05](05_Credit_Spread_Risk.md), [06](06_FX_Risk.md), [07](07_Equity_Risk.md), [08](08_Commodity_Risk.md)
**Prerequisites:** L3

| You understand this level when you can... |
|---|
| Compute DV01 analytically **and** by central bump, and explain why they should agree |
| Explain why a single DV01 can conceal an arbitrarily large curve position |
| State and verify the completeness identity `Σ KRD01 = parallel DV01` |
| Explain why key-rate ladders are not comparable across institutions but totals are |
| Explain why CS01 and DV01 must be separated, using the FRN as proof |
| Explain why CS01 and JTD are largest in *opposite* places |
| Compute a net open position and say what it omits |
| Explain why net equity exposure is not risk |

**This is the level that takes longest and matters most.** A practitioner fluent at Level 4 is useful immediately; one who has memorised VaR without it is not.

---

## Level 5 — Derivatives and Greeks

**Read:** [09](09_Options_and_Greeks.md)
**Prerequisites:** L4

| You understand this level when you can... |
|---|
| Write the Taylor expansion and identify each Greek in it |
| Explain why a delta-hedged option book is a bet on realised vs implied volatility |
| Explain the gamma-theta relationship from the Black-Scholes PDE |
| Explain why total vega is a misleading number |
| Show numerically where the delta-gamma approximation breaks down |
| Explain what sticky strike vs sticky delta changes about a reported delta |
| Explain why barriers and digitals require full revaluation |

---

## Level 6 — Portfolio mathematics

**Read:** [10](10_Portfolio_Risk_Mathematics.md)
**Prerequisites:** L4

| You understand this level when you can... |
|---|
| Explain why arithmetic returns aggregate across assets and log returns across time |
| Compute portfolio variance from weights, volatilities and correlations |
| Explain why a covariance matrix must be **positive semi-definite**, in terms of variance |
| Explain what a failed Cholesky decomposition is telling you |
| Distinguish **marginal**, **component** and **incremental** contribution — and say which sums to the total |
| Explain why capital allocation and risk allocation are different things |
| Explain what happens to diversification benefit in a crisis, and why |

---

## Level 7 — Value at Risk

**Read:** [11](11_VaR.md)
**Prerequisites:** L6

| You understand this level when you can... |
|---|
| State precisely what VaR does and does **not** say |
| Explain why absolute shocks are used for rates and relative shocks for prices |
| Explain how a quantile convention can move reported VaR by 13% |
| Explain why 99% VaR on 250 days rests on two or three observations |
| Explain why √T scaling tends to **understate** risk |
| Explain what a **ghost feature** is |
| Explain how a VaR-based limit rewards selling deep out-of-the-money options |

---

## Level 8 — Expected Shortfall

**Read:** [12](12_Expected_Shortfall.md)
**Prerequisites:** L7

| You understand this level when you can... |
|---|
| Construct the two-bond example showing VaR is not sub-additive |
| Explain why Basel chose **97.5%** ES rather than 99% |
| Show that ES(97.5%) ≈ VaR(99%) under normality, and explain what a large gap means |
| Handle the fractional tail observation correctly |
| Explain the FRTB liquidity-horizon scaling formula and the **nesting** of `Q(pᵢ,j)` |
| Explain why ES is validated *indirectly*, through VaR backtesting and PLA |

---

## Level 9 — Stress testing

**Read:** [13](13_Stress_Testing.md)
**Prerequisites:** L8

| You understand this level when you can... |
|---|
| Explain why stress shocks must be **extracted from data**, never copied from a document |
| Design a *coherent* hypothetical scenario and say why incoherent ones are ignored |
| Explain why a 2008-style scenario flatters a book that a 2022-style scenario exposes |
| Read a spot × vol grid and identify a short-gamma, short-vega book |
| Explain reverse stress testing and interpret a Mahalanobis distance |
| Name three episodes that broke a *modelling assumption* rather than merely being severe |

---

## Level 10 — P&L and backtesting

**Read:** [14](14_PnL_and_PnL_Explain.md), then [15](15_Backtesting.md)
**Prerequisites:** L9

| You understand this level when you can... |
|---|
| Define APL, HPL and RTPL precisely, and say what is excluded from each |
| Explain why RTPL must **not** contain factors the risk model lacks |
| Explain why the residual ratio uses a **gross** denominator |
| Explain why a small persistent residual is worse than a larger random one |
| Explain why the exception count is the **greater** of APL and HPL exceptions |
| Compute Spearman and KS metrics and apply the zone logic correctly |
| Explain why a model can pass backtesting and fail PLA |

---

## Level 11 — FRTB: overview and standardised approach

**Read:** [16](16_FRTB_Overview.md), [17](17_FRTB_Standardised_Approach.md), [19](19_Default_Risk_and_DRC.md)
**Prerequisites:** L10

| You understand this level when you can... |
|---|
| Explain each pre-crisis failure FRTB was designed to fix |
| Explain why the SA had to be made good before models could be withdrawn |
| Compute an SBM bucket charge under all three correlation scenarios |
| Explain why **low** correlation is the binding scenario for a hedged book |
| Explain the curvature `RW·s` subtraction and the ψ function |
| Compute gross JTD, net JTD, HBR and a DRC bucket charge |
| Explain why the DRC is calibrated to the banking book |
| Explain what the RRAO covers and what `MAR23.6` explicitly excludes |

---

## Level 12 — FRTB: internal models and modellability

**Read:** [18](18_FRTB_Internal_Models_Approach.md), [20](20_NMRF_and_Modellability.md), [20A](20A_Trading_Book_Boundary_and_IRRBB.md)
**Prerequisites:** L11

| You understand this level when you can... |
|---|
| Name the four gates a desk must pass and the consequence of failing each |
| Explain why the IMCC weight is **0.5** and what that expresses |
| Explain why the SES ρ is **0.6** and how the formula's three terms differ |
| State the RFET criteria, including the 90-day gap condition |
| Explain what counts as a **real price** and what explicitly does not |
| Explain why proxying an NMRF into a modellable factor plus a basis does not work |
| Explain the trading-book switching rule and why the capital-benefit provision is elegant |
| Distinguish IRRBB from trading-book market risk on five dimensions |

---

## Level 13 — Limits, aggregation and controls

**Read:** [21](21_Market_Risk_Limits.md), [42](42_Risk_Aggregation.md), [27](27_Controls_and_Governance.md)
**Prerequisites:** L12

| You understand this level when you can... |
|---|
| Explain why sub-limits deliberately exceed the parent limit |
| Explain why a firm limit can breach with no desk in breach |
| Distinguish **active** from **passive** breaches and say why conflating them destroys the statistic |
| Cross-check a DV01 limit against a stress limit for coherence |
| Explain the difference between a **control** and **monitoring** |
| Explain why a stale price makes the risk number look *better* |
| Name the gates in the daily process that must halt rather than annotate |

---

## Level 14 — Systems and data

**Read:** [24](24_Risk_Data_Model.md), [25](25_Risk_System_Architecture.md), [40](40_Implementation_Pseudocode_and_Contracts.md)
**Prerequisites:** L13

| You understand this level when you can... |
|---|
| Explain why bi-temporal storage is required, with a concrete scenario |
| Explain why `computation_method`, `bump_size` and `sign_convention` are mandatory fields |
| Explain why the three P&L types must be separate entities |
| Explain why `capital_approach` must be derived and never editable |
| Size the compute problem and identify that **sensitivities**, not pricing, dominate |
| Explain why front office and risk must share one pricing library |

---

## Level 15 — Model risk and validation

**Read:** [26](26_Model_Risk_and_Validation.md)
**Prerequisites:** L14

| You understand this level when you can... |
|---|
| Cite the **current** US guidance (SR 26-2, April 2026) and know SR 11-7 is superseded |
| Apply SR 26-2's definition of "model" and say what it excludes |
| State the AI scope boundary correctly in both directions |
| Explain the three requirements of **effective challenge** and which one usually fails |
| Explain **aggregate** model risk from shared dependencies |
| Design a validation agenda for a VaR model that would catch a stale calibration window |
| Explain why a "no issues" validation report is suspicious |

---

## Level 16 — Regulatory landscape and adjacent risks

**Read:** [29](29_Regulatory_Framework.md), [22](22_Counterparty_CVA_and_SIMM.md), [41](41_Market_Risk_vs_Related_Risk_Types.md)
**Prerequisites:** L15

| You understand this level when you can... |
|---|
| State, without hedging, that FRTB is a **standard** and not law anywhere |
| Give current status and dates for Basel, EU, UK and US — and flag the US as **proposed** |
| Explain why the EU is applying a multiplier and what period it covers |
| Explain why the UK split its SA and IMA dates |
| List what FRTB superseded and the two things it **retained** |
| Explain why SIMM is not a capital framework |
| Resolve a classification dispute by asking **what event causes the loss** |

---

## Level 17 — Practice

**Read:** [43](43_Daily_Workflow.md), [44](44_Roles_and_Responsibilities.md), [28](28_Reporting_and_Dashboards.md), [30](30_Worked_Examples.md), [38](38_Question_to_Calculation_Catalog.md)
**Prerequisites:** L16

| You understand this level when you can... |
|---|
| Walk the daily cycle from market close to published report, naming each gate |
| Say who calculates, consumes, verifies and approves each metric |
| Write a daily report that leads with exceptions and attributes every mover |
| Reproduce the Treasury portfolio worked example end to end |
| Translate an arbitrary business question into the right calculation |
| Answer the ten questions in [01 §13](01_Market_Risk_Fundamentals.md) for a real book |

---

## Reading paths by role

Not everyone needs all seventeen levels. Four practical routes:

### Market risk analyst (new joiner)

`01 → 01A → 02 → 03 → 04 → 05 → 10 → 11 → 12 → 13 → 21 → 43`

Then depth in whichever asset class the desk trades. **Level 4 is where to spend the most time.**

### Quantitative developer

`01 → 02 → 03 → 04 → 09 → 10 → 11 → 12 → 23 → 24 → 25 → 40 → 32`

**Formula handbook and data contracts are the working documents.** Read [24 §10](24_Risk_Data_Model.md) before designing anything.

### Regulatory capital specialist

`01 → 01A → 16 → 17 → 19 → 18 → 20 → 20A → 29 → 15 → 22`

**Read [29](29_Regulatory_Framework.md) first and last** — first for orientation, last to re-verify status before relying on anything.

### Model validator

`01 → 03 → 04 → 09 → 10 → 11 → 12 → 14 → 15 → 26 → 20 → 25`

**[26](26_Model_Risk_and_Validation.md) is the governing document**, but validation of a market risk model requires Level 4–8 fluency to be anything other than a documentation review.

---

## What separates competent from expert

Levels 1–14 make someone competent. Three things make someone expert, and none of them is another formula.

**1. Knowing what the number does not say.**
VaR is not a maximum. A stress result has no probability. A backtest with zero exceptions is a finding. Net exposure is not risk. A clean P&L residual proves the model matches the front office, not that either is right.

**2. Knowing where the silence is.**
The dangerous failures in this discipline are **self-concealing**: a stale price lowers measured volatility; a failed valuation defaulted to zero removes both value and risk; an unmapped stress factor produces a complete-looking result; a proxied issuer shows no idiosyncratic risk. **Expertise is largely the habit of asking what is missing rather than checking what is present** — which is why [01 §13](01_Market_Risk_Fundamentals.md) ends with "what do we not know?"

**3. Knowing which convention is in force.**
DV01 or PV01, and what was bumped. Normal or lognormal vol. Round up, round down or interpolate. Sticky strike or sticky delta. Which SR letter is current. **A number without its convention is not a number**, and a great deal of senior analytical work consists of establishing conventions before comparing anything.

---

## Related Concepts

- [00 — Master Index](00_Master_Index.md) — the full document map
- [31](31_Master_Calculation_Catalog.md) · [32](32_Master_Formula_Handbook.md) · [33](33_Master_Risk_Factor_Catalog.md) · [34](34_Glossary.md) — the four reference documents
- [38 — Question-to-Calculation Catalog](38_Question_to_Calculation_Catalog.md) — the practical index

---

*Accessed 25 August 2026.*
