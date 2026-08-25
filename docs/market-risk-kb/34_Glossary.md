# 34 — Market Risk Glossary

**Level:** Reference · **Format:** Term · Full name · Plain English · Technical definition · Example

> **Terms in bold within definitions are themselves defined in this glossary.** Where a term is used inconsistently across the industry — **DV01/PV01/BPV** and **clean P&L** being the clearest cases — the ambiguity is stated rather than resolved by fiat.

---

## A

**ABS** — *Asset-Backed Security*. A bond paid from a pool of loans. *Technical:* securitised exposure whose cash flows derive from a specified asset pool, usually tranched by seniority. *Example:* an auto-loan ABS senior tranche.

**Accrued interest** — Coupon earned but not yet paid. *Technical:* `Coupon × (days since last coupon / days in period)`, on the instrument's **day-count convention**. *Example:* a 4% semiannual bond 60 days into a 182-day period accrues ≈ 0.659% of face.

**Actual P&L (APL)** — The real, booked daily profit and loss. *Technical:* the reported daily P&L, with **fees and commissions excluded** and certain valuation adjustments excluded per `MAR32.26`. *Used for:* **backtesting**.

**AI** — See **Accrued interest**.

**Annuity** — The sum of discounted accrual factors on a swap's fixed leg. *Technical:* `Σ τⱼ·DF(tⱼ)`. *Example:* a 10-year USD swap annuity of 8.10 implies a **DV01** of ≈ $81,000 per $100m notional.

**AAD** — *Adjoint Algorithmic Differentiation*. A technique computing all sensitivities at roughly a constant multiple of one pricing, independent of the number of factors. Highest-leverage optimisation for large derivative books.

**APL** — See **Actual P&L**.

**Arbitrage-free surface** — A **volatility surface** admitting no riskless profit. *Technical:* satisfies calendar (total variance non-decreasing in τ) and butterfly (non-negative implied density) conditions.

**Asset swap spread (ASW)** — A bond's spread expressed in swap terms. *Technical:* the spread over the floating index in an asset swap package.

---

## B

**Backtesting** — Checking whether a model's predictions matched reality. *Technical:* comparing one-day **VaR** against **APL** and **HPL**; an exception occurs when either loss exceeds VaR, counted separately, **the overall count being the greater** (`MAR32.5(1)`).

**Backwardation** — A futures curve sloping **downward**. *Technical:* `F(T) < S`. *Consequence:* a long position earns **positive roll yield**.

**BA-CVA** — *Basic Approach to CVA*. The simpler of the Basel CVA approaches, in **reduced** (no active hedging) and **full** (active hedging) variants. **All banks must compute the reduced version.**

**Basis** — The difference between two things that should track. *Example:* the **CDS-bond basis**; **cross-currency basis**; WTI-Brent location basis.

**Basis point (bp)** — One hundredth of a percent, 0.01%.

**Basis risk** — Loss because two supposedly offsetting instruments moved apart. *Why it matters:* basis positions are large in notional relative to apparent risk and structurally over-represented in trading loss events.

**Bachelier model** — Option pricing assuming **normally** distributed prices, so the underlying may go negative. *Required* for negative-rate and negative-price markets.

**Behavioural risk** — Risk that exercise or prepayment decisions are driven by non-financial factors. *Technical:* an **RRAO** category; a callable bond bears it only if the **call right lies with a retail client** (`MAR23.5(3)`).

**Beta (β)** — How much a stock moves when the market moves. *Technical:* `Cov(rᵢ, r_m)/Var(r_m)`.

**BPV** — *Basis Point Value*. Generic term for 1bp sensitivity; usually synonymous with **DV01**. **Always ask what was bumped.**

**Bootstrapping** — Deriving **discount factors** sequentially from quoted par instruments.

**Butterfly (curve)** — A trade long the belly and short both wings, **DV01-neutral**; profits when the belly richens.

**Butterfly (FX)** — A volatility quote measuring smile curvature: `½[σ(25Δc) + σ(25Δp)] − σ_ATM`.

