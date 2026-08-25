# 06 — Foreign Exchange Risk

**Level:** 4 · **Prerequisites:** [03](03_Pricing_Fundamentals.md), [04](04_Interest_Rate_Risk.md) · **Feeds:** [09](09_Options_and_Greeks.md), [17](17_FRTB_Standardised_Approach.md)

---

## 1. Plain English

**FX risk is the risk of loss because the value of one currency changed relative to another.**

It is the one market risk a bank cannot opt out of. A bank reports in one currency. Every asset, liability, revenue and cost denominated in another currency carries FX risk **whether or not the bank ever traded a currency pair.**

---

## 2. Banking example

A U.S. bank holds €100 million of German government bonds, unhedged.

EUR/USD moves from 1.1000 to 1.0800.

```
Value before  =  €100,000,000 × 1.1000  =  $110,000,000
Value after   =  €100,000,000 × 1.0800  =  $108,000,000
Loss                                     =    $2,000,000
```

The euro value of the bonds did not change by a cent. The bunds are worth exactly what they were worth. The **reporting currency** changed, and that is a real, booked, capital-reducing loss.

---

## 3. Net Open Position — the foundational FX metric

### 3.1 Plain English

Add up everything you own in a currency, subtract everything you owe in it. What is left is exposed.

### 3.2 Formula

```
NOP(ccy)  =  Spot assets − Spot liabilities
           + Net forward position
           + Net delta-equivalent of FX options
           + Accrued but unrealised income/expense
           + Structural positions (if included by policy)
```

### 3.3 Numerical example

A bank's EUR book:

| Component | EUR |
|---|---|
| Spot assets (bonds, loans, cash) | +250,000,000 |
| Spot liabilities (deposits, issued debt) | −180,000,000 |
| Net forward purchases | +40,000,000 |
| Net forward sales | −75,000,000 |
| FX option delta equivalent | +12,000,000 |
| Accrued interest receivable | +3,000,000 |
| **Net Open Position** | **+50,000,000** |

The bank is **long €50m**. At 1.0850, that is $54.25m of exposure. A 1% adverse move costs roughly $542,500.

### 3.4 The three sub-questions the NOP hides

| Question | Why it matters |
|---|---|
| Is it **overnight or intraday**? | Intraday flows can dwarf the reported end-of-day NOP |
| Is it **structural or trading**? | Structural (subsidiary net investment) is often excluded from trading limits and hedged separately |
| Is it **deliverable**? | A CNH position is not a CNY position; an NDF is not a forward |

---

## 4. FX forwards and covered interest parity

### 4.1 The relationship

An FX forward's rate is not a forecast. It is arithmetic on two interest rates:

```
                  1 + r_quote · τ
   F  =  S ·  ───────────────────────
                  1 + r_base · τ
```

or continuously: `F = S · e^((r_q − r_b)·τ)`.

**Why it must hold.** To deliver EUR in one year you can either buy the forward, or borrow USD, buy EUR spot, and deposit the EUR for a year. Both routes deliver the same thing; both must therefore cost the same, or there is an arbitrage.

### 4.2 Numerical example

`S` = 1.0850 (USD per EUR), USD 1y rate 4.50%, EUR 1y rate 3.00%, τ = 1.

```
F  =  1.0850 × (1.045 / 1.030)  =  1.0850 × 1.014563  =  1.1008
```

**Forward points** = `(1.1008 − 1.0850) × 10,000 = 158 pips`.

The euro trades at a **forward premium** because euro rates are lower. This is not a market view that EUR will rise; it is the compensation for the interest differential. Confusing the two is the single most common misreading of a forward curve.

### 4.3 The critical risk insight

> **An FX forward is not one risk. It is three.**

A one-year EUR/USD forward has:
1. **FX spot delta** — the position moves with `S`
2. **USD interest-rate DV01** — through the USD discounting leg
3. **EUR interest-rate DV01** — through the EUR leg

A risk system reporting only spot delta on a forward book has missed both rate legs. For a large, long-dated forward book those legs can carry more DV01 than a mid-sized swap desk.

---

## 5. Cross-currency basis

### 5.1 What it is

Covered interest parity **has not held exactly since 2008**. The residual — the extra spread that must be paid to swap one currency into another — is the **cross-currency basis**.

```
   F_observed   =   S · (1 + r_q·τ) / (1 + (r_b + basis)·τ)
```

### 5.2 Why it exists

- Post-crisis balance-sheet costs and leverage-ratio constraints on arbitrage
- Regulatory constraints on the banks that would otherwise close it
- Structural demand for dollar funding by non-U.S. institutions
- Quarter-end and year-end reporting effects, which produce sharp, predictable spikes

