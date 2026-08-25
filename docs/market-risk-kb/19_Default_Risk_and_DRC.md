# 19 — Default Risk and the Default Risk Charge

**Level:** 10 · **Prerequisites:** [05](05_Credit_Spread_Risk.md), [17](17_FRTB_Standardised_Approach.md) · **Feeds:** [22](22_Counterparty_CVA_and_SIMM.md), [30](30_Worked_Examples.md)

---

## 1. Plain English

**Default risk is the risk that an issuer stops paying — and the loss arrives as a jump, not a drift.**

A bond trading at 98 does not go to 30 by moving smoothly through 97, 96, 95. On a default it gaps. That discontinuity is why default risk is capitalised **separately** from credit spread risk, and why a spread model cannot substitute for a default model.

`MAR22.1` puts it directly: the DRC requirement *"is intended to capture jump-to-default (JTD) risk that may not be captured by credit spread shocks under the sensitivities-based method."*

---

## 2. Banking example — the position that CS01 cannot see

A desk sells $100m of five-year protection on a **AAA-rated** sovereign at 12bp.

| Measure | Value | Reading |
|---|---|---|
| **CS01** | ~$48,000/bp | Small. A 10bp widening costs $480,000 |
| **JTD** | ~**$75,000,000** | The loss if the obligor defaults tomorrow |

The desk's CS01 limit is $500,000/bp. This position uses under 10% of it. A book built entirely of such trades would show modest spread risk and carry catastrophic default exposure.

> **CS01 and JTD are largest in opposite places.** CS01 scales with spread duration and spread level; JTD scales with `(1 − Recovery) × Notional` and is *independent of spread*. The tightest, safest-looking names generate the smallest CS01 and, per dollar of notional, the largest JTD relative to the premium earned. **This is precisely the exposure Basel capitalises separately, and precisely the exposure a spread-based limit framework will not constrain.**

---

## 3. Why Basel separates DRC from CSR

| | CSR (spread) | DRC (default) |
|---|---|---|
| Underlying process | Diffusive — continuous | **Jump — discontinuous** |
| Measured by | Bumping a curve | **Direct calculation** — cannot be bumped into existence |
| Model | Sensitivity + correlation aggregation | Loss-given-default × exposure, or a default simulation |
| Calibration reference | Market spread history | **The banking-book credit risk treatment** |
| Basel chapter | `MAR21` | `MAR22` (SA) / `MAR33` (IMA) |

`MAR20.4(2)` explains the calibration choice: the DRC *"is calibrated based on the credit risk treatment in the banking book in order to reduce the potential discrepancy in capital requirements for similar risk exposures across the bank."*

> **That is the anti-arbitrage mechanism.** If trading-book default risk on an obligor were charged materially less than banking-book credit risk on the same obligor, the book boundary would be worth gaming. Aligning the two removes most of the incentive.

---

## 4. Gross JTD

### 4.1 Position by position (`MAR22.9`)

> The gross JTD risk position is computed **exposure by exposure**. Basel's own example: a bank with a long position on an Apple bond and a short position on another Apple bond *"must compute two separate JTD exposures."*

Netting happens later, and under rules. It does not happen at input.

### 4.2 Direction is defined by the default outcome (`MAR22.10`)

**Long/short is determined by whether the credit exposure results in a loss or a gain on default — not by whether an instrument was bought or sold.**

- A **long** exposure is one that results in a **loss** in the case of a default.
- For derivatives, direction *"is not determined by whether the option or credit default swap (CDS) is bought or sold."*

Basel's example: **a sold put option on a bond is a LONG credit exposure**, because a default results in a loss to the seller of the option.

| Instrument | Direction for DRC |
|---|---|
| Long bond | **Long** |
| Short bond | Short |
| **Bought** CDS protection | **Short** (gains on default) |
| **Sold** CDS protection | **Long** (loses on default) |
| **Sold** put on a bond | **Long** |
| **Bought** call on a bond | See §4.5 — notional is **zero** |
| Long equity | **Long** |

