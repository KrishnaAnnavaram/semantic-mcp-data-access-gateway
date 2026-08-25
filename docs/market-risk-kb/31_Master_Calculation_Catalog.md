# 31 — Master Market Risk Calculation Catalog

**Level:** Reference · **Prerequisites:** none (index document) · **Companion to:** [32 — Formula Handbook](32_Master_Formula_Handbook.md), [33 — Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md)

---

## How this catalogue is organised

A single 26-column table over 160 calculations is unreadable, and an unreadable reference is not a reference. This catalogue therefore carries **all 26 fields**, distributed as follows:

| Where | Fields |
|---|---|
| **Category header block** | Category · Subcategory · Market data required · Historical data required · Position data required · Reference data required · Aggregation level · Regulatory use (category-level) · Validation approach (category-level) |
| **Row** | Calculation ID · Name · Alternative names · Instruments · Purpose / simple explanation · Formula or method · Key inputs · Output and units · Frequency · Primary users · FRTB relevance |
| **Detailed document** | Full worked example · assumptions · limitations · edge cases · common errors · per-calculation validation checklist · related calculations · sources |

**The `Doc` column is the join key to the detailed treatment**, where every field is expanded and every formula is worked numerically.

**Frequency codes:** `RT` real time · `ID` intraday · `EOD` end of day · `W` weekly · `M` monthly · `Q` quarterly · `AH` ad hoc
**User codes:** `TR` trader · `DH` desk head · `MR` market risk · `PC` product control · `CAP` capital team · `MV` model validation · `SM` senior management · `REG` regulator · `TRS` treasury

---

## A. Pricing and Valuation — `PV`

> **Category:** Pricing · **Subcategory:** Valuation primitives
> **Market data:** curves, surfaces, prices, spreads · **Historical data:** none · **Position data:** contractual terms · **Reference data:** calendars, day counts, conventions
> **Aggregation:** position → book → desk (simple sum of PV within a currency)
> **Regulatory use:** input to every capital calculation; `MAR32.29` requires the same pricing models across APL, HPL and reported P&L
> **Validation:** reprice market inputs; put-call parity; benchmark model; independent price verification

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PV-01 | **Present value** | PV, discounting | All | Value of future cash today | `Σ CFᵢ · DF(tᵢ)` | cash flows, curve | currency | RT–EOD | TR·MR·PC | Basis of all | [03](03_Pricing_Fundamentals.md) |
| PV-02 | **Discount factor** | DF | All dated | PV of $1 at *t* | `e^(−z(t)·t)` | zero rate | ratio | EOD | MR | — | [03](03_Pricing_Fundamentals.md) |
| PV-03 | **Forward rate** | implied forward | Rates | Rate contracted today for a future period | `(1/(t₂−t₁))·ln(DF(t₁)/DF(t₂))` | two DFs | % p.a. | EOD | TR·MR | GIRR factor | [03](03_Pricing_Fundamentals.md) |
| PV-04 | **Par swap rate** | par rate, swap rate | Swaps | Fixed rate making PV zero | `Σ Lᵢτᵢ DF(tᵢ) / Σ τⱼDF(tⱼ)` | proj. + disc. curves | % p.a. | EOD | TR·MR | GIRR input | [04](04_Interest_Rate_Risk.md) |
| PV-05 | **Bootstrapping** | curve build, stripping | Rates | Derive DFs from quoted par instruments | sequential or global solve | market quotes | curve | EOD | MR | Curve basis | [23](23_Market_Data_and_Curves.md) |
| PV-06 | **Accrued interest** | AI | Coupon bonds | Coupon earned not yet paid | `Cpn × days/period` | dates, day count | currency | EOD | PC·MR | — | [03](03_Pricing_Fundamentals.md) |
| PV-07 | **Clean price** | quoted price | Bonds | Price excluding accrued | `dirty − AI` | dirty, AI | price | EOD | TR·PC | — | [03](03_Pricing_Fundamentals.md) |
| PV-08 | **Dirty price** | full price, invoice price | Bonds | Price actually paid | `Σ CFᵢDF(tᵢ)` | curve, CFs | price | EOD | PC·MR | Sensitivity basis | [03](03_Pricing_Fundamentals.md) |
| PV-09 | **Yield to maturity** | YTM, redemption yield | Bonds | Single rate equating PV to price | Newton-Raphson solve | price, CFs | % p.a. | EOD | TR | — | [03](03_Pricing_Fundamentals.md) |
| PV-10 | **Discount ↔ coupon-equivalent** | BEY conversion | Bills | Convert quoting basis | convention formula | discount rate, days | % p.a. | EOD | MR | Curve integrity | [02](02_Financial_Instruments.md) |
| PV-11 | **Annuity / fixed-leg PV01** | annuity factor | Swaps | Sum of discounted accruals | `Σ τⱼ DF(tⱼ)` | curve, schedule | years | EOD | TR·MR | GIRR delta | [04](04_Interest_Rate_Risk.md) |
| PV-12 | **Swap PV** | MTM | IRS, OIS | Net value of both legs | `N·[K·A − FloatPV]` | 2 curves, CSA | currency | RT–EOD | TR·MR | GIRR | [02](02_Financial_Instruments.md) |
| PV-13 | **FX forward rate** | CIP forward | FX fwd, swap | No-arbitrage forward | `S·(1+r_q τ)/(1+r_b τ)` | spot, 2 rates | rate | RT–EOD | TR·MR | FX + GIRR | [06](06_FX_Risk.md) |
| PV-14 | **Forward points** | swap points, pips | FX fwd | Forward minus spot | `(F − S)×10⁴` | F, S | pips | RT | TR | — | [06](06_FX_Risk.md) |
| PV-15 | **Equity forward price** | — | Eq fwd/future | Cost-of-carry forward | `S·e^((r−q)τ)` | spot, rate, div | price | EOD | TR·MR | Equity | [07](07_Equity_Risk.md) |
| PV-16 | **Commodity forward** | cost of carry | Cmdty fwd | Storage-adjusted forward | `S·e^((r+u−y)τ)` | spot, r, storage | price | EOD | TR·MR | Commodity | [08](08_Commodity_Risk.md) |
| PV-17 | **Convenience yield** | implied *y* | Cmdty | Benefit of holding physical | residual of PV-16 | F, S, r, u | % p.a. | EOD | MR | — | [08](08_Commodity_Risk.md) |
| PV-18 | **Black-Scholes-Merton** | BSM | Vanilla options | Price a European option on spot | `S·N(d₁) − K·e^(−rτ)N(d₂)` | S,K,r,σ,τ | currency | RT–EOD | TR·MR | Vega/curvature basis | [03](03_Pricing_Fundamentals.md) |
| PV-19 | **Black model** | Black-76 | Swaptions, caps, cmdty | Option on a forward | `e^(−rτ)[F·N(d₁)−K·N(d₂)]` | F,K,r,σ,τ | currency | EOD | TR·MR | GIRR vega | [03](03_Pricing_Fundamentals.md) |
| PV-20 | **Bachelier (normal)** | normal model | Rate options | Option where the underlying can go negative | `e^(−rτ)[(F−K)N(d)+σ_N√τ·φ(d)]` | F,K,σ_N,τ | currency | EOD | TR·MR | GIRR vega | [03](03_Pricing_Fundamentals.md) |
| PV-21 | **Put-call parity** | — | Vanilla options | Consistency identity | `C−P = S e^(−qτ) − K e^(−rτ)` | C,P,S,K | check | EOD | MR·MV | Surface validation | [09](09_Options_and_Greeks.md) |
| PV-22 | **Implied volatility** | IV solve | Options | Invert price to σ | root-find on BSM | price, S,K,r,τ | % p.a. | RT–EOD | TR·MR | Vega factor | [09](09_Options_and_Greeks.md) |
| PV-23 | **Lattice pricing** | binomial, trinomial | American, callable | Price early-exercise products | backward induction | tree params | currency | EOD | MR | Curvature | [02](02_Financial_Instruments.md) |
| PV-24 | **Monte Carlo pricing** | simulation | Path-dependent, exotic | Price by simulated paths | average discounted payoff | model, paths | currency | EOD | MR | RRAO population | [11](11_VaR.md) |
| PV-25 | **PDE / finite difference** | grid solver | Barriers, American | Price by solving the PDE | discretised PDE | grid, boundaries | currency | EOD | MR | Curvature | [09](09_Options_and_Greeks.md) |
| PV-26 | **Z-spread** | zero-volatility spread | Credit bonds | Constant spread over the zero curve | root-find on price | price, curve, CFs | bp | EOD | TR·MR | CSR input | [05](05_Credit_Spread_Risk.md) |
| PV-27 | **Option-adjusted spread** | OAS | Callables, MBS | Z-spread net of option value | model + spread solve | price, curve, vol | bp | EOD | TR·MR | CSR input | [05](05_Credit_Spread_Risk.md) |
| PV-28 | **Asset swap spread** | ASW | Credit bonds | Spread in swap terms | par/par or MV ASW | price, swap curve | bp | EOD | TR | — | [05](05_Credit_Spread_Risk.md) |
| PV-29 | **G-spread** | yield spread | Credit bonds | YTM over interpolated govt | `y_corp − y_govt` | 2 yields | bp | RT | TR | — | [05](05_Credit_Spread_Risk.md) |
| PV-30 | **CDS upfront / par spread** | — | CDS | Reconcile fixed coupon to market | ISDA standard model | spread, recovery | currency / bp | EOD | TR·MR | CSR, DRC | [05](05_Credit_Spread_Risk.md) |
| PV-31 | **Credit triangle** | hazard rate approx. | CDS | Link spread, hazard, recovery | `s ≈ λ(1−R)` | spread, recovery | % p.a. | EOD | MR | — | [05](05_Credit_Spread_Risk.md) |
| PV-32 | **Survival probability** | `Q(t)` | Credit | Probability of no default by *t* | `exp(−∫λ du)` | hazard curve | probability | EOD | MR | CVA, DRC | [22](22_Counterparty_CVA_and_SIMM.md) |