---

## C

**Carry** — What a position earns for being held if nothing moves. *Technical:* coupon accrual minus financing cost. *Note:* the two legs typically use **different day-count bases**.

**Cheapest-to-deliver (CTD)** — The bond a futures short would most economically deliver. *Note:* `MAR23.6(1)` states CTD optionality does **not** by itself bring an instrument into the **RRAO**.

**Cholesky decomposition** — Factorising `Σ = LLᵀ` to simulate correlated variables. **Exists iff Σ is positive definite**; failure means the covariance matrix is invalid.

**Clean price** — Quoted price excluding **accrued interest**. *Note:* every risk calculation uses **dirty** price.

**Clean P&L** — Loosely, P&L excluding fees, commissions and reserves. **Institution-specific — always ask for the local definition.** Often a synonym for **HPL**.

**Coherent risk measure** — A measure satisfying monotonicity, translation invariance, positive homogeneity and **sub-additivity**. **ES is coherent; VaR is not.**

**Component contribution to risk (CCR)** — Each position's share of *current* total risk. *Technical:* `wᵢ·MCRᵢ`, and `Σ CCRᵢ = σ_p` exactly (Euler's theorem). **The correct basis for limit allocation.**

**Contango** — A futures curve sloping **upward**; a long position suffers **negative roll yield**.

**Convenience yield** — The benefit of holding the physical commodity rather than a future. *Technical:* the residual `y` in `F = S·e^((r+u−y)τ)` — **unobservable, backed out**.

**Convexity** — The curvature of price against yield. *Technical:* `(1/P)·∂²P/∂y²`. *Consequence:* you lose less than duration predicts on a sell-off and gain more on a rally.

**Correlation trading portfolio (CTP)** — A defined set of securitisation positions and their hedges meeting `MAR20.5` conditions, receiving its own **CSR** class and **DRC** treatment.

**Counterparty credit risk (CCR)** — Loss because a **derivative counterparty** defaults while owing mark-to-market. **Not market risk**, though the exposure is market-driven.

**Covered bond** — A bond secured on a ring-fenced pool. *FRTB:* CSR bucket 8; **LGD 25%** for DRC; risk weight may be **1.5%** if rated AA− or higher.

**CRR3** — Regulation (EU) 2024/1623, the EU implementation of final Basel III. In force 9 July 2024; general application 1 January 2025; **FRTB own-funds requirements deferred to 1 January 2027**.

**CS01** — Money lost per **1bp** widening of credit spread. *Also:* SDV01, CR01, spread delta. *Note:* **independent of** **JTD** — they are largest in opposite places.

**CSA** — *Credit Support Annex*. The collateral agreement. **Determines the discount curve** for a collateralised derivative.

**CTD** — See **Cheapest-to-deliver**.

**Curvature (FRTB)** — The SBM charge for **non-linearity**, computed as the loss beyond delta under prescribed up/down shocks. *Not* an analytical second derivative.

**CVA** — *Credit Valuation Adjustment*. The market value of counterparty default risk on derivatives. *Technical:* `LGD·Σ EE·ΔPD·DF`. **Capitalised separately under `MAR50`.**

**CVR** — The curvature risk charge per risk factor under `MAR21.5(2)`.

---

## D

**Day count** — The convention converting dates to year fractions. ACT/360, ACT/365F, 30/360, ACT/ACT.

**Default risk charge (DRC)** — Capital for **jump-to-default** risk in the trading book. *Technical:* `MAR22` (SA) and `MAR33` (IMA); calibrated to the **banking book credit risk treatment** to remove boundary arbitrage.

**Delta (Δ)** — Value change per unit move in the underlying. *Technical:* `e^(−qτ)N(d₁)` for a call.

**Delta-normal VaR** — Parametric VaR using only first-order sensitivities. **Can be badly wrong for optioned books.**

**Dirty price** — Price actually paid, including **accrued interest**. **The basis for all sensitivity calculations.**