### 4.3 The formula (`MAR22.11`)

```
   JTD (long)   =   max( LGD × notional  +  P&L ,  0 )
   JTD (short)  =   min( LGD × notional  +  P&L ,  0 )
```

where:
- **notional** is the bond-equivalent notional amount (or face value) of the position;
- **P&L** is the cumulative mark-to-market loss (or gain) already taken — *"equal to the market value minus the notional amount."*

### 4.4 Sign conventions (`MAR22.13`)

> The notional amount of an instrument giving rise to a **long (short)** exposure is recorded as a **positive (negative)** value, while the P&L **loss (gain)** is recorded as a **negative (positive)** value.

**And:** if the contractual or legal terms of a derivative allow the instrument to be unwound with no exposure to default risk, **the JTD is zero**.

### 4.5 LGD (`MAR22.12`)

| Instrument type | **LGD** |
|---|---|
| Equity instruments and **non-senior** debt | **100%** |
| **Senior** debt instruments | **75%** |
| **Covered bonds** (as defined in `MAR21.51`) | **25%** |

`MAR22.12(4)`: where the price of the instrument is **not linked to the recovery rate** of the defaulter — Basel's example is an FX-credit hybrid option swapping long EUR coupons against short USD coupons with a knockout on default — **there should be no multiplication of the notional by the LGD**.

### 4.6 Notional (`MAR22.14`)

The notional determines the loss of principal at default; the mark-to-market loss is subtracted so as **not to double-count** the loss already recorded in market value.

| Instrument | Notional for JTD |
|---|---|
| Bond | **Face value** |
| CDS, or a put option on a bond | The **notional of the derivative contract** |
| **Call option on a bond** | **Zero** — *"since, in the event of default, the call option will not be exercised."* The loss of the option's value is captured entirely through the P&L term |

> **The call-option treatment is the clearest illustration of the framework's logic.** A long call on a defaulting bond loses its remaining value, but there is no principal to lose — you were never going to exercise. So notional is zero and the whole loss flows through the mark-to-market term. Getting this wrong by using the contract notional materially overstates DRC on an options book.

---

## 5. Net JTD

### 5.1 The offsetting rule

Offsetting is permitted **within the same obligor**, subject to maturity treatment.

`MAR22.20`:

- **(a)** Exposures with maturities **longer than the capital horizon (one year)** may be **fully offset**.
- **(b)** An exposure to an obligor comprising a mix of long and short exposures **with a maturity less than one year** must be **weighted by the ratio of the exposure's maturity to the capital horizon**.

Basel's example: *"a three-month short exposure would be weighted so that its benefit against long exposures of longer-than-one-year maturity would be reduced to one quarter of the exposure size."*

`MAR22.21`: where **both** the long and short offsetting exposures have maturity under one year, the scaling can be applied to **both**.

> **The economic logic is precise.** A three-month CDS does not hedge a ten-year bond against default over a one-year capital horizon — it expires nine months into that horizon and the bond is unprotected thereafter. Scaling the short by 3/12 recognises exactly the fraction of the horizon it covers.

The result is a set of **net long** and **net short** JTD positions, which `MAR22.21` requires to be *"aggregated separately."*

### 5.2 Look-through (`MAR22.5`)

For traded non-securitisation credit and equity derivatives, JTD positions **by individual constituent issuer legal entity** must be determined by applying a **look-through approach**. An index CDS is not one exposure; it is *n* exposures.

---

## 6. The DRC calculation for non-securitisations

### 6.1 Three buckets (`MAR22.22`)

1. **Corporates**
2. **Sovereigns**
3. **Local governments and municipalities**

### 6.2 Default risk weights (`MAR22.24`, Table 2)

Weights depend on **credit quality category, irrespective of the type of counterparty** — the same table applies to all three buckets:

| Credit quality category | **Default risk weight** |
|---|---|
| AAA | **0.5%** |
| AA | **2%** |
| A | **3%** |
| BBB | **6%** |
| BB | **15%** |
| B | **30%** |
| CCC | **50%** |
| **Unrated** | **15%** |
| **Defaulted** | **100%** |

**Note that "unrated" (15%) is treated as equivalent to BB, not to the worst category.** This is a deliberate calibration, and it differs from the SBM's treatment of unclassifiable issuers (CSR bucket 16 at 12%, with no offsetting at all).

### 6.3 The zero-risk-weight discretion (`MAR22.7`)

Claims on **sovereigns, public sector entities and multilateral development banks** may, **at national discretion**, receive a **zero default risk weight**, in line with the Basel III credit risk framework. National authorities may apply a **non-zero** weight to securities issued by certain foreign governments, including securities denominated in a currency other than that of the issuing government.

> **This is a national discretion, not an entitlement.** A bank must confirm its own supervisor's position before assuming a zero weight on any sovereign, and cannot assume the treatment travels across jurisdictions.

### 6.4 The hedge benefit ratio (`MAR22.23`)

To recognise hedging between net long and net short positions **within a bucket**:

```
                        Σ net JTD_long
   HBR  =  ────────────────────────────────────────
             Σ net JTD_long  +  | Σ net JTD_short |
```

Both sums are **simple sums of net JTD, not risk-weighted**, taken across the credit quality categories.

### 6.5 The bucket capital requirement (`MAR22.25`)

```
   DRC_b  =  max(   Σ      RW_i · net JTD_i
                  i∈Long

                  −  HBR ·  Σ      RW_i · | net JTD_i |   ,   0   )
                          i∈Short
```

### 6.6 No offsetting between buckets (`MAR22.26`)

> No hedging is recognised between different buckets — **the total DRC requirement for non-securitisations must be calculated as a simple sum of the bucket level capital requirements.**

A short sovereign position provides no relief against a long corporate position, however economically related.

---

## 7. Worked example — DRC for a corporate bucket

### 7.1 The positions

| Position | Notional | Market value | P&L | LGD | Direction |
|---|---|---|---|---|---|
| Long $50m senior bond, **issuer A** (rated A) | +50.0 | 48.0 | −2.0 | 75% | Long |
| **Bought** $30m CDS protection, **issuer A** | −30.0 | — | +0.8 | 75% | **Short** |
| Long $20m senior bond, **issuer B** (rated BB) | +20.0 | 19.4 | −0.6 | 75% | Long |
| Long $10m equity, **issuer C** (unrated) | +10.0 | 10.0 | 0.0 | **100%** | Long |
| **Bought** $25m CDS protection, **issuer D** (rated BBB) | −25.0 | — | +0.3 | 75% | **Short** |

All maturities exceed one year, so full offsetting applies per `MAR22.20(a)`.

### 7.2 Gross JTD

```
   A bond   :  max(0.75 × 50.0  +  (−2.0), 0)   =  max(37.50 − 2.00, 0)  =  +35.50
   A CDS    :  min(0.75 × (−30.0) + 0.8, 0)     =  min(−22.50 + 0.80, 0) =  −21.70
   B bond   :  max(0.75 × 20.0  +  (−0.6), 0)   =  max(15.00 − 0.60, 0)  =  +14.40
   C equity :  max(1.00 × 10.0  +  0.0, 0)      =                           +10.00
   D CDS    :  min(0.75 × (−25.0) + 0.3, 0)     =  min(−18.75 + 0.30, 0) =  −18.45
```

### 7.3 Net JTD by obligor

| Obligor | Net JTD ($m) | Rating | RW |
|---|---|---|---|
| A | 35.50 − 21.70 = **+13.80** | A | **3%** |
| B | **+14.40** | BB | **15%** |
| C | **+10.00** | Unrated | **15%** |
| D | **−18.45** | BBB | **6%** |

### 7.4 Hedge benefit ratio