---

## B. Interest Rate Sensitivities — `IR`

> **Category:** Sensitivities · **Subcategory:** Interest rate
> **Market data:** risk-free and projection curves · **Historical data:** none · **Position data:** all rate-bearing positions · **Reference data:** schedules, day counts, calendars
> **Aggregation:** by **currency and tenor** — never across currencies
> **Regulatory use:** direct input to **FRTB SBM GIRR delta**; `MAR21.8` fixes ten vertices (0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30 years)
> **Validation:** analytic vs bumped agreement; bump-size stability; sign check; `Σ KRD01 = parallel DV01`; dirty-price basis

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| IR-01 | **Macaulay duration** | — | Fixed CF bonds | PV-weighted average time to cash flow | `Σ tᵢPV(CFᵢ)/P` | CFs, curve | years | EOD | MR·TRS | `MAR40` only | [04 §1](04_Interest_Rate_Risk.md) |
| IR-02 | **Modified duration** | mod dur | Fixed CF bonds | % price change per 100bp | `D_mac/(1+y/f)` | D_mac, y, f | % per 100bp | EOD | TR·DH·MR | `MAR40` | [04 §2](04_Interest_Rate_Risk.md) |
| IR-03 | **Dollar duration** | DD | Bonds | Currency price change per unit yield | `D_mod × P` | D_mod, P | currency | EOD | MR | — | [04](04_Interest_Rate_Risk.md) |
| IR-04 | **DV01** | dollar value of an 01 | All rate products | **Money lost per 1bp rate rise** | `[P(y−1bp)−P(y+1bp)]/2` | curve, pricer | **currency/bp** | RT–EOD | TR·DH·MR·CAP | **GIRR delta** | [04 §4](04_Interest_Rate_Risk.md) |
| IR-05 | **PV01** | present value of an 01 | Swaps | Value change per 1bp curve shift | bump par/zero curve | curve, pricer | currency/bp | EOD | TR·MR | GIRR delta | [04 §4.4](04_Interest_Rate_Risk.md) |
| IR-06 | **BPV** | basis point value | Bonds, futures | Generic 1bp sensitivity | as DV01 | curve, pricer | currency/bp | EOD | TR | GIRR delta | [04 §4.4](04_Interest_Rate_Risk.md) |
| IR-07 | **Key-rate DV01** | KRD01, bucketed PV01 | All rate products | **Where on the curve the risk sits** | tent bump per node | curve, node set | currency/bp per node | ID–EOD | TR·DH·MR·CAP | **GIRR delta by vertex** | [04 §5](04_Interest_Rate_Risk.md) |
| IR-08 | **Key rate duration** | KRD | Bonds | KRD01 expressed as duration | `KRD01/(P·0.0001)` | KRD01, P | years | EOD | MR | — | [04 §5](04_Interest_Rate_Risk.md) |
| IR-09 | **Convexity (analytical)** | — | Fixed CF bonds | Curvature of price vs yield | `Σ tᵢ²PV(CFᵢ)/P` | CFs, curve | dimensionless | EOD | TR·MR | Curvature analogue | [04 §6](04_Interest_Rate_Risk.md) |
| IR-10 | **Effective duration** | option-adjusted duration | Callables, MBS | Duration when cash flows respond to rates | `[P(−Δy)−P(+Δy)]/(2P₀Δy)` | pricer + option model | years | EOD | TR·MR | Curvature basis | [04 §3](04_Interest_Rate_Risk.md) |
| IR-11 | **Effective convexity** | — | Callables, MBS | Convexity by revaluation | `[P₊+P₋−2P₀]/(P₀Δy²)` | pricer + model | dimensionless | EOD | MR | Curvature | [04 §6](04_Interest_Rate_Risk.md) |
| IR-12 | **Dollar convexity** | — | Bonds | Convexity in currency terms | `C × P` | C, P | currency | EOD | MR | — | [04 §6.3](04_Interest_Rate_Risk.md) |
| IR-13 | **Basis DV01** | tenor basis sensitivity | Basis swaps | Sensitivity to index basis | bump basis curve | basis curve | currency/bp | EOD | TR·MR | GIRR sep. curves | [04 §8](04_Interest_Rate_Risk.md) |
| IR-14 | **Cross-currency basis DV01** | XCCY DV01 | XCCY swaps, FX fwd | Sensitivity to XCCY basis | bump basis curve | XCCY curve | currency/bp | EOD | TR·MR | **GIRR, ρ = 0%** | [06 §5](06_FX_Risk.md) |
| IR-15 | **Inflation DV01** | breakeven sensitivity | Linkers, infl. swaps | Sensitivity to breakeven | bump inflation curve | inflation curve | currency/bp | EOD | TR·MR | GIRR, RW 1.6% | [02 §1.4](02_Financial_Instruments.md) |
| IR-16 | **Swap DV01** | annuity DV01 | Swaps | Swap sensitivity ≈ annuity | `N·A·0.0001` | notional, annuity | currency/bp | EOD | TR·MR | GIRR delta | [04 §11.4](04_Interest_Rate_Risk.md) |
| IR-17 | **Curve slope sensitivity** | 2s10s, steepener risk | Curve trades | P&L per bp of slope change | KRD ladder × slope vector | ladder | currency/bp | EOD | TR·DH·MR | Cross-tenor ρ | [04 §7](04_Interest_Rate_Risk.md) |
| IR-18 | **Butterfly sensitivity** | fly risk | Butterfly trades | P&L per bp of curvature change | ladder × fly vector | ladder | currency/bp | EOD | TR·MR | Cross-tenor ρ | [04 §7](04_Interest_Rate_Risk.md) |
| IR-19 | **Carry** | net carry | Financed positions | Earned for holding, all else equal | `coupon accrual − funding` | coupon, repo, days | currency/period | EOD | TR·DH·PC | P&L attribution | [04 §9](04_Interest_Rate_Risk.md) |
| IR-20 | **Roll-down** | rolldown | Bonds, swaps | Gain from ageing down a sloped curve | reprice at shorter tenor | curve, horizon | currency | EOD | TR·DH | P&L attribution | [04 §10](04_Interest_Rate_Risk.md) |
| IR-21 | **Carry + roll** | total static return | Bonds, swaps | Expected return if nothing moves | `IR-19 + IR-20` | both | currency | EOD | TR·DH | — | [04 §10.4](04_Interest_Rate_Risk.md) |
| IR-22 | **Repo / financing sensitivity** | specialness risk | Repo, cash bonds | Sensitivity to financing rate | bump repo rate | repo curve | currency/bp | EOD | TR·MR | GIRR | [02 §2](02_Financial_Instruments.md) |