**Discount factor (DF)** — Present value of $1 at time *t*. *Technical:* `e^(−z(t)·t)`. **Can exceed 1 for negative rates.**

**Diversification ratio** — `σ_p / Σ wᵢσᵢ`. Below 1 when correlations are below 1.

**DV01** — *Dollar Value of an 01*. **Money made or lost per 1bp move in rates.** *Technical:* `[P(y−1bp) − P(y+1bp)]/2` by central bump. **The most-used number on a rates floor.** *Note:* sign conventions vary — establish the house convention.

**DVA** — *Debit Valuation Adjustment*. The mirror of **CVA** on one's own default. Controversial; **excluded from APL and HPL** and deducted from CET1.

---

## E

**Effective duration** — Duration measured by revaluation with the option model re-run. **Mandatory** for callables and **MBS**.

**Effective challenge** — Critical analysis by objective experts with **expertise, independence, and the organisational standing to effect change** (SR 26-2). *Note:* the third element is the one that most often fails.

**EE** — *Expected Exposure*. Mean positive exposure at a future date.

**EEPE** — *Effective Expected Positive Exposure*. EPE with a non-decreasing floor, handling rolling short-dated trades.

**EPE** — *Expected Positive Exposure*. Time-weighted average of **EE**.

**ERBA** — *Expanded Risk-Based Approach*. The single framework in the March 2026 U.S. proposal, replacing the advanced approaches. **Proposed, not final.**

**ES** — See **Expected Shortfall**.

**EWMA** — *Exponentially Weighted Moving Average*. Volatility estimator `σ²ₜ = λσ²ₜ₋₁ + (1−λ)r²ₜ₋₁`. Eliminates **ghost features**; effective window ≈ `1/(1−λ)`.

**EVE** — *Economic Value of Equity*. The **IRRBB** value metric, over full balance-sheet run-off.

**Expected Shortfall (ES)** — **The average loss on days when the loss exceeds VaR.** *Technical:* `E[L | L ≥ VaR_α]`. **Coherent**, unlike VaR. *FRTB:* **97.5th percentile, one-tailed** (`MAR33.3`).

---

## F

**Fat tail** — More probability in the extremes than a normal distribution implies. *Diagnostic:* `ES(97.5%)/VaR(99%)` materially above 1.005.

**Flattener** — A **DV01-neutral** trade profiting when the curve flattens.

**FRN** — *Floating Rate Note*. A bond whose coupon resets. *Signature:* **near-zero DV01** (only to the next reset) and **full CS01**.

**FRTB** — *Fundamental Review of the Trading Book*. The Basel revised market risk framework: BCBS d457 (Jan 2019, rev. Feb 2019), consolidated as `RBC25` and `MAR10`–`MAR99`. **A standard, not law anywhere.**

**FVA** — *Funding Valuation Adjustment*. The funding cost of uncollateralised derivative exposure.

---

## G

**Gamma (Γ)** — The rate of change of **delta**. *Technical:* `e^(−qτ)φ(d₁)/(Sσ√τ)`; **identical for call and put**. *Short gamma means buying high and selling low, mechanically.*

**Gap risk** — In **RRAO** terms, *"risk of a significant change in vega parameters in options due to small movements in the underlying, which results in hedge slippage"* (`MAR23.5(1)`) — covering barriers, Asians and digitals. **In ordinary desk usage it means an overnight price jump. State which you mean.**

**Ghost feature** — A discontinuous jump in **VaR** caused by a large observation leaving the lookback window. Corresponds to nothing in the market.

**GIRR** — *General Interest Rate Risk*. SBM risk class 1: risk-free curves, inflation and cross-currency basis.

**GMS** — *Global Market Shock*. The market-risk component of the Federal Reserve's supervisory stress test for banks with significant trading activity, applied to positions on a specified **as-of date**.

**G-spread** — A bond's yield minus the interpolated government yield at matched maturity.

---

## H

**HBR** — *Hedge Benefit Ratio*. Partial recognition of short positions within a DRC bucket. *Technical:* `Σ net JTD_long / (Σ net JTD_long + |Σ net JTD_short|)`, computed on **unweighted** net JTD.

