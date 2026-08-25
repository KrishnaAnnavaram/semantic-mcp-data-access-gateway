# 01 — Market Risk Fundamentals

**Level:** 1 (Foundation) · **Prerequisites:** none · **Read before:** every other document in this knowledge base.

---

## 1. Plain English

> **Market risk is the possibility that changes in market prices or market variables cause a bank to lose money.**

That sentence is the whole subject. Everything else — duration, DV01, VaR, Expected Shortfall, FRTB capital — is machinery for answering three questions about it:

1. **How much** could we lose?
2. **From what** would the loss come?
3. **How confident** are we in that answer?

Note what the definition does *not* say. It does not say the bank did something wrong, that a counterparty failed, or that a system broke. Market risk is the risk that *the market moved*. The bank can be perfectly solvent, perfectly operated, and dealing only with impeccable counterparties, and still lose a great deal of money because the ten-year yield rose forty basis points overnight.

---

## 2. Banking Example — the whole subject in one trade

A bank buys **$100 million face value of the 10-year U.S. Treasury note**. It pays roughly par.

The next morning, the market's required yield on 10-year Treasuries rises by **10 basis points** (0.10%).

Nothing about the bond changed. The U.S. government is exactly as creditworthy as it was yesterday. The coupon it will pay is unchanged. The maturity date is unchanged. Nobody defaulted, no system failed, no trader made an error.

And yet the bank has lost roughly **$850,000**.

Why? Because the *price* at which that bond changes hands is the present value of its fixed cash flows, and the rate used to discount those cash flows just went up. Higher discount rate, lower present value. The bank still owns exactly what it owned yesterday; what it owns is simply worth less.

That single event is the seed of the entire discipline:

| Question the loss provokes | The metric invented to answer it | Document |
|---|---|---|
| How much do I lose per basis point? | **DV01** | [04](04_Interest_Rate_Risk.md) |
| How much per 1% yield move, in percentage terms? | **Modified duration** | [04](04_Interest_Rate_Risk.md) |
| Is that sensitivity itself stable? | **Convexity** | [04](04_Interest_Rate_Risk.md) |
| *Which part* of the curve hurt me? | **Key-rate DV01** | [04](04_Interest_Rate_Risk.md) |
| How much could I lose on a normal bad day? | **VaR** | [11](11_VaR.md) |
| And on the bad days beyond that? | **Expected Shortfall** | [12](12_Expected_Shortfall.md) |
| What if 2008 happened again? | **Stress testing** | [13](13_Stress_Testing.md) |
| How much am I *allowed* to lose? | **Limits** | [21](21_Market_Risk_Limits.md) |
| How much capital must I hold against it? | **FRTB** | [16](16_FRTB_Overview.md)–[20](20_NMRF_and_Modellability.md) |

Every one of those metrics exists because somebody, at some point, lost money and could not explain why.

---

## 3. Why banks have market risk at all

Market risk is not an accident that befalls a bank. For a dealer bank it is, to a large degree, **the business itself**. It arises from four distinct activities, and conflating them is one of the most common analytical errors in the field.

### 3.1 Market making

A bank quotes a two-way price — a bid and an offer — in a security or derivative, and stands ready to deal on either side. It earns the spread. But a market maker who has just bought from a client owns a position it did not choose, in a size it did not choose, at a moment it did not choose. It holds that position until it can hedge or unwind it, and during that time it carries the market's risk.

**This is the purest form of market risk in banking: risk accepted as the cost of providing liquidity.**

### 3.2 Proprietary risk-taking

The bank takes a deliberate directional or relative-value position because it expects to profit from it. Post-crisis regulation (notably the Volcker Rule in the United States) has sharply constrained pure proprietary trading at deposit-taking institutions, but the *risk mechanics* are identical to market making — only the intent differs. Intent, however, matters enormously for the trading-book/banking-book boundary ([20](20A_Trading_Book_Boundary_and_IRRBB.md)).

### 3.3 Hedging that is imperfect

A bank hedges a position and believes itself flat. It is almost never exactly flat. A ten-year corporate bond hedged with a ten-year Treasury future is not hedged against a widening of credit spreads; it has merely exchanged outright interest-rate risk for **basis risk**. The residual is real, it is market risk, and because it looks small it is frequently under-monitored — which is precisely why basis positions produce outsized surprises.

### 3.4 Structural and franchise positions

