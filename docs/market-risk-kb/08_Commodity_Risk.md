# 08 — Commodity Market Risk

**Level:** 4 · **Prerequisites:** [02](02_Financial_Instruments.md), [03](03_Pricing_Fundamentals.md) · **Feeds:** [17](17_FRTB_Standardised_Approach.md)

---

## 1. Plain English

**Commodity risk is the risk of loss because the price of a physical good changed.**

Commodities differ from every other asset class in one respect that drives all the rest: **they are physical.** They must be stored, transported, insured and delivered. Storage costs money. Transport takes time. Quality varies. Delivery location matters. Every one of those facts becomes a risk factor.

---

## 2. Banking example

A bank is long 1,000 WTI crude futures for December delivery, at $70.00/barrel. Each contract is 1,000 barrels.

```
Notional  =  1,000 × 1,000 × $70.00  =  $70,000,000
```

The price falls to $67.00.

```
Loss  =  1,000 × 1,000 × $3.00  =  $3,000,000
```

Straightforward. Now note what the futures position does *not* tell you: whether the whole curve moved or only December; whether Brent moved with WTI; whether the loss would have been avoidable by rolling; and whether, at expiry, the bank is contractually obliged to take delivery of a million barrels of oil in Cushing, Oklahoma.

---

## 3. The forward curve — the defining structure

### 3.1 Contango and backwardation

| Shape | Definition | Roll consequence for a long |
|---|---|---|
| **Contango** | Futures price > spot; curve slopes **up** | **Negative roll yield** — sell cheap expiring, buy expensive next |
| **Backwardation** | Futures price < spot; curve slopes **down** | **Positive roll yield** — sell expensive expiring, buy cheap next |

### 3.2 The theoretical relationship

```
   F(T)  =  S · e^((r + u − y)·T)
```

| Term | Meaning |
|---|---|
| `r` | Risk-free financing rate |
| `u` | Storage cost rate (positive: storage costs money) |
| `y` | **Convenience yield** — the benefit of holding the physical good |

**Convenience yield is the residual that makes the equation balance**, and it is a genuine economic concept: a refinery that runs out of crude stops running, so holding physical inventory has option-like value that a futures contract does not confer. When inventories are scarce, convenience yield spikes and the curve inverts into backwardation.

### 3.3 Why roll yield dominates

**Worked example.** Long WTI, held one year, spot unchanged at $70. The curve is in contango with each successive month $0.50 higher.

Rolling monthly, twelve times, each roll costs approximately $0.50:

```
   Roll cost  =  12 × $0.50  =  $6.00/barrel  =  −8.6% of the position
```

**The spot price did not move, and the position lost 8.6%.** Over multi-year horizons roll yield frequently exceeds the cumulative spot move — which is why commodity index products can lose money in a flat or gently rising market, and why "long oil" and "long the oil future" are materially different positions.

---

## 4. Basis risks — the commodity speciality

Commodity basis risk is richer than in any other asset class because the underlying is physical.

| Basis | The two legs | Driver |
|---|---|---|
| **Location** | WTI (Cushing) vs Brent (North Sea); Henry Hub vs TTF | Transport capacity, pipeline constraints, export infrastructure |
| **Grade / quality** | Light-sweet vs heavy-sour crude; protein content in wheat | Refining economics; end-use requirements |
| **Calendar** | Dec-25 vs Jun-26 | Inventory, seasonality, storage capacity |
| **Product / crack** | Crude vs refined products | Refining margin and capacity |
| **Time-of-delivery** | Peak vs off-peak electricity | Non-storability of power |

> **A location basis can move more than the outright price.** In 2011–13 the WTI–Brent spread moved from near parity to over $25/barrel as U.S. shale production overwhelmed pipeline capacity out of Cushing. A "hedged" position — long WTI, short Brent — would have sustained losses far larger than the flat-price risk it was constructed to avoid.

---

## 5. Electricity — the special case

Electricity deserves separate treatment because it violates the storage assumption underlying all commodity curve mathematics.

| Property | Consequence |
|---|---|
| **Not economically storable at scale** | No cash-and-carry arbitrage; `F ≠ S·e^(cost)`; the curve is pure expectation |
| **Instantaneous supply-demand balance** | Prices spike by orders of magnitude within an hour |
| **Negative prices occur** | Must-run generation plus excess renewables |
| **Extreme seasonality and time-of-day structure** | Peak and off-peak are genuinely distinct commodities |

