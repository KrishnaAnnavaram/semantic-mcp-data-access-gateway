# 30 — Worked Examples

**Level:** 9 · **Prerequisites:** [03](03_Pricing_Fundamentals.md)–[13](13_Stress_Testing.md) · **Feeds:** [31](31_Master_Calculation_Catalog.md), [32](32_Master_Formula_Handbook.md)

> **Every figure in this document was computed, not asserted.** The Treasury portfolio in §1 is carried through pricing, duration, DV01, key-rate decomposition, curve scenarios, VaR, ES and stress — so each number can be checked against the one before it.

---

## 1. The Treasury portfolio

### 1.1 The book

Four U.S. Treasury positions, semiannual coupons, valued 24 August 2026.

| Bond | Maturity | Coupon | Face ($) |
|---|---|---|---|
| **2Y** | 2 years | 4.250% | 100,000,000 |
| **5Y** | 5 years | 4.000% | 150,000,000 |
| **10Y** | 10 years | 4.125% | 200,000,000 |
| **30Y** | 30 years | 4.500% | 50,000,000 |
| | | | **500,000,000** |

### 1.2 The curve

Continuously-compounded zero rates, linearly interpolated between nodes:

| Tenor | 0.5Y | 1Y | 2Y | 3Y | 5Y | 7Y | 10Y | 20Y | 30Y |
|---|---|---|---|---|---|---|---|---|---|
| **Zero rate** | 4.00% | 4.05% | 4.10% | 4.15% | 4.25% | 4.32% | 4.40% | 4.55% | 4.60% |

A gently upward-sloping curve — 2s30s of **50bp**.

---

## 2. Bond analytics

`DF(t) = e^(−z(t)·t)`; price is the sum of discounted cash flows; DV01 by **central** bump of ±1bp; convexity by ±100bp revaluation.

| Bond | Price ($) | % of face | YTM | Macaulay Dur. | DV01 ($/bp) | Convexity |
|---|---|---|---|---|---|---|
| **2Y** | 100,207,477 | 100.2075 | 4.1408% | 1.9385 | **19,425** | 3.83 |
| **5Y** | 148,080,820 | 98.7205 | 4.2870% | 4.5769 | **67,775** | 22.13 |
| **10Y** | 195,172,014 | 97.5860 | 4.4264% | 8.2602 | **161,215** | 76.96 |
| **30Y** | 49,281,139 | 98.5623 | 4.5887% | 16.5109 | **81,368** | 387.92 |
| **TOTAL** | **492,741,450** | | | | **329,783** | |

### 2.1 Reading the table

**Prices behave as the coupon-versus-market-rate rule requires.** The 2Y coupon (4.250%) exceeds its 4.1408% yield, so it trades **above par**. The other three have coupons below their yields and trade at a **discount**. ✓

**DV01 is not proportional to face value.** The 30Y is a quarter the size of the 10Y in face terms and carries **half** its DV01, because its duration is twice as long. The 2Y is twice the 30Y's face and carries **less than a quarter** of its DV01.

> This is precisely why the trading floor works in DV01 rather than notional ([04 §4.3](04_Interest_Rate_Risk.md)). "We hold $100m of 2Y and $50m of 30Y" says almost nothing about relative risk; "$19,425/bp and $81,368/bp" says it exactly.

**Convexity scales far faster than duration.** From the 2Y to the 30Y, duration multiplies by **8.5×** and convexity by **101×**. Convexity is roughly quadratic in maturity — which is why the long end dominates second-order effects and why convexity hedging is a long-end business.

---

## 3. The key-rate DV01 ladder

Each key rate is bumped ±1bp with a triangular (tent) shock, tapering to zero at the adjacent key rates. The outermost tents are **flat beyond the outer key rates** — the 2Y tent covers everything shorter, the 30Y tent everything longer — which is what makes the ladder complete.

| Bond | 2Y | 5Y | 10Y | 30Y | Row sum | Parallel DV01 |
|---|---|---|---|---|---|---|
| **2Y** | 19,425 | 0 | 0 | 0 | 19,425 | 19,425 |
| **5Y** | 3,483 | 64,293 | 0 | 0 | 67,775 | 67,775 |
| **10Y** | 4,788 | 14,400 | 142,027 | 0 | 161,215 | 161,215 |
| **30Y** | 1,306 | 3,927 | 20,293 | 55,841 | 81,368 | 81,368 |
| **TOTAL** | **29,002** | **82,620** | **162,320** | **55,841** | **329,783** | **329,783** |