The bank holds assets and liabilities that create market exposure as a by-product of banking rather than trading: a fixed-rate mortgage book funded with floating-rate deposits, foreign-currency earnings from an overseas subsidiary, a securities portfolio held for liquidity purposes. Much of this sits in the **banking book** and is managed as **IRRBB** or ALM rather than as trading market risk — a distinction with major capital consequences, treated in [20](20A_Trading_Book_Boundary_and_IRRBB.md).

---

## 4. Where market risk lives — the structural vocabulary

To measure risk you must first say *whose* risk, *over what*, and *at what level of the organisation*. These terms are used with precision in a bank and should be used with precision here.

### 4.1 Trade

A single executed transaction. It has an identifier, an execution time, a counterparty, a notional, a direction, and a set of economic terms. A trade is an **event**; it happens once.

### 4.2 Position

The bank's net holding in an instrument, as of a point in time — the accumulated result of trades. A position is a **state**; it persists. Risk is measured on positions, not on trades. (P&L attribution, by contrast, cares intensely about which trades occurred during the day — see [14](14_PnL_and_PnL_Explain.md).)

### 4.3 Portfolio / book

A named collection of positions managed together. "Book" usually carries the connotation of a managed, P&L-bearing unit with an owner.

### 4.4 Trading desk

**This is a regulatory object, not merely an organisational convenience.** Under the Basel market risk framework a trading desk is defined in `MAR12` and is the unit at which internal-model approval is granted, backtested, and revoked. A desk has a single head, a defined business strategy, a documented risk management structure, and clear reporting lines. Under FRTB the desk is the atom of model eligibility: one desk can lose IMA approval while its neighbour retains it ([18](18_FRTB_Internal_Models_Approach.md)).

### 4.5 Legal entity

The incorporated company that actually owns the position and is subject to a regulator's rules. A global bank is a group of legal entities in many jurisdictions. Capital is required at legal-entity level *and* at consolidated group level, which is why the same position is frequently capitalised more than once under different rule sets.

### 4.6 The hierarchy

```
Trade
  └─► Position
        └─► Portfolio / book
              └─► Trading desk        ◄── regulatory unit for IMA approval
                    └─► Business line
                          └─► Division
                                └─► Legal entity   ◄── regulatory unit for capital
                                      └─► Region
                                            └─► Consolidated group
```

Risk aggregates *up* this hierarchy, and limits cascade *down* it. Neither aggregation nor limit-setting is a simple sum, because of diversification — see [42](42_Risk_Aggregation.md).

---

## 5. Risk factors — the single most important concept in the field

A bank does not, in practice, model "the price of the bond." It models the **risk factors** that drive that price, and then revalues the bond as a function of them.

> **A risk factor is a market observable whose movement changes the value of a position.**

Examples:

| Risk factor | Asset class | Typical observation |
|---|---|---|
| USD 10-year swap zero rate | Rates | 4.12% |
| EUR/USD spot | FX | 1.0850 |
| S&P 500 index level | Equity | 5,420 |
| 5-year CDS spread on a given issuer | Credit | 78 bp |
| WTI crude 3-month futures price | Commodity | $71.40 |
| 3-month at-the-money implied volatility on EUR/USD | Volatility | 7.9% |

### 5.1 Why the abstraction matters

Three reasons, all of them load-bearing:

**Dimensionality.** A bank may hold hundreds of thousands of distinct instruments but be exposed to only a few thousand risk factors. Modelling factors rather than instruments makes the problem tractable.

**Aggregation.** Two positions can only be netted if they are expressed against a *common* factor. A bund future and a bund cash bond both load onto the EUR risk-free curve; expressing both as sensitivities to that curve is what allows the hedge to be recognised.

**History.** VaR and ES need a history of *changes*. There is a long, clean history for "the USD 10-year zero rate." There is no such history for a swap that was traded yesterday. You simulate the factor and reprice the instrument — never the reverse.

### 5.2 The mapping problem

Every instrument must be mapped to factors, and **mapping is where a great deal of real-world risk error lives.** A bond of an issuer with no liquid CDS gets mapped to a sector-and-rating proxy curve. That proxy is a modelling decision. If the issuer subsequently blows up idiosyncratically, the risk system will have shown almost nothing, because the factor it was mapped to did not move. Under FRTB this concern is formalised as the **Risk Factor Eligibility Test** and the **non-modellable risk factor** regime ([20](20_NMRF_and_Modellability.md)).

---

## 6. Sensitivities — the derivative of value with respect to a factor

> **A sensitivity is the rate of change of a position's value with respect to a risk factor.**

Formally, for portfolio value *V* and risk factor *x*:

