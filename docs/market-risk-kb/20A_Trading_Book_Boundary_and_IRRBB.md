# 20A — The Trading Book Boundary and IRRBB

**Level:** 10 · **Prerequisites:** [01](01_Market_Risk_Fundamentals.md), [16](16_FRTB_Overview.md) · **Feeds:** [29](29_Regulatory_Framework.md), [41](41_Market_Risk_vs_Related_Risk_Types.md)

---

## 1. Why the boundary is a regulated object

**The same bond, in two different books, attracts entirely different capital treatment and entirely different accounting.**

| | Trading book | Banking book |
|---|---|---|
| Accounting | **Fair value through P&L**, daily | Amortised cost or OCI |
| A price fall | Hits **today's** P&L and capital | May not be recognised at all |
| Capital framework | **Market risk** (FRTB) | Credit risk RWA; interest-rate risk via **IRRBB** (Pillar 2) |
| Risk metrics | VaR, ES, sensitivities, stress | **EVE** and **NII** sensitivity |

That difference is an arbitrage opportunity. An institution able to reclassify a losing position out of the fair-valued trading book into the accrual banking book could make a loss disappear from reported earnings. Pre-crisis, the boundary was intent-based and porous, and it was gamed.

**`RBC25` of the consolidated Basel Framework is the response.** Its entire structure is a defence against discretionary reclassification.

---

## 2. What the trading book is (`RBC25.1`–`RBC25.4`)

> A trading book consists of all instruments that meet the specifications set out in `RBC25.2` through `RBC25.13`. **All other instruments must be included in the banking book.**

The banking book is the **residual**, not a positively-defined category. Everything that does not qualify for the trading book falls into it by default.

**Instruments** comprise financial instruments, foreign exchange, and commodities (`RBC25.2`). Commodities *"also include non-tangible (ie non-physical) goods such as electric power."*

Two hard conditions:

- **`RBC25.3`** — a bank may only include an instrument in the trading book *"when there is no legal impediment against selling or fully hedging it."*
- **`RBC25.4`** — a bank **must fair value daily** any trading book instrument and **recognise any valuation change in the P&L account.**

> **`RBC25.4` is the substantive test.** An instrument that is not marked daily through P&L is not a trading book instrument, whatever the desk calls it. This closes the route of holding an illiquid position at a stale mark inside the trading book.

---

## 3. The intent test (`RBC25.5`)

An instrument held for **any** of the following must, **when first recognised**, be designated as a trading book instrument:

1. **Short-term resale**
2. **Profiting from short-term price movements**
3. **Locking in arbitrage profits**
4. **Hedging risks that arise from instruments meeting (1), (2) or (3)**

`RBC25.7`: anything not held for these purposes at inception, and not caught by the presumptive list, **must be assigned to the banking book**.

**Designation happens once, at inception.** It is not revisited as circumstances change — see §6.

---

## 4. The presumptive lists

### 4.1 Must be in the trading book (`RBC25.6`)

Regardless of stated intent:

1. **Instruments in the correlation trading portfolio**
2. **Instruments that would give rise to a net short credit or equity position in the banking book**
3. **Instruments resulting from underwriting commitments** — securities underwriting only, and only securities expected to be actually purchased on the settlement date

Footnote 1 defines the net short test precisely: a bank has a net short risk position for equity or credit risk in the banking book *"if the present value of the banking book increases when an equity price decreases or when a credit spread on an issuer or group of issuers of debt increases."*

> **Item 2 exists because a net short position in an accrual book is economically a trading position.** Nobody holds a short to maturity; a short is a view. Basel refuses to let a directional short sit outside the fair-value regime.

### 4.2 Must be in the banking book (`RBC25.8`)

1. **Unlisted equities**
2. **Instruments designated for securitisation warehousing**
3. **Real estate holdings** — direct holdings of real estate, and derivatives on direct holdings
4. **Retail and SME credit**
5. **Equity investments in a fund**, unless the bank meets at least one of:
   - **(a)** it can **look through** the fund to its individual components, with sufficient and frequent information **verified by an independent third party**; or
   - **(b)** it obtains **daily price quotes** for the fund and has access to the information in the fund's mandate

**The fund test drives the treatment elsewhere.** `MAR31.11` follows it directly: funds meeting (a) are treated by look-through, with positions assigned to the desk the fund is assigned to; funds meeting only (b) **must use the standardised approach**.