```
   Σ net JTD_long    =  13.80 + 14.40 + 10.00  =  38.20
   | Σ net JTD_short |                          =  18.45

   HBR  =  38.20 / (38.20 + 18.45)  =  38.20 / 56.65  =  0.674316
```

### 7.5 Risk-weighted sums

```
   Long :   0.03 × 13.80  +  0.15 × 14.40  +  0.15 × 10.00
        =   0.414         +  2.160         +  1.500          =  4.074000

   Short:   0.06 × 18.45                                      =  1.107000
```

### 7.6 The bucket charge

```
   DRC_corporates  =  max( 4.074000  −  0.674316 × 1.107000 ,  0 )
                   =  max( 4.074000  −  0.746468 ,  0 )
                   =  $3,327,532
```

### 7.7 What the HBR actually costs

| Treatment | DRC |
|---|---|
| **Full offset** (if HBR were 1.0) | $2,967,000 |
| **Actual, with HBR = 0.674316** | **$3,327,532** |
| **Cost of partial hedge recognition** | **$360,532** |

**The HBR is a haircut on hedge recognition that bites hardest when the book is directionally long.** As the short position grows relative to the long, HBR falls toward zero and *less* of the short's benefit is recognised — the framework declining to grant full offset to a book that is hedging its way out of a large directional position rather than running a genuinely matched one.

### 7.8 Total DRC

If this bank also has a sovereign bucket charge of $1.2m and a municipalities bucket charge of $0.4m:

```
   Total DRC  =  3.327532  +  1.200  +  0.400  =  $4,927,532
```

**A simple sum** (`MAR22.26`) — no diversification across buckets.

---

## 8. Securitisations

The DRC applies to three sub-portfolios, with **no diversification benefit recognised between them** (`MAR22.4`):

1. **Non-securitisations** (§6 above)
2. **Securitisations (non-CTP)**
3. **Securitisations (CTP)**

**Non-CTP** (`MAR22`): the DRC within a bucket is calculated by an approach analogous to non-securitisations, but with buckets defined by asset class and region.

**CTP** (`MAR22.40`–`MAR22.45`): the correlation trading portfolio has its own treatment. Bucket-level capital amounts are aggregated in a way that permits offsetting between long and short *bucket-level* amounts — Basel's own example concerns a DRC of +100 for the index CDX North America IG against a DRC of −(some amount) for the index Major Sovereign (G7 and Western Europe). `MAR22.6` requires that for the CTP the calculation **includes the default risk for non-securitisation hedges**, and that **these hedges must be removed from the non-securitisation DRC calculation** to avoid double-counting.

---

## 9. Equity investments in funds (`MAR22.8`)

Where a claim is an equity investment in a fund treated as unrated "other sector" equity under `MAR21.36(3)`, it is treated as an **unrated equity instrument**.

**Where the fund's mandate permits investment primarily in high-yield or distressed names**, the bank must apply the **maximum risk weight achievable under that mandate**, computed by assuming the fund invests:

1. first in **defaulted** instruments to the maximum possible extent allowed,
2. then in **CCC**-rated names to the maximum possible extent,
3. then **B**-rated,
4. then **BB**-rated.

**Neither offsetting nor diversification is allowed** between these generated exposures and other exposures.

> This is the framework refusing to let a mandate's *worst permitted* behaviour go uncapitalised simply because the fund is not currently exercising it.

---

## 10. DRC under the Internal Models Approach

A **separate internal model** from the ES model (`MAR33.18`). Summarised here; see [18 §7](18_FRTB_Internal_Models_Approach.md).

