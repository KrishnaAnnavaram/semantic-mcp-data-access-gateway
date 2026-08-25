# 02 — Financial Instruments and Their Market Risk

**Level:** 2 · **Prerequisites:** [01](01_Market_Risk_Fundamentals.md), [01A](01A_Master_Market_Risk_Taxonomy.md) · **Feeds:** [03](03_Pricing_Fundamentals.md), [04](04_Interest_Rate_Risk.md)–[09](09_Options_and_Greeks.md)

---

## 0. How to read this document

Every instrument is documented against the same ten questions:

1. **What is it?**
2. **Why does a bank trade it?**
3. **What cash flows does it produce?**
4. **What is required to price it?**
5. **What market data is required?**
6. **Which risk factors affect it?**
7. **What sensitivities are calculated?**
8. **What risk calculations are run?**
9. **What stress tests are relevant?**
10. **How does FRTB treat it?**

The most important instruments get the full narrative treatment. The rest are documented in the compact matrices in §9 and §10, which carry the same ten fields in tabular form.

**One rule governs the whole document:** an instrument's risk is determined by *what it is a function of*, not by what it is called. A cross-currency swap is called an FX product and is mostly an interest-rate product. A convertible bond is called a bond and is substantially an equity option. Classify by risk factor sensitivity, always.

---

## 1. Fixed Income

### 1.1 Government bonds (the reference case)

**1. What is it?** A tradeable debt security issued by a sovereign, paying fixed coupons at regular intervals and redeeming principal at maturity. The U.S. Treasury market is the deepest and functions as the global risk-free benchmark.

**2. Why does a bank trade it?** Market making for clients; a liquidity buffer (HQLA); the hedging instrument of choice for interest-rate risk in every other product; collateral in repo; the benchmark against which all spread products are quoted.