### 3.1 The completeness check

```
   Σ KRD01  =  $329,783/bp
   Parallel DV01 =  $329,783/bp
   Difference    =  $0.00  (0.0000%)
```

**The tents sum exactly to a parallel shift**, so the ladder reconciles to the scalar to the last dollar. This is the mandatory reconciliation of [04 §5.4](04_Interest_Rate_Risk.md), and a failure would mean the bump scheme has a gap or an overlap.

### 3.2 What the off-diagonal entries mean

**Each bond has sensitivity to key rates shorter than its maturity, and none to longer ones.** The 30Y bond carries $20,293/bp at the 10Y node and $3,927/bp at the 5Y — because its intermediate coupons are discounted at those points of the curve.

**The 2Y bond is the only pure one**, with its entire DV01 at the 2Y node. That is not a property of two-year bonds in general; it is because the 2Y tent is flat below 2 years, so every cash flow of that bond sits inside a single tent.

> **Practical consequence: you cannot hedge the 10Y node by trading only the 10Y bond.** Selling the 10Y bond removes $142,027/bp at that node *and* $14,400/bp at the 5Y and $4,788/bp at the 2Y. Constructing a clean single-node hedge requires solving the full ladder simultaneously.

---

## 4. Curve scenario P&L

Full revaluation against the first-order KRD estimate, `ΔP ≈ −Σ KRD01(k) × Δy(k)`.

| Scenario | 2Y | 5Y | 10Y | 30Y | **Full reval ($)** | KRD estimate ($) | Error ($) | Error % |
|---|---|---|---|---|---|---|---|---|
| **Parallel +100bp** | +100 | +100 | +100 | +100 | **−31,199,004** | −32,978,331 | +1,779,327 | 5.7% |
| **Parallel −100bp** | −100 | −100 | −100 | −100 | **+34,978,884** | +32,978,331 | +2,000,552 | 5.7% |
| **Steepener** (2s30s +75) | −25 | −5 | +20 | +50 | **−4,684,162** | −4,900,310 | +216,148 | 4.6% |
| **Flattener** (2s30s −75) | +25 | +5 | −20 | −50 | **+5,134,638** | +4,900,310 | +234,329 | 4.6% |
| **Butterfly** (belly +30) | −15 | +30 | +15 | −15 | **−3,590,456** | −3,640,755 | +50,299 | 1.4% |
| **2022-style +250bp** | +250 | +250 | +250 | +250 | **−72,176,646** | −82,445,828 | **+10,269,182** | **14.2%** |

### 4.1 Convexity is visible in the asymmetry

```
   Parallel −100bp gain :  +$34,978,884
   Parallel +100bp loss :  −$31,199,004
   Asymmetry            :   +$3,779,880
```

**The portfolio gains $3.78m more on a 100bp rally than it loses on a 100bp sell-off**, on an identical shock magnitude. That is positive convexity, and it is worth real money — it is also exactly what the first-order estimate cannot see, since the KRD estimate is symmetric by construction (−32,978,331 and +32,978,331).

### 4.2 The error grows super-linearly with shock size

| Shock | Full reval loss | KRD error | Error as % of loss |
|---|---|---|---|
| ±100bp | $31.2m | $1.78m | **5.7%** |
| +250bp | $72.2m | $10.27m | **14.2%** |

> **This is the numerical case for full revaluation in stress testing.** At ±100bp the linear estimate is tolerable for an intraday indication. At +250bp — a shock size well within recent experience — it overstates the loss by **$10.3 million**, and the direction of the error is not obvious in advance. [13 §10](13_Stress_Testing.md) makes the rule; this table is the evidence for it.

### 4.3 The curve trades

The **steepener** and **flattener** rows show the point of the ladder. Both scenarios have an *average* shock of roughly +10bp and −10bp respectively across the four nodes — yet the P&L is not what a parallel move of that size would produce, because the book's risk is concentrated at the 10Y where the shocks are largest.

**A single DV01 number cannot distinguish these scenarios at all.** Only the ladder can.

---

## 5. Historical simulation VaR and Expected Shortfall