```
s = ∂V / ∂x
```

Sensitivities are the working currency of a trading floor because they are **additive across positions for the same factor**. If desk A has +$40,000/bp of 10-year DV01 and desk B has −$25,000/bp, the firm has +$15,000/bp. You cannot add two bonds' *prices* meaningfully; you can add their DV01s.

The named sensitivities by asset class:

| Factor moved | Sensitivity | Conventional unit |
|---|---|---|
| Interest rate, +1bp | **DV01 / PV01 / BPV** | currency per bp |
| Credit spread, +1bp | **CS01 / SDV01** | currency per bp |
| Underlying price, +1 unit | **Delta** | currency per unit, or shares |
| Delta itself, per unit of underlying | **Gamma** | delta per unit |
| Implied volatility, +1 vol point | **Vega** | currency per vol point |
| Time, +1 day | **Theta** | currency per day |
| FX rate, +1% | **FX delta** | currency |

### 6.1 The critical limitation

A sensitivity is a **first derivative**: a local, linear approximation valid for small moves. For a portfolio of options it can be catastrophically wrong for large moves. This is exactly why banks run **full revaluation** for stress tests and, where they can afford the computation, for VaR — see [09](09_Options_and_Greeks.md) and [13](13_Stress_Testing.md).

The Taylor expansion states the position precisely:

```
ΔV  ≈   (∂V/∂x)·Δx            ← delta / DV01 term      (first order, linear)
      + ½·(∂²V/∂x²)·(Δx)²     ← gamma / convexity term (second order)
      + (∂V/∂σ)·Δσ            ← vega term
      + (∂V/∂t)·Δt            ← theta term
      + cross terms …
```

Everything a risk system does is, in one sense or another, an attempt to evaluate that expansion or to escape the need for it by full repricing.

---

## 7. Hedging — and why hedged is not the same as flat

A hedge is a position taken to offset the risk of another position.

The bank that bought $100m of 10-year Treasuries can sell 10-year Treasury futures against it. Now a rate rise costs it on the cash bond and pays it on the future. Its outright interest-rate risk falls dramatically.

**It has not eliminated risk. It has changed its shape.** What remains:

- **Basis risk** — cash Treasuries and Treasury futures are different instruments with different supply-demand dynamics. The basis between them moves.
- **Cheapest-to-deliver optionality** — the futures contract's deliverable basket embeds an option that responds to yield levels and curve shape.
- **Financing / repo risk** — the cash bond must be funded; the future is margined. Repo specialness on that bond is an independent risk factor.
- **Curve risk** — if the hedge ratio was struck on a parallel-shift assumption, a curve twist produces P&L the hedge was never designed to capture.

> **A risk framework that reports the hedged portfolio as "no risk" is not conservative; it is wrong.** The residual risks after hedging are systematically smaller and systematically less monitored, which is a reliable recipe for surprise. Basis positions are where a disproportionate share of trading disasters originate.

---

## 8. Mark-to-market, P&L, and why measurement drives everything

### 8.1 Mark-to-market

The trading book is **fair valued**: positions are carried at the price at which they could be transacted, remeasured every day, with the change flowing through profit and loss.

This is the mechanism that makes market risk *bite*. In a held-to-maturity accounting regime a bond whose price fell is simply a bond whose price fell — the loss is not recognised. In a fair-value regime it is recognised **today**, it hits the P&L **today**, it reduces capital **today**, and if it is large enough it produces a limit breach and a phone call **today**.

The single most important structural fact about market risk is therefore: **it is a risk to reported earnings and regulatory capital on a daily cycle.**

### 8.2 The flavours of P&L

The word "P&L" is used to mean at least five different things, and FRTB depends on distinguishing three of them precisely. Full treatment in [14](14_PnL_and_PnL_Explain.md); the essentials:

| Term | Definition | Used for |
|---|---|---|
| **Actual P&L (APL)** | The real, booked daily P&L including fees, commissions, reserves, intraday trading | Financial reporting; backtesting |
| **Hypothetical P&L (HPL)** | P&L from holding *yesterday's* position through *today's* market move, with no new trades, no fees, no intraday activity | Backtesting; the PLA test benchmark |
| **Risk-theoretical P&L (RTPL)** | P&L predicted by the **risk model** for that same static position and market move | The PLA test candidate |
| **Clean P&L** | Loosely, P&L excluding fees/commissions/reserves; often a synonym for HPL, but institution-specific — **always ask for the local definition** | Internal analysis |
| **Carry P&L** | The portion of P&L from the passage of time — accrual, roll-down, funding | P&L explain |

