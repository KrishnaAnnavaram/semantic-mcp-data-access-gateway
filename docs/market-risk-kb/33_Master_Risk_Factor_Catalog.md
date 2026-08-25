# 33 — Master Risk Factor Catalog

**Level:** Reference · **Companion to:** [31 — Calculation Catalog](31_Master_Calculation_Catalog.md), [37 — Dependency Graph](37_Calculation_Dependency_Graph.md)

> **A risk factor is a market observable whose movement changes the value of a position.** It is the atom of market risk measurement: instruments are mapped to factors, factors are shocked, positions are revalued. Everything in this library is ultimately a function of the objects catalogued here.

---

## How to read the columns

| Column | Meaning |
|---|---|
| **Risk factor** | The modelled observable |
| **Class** | FRTB SBM risk class: GIRR · CSR · EQ · FX · CM |
| **Market data** | What must be sourced and validated |
| **Sensitivity** | The calculation that measures exposure to it |
| **Shock convention** | **ABS** = absolute (bp) · **REL** = relative (%) |
| **LH** | FRTB IMA liquidity horizon in days (`MAR33.12` Table 2) |
| **Instruments** | What loads onto it |

**The shock convention column is not decoration.** Applying relative shocks to rates or spreads breaks at zero and cannot represent negative values — one of the standard ways to produce a VaR model that reports nonsense ([11 §4.4](11_VaR.md)).

---

## 1. Interest rate factors — GIRR

| Risk factor | Class | Market data | Sensitivity | Shock | LH | Instruments |
|---|---|---|---|---|---|---|
| **Risk-free zero rate, 0.25y** | GIRR | OIS/RFR curve | DV01, KRD01 | **ABS** | 10 / 20 | All dated cash flows |
| **Risk-free zero rate, 0.5y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 1y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 2y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 3y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 5y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 10y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 15y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 20y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Risk-free zero rate, 30y** | GIRR | OIS/RFR curve | KRD01 | ABS | 10 / 20 | " |
| **Projection curve (per index/tenor)** | GIRR | Basis swaps vs RFR | Basis DV01 | ABS | 10 / 20 | Floating legs, FRNs, FRAs |
| **Tenor basis (1M vs 3M vs 6M)** | GIRR | Basis swap spreads | Basis DV01 | ABS | 10 / 20 | Basis swaps |
| **Cross-currency basis** | GIRR | XCCY basis swaps | XCCY DV01 | ABS | 10 / 20 | XCCY swaps, FX forwards, foreign CSAs |
| **Inflation curve** | GIRR | Inflation swaps, linker breakevens | Inflation DV01 | ABS | 10 / 20 | Linkers, inflation swaps |
| **Repo / financing rate** | GIRR | Repo market, GC and specials | Repo DV01 | ABS | 10 / 20 | Repo, financed cash bonds |
| **Swaption volatility (expiry × tenor × strike)** | GIRR | Swaption vol cube | Vega, volga, vanna | REL or ABS | **60** | Swaptions, callables, structured notes |
| **Cap/floor volatility** | GIRR | Caplet vol surface | Vega | REL or ABS | **60** | Caps, floors |

**Key regulatory parameters** (`MAR21.42`–`MAR21.50`):

- Delta risk weights by vertex: **1.7%, 1.7%, 1.6%, 1.3%, 1.2%, 1.1%, 1.1%, 1.1%, 1.1%, 1.1%**
- Inflation and cross-currency basis: **1.6%**
- √2 discount available for **EUR, USD, GBP, AUD, JPY, SEK, CAD** plus the reporting currency
- Same tenor, different curves: **ρ = 99.90%**
- Cross-tenor: `ρ = max(e^(−0.03·|T_k−T_l|/min(T_k,T_l)), 40%)`
- **Cross-currency basis vs anything else: ρ = 0%** — no offset whatsoever
- Across currencies: **γ = 50%**
- LH is **10 days for specified currencies** (EUR, USD, GBP, AUD, JPY, SEK, CAD, domestic), **20 otherwise**; **60 for rate volatility and other types**

---

## 2. Credit spread factors — CSR