**Historical simulation** — VaR/ES computed by applying observed historical factor changes to today's portfolio. **Makes no distributional assumption. The industry default.**

**HPL** — *Hypothetical P&L*. **Revaluation of the previous day's positions using today's market data** (`MAR32.25`). No intraday trading, no new or modified deals. *Used for:* **backtesting and the PLA test.**

---

## I

**IMA** — *Internal Models Approach*. The FRTB approach permitting a bank's own model, granted **per trading desk** and re-assessed quarterly.

**IMCC** — *Internally Modelled Capital Charge*. Capital for **modellable** risk factors: `ρ·IMCC(C) + (1−ρ)·Σ IMCC(Cᵢ)` with **ρ = 0.5**.

**Implied volatility** — The volatility that makes a model reproduce the market price. **A quoting device**, not a belief about the model.

**Incremental VaR** — The change in VaR from removing a position entirely.

**Index skew** — The difference between an index spread and the spread implied by its constituents.

**IPV** — *Independent Price Verification*. Second-line verification of front-office marks against independent evidence.

**IRRBB** — *Interest Rate Risk in the Banking Book*. **Pillar 2**, `SRP31`. Metrics: **ΔEVE** and **ΔNII**. Outlier test: **max ΔEVE > 15% of Tier 1 capital**.

**ISDA SIMM** — *Standard Initial Margin Model*. An **industry methodology for initial margin, not a capital framework.** Current version **2.8+2512**, effective **11 July 2026**; recalibrated **semiannually**.

---

## J

**JTD** — *Jump-to-Default*. **The loss if an obligor defaults now.** *Technical:* `max/min(LGD·notional + P&L, 0)` (`MAR22.11`). **Cannot be derived by bumping a spread curve.**

---

## K

**Key-rate DV01 (KRD01)** — DV01 decomposed across curve nodes using tent shocks. **Completeness identity:** `Σ KRD01 = parallel DV01`. *Depends on the interpolation scheme* — reconcile totals across institutions, never buckets.

**KS test** — *Kolmogorov-Smirnov*. The **PLA** distributional metric: the largest absolute difference between the empirical CDFs of **RTPL** and **HPL**, each stepping by **0.004** on a 250-day sample.

**Kupiec test** — A likelihood-ratio test of whether the **number** of VaR exceptions is consistent with the confidence level.

---

## L

**LGD** — *Loss Given Default*. `1 − recovery`. *FRTB DRC:* **100%** equity and non-senior debt; **75%** senior debt; **25%** covered bonds.

**Liquidity horizon (LH)** — The period assumed necessary to exit a position. *FRTB:* **10, 20, 40, 60 or 120 days** by risk-factor category (`MAR33.12`). **A floor, increasable with documentation and approval; capped at instrument maturity.**

---

## M

**Macaulay duration** — PV-weighted average time to cash flow, in **years**.

**MAR** — The market risk chapters of the consolidated Basel Framework, `MAR10`–`MAR99`.

**Marginal contribution to risk (MCR)** — The change in portfolio risk from a *small* addition. *Technical:* `Cov(rᵢ, r_p)/σ_p`. **Does not sum to the total** — that is **CCR**.

**Mark-to-market** — Daily fair valuation with the change through P&L. **The mechanism that makes market risk bite on a daily cycle.**

**MBS** — *Mortgage-Backed Security*. Carries **negative convexity** through the borrower's prepayment option.

**Modellable risk factor** — A factor passing the **RFET**. Included in the **ES** model with full diversification.

**Modified duration** — Percentage price change per 100bp. *Technical:* `D_mac/(1+y/f)`; equals `D_mac` under continuous compounding.

**MPOR** — *Margin Period of Risk*. The gap between the last successful margin call and completed close-out. **What initial margin exists to cover.**

**MVA** — *Margin Valuation Adjustment*. The funding cost of posted initial margin.

---

## N