> ⚠ **The 250 scenarios below are *illustrative*, generated from a stated three-factor process (level, slope, curvature) with Student-t(5) innovations and an idiosyncratic term.** In production, scenarios **must** be extracted from the institution's own observed market-data history — [13 §4.1](13_Stress_Testing.md). They are used here so the arithmetic can be followed, not as a claim about actual Treasury volatility.

Each scenario is applied to the ladder's key rates and the portfolio is **fully revalued**.

### 5.1 The tail

Ten worst scenario P&Ls ($):

| Rank | P&L |
|---|---|
| 1 | **−9,855,475** |
| 2 | **−4,100,048** |
| 3 | **−4,058,486** |
| 4 | −3,959,944 |
| 5 | −3,939,659 |
| 6 | −3,595,171 |
| 7 | −3,508,384 |
| 8 | −3,432,791 |
| 9 | −3,357,952 |
| 10 | −3,315,853 |

### 5.2 The measures

| Measure | Value | Basis |
|---|---|---|
| **99% VaR** (round **up** — 3rd worst) | **$4,058,486** | conservative convention |
| **99% VaR** (round **down** — 2nd worst) | **$4,100,048** | |
| **99% VaR** (interpolated) | **$4,079,267** | |
| **97.5% ES** (average of worst 6.25) | **$4,861,741** | |
| **99% ES** (average of worst 2.5) | **$6,393,907** | |

### 5.3 Three things this tail demonstrates

**(a) The quantile convention matters, but less than the tail shape.** The three 99% VaR conventions span $41,562 — about 1% ([11 §4.5](11_VaR.md) shows a case where the spread reaches 13%; here the 2nd and 3rd worst happen to be close together, which is luck, not design).

**(b) 97.5% ES exceeds 99% VaR by far more than normality predicts.**

```
   ES(97.5) / VaR(99, round-up)  =  4,861,741 / 4,058,486  =  1.198
```

Under a **normal** distribution that ratio would be **1.005** — the multipliers are 2.3378 and 2.3263 ([12 §6.3](12_Expected_Shortfall.md)). Here it is **1.198**, nearly 20% higher.

> **The gap between 1.005 and 1.198 is the fat tail, measured.** It is exactly the property Basel's move to ES was designed to capture, and it is invisible to VaR by construction.

**(c) One scenario dominates the tail.** The worst outcome (−$9.86m) is **2.4× the second worst**. That single observation moves 97.5% ES by roughly `9.86m / 6.25 ≈ $1.58m` — a third of the measure. This is ES's known sensitivity to outliers ([12 §13](12_Expected_Shortfall.md)): the sensitivity is the *intent*, but it means data quality in the tail matters more for ES than for VaR.

---

## 6. Stress testing

Full revaluation, no approximation.

| Scenario | 2Y | 5Y | 10Y | 30Y | **P&L ($)** | % of PV |
|---|---|---|---|---|---|---|
| **Parallel +200bp** | +200 | +200 | +200 | +200 | **−59,212,349** | −12.0% |
| **Parallel +300bp** | +300 | +300 | +300 | +300 | **−84,514,846** | −17.2% |
| **1994-style bear flattener** | +300 | +280 | +250 | +200 | **−74,215,903** | −15.1% |
| **2013 taper-tantrum style bear steepener** | +60 | +120 | +150 | +145 | **−40,526,851** | −8.2% |
| **Flight to quality (bull flattener)** | −100 | −140 | −170 | −180 | **+58,238,486** | +11.8% |

> ⚠ **The shock vectors above are shaped to resemble the named episodes; they are not the actual observed moves.** Production stress vectors must be extracted from the institution's own market-data archive for the precise dated window — [13 §4.1](13_Stress_Testing.md). **Any shock magnitude that cannot be traced to an observation is a fabricated number and must not be used.**

### 6.1 Stress against VaR — the whole argument in one comparison

| Measure | Value | Multiple of VaR |
|---|---|---|
| **99% 1-day VaR** | $4,058,486 | 1.0× |
| **97.5% 1-day ES** | $4,861,741 | 1.2× |
| **Worst stress (+300bp)** | **$84,514,846** | **20.8×** |