| Requirement | Specification | Source |
|---|---|---|
| Model type | **VaR model** | `MAR33.20` |
| Confidence / horizon / frequency | **99.9th percentile, one-tail, one-year horizon, computed WEEKLY** | `MAR33.20(5)` |
| Systematic factors | Default simulation with **two types** of systematic risk factor | `MAR33.20(1)` |
| Correlations | Based on credit spreads **or** listed equity prices; **≥10 years** of data including a stress period; measured over a **one-year** liquidity horizon | `MAR33.20(2)`, `MAR33.27` |
| Equity sub-portfolios | Discretion to apply a **60-day** minimum liquidity horizon | `MAR33.20(4)` |
| Positions | **Constant** over the horizon | `MAR33.22` |
| Capital measure | **Greater of** the 12-week average and the most recent measure | `MAR33.21`/`MAR33.22` |
| PD floor | **0.03%** | `MAR33.24(2)` |
| Market-implied PDs | **Not acceptable** unless corrected to objective PDs | `MAR33.24(1)` |
| Equity default | Modelled as **price dropping to zero** | `MAR33.21(2)` |
| Scope | Includes sovereigns (**even domestic-currency**), equities, and **defaulted debt** | `MAR33.21(1)` |
| Netting | Same-obligor permitted, **accounting for seniority differences**; **pre-netting otherwise not allowed** | `MAR33.25`–`MAR33.26` |
| Cross-obligor offset | **Only through the modelling of defaults**; basis risk modelled explicitly | `MAR33.26` |
| Anti-opportunism | Correlations must not be chosen to suit portfolio shape | `MAR33.27(1)` |
| Approval | **Second stage**, conditional on market risk model approval | `MAR32.19` fn 1 |

---

## 11. Pseudocode

```
FUNCTION gross_jtd(position):
    IF position.can_unwind_without_default_exposure:      # MAR22.13
        RETURN 0

    lgd = ( 0.25 if position.is_covered_bond
       else 0.75 if position.is_senior_debt
       else 1.00 )                                        # MAR22.12

    IF NOT position.price_linked_to_recovery:             # MAR22.12(4)
        lgd = 1.0                                         # no LGD multiplication

    notional = notional_for_jtd(position)                 # MAR22.14
    #   bond            -> face value
    #   CDS / bond put  -> contract notional
    #   bond CALL       -> ZERO
    IF position.direction == SHORT:
        notional = -abs(notional)

    pnl = position.market_value - abs(notional)           # loss negative

    raw = lgd * notional + pnl
    RETURN max(raw, 0) IF position.direction == LONG ELSE min(raw, 0)


FUNCTION net_jtd(positions_for_obligor, capital_horizon_years = 1.0):
    net = 0
    FOR p IN positions_for_obligor:
        j = gross_jtd(p)
        IF p.maturity_years < capital_horizon_years:      # MAR22.20(b)
            j *= p.maturity_years / capital_horizon_years
        net += j
    RETURN net


FUNCTION drc_bucket(net_jtds, risk_weights):
    longs  = { o: v for o, v in net_jtds.items() if v > 0 }
    shorts = { o: v for o, v in net_jtds.items() if v < 0 }

    sum_long  = sum(longs.values())                       # NOT risk-weighted
    sum_short = abs(sum(shorts.values()))                 # NOT risk-weighted

    hbr = sum_long / (sum_long + sum_short) IF (sum_long + sum_short) > 0 ELSE 0

    wl = sum(risk_weights[o] * v        for o, v in longs.items())
    ws = sum(risk_weights[o] * abs(v)   for o, v in shorts.items())

    RETURN max(wl - hbr * ws, 0)                          # MAR22.25


FUNCTION total_drc(portfolio):
    # MAR22.26 / MAR22.4 — SIMPLE SUM at every level, no diversification
    non_sec = sum(drc_bucket(b) for b in ["corporates","sovereigns","municipals"])
    sec     = sum(drc_bucket(b) for b in securitisation_buckets)
    ctp     = drc_ctp(portfolio)
    RETURN non_sec + sec + ctp
```

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Exposure-by-exposure** | Gross JTD computed per position, not netted at input (`MAR22.9`) |
| 2 | **Direction by outcome** | Sold put on a bond classified **long** (`MAR22.10`) |
| 3 | **LGD assignment** | 100% equity/non-senior, 75% senior, 25% covered bonds |
| 4 | **Recovery-independent instruments** | No LGD multiplication (`MAR22.12(4)`) |
| 5 | **Bond call notional** | **Zero** (`MAR22.14(1)(c)`) |
| 6 | **Sign convention** | Long notional +, short −; loss −, gain + (`MAR22.13`) |
| 7 | **Unwind clause** | JTD zero where no default exposure on unwind |
| 8 | **Maturity scaling** | Sub-one-year exposures weighted by maturity/horizon (`MAR22.20(b)`) |
| 9 | **Both legs scaled** | Where both are under one year (`MAR22.21`) |
| 10 | **HBR unweighted** | Computed on **net JTD**, not risk-weighted JTD (`MAR22.23`) |
| 11 | **Floored at zero** | `DRC_b ≥ 0` (`MAR22.25`) |
| 12 | **No cross-bucket offset** | Simple sum (`MAR22.26`) |
| 13 | **No cross-sub-portfolio offset** | Non-sec / sec / CTP summed (`MAR22.4`) |
| 14 | **Look-through** | Applied to index and basket credit and equity derivatives (`MAR22.5`) |
| 15 | **CTP hedge removal** | Non-securitisation hedges in CTP removed from non-sec DRC (`MAR22.6`) |
| 16 | **Sovereign zero RW** | Confirmed as an actual national discretion, not assumed (`MAR22.7`) |
| 17 | **Fund mandate** | Maximum achievable RW applied where mandate permits HY/distressed (`MAR22.8`) |
| 18 | **JTD independent of CS01** | Never derived by bumping a spread curve |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Deriving JTD from CS01 | Default exposure unmeasured — the §2 position looks tiny |
| Direction by bought/sold rather than default outcome | Sign errors throughout; sold puts misclassified |
| Contract notional on a bond **call** | Materially overstates DRC on options books |
| LGD 100% applied to senior debt | Overstates DRC by a third |
| LGD applied to recovery-independent instruments | Contradicts `MAR22.12(4)` |
| Netting at input rather than after gross computation | Contradicts `MAR22.9` |
| Full offset for sub-one-year hedges | Overstates hedge benefit |
| HBR computed on **risk-weighted** JTD | Wrong ratio; wrong capital |
| Offsetting across buckets | Contradicts `MAR22.26` |
| No look-through on index CDS | Single-name concentration invisible |
| Assuming sovereign zero RW | It is a national discretion (`MAR22.7`) |
| DRC IMA run daily at 99% | Wrong parameters — 99.9%, one year, **weekly** |
| Using raw market-implied PDs under IMA | Explicitly not acceptable |