**Negative convexity** — Price rises less on a rally than it falls on a sell-off. Held by **MBS**, callables and short-option positions. **Forces you to buy high and sell low to stay hedged.**

**NII** — *Net Interest Income*. The **IRRBB** earnings metric, typically over 1–2 years.

**NMD** — *Non-Maturity Deposit*. Contractually repayable on demand, behaviourally sticky. **The single largest driver of measured IRRBB, and an assumption rather than a contract term.**

**NMRF** — *Non-Modellable Risk Factor*. A factor failing the **RFET**, capitalised through **SES** with limited diversification.

**NOP** — *Net Open Position*. Total FX exposure per currency: spot + forward + option delta + accruals.

---

## O

**OAS** — *Option-Adjusted Spread*. **Z-spread** with embedded option value removed. **The only valid comparison basis for callables and MBS.**

**OIS** — *Overnight Index Swap*. A swap on the compounded overnight rate. Post-reform, **the risk-free curve** for most purposes.

**Outcomes analysis** — Comparing model outputs to real-world outcomes. **For market risk models, backtesting is outcomes analysis.**

**Output floor** — A Basel III constraint limiting how far modelled RWA may fall below the standardised calculation.

---

## P

**Par rate** — The coupon making an instrument price at par. **What the market quotes**; discount factors are derived from it.

**PFE** — *Potential Future Exposure*. A high percentile of future exposure.

**PLA** — *P&L Attribution test*. Compares **RTPL** with **HPL** using **Spearman correlation** and the **KS** metric on 250 days. **Green requires both conditions; red triggers on either.**

**Positive semi-definite (PSD)** — Required property of a covariance matrix: `xᵀΣx ≥ 0` for all `x`, because that quantity **is** a portfolio variance.

**Prudent valuation** — Additional value adjustments (AVAs) above accounting fair value, taken as a **capital deduction**.

**PV01** — *Present Value of an 01*. Change in value for a 1bp shift in the **par or zero curve**; often the fixed-leg **annuity**. **Not always identical to DV01 — ask what was bumped.**

---

## R

**Real price observation** — Evidence a market exists at a risk factor. *Technical:* a transaction the bank conducted; a verifiable arm's-length transaction; a **committed** quote verified through a vendor, platform or exchange; or a qualifying vendor price (`MAR31.12`). **Collateral valuations do not count. Indicative quotes are not committed quotes.**

**Reverse stress testing** — Starting from an outcome and finding the scenario that produces it. **Limited by the portfolio's vulnerabilities rather than by the designer's imagination.**

**RFET** — *Risk Factor Eligibility Test*. **24 observations per year with no 90-day gap below 4**, **or** **100 over 12 months**; max one per day; assessed **quarterly**, monitored **monthly**.

**Risk factor** — A market observable whose movement changes a position's value. **The atom of market risk measurement.**

**Risk reversal (RR)** — An FX volatility quote measuring **skew**: `σ(25Δ call) − σ(25Δ put)`.

**Roll-down** — Price gain from a bond ageing down a sloped curve with the curve unchanged. **Negative on an inverted curve.**

**RRAO** — *Residual Risk Add-On*. `Σ gross notional × RW`, with **1.0%** for exotic underlyings and **0.1%** for other residual risks. **Additive on top of SBM and DRC, never a substitute.**

**RTPL** — *Risk-Theoretical P&L*. **P&L produced by the valuation engine of the trading desk's risk management model** (`MAR32.22`). **Must not include factors the risk model does not contain** — that constraint is the entire mechanism of the PLA test.

---

## S

**SA-CCR** — The standardised approach for counterparty credit exposure: `EAD = alpha × (RC + PFE)` (`CRE52`).

**SA-CVA** — The standardised approach for CVA risk, **requiring supervisory approval**. Adapted from the market risk SA but **has no curvature charge**.

**SBM** — *Sensitivities-Based Method*. The FRTB SA core: **delta + vega + curvature** over **seven risk classes**, run under **three correlation scenarios** with capital set to the maximum.