| Risk factor | Class | Market data | Sensitivity | Shock | LH | Instruments |
|---|---|---|---|---|---|---|
| **Issuer spread, 0.5y** | CSR | CDS + bond spread curves | CS01 | **ABS** | 20–120 | Bonds, CDS, credit options |
| **Issuer spread, 1y** | CSR | " | CS01 | ABS | 20–120 | " |
| **Issuer spread, 3y** | CSR | " | CS01 | ABS | 20–120 | " |
| **Issuer spread, 5y** | CSR | " | CS01 | ABS | 20–120 | " |
| **Issuer spread, 10y** | CSR | " | CS01 | ABS | 20–120 | " |
| **Sector/rating proxy spread** | CSR | Sector index curves | Proxy CS01 | ABS | 20–120 | Issuers without liquid CDS |
| **Index spread (CDX, iTraxx)** | CSR | Index quotes | Index CS01 | ABS | 40–60 | Index CDS, tranches |
| **Index skew** | CSR | Index vs constituents | Skew sensitivity | ABS | 40–60 | Index vs single-name books |
| **CDS-bond basis** | CSR | Both curves | Basis CS01 | ABS | 40–60 | Basis packages |
| **Sovereign spread** | CSR | Sovereign CDS, bond spreads | CS01 | ABS | **20** (IG) / **40** (HY) | Sovereign bonds, CDS |
| **Securitisation tranche spread** | CSR (sec) | Tranche quotes | CS01 | ABS | 20–120 | ABS, MBS, CLO tranches |
| **Base correlation** | CSR (CTP) | Tranche-implied correlation | Correlation sensitivity | REL | 120 | Index tranches |
| **Credit spread volatility** | CSR | Credit option vols | Vega | REL | **120** | Credit options |
| **Recovery rate assumption** | CSR / DRC | Market convention, auctions | Recovery sensitivity | ABS | — | CDS, bonds |
| **Obligor default event** | **DRC** | Not a price series | **JTD** | Event | 1 year (IMA) | Bonds, CDS, equity derivatives |

**Key parameters:** delta vertices **0.5, 1, 3, 5, 10y** (`MAR21.9`); 18 buckets by credit quality × sector; risk weights **0.5%–12.0%**; intra-bucket `ρ = ρ(name) × ρ(tenor) × ρ(basis)` = **35% × 65% × 99.90%** for different name/tenor/curve; **bucket 16 has no offsetting at all**; DRC risk weights **0.5% (AAA) → 100% (defaulted)**, unrated **15%**.

> **Note the last row.** *Default* is a risk factor in the taxonomy but has **no price series** — it is an event, not an observable. It cannot be bumped into existence, which is exactly why the DRC is a separate charge ([19 §3](19_Default_Risk_and_DRC.md)).

---

## 3. Equity factors — EQ

| Risk factor | Class | Market data | Sensitivity | Shock | LH | Instruments |
|---|---|---|---|---|---|---|
| **Single-name spot price** | EQ | Exchange prices | Delta | **REL** | **10** (large cap) / **20** (small) | Cash equity, options, swaps |
| **Index level** | EQ | Index quotes | Index delta, beta-adj. | REL | **10** | Index futures/options, ETFs |
| **Sector index** | EQ | Sector indices | Sector delta | REL | 10–20 | Sector products |
| **Equity repo rate** | EQ | Stock borrow market | Repo sensitivity | **ABS** | 10–60 | Shorts, swaps, options |
| **Dividend forecast / dividend future** | EQ | Dividend futures, forecasts | Dividend delta | REL | 10–60 | Forwards, futures, options, swaps |
| **Implied volatility (strike × expiry)** | EQ | Option markets | Vega, vanna, volga | REL | **20** (large cap) / **60** (small) | Equity options |
| **Volatility skew** | EQ | 25Δ put/call vols | Skew sensitivity | REL | 20–60 | Options, structured products |
| **Implied correlation** | EQ | Index vs constituent vols | Correlation sensitivity | REL | 60 | Baskets, dispersion, autocallables |
| **Equity: other types** | EQ | Various | Various | REL | **60** | Non-standard equity exposures |