---

## C. Credit Spread and Default — `CR`

> **Category:** Sensitivities and default · **Subcategory:** Credit
> **Market data:** CDS curves, bond spreads, index levels, recovery assumptions · **Historical data:** for spread VaR only · **Position data:** credit-risky positions · **Reference data:** issuer, rating, sector, seniority, parent linkage
> **Aggregation:** by issuer → sector → rating → country; DRC by bucket with **no cross-bucket offset** (`MAR22.26`)
> **Regulatory use:** **CSR delta** (`MAR21.9`, five vertices: 0.5, 1, 3, 5, 10y); **DRC** (`MAR22`)
> **Validation:** rate/spread separation; FRN signature (near-zero DV01, full CS01); Z-spread reprices; JTD computed independently of CS01

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CR-01 | **CS01** | SDV01, CR01, spread delta | Bonds, CDS, FRNs | **Money lost per 1bp spread widening** | `[P(s−1bp)−P(s+1bp)]/2` | spread curve | **currency/bp** | RT–EOD | TR·DH·MR·CAP | **CSR delta** | [05 §4](05_Credit_Spread_Risk.md) |
| CR-02 | **Bucketed CS01** | CS01 ladder | Credit | Where on the credit curve | tent bump per vertex | spread curve | currency/bp per tenor | EOD | TR·MR·CAP | CSR by vertex | [05 §4.5](05_Credit_Spread_Risk.md) |
| CR-03 | **Issuer CS01** | single-name CS01 | Credit | Concentration by obligor | aggregate by issuer | issuer mapping | currency/bp | EOD | MR·DH | CSR bucketing | [05 §4.6](05_Credit_Spread_Risk.md) |
| CR-04 | **Sector CS01** | — | Credit | Concentration by industry | aggregate by sector | sector scheme | currency/bp | EOD | MR·SM | CSR buckets | [05 §4.6](05_Credit_Spread_Risk.md) |
| CR-05 | **Index CS01** | — | Index CDS | Systematic credit exposure | bump index spread | index level | currency/bp | EOD | TR·MR | CSR buckets 17/18 | [05 §6.2](05_Credit_Spread_Risk.md) |
| CR-06 | **CDS-bond basis** | — | Bond + CDS | Cash-derivative dislocation | `CDS spread − bond spread` | both spreads | bp | EOD | TR·MR | ρ(basis) 99.90% | [05 §7](05_Credit_Spread_Risk.md) |
| CR-07 | **Index skew** | index basis | Index vs constituents | Index vs theoretical | `index − Σ w·single` | index, constituents | bp | EOD | TR·MR | — | [05 §7](05_Credit_Spread_Risk.md) |
| CR-08 | **Gross JTD** | jump-to-default | Credit, equity | **Loss if the obligor defaults now** | `max/min(LGD·N + P&L, 0)` | notional, MV, LGD | **currency** | EOD | MR·CAP | **DRC** (`MAR22.11`) | [19 §4](19_Default_Risk_and_DRC.md) |
| CR-09 | **Net JTD** | — | Credit, equity | Same-obligor offset, maturity-scaled | sum with `<1y` scaling | gross JTDs, maturities | currency | EOD | MR·CAP | DRC (`MAR22.20`) | [19 §5](19_Default_Risk_and_DRC.md) |
| CR-10 | **Hedge benefit ratio** | HBR | Credit | Partial recognition of shorts in a bucket | `ΣJTD_L/(ΣJTD_L+\|ΣJTD_S\|)` | net JTDs | ratio | EOD | CAP | DRC (`MAR22.23`) | [19 §6.4](19_Default_Risk_and_DRC.md) |
| CR-11 | **Recovery sensitivity** | — | CDS, bonds | Sensitivity to the recovery assumption | bump *R* | R, spread | currency/% | EOD | MR·MV | DRC LGD | [05 §6](05_Credit_Spread_Risk.md) |

---

## D. Foreign Exchange — `FX`

> **Category:** Sensitivities · **Subcategory:** FX
> **Market data:** spot, forward points, both rate curves, XCCY basis, vol surfaces · **Position data:** all non-reporting-currency positions
> **Aggregation:** per currency pair against the **reporting currency** (`MAR21.14`)
> **Regulatory use:** **FX delta, RW 15%** (`MAR21.87`); cross-bucket **γ = 60%** (`MAR21.89`)
> **Validation:** NOP completeness; triangular consistency; forward = CIP + basis; both rate legs reported; delta convention stated

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FX-01 | **Net open position** | NOP | All FX-exposed | Total exposure per currency | spot + fwd + Δ + accruals | positions, spot | currency | RT–EOD | TR·DH·MR·TRS | FX delta | [06 §3](06_FX_Risk.md) |
| FX-02 | **FX delta** | spot delta | FX products | Sensitivity to the spot rate | bump spot | spot | currency | RT | TR·MR | **FX delta** | [06 §8](06_FX_Risk.md) |
| FX-03 | **FX forward valuation** | — | Forwards, NDFs | MTM of a forward | `N(F−K)·DF_q` | F, K, DFs | currency | EOD | TR·MR | FX + GIRR | [06 §4](06_FX_Risk.md) |
| FX-04 | **FX vega** | — | FX options | Sensitivity to implied vol | `S·e^(−qτ)φ(d₁)√τ` | S,σ,τ | currency/vol pt | RT–EOD | TR·MR | FX vega, LH 40 | [09 §5](09_Options_and_Greeks.md) |
| FX-05 | **Vanna** | — | FX options | How vega moves with spot | `−e^(−qτ)φ(d₁)d₂/σ` | S,K,σ,τ | currency/(unit·vol) | EOD | TR·MR | Curvature-adjacent | [09 §8](09_Options_and_Greeks.md) |
| FX-06 | **Volga** | vomma | FX options | Vega convexity | `ν·d₁d₂/σ` | as above | currency/vol pt² | EOD | TR·MR | — | [09 §8](09_Options_and_Greeks.md) |
| FX-07 | **RR / BF decomposition** | skew & smile | FX options | Reconstruct strike vols from quotes | `σ_ATM ± BF ± RR/2` | ATM, RR, BF | % vol | RT–EOD | TR·MR | Vega surface | [06 §6](06_FX_Risk.md) |
| FX-08 | **Currency concentration** | — | All | Exposure vs limit per currency | NOP / limit | NOP, limits | ratio | EOD | MR·SM | — | [06 §3](06_FX_Risk.md) |