**SDV01** — *Spread DV01*. See **CS01**.

**SES** — *Stress Scenario Capital*. Capital for **NMRFs**, aggregated at **ρ = 0.6**, with a liquidity horizon of **max(Table 2 horizon, 20 days)**.

**Sensitivity** — The rate of change of value with respect to a risk factor. **Additive across positions for the same factor** — which is why the trading floor works in sensitivities.

**Spearman correlation** — The **PLA** rank-correlation metric. Robust to outliers; tests whether the model **orders** days correctly.

**SR 26-2** — *Revised Guidance on Model Risk Management*, Fed/OCC/FDIC, **17 April 2026**. **Supersedes and replaces SR 11-7 and SR 21-8.**

**SS1/23** — PRA *Model risk management principles for banks*, effective **17 May 2024**. Five principles.

**Steepener** — A **DV01-neutral** trade profiting when the curve steepens.

**Sticky strike / sticky delta** — Assumptions about whether the **volatility surface** moves with spot. **A modelling choice that changes every reported delta** — state which regime is used.

**Stressed VaR/ES** — A risk measure calibrated to a stress period rather than a recent window.

**Sub-additivity** — `ρ(A+B) ≤ ρ(A) + ρ(B)`: diversification cannot increase risk. **ES satisfies it; VaR does not.**

---

## T

**Theta (Θ)** — Value change per day from the passage of time. **Not a risk factor** — time passes with certainty, so theta belongs in attribution, not VaR.

**Trading book** — Instruments held for short-term resale, short-term price movements, arbitrage, or hedging those (`RBC25.5`). **Must be fair valued daily through P&L** (`RBC25.4`). **The banking book is the residual.**

**Trading desk** — A **regulatory object** under `MAR12`: one head, defined strategy, documented risk structure, clear reporting lines. **The unit at which IMA approval is granted and withdrawn.**

**Traffic light zones** — Green/amber/red backtesting zones. **Retained under FRTB** for bank-wide backtesting (`MAR32.8`–`MAR32.9`); the multiplier scale changed from 3+ to **1.50–2.00**.

---

## V

**Vanna** — `∂²V/∂S∂σ`. How **vega** changes as spot moves — exposure to **skew**. **A first-class desk risk in FX.**

**VaR** — *Value at Risk*. **The loss that will not be exceeded with probability α over horizon h, assuming the model is right.** *Technical:* the α-quantile of the loss distribution. **Not a maximum; not sub-additive; says nothing about the tail's shape.**

**Vega (ν)** — Value change per **vol point**. *Technical:* `S·e^(−qτ)φ(d₁)√τ`; **identical for call and put**. **Must be bucketed by expiry and strike — a single scalar vega conceals term-structure positions.**

**Volatility surface** — Implied volatility as a function of strike and expiry. **The market's systematic correction to Black-Scholes.**

**Volga (vomma)** — `∂²V/∂σ²`. Vega convexity — exposure to the **smile**.

---

## W

**Wrong-way risk** — Exposure that **increases as the counterparty's creditworthiness deteriorates**. **Specific** wrong-way risk (exposure directly linked to the counterparty's own credit) receives punitive treatment; the 2008 monoline experience is the reference case.

---

## X–Z

**XVA** — The family of valuation adjustments: **CVA**, **DVA**, **FVA**, **MVA**, ColVA, KVA.

**Yield to maturity (YTM)** — The single rate equating discounted cash flows to price. **A quoting convention that compresses a curve into one number** — useful for comparison, dangerous for valuation.

**Z-spread** — The constant spread added to **every zero rate** such that PV equals market price. **The correct comparison basis for bullet bonds; use OAS for callables.**

---

## Abbreviation quick index