FRTB recognises this explicitly. `MAR21.84(1)(a)`: for bucket 3 (energy — electricity and carbon trading), *"Each time interval (i) at which the electricity can be delivered and (ii) that is specified in a contract that is made on a financial market is considered a distinct electricity commodity (eg peak and off-peak)."*

**Lognormal models are inapplicable to power.** Prices can be negative, and the spike behaviour is not diffusive. Jump-diffusion or regime-switching models are the usual response, and stress testing matters more here than almost anywhere else.

---

## 6. FRTB treatment

### 6.1 Risk factors

- **Delta:** commodity spot/forward prices, by commodity, by tenor, by delivery location
- **Vega:** implied volatilities of commodity options
- **Curvature:** commodity prices

### 6.2 Buckets and risk weights (`MAR21.82`, Tables 11)

| Bucket | Commodity bucket | Examples (non-exhaustive) | **Risk weight** |
|---|---|---|---|
| 1 | Energy — solid combustibles | Coal, charcoal, wood pellets, uranium | **30%** |
| 2 | Energy — liquid combustibles | Light-sweet/heavy crude, WTI, Brent; biofuels; petrochemicals; refined fuels | **35%** |
| 3 | Energy — electricity and carbon trading | Spot/day-ahead/peak/off-peak electricity; CERs, EU allowances, RGGI CO₂, RECs | **60%** |
| 4 | Freight | Capesize, Panamax, Handysize, Supramax; Suezmax, Aframax, VLCCs | **80%** |
| 5 | Metals — non-precious | Aluminium, copper, lead, nickel, tin, zinc; steel raw materials; minor metals | **40%** |
| 6 | Gaseous combustibles | Natural gas, LNG | **45%** |
| 7 | Precious metals (including gold) | Gold, silver, platinum, palladium | **20%** |
| 8 | Grains and oilseed | Corn, wheat, soybean complex, oats, palm oil, canola, barley, rice, etc. | **35%** |
| 9 | Livestock and dairy | Live/feeder cattle, hog, poultry, lamb, fish, shrimp, milk, whey, eggs, butter, cheese | **25%** |
| 10 | Softs and other agriculturals | Cocoa, coffee, tea, citrus/orange juice, potatoes, sugar, cotton, wool, lumber, pulp, rubber | **35%** |
| 11 | Other commodity | Potash, fertilizer, phosphate rocks; rare earths, terephthalic acid, flat glass | **50%** |

**Freight at 80% is the highest risk weight in the entire SBM commodity table** — higher than electricity. Shipping rates are extraordinarily volatile, non-storable, and driven by a capacity cycle measured in years.

**Precious metals at 20% is the lowest**, reflecting deep liquidity, low storage cost relative to value, and monetary-asset characteristics.

### 6.3 Intra-bucket correlations (`MAR21.83`, Table 12)

```
   ρ_kl  =  ρ(commodity)  ×  ρ(tenor)  ×  ρ(basis)
```

| Factor | Same | Different |
|---|---|---|
| `ρ(commodity)` | 1 | Table 12 value (below) |
| `ρ(tenor)` | 1 | **99.00%** |
| `ρ(basis)` — delivery location | 1 | **99.90%** |

Table 12 values of `ρ(commodity)`:

| Bucket | Commodity bucket | ρ(cty) |
|---|---|---|
| 1 | Energy — solid combustibles | **55%** |
| 2 | Energy — liquid combustibles | **95%** |
| 3 | Energy — electricity and carbon trading | **40%** |
| 4 | Freight | **80%** |
| 5 | Metals — non-precious | **60%** |
| 6 | Gaseous combustibles | **65%** |
| 7 | Precious metals (including gold) | **55%** |
| 8 | Grains and oilseed | **45%** |
| 9 | Livestock and dairy | **15%** |
| 10 | Softs and other agriculturals | **40%** |
| 11 | Other commodity | **15%** |

**Worked example from the standard's own footnote 21** — the correlation between a sensitivity to Brent, one-year tenor, delivered at Le Havre and a sensitivity to WTI, five-year tenor, delivered at Oklahoma:

```
   ρ  =  95%  ×  99.00%  ×  99.90%  =  93.96%
```

Two readings worth taking from Table 12:

- **Bucket 2 at 95%** says two different crude grades are nearly perfect substitutes for capital purposes — which is why a WTI/Brent basis position receives almost full offset in the SBM, and why the framework's treatment can understate a location-basis blowout of the kind described in §4.
- **Buckets 9 and 11 at 15%** say livestock/dairy and "other commodity" constituents are nearly unrelated — a hog position gets almost no offset against a milk position.