---

## E. Equity — `EQ`

> **Category:** Sensitivities · **Subcategory:** Equity
> **Market data:** spot, index levels, dividend forecasts, borrow rates, vol surfaces, implied correlation · **Historical data:** for beta
> **Reference data:** market cap (single listed entity, all markets — `MAR21.74`), economy (`MAR21.75` exhaustive list), sector
> **Aggregation:** name → sector → economy → market cap band (13 buckets)
> **Regulatory use:** **Equity delta** (spot **and** repo rates), vega, curvature (**spot only**); DRC
> **Validation:** exposure identities; beta window documented; idiosyncratic risk reported; **no vega or curvature on repo rates**

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EQ-01 | **Market value** | MV | Equity | Position value | `qty × spot` | qty, spot | currency | RT | TR·PC | Equity delta | [07 §3](07_Equity_Risk.md) |
| EQ-02 | **Net exposure** | net | Equity book | Directional bet | `long − short` | MVs | currency | RT–EOD | TR·DH·MR | — | [07 §3](07_Equity_Risk.md) |
| EQ-03 | **Gross exposure** | gross | Equity book | **Capital at work; leverage** | `long + short` | MVs | currency | EOD | DH·MR·SM | — | [07 §3](07_Equity_Risk.md) |
| EQ-04 | **Beta** | β | Equity | Co-movement with the market | `Cov(rᵢ,r_m)/Var(r_m)` | return histories | dimensionless | M | MR | — | [07 §4](07_Equity_Risk.md) |
| EQ-05 | **Beta-adjusted exposure** | — | Equity book | Market bet in index terms | `Σ MVᵢβᵢ` | MVs, betas | currency | EOD | DH·MR | — | [07 §3.2](07_Equity_Risk.md) |
| EQ-06 | **Equity delta** | — | Eq. derivatives | Sensitivity to spot | `e^(−qτ)N(d₁)` etc. | S,K,σ,τ | shares or currency | RT | TR·MR | **Equity delta** | [09 §3](09_Options_and_Greeks.md) |
| EQ-07 | **Dividend sensitivity** | div delta, ρ_q | Fwds, options, swaps | Sensitivity to forecast dividends | bump *q* | dividend curve | currency/% | EOD | TR·MR | Equity risk factor | [07 §5](07_Equity_Risk.md) |
| EQ-08 | **Equity repo sensitivity** | borrow sensitivity | Shorts, swaps, options | Sensitivity to borrow cost | bump repo rate | repo rate | currency/bp | EOD | TR·MR | **Equity delta, RW = spot/100** | [07 §6](07_Equity_Risk.md) |
| EQ-09 | **Implied correlation** | dispersion | Baskets, index options | Correlation priced in a basket | invert index vs constituents | vols, weights | correlation | EOD | TR·MR | RRAO | [07 §7.3](07_Equity_Risk.md) |
| EQ-10 | **Single-name concentration** | — | Equity book | Idiosyncratic exposure | largest MV / limits | MVs, limits | currency, ratio | EOD | MR·SM | DRC | [07 §2](07_Equity_Risk.md) |

---

## F. Commodity — `CM`

> **Category:** Sensitivities · **Subcategory:** Commodity
> **Market data:** futures curves by delivery month, location differentials, vol surfaces · **Reference data:** commodity bucket (11), delivery location, grade, contract size
> **Aggregation:** commodity → tenor → delivery location (`ρ = ρ_cty × 99.00% × 99.90%`)
> **Regulatory use:** **Commodity delta**, vega (LH 120), curvature; RW 20%–80% by bucket
> **Validation:** curve completeness; negative prices supported; unit conversions; peak vs off-peak power as distinct commodities (`MAR21.84`)

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CM-01 | **Commodity delta** | — | Futures, swaps, options | Sensitivity to the commodity price | relative bump | forward curve | currency | RT–EOD | TR·MR | **Commodity delta** | [08 §6](08_Commodity_Risk.md) |
| CM-02 | **Calendar spread sensitivity** | time spread risk | Cal spreads | Sensitivity to curve shape | bump one month | curve by month | currency | EOD | TR·MR | Commodity, ρ_tenor 99% | [08 §4](08_Commodity_Risk.md) |
| CM-03 | **Location basis sensitivity** | — | Physical, basis swaps | Sensitivity to hub differentials | bump differential | location prices | currency | EOD | TR·MR | ρ_basis 99.90% | [08 §4](08_Commodity_Risk.md) |
| CM-04 | **Roll yield** | roll return | Futures, indices | Return from rolling the curve | `(F₁−F₂)/F₁` | two contracts | % per roll | EOD | TR·DH | — | [08 §3.3](08_Commodity_Risk.md) |
| CM-05 | **Commodity vega** | — | Cmdty options | Sensitivity to implied vol | as GK-03 | S,σ,τ | currency/vol pt | EOD | TR·MR | Commodity vega, LH 120 | [08 §6.4](08_Commodity_Risk.md) |

---

## G. Options and Greeks — `GK`