### 5.3 Why it is a first-class risk factor

`MAR21.50` assigns the correlation between a cross-currency basis sensitivity and:
- a given tenor of the relevant yield curve → **0%**
- the inflation curve → **0%**
- another cross-currency basis curve → **0%**

**Basel grants no offset whatsoever.** That is a deliberate statement: the basis is not a residual of the rate curves, it is its own risk, and a bank cannot claim diversification against it.

Its GIRR risk weight is **1.6%** (`MAR21.43`), the same as inflation.

### 5.4 The CSA consequence

A USD-denominated swap collateralised in EUR is discounted on a curve that embeds the EUR/USD basis. **A pure interest-rate swap book with a foreign-currency CSA has cross-currency basis exposure.** This is invisible to any system that does not model the CSA. It is one of the most commonly missed exposures in mid-sized institutions.

---

## 6. FX options

### 6.1 The FX quoting convention

FX options are quoted differently from every other asset class — **by delta rather than by strike**, and in three building blocks:

| Quote | Meaning | What it captures |
|---|---|---|
| **ATM volatility** | Volatility at the at-the-money strike | Level |
| **Risk reversal (RR)** | `σ(25Δ call) − σ(25Δ put)` | **Skew** — the market's directional fear |
| **Butterfly (BF)** | `½[σ(25Δ call) + σ(25Δ put)] − σ_ATM` | **Smile curvature** — tail fear both ways |

Reconstructing strike volatilities:

```
   σ(25Δ call)  =  σ_ATM  +  BF  +  RR/2
   σ(25Δ put)   =  σ_ATM  +  BF  −  RR/2
```

### 6.2 Worked example

`σ_ATM` = 8.0%, 25Δ RR = −0.8% (puts bid — the market fears EUR downside), 25Δ BF = 0.25%.

```
   σ(25Δ call)  =  8.0 + 0.25 + (−0.4)  =  7.85%
   σ(25Δ put)   =  8.0 + 0.25 − (−0.4)  =  8.65%
```

The negative risk reversal says the market pays up for downside protection. **This is directional information embedded in an options quote**, and it is traded in its own right.

### 6.3 Why vanna and volga are first-class FX risks

In equity options, vanna and volga are refinements. In FX they are **daily desk risks**, because the skew itself moves a great deal and is separately traded.

| Greek | Definition | FX meaning |
|---|---|---|
| **Vanna** | `∂²V/∂S∂σ` | How vega changes as spot moves — exposure to the *skew* |
| **Volga (vomma)** | `∂²V/∂σ²` | How vega changes as vol moves — exposure to the *smile* |

The market-standard "vanna-volga" pricing approach for FX exotics exists precisely because these two second-order sensitivities carry so much of the value in that market.

---

## 7. Translation vs transaction exposure

| | **Transaction exposure** | **Translation (structural) exposure** |
|---|---|---|
| Arises from | A contracted cash flow in foreign currency | Consolidating a foreign subsidiary's net assets |
| Hits | P&L directly | Other comprehensive income / reserves |
| Horizon | Days to months | Indefinite |
| Managed by | Trading desk, within FX limits | Treasury/ALM, by policy |
| In the trading NOP? | Yes | **Usually excluded, by explicit policy** |

> The exclusion of structural positions from the trading NOP is legitimate and near-universal — but it must be an *explicit, documented, governed* exclusion. An undocumented exclusion is how a large currency exposure ends up in no one's report.

---

## 8. FRTB treatment

### 8.1 Risk factors (`MAR21.14`)

The FX delta risk factors are **all exchange rates between the currency in which an instrument is denominated and the reporting currency.** For a transaction referencing two non-reporting currencies, the risk factors are the rates between the reporting currency and *each* of the currencies involved.

Subject to supervisory approval, a bank may compute FX risk relative to a **base currency** rather than the reporting currency (`MAR21.14(1)(b)`), but it must then also capture the **translation risk** between reporting and base currency, and may nominate only one base currency.

### 8.2 Risk weight (`MAR21.87`–`MAR21.88`)

> **A unique relative risk weight equal to 15% applies to all the FX sensitivities.** (`MAR21.87`)

For a Basel-specified list of currency pairs — and for first-order crosses across them — the risk weight may at the bank's discretion be divided by **√2**, giving approximately 10.61%.

The specified pairs (`MAR21.88`, footnote 22):

