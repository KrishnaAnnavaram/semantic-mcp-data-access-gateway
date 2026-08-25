# 01A — The Master Market-Risk Taxonomy

**Level:** 1 (Foundation) · **Prerequisites:** [01 — Market Risk Fundamentals](01_Market_Risk_Fundamentals.md)

---

## 1. There is no single official count of market-risk categories

This must be said first, because a great deal of confusion follows from assuming otherwise.

Ask four sources how many kinds of market risk there are and you get four answers, because **they are classifying for four different purposes**:

| Source | Classifies by | Result |
|---|---|---|
| **Basel FRTB, Standardised Approach** | What must be capitalised, in what bucket, at what risk weight | **7 SBM risk classes** + DRC + RRAO |
| **Basel FRTB, Internal Models Approach** | Which empirical correlations may be recognised | **5 broad regulatory risk classes** |
| **A bank's internal risk framework** | Who manages it and against what limit | Typically 5–8 asset-class pillars plus a set of cross-cutting risks |
| **Quantitative finance literature** | The mathematical character of the exposure | Linear vs non-linear; diffusive vs jump; first-order vs higher-order |

None is wrong. A taxonomy is a tool, and the right tool depends on the job. What matters is that **you always know which taxonomy you are speaking in**, because the same position is classified differently under each.

### 1.1 The authoritative regulatory counts

Two counts *are* fixed by the Basel text and should never be paraphrased loosely:

**Seven risk classes** under the sensitivities-based method (`MAR21.39`–`MAR21.89`):

1. General Interest Rate Risk (**GIRR**)
2. Credit Spread Risk: **non-securitisations** (CSR non-sec)
3. Credit Spread Risk: **securitisations — correlation trading portfolio** (CSR sec CTP)
4. Credit Spread Risk: **securitisations — non-CTP** (CSR sec non-CTP)
5. **Equity** risk
6. **Commodity** risk
7. **Foreign exchange** (FX) risk

Each of the seven is charged for **delta**, **vega** and **curvature**, which is why the SBM is sometimes loosely described as having "21 components."

**Five broad regulatory risk classes** under the IMA, for the purpose of the constrained-correlation expected shortfall calculation (`MAR33.14`):

interest rate risk · equity risk · foreign exchange risk · commodity risk · credit spread risk

> Note the asymmetry: the SA splits credit spread risk three ways and treats FX as its own class; the IMA collapses credit spread into one and uses five. **Neither list includes "volatility risk" or "correlation risk" as top-level classes** — volatility is captured as vega *within* each class, and correlation risk is largely pushed into the RRAO. Practitioners who speak of "volatility risk" as a separate category are using the internal taxonomy, not the regulatory one.

---

## 2. The structural taxonomy used in this knowledge base

We use a three-level scheme. Level 1 is the **driver** (what kind of market variable moved). Level 2 is the **mode** (how it moved). Level 3 is the **specific exposure**.

```
LEVEL 1 — DRIVER                LEVEL 2 — MODE                LEVEL 3 — EXPOSURE
─────────────────────────────────────────────────────────────────────────────────
Interest rate           ┬─ Level (parallel)            ── outright duration
                        ├─ Slope                        ── steepener / flattener
                        ├─ Curvature                    ── butterfly
                        ├─ Tenor / key rate             ── bucketed KRD
                        ├─ Basis                        ── SOFR vs Treasury, tenor basis
                        ├─ Cross-currency basis         ── XCCY basis
                        ├─ Inflation / real rate        ── breakeven
                        └─ Rate volatility              ── swaption vega, cap/floor vega

Credit spread           ┬─ Level                        ── outright CS01
                        ├─ Curve                        ── bucketed CS01
                        ├─ Issuer / idiosyncratic       ── single-name CS01
                        ├─ Sector / systematic          ── index CS01
                        ├─ Basis                        ── CDS-bond basis, index skew
                        └─ Spread volatility            ── credit option vega

Equity                  ┬─ Price (index)                ── beta-adjusted exposure
                        ├─ Price (single name)          ── idiosyncratic delta
                        ├─ Sector                       ── sector delta
                        ├─ Dividend                     ── dividend delta / rho_q
                        ├─ Repo / borrow                ── equity repo rate risk
                        ├─ Volatility                   ── vega, skew, term structure
                        └─ Correlation                  ── dispersion, basket correlation

Foreign exchange        ┬─ Spot                         ── net open position
                        ├─ Forward / points            ── FX forward, IR parity
                        ├─ FX basis                     ── XCCY basis spread
                        ├─ Volatility                   ── FX option vega, RR, BF
                        └─ Concentration                ── single-currency limit

Commodity               ┬─ Spot / front price           ── outright delta
                        ├─ Futures curve                ── calendar spread
                        ├─ Location basis               ── WTI vs Brent, hub differentials
                        ├─ Grade / quality basis        ── sulphur, density spreads
                        └─ Volatility                   ── commodity option vega

Cross-cutting           ┬─ Default / jump-to-default    ── JTD, DRC
                        ├─ Gap / jump                   ── overnight gap, digital cliff
                        ├─ Correlation                  ── multi-underlying products
                        ├─ Basis (generic)              ── any imperfect hedge
                        ├─ Concentration                ── position vs market depth
                        ├─ Liquidity-adjusted           ── liquidity horizons, bid-offer
                        ├─ Residual / exotic            ── RRAO population
                        └─ Non-modellable               ── NMRF, SES
```