> **Category:** Sensitivities · **Subcategory:** Optionality
> **Market data:** underlying prices, vol surfaces, rate curves, dividends/carry · **Position data:** all optioned positions
> **Aggregation:** by underlying, then **bucketed by expiry and strike** — never a single scalar vega
> **Regulatory use:** **SBM vega** (`MAR21.92`, σ = 55%, LH by class) and **curvature** (`MAR21.5`)
> **Validation:** put-call parity; gamma/vega identical for call and put; delta bounds; theta–gamma PDE consistency; full revaluation near barriers

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GK-01 | **Delta** | Δ | Options | Value change per unit of underlying | `e^(−qτ)N(d₁)` | S,K,r,q,σ,τ | currency/unit | RT | TR·MR | Delta class | [09 §3](09_Options_and_Greeks.md) |
| GK-02 | **Gamma** | Γ | Options | Rate of change of delta | `e^(−qτ)φ(d₁)/(Sσ√τ)` | as above | delta/unit | RT–EOD | TR·DH·MR | Curvature | [09 §4](09_Options_and_Greeks.md) |
| GK-03 | **Vega** | ν, kappa | Options | Value change per vol point | `S e^(−qτ)φ(d₁)√τ` | as above | currency/vol pt | RT–EOD | TR·DH·MR·CAP | **SBM vega** | [09 §5](09_Options_and_Greeks.md) |
| GK-04 | **Theta** | Θ | Options | Value change per day | BSM theta formula | as above | currency/day | EOD | TR·DH·PC | P&L attribution | [09 §6](09_Options_and_Greeks.md) |
| GK-05 | **Rho** | ρ | Options | Sensitivity to the rate | `Kτe^(−rτ)N(d₂)` | as above | currency/% | EOD | TR·MR | GIRR | [09 §7](09_Options_and_Greeks.md) |
| GK-06 | **Vanna** | — | Options | Spot-vol cross sensitivity | `−e^(−qτ)φ(d₁)d₂/σ` | as above | mixed | EOD | TR·MR | Skew exposure | [09 §8](09_Options_and_Greeks.md) |
| GK-07 | **Volga** | vomma | Options | Vega convexity | `ν d₁d₂/σ` | as above | currency/vol pt² | EOD | TR·MR | Smile exposure | [09 §8](09_Options_and_Greeks.md) |
| GK-08 | **Charm** | delta decay | Options | Delta change with time | `∂²V/∂S∂t` | as above | delta/day | EOD | TR | — | [09 §8](09_Options_and_Greeks.md) |
| GK-09 | **Speed** | — | Barriers, large moves | Gamma's rate of change | `∂³V/∂S³` | as above | gamma/unit | EOD | TR·MR | Curvature residual | [09 §8](09_Options_and_Greeks.md) |
| GK-10 | **Colour** | gamma decay | Near-expiry options | Gamma change with time | `∂³V/∂S²∂t` | as above | gamma/day | EOD | TR | — | [09 §8](09_Options_and_Greeks.md) |
| GK-11 | **Cross-gamma** | — | Multi-underlying | Joint second-order sensitivity | `∂²V/∂S₁∂S₂` | 2 underlyings | mixed | EOD | MR | RRAO correlation | [09 §8](09_Options_and_Greeks.md) |
| GK-12 | **Taylor P&L expansion** | Greeks P&L | Optioned books | Predict P&L from Greeks | `ΔΔS+½Γ(ΔS)²+νΔσ+ΘΔt` | Greeks, moves | currency | EOD | MR·PC | RTPL basis | [09 §2](09_Options_and_Greeks.md) |

---

## H. Portfolio Statistics — `PS`

> **Category:** Portfolio mathematics · **Subcategory:** Statistics
> **Market data:** factor levels · **Historical data:** **required** — return histories · **Position data:** weights or sensitivities
> **Aggregation:** the mechanism *of* aggregation
> **Regulatory use:** underlies IMA correlation treatment; SBM correlations are **prescribed**, not estimated
> **Validation:** PSD; Cholesky succeeds; Euler identity `Σ CCR = σ_p`; diversification bound `σ_p ≤ Σ wᵢσᵢ`

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PS-01 | **Arithmetic return** | simple return | All | Cross-sectional aggregation | `(P₁−P₀)/P₀` | prices | % | EOD | MR | — | [10 §1](10_Portfolio_Risk_Mathematics.md) |
| PS-02 | **Log return** | continuous return | All | **Time aggregation** | `ln(P₁/P₀)` | prices | % | EOD | MR | Factor simulation | [10 §1](10_Portfolio_Risk_Mathematics.md) |
| PS-03 | **Historical volatility** | realised vol | All | Dispersion of returns | sample std dev | return history | % p.a. | EOD | MR | ES input | [10 §2](10_Portfolio_Risk_Mathematics.md) |
| PS-04 | **EWMA volatility** | — | All | Recency-weighted vol | `λσ²ₜ₋₁+(1−λ)r²ₜ₋₁` | returns, λ | % p.a. | EOD | MR | — | [10 §2.4](10_Portfolio_Risk_Mathematics.md) |
| PS-05 | **Covariance** | — | All | Joint variation | `E[(X−μ)(Y−ν)]` | two histories | product units | EOD | MR | — | [10 §3](10_Portfolio_Risk_Mathematics.md) |
| PS-06 | **Correlation** | ρ | All | Normalised co-movement | `Cov/(σ_Xσ_Y)` | covariance, vols | ∈[−1,1] | EOD | MR | IMA correlations | [10 §3](10_Portfolio_Risk_Mathematics.md) |
| PS-07 | **Covariance matrix** | Σ | Portfolio | Full dependence structure | `D·R·D` | vols, correlations | matrix | EOD | MR | IMCC | [10 §3.2](10_Portfolio_Risk_Mathematics.md) |
| PS-08 | **PSD check / repair** | eigenvalue clipping, Higham | Portfolio | **Ensure the matrix is valid** | eigen-decomposition | Σ | matrix | EOD | MR·MV | Prerequisite | [10 §3.3](10_Portfolio_Risk_Mathematics.md) |
| PS-09 | **Cholesky decomposition** | — | Portfolio | Factorise for simulation | `Σ = LLᵀ` | Σ | matrix | EOD | MR | MC VaR | [10 §3.4](10_Portfolio_Risk_Mathematics.md) |
| PS-10 | **Portfolio variance** | — | Portfolio | Aggregate risk | `wᵀΣw` | weights, Σ | %² | EOD | MR·SM | — | [10 §4](10_Portfolio_Risk_Mathematics.md) |
| PS-11 | **Diversification ratio** | — | Portfolio | Benefit vs standalone sum | `σ_p/Σwᵢσᵢ` | both | ratio | EOD | MR·SM | — | [10 §5](10_Portfolio_Risk_Mathematics.md) |
| PS-12 | **Marginal contribution** | MCR | Portfolio | Risk of a *small* addition | `Cov(rᵢ,r_p)/σ_p` | Σ, weights | risk/unit | EOD | MR·DH | — | [10 §6.1](10_Portfolio_Risk_Mathematics.md) |
| PS-13 | **Component contribution** | CCR | Portfolio | **Share of current total risk** | `wᵢ·MCRᵢ`; `ΣCCR = σ_p` | Σ, weights | risk units | EOD | MR·DH·SM | Limit allocation | [10 §6.2](10_Portfolio_Risk_Mathematics.md) |
| PS-14 | **Incremental VaR** | IVaR | Portfolio | Effect of removing a position | `VaR − VaR_ex-i` | two VaR runs | currency | AH | MR·DH | — | [10 §6](10_Portfolio_Risk_Mathematics.md) |

---

## I. Risk Measures — `RM`