**3. Cash flows.** Fixed coupon *c*·*F*/*f* at each of *n* payment dates, plus face *F* at maturity. No optionality in the plain-vanilla case. Note that some sovereign markets issue with embedded calls or in linker form; those are different instruments.

**4. What is required to price it?** A discount curve and the bond's contractual terms. Price is the present value of the cash flows:

```
        n
P   =   Σ  CFᵢ · DF(tᵢ)
       i=1
```

where `DF(t)` is the discount factor to time *t*. Equivalently, using a single yield *y* compounded *f* times per year:

```
        n     c·F/f          F
P   =   Σ  ───────────  +  ─────────
       i=1  (1+y/f)^i      (1+y/f)^n
```

The first form is how a risk system prices; the second is how a trader quotes. They agree only when the curve is flat, which is why "yield" is a *quoting convention*, not a risk factor.

**5. Market data required.** On-the-run and off-the-run yields across the curve; repo rates for financing; for a full curve build, bills, notes and bonds across maturities.

**6. Risk factors.** Risk-free zero rates at each vertex; issue-specific repo/specialness; for non-domestic sovereigns, a sovereign credit spread and an FX rate.

**7. Sensitivities.** DV01; key-rate DV01 at the ten regulatory vertices; convexity; for foreign sovereigns, CS01 and FX delta.

**8. Risk calculations.** PV, accrued interest, clean/dirty price, YTM, duration family, carry and roll-down, curve scenario P&L, VaR, ES, stress.

**9. Stress tests.** Parallel ±100/200/300bp; 1994; 2013 taper tantrum; 2022 rate shock; 2022 gilt/LDI; auction failure; flight-to-quality rally.

**10. FRTB treatment.** GIRR delta and curvature. A domestic-currency sovereign may, at national discretion, receive a **zero default risk weight** under `MAR22.7`. Non-domestic sovereigns attract CSR (bucket 1 of `MAR21.51` Table 3 — "Sovereigns including central banks, multilateral development banks") and DRC.

---

### 1.2 Corporate bonds

**1–3.** As government bonds, but issued by a company and therefore carrying default risk and a credit spread. Cash flows are contractually identical to a government bond of the same structure; the difference is the *probability* of receiving them.

**4. Pricing.** Discount at risk-free + spread. Three spread conventions coexist and are **not interchangeable**:

| Spread | Definition | Correct use |
|---|---|---|
| **Yield spread** (G-spread) | Bond YTM − interpolated government yield at same maturity | Quick quoting; ignores curve shape |
| **Z-spread** | Constant spread added to *every* zero rate such that PV equals market price | Comparing bonds with different cash-flow profiles |
| **OAS** | Z-spread after stripping out the value of embedded options | The only valid comparison for callable/putable bonds |

**5. Market data.** Government curve; issuer or sector/rating spread curve; CDS curve where available; rating and sector reference data.

**6. Risk factors.** Risk-free zero rates; issuer credit spread by tenor; recovery assumption; FX if non-domestic.

**7. Sensitivities.** DV01 (rate) and **CS01 (spread) separately** — this separation is the entire point of the credit trading business, and a system that reports only "total DV01" on a corporate bond is unfit for purpose.

**8. Risk calculations.** As government bonds, plus Z-spread/OAS, CS01, JTD, spread VaR.

**9. Stress tests.** 2008 spread widening; 2011 euro sovereign; March 2020; sector-specific shock; single-name downgrade/default.

**10. FRTB treatment.** GIRR (delta, curvature) **and** CSR non-securitisation (delta, vega if optionality, curvature) **and** DRC. One bond, three separate capital components — a fact that surprises newcomers and drives a great deal of the SA's conservatism.

---

### 1.3 Floating-rate notes (FRNs)

**What it is.** A bond whose coupon resets periodically to a reference rate (SOFR, EURIBOR, €STR) plus a fixed quoted margin.

**The key risk insight.** An FRN's price is *approximately* insensitive to parallel moves in the reference rate, because the coupon resets. Its interest-rate DV01 is roughly the DV01 to the **next reset date only** — days or weeks, not years.

**But it retains full credit spread duration.** If the issuer's spread widens, the fixed quoted margin is now too low relative to what the market demands, and the price falls by approximately (spread change × maturity). An FRN is therefore a **low-DV01, high-CS01** instrument.

> This asymmetry is one of the most useful facts in fixed income and one of the most commonly mis-modelled. A risk system that applies a bond's maturity to *both* the rate and spread sensitivities will overstate FRN interest-rate risk by an order of magnitude.

**FRTB.** Small GIRR delta (to next reset); full CSR delta; DRC.

---

### 1.4 Inflation-linked securities

**What it is.** Principal (and therefore coupon) indexed to a published inflation index — TIPS in the U.S., linkers in the UK, OATi in France.

**Risk factors.** *Real* rates, *and* the inflation breakeven curve. The relationship is the Fisher identity:

```
nominal ≈ real + breakeven inflation
```

Being long a linker and short a nominal of the same maturity is a pure **breakeven** position.

**Traps.** Indexation lags (typically 3 months in the U.S., previously 8 months in older UK issues); seasonality in the index; a deflation floor on principal in some issues, which is a genuine embedded option.

**FRTB.** GIRR, with **inflation as its own risk factor** carrying a risk weight of **1.6%** (`MAR21.43`) and a correlation of **40%** to the yield curve (`MAR21.49`). Note the framework treats the inflation curve as a single flat risk factor per currency, not a term structure of vertices.

---

### 1.5 Mortgage-backed and asset-backed securities

**What it is.** Securities whose cash flows come from a pool of underlying loans, usually tranched by seniority.

**Why they are hard.** The borrower holds a **prepayment option**. When rates fall, borrowers refinance and the security shortens exactly when the investor would have wanted duration. This produces **negative convexity**: the price rises less on a rally than it falls on a sell-off.

**Consequence for risk measurement.** Analytical duration is meaningless. You must use **effective duration** and **effective convexity**, computed by bumping the curve and re-running a prepayment model:

```
                P(−Δy) − P(+Δy)
Effective D  =  ─────────────────
                  2 · P₀ · Δy
```

with `P(±Δy)` obtained by full revaluation including the prepayment model's response.

**Risk factors.** Rates; prepayment speed (itself a model output driven by rates, burnout, seasonality, credit); OAS; for non-agency, credit spread and default/severity.

**FRTB.** GIRR + CSR **securitisation** (non-CTP unless part of the correlation trading portfolio) + DRC for securitisations. Prepayment behaviour driven by retail decision-making may bring **behavioural risk** into scope for the RRAO — `MAR23.5(3)` cites "fixed rate mortgage products where retail clients may make decisions motivated by factors other than pure financial gain."

---

## 2. Money Markets

| Instrument | What it is | Key risk | Main sensitivity | FRTB |
|---|---|---|---|---|
| **Deposit** | Unsecured short-term lending/borrowing | Rate to maturity; counterparty credit | Short-dated DV01 | GIRR |
| **Commercial paper** | Short-term unsecured corporate note, issued at discount | Rate + issuer spread | DV01, CS01 | GIRR + CSR + DRC |
| **Treasury bill** | Sovereign discount instrument, ≤1y | Short-dated rate | DV01 | GIRR |
| **Repo** | Sale with agreement to repurchase — secured financing | Repo rate; collateral haircut; specialness | Repo DV01; collateral risk | GIRR (financing leg) |
| **Reverse repo** | The other side — secured lending | As above, opposite sign | As above | GIRR |

**Note on repo.** Repo is economically secured financing but is legally a sale and repurchase, and this matters. The **specialness** of an individual bond in repo — the degree to which it finances below the general collateral rate — is an independent, tradeable risk factor, and it is a real driver of P&L on a cash-bond market-making book. Risk systems that treat all financing at a single GC rate miss it entirely.

**Discount convention trap.** A Treasury *bill* is quoted on a **discount** basis; a Treasury *note* is quoted as a **coupon-equivalent yield**. They are different quoting bases and must never be placed on the same curve without conversion. Mixing them produces a curve that looks plausible and is wrong at the short end.

---

## 3. Interest-Rate Derivatives

### 3.1 Interest-rate swap (the workhorse)

**1. What is it?** An agreement to exchange a stream of fixed payments for a stream of floating payments on a notional that is never exchanged.

**2. Why trade it?** It is the cheapest, most capital-efficient way to take or hedge interest-rate risk. No principal changes hands, so a swap gives duration without balance sheet.

**3. Cash flows.** Fixed leg: *N* · *K* · *τᵢ* at each fixed date. Floating leg: *N* · *Lᵢ* · *τᵢ*, where *Lᵢ* is the fixing observed for that period. No principal exchange.

**4. Pricing.** Post-LIBOR, this requires **two curves** — a discounting curve (OIS/SOFR, reflecting the collateral remuneration rate under the CSA) and a projection curve for the floating index:

```
                   n                                m
PV  =  N · [  Σ  Lᵢ^proj · τᵢ · DF(tᵢ)   −   K ·  Σ  τⱼ · DF(tⱼ)  ]
                  i=1                              j=1
              └──── floating leg ────┘        └─── fixed leg ───┘
```

The par swap rate is the *K* that makes PV zero:

```
              Σ Lᵢ^proj · τᵢ · DF(tᵢ)
    K_par  =  ────────────────────────
                  Σ τⱼ · DF(tⱼ)
                  └── annuity ──┘
```

The denominator is the **annuity** (or PV01 of the fixed leg), and it is the single most useful quantity in swap risk: the swap's DV01 is very nearly the annuity.

**5. Market data.** OIS/SOFR curve for discounting; index projection curve; basis spreads between them; the CSA terms, which determine *which* discount curve is correct.

**6. Risk factors.** Discount curve zero rates; projection curve zero rates; tenor basis; cross-currency basis if the CSA is in a different currency.

**7. Sensitivities.** DV01 (usually reported as annuity-based PV01); key-rate DV01; basis DV01; cross-gamma between discount and projection curves.

**8. Risk calculations.** PV; par rate; DV01 ladder; carry and roll; curve scenario P&L; VaR, ES, stress.

**9. Stress tests.** Parallel and curve shocks; basis widening; a CSA/discounting regime change.

**10. FRTB.** GIRR delta and curvature. Vega only if the swap embeds optionality (it does not, in vanilla form).

> **The discounting point deserves emphasis.** The move from LIBOR-discounting to OIS/CSA-discounting was not a refinement — it changed the value of every collateralised derivative book in the world, and it made the *choice of discount curve* a risk factor. A swap collateralised in EUR but denominated in USD is exposed to the EUR/USD cross-currency basis through its discounting. This is invisible unless the risk system models the CSA.

### 3.2 OIS and FRAs

**OIS.** A swap where the floating leg is the compounded overnight rate (SOFR, €STR, SONIA). Post-reform, OIS *is* the risk-free curve for most purposes — it is both the benchmark instrument and the discounting basis.

**FRA.** A single-period forward rate agreement: one fixed-vs-floating exchange at a future date. Its risk is a forward rate at one point. FRAs are the natural short-end curve-building instrument, and their **settlement convention** (discounted at the fixing rate, paid at period start) introduces a small convexity adjustment that must not be ignored at large sizes.

### 3.3 Bond futures

**What it is.** An exchange-traded contract for the future delivery of a government bond from a defined **deliverable basket**.

**The complication that defines the instrument.** The short may choose which bond to deliver. That is an option, and it belongs to the seller. The **cheapest-to-deliver (CTD)** bond is the one minimising delivery cost, and *which bond is CTD changes as yields move* — typically low-duration bonds become CTD as yields rise above the notional coupon, and high-duration bonds as yields fall.

**Consequence.** A bond future's DV01 is the CTD's DV01 divided by the conversion factor, but that relationship is itself unstable. Near a CTD switch the future has meaningful negative convexity that a simple `DV01_CTD / CF` calculation misses.

**FRTB.** GIRR. Note `MAR23.6(1)` explicitly states that risk from a **cheapest-to-deliver option** does *not*, by itself, bring an instrument into the RRAO.

### 3.4 Swaptions, caps and floors

**Swaption.** An option to enter a swap. A *payer* swaption is the right to pay fixed (profits if rates rise); a *receiver* swaption the right to receive fixed. Quoted in normal (bp/day or bp/annum) or lognormal volatility; the market moved substantially to **normal (Bachelier) volatility** after rates went negative in EUR and JPY, because lognormal models cannot represent negative rates.

**Cap/floor.** A strip of independent options (caplets/floorlets) on successive forward rates. A cap is *not* a single option on an average — it is a portfolio of options, and its value therefore contains no correlation between the forwards, unlike a swaption which does.

> **This distinction — cap as a strip vs swaption as a single option on a basket — is the origin of the cap/swaption volatility relationship and of a whole class of relative-value trades.** A swaption's implied volatility is lower than the corresponding cap strip's precisely because of imperfect correlation between forwards.

**Risk factors.** Rates; swaption volatility cube (expiry × underlying tenor × strike).
**Sensitivities.** Delta (DV01), gamma, vega (bucketed by expiry and tenor), volga, vanna, theta.
**FRTB.** GIRR delta, **vega** and curvature. Vega risk weight per `MAR21.92` Table 13, GIRR liquidity horizon 60.

---

## 4. Foreign Exchange

### 4.1 FX spot and forwards

**Spot.** An agreement to exchange currencies at the current rate, settling T+1 or T+2. Pure FX delta.

**Forward.** Exchange at a fixed rate on a future date. The forward rate is fixed by **covered interest-rate parity**:

```
F  =  S · ( 1 + r_quote · τ ) / ( 1 + r_base · τ )
```

or, in continuous form, `F = S · e^((r_q − r_b)·τ)`.

**The key insight.** An FX forward is *not* primarily an FX product. It is an FX spot position **plus two interest-rate positions**. A one-year EUR/USD forward has EUR rate risk, USD rate risk, and EUR/USD spot risk. A risk system that reports only spot delta on a forward book is missing most of the risk.

**Cross-currency basis.** Covered interest parity has not held exactly since 2008. The residual is the **cross-currency basis**, a persistent, tradeable and volatile spread. It is a first-class risk factor: `MAR21.50` gives it **0% correlation** with the yield curve, with inflation, and with other cross-currency basis curves — Basel granting no offset whatsoever.

**FRTB.** FX delta (RW **15%**, `MAR21.87`) + GIRR on both legs + cross-currency basis as a GIRR risk factor.

### 4.2 FX swaps and NDFs

**FX swap.** Simultaneous spot and offsetting forward. Almost pure *funding* — it is the primary instrument for cross-currency short-term funding, and its risk is overwhelmingly rate differential and basis rather than spot.

**NDF.** A forward on a non-deliverable currency, cash-settled in a hard currency against a published fixing. Adds **fixing risk** (the reference fixing may be manipulated, suspended, or diverge from the offshore rate) and, critically, **onshore/offshore basis** — CNY vs CNH being the canonical case, where two prices for the same currency can diverge substantially and persistently.

### 4.3 FX options

Quoted in a convention unique to FX: **at-the-money volatility**, **risk reversals** (the skew, `σ_25call − σ_25put`) and **butterflies** (the smile curvature), by delta rather than by strike.

**Risk factors.** Spot; both rate curves; the volatility surface.
**Sensitivities.** Delta, gamma, vega, vanna (spot-vol cross), volga (vol convexity), theta. In FX, **vanna and volga are first-class desk risks**, not exotic refinements, because the skew moves a great deal and is itself traded.

### 4.4 Cross-currency swaps

Exchange of interest streams in two currencies, **with principal exchanged** at start and end.

**Risk factors.** Two rate curves, the FX spot rate, and the cross-currency basis. The principal exchange means the FX delta is large and persists to maturity — unlike an interest-rate swap, a cross-currency swap has substantial FX risk.

**FRTB.** GIRR (both currencies + basis) + FX delta.

---

## 5. Equities

| Instrument | Cash flows | Key risk factors | Sensitivities | FRTB |
|---|---|---|---|---|
| **Cash equity** | Dividends; residual claim | Spot, dividend, borrow | Delta, beta | Equity delta + curvature; DRC |
| **ETF** | Tracks index/basket | Constituent spots, tracking error | Delta, sector delta | Equity delta; look-through per `MAR21.36` |
| **Index future** | Daily margin | Index level, dividend, repo rate | Delta, dividend delta | Equity delta |
| **Equity forward** | Single exchange at maturity | Spot, dividend, financing | Delta, rho, dividend delta | Equity + GIRR |
| **Equity option** | Contingent | Spot, vol surface, dividend, rate, borrow | Delta, gamma, vega, theta, rho | Equity delta + **vega** + curvature |
| **Equity swap (TRS)** | Total return vs funding leg | Spot, dividend, funding spread | Delta, funding DV01 | Equity + GIRR + CSR (funding) |

**The dividend point.** Equity derivatives are exposed to *forecast* dividends, which are not contractual. A dividend cut moves forwards and options without the spot moving at all. Dividend risk is a genuine, separately-hedged desk risk (there is a listed dividend futures market), and under FRTB it is an Equity risk factor in its own right.

**The borrow point.** Short positions require stock borrow, and the borrow rate is a risk factor. Hard-to-borrow names can see the borrow cost move hundreds of basis points, which reprices every derivative on them. Under FRTB, **equity repo rates** are Equity delta risk factors alongside spot.

---

## 6. Credit

### 6.1 Credit default swaps

**What it is.** Protection against a credit event on a reference entity. The buyer pays a running premium (standardised at 100bp or 500bp, with an upfront payment reconciling to the market spread); the seller pays out on default, against delivery of a deliverable obligation or via auction settlement.

**Risk factors.** The issuer's credit curve by tenor; recovery rate assumption; the risk-free curve (for discounting the premium leg and the contingent leg).

**Sensitivities.** CS01 (par spread bumped 1bp); bucketed CS01; **JTD** (the immediate loss on default, which is *not* a derivative of anything and cannot be obtained by bumping); recovery sensitivity.

**Critical modelling point.** CS01 and JTD are **independent** risks that move in opposite directions for the same position. Selling protection on a high-quality name gives small positive CS01 and large negative JTD. A book can be spread-neutral and catastrophically exposed to a default. This is precisely why Basel capitalises DRC separately from CSR.

**FRTB.** CSR delta + curvature + DRC. Credit options add vega.

### 6.2 CDS indices

CDX (North America) and iTraxx (Europe/Asia) are standardised, equally-weighted baskets of single-name CDS, rolling every six months.

**Additional risk factor: index skew** — the difference between the index spread and the theoretical spread implied by its constituents. It is persistently non-zero and is itself a traded basis. A long-index/short-constituents position is a pure skew position, and its risk is invisible unless the system models index and constituents as separate factors.

### 6.3 Structured credit and the correlation trading portfolio

Tranched exposures (CDOs, index tranches) whose value depends on **default correlation**, not merely on individual default probabilities. An equity tranche is long correlation; a senior tranche is short correlation.

**FRTB.** These are the reason the SBM has *two* securitisation risk classes. The **correlation trading portfolio (CTP)** is defined in `MAR20` and receives its own CSR class and its own DRC treatment (`MAR22`, securitisations-CTP), because hedging relationships within a CTP are genuine and the framework grants limited recognition of them — recognition it refuses for non-CTP securitisations.

---

## 7. Commodities

| Instrument | Distinguishing feature | Key risk factors | FRTB |
|---|---|---|---|
| **Physical / spot** | Requires storage, transport, insurance | Spot, location, grade, storage cost | Commodity delta |
| **Future** | Exchange traded, dated by delivery month | Price per contract month | Commodity delta + curvature |
| **Forward** | OTC, bespoke date/location | Price, location basis | Commodity delta |
| **Swap** | Fixed vs floating average price | Curve, averaging convention | Commodity delta |
| **Option** | Contingent | Price, vol surface | Commodity delta + **vega** + curvature |

**Contango and backwardation.** When the futures curve is upward-sloping (contango), a long roll loses money as each expiring contract is replaced by a more expensive one. In backwardation the roll earns. **Roll yield is a first-order driver of returns** in commodity portfolios and is frequently larger than the spot move over any extended holding period.

**The April 2020 lesson.** WTI front-month settled at **−$37.63** on 20 April 2020. Any model assuming lognormal prices — which cannot go below zero — assigned that event probability zero. It is the definitive modern argument for stress testing outside the model's distributional assumptions, and for using normal rather than lognormal dynamics where the underlying can genuinely go negative. See [13](13_Stress_Testing.md).

---

## 8. Structured Products

| Instrument | Decomposition | Hidden risk |
|---|---|---|
| **Callable bond** | Straight bond − call option sold to issuer | Negative convexity; vol risk; OAS ≠ Z-spread |
| **Puttable bond** | Straight bond + put option bought | Positive convexity |
| **Convertible bond** | Straight bond + equity call | Equity delta, vol, credit, and their **cross-gammas** |
| **Barrier option** | Vanilla with knock-in/out | **Discontinuous delta and gamma at the barrier**; hedge slippage |
| **Digital option** | Pays fixed amount if in the money | Infinite theoretical gamma at expiry at the strike |
| **Autocallable** | Short down-and-in put + coupon stream | Short vol, short skew, long correlation, huge cross-gamma |
| **Structured note** | Bond + embedded derivative | Funding spread + derivative risk; illiquid |

**Why these dominate the RRAO.** `MAR23.5` names path-dependent options (barriers, Asians) and digitals as bearing **gap risk**, and basket/best-of/spread/basis/Bermudan/quanto options as bearing **correlation risk**. Both fall into the RRAO population. `MAR23.7` then excludes anything listed or eligible for central clearing, and excludes exactly-matched back-to-back transactions.

**The convertible bond point.** A convertible is a bond, an equity option, and a credit exposure simultaneously, and its cross-gammas are large: equity delta depends on credit spread (a distressed convertible is nearly all equity), and credit spread sensitivity depends on the equity level. No sensitivity-based framework captures a convertible well; it requires full revaluation.

---

## 9. MATRIX — Instrument × Risk Factor

`●` = primary exposure · `○` = secondary exposure · blank = not material

| Instrument | IR curve | IR vol | Credit spread | Default | Equity | Eq. vol | FX | FX vol | Commodity | Cmdty vol | Inflation | XCCY basis | Correlation |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Government bond | ● | | ○ | ○ | | | | | | | | | |
| Corporate bond | ● | | ● | ● | | | | | | | | | |
| FRN | ○ | | ● | ● | | | | | | | | | |
| Inflation linker | ● | | ○ | ○ | | | | | | | ● | | |
| MBS / ABS | ● | ○ | ● | ● | | | | | | | | | |
| T-bill / CP | ● | | ○ | ○ | | | | | | | | | |
| Repo | ● | | ○ | ○ | | | | | | | | | |
| IR swap | ● | | | | | | | | | | | ○ | |
| OIS | ● | | | | | | | | | | | | |
| FRA | ● | | | | | | | | | | | | |
| Bond future | ● | ○ | ○ | | | | | | | | | | |
| Swaption | ● | ● | | | | | | | | | | | ○ |
| Cap / floor | ● | ● | | | | | | | | | | | |
| FX spot | | | | | | | ● | | | | | | |
| FX forward | ● | | | | | | ● | | | | | ○ | |
| FX swap | ● | | | | | | ○ | | | | | ● | |
| NDF | ● | | | | | | ● | | | | | ○ | |
| FX option | ● | | | | | | ● | ● | | | | | |
| XCCY swap | ● | | | | | | ● | | | | | ● | |
| Cash equity | | | | ○ | ● | | ○ | | | | | | |
| Equity index future | ○ | | | | ● | | | | | | | | |
| Equity option | ○ | | | | ● | ● | | | | | | | ○ |
| Equity swap / TRS | ● | | ○ | | ● | | | | | | | | |
| CDS | ● | | ● | ● | | | | | | | | | |
| CDS index | ● | | ● | ● | | | | | | | | | ○ |
| Index tranche | ● | | ● | ● | | | | | | | | | ● |
| Commodity future | ○ | | | | | | ○ | | ● | | | | |
| Commodity option | ○ | | | | | | ○ | | ● | ● | | | |
| Callable bond | ● | ● | ● | ● | | | | | | | | | |
| Convertible bond | ● | ○ | ● | ● | ● | ● | | | | | | | ● |
| Barrier option | ○ | | | | ● | ● | ○ | ○ | | | | | |
| Autocallable | ● | | ○ | | ● | ● | | | | | | | ● |

---

## 10. MATRIX — Instrument × Calculation

| Instrument | PV | DV01 | KRD | Convexity | CS01 | JTD | Delta | Gamma | Vega | Theta | Carry/Roll | VaR/ES | Stress | SBM | DRC | RRAO |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Government bond | ● | ● | ● | ● | ○ | ○ | | | | | ● | ● | ● | ● | ○ | |
| Corporate bond | ● | ● | ● | ● | ● | ● | | | | | ● | ● | ● | ● | ● | |
| FRN | ● | ○ | ○ | | ● | ● | | | | | ● | ● | ● | ● | ● | |
| MBS / ABS | ● | ● | ● | ● | ● | ● | | ● | ○ | | ● | ● | ● | ● | ● | ○ |
| IR swap | ● | ● | ● | ● | | | | | | | ● | ● | ● | ● | | |
| Bond future | ● | ● | ● | ● | | | | ○ | | | ● | ● | ● | ● | | |
| Swaption | ● | ● | ● | | | | ● | ● | ● | ● | ● | ● | ● | ● | | |
| FX forward | ● | ● | ○ | | | | ● | | | | ● | ● | ● | ● | | |
| FX option | ● | ○ | | | | | ● | ● | ● | ● | ● | ● | ● | ● | | |
| Cash equity | ● | | | | | ○ | ● | | | | ● | ● | ● | ● | ● | |
| Equity option | ● | ○ | | | | | ● | ● | ● | ● | ● | ● | ● | ● | | |
| CDS | ● | ● | | | ● | ● | | | | | ● | ● | ● | ● | ● | |
| CDS index | ● | ● | | | ● | ● | | | | | ● | ● | ● | ● | ● | |
| Index tranche | ● | ● | | | ● | ● | | ● | ● | | ● | ● | ● | ● | ● | ● |
| Commodity future | ● | ○ | | | | | ● | | | | ● | ● | ● | ● | | |
| Convertible bond | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ● | ○ |
| Barrier option | ● | | | | | | ● | ● | ● | ● | ● | ● | ● | ● | | ● |
| Autocallable | ● | ● | | | ○ | | ● | ● | ● | ● | ● | ● | ● | ● | | ● |

---

## 11. Common implementation errors, by instrument

| Instrument | The error | The consequence |
|---|---|---|
| FRN | Applying full maturity to interest-rate DV01 | IR risk overstated ~50×; hedges wrong |
| Corporate bond | Reporting a single blended "DV01" | Rate and spread risk indistinguishable; hedging impossible |
| Bond future | Fixed `DV01_CTD / CF` with no CTD-switch modelling | Missing negative convexity near the switch point |
| Swap | Single-curve pricing (discount = projection) | Systematic mispricing; basis risk invisible |
| Swap under a foreign-currency CSA | Ignoring the CSA discount currency | Cross-currency basis exposure entirely unreported |
| FX forward | Reporting spot delta only | Both rate legs missing |
| MBS | Analytical rather than effective duration | Negative convexity invisible; hedge wrong-signed in a rally |
| CDS | Treating JTD as derivable from CS01 | Default exposure unmeasured |
| Callable bond | Comparing on Z-spread rather than OAS | Systematically favours the bonds with the most sold optionality |
| T-bill | Placing discount rates on a coupon-equivalent curve | Short end of the curve wrong |
| Barrier option | Sensitivity-based risk near the barrier | Delta/gamma discontinuity → hedge failure exactly when it matters |
| Convertible | Treating as bond + independent option | Cross-gammas missed; behaves unexpectedly in distress |

---

## 12. Validation checks

- **Put-call parity** on every vanilla option book: `C − P = S·e^(−qτ) − K·e^(−rτ)`. Failures indicate a surface or discounting inconsistency.
- **Par swap reprices to zero** at inception on the curve it was built from. If it does not, the curve build and the pricer disagree.
- **Bond price from curve equals bond price from YTM** when the YTM is derived from that same curve.
- **FX forward equals covered interest parity** plus the observed basis — the residual should be the basis and nothing else.
- **Futures DV01 ≈ CTD DV01 / conversion factor**, checked across yield levels to detect CTD switches.
- **CDS upfront reconciles** to the ISDA standard model at the quoted par spread.

---

## 13. Limitations

- The matrices mark *materiality*, not existence. Almost every instrument has a second-order exposure to almost every factor; the tables record what a risk system must capture to be fit for purpose.
- FRTB columns state the *risk classes engaged*, not the capital outcome, which depends on buckets, weights and correlations — [17](17_FRTB_Standardised_Approach.md).
- Product conventions vary by market and jurisdiction. Where a convention is quoted here it is the dominant one; always confirm against the term sheet.

---

## 14. Related Concepts

- [03 — Pricing Fundamentals](03_Pricing_Fundamentals.md) · [04 — Interest Rate Risk](04_Interest_Rate_Risk.md)
- [09 — Options and Greeks](09_Options_and_Greeks.md) · [23 — Market Data and Curves](23_Market_Data_and_Curves.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21`–`MAR23` risk factor and RRAO definitions |
| CME Group | Treasury futures conversion factors and delivery | ongoing | https://www.cmegroup.com/ | CTD and deliverable basket mechanics |
| U.S. Treasury | Daily Treasury Par Yield Curve Rates | ongoing | https://home.treasury.gov/ | Quoting bases: discount vs coupon-equivalent |

*Accessed 25 August 2026.*