`MAR21.85` sets the cross-bucket correlation parameter γ for aggregating delta commodity risk across buckets.

### 6.4 Vega

Commodity vega uses a regulatory liquidity horizon of **120** in `MAR21.92` Table 13 — the longest alongside CSR — with the risk weight determined by the standard formula in which σ is set at 55%.

### 6.5 IMA liquidity horizons (`MAR33.12`, Table 2)

| Risk factor category | Liquidity horizon (days) |
|---|---|
| Energy and carbon emissions trading **price** | **20** |
| Precious metals and non-ferrous metals **price** | **20** |
| Other commodities **price** | **60** |
| Energy and carbon emissions trading price: **volatility** | **60** |
| Precious metals and non-ferrous metals price: **volatility** | **60** |
| Other commodities price: **volatility** | **120** |
| Commodity: **other types** | **120** |

---

## 7. Worked example — a commodity book

**Portfolio:**

| Position | Contracts | Unit | Price | Notional |
|---|---|---|---|---|
| Long WTI Dec-26 | +1,000 | 1,000 bbl | $70.00 | +$70,000,000 |
| Short Brent Dec-26 | −900 | 1,000 bbl | $74.00 | −$66,600,000 |
| Long Henry Hub Jan-27 | +500 | 10,000 MMBtu | $3.20 | +$16,000,000 |
| Long Gold Jun-27 | +200 | 100 oz | $2,400 | +$48,000,000 |

### 7.1 Scenario: crude falls 10%, gas falls 5%, gold rises 3%

```
WTI    :  +70,000,000 × (−10%)  =  −$7,000,000
Brent  :  −66,600,000 × (−10%)  =  +$6,660,000
Gas    :  +16,000,000 × (−5%)   =    −$800,000
Gold   :  +48,000,000 × (+3%)   =  +$1,440,000
                            Net  =    +$300,000
```

The crude spread position is nearly neutral to a parallel crude move — as designed.

### 7.2 Scenario: the WTI–Brent basis widens $5

WTI unchanged; Brent rises $5 to $79.

```
WTI    :  no change            =           $0
Brent  :  −900 × 1,000 × $5    =  −$4,500,000
                          Net  =  −$4,500,000
```

**The "hedged" position loses $4.5m from a basis move, while the outright 10% price move cost it nothing.** This is §4's point in numbers, and it is the single most important lesson in commodity risk management.

### 7.3 SBM delta capital, medium scenario (crude leg only)

Both WTI and Brent are in **bucket 2** (energy — liquid combustibles), RW **35%**, same tenor, different delivery locations.

```
   WS_WTI    =  +70,000,000 × 0.35  =  +24,500,000
   WS_Brent  =  −66,600,000 × 0.35  =  −23,310,000

   ρ  =  ρ(cty) × ρ(tenor) × ρ(basis)
      =  0.95   ×   1.00    ×  0.9990   =  0.94905

   K² =  24,500,000² + (−23,310,000)² + 2(0.94905)(24,500,000)(−23,310,000)
      =  6.00250e14  +  5.43356e14  −  1.08402e15
      =  4.5834e13

   K  =  $6,770,000   (approximately)
```

Against a **gross notional of $136.6m**, the delta charge on the spread is about $6.8m — the framework grants substantial but not complete offset, retaining a charge that is broadly consistent with the $4.5m basis loss in §7.2. Under the **low correlation scenario**, ρ becomes `max(2×0.94905 − 1, 0.75×0.94905) = max(0.89810, 0.71179) = 0.89810`, the offset shrinks, and the charge rises — which is precisely the mechanism `MAR21.6` exists to provide.

---

## 8. Stress scenarios

| Scenario | Date | Character |
|---|---|---|
| **Oil spike and collapse** | 2008 | $147 to $32 within six months |
| **Negative WTI** | 20 Apr 2020 | Front-month settled at **−$37.63**; storage at Cushing exhausted |
| **LME nickel squeeze** | Mar 2022 | Price doubled intraday; **the exchange cancelled trades** |
| **European gas** | 2021–22 | TTF rose by a multiple on supply disruption |
| **Freight rate cycle** | various | Baltic indices move by multiples over months |
| **Location basis blowout** | 2011–13 | WTI–Brent from parity to >$25 |