The FRTB **P&L Attribution test** compares HPL with RTPL. If the risk model's prediction of the day's P&L systematically diverges from what a static portfolio would actually have earned, the model is not describing the portfolio, and the desk loses the right to use it for capital ([15](15_Backtesting.md), [18](18_FRTB_Internal_Models_Approach.md)).

---

## 9. Economic risk versus regulatory capital

A bank computes two families of numbers over the same positions, for two different purposes. Confusing them is the most common conceptual error made by newcomers.

| | **Internal / economic risk** | **Regulatory capital** |
|---|---|---|
| Question answered | What might we actually lose? | How much capital must we legally hold? |
| Chosen by | The bank | The regulator |
| Metrics | VaR, ES, stress, sensitivities, limits | FRTB SA (SBM + DRC + RRAO), FRTB IMA |
| Calibration | The bank's own view of plausible severity | Prescribed parameters, prescribed confidence, prescribed horizons |
| Can be changed by | Management decision | Rulemaking only |
| Cadence | Daily, often intraday | Daily calculation, quarterly/periodic reporting |

The regulatory number is deliberately **conservative and standardised** — designed to be comparable across banks and robust to model gaming. The internal number is designed to be **accurate and decision-useful**. A bank's FRTB SA capital charge on a portfolio may be several multiples of its internal 99% VaR, and that is not evidence that either is wrong; they are answering different questions.

Both are needed. The internal number runs the business; the regulatory number constrains its size. See [42](42_Risk_Aggregation.md) and [29](29_Regulatory_Framework.md).

---

## 10. Trading book versus banking book — first pass

Because the capital consequences are so large, the boundary is a regulated object in its own right, defined in `RBC25` of the consolidated Basel Framework.

| | **Trading book** | **Banking book** |
|---|---|---|
| Intent | Held for trading / to hedge trading book | Held to maturity / for the banking franchise |
| Accounting | Fair value through P&L | Amortised cost or OCI, depending on classification |
| Typical contents | Market-making inventory, derivatives, repo book | Loans, deposits, HTM securities, funding |
| Capital framework | Market risk (FRTB) | Credit risk RWA; interest-rate risk via **IRRBB** (Pillar 2) |
| Risk measured as | VaR, ES, sensitivities, stress | EVE and NII sensitivity |

Basel imposes **presumptive assignments** for certain instrument classes and severely restricts moving instruments between books after initial designation, precisely because the boundary is an arbitrage opportunity: an institution that could reclassify a losing position out of the fair-valued trading book into the accrual banking book could make a loss disappear from its reported P&L. Full treatment in [20](20A_Trading_Book_Boundary_and_IRRBB.md).

---

## 11. The measurement chain, end to end

This is the spine of the entire knowledge base. Every document below is an expansion of one link in it.

```
     MARKET DATA                        Prices, yields, quotes, vols, spreads       ─► doc 23
          │                             validated · cleaned · normalised
          ▼
     CURVE / SURFACE CONSTRUCTION       Bootstrapping, interpolation, calibration   ─► doc 23
          │
          ▼
     RISK FACTORS                       The modelled observables                    ─► doc 33
          │
          ▼
     PRICING / VALUATION                PV of each position                         ─► doc 03
          │
          ├──────────────► SENSITIVITIES     DV01, CS01, Greeks                     ─► doc 04-09
          │                     │
          ▼                     ▼
     SCENARIO P&L          AGGREGATION       across desk, entity, factor            ─► doc 42
          │                     │
          ├─────────┬───────────┴──────────┐
          ▼         ▼                      ▼
        VaR        ES                   STRESS                                      ─► doc 11,12,13
          │         │                      │
          └────┬────┴──────────────────────┘
               │
       ┌───────┴────────┬──────────────────┐
       ▼                ▼                  ▼
    LIMITS        REGULATORY CAPITAL     REPORTING                                  ─► doc 21,16-20,28
       │                │                  │
       ▼                ▼                  ▼
    BREACH          FRTB SA / IMA       DASHBOARDS, REGULATORY RETURNS
    ESCALATION
```

Two properties of this chain deserve emphasis:

1. **It is strictly ordered.** You cannot compute VaR without a pricing function; you cannot price without curves; you cannot build curves without validated market data. A market-data failure at 06:00 propagates to a missing regulatory return at 18:00. This is why data quality controls ([27](27_Controls_and_Governance.md)) are not a peripheral concern.