| Abbr. | Expansion | Doc |
|---|---|---|
| AAD | Adjoint Algorithmic Differentiation | [25](25_Risk_System_Architecture.md) |
| APL | Actual P&L | [14](14_PnL_and_PnL_Explain.md) |
| ASW | Asset Swap Spread | [05](05_Credit_Spread_Risk.md) |
| AVA | Additional Value Adjustment | [27](27_Controls_and_Governance.md) |
| BA-CVA | Basic Approach to CVA | [22](22_Counterparty_CVA_and_SIMM.md) |
| BPV | Basis Point Value | [04](04_Interest_Rate_Risk.md) |
| CCR | Counterparty Credit Risk / Component Contribution to Risk | [22](22_Counterparty_CVA_and_SIMM.md) / [10](10_Portfolio_Risk_Mathematics.md) |
| CE | Current Exposure | [22](22_Counterparty_CVA_and_SIMM.md) |
| CS01 | Credit Spread 01 | [05](05_Credit_Spread_Risk.md) |
| CSA | Credit Support Annex | [03](03_Pricing_Fundamentals.md) |
| CSR | Credit Spread Risk | [05](05_Credit_Spread_Risk.md) |
| CTD | Cheapest-to-Deliver | [02](02_Financial_Instruments.md) |
| CTP | Correlation Trading Portfolio | [16](16_FRTB_Overview.md) |
| CVA | Credit Valuation Adjustment | [22](22_Counterparty_CVA_and_SIMM.md) |
| CVR | Curvature Risk Charge | [17](17_FRTB_Standardised_Approach.md) |
| DF | Discount Factor | [03](03_Pricing_Fundamentals.md) |
| DRC | Default Risk Charge | [19](19_Default_Risk_and_DRC.md) |
| DV01 | Dollar Value of an 01 | [04](04_Interest_Rate_Risk.md) |
| DVA | Debit Valuation Adjustment | [22](22_Counterparty_CVA_and_SIMM.md) |
| EAD | Exposure at Default | [22](22_Counterparty_CVA_and_SIMM.md) |
| EE / EPE / EEPE | Expected (Positive) Exposure | [22](22_Counterparty_CVA_and_SIMM.md) |
| ERBA | Expanded Risk-Based Approach | [29](29_Regulatory_Framework.md) |
| ES | Expected Shortfall | [12](12_Expected_Shortfall.md) |
| EVE | Economic Value of Equity | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| EWMA | Exponentially Weighted Moving Average | [10](10_Portfolio_Risk_Mathematics.md) |
| FRN | Floating Rate Note | [02](02_Financial_Instruments.md) |
| FRTB | Fundamental Review of the Trading Book | [16](16_FRTB_Overview.md) |
| FVA | Funding Valuation Adjustment | [22](22_Counterparty_CVA_and_SIMM.md) |
| GIRR | General Interest Rate Risk | [04](04_Interest_Rate_Risk.md) |
| GMS | Global Market Shock | [13](13_Stress_Testing.md) |
| HBR | Hedge Benefit Ratio | [19](19_Default_Risk_and_DRC.md) |
| HPL | Hypothetical P&L | [14](14_PnL_and_PnL_Explain.md) |
| IMA | Internal Models Approach | [18](18_FRTB_Internal_Models_Approach.md) |
| IMCC | Internally Modelled Capital Charge | [18](18_FRTB_Internal_Models_Approach.md) |
| IPV | Independent Price Verification | [27](27_Controls_and_Governance.md) |
| IRRBB | Interest Rate Risk in the Banking Book | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| IRT | Internal Risk Transfer | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| JTD | Jump-to-Default | [19](19_Default_Risk_and_DRC.md) |
| KRD01 | Key-Rate DV01 | [04](04_Interest_Rate_Risk.md) |
| KS | Kolmogorov-Smirnov | [15](15_Backtesting.md) |
| LGD | Loss Given Default | [19](19_Default_Risk_and_DRC.md) |
| LH | Liquidity Horizon | [18](18_FRTB_Internal_Models_Approach.md) |
| MCR | Marginal Contribution to Risk | [10](10_Portfolio_Risk_Mathematics.md) |
| MPOR | Margin Period of Risk | [22](22_Counterparty_CVA_and_SIMM.md) |
| MVA | Margin Valuation Adjustment | [22](22_Counterparty_CVA_and_SIMM.md) |
| NII | Net Interest Income | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| NMD | Non-Maturity Deposit | [20A](20A_Trading_Book_Boundary_and_IRRBB.md) |
| NMRF | Non-Modellable Risk Factor | [20](20_NMRF_and_Modellability.md) |
| NOP | Net Open Position | [06](06_FX_Risk.md) |
| OAS | Option-Adjusted Spread | [05](05_Credit_Spread_Risk.md) |
| OIS | Overnight Index Swap | [02](02_Financial_Instruments.md) |
| PFE | Potential Future Exposure | [22](22_Counterparty_CVA_and_SIMM.md) |
| PLA | P&L Attribution test | [15](15_Backtesting.md) |
| PSD | Positive Semi-Definite | [10](10_Portfolio_Risk_Mathematics.md) |
| PV01 | Present Value of an 01 | [04](04_Interest_Rate_Risk.md) |
| RFET | Risk Factor Eligibility Test | [20](20_NMRF_and_Modellability.md) |
| RRAO | Residual Risk Add-On | [17](17_FRTB_Standardised_Approach.md) |
| RTPL | Risk-Theoretical P&L | [14](14_PnL_and_PnL_Explain.md) |
| RWA | Risk-Weighted Assets | [16](16_FRTB_Overview.md) |
| SA-CCR | Standardised Approach for Counterparty Credit Risk | [22](22_Counterparty_CVA_and_SIMM.md) |
| SBM | Sensitivities-Based Method | [17](17_FRTB_Standardised_Approach.md) |
| SDV01 | Spread DV01 | [05](05_Credit_Spread_Risk.md) |
| SES | Stress Scenario Capital | [20](20_NMRF_and_Modellability.md) |
| SIMM | Standard Initial Margin Model | [22](22_Counterparty_CVA_and_SIMM.md) |
| VaR | Value at Risk | [11](11_VaR.md) |
| XVA | Valuation Adjustments (family) | [22](22_Counterparty_CVA_and_SIMM.md) |