```
USD/EUR   USD/JPY   USD/GBP   USD/AUD   USD/CAD   USD/CHF   USD/MXN
USD/CNY   USD/NZD   USD/RUB   USD/HKD   USD/SGD   USD/TRY   USD/KRW
USD/SEK   USD/ZAR   USD/INR   USD/NOK   USD/BRL
```

Footnote 23 gives the crosses rule by example: *EUR/AUD* is not on the list but is a first-order cross of USD/EUR and USD/AUD, so it qualifies.

### 8.3 Correlation (`MAR21.89`)

Across FX buckets (each currency pair being a bucket), the correlation parameter γ is uniformly **60%**.

### 8.4 Vega

FX vega uses a regulatory liquidity horizon of **40** in `MAR21.92` Table 13, with the risk weight determined by the standard formula in which σ is set at 55%.

### 8.5 IMA liquidity horizons (`MAR33.12`, Table 2)

| Risk factor category | Liquidity horizon (days) |
|---|---|
| FX rate: **specified** currency pairs | **10** |
| FX rate: other currency pairs | **20** |
| FX: volatility | **40** |
| FX: other types | **40** |

The specified-pair list for liquidity-horizon purposes (footnote 1 to Table 2) is the `MAR21.88` list **plus EUR/JPY, EUR/GBP, EUR/CHF and JPY/AUD**, together with first-order crosses across them. Note carefully: **the two specified lists are not identical**, and using the SBM list for the IMA horizon is a real and easily-made implementation error.

---

## 9. Worked example — a full FX book

**Portfolio** (reporting currency USD):

| Position | Amount | Rate | USD equivalent |
|---|---|---|---|
| Long EUR spot | +€80,000,000 | 1.0850 | +$86,800,000 |
| Short GBP spot | −£40,000,000 | 1.2700 | −$50,800,000 |
| Long JPY spot | +¥6,000,000,000 | 0.00680 | +$40,800,000 |
| Long EUR 1y forward | +€30,000,000 | 1.1008 | +$33,024,000 |
| EUR call option delta | +€15,000,000 | 1.0850 | +$16,275,000 |

**Net open positions:**

| Currency | NOP (local) | NOP (USD) |
|---|---|---|
| EUR | +125,000,000 | +$136,099,000 |
| GBP | −40,000,000 | −$50,800,000 |
| JPY | +6,000,000,000 | +$40,800,000 |

**Scenario: USD strengthens 5% against everything.**

```
EUR:  +136,099,000 × (−5%)  =  −$6,804,950
GBP:   −50,800,000 × (−5%)  =  +$2,540,000
JPY:   +40,800,000 × (−5%)  =  −$2,040,000
                       Net  =  −$6,304,950
```

**SBM FX delta capital (medium correlation scenario), before considering the √2 discount:**

Weighted sensitivities, each = |NOP| × 15%:

```
   WS_EUR  =  136,099,000 × 0.15  =  20,414,850
   WS_GBP  =  −50,800,000 × 0.15  =  −7,620,000
   WS_JPY  =   40,800,000 × 0.15  =   6,120,000
```

Aggregating across buckets with γ = 60%:

```
   K² = ΣWS² + 2γ·Σ_{b<c} WS_b·WS_c

   ΣWS²  = 20,414,850² + (−7,620,000)² + 6,120,000²
         = 4.1677e14 + 5.8064e13 + 3.7454e13  =  5.1229e14

   Σ pairs = (20,414,850)(−7,620,000) + (20,414,850)(6,120,000)
             + (−7,620,000)(6,120,000)
           = −1.5556e14 + 1.2494e14 − 4.6634e13  =  −7.7254e13

   K² = 5.1229e14 + 2(0.60)(−7.7254e13) = 5.1229e14 − 9.2705e13 = 4.1959e14

   K  = $20,483,800   (approximately)
```

Note that the short GBP position produces genuine diversification benefit — the delta capital of $20.5m is below the $34.2m simple sum of the weighted sensitivities. **Under the "high correlation" scenario** γ becomes 0.75 and the charge rises; under "low" it becomes `max(2×0.6−1, 0.75×0.6) = max(0.20, 0.45) = 45%` and the charge falls. The reported capital is the **maximum across the three** (`MAR21.7`).

---

## 10. Stress scenarios

| Scenario | Date | Character |
|---|---|---|
| **CHF de-peg** | 15 Jan 2015 | SNB abandons the 1.20 EUR/CHF floor; CHF appreciates violently intraday; several brokers fail |
| **GBP referendum** | 24 Jun 2016 | GBP gaps overnight on the Brexit result |
| **JPY depreciation** | 2022 | Sustained trend move on policy divergence |
| **EM currency crisis** | various | Sharp depreciation plus capital controls plus liquidity collapse |
| **Peg break** | generic | A managed rate ceases to be managed — the defining FX tail event |