**Neither number is wrong.** VaR describes a normal bad day; the stress describes a specific catastrophe with no probability attached. A framework reporting only the first tells management the truth about ordinary conditions and nothing about the conditions that determine survival ([13 §2](13_Stress_Testing.md)).

### 6.2 Shape matters as much as size

Compare two scenarios with similar *average* shocks:

```
   1994-style bear flattener  (avg +258bp)  :  −$74.2m
   Parallel +250bp             (avg +250bp)  :  −$72.2m
```

Similar. Now compare on *maximum* shock:

```
   1994-style (max +300bp at the 2Y)         :  −$74.2m
   Parallel +300bp                            :  −$84.5m
```

**The 1994-style scenario has the same peak shock and costs $10.3m less**, because its largest moves fall at the short end where this book has least risk. **A scenario's severity is a property of the shock vector *and* the portfolio jointly** — never of the shock alone.

---

## 7. Portfolio summary

```
 ═══════════════════════════════════════════════════════════════════════
  U.S. TREASURY PORTFOLIO — RISK SUMMARY              2026-08-24
 ═══════════════════════════════════════════════════════════════════════
  Market value                                   $492,741,450
  Face value                                     $500,000,000

  SENSITIVITIES
    Total DV01                                       $329,783 /bp
      2Y node                                          29,002   (8.8%)
      5Y node                                          82,620  (25.1%)
      10Y node                                        162,320  (49.2%)   ◄ dominant
      30Y node                                         55,841  (16.9%)
    Ladder reconciles to parallel DV01                 ✓ exact

  STATISTICAL RISK  (250 scenarios, full revaluation)
    99% 1-day VaR  (round up)                      $4,058,486   (0.82% of PV)
    97.5% 1-day ES                                 $4,861,741   (0.99% of PV)
    ES(97.5) / VaR(99)                                  1.198   ◄ fat tail

  STRESS  (full revaluation)
    Parallel +200bp                               −$59,212,349  (−12.0%)
    Parallel +300bp                               −$84,514,846  (−17.2%)   ◄ worst
    1994-style bear flattener                     −$74,215,903  (−15.1%)
    Flight to quality                             +$58,238,486  (+11.8%)

  CONVEXITY
    −100bp gain minus +100bp loss                  +$3,779,880   ◄ positive convexity
 ═══════════════════════════════════════════════════════════════════════
```

**The book is long duration, concentrated at the 10-year point (49% of DV01), positively convex, and carries a stress loss roughly 21× its VaR.**

---

## 8. Cross-references to the single-asset worked examples

The remaining worked examples in this library are computed in the documents where their theory is established, so that each sits next to the formula it demonstrates:

| Portfolio / calculation | Worked in |
|---|---|
| **Single bond** — price, Macaulay, modified duration, DV01, convexity, second-order accuracy | [04 §1.7, §2.7, §4.8, §6.4–6.5](04_Interest_Rate_Risk.md) |
| **Bond valuation from a flat curve** — full cash flow table | [03 §3.3](03_Pricing_Fundamentals.md) |
| **Bootstrapping** a 2-year discount factor from par swaps | [03 §2.3](03_Pricing_Fundamentals.md) |
| **Swap book** — key-rate ladder and flattening scenario | [04 §5.5, §7.2](04_Interest_Rate_Risk.md) |
| **Carry and roll-down** | [04 §9.3, §10.3](04_Interest_Rate_Risk.md) |
| **Credit portfolio** — CS01, bucketed CS01, FRN contrast | [05 §4.4–4.5, §5](05_Credit_Spread_Risk.md) |
| **FX book** — NOP, scenario, SBM delta capital with γ = 60% | [06 §9](06_FX_Risk.md) |
| **FX forward** — covered interest parity, forward points | [06 §4.2](06_FX_Risk.md) |
| **FX options** — risk reversal and butterfly reconstruction | [06 §6.2](06_FX_Risk.md) |
| **Equity book** — long/short/net/gross/beta-adjusted; variance decomposition | [07 §3.2, §4.3](07_Equity_Risk.md) |
| **Dividend risk** — forward repricing on a dividend cut | [07 §5](07_Equity_Risk.md) |
| **Commodity book** — crude spread, basis blowout, SBM with the correlation triple | [08 §7](08_Commodity_Risk.md) |
| **Options** — full Greeks; the approximation-error table | [09 §3–8, §10.2](09_Options_and_Greeks.md) |
| **Multi-asset portfolio** — variance, diversification, marginal and component risk | [10 §4.2, §5.1, §6.3](10_Portfolio_Risk_Mathematics.md) |
| **Parametric VaR and ES**, and the 97.5%/99% calibration identity | [11 §5.4](11_VaR.md), [12 §6.3–6.4](12_Expected_Shortfall.md) |
| **Historical ES** with the fractional tail observation | [12 §5](12_Expected_Shortfall.md) |
| **Options spot × vol stress grid** | [13 §6.2](13_Stress_Testing.md) |
| **Daily P&L explain**, and HPL/RTPL derivation | [14 §3](14_PnL_and_PnL_Explain.md) |
| **Spearman and KS** PLA metrics | [15 §6.5](15_Backtesting.md) |
| **FRTB SBM GIRR delta** across all three correlation scenarios | [17 §6](17_FRTB_Standardised_Approach.md) |
| **RRAO** by instrument category | [17 §9.6](17_FRTB_Standardised_Approach.md) |
| **DRC** — gross JTD, net JTD, hedge benefit ratio, bucket charge | [19 §7](19_Default_Risk_and_DRC.md) |
| **SES** — NMRF aggregation at ρ = 0.6 | [20 §7.6](20_NMRF_and_Modellability.md) |
| **CVA** and netting benefit | [22 §4.1, §5.1](22_Counterparty_CVA_and_SIMM.md) |
| **Desk limit pack** and utilisation reading | [21 §9](21_Market_Risk_Limits.md) |
| **Daily market risk report** | [28 §3.2](28_Reporting_and_Dashboards.md) |