---

## 3. The categories in detail

Each subsection follows the same ten-field record.

---

### 3.1 General Interest Rate Risk (GIRR)

**Definition.** The risk of loss from changes in risk-free interest rates — the level, shape and volatility of the curve used to discount and project cash flows, excluding any issuer-specific credit component.

**Plain-English example.** A bank holds a 10-year government bond. The market's required 10-year yield rises 10bp. The bond falls about 0.85% in price. Nothing about the issuer changed.

**Instruments exposed.** Government bonds, corporate bonds (jointly with CSR), interest-rate swaps, OIS, FRAs, bond and rate futures, swaptions, caps/floors, cross-currency swaps, FX forwards (through the interest-rate parity legs), essentially every dated cash flow the bank holds.

**Market data involved.** Deposit and OIS fixings, futures prices, par swap rates, government bond yields, basis swap spreads, inflation swap rates, swaption volatility cubes.

**Calculations used.** PV; DV01/PV01/BPV; modified, effective and Macaulay duration; key-rate DV01; convexity; carry and roll-down; forward rates; scenario P&L; VaR; ES.

**Sensitivities used.** Bucketed DV01 at the regulatory vertices; inflation and cross-currency basis deltas; swaption vega by expiry/tenor.

**Stress scenarios.** Parallel ±100/200/300bp; steepener and flattener; butterfly; 1994 bond massacre; 2013 taper tantrum; 2022 rate shock; 2022 UK gilt/LDI episode.

**Regulatory treatment.** SBM risk class 1. Delta risk factors are the risk-free curve at the ten vertices **0.25, 0.5, 1, 2, 3, 5, 10, 15, 20, 30 years**, plus a flat inflation curve and cross-currency basis curves (`MAR21.8`). Each **currency is a separate bucket** (`MAR21.41`). Risk weights per `MAR21.42` Table 1 — see [17](17_FRTB_Standardised_Approach.md) for the full table. IMA liquidity horizon 10 days for specified currencies, 20 days otherwise, 60 days for rate volatility (`MAR33.12` Table 2).

**Common limits.** DV01 by currency and by tenor bucket; total curve risk; steepener/flattener limits; basis limits; VaR and stress-loss limits.

**How banks monitor it.** Intraday DV01 ladders by tenor and currency on the desk blotter; end-of-day bucketed reports; daily VaR/ES; weekly or daily stress; monthly limit review.

**Detail:** [04 — Interest Rate Risk](04_Interest_Rate_Risk.md)

---

### 3.2 Credit Spread Risk (CSR)

**Definition.** The risk of loss from changes in the *spread* an issuer's obligations trade at over the risk-free curve, **without** the issuer defaulting.

**Plain-English example.** A bank owns an investment-grade corporate bond yielding 120bp over Treasuries. Sentiment sours and the spread widens to 160bp. Treasury yields are unchanged. The bond falls; the issuer has not missed a payment and may never do so.

**Instruments exposed.** Corporate and sovereign bonds, CDS, CDS indices, credit options, total return swaps, securitisations, covered bonds.