### 4.3 The presumptive trading-book list (`RBC25.9`) and its carve-outs

`RBC25.9` sets a presumptive list of instruments presumed to be trading book. Three footnoted carve-outs matter in practice:

| Carve-out | Substance |
|---|---|
| **Listed equities** (fn 3) | Subject to supervisory review, **certain listed equities may be excluded** from the market risk framework — examples include equity from **deferred compensation plans**, convertible debt securities, loan products with **"equity kickers"**, equities **taken as a debt previously contracted**, bank-owned life insurance products, and legislated programmes. The excluded set must be **made available to and discussed with the national supervisor**, and **managed by a desk separate from proprietary or short-term buy/sell desks** |
| **Repo-style transactions** (fn 4) | Those entered **for liquidity management** *and* **valued at accrual** for accounting purposes are **not** part of the presumptive list |
| **Embedded derivatives** (fn 5) | A component of a hybrid contract with a non-derivative host — e.g. banking-book-issued liabilities containing embedded derivatives. The embedded derivative **should be bifurcated and separately recognised** |

### 4.4 Deviating from the presumptive list (`RBC25.10`)

A bank that believes it needs to deviate **must submit a request to its supervisor and receive explicit approval**, providing evidence that the instrument is not held for any `RBC25.5` purpose.

> **Where approval is not given, the instrument must be designated as a trading book instrument.** Silence is not consent, and the default runs against the bank. Deviations must be **documented in detail on an ongoing basis**.

---

## 5. Supervisory powers (`RBC25.11`–`RBC25.12`)

The powers run in **both** directions, and are deliberately asymmetric in their exceptions:

| Direction | Power | Exception |
|---|---|---|
| **Trading → Banking** | The supervisor may require evidence that a trading book instrument is held for an `RBC25.5` purpose. If unconvinced, or if it believes the instrument *"customarily would belong in the banking book,"* it may **require reassignment to the banking book** | **Except** instruments listed under `RBC25.6` |
| **Banking → Trading** | The supervisor may require evidence that a banking book instrument is **not** held for any `RBC25.5` purpose. If unconvinced, it may **require reassignment to the trading book** | **Except** instruments listed under `RBC25.8` |

The "customarily would belong" language is unusually broad drafting: it lets a supervisor act on market practice rather than requiring it to disprove the bank's stated intent.

---

## 6. Restrictions on switching — the sharpest provision in the chapter

### 6.1 The prohibition (`RBC25.14`)

> **"Switching instruments for regulatory arbitrage is strictly prohibited. In practice, switching should be rare and will be allowed by supervisors only in extraordinary circumstances."**

Basel's examples of what *does* qualify:

- a **major publicly announced event**, such as a bank restructuring resulting in the **permanent closure of trading desks**, requiring termination of the business activity; or
- a **change in accounting standards** that allows an item to be fair-valued through P&L.

And what does **not**:

> **"Market events, changes in the liquidity of a financial instrument, or a change of trading intent alone are not valid reasons for reassigning an instrument to a different book."**

> **Read that list again.** The three things that would *actually* motivate a bank to switch — the market moved, the instrument became illiquid, the desk changed its mind — are each named and each excluded. There is essentially no commercially-motivated route to a switch.

### 6.2 The capital-benefit rule (`RBC25.15`)

> **"Without exception, a capital benefit as a result of switching will not be allowed in any case or circumstance."**

The mechanism:

1. The bank determines its **total capital requirement across both books** immediately **before** and immediately **after** the switch.
2. If the requirement **falls**, the difference **as measured at the time of the switch** is imposed as a **disclosed Pillar 1 capital surcharge**.
3. The surcharge **runs off as the positions mature or expire**, in a manner agreed with the supervisor.
4. It is **not recalculated on an ongoing basis** — a deliberate simplification.
5. The positions remain subject to the ongoing capital requirements of the book they moved **into**.

> **This is the single most effective provision in the chapter, and its elegance is worth appreciating.** It does not attempt to police intent, which is unobservable. It simply removes the payoff. A bank may switch for genuine business reasons and gain nothing in capital; a bank switching for capital gets a surcharge exactly equal to what it hoped to save. **The arbitrage is arithmetically neutralised rather than legally forbidden.**

### 6.3 Approval (`RBC25.16`)

Any reassignment must be approved by **senior management and the supervisor**. Critically:

> *"Any reallocation of securities between the trading book and banking book, **including outright sales at arm's length**, should be considered a reassignment of securities."*

Selling a position out of one book and buying it into the other does not escape the rule.

---

## 7. Documentation and internal audit (`RBC25.13`)

A bank must have **clearly defined policies, procedures and documented practices** for determining book assignment.

**Internal control functions must conduct an ongoing evaluation** of instruments both in and out of the trading book, to assess whether they are properly designated in the context of the bank's trading activities.

Compliance must be **fully documented and subject to periodic (at least yearly) internal audit**, with results available for supervisory review.

---

## 8. Internal risk transfers

A bank frequently wants to move risk from the banking book to the trading book — for example, hedging banking-book credit risk with the trading desk that has the market access. `RBC25` sets strict conditions, because an unconstrained internal risk transfer (IRT) would reintroduce the boundary arbitrage through the back door.

The framework's principles, at a high level:

| IRT type | Treatment |
|---|---|
| **Banking book credit risk → trading book** | Recognised for banking book capital purposes **only if** the internal transfer is hedged with an **eligible third-party protection provider**, matching the internal hedge |
| **Banking book equity risk → trading book** | Similar external-hedge requirement |
| **Banking book interest rate risk → trading book** | Recognised subject to conditions, including that the transfer is documented, and that the trading book side sits in a **dedicated IRT desk** |
| **Trading book → banking book** | Generally **not recognised** |

> **The organising principle: an internal trade is not a hedge.** Risk moved from one book to another has not left the bank. Recognition therefore generally requires that the risk be passed on to an external party, or that it be booked into a ring-fenced desk whose whole purpose is transparency about the transfer.

---

## 9. IRRBB — the adjacent framework

**IRRBB is not trading-book market risk, and treating them as the same thing is a significant error.** It is the same underlying driver — interest rates — in a different book, measured differently, under a different framework, with different consequences.

### 9.1 The framework

| Field | Value |
|---|---|
| **Framework** | Interest Rate Risk in the Banking Book |
| **Jurisdiction** | Global (Basel standard) |
| **Regulator** | Basel Committee on Banking Supervision |
| **Original publication** | *Interest rate risk in the banking book*, **BCBS d368, April 2016** |
| **Consolidated Framework location** | **`SRP31`** (and `SRP98`) |
| **Pillar** | **Pillar 2** — supervisory review, **not** a Pillar 1 minimum capital charge |
| **Recalibration standard** | *Recalibration of shocks for interest rate risk in the banking book*, **BCBS d578, 16 July 2024** |
| **Recalibration implementation** | **By 1 January 2026** |
| **Institutions affected** | Banks with material banking book interest rate exposure |
| **Trading book applicability** | **None** — IRRBB applies to the banking book only |
| **Latest verification** | 25 August 2026 |

### 9.2 The two metrics

| Metric | Perspective | Horizon | Question |
|---|---|---|---|
| **ΔEVE** — Economic Value of Equity | **Value** | Full run-off of the balance sheet | What is the present-value hit to equity from a rate shock? |
| **ΔNII** — Net Interest Income | **Earnings** | Typically 1–2 years | What is the hit to earnings over the near term? |

> **The two can point in opposite directions, and routinely do.** A bank funding long fixed-rate assets with short-dated deposits is hurt in EVE terms by rising rates (asset values fall further than liabilities). But if its deposits are sticky and slow to reprice, rising rates may *increase* near-term NII. **Managing to one metric alone is how a bank ends up with a problem visible only in the other** — which is a fair description of what surfaced at several institutions in March 2023.

### 9.3 The six prescribed shock scenarios (`SRP31`)

Banks must apply specified interest rate shocks, **per currency for each currency with material positions**:

1. **Parallel up**
2. **Parallel down**
3. **Steepener** (short rates down, long rates up)
4. **Flattener** (short rates up, long rates down)
5. **Short rates up**
6. **Short rates down**

### 9.4 The outlier test

> The outlier/materiality test compares the bank's **maximum ΔEVE under the six prescribed scenarios** with **15% of its Tier 1 capital**.

Two points frequently misstated:

- **The threshold was tightened.** It moved from **20% of total capital** to **15% of Tier 1 capital** — a materially stricter standard on both the numerator base and the capital measure.
- **15% is a floor, not a ceiling.** Supervisors may implement **additional** outlier tests using different capital measures (e.g. CET1) or capturing IRRBB relative to **earnings**, since the threshold is *at least* 15% of Tier 1.