---

## Terms whose meaning is genuinely contested

**These are the ones to clarify before any cross-institution conversation.**

| Term | The ambiguity | Resolution |
|---|---|---|
| **DV01 / PV01 / BPV** | Which curve object was bumped — yield, par curve, or zero curve; and whether all legs were bumped | **Always ask what was bumped.** Roughly half of all sensitivity reconciliation breaks resolve here |
| **Clean P&L** | Institution-specific; sometimes = HPL, sometimes = P&L ex-fees only | Ask for the local definition |
| **Gap risk** | RRAO hedge-slippage meaning vs ordinary overnight-jump meaning | State which |
| **DV01 sign** | Positive = long duration, or positive = `∂P/∂y` | Establish the house convention |
| **Vega scaling** | Per 1.00 of vol, or per 1 vol point (1%) | Market convention is per vol point |
| **Theta scaling** | Per year or per day | Market convention is per day |
| **Normal vs lognormal vol** | Both quoted as a bare number | **Order-of-magnitude consequences** — confirm the convention |
| **"Duration"** | Macaulay, modified or effective | Specify |
| **"Stress test"** | A scenario analysis, a supervisory exercise, or a sensitivity grid | Specify |
| **"Model"** | SR 26-2 narrows this to theory-based quantitative methods, excluding spreadsheets and rule engines | Use the applicable regulatory definition |

---

## Related Concepts

- [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) · [32 — Master Formula Handbook](32_Master_Formula_Handbook.md)
- [33 — Master Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md) · [29 — Regulatory Framework](29_Regulatory_Framework.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR10` terminology; all regulatory definitions cited |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | `MAR50`, `CRE52`, `SRP31` terms |
| Federal Reserve / OCC / FDIC | SR 26-2 | 17 Apr 2026 | https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf | Definition of "model"; effective challenge |
| ISDA | ISDA SIMM Methodology v2.8+2512 | 12 Jun 2026 | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ | SIMM terms |

*Accessed 25 August 2026.*