**Key parameters:** 13 buckets by **market cap × economy × sector**; large cap = **≥ USD 2bn** for the **single listed entity across all markets** (`MAR21.74`); advanced economies per the `MAR21.75` exhaustive list; spot risk weights **15%–70%**; **repo risk weight = spot risk weight ÷ 100**; same-issuer spot↔repo `ρ = 99.90%`. **No vega and no curvature charge on equity repo rates.**

---

## 4. Foreign exchange factors — FX

| Risk factor | Class | Market data | Sensitivity | Shock | LH | Instruments |
|---|---|---|---|---|---|---|
| **Spot rate vs reporting currency** | FX | Spot market | FX delta, NOP | **REL** | **10** (specified pairs) / **20** | Everything non-domestic |
| **Forward points** | FX + GIRR | Forward market | Forward delta + 2 DV01s | REL/ABS | 10–20 | Forwards, swaps, NDFs |
| **Onshore/offshore basis (e.g. CNY/CNH)** | FX | Both markets | Basis sensitivity | REL | 20 | NDFs, restricted currencies |
| **NDF fixing** | FX | Published fixings | Fixing exposure | REL | 20 | NDFs |
| **FX implied volatility (delta × expiry)** | FX | ATM, RR, BF quotes | Vega, vanna, volga | REL | **40** | FX options |
| **Risk reversal (skew)** | FX | 25Δ RR quotes | Skew / vanna | REL | 40 | FX options |
| **Butterfly (smile)** | FX | 25Δ BF quotes | Smile / volga | REL | 40 | FX options |
| **FX: other types** | FX | Various | Various | REL | **40** | Non-standard FX exposures |

**Key parameters:** risk factors are **all rates between the currency of denomination and the reporting currency** (`MAR21.14`); **a unique 15% risk weight applies to all FX sensitivities** (`MAR21.87`), divisible by √2 for a specified pair list and its first-order crosses; cross-bucket **γ = 60%**.

> ⚠ **The specified-pair list for the SBM √2 discount (`MAR21.88`) and the list for the 10-day liquidity horizon (`MAR33.12` fn 1) are NOT identical.** The liquidity-horizon list additionally includes **EUR/JPY, EUR/GBP, EUR/CHF and JPY/AUD**. Using one list for the other is a real and easily-made error.

---

## 5. Commodity factors — CM

| Risk factor | Class | Market data | Sensitivity | Shock | LH | Instruments |
|---|---|---|---|---|---|---|
| **Front-month futures price** | CM | Exchange settlements | Commodity delta | **REL** | 20–60 | Futures, swaps, options |
| **Futures price by delivery month** | CM | Full curve | Calendar sensitivity | REL | 20–60 | Calendar spreads |
| **Location differential** | CM | Hub prices, basis swaps | Location basis delta | REL | 20–60 | Physical, basis swaps |
| **Grade / quality differential** | CM | Grade-specific quotes | Grade basis delta | REL | 20–60 | Physical, quality swaps |
| **Energy & carbon price** | CM | Exchange, PRAs | Delta | REL | **20** | Crude, refined, gas, power, allowances |
| **Precious & non-ferrous metals price** | CM | LME, exchanges | Delta | REL | **20** | Metals futures, forwards |
| **Other commodities price** | CM | Exchanges, PRAs | Delta | REL | **60** | Agriculture, freight, softs |
| **Energy & carbon volatility** | CM | Option markets | Vega | REL | **60** | Energy options |
| **Metals volatility** | CM | Option markets | Vega | REL | **60** | Metals options |
| **Other commodities volatility** | CM | Option markets | Vega | REL | **120** | Ags, freight options |
| **Commodity: other types** | CM | Various | Various | REL | **120** | Non-standard commodity exposures |
| **Convenience yield (implied)** | CM | Residual of cost-of-carry | Curve sensitivity | REL | 20–60 | Physical, storage plays |

**Key parameters:** 11 buckets; risk weights **30%, 35%, 60%, 80% (freight — highest), 40%, 45%, 20% (precious metals — lowest), 35%, 25%, 35%, 50%**; intra-bucket `ρ = ρ(commodity) × 99.00% (tenor) × 99.90% (location)`. **For bucket 3, each electricity delivery time interval is a distinct commodity** (`MAR21.84`) — peak and off-peak do not net.

---

## 6. Cross-cutting factors