> **Category:** Risk measures · **Subcategory:** Statistical and scenario
> **Market data:** current levels · **Historical data:** **required** for HS and stress · **Position data:** full portfolio
> **Aggregation:** desk → business → entity → firm, with diversification
> **Regulatory use:** **ES 97.5% for IMA capital** (`MAR33.3`); VaR at 97.5% and 99% for **backtesting** (`MAR32.18`)
> **Validation:** backtesting; scenario completeness; sub-portfolio reconciliation; quantile convention documented; full revaluation for optioned books

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RM-01 | **Historical simulation VaR** | HS VaR | All | Loss quantile from observed history | rank revalued scenario P&L | history, positions | currency | EOD | MR·DH·SM | Backtesting | [11 §4](11_VaR.md) |
| RM-02 | **Parametric VaR** | variance-covariance VaR | Linear books | Loss quantile assuming normality | `z_α·σ_p·V` | Σ, weights | currency | EOD | MR | Benchmark | [11 §5](11_VaR.md) |
| RM-03 | **Monte Carlo VaR** | simulation VaR | Non-linear, exotic | Loss quantile by simulation | simulate + full reval | model, paths | currency | EOD | MR | — | [11 §6](11_VaR.md) |
| RM-04 | **Delta-normal VaR** | — | Linear books | Fast approximate VaR | `z_α√(δᵀΣδ)` | sensitivities, Σ | currency | ID | MR | — | [11 §5.6](11_VaR.md) |
| RM-05 | **Delta-gamma VaR** | — | Mildly non-linear | Second-order approximate VaR | Cornish-Fisher / partial sim | Δ, Γ, Σ | currency | EOD | MR | — | [11 §5.6](11_VaR.md) |
| RM-06 | **Historical ES** | CVaR, ETL, AVaR | All | **Average loss beyond VaR** | mean of worst `(1−α)N` | scenario P&L | currency | EOD | MR·CAP·SM | **IMA capital** | [12 §5](12_Expected_Shortfall.md) |
| RM-07 | **Parametric ES** | — | Linear books | ES assuming normality | `σ·φ(z_α)/(1−α)` | σ | currency | EOD | MR | Benchmark | [12 §6](12_Expected_Shortfall.md) |
| RM-08 | **Monte Carlo ES** | — | Non-linear | ES by simulation | mean of simulated tail | model, paths | currency | EOD | MR | — | [12 §7](12_Expected_Shortfall.md) |
| RM-09 | **Liquidity-adjusted ES** | FRTB ES | IMA desks | ES across nested liquidity horizons | `MAR33.4` nested formula | ES by subset, LHs | currency | **Daily** | CAP·MR·REG | **IMCC** | [12 §8.2](12_Expected_Shortfall.md) |
| RM-10 | **√T scaling** | time scaling | All | Extend a 1-day measure | `VaR₁·√h` | 1-day measure | currency | EOD | MR | **Prohibited for ES base horizon** | [11 §8](11_VaR.md) |
| RM-11 | **Stressed VaR/ES** | stress-calibrated measure | All | Measure on a stress window | HS on a stressed period | stress history | currency | EOD | MR·CAP | `MAR33.5` | [12 §8.3](12_Expected_Shortfall.md) |
| RM-12 | **Scenario P&L (full reval)** | — | All | Exact loss under a scenario | reprice under shock | shock vector | currency | EOD | MR·SM·REG | Stress, curvature | [13 §4](13_Stress_Testing.md) |
| RM-13 | **Scenario P&L (sensitivity)** | — | Linear books | Fast approximate scenario loss | `−Σ sᵢ·Δxᵢ` | sensitivities, shocks | currency | ID | TR·MR | Indicative only | [04 §7.2](04_Interest_Rate_Risk.md) |
| RM-14 | **Reverse stress** | — | All | **Scenario that produces a target loss** | min `xᵀΣ⁻¹x` s.t. loss = L* | Σ, sensitivities | shock vector + σ distance | Q–AH | MR·SM | Supervisory expectation | [13 §7](13_Stress_Testing.md) |
| RM-15 | **Spot × vol grid** | scenario matrix | Optioned books | Two-dimensional stress surface | reprice on a grid | grid definition | currency matrix | EOD | TR·DH·MR | — | [13 §6.2](13_Stress_Testing.md) |
| RM-16 | **Historical stress** | scenario replay | All | Replay a dated episode | extract + apply shock vector | dated history | currency | EOD–W | MR·SM·REG | `MAR30` | [13 §4](13_Stress_Testing.md) |
| RM-17 | **Supervisory stress** | GMS, EBA ST | Trading books | Prescribed regulatory scenario | apply published shocks | published vectors | currency | Annual | CAP·SM·REG | Fed GMS | [13 §8](13_Stress_Testing.md) |

---

## J. P&L and Attribution — `PL`

> **Category:** P&L · **Subcategory:** Measurement and explanation
> **Market data:** two consecutive snapshots · **Position data:** previous and current EOD · **Reference data:** trade activity, fees, reserves
> **Aggregation:** desk-level for regulatory purposes; some VAs only bank-wide (`MAR32.28`)
> **Regulatory use:** **APL and HPL for backtesting**; **HPL and RTPL for the PLA test**
> **Validation:** APL ties to the ledger; same pricing models (`MAR32.29`); exclusions per `MAR32.26`–`MAR32.27`; consistent time effects (`MAR32.28`)

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PL-01 | **Actual P&L** | APL | All | The booked daily P&L | ledger, fees excluded | books | currency | EOD | PC·MR·REG | **Backtesting** | [14 §2](14_PnL_and_PnL_Explain.md) |
| PL-02 | **Hypothetical P&L** | HPL, clean P&L | All | **Static book, today's market** | reprice prior EOD positions | positions t−1, market t | currency | EOD | PC·MR·REG | **Backtesting + PLA** | [14 §2.1](14_PnL_and_PnL_Explain.md) |
| PL-03 | **Risk-theoretical P&L** | RTPL | IMA desks | **What the risk model predicts** | risk model valuation engine | risk model factors only | currency | EOD | MR·MV·REG | **PLA candidate** | [14 §2.1](14_PnL_and_PnL_Explain.md) |
| PL-04 | **P&L attribution** | P&L explain | All | Decompose the day's P&L | sequential factor application | Greeks, market moves | currency by component | EOD | TR·DH·PC·MR | Control | [14 §3](14_PnL_and_PnL_Explain.md) |
| PL-05 | **Unexplained residual** | — | All | **What the decomposition misses** | `APL − Σ components` | attribution | currency, % of gross | EOD | PC·MR·MV | Model completeness | [14 §3.2](14_PnL_and_PnL_Explain.md) |
| PL-06 | **Realised P&L** | — | Closed positions | P&L crystallised on exit | exit vs entry | trades | currency | EOD | PC | — | [14 §2](14_PnL_and_PnL_Explain.md) |
| PL-07 | **Unrealised P&L** | MTM P&L | Open positions | P&L on open positions | current vs prior MV | valuations | currency | EOD | PC·MR | — | [14 §2](14_PnL_and_PnL_Explain.md) |

---

## K. Backtesting and Model Validation — `BT`

> **Category:** Validation · **Subcategory:** Model performance
> **Historical data:** 250 trading days of VaR, APL, HPL, RTPL
> **Aggregation:** **bank-wide and per trading desk** — both required
> **Regulatory use:** `MAR32` in full; drives the multiplier and desk IMA eligibility
> **Validation:** this *is* validation; independence per `MAR30.8` and SR 26-2 effective challenge

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BT-01 | **VaR exception count** | breach count, outliers | All | Count days loss exceeded VaR | compare vs **APL and HPL**; take the **greater** | VaR, APL, HPL | count | **Daily** | MR·MV·REG | `MAR32.5`, `MAR32.18` | [15 §4](15_Backtesting.md) |
| BT-02 | **Backtesting zone** | traffic light | Bank-wide | Map exceptions to a supervisory zone | `MAR32.9` Table 1 | exception count | zone | Daily | MR·CAP·REG | **Multiplier 1.50–2.00** | [15 §4.3](15_Backtesting.md) |
| BT-03 | **Backtesting multiplier** | `m_c` add-on | Bank-wide | Capital multiplier from performance | 1.5 + add-on (0–0.5) | zone | multiplier | Q | CAP·REG | `MAR33.42` | [18 §8.2](18_FRTB_Internal_Models_Approach.md) |
| BT-04 | **Desk exception test** | — | IMA desks | **Pass/fail for IMA eligibility** | >12 @99% or >30 @97.5% | desk exceptions | pass/fail | Daily, 12m window | MR·CAP·REG | `MAR32.19` | [15 §5](15_Backtesting.md) |
| BT-05 | **Kupiec POF test** | unconditional coverage | All | Is the exception *count* right? | LR test on binomial | exceptions, N, α | statistic | Q | MV | Supplementary | [15 §3.3](15_Backtesting.md) |
| BT-06 | **Christoffersen test** | independence test | All | Are exceptions **clustered**? | LR test on transitions | exception series | statistic | Q | MV | Supplementary | [15 §3.3](15_Backtesting.md) |
| BT-07 | **Spearman correlation (PLA)** | rank correlation | IMA desks | Does the model **rank** days correctly? | correlation of rank series | 250 RTPL, HPL | ∈[−1,1] | **Quarterly** | MR·MV·REG | **`MAR32.36`–`32.38`** | [15 §6.3](15_Backtesting.md) |
| BT-08 | **Kolmogorov-Smirnov (PLA)** | KS metric | IMA desks | Do the **distributions** match? | max \|ECDF_RTPL − ECDF_HPL\|, step 0.004 | 250 RTPL, HPL | ∈[0,1] | **Quarterly** | MR·MV·REG | **`MAR32.39`–`32.41`** | [15 §6.4](15_Backtesting.md) |
| BT-09 | **PLA zone** | green/amber/red | IMA desks | Model-to-portfolio fit verdict | ρ>0.80 **and** KS<0.09 → green | both metrics | zone | Quarterly | MR·CAP·REG | **`MAR32.42`** | [15 §6.6](15_Backtesting.md) |