> **The CHF lesson is the most important one in FX risk.** A pegged or managed currency shows near-zero historical volatility right up until the moment the peg breaks. Every VaR model calibrated on that history reported almost no risk. Peg regimes must be stressed by **scenario**, never trusted to **history** — a point that generalises to any market variable whose stability is a policy choice rather than an economic fact.

---

## 11. Pseudocode

```
FUNCTION net_open_position(positions, ccy, spot_rates, reporting_ccy):
    nop = 0
    FOR p IN positions WHERE p.currency == ccy:
        IF   p.type == "SPOT":     nop += p.amount
        ELIF p.type == "FORWARD":  nop += p.amount            # notional, both legs
        ELIF p.type == "OPTION":   nop += p.delta * p.notional
        ELIF p.type == "ACCRUAL":  nop += p.accrued
    IF  policy.exclude_structural:
        nop -= structural_position(ccy)                        # documented exclusion
    RETURN nop, nop * spot_rates[ccy, reporting_ccy]


FUNCTION fx_forward_pv(notional_base, K, S, df_base, df_quote, tau):
    # value of a forward to buy base currency at rate K, in quote-currency terms
    F  = S * df_base / df_quote
    RETURN notional_base * (F - K) * df_quote


FUNCTION sbm_fx_delta_capital(nops_usd, scenario):
    RW    = 0.15                       # MAR21.87; /sqrt(2) for specified pairs
    WS    = { ccy: nop * rw_for(ccy) for ccy, nop in nops_usd }
    gamma = apply_scenario(0.60, scenario)      # MAR21.89
    K_sq  = sum(ws*ws for ws in WS.values())
    FOR each unordered pair (b, c):
        K_sq += 2 * gamma * WS[b] * WS[c]
    RETURN sqrt(max(K_sq, 0))
```

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | NOP completeness | Spot + forward + option delta + accruals all included |
| 2 | Triangular consistency | EUR/USD × USD/JPY ≈ EUR/JPY, within bid-offer |
| 3 | Forward = CIP + basis | Residual equals observed basis and nothing else |
| 4 | Forward rate legs | Both currencies' DV01 reported, not spot delta alone |
| 5 | Option delta convention | Premium-adjusted vs plain delta stated explicitly |
| 6 | Structural exclusion | Documented, approved, reconciled |
| 7 | CSA discounting | Foreign-currency CSAs produce basis sensitivity |
| 8 | Deliverability | CNY and CNH held as separate risk factors |
| 9 | Specified-pair lists | `MAR21.88` list used for SBM; `MAR33.12` list used for liquidity horizons — **not interchanged** |
| 10 | Reporting currency | All FX sensitivities expressed against the reporting currency, per `MAR21.14` |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Spot delta only on forwards | Both interest-rate legs unreported |
| Treating forward points as a forecast | Systematic misinterpretation of the curve |
| Ignoring cross-currency basis | Funding and CSA exposure invisible |
| Netting CNY against CNH | Onshore/offshore basis unmeasured |
| Applying the SBM specified-pair list to liquidity horizons | Wrong IMA horizon on EUR/JPY, EUR/GBP, EUR/CHF, JPY/AUD |
| Trusting a pegged currency's historical volatility | Tail risk reported as approximately zero |
| Undocumented structural exclusion | Real exposure appears in no report |
| Mixing delta conventions (spot vs forward vs premium-adjusted) | Hedge ratios systematically off |

---

## 14. Limitations

- FX return distributions are fat-tailed and, for managed currencies, **regime-dependent** in a way that no stationary model captures.
- The NOP is a *linear* summary. An options book with significant gamma is not described by its delta.
- Pegged and heavily-managed currencies invalidate historical-simulation approaches, essentially by construction.
- Capital controls and non-deliverability introduce risks with no price series at all.

---

## 15. Related Concepts

- [04 — Interest Rate Risk](04_Interest_Rate_Risk.md) · [09 — Options and Greeks](09_Options_and_Greeks.md)
- [13 — Stress Testing](13_Stress_Testing.md) · [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.14`, `MAR21.87`–`MAR21.89`, `MAR21.92`, `MAR33.12` |
| BIS | Quarterly Review — covered interest parity deviations | various | https://www.bis.org/publ/qtrpdf/ | Cross-currency basis mechanics |
| SNB | Discontinuation of the minimum exchange rate | 15 Jan 2015 | https://www.snb.ch/ | CHF de-peg event |

*Accessed 25 August 2026.*