| Risk factor | Class | Market data | Sensitivity | Shock | Instruments |
|---|---|---|---|---|---|
| **Time (theta)** | — | Calendar | Theta | Deterministic | All optioned positions |
| **Correlation (multi-underlying)** | RRAO | Implied from baskets | Correlation sensitivity | REL | Baskets, best-of, spread, quanto, Bermudan |
| **Barrier proximity** | RRAO | Spot vs barrier | Discontinuous Δ, Γ | — | Barriers, digitals, Asians |
| **Prepayment speed** | GIRR / CSR | Model output from rates, burnout | Effective duration | Model-driven | MBS, callables |
| **Behavioural exercise** | RRAO | Model output | Effective duration | Model-driven | Retail-callable products |
| **Bid-offer / liquidity** | — | Quote spreads | Reserve, LH | — | All, especially illiquid |
| **Concentration** | — | Position vs ADV | Days-to-liquidate | — | Any large position |

> **Time is a risk factor in the P&L sense and not in the VaR sense.** It moves with certainty, so it belongs in attribution ([14 §4.2](14_PnL_and_PnL_Explain.md)) and is deliberately excluded from VaR — forecasting a known quantity is not risk measurement.

---

## 7. Modellability — the factors that typically fail

`MAR31.13` requires either **24 real price observations per year with no 90-day gap below 4**, or **100 observations over 12 months**. The factors that commonly fail, and why:

| Factor type | Typical failure mode |
|---|---|
| **Long-end points in minor currencies** | Genuine illiquidity — few or no trades at 30y+ |
| **Issuer-specific idiosyncratic spread** | Most issuers have no liquid CDS; only a *systematic* proxy passes (`MAR31.20`) |
| **Far-wing volatility (deep OTM strikes)** | Quoted but rarely traded; indicative quotes do not count |
| **Long-dated volatility** | Thin market beyond a few years |
| **Exotic correlation parameters** | No observable market at all |
| **Emerging-market curve points** | Sparse and episodic trading |
| **Location and grade basis in commodities** | Physical differentials with few financial trades |
| **Onshore/offshore basis in restricted currencies** | Limited observable market |
| **Base correlation** | Tranche market liquidity varies sharply by attachment point |

**The rule that closes the escape route** (`MAR31.13` fn 3): a non-modellable factor decomposed into a modellable proxy plus a basis leaves the **basis** non-modellable. *"A combination between modellable and non-modellable risk factors will be a non-modellable risk factor."* **Contamination flows in one direction only.**

Consequences: **SES capital**, with a liquidity horizon of **max(Table 2 horizon, 20 days)**, aggregated at **ρ = 0.6** rather than with full diversification ([20](20_NMRF_and_Modellability.md)).

---

## 8. Factor counts

Indicative scale for a large dealer bank. **These are illustrative orders of magnitude, not a survey.**

| Class | Typical factor count | Driver of the count |
|---|---|---|
| GIRR | Thousands | currencies × curves × vertices, plus vol cubes |
| CSR | Tens of thousands | issuers × 5 vertices × curve types |
| Equity | Thousands to tens of thousands | names × spot/repo/dividend, plus surfaces |
| FX | Hundreds | pairs × (spot + vol surface points) |
| Commodity | Thousands | commodities × months × locations, plus surfaces |
| **Total** | **Tens of thousands** | |

> **The dimensionality is the reason factors exist as an abstraction at all.** A bank may hold hundreds of thousands of distinct instruments and be exposed to a far smaller set of factors — and a long, clean history exists for a factor where none exists for a swap traded yesterday ([01 §5.1](01_Market_Risk_Fundamentals.md)).

---

## 9. Mapping instruments to factors