---

## L. FRTB Capital — `FR`

> **Category:** Regulatory capital · **Subcategory:** Market risk
> **Market data:** curves, surfaces, spreads · **Position data:** all trading book positions · **Reference data:** issuer, rating, sector, market cap, economy, commodity bucket, listing/clearing status
> **Aggregation:** risk factor → bucket → risk class → **three correlation scenarios** → maximum
> **Regulatory use:** this **is** the regulatory use
> **Validation:** netting before weighting; floors at zero; `S_b` clamping fallback; all three scenarios; `RW·s` subtraction in curvature; simple sum of SBM + DRC + RRAO

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FR-01 | **Weighted sensitivity** | WS | Trading book | Risk-weight a net sensitivity | `WS_k = s_k · RW_k` | net sens., RW | currency | Daily calc | CAP | `MAR21.4(3)` | [17 §1](17_FRTB_Standardised_Approach.md) |
| FR-02 | **Within-bucket aggregation** | `K_b` | Trading book | Aggregate within a bucket | `√max(0, ΣWS²+ΣΣρWSWS)` | WS, ρ | currency | Daily | CAP | `MAR21.4(4)` | [17 §3.1](17_FRTB_Standardised_Approach.md) |
| FR-03 | **Across-bucket aggregation** | risk class charge | Trading book | Aggregate across buckets | `√(ΣK_b²+ΣΣγS_bS_c)` | `K_b`, `S_b`, γ | currency | Daily | CAP | `MAR21.4(5)` | [17 §3.2](17_FRTB_Standardised_Approach.md) |
| FR-04 | **`S_b` clamping fallback** | — | Trading book | Handle a negative aggregate | `max[min(ΣWS,K_b),−K_b]` | `ΣWS`, `K_b` | currency | Daily | CAP | `MAR21.4(5)(b)` | [17 §3.2](17_FRTB_Standardised_Approach.md) |
| FR-05 | **Curvature CVR** | — | Optioned positions | **Loss beyond delta** under prescribed shocks | `−Σ[V(x^RW±)−V(x)∓RW·s]` | pricer, RW, delta | currency | Daily | CAP·MR | `MAR21.5(2)` | [17 §3.3](17_FRTB_Standardised_Approach.md) |
| FR-06 | **Curvature aggregation** | — | Optioned positions | Aggregate CVR with the ψ function | ψ = 0 iff both negative | CVR, ρ, γ | currency | Daily | CAP | `MAR21.5(3)`–`(4)` | [17 §3.3](17_FRTB_Standardised_Approach.md) |
| FR-07 | **Correlation scenarios** | medium/high/low | Trading book | **Stress the correlation assumption** | ×1.25 capped; `max(2ρ−1,0.75ρ)` | ρ, γ | 3 results | Daily | CAP·MR | **`MAR21.6`–`21.7`** | [17 §4](17_FRTB_Standardised_Approach.md) |
| FR-08 | **DRC bucket charge** | — | Credit, equity | Default charge per bucket | `max(ΣRW·JTD_L − HBR·ΣRW·\|JTD_S\|, 0)` | net JTD, RW, HBR | currency | Daily | CAP | `MAR22.25` | [19 §6.5](19_Default_Risk_and_DRC.md) |
| FR-09 | **RRAO** | residual risk add-on | Exotics | Notional charge for residual risks | `Σ notional × 1.0% or 0.1%` | gross notional | currency | Daily | CAP | `MAR23.8` | [17 §9](17_FRTB_Standardised_Approach.md) |
| FR-10 | **SA total** | — | Trading book | **Simple sum**, no diversification | `SBM + DRC + RRAO` | three components | currency | **Monthly report** | CAP·REG | `MAR20.4` | [17](17_FRTB_Standardised_Approach.md) |
| FR-11 | **IMCC** | modellable capital | IMA desks | Weighted constrained/unconstrained ES | `ρ·IMCC(C)+(1−ρ)ΣIMCC(Cᵢ)`, **ρ = 0.5** | two ES runs | currency | Daily | CAP·REG | `MAR33.15` | [18 §5](18_FRTB_Internal_Models_Approach.md) |
| FR-12 | **SES** | NMRF capital | IMA desks | Stress capital for non-modellable factors | `MAR33.17`, **ρ = 0.6** | per-NMRF stress | currency | Daily | CAP·REG | `MAR33.17` | [20 §7.5](20_NMRF_and_Modellability.md) |
| FR-13 | **RFET** | risk factor eligibility test | IMA desks | **Is a factor modellable?** | 24/year with no 90-day gap <4, **or** 100/year | real price observations | pass/fail | **Quarterly** (monthly monitoring) | MR·CAP·REG | `MAR31.13` | [20 §3](20_NMRF_and_Modellability.md) |
| FR-14 | **IMA capital aggregation** | `C_A` | IMA desks | Combine latest and 60-day average | `max(IMCC+SES, m_c·avg60+avg60)` | IMCC, SES, `m_c` | currency | Daily | CAP·REG | `MAR33.41` | [18 §8](18_FRTB_Internal_Models_Approach.md) |
| FR-15 | **DRC under IMA** | — | IMA desks | Default risk by simulation | VaR, **99.9%, 1yr, weekly** | PDs, correlations | currency | **Weekly** | CAP·REG | `MAR33.20` | [19 §10](19_Default_Risk_and_DRC.md) |
| FR-16 | **RWA conversion** | — | Trading book | Capital → RWA | `capital × 12.5` | capital | currency | Monthly | CAP·REG | `MAR20.1`, `MAR33.46` | [16 §2.2](16_FRTB_Overview.md) |
| FR-17 | **10% IMA floor** | — | Firm | Anti-cherry-picking eligibility test | IMA-qualifying share ≥ 10% | capital by desk | ratio | **Quarterly** | CAP·REG | `MAR32.2` | [18 §2.2](18_FRTB_Internal_Models_Approach.md) |

---

## M. Counterparty and XVA — `XV`