**Market data involved.** CDS curves by issuer and tenor, bond spread curves (Z-spread, ASW, OAS), index levels (CDX, iTraxx), rating and sector reference data, recovery rate assumptions.

**Calculations used.** CS01 / SDV01; bucketed CS01 by tenor; issuer, sector and country CS01; Z-spread; OAS; asset swap spread; jump-to-default; spread VaR.

**Sensitivities used.** CS01 at the regulatory vertices **0.5, 1, 3, 5, 10 years** (`MAR21.9`); vega on credit options.

**Stress scenarios.** 2008 GFC spread widening; 2011 euro sovereign crisis; March 2020 COVID dislocation; single-name idiosyncratic gap; sector-wide widening.

**Regulatory treatment.** SBM risk classes 2, 3 and 4 (non-securitisation, securitisation-CTP, securitisation-non-CTP). Buckets for CSR non-sec are set along **credit quality × sector** (`MAR21.51` Table 3). Default risk is capitalised *separately* via the **DRC** (`MAR22`), because a spread model does not capture a jump to default. IMA liquidity horizons run 20 days (IG sovereign) to 120 days (credit spread volatility and "other types") — `MAR33.12`.

**Common limits.** CS01 by rating band, sector, issuer, tenor; single-name concentration; index-vs-single-name basis; jump-to-default limits.

**How banks monitor it.** Daily CS01 ladders; issuer concentration reports; top-20 exposures; JTD by name; spread VaR; credit stress.

**Detail:** [05 — Credit Spread Risk](05_Credit_Spread_Risk.md), [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)

---

### 3.3 Equity Risk

**Definition.** The risk of loss from changes in equity prices, equity indices, dividends, equity repo rates, and equity implied volatilities and correlations.

**Plain-English example.** A bank holds a $50m long position in a single technology stock. The stock falls 6% on an earnings miss. The bank loses $3m — regardless of what the wider index did.

**Instruments exposed.** Cash equities, ETFs, index and single-stock futures and forwards, equity options, equity swaps, convertibles, structured equity notes.

**Market data involved.** Spot prices, index levels, dividend forecasts and dividend futures, borrow/repo rates, implied volatility surfaces by strike and expiry, implied correlations.

**Calculations used.** Market value; gross, net, long and short exposure; beta and beta-adjusted exposure; delta, gamma, vega, theta, rho; dividend sensitivity; equity VaR.

**Sensitivities used.** Delta (in shares or currency); index vs single-name delta; sector delta; vega by strike and tenor; correlation sensitivity for basket products.

**Stress scenarios.** October 1987; 2008; February 2018 volatility spike; March 2020; single-name gap; dispersion/correlation break.

**Regulatory treatment.** SBM risk class 5. Buckets by **market cap × economy × sector** (`MAR21.36`ff). Delta risk factors are spot prices and equity repo rates; vega on implied volatilities; curvature on spot only. IMA liquidity horizons: large-cap price 10 days, small-cap price 20, large-cap vol 20, small-cap vol 60, other equity types 60 (`MAR33.12`).

**Common limits.** Net and gross exposure; single-name and sector concentration; beta-adjusted exposure; vega and gamma limits; dividend risk limits.

**How banks monitor it.** Real-time delta on the desk; end-of-day exposure and Greeks; concentration reporting; equity VaR; scenario grids over spot × vol.

**Detail:** [07 — Equity Risk](07_Equity_Risk.md), [09 — Options and Greeks](09_Options_and_Greeks.md)

---

### 3.4 Foreign Exchange Risk

**Definition.** The risk of loss from changes in exchange rates, FX forward points, cross-currency basis, and FX implied volatilities.

**Plain-English example.** A U.S. bank holds €100m of unhedged assets. EUR/USD falls from 1.10 to 1.08. The bank loses $2m in reporting-currency terms, with no change in the euro value of anything it owns.

**Instruments exposed.** FX spot, forwards, swaps, NDFs, FX options, cross-currency swaps, and *any* instrument denominated in a currency other than the reporting currency.

**Market data involved.** Spot rates, forward points, deposit and OIS curves in both currencies, cross-currency basis spreads, FX volatility surfaces (ATM, risk reversals, butterflies).

**Calculations used.** Net open position; FX delta; forward valuation; interest-rate parity; FX option Greeks; FX VaR; currency concentration.