---

## 14. Limitations

- **DRC is a capital construct, not a prediction.** The prescribed risk weights are calibrated, not estimated for any particular portfolio.
- **Rating-based weights inherit rating agency lag.** A deteriorating credit carries its old weight until downgraded, and downgrades cluster.
- **The HBR is a blunt instrument.** It applies one ratio to an entire bucket regardless of how well individual hedges match.
- **Recovery is assumed, not observed.** The LGD schedule (100/75/25) is a fixed convention; realised recoveries vary enormously by seniority, jurisdiction and cycle.
- **Correlation is absent from the SA DRC.** Bucket-level aggregation is a simple sum, which neither recognises diversification nor models contagion.
- **The one-year capital horizon is a convention.** Default timing within the year is captured only through the maturity-scaling rule.

---

## 15. Related Concepts

- [05 — Credit Spread Risk](05_Credit_Spread_Risk.md) — the CS01/JTD pairing
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md)
- [22 — Counterparty, CVA and SIMM](22_Counterparty_CVA_and_SIMM.md) · [41 — Market Risk vs Related Risk Types](41_Market_Risk_vs_Related_Risk_Types.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR22` in full; `MAR33.18`–`MAR33.39` DRC under IMA |
| BCBS | *Revisions to the securitisation framework* | Dec 2014, 2016, 2018 | https://www.bis.org/bcbs/publ/d442.pdf | Referenced by `MAR22.20` |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR22 text |

*Accessed 25 August 2026.*