> **Category:** Adjacent · **Subcategory:** Counterparty and valuation adjustment
> **Market data:** curves, surfaces, credit spreads · **Position data:** netting sets · **Reference data:** CSAs, netting agreements, legal opinions
> **Aggregation:** **netting set**, then counterparty, then firm
> **Regulatory use:** **`MAR50`** for CVA risk; `CRE52` for CCR — **not** trading-book market risk
> **Validation:** netting enforceability; MPOR appropriateness; profile shape; CVA reconciles front office to risk

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XV-01 | **Current exposure** | CE, replacement cost | Derivatives | Loss if they default now | `max(Σ MTM − collateral, 0)` | MTMs, collateral | currency | Daily | MR·CAP | SA-CCR input | [22 §3](22_Counterparty_CVA_and_SIMM.md) |
| XV-02 | **Expected exposure** | EE | Derivatives | Expected positive exposure at *t* | mean of simulated `max(V,0)` | simulation | currency | Daily | MR | CVA input | [22 §3](22_Counterparty_CVA_and_SIMM.md) |
| XV-03 | **EPE / EEPE** | effective EPE | Derivatives | Time-weighted average exposure | average of EE, non-decreasing floor | EE profile | currency | Daily | MR·CAP | `CRE52` | [22 §3](22_Counterparty_CVA_and_SIMM.md) |
| XV-04 | **PFE** | potential future exposure | Derivatives | High percentile of exposure | percentile of simulated exposure | simulation | currency | Daily | MR·DH | Limits | [22 §3](22_Counterparty_CVA_and_SIMM.md) |
| XV-05 | **Netting benefit** | — | Derivatives | Value of an enforceable netting set | `Σmax(V,0) − max(ΣV,0)` | MTMs | currency | Daily | MR·CAP | Requires legal opinion | [22 §4.1](22_Counterparty_CVA_and_SIMM.md) |
| XV-06 | **CVA** | credit valuation adjustment | Derivatives | **Market value of counterparty default risk** | `LGD·Σ EE·ΔPD·DF` | EE, credit curve, R | currency | Daily | PC·MR·CAP | **`MAR50`** | [22 §5](22_Counterparty_CVA_and_SIMM.md) |
| XV-07 | **DVA** | debit valuation adjustment | Derivatives | Own-default adjustment | mirror of CVA | own spread | currency | Daily | PC | **Excluded from APL/HPL** | [22 §5.2](22_Counterparty_CVA_and_SIMM.md) |
| XV-08 | **FVA / MVA / ColVA** | funding adjustments | Derivatives | Funding cost adjustments | funding spread × exposure | funding curve | currency | Daily | PC·TRS | Not separately capitalised | [22 §5.2](22_Counterparty_CVA_and_SIMM.md) |
| XV-09 | **SA-CCR EAD** | — | Derivatives | Regulatory exposure at default | `alpha × (RC + PFE)` | RC, add-ons, multiplier | currency | Daily | CAP·REG | `CRE52` | [22 §7](22_Counterparty_CVA_and_SIMM.md) |
| XV-10 | **ISDA SIMM margin** | initial margin | Non-cleared derivatives | Initial margin per netting set | delta + vega + curvature + base corr., with concentration | sensitivities | currency | Daily | TRS·MR | **Not capital** | [22 §8](22_Counterparty_CVA_and_SIMM.md) |

---

## N. Limits and Aggregation — `LM`

> **Category:** Control · **Subcategory:** Limits and roll-up
> **Position data:** all · **Reference data:** limit definitions, hierarchy
> **Aggregation:** the mechanism itself
> **Regulatory use:** governance expectations under `MAR30` and BCBS 239; limit structures are **not** prescribed
> **Validation:** coherence between sensitivity and stress limits; parent/child buffer; every level monitored independently

| ID | Calculation | Alt names | Instruments | Purpose | Formula / method | Key inputs | Output · units | Freq | Users | FRTB | Doc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LM-01 | **Limit utilisation** | — | All | Position vs appetite | `measure / limit` | measure, limit | % | RT–EOD | TR·DH·MR·SM | Governance | [21 §9](21_Market_Risk_Limits.md) |
| LM-02 | **Pre-trade limit check** | what-if check | All | **Would this trade breach?** | recompute on hypothetical book | proposed trade | allow/deny | RT | TR·MR | Preventive control | [21 §10](21_Market_Risk_Limits.md) |
| LM-03 | **Breach classification** | — | All | Active vs passive vs technical | compare position and market change | prior/current state | category | EOD | MR·SM | Control quality | [21 §8.2](21_Market_Risk_Limits.md) |
| LM-04 | **Correlation aggregation** | — | Portfolio | Roll up with diversification | `√(Σx²+ΣΣρxy)` | measures, ρ | currency | EOD | MR·SM | IMCC analogue | [42](42_Risk_Aggregation.md) |
| LM-05 | **Simple-sum aggregation** | no-offset roll-up | Portfolio | Roll up with no diversification | `Σ` | measures | currency | EOD | MR·CAP | **SBM+DRC+RRAO**, DRC buckets | [42](42_Risk_Aggregation.md) |
| LM-06 | **Concentration measure** | — | All | Position vs market capacity | position / ADV; top-N share | position, volumes | ratio, days | EOD | MR·SM | LH, SIMM concentration | [21 §5.3](21_Market_Risk_Limits.md) |

---

## Catalogue summary

| Category | Code | Entries |
|---|---|---|
| Pricing and valuation | `PV` | 32 |
| Interest rate sensitivities | `IR` | 22 |
| Credit spread and default | `CR` | 11 |
| Foreign exchange | `FX` | 8 |
| Equity | `EQ` | 10 |
| Commodity | `CM` | 5 |
| Options and Greeks | `GK` | 12 |
| Portfolio statistics | `PS` | 14 |
| Risk measures | `RM` | 17 |
| P&L and attribution | `PL` | 7 |
| Backtesting and validation | `BT` | 9 |
| FRTB capital | `FR` | 17 |
| Counterparty and XVA | `XV` | 10 |
| Limits and aggregation | `LM` | 6 |
| **TOTAL** | | **180** |

---

## Notes on completeness

- **This catalogue covers the calculations a market risk function performs or consumes.** It deliberately includes adjacent calculations (`XV`) marked as adjacent, because derivative portfolios link them — but it does **not** reclassify counterparty or CVA risk as market risk ([41](41_Market_Risk_vs_Related_Risk_Types.md)).
- **Banking-book calculations (IRRBB EVE/NII) are excluded** and treated separately in [20A](20A_Trading_Book_Boundary_and_IRRBB.md), because they belong to a different framework.
- **Some entries are conventions rather than calculations** (PV-10 quoting-basis conversion, PV-21 put-call parity). They are included because getting them wrong produces wrong numbers everywhere downstream.
- **Vendor-specific and institution-specific metrics are excluded.** Where a term is used inconsistently across the industry — DV01 / PV01 / BPV being the clearest case — the entries are listed separately with the ambiguity flagged ([04 §14.2](04_Interest_Rate_Risk.md)).

---

## Related Concepts

- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md) — the mathematics, organised basic → advanced
- [33 — Master Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md) — what each calculation is a function of
- [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md) — what must be computed before what
- [38 — Question-to-Calculation Catalog](38_Question_to_Calculation_Catalog.md) — which calculation answers which question
- [34 — Glossary](34_Glossary.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | Every `MAR` citation in the FRTB, backtesting, DRC and NMRF rows |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | `MAR50` (CVA), `CRE52` (SA-CCR), `SRP31` (IRRBB) |
| ISDA | ISDA SIMM Methodology v2.8+2512 | 12 Jun 2026 | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ | XV-10 |
| Artzner, Delbaen, Eber, Heath | *Coherent Measures of Risk* | 1999 | — | RM-06 coherence properties |

*Accessed 25 August 2026.*