**Sensitivities used.** Delta per currency pair against the reporting currency; vega by expiry and delta-strike; basis sensitivity.

**Stress scenarios.** January 2015 CHF de-peg; 2016 GBP referendum; 2022 JPY depreciation; EM currency crises; a pegged currency breaking.

**Regulatory treatment.** SBM risk class 7. Delta risk factors are all exchange rates between the currency of denomination and the reporting currency (`MAR21.14`). A **single relative risk weight of 15%** applies to all FX sensitivities (`MAR21.87`); for a Basel-specified list of currency pairs and their first-order crosses this may be divided by √2 (`MAR21.88`). Cross-bucket correlation γ = **60%** (`MAR21.89`). IMA liquidity horizons: 10 days for specified pairs, 20 for other pairs, 40 for FX volatility and other FX types (`MAR33.12`).

**Common limits.** Net open position per currency and aggregate; overnight vs intraday limits; vega limits; EM-specific sub-limits.

**How banks monitor it.** Real-time position by currency; end-of-day NOP; FX VaR; concentration by currency; separate treatment of structural/translation exposure.

**Detail:** [06 — FX Risk](06_FX_Risk.md)

---

### 3.5 Commodity Risk

**Definition.** The risk of loss from changes in commodity spot and futures prices, the shape of forward curves, location and grade differentials, and commodity implied volatilities.

**Plain-English example.** A bank is long 1,000 WTI crude futures at $70. The price falls to $67. At 1,000 barrels per contract the loss is $3m.

**Instruments exposed.** Commodity futures, forwards, swaps and options; physically settled contracts; commodity-linked notes.

**Market data involved.** Spot and futures prices by delivery month, forward curves, location differentials, freight, storage and convenience-yield proxies, implied volatility surfaces.

**Calculations used.** Delta by contract month; calendar-spread exposure; basis exposure; commodity VaR; scenario P&L.

**Sensitivities used.** Delta per commodity per maturity bucket; vega; spread sensitivities.

**Stress scenarios.** 2008 oil spike and collapse; April 2020 negative WTI settlement; 2022 European gas and the LME nickel squeeze.

**Regulatory treatment.** SBM risk class 6. Buckets by commodity type (energy, metals, agriculture, etc.). IMA liquidity horizons: energy and carbon price 20 days, precious/non-ferrous metals price 20, other commodities price 60, energy vol 60, metals vol 60, other commodity vol 120, commodity other types 120 (`MAR33.12`).

**Common limits.** Delta by commodity; calendar-spread limits; location-basis limits; physical delivery limits; vega limits.

**Detail:** [08 — Commodity Risk](08_Commodity_Risk.md)

---

### 3.6 Default risk — and why it is *not* credit spread risk

**Definition.** The risk of loss from an issuer failing outright, causing a discontinuous jump in value rather than a diffusive spread move.

**Why it is separated.** A spread model calibrated on daily changes describes a *continuous* process. Default is a *jump*: a bond going from 95 to 30 overnight is not a large draw from the distribution of daily spread changes — it is a different kind of event. A VaR or SBM model built on spread diffusion will systematically under-capture it.

Basel therefore capitalises it separately. `MAR22.1` states the DRC requirement "is intended to capture jump-to-default (JTD) risk that may not be captured by credit spread shocks under the sensitivities-based method."

**Calculations used.** Gross JTD; net JTD (offsetting long and short on the same obligor); the hedge benefit ratio (HBR); weighted net JTD; bucket-level and total DRC.

**Regulatory treatment.** `MAR22`. Default risk weights by credit quality category (`MAR22.24` Table 2): AAA 0.5%, AA 2%, A 3%, BBB 6%, BB 15%, B 30%, CCC 50%, unrated 15%, defaulted 100%. Three buckets — corporates, sovereigns, local government/municipalities — with **no diversification recognised between them** (`MAR22.26`).

**Relationship to market risk.** Default risk of *trading book* positions is capitalised inside the market risk framework. Default risk of *banking book* loans is credit risk. Same underlying event, different framework, decided entirely by which book the instrument sits in.

**Detail:** [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)

---

### 3.7 Volatility risk

**Definition.** The risk of loss from changes in *implied volatility* — the market's forward-looking price of uncertainty — independent of any move in the underlying.