2. **Errors amplify downward, not upward.** A one-basis-point error in a curve node is invisible; the same error propagated into a 10-year DV01 on a large book, then into a stressed revaluation, then into a capital charge, is not.

---

## 12. Market risk in the taxonomy of bank risks

Market risk is one risk among several, and precision about the boundaries is required. Full comparison in [41](41_Market_Risk_vs_Related_Risk_Types.md).

| Risk | One-line distinction from market risk |
|---|---|
| **Credit risk** | Loss because a *borrower* fails to pay. Market risk is loss because a *price* moved. |
| **Counterparty credit risk (CCR)** | Loss because a *derivative counterparty* defaults while owing you mark-to-market. Sits at the intersection: the exposure amount is driven by market factors. |
| **CVA risk** | Loss from the change in value of the *credit adjustment* on derivatives — market-driven, but separately capitalised. |
| **Liquidity risk** | Loss because you cannot fund or cannot exit. Related to, but distinct from, market risk — FRTB partially internalises it via **liquidity horizons**. |
| **Operational risk** | Loss from failed processes, systems or people. |
| **Model risk** | Loss from using a wrong or misapplied model — including the market risk models themselves. |
| **IRRBB** | Interest-rate risk in the *banking* book. Same underlying driver, different book, different framework. |

> The most common misclassification in practice is treating **everything with a price** as market risk. A defaulted loan's recovery uncertainty is credit risk even though recovery has a price. Correct classification determines which framework capitalises it, and double-counting or gapping between frameworks is a genuine supervisory concern.

---

## 13. What "good" looks like

A mature market risk function can answer all ten of the following on demand, for any level of the hierarchy, on any business day:

1. **What is our exposure?** — sensitivities by factor, tenor, currency, issuer.
2. **What did we make or lose, and why?** — P&L explained to within a small unexplained residual.
3. **What might we lose tomorrow?** — VaR and ES, with the model's assumptions stated.
4. **What might we lose in a crisis?** — stress results against named, dated scenarios.
5. **Are we within limits?** — utilisation, breaches, escalation status.
6. **Is our model any good?** — backtesting exceptions, PLA zone, validation status.
7. **What capital does this consume?** — SA and, where approved, IMA.
8. **What is concentrated?** — top exposures by issuer, factor, tenor, country.
9. **What changed since yesterday?** — risk deltas, and their attribution to new trades versus market moves.
10. **What do we not know?** — NMRFs, proxies, valuation uncertainty, model limitations.

The tenth is the one that separates a competent function from a merely compliant one. See [26](26_Model_Risk_and_Validation.md).

---

## 14. Regulatory Relevance

| Concept in this document | Basel reference | Notes |
|---|---|---|
| Trading book / banking book boundary | `RBC25` | Presumptive lists, switching restrictions, internal risk transfers |
| Market risk terminology | `MAR10` | Basel's own definitions of the vocabulary used here |
| Definition and scope of market risk | `MAR11` | Which risks must be capitalised as market risk |
| Definition of a trading desk | `MAR12` | The regulatory unit for IMA approval |

All Basel citations in this knowledge base refer to the consolidated Basel Framework and to *Minimum capital requirements for market risk*, BCBS d457, January 2019 (rev. February 2019). See [45](45_Source_Register.md).

---

## 15. Limitations of this document

- It is deliberately conceptual. Every quantity named here is defined precisely elsewhere in the library; nothing here should be used as a formula reference.
- The organisational vocabulary (desk, book, business line) varies between institutions. The *regulatory* definitions (`MAR12` trading desk, `RBC25` book boundary) do not, and are the ones to rely on in any capital context.
- Jurisdictional implementation of the Basel standard differs materially and is in flux as at the date of this document. See [29](29_Regulatory_Framework.md) for the status tracker.

---

## 16. Related Concepts

- [02 — Financial Instruments](02_Financial_Instruments.md) — what banks actually hold
- [03 — Pricing Fundamentals](03_Pricing_Fundamentals.md) — how a position gets a value
- [04 — Interest Rate Risk](04_Interest_Rate_Risk.md) — the sensitivity family, in full
- [11 — Value at Risk](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [16 — FRTB Overview](16_FRTB_Overview.md)
- [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `RBC25`, `MAR10`–`MAR12` definitions used throughout |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Authoritative current text of RBC/MAR chapters |
| BCBS | *The market risk framework — In brief* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_inbrief.pdf | Plain-language summary of framework intent |

*Accessed 25 August 2026.*