**Being an outlier is not automatically a breach.** It triggers supervisory attention under Pillar 2, which may lead to a capital add-on, a required reduction in exposure, or a conclusion that the exposure is well-managed.

### 9.5 The 2024 shock recalibration (BCBS d578)

The July 2024 standard makes four targeted methodological changes, aimed at calibration problems *"when rates are close to zero"*:

1. **Expansion of the time series** used in calibration — from December 2015 to **December 2023**
2. **Replacement of global shock factors with local shock factors** calculated **directly for each currency**
3. **Move from a 99th percentile to a 99.9th percentile** value in determining the shock factor
4. **Reduction of rounding** from a multiple of **50 basis points** to a multiple of **25 basis points**

> *"The revised standard should be implemented by 1 January 2026."* As at the date of this document that implementation date has passed, so any IRRBB shock magnitudes drawn from pre-2024 material are **out of date**. The Committee has noted the recalibration is **unrelated** to its post-2023 banking-crisis analytical work.

---

## 10. Market risk versus IRRBB — the comparison

| | **Trading book market risk** | **IRRBB** |
|---|---|---|
| Book | Trading | **Banking** |
| Basel chapters | `MAR10`–`MAR99` | **`SRP31`**, `SRP98` |
| Pillar | **Pillar 1** (minimum capital) | **Pillar 2** (supervisory review) |
| Accounting | Fair value through P&L | Amortised cost / OCI |
| Primary metrics | ES, VaR, sensitivities, stress | **ΔEVE**, **ΔNII** |
| Horizon | 1 day to 120 days | Full run-off (EVE); 1–2 years (NII) |
| Shocks | Modelled, or prescribed risk weights | **Six prescribed scenarios**, recalibrated 2024 |
| Behavioural modelling | Minimal | **Central** — deposit stability, prepayment, non-maturity deposits |
| Capital consequence | Direct RWA | Supervisory add-on if warranted |
| Outlier threshold | n/a | **max ΔEVE > 15% of Tier 1** |
| Optionality treated as | Vega, curvature, RRAO | Automatic and **behavioural** options |

### 10.1 The behavioural dimension — where IRRBB is genuinely harder

Trading book instruments have contractual cash flows. Banking book instruments frequently do not:

| Item | The modelling problem |
|---|---|
| **Non-maturity deposits** | Contractually repayable on demand; behaviourally sticky for years. Their assumed repricing profile is the single largest driver of a bank's measured IRRBB, and it is an **assumption**, not a contract term |
| **Prepayable mortgages** | The borrower holds an option; exercise depends on rates, burnout, seasonality and refinancing frictions |
| **Term deposits with early withdrawal** | A depositor option, exercised on rate moves |
| **Committed credit lines** | Drawdown behaviour correlates with the cycle |