---

## 9. Reproducing these numbers

Every figure in §2–§7 follows from four stated inputs: the four bonds, the nine curve nodes, the tent-shock definition, and the scenario vectors. The computational recipe:

```
   DF(t)              = exp(-z(t) * t),  z linearly interpolated between nodes
   Price              = Σ CF_i · DF(t_i),  semiannual coupons, principal at maturity
   DV01               = [ P(curve − 1bp) − P(curve + 1bp) ] / 2       (central)
   Convexity          = [ P(+100bp) + P(−100bp) − 2·P(0) ] / (P(0)·0.01²)
   Macaulay duration  = Σ t_i · CF_i · DF(t_i) / P
   KRD01(k)           = [ P(tent_k − 1bp) − P(tent_k + 1bp) ] / 2
     tent_k weight    = 1 at k; linear taper to 0 at adjacent key rates;
                        FLAT beyond the outermost key rates
   Scenario P&L       = P(shocked curve) − P(base curve)               (FULL reval)
   VaR_α              = −(quantile of sorted scenario P&L)             (state convention)
   ES_α               = −(mean of the worst (1−α)·N observations, fractional included)
```

**Two checks that must pass before any of the numbers above are trusted:**

1. **`Σ KRD01 = parallel DV01`** — verified exact here.
2. **Coupon vs yield implies the price side of par** — verified for all four bonds.

---

## 10. Limitations

- **The 250 VaR scenarios and the stress vectors are illustrative**, generated to make the arithmetic followable. Production figures must come from observed history.
- **The portfolio is deliberately simple** — four bullet Treasuries, one currency, no optionality, no credit. Its purpose is to make every step checkable; a real book requires the full machinery in [25](25_Risk_System_Architecture.md).
- **Interpolation is linear on zero rates**, chosen for transparency. A production curve would use a scheme validated against implied forwards ([23 §6.4](23_Market_Data_and_Curves.md)), and the KRD ladder would differ in its *distribution* while agreeing on the total.
- **All results are model-implied**, computed off a constructed curve rather than from executable market prices.

---

## 11. Related Concepts

- [04 — Interest Rate Risk](04_Interest_Rate_Risk.md) · [11 — VaR](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [13 — Stress Testing](13_Stress_Testing.md) · [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md)
- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.8` vertices; `MAR33.3` ES confidence level |
| U.S. Treasury | Daily Treasury Par Yield Curve Rates | ongoing | https://home.treasury.gov/ | Curve conventions and quoting bases |

> **Note on sourcing.** The curve levels, portfolio composition and scenario vectors in this document are constructed for exposition. They are not market data, and no figure here should be cited as an observation.

*Accessed 25 August 2026.*