| Instrument | Factors it loads onto |
|---|---|
| **Government bond** | Risk-free zero rates (all vertices to maturity); repo/specialness; sovereign spread and FX if foreign |
| **Corporate bond** | Risk-free zero rates **+ issuer spread curve** (+ FX if foreign) |
| **FRN** | Zero rate **to next reset only** + **full issuer spread curve** |
| **Interest rate swap** | Discount curve + projection curve (+ XCCY basis if a foreign CSA) |
| **Swaption** | Rate curves + **swaption vol cube** |
| **FX forward** | Spot + **both** rate curves (+ XCCY basis) |
| **FX option** | Spot + both rate curves + **FX vol surface** |
| **Cash equity** | Spot + borrow rate (+ FX) |
| **Equity option** | Spot + **vol surface** + dividend + rate + borrow |
| **CDS** | Issuer spread curve + risk-free curve + **recovery** + **default event (JTD)** |
| **Index CDS** | Index spread + **constituent spreads (look-through)** + skew |
| **Commodity future** | Price for that delivery month + location + grade |
| **Convertible bond** | Rates + **issuer spread** + **equity spot** + **equity vol** + **cross-gammas** |
| **MBS** | Rates + **prepayment model** + OAS (+ credit for non-agency) |
| **Autocallable** | Spot + vol + skew + **correlation** + rates + issuer funding spread |

> **The mapping is where a great deal of real-world risk error lives.** An issuer with no liquid CDS is mapped to a sector-and-rating proxy — and that proxy, by construction, contains **no idiosyncratic risk**. If the issuer blows up on its own news, the risk system will have shown almost nothing ([01 §5.2](01_Market_Risk_Fundamentals.md), [05 §13](05_Credit_Spread_Risk.md)).

---

## 10. Factor governance checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Every material factor is defined** | With a stable identifier and a documented meaning |
| 2 | **Shock convention correct** | ABS for rates and spreads; REL for prices |
| 3 | **Negative values supported** | Rates and some commodity prices can be below zero |
| 4 | **Mapping documented** | Every instrument → factor path recorded |
| 5 | **Proxies flagged** | Proxied factors visible in reporting, with the residual identified |
| 6 | **Idiosyncratic residual** | Treated as an NMRF unless the issuer itself passes the RFET |
| 7 | **Regulatory vertices** | GIRR at ten vertices; CSR at five |
| 8 | **Bucket assignment** | Every factor mapped to an SBM bucket |
| 9 | **Liquidity horizon assigned** | From `MAR33.12` Table 2; documented, validated, **audited** |
| 10 | **FX lists distinguished** | SBM `MAR21.88` list ≠ liquidity-horizon `MAR33.12` list |
| 11 | **RFET evidence** | Real price observations captured and tagged **to the factor** |
| 12 | **Derived factors classified** | Any combination touching an NMRF is non-modellable |
| 13 | **Volatility surfaces modelled in two dimensions** | Strike **and** tenor (`MAR33.12`) |
| 14 | **Electricity granularity** | Delivery intervals as distinct commodities |
| 15 | **Factor set reconciles to RTPL** | The PLA test uses only the risk model's factors (`MAR32.22(2)`) |

---

## 11. Limitations

- **Factor counts in §8 are illustrative**, not surveyed. Actual counts vary by an order of magnitude between institutions with similar balance sheets, driven mainly by how finely the credit and volatility surfaces are decomposed.
- **Liquidity horizons in the tables show the range** where a category spans several values; the precise assignment is per `MAR33.12` Table 2 and is reproduced in full at [18 §4.3](18_FRTB_Internal_Models_Approach.md).
- **The instrument→factor mapping in §9 is the typical case.** Structured and bespoke products routinely load onto factors not listed, and identifying them is a new-product-approval activity ([27 §10.1](27_Controls_and_Governance.md)).
- **Some factors in §6 have no market data at all** — barrier proximity, behavioural exercise, concentration. They are real exposures managed through the RRAO, reserves and limits rather than through simulation.

---

## 12. Related Concepts

- [01A — Master Market Risk Taxonomy](01A_Master_Market_Risk_Taxonomy.md) — how these factors classify
- [31 — Master Calculation Catalog](31_Master_Calculation_Catalog.md) — what is computed from them
- [20 — NMRF and Modellability](20_NMRF_and_Modellability.md) — when a factor cannot be modelled
- [23 — Market Data and Curves](23_Market_Data_and_Curves.md) — where the data comes from

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.8`–`MAR21.14` risk factor definitions; `MAR21.42`–`MAR21.101` weights and correlations; `MAR31.13`, `MAR31.20`; `MAR33.12` liquidity horizons |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR21/MAR31/MAR33 text |

*Accessed 25 August 2026.*