> **The non-maturity deposit assumption is where IRRBB is won or lost.** Assume deposits behave like five-year fixed funding and the bank looks well-matched against a long fixed-rate asset book. Assume they reprice immediately and the same balance sheet looks severely exposed. **Both assumptions are defensible in the abstract; only one survives a rate shock plus a deposit run.** March 2023 was a live test of that, and it is why supervisors scrutinise NMD assumptions harder than almost anything else in the framework.

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Daily fair value** | Every trading book instrument marked daily through P&L (`RBC25.4`) |
| 2 | **No legal impediment** | Confirmed for every trading book instrument (`RBC25.3`) |
| 3 | **Designation at inception** | Recorded when first recognised (`RBC25.5`) |
| 4 | **Net short test** | Banking book scanned for net short credit/equity positions (`RBC25.6(2)`) |
| 5 | **Banking-book mandatory list** | Unlisted equities, warehousing, real estate, retail/SME credit correctly assigned (`RBC25.8`) |
| 6 | **Fund test** | Look-through or daily quotes evidenced; SA applied where only (b) is met |
| 7 | **Deviations approved** | Explicit supervisory approval obtained and documented (`RBC25.10`) |
| 8 | **Excluded listed equities** | Set discussed with the supervisor; managed on a **separate desk** |
| 9 | **Repo carve-out** | Liquidity-management, accrual-valued repo correctly excluded from the presumptive list |
| 10 | **Embedded derivatives** | Bifurcated and separately recognised |
| 11 | **Switching log** | Every reassignment recorded, with senior management **and** supervisory approval |
| 12 | **Capital surcharge** | Before/after capital computed at the time of any switch; surcharge imposed if lower (`RBC25.15`) |
| 13 | **Arm's-length sales** | Treated as reassignments (`RBC25.16`) |
| 14 | **Annual internal audit** | Book designation audited at least yearly (`RBC25.13`) |
| 15 | **IRT recognition** | External hedge or dedicated IRT desk evidenced |
| 16 | **IRRBB currencies** | All material currencies shocked separately |
| 17 | **IRRBB shocks current** | **Post-d578 recalibrated shocks in use** (implementation date 1 Jan 2026) |
| 18 | **Outlier test** | max ΔEVE vs **15% of Tier 1**, plus any local additional test |
| 19 | **NMD assumptions** | Documented, validated, back-tested against observed depositor behaviour |
| 20 | **EVE and NII both reported** | Neither managed in isolation |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Treating book assignment as revisable with market conditions | Contradicts `RBC25.14`; the three commercial motivations are all excluded |
| Holding an unmarked position in the trading book | Contradicts `RBC25.4` |
| Missing net short credit/equity positions in the banking book | Instruments in the wrong book (`RBC25.6(2)`) |
| Assuming supervisory silence permits a deviation | Default is trading book designation (`RBC25.10(2)`) |
| Excluded listed equities managed on a trading desk | Contradicts the fn 3 separate-desk condition |
| Treating an outright arm's-length sale as escaping the switching rules | Contradicts `RBC25.16` |
| Not computing before/after capital on a switch | The surcharge cannot be determined |
| Recognising an internal risk transfer with no external leg | Risk has not left the bank |
| Applying market risk metrics to the banking book | Wrong framework; EVE/NII are the IRRBB measures |
| Using pre-2024 IRRBB shock magnitudes | Superseded by d578, implementation 1 Jan 2026 |
| Testing ΔEVE against 20% of total capital | Superseded — the test is **15% of Tier 1** |
| Managing NII while ignoring EVE (or vice versa) | The exposure surfaces in the metric not being watched |
| Undocumented non-maturity deposit assumptions | The largest single IRRBB driver, unevidenced |

---

## 13. Limitations

- **`RBC25` constrains discretion; it does not eliminate judgement.** "Held for short-term resale" still requires an assessment at inception, and reasonable people differ.
- **The switching surcharge is not recalculated**, so it can become stale relative to the positions it relates to — a deliberate simplicity/accuracy trade-off Basel acknowledges.
- **Internal risk transfer rules are complex and jurisdiction-sensitive**; the treatment here is the Basel principle, and local implementation should be checked.
- **IRRBB is Pillar 2**, so outcomes vary by supervisor in a way Pillar 1 outcomes do not. Two banks with identical balance sheets in different jurisdictions may face different consequences.
- **Behavioural models are the dominant source of IRRBB model risk**, and they are calibrated on a history that may not contain the regime being modelled.

---

## 14. Related Concepts

- [01 — Market Risk Fundamentals](01_Market_Risk_Fundamentals.md) · [16 — FRTB Overview](16_FRTB_Overview.md)
- [41 — Market Risk vs Related Risk Types](41_Market_Risk_vs_Related_Risk_Types.md) · [29 — Regulatory Framework](29_Regulatory_Framework.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25` in full; `MAR31.11` fund treatment |
| BCBS | *Interest rate risk in the banking book* (d368) | Apr 2016 | https://www.bis.org/bcbs/publ/d368.pdf | The IRRBB standard; six shock scenarios; outlier test |
| BCBS | *Recalibration of shocks for interest rate risk in the banking book* (d578) | **16 Jul 2024** | https://www.bis.org/bcbs/publ/d578.pdf | Four recalibration changes; implementation by 1 Jan 2026 |
| BIS FSI | *IRRBB: Pillar 2 standardised framework — Executive Summary* | ongoing | https://www.bis.org/fsi/fsisummaries/irrbb.htm | 15% of Tier 1 outlier threshold; supervisory additional tests |
| BCBS | Consolidated Basel Framework — `SRP31` | ongoing | https://www.bis.org/basel_framework/chapter/SRP/31.htm | Current IRRBB text |

*Accessed 25 August 2026.*