> **Two of these events are model-breaking rather than merely severe.**
>
> **Negative WTI** assigned a realised outcome probability zero under any lognormal model. The lesson is not "widen the distribution" — it is that a *structural* constraint (storage capacity) can bind and change the price process qualitatively.
>
> **The LME nickel cancellation** introduced a risk with no market-data representation at all: the exchange voided executed trades. No price series contains that event. It can only be addressed by scenario analysis and by governance, never by a statistical model. See [13](13_Stress_Testing.md).

---

## 9. Pseudocode

```
FUNCTION commodity_delta(position, curve, bump = 0.01):
    # bump is relative, per MAR21 commodity sensitivity definition
    up   = price(position, scale_curve(curve, 1 + bump))
    down = price(position, scale_curve(curve, 1 - bump))
    RETURN (up - down) / (2 * bump)


FUNCTION roll_yield(curve, front_tenor, next_tenor):
    F1 = curve[front_tenor]
    F2 = curve[next_tenor]
    RETURN (F1 - F2) / F1        # positive = backwardation = positive roll


FUNCTION sbm_commodity_bucket_capital(sensitivities, bucket, scenario):
    RW = commodity_rw(bucket)                      # Table 11
    WS = [ s.value * RW for s in sensitivities ]
    K_sq = sum(ws*ws for ws in WS)
    FOR each pair (k, l), k != l:
        rho = rho_commodity(k, l, bucket)          # Table 12, or 1 if same commodity
             * (1.0 if same_tenor(k,l)    else 0.9900)
             * (1.0 if same_location(k,l) else 0.9990)
        rho = apply_scenario(rho, scenario)
        K_sq += 2 * rho * WS[k] * WS[l]
    RETURN sqrt(max(K_sq, 0))
```

---

## 10. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Curve completeness | Every traded delivery month has a price |
| 2 | Roll yield reported | Separately from spot P&L |
| 3 | Location basis modelled | WTI and Brent as distinct risk factors, not one "crude" factor |
| 4 | Grade basis modelled | Where the book has quality exposure |
| 5 | Electricity granularity | Peak and off-peak held as distinct commodities per `MAR21.84` |
| 6 | Negative prices supported | Pricing and risk engines accept `F < 0` without error |
| 7 | Physical delivery | Contracts approaching delivery flagged; delivery capability confirmed |
| 8 | Unit consistency | Barrels, MMBtu, troy ounces, tonnes — conversions verified end-to-end |
| 9 | Bucket assignment | Every commodity mapped to one of the eleven buckets |
| 10 | Correlation triple | `ρ(cty) × ρ(tenor) × ρ(basis)` applied, not just `ρ(cty)` |
| 11 | Convenience yield | Implied residual reviewed for economic plausibility |

---

## 11. Common implementation errors

| Error | Consequence |
|---|---|
| Treating all crude as one risk factor | Location basis invisible (see §7.2) |
| Ignoring roll yield | Return attribution wrong; index products misunderstood |
| Lognormal price models | Cannot represent negative prices; broke in Apr 2020 |
| Treating electricity as storable | Curve mathematics invalid |
| Aggregating peak and off-peak power | Contradicts `MAR21.84`; understates risk |
| Unit conversion errors | Order-of-magnitude position errors |
| Missing physical delivery obligations | Operational and legal exposure at expiry |
| Applying `ρ(commodity)` alone | Ignores the 99.00% tenor and 99.90% location factors |

---

## 12. Limitations

- Commodity prices are driven by **physical supply and demand**, which respond to weather, geopolitics, infrastructure and policy — none of which is a financial variable and none of which is well described by a price history.
- Convenience yield is unobservable and backed out as a residual; it therefore absorbs every modelling error in the storage and financing assumptions.
- Non-storable commodities (electricity, freight) have no cash-and-carry relationship, so the entire forward-curve framework rests on expectation rather than arbitrage.
- Exchange intervention (position limits, trade cancellation, forced liquidation) is a real risk with no representation in any price series.

---

## 13. Related Concepts

- [02 — Financial Instruments](02_Financial_Instruments.md) · [13 — Stress Testing](13_Stress_Testing.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.82`–`MAR21.85` buckets, weights, correlations; `MAR21.92`; `MAR33.12` |
| CME Group | WTI crude oil futures contract specifications and 2020 settlement | 2020 | https://www.cmegroup.com/ | Negative settlement mechanics |
| LME | Nickel market events, March 2022 | 2022 | https://www.lme.com/ | Trade cancellation event |

*Accessed 25 August 2026.*