**Plain-English example.** A bank is short a straddle. The underlying does not move at all. Implied volatility rises from 18% to 24%. The bank loses money on a position whose underlying never budged.

**Where it sits in the taxonomy.** Volatility risk is **not a top-level Basel risk class**. It is captured as **vega within each of the seven SBM classes**, and separately in the IMA through volatility risk factors with their own (longer) liquidity horizons.

**Sensitivities used.** Vega; volga/vomma (vega convexity); vanna (vega's sensitivity to spot); bucketed vega by expiry and strike.

**Regulatory treatment.** Vega risk weights are set per `MAR21.92` Table 13 by a regulatory liquidity horizon per risk class — GIRR 60, CSR (all) 120, equity large-cap/indices 20, equity small-cap/other 60, commodity 120, FX 40 — with the risk weight determined by a formula in which σ is set at **55%**. Note that a bank must model the volatility surface **across both strike and tenor** for material options books (`MAR33.12`).

**Detail:** [09 — Options and Greeks](09_Options_and_Greeks.md)

---

### 3.8 Correlation risk

**Definition.** The risk of loss from changes in the co-movement between risk factors.

**Two quite different phenomena share the name:**

1. **Product-level correlation risk** — the value of a multi-underlying instrument (basket option, spread option, quanto, best-of) depends explicitly on a correlation parameter. This is a genuine, priced, hedgeable-in-principle exposure.
2. **Portfolio-level correlation risk** — diversification assumed in a VaR model fails when correlations converge in stress. This is a *model* risk about the aggregation, not a position.

**Regulatory treatment.** Basel handles the two differently and deliberately:

- Product-level correlation risk on exotic multi-underlying instruments is pushed into the **RRAO** — `MAR23.5(2)` lists "all basket options, best-of-options, spread options, basis options, Bermudan options and quanto options."
- **However** `MAR23.6(3)` explicitly excludes correlation risk arising from *multi-underlying European or American plain vanilla* options from triggering the RRAO by itself.
- Portfolio-level correlation instability is addressed by the **three correlation scenarios** in the SBM (`MAR21.6`) and by constrained cross-class correlations in the IMA (`MAR33.14`).

**Detail:** [17](17_FRTB_Standardised_Approach.md), [10 — Portfolio Risk Mathematics](10_Portfolio_Risk_Mathematics.md)

---

### 3.9 Basis risk

**Definition.** The risk that two instruments intended to offset each other do not move together.

**Plain-English example.** A bank is long a corporate bond and short the same issuer's CDS at the same maturity, believing itself credit-neutral. The CDS-bond basis moves 20bp. The "hedged" position loses money.

**Varieties.** Cash vs derivative (CDS-bond); tenor basis (1M vs 3M floating); cross-currency basis; index vs constituents (index skew); location and grade basis in commodities; futures vs cash (the deliverable basket).

**Why it matters disproportionately.** Basis positions are constructed precisely because their *outright* risk is small. That makes them large in notional relative to their apparent risk, cheap to carry, and easy to under-report. They are structurally over-represented in trading loss events.

**Regulatory treatment.** No single "basis risk" class. It is captured where the framework happens to separate the two curves — cross-currency basis has its own GIRR risk factors and a **0% correlation** to the yield curve, to inflation, and to other cross-currency basis curves (`MAR21.50`), which is Basel refusing to grant any offset at all.

---

### 3.10 Concentration risk

**Definition.** The risk that a position is large relative to the market's capacity to absorb it, so that exiting moves the price against you.

**Why standard metrics miss it.** VaR is computed from *historical* factor changes, which reflect trading in *normal* size. A position ten times the average daily volume cannot be liquidated at historical prices, and no amount of history will reveal that.

**Regulatory treatment.** Not a separate FRTB risk class. Partially internalised through **liquidity horizons** in the IMA (`MAR33.12`) and through supervisory scrutiny. ISDA SIMM, by contrast, has an **explicit concentration risk component** with concentration thresholds — a genuine methodological difference between SIMM and FRTB ([22](22_Counterparty_CVA_and_SIMM.md)).

**Common limits.** Position vs average daily volume; days-to-liquidate; single-issuer, single-name, single-country caps.

---

### 3.11 Gap risk and jump risk

**Definition.** The risk of a discontinuous price move — an overnight gap, a policy shock, a digital payoff crossing its barrier — during which no hedging is possible.

**Regulatory treatment.** `MAR23.5(1)` defines gap risk for RRAO purposes as "risk of a significant change in vega parameters in options due to small movements in the underlying, which results in hedge slippage," and names "all path dependent options, such as barrier options, and Asian options as well as all digital options."

**Note the definitional trap.** "Gap risk" in the RRAO sense is a *specific* hedge-slippage phenomenon in optionality. "Gap risk" in ordinary desk usage means an overnight price jump. Both usages are current. State which you mean.

---

### 3.12 Non-linear / optionality risk

**Definition.** The risk arising because value is a non-linear function of the risk factor, so first-order sensitivities misstate the loss for anything but small moves.

**Consequence.** For non-linear portfolios, delta-normal VaR is not merely imprecise — it can have the wrong sign for the tail. A short-gamma book looks flat on delta and loses on *any* large move in *either* direction.

**Regulatory treatment.** The SBM adds an explicit **curvature** charge on top of delta and vega for exactly this reason. The IMA requires that models "capture the non-linear price characteristics of options positions" (`MAR33.12`).

---

### 3.13 Liquidity-related market risk

**Definition.** The risk that the price obtainable differs from the marked price because of market illiquidity, and that the time required to exit exceeds the assumed holding period.

**Regulatory treatment.** This is FRTB's single largest conceptual advance over Basel 2.5. The IMA replaces a uniform 10-day holding period with **risk-factor-specific liquidity horizons** of 10, 20, 40, 60 or 120 days (`MAR33.4`, Table 1), assigned per risk-factor category by `MAR33.12` Table 2 — with the horizon treated as a *floor* that a bank may increase, subject to documentation and supervisory approval, and capped at the maturity of the related instrument.

**Distinguish clearly** from *funding* liquidity risk (can the bank finance itself), which is a separate discipline under LCR/NSFR and is not market risk.

---

### 3.14 Residual risks (RRAO)

**Definition.** Risks that genuinely exist in exotic instruments but which the SBM's delta/vega/curvature machinery does not represent.

**Regulatory treatment.** `MAR23`. The RRAO is a blunt **gross-notional × risk-weight** charge, deliberately crude because the instruments are heterogeneous:

- **1.0%** for instruments with an **exotic underlying** (`MAR23.8(2)(a)`)
- **0.1%** for instruments bearing **other residual risks** (`MAR23.8(2)(b)`)

Back-to-back transactions that exactly match a third-party transaction are excluded, as is any instrument that is listed or eligible for central clearing (`MAR23.7`).

**Detail:** [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)

---

### 3.15 Non-modellable risk factors (NMRF)

**Definition.** Risk factors that fail the **Risk Factor Eligibility Test** — that is, for which the bank cannot evidence enough **real price observations** to model them credibly.

**Why the category exists.** Before FRTB, a bank could include a thinly-observed risk factor in its VaR model, obtain full diversification benefit against everything else, and never demonstrate that its distribution was based on anything real. FRTB severs that: a factor that cannot be evidenced cannot be diversified.

**Regulatory treatment.** `MAR31.12`–`MAR31.24` set the RFET. Failing factors are capitalised through **stress scenario capital (SES)** rather than the ES model, with the stress calibrated to a 97.5% confidence threshold over a period of stress, and a liquidity horizon that is the greater of the factor's `MAR33.12` horizon and **20 days** (`MAR33`, NMRF section). Crucially, SES is aggregated with **limited diversification benefit**, which is the whole point of the regime.

**Detail:** [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)

---

## 4. MASTER MARKET-RISK TAXONOMY TABLE

| Level 1 | Level 2 | Level 3 | Risk factor | Instruments | Risk metric | Regulation | Example |
|---|---|---|---|---|---|---|---|
| Interest rate | Level | Parallel shift | Risk-free zero curve, all tenors | Bonds, swaps, futures, FRAs | DV01, mod. duration | SBM GIRR delta; `MAR21.42` | +100bp parallel → 10y bond −8.5% |
| Interest rate | Slope | Steepener/flattener | 2s10s spread | Curve trades, swap spreads | KRD ladder, curve VaR | SBM GIRR delta, cross-tenor corr. `MAR21.46` | 2s10s +50bp on a flattener |
| Interest rate | Curvature | Butterfly | 2y/5y/10y wings vs body | Butterfly trades | KRD, butterfly P&L | SBM GIRR delta | 5y richens vs wings |
| Interest rate | Tenor | Key rate | Zero rate at 0.25–30y vertices | All rate products | Key-rate DV01 | `MAR21.8` ten vertices | 10y node +1bp |
| Interest rate | Basis | Tenor basis | 1M vs 3M SOFR basis | Basis swaps | Basis DV01 | GIRR separate curves; 99.90% corr. `MAR21.45` | 3M/6M basis widens 5bp |
| Interest rate | Basis | Cross-currency | XCCY basis spread | XCCY swaps, FX forwards | Basis DV01 | GIRR risk factor, **0% corr.** `MAR21.50` | EUR/USD basis −20bp |
| Interest rate | Inflation | Breakeven | Inflation curve | Linkers, inflation swaps | Inflation DV01 | GIRR; RW 1.6% `MAR21.43` | 10y breakeven +15bp |
| Interest rate | Volatility | Rate vol | Swaption vol cube | Swaptions, caps/floors | Vega, volga | SBM GIRR vega; LH 60 `MAR21.92` | Normal vol +10bp/day |
| Credit spread | Level | Outright | Issuer spread curve | Corp bonds, CDS | CS01 | SBM CSR delta; `MAR21.51` | IG spread +40bp |
| Credit spread | Curve | Tenor structure | Spread at 0.5/1/3/5/10y | CDS curve trades | Bucketed CS01 | `MAR21.9` five vertices | 5s10s credit curve flattens |
| Credit spread | Idiosyncratic | Single name | Single-issuer spread | Single-name CDS/bonds | Issuer CS01, JTD | SBM CSR + `MAR22` DRC | Name gaps 200bp on downgrade |
| Credit spread | Systematic | Sector/index | CDX/iTraxx level | Index CDS | Index CS01 | SBM CSR buckets by sector | iTraxx Main +25bp |
| Credit spread | Basis | CDS-bond | Basis spread | Long bond / short CDS | Basis CS01 | Separate curves in CSR | Basis moves 20bp |
| Default | Jump | JTD | Obligor default event | Bonds, CDS, equity deriv. | Gross/net JTD, DRC | `MAR22`; RW 0.5%–100% `MAR22.24` | BBB issuer defaults → 6% RW |
| Equity | Price | Index | Index level | Futures, index options | Delta, beta-adj. exposure | SBM Equity delta | S&P −5% |
| Equity | Price | Single name | Spot price | Cash equity, options | Delta | SBM Equity, bucket by cap/sector | Stock −6% on earnings |
| Equity | Dividend | Dividend | Dividend forecast/futures | Equity swaps, options | Dividend delta | SBM Equity risk factor | Dividend cut |
| Equity | Repo | Borrow cost | Equity repo rate | Equity swaps, financing | Repo DV01 | SBM Equity delta risk factor | Borrow tightens 50bp |
| Equity | Volatility | Implied vol | Vol surface (strike × expiry) | Equity options | Vega, skew, term | SBM Equity vega; LH 20/60 | VIX 14 → 30 |
| Equity | Correlation | Basket/dispersion | Implied correlation | Basket options, dispersion | Correlation sensitivity | RRAO `MAR23.5(2)` | Correlation → 1 in stress |
| FX | Spot | Net position | Spot rate vs reporting ccy | Everything non-domestic | Net open position, delta | SBM FX; RW **15%** `MAR21.87` | EUR/USD 1.10 → 1.08 |
| FX | Forward | Points | Forward points / IR differential | FX forwards, swaps, NDFs | Forward delta, DV01 legs | GIRR + FX | Points widen on rate divergence |
| FX | Volatility | Implied vol | FX vol surface, RR, BF | FX options | Vega, vanna, volga | SBM FX vega; LH 40 | CHF de-peg vol explosion |
| Commodity | Price | Spot/front | Front-month futures | Futures, swaps | Delta | SBM Commodity delta | WTI $70 → $67 |
| Commodity | Curve | Calendar | Futures curve by month | Calendar spreads | Spread delta | SBM Commodity buckets | Contango steepens |
| Commodity | Basis | Location | Hub differential | Physical, basis swaps | Basis delta | SBM Commodity | WTI-Brent widens |
| Cross | Gap | Hedge slippage | Barrier/digital proximity | Barriers, digitals, Asians | RRAO notional | RRAO 0.1% `MAR23.5(1)` | Spot pins the barrier |
| Cross | Concentration | Liquidity | Position vs ADV | Any large position | Days-to-liquidate | LH `MAR33.12`; SIMM conc. | 10× ADV position |
| Cross | Residual | Exotic underlying | Non-standard underlying | Exotic notes | RRAO 1.0% | `MAR23.8(2)(a)` | Longevity-linked note |
| Cross | Non-modellable | RFET failure | Sparse-observation factor | Illiquid tenors/names | SES stress capital | `MAR31.12`+ | 40y point with 8 obs/year |

---

## 5. Mapping between the taxonomies

Because the same position must be classified in several schemes simultaneously, this crosswalk is worth memorising:

| Internal desk view | FRTB SBM class | FRTB IMA broad class | ISDA SIMM risk class |
|---|---|---|---|
| Rates | GIRR | Interest rate | Interest Rate |
| Inflation | GIRR (inflation risk factor) | Interest rate | Interest Rate |
| Credit — flow/cash | CSR non-securitisation | Credit spread | Credit (Qualifying) |
| Credit — structured | CSR securitisation (CTP / non-CTP) | Credit spread | Credit (Non-Qualifying) |
| Equity | Equity | Equity | Equity |
| FX | FX | Foreign exchange | FX |
| Commodities | Commodity | Commodity | Commodity |
| Exotics/correlation desk | RRAO (+ underlying class) | (modelled where possible) | Add-on / concentration |
| Default risk on any of the above | DRC | DRC under IMA | *not covered* — SIMM is margin, not capital |

> The final row is the one most often got wrong. **ISDA SIMM is an initial-margin methodology, not a capital framework.** It looks like FRTB SBM because both are sensitivity-based, bucketed and correlation-aggregated, but they answer different questions with different calibrations and different governance. See [22](22_Counterparty_CVA_and_SIMM.md).

---

## 6. Counting the taxonomy

Per the scheme set out in section 2 of this document — and *only* per that scheme, since section 1 establishes there is no universal count:

| Measure | Count | Basis |
|---|---|---|
| Level 1 drivers | **6** | Interest rate, credit spread, equity, FX, commodity, cross-cutting |
| Level 2 modes | **34** | As enumerated in the section 2 tree |
| Level 3 exposures | **34** | One per Level 2 leaf in the tree |
| Basel SBM risk classes | **7** | `MAR21.39`–`MAR21.89` — fixed by regulation |
| Basel IMA broad risk classes | **5** | `MAR33.14` — fixed by regulation |
| Basel SA capital components | **3** | SBM + DRC + RRAO (`MAR20`) |
| Named cross-cutting risks | **8** | Default, gap/jump, correlation, basis, concentration, liquidity-adjusted, residual, non-modellable |

---

## 7. Limitations

- The Level 2/Level 3 scheme is **this knowledge base's construction**, informed by regulatory and industry practice but not itself a regulatory object. Do not cite it to a supervisor.
- The regulatory counts (7 SBM classes, 5 IMA classes, 3 SA components) **are** regulatory and are cited to paragraph.
- Bucket definitions, risk weights and correlations quoted here are from the Basel standard. **Jurisdictional implementations may differ** — the EU is applying a targeted multiplier and operational relief measures from 1 January 2027 for a three-year period. See [29](29_Regulatory_Framework.md).

---

## 8. Related Concepts

- [01 — Market Risk Fundamentals](01_Market_Risk_Fundamentals.md)
- [33 — Master Risk Factor Catalog](33_Master_Risk_Factor_Catalog.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)
- [41 — Market Risk vs Related Risk Types](41_Market_Risk_vs_Related_Risk_Types.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | All `MAR` paragraph citations in this document |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current text of MAR20–MAR33 |
| ISDA | ISDA SIMM Methodology v2.8+2512 | Jun 2026, effective 11 Jul 2026 | https://www.isda.org/2026/06/12/isda-publishes-isda-simm-methodology-version-2-8-2512/ | SIMM risk-class crosswalk |

*Accessed 25 August 2026.*
