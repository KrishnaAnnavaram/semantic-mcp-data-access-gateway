# 20 — Non-Modellable Risk Factors and Modellability

**Level:** 11 · **Prerequisites:** [18](18_FRTB_Internal_Models_Approach.md) · **Feeds:** [23](23_Market_Data_and_Curves.md), [26](26_Model_Risk_and_Validation.md)

---

## 1. Plain English

**A risk factor is "modellable" if the bank can prove there is enough real market evidence to model it. If it cannot, the factor is capitalised through a stress scenario instead — with far less diversification benefit.**

The regime exists to close a specific pre-crisis gap: a bank could include a thinly-traded risk factor in its VaR model, obtain **full diversification benefit** against everything else, and never be asked to demonstrate that the factor's distribution was based on anything real.

> **FRTB severs the link between "in my model" and "diversified."** A factor that cannot be evidenced can still be modelled for pricing — but it cannot buy offset against the rest of the book for capital.

---

## 2. Banking example

A bank holds a bespoke 40-year interest rate swap in an emerging-market currency.

| | |
|---|---|
| Trades observed in that tenor over the last year | **8** |
| RFET requirement | 24 per year with no 90-day gap below 4, **or** 100 in 12 months |
| Outcome | **Fails** |
| Consequence | The 40-year point becomes an **NMRF**; capitalised through **SES** |

Before FRTB, that 40-year point would have sat in the VaR model, been simulated from a sparse and possibly stale series, and received full offset against the bank's other rate positions. Its measured risk contribution would have been close to zero.

Under FRTB it attracts a **stress scenario** calibrated to a 97.5% loss over a stress period, with a **minimum 20-day liquidity horizon**, aggregated under a formula that grants only partial diversification. The capital difference is typically large — and that is the intent.

---

## 3. The Risk Factor Eligibility Test

### 3.1 What counts as a "real price" (`MAR31.12`)

**Collateral reconciliations and valuations cannot be considered real prices.** A price is real if it meets **at least one** of:

1. **It is a price at which the institution has conducted a transaction.**
2. **It is a verifiable price for an actual transaction between other arm's-length parties.**
3. **It is a price obtained from a committed quote** made by (i) the bank itself or (ii) another party — where the committed quote is **collected and verified through a third-party vendor, a trading platform or an exchange**.
4. **It is a price obtained from a third-party vendor**, where:
   - the transaction or committed quote has been processed through the vendor;
   - the vendor agrees to provide evidence of the transaction or committed quote **to supervisors on request**; or
   - the price meets any of criteria (1) to (3).

> **Note what is excluded and why.** An indicative quote is not a committed quote. A model mark is not a price. A collateral valuation — the number two counterparties agreed for margin purposes — is explicitly not a real price. The test is about **evidence of a market**, not evidence of a number.

### 3.2 The two counting criteria (`MAR31.13`)

A risk factor passes the RFET on a **quarterly** basis if it meets **either**:

**Criterion 1 — the 24/4 test**

- **At least 24 real price observations per year**, measured over the period used to calibrate the current ES model; **and**
- over the previous 12 months, **no 90-day period** in which **fewer than 4** real price observations are identified.
- **Monitored monthly.**

**Criterion 2 — the 100 test**

- **At least 100 real price observations over the previous 12 months.**

**In both cases: no more than one real price observation per day is included in the count.**

> **The 90-day gap condition in Criterion 1 is the interesting half.** A factor could accumulate 24 observations in a single active month and be dormant for the rest of the year. Criterion 1 refuses that: liquidity must be *sustained*, not merely *total*. Criterion 2 offers an alternative for factors with high but irregular volume.

`MAR31.13`: *"Any real price that is observed for a transaction should be counted as an observation for all of the risk factors for which it is representative."* One trade can support several factors.

### 3.3 The data-lag allowance (footnote 2 to `MAR31.13`)

Where a bank uses real price observations from an external source provided with a **time lag**, the RFET period may differ from the ES calibration period — but **by no more than one month**. A bank may use, per risk factor, a one-year window finishing up to one month before the RFET assessment.

### 3.4 The basis rule (footnote 3 to `MAR31.13`)

> A bank may add modellable risk factors and **replace non-modellable risk factors by a basis** between the additional modellable factors and the non-modellable ones. **This basis will then be considered a non-modellable risk factor.** A combination between modellable and non-modellable risk factors will be a **non-modellable** risk factor.

**This is the anti-laundering provision.** The illiquid part cannot be dissolved into a liquid proxy: decompose an NMRF into a modellable component plus a basis, and the basis inherits the non-modellable status. Contamination flows in only one direction.

---

## 4. Bucketing — how observations are counted

A bank does not need a real price at the exact point on a curve. `MAR31.16`–`MAR31.17` permit bucketing, with two approaches.

### 4.1 Own bucketing approach

The bank defines its own buckets, subject to conditions — including (`MAR31.16`) that **the buckets must be non-overlapping**.

### 4.2 The regulatory bucketing approach (`MAR31.17`, Table 1)

Standard buckets, in years (*t*) or delta-moneyness (Δ):

| Row | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| **(A)** | 0 ≤ t < 0.75 | 0.75 ≤ t < 1.5 | 1.5 ≤ t < 4 | 4 ≤ t < 7 | 7 ≤ t < 12 | 12 ≤ t < 18 |
| **(B)** | 0 ≤ t < 0.75 | 0.75 ≤ t < 4 | 4 ≤ t < 10 | 10 ≤ t < 18 | 18 ≤ t < 30 | 30 ≤ t |
| **(C)** | 0 ≤ t < 1.5 | 1.5 ≤ t < 3.5 | 3.5 ≤ t < 7.5 | 7.5 ≤ t < 15 | 15 ≤ t | |
| **(D)** | 0 < Δ ≤ 0.05 | 0.05 < Δ ≤ 0.3 | 0.3 < Δ ≤ 0.7 | 0.7 < Δ ≤ 0.95 | 0.95 < Δ ≤ 1.00 | |

*(Row A has further buckets beyond 18 years in the full table; rows are truncated here at the boundaries shown in the standard's Table 1 excerpt.)*

**Which row applies (`MAR31.17(2)`):**

| Risk factor type | Row |
|---|---|
| Interest rate, FX, commodity with **one** maturity dimension (excl. implied vols) | **(A)** |
| Interest rate, FX, commodity with **several** maturity dimensions (excl. implied vols) | **(B)** |
| **Credit spread and equity** with one or several maturity dimensions (excl. implied vols) | **(C)** |
| Any risk factor with one or several **strike** dimensions (delta) | **(D)** |
| **Expiry and strike** dimensions of implied volatility risk factors (**excluding** interest rate swaptions) | **(C) and (D) only** |
| **Maturity, expiry and strike** dimensions of implied volatility from **interest rate swaptions** | **(B), (C) and (D) only** |

### 4.3 The maturity-migration rule (`MAR31.18`)

As debt instruments mature, real price observations identified in the prior 12 months are **usually still counted in the bucket to which they were initially allocated**. When a bank no longer needs to model a credit spread factor in a given maturity bucket, it **may re-allocate** those observations to the **adjacent (shorter)** maturity bucket.

Basel's example: a bond with an original four-year maturity that had a real price observation on its issuance date eight months ago may be allocated to the 1.5–3.5 year bucket instead of the 3.5–7.5 year bucket to which it would normally belong.

**A real price observation may only be counted in a single maturity bucket.**

### 4.4 Parametric functions (`MAR31.19`)

Where a bank uses a **parametric function** to represent a curve or surface and defines the function's parameters as risk factors, **the RFET must be passed at the level of the market data used to calibrate the parameters** — *not* at the level of the parameters themselves, because real price observations directly representative of an abstract parameter generally do not exist.

### 4.5 Systematic versus idiosyncratic (`MAR31.20`–`MAR31.21`)

A bank may use **systematic** credit or equity risk factors designed to capture market-wide movements for an economy, region or sector. But:

> **The idiosyncratic risk of a specific issuer is a non-modellable risk factor unless there are sufficient real price observations of that issuer.**

Real price observations of market indices or of individual issuers' instruments may be counted as representative of a *systematic* factor, provided they share the same attributes as that factor.

Where systematic credit or equity factors include a **maturity dimension** (e.g. a credit spread curve), one of the bucketing approaches must be applied to that dimension for RFET counting.

> **This is the practical heart of the regime for a credit book.** Most issuers have no liquid CDS. Their spread risk is modelled against a sector-and-rating proxy — which is a *systematic* factor and may well pass the RFET. The **idiosyncratic residual** — the part that is specific to that issuer, and the part that actually blows up — does not pass, and becomes an NMRF. See [05 §13](05_Credit_Spread_Risk.md).

---

## 5. Passing the RFET is necessary, not sufficient

`MAR31.22`: once a risk factor has passed, the bank chooses the most appropriate data to calibrate its model. **The calibration data need not be the same data used to pass the RFET.**

`MAR31.23`: the bank must nonetheless **demonstrate that the calibration data are appropriate** under the `MAR31.25`–`MAR31.26` principles. Where it has not done so to the supervisor's satisfaction, **the supervisor may deem the data unsuitable, exclude the factor from the ES model, and require it to be capitalised as an NMRF.**

`MAR31.25` is explicit: *"Banks must not rely solely on the number of observations of real prices to determine whether a risk factor is modellable. The accuracy of the source of the risk factor real price observation must also be considered."*

### 5.1 The four principles (`MAR31.26`)

**Principle one — combinations of modellable risk factors.**
Risk factors derived **solely** from a combination of modellable factors are generally modellable — including factors derived through multifactor beta models whose inputs and calibrations rest solely on modellable factors. **But** a risk factor derived from a combination of modellable factors that are mapped to *distinct buckets* of a given curve/surface is modellable **only if that risk factor also passes the RFET**.

- Interpolation must be **consistent with the mappings used for PLA testing** to determine RTPL, and must not use alternative, broader bucketing.
- Compression into orthogonal factors (e.g. principal components) and derivation of parameters from modellable observations (e.g. stochastic implied volatility models) is permitted without the parameters being directly observable.
- **Extrapolation** is permitted subject to supervisory approval, **up to a reasonable distance** from the closest modellable factor; it **must not rely solely on the closest factor** but on more than one; and where used, **it must be considered in the determination of RTPL**.

**Principle two — idiosyncratic and general market risk.**
The data must allow the model to pick up **both**. General market risk is the tendency of an instrument's value to move with the broader market; idiosyncratic risk is specific to a particular issuance, *"including default provisions, maturity and seniority."* **If the data reflect only one, the bank must apply an NMRF charge for the aspect not adequately captured.**

**Principle three — volatility and correlation.**
Banks must **not understate volatility** (for example by inappropriate averaging of data, or by proxies), and must **accurately reflect correlation** — across asset prices, across yield curve tenors, and within volatility surfaces. Basel notes that *"different data sources can provide dramatically different volatility and correlation estimates."* Data sources must be chosen so that the data are representative of real price observations, volatility is not understated, and correlations are reasonable approximations of those among real prices. **Transformations must not understate volatility.**

**Principle four — reflective of observed or quoted prices.**
Where the data used are **not** derived from real price observations, the bank carries an additional demonstration burden.

> **Principle three is the one that catches proxying.** Smoothing a sparse series, averaging across names, or substituting a broad index will all *reduce measured volatility* — which reduces capital. The principle names that behaviour and forbids it.

---

## 6. The exceptional-circumstances provision (`MAR31.24`)

Basel acknowledges that *"on very rare occasions"* a significant number of modellable risk factors across different banks may become non-modellable **due to a widespread reduction in trading activities** — during significant cross-border financial market stress, or a major regime shift.

A possible supervisory response is to **continue treating as modellable a risk factor that no longer passes the RFET**. However:

> **"Such a response should not facilitate a decrease in capital requirements. Supervisory authorities should only pursue such a response under the most extraordinary, systemic circumstances."**

This is a stability provision, not relief. Its purpose is to stop a liquidity shock from mechanically converting a large share of a bank's model into NMRFs at exactly the worst moment — a procyclicality trap.

---

## 7. Capitalising NMRFs — the SES

### 7.1 The stress scenario (`MAR33.16`)

Capital for each NMRF is determined using a stress scenario *"calibrated to be at least as prudent as the ES calibration used for modelled risks (ie a loss calibrated to a 97.5% confidence threshold over a period of stress)."*

The bank must determine a **common 12-month period of stress across all NMRFs in the same risk class**.

**Bucket-level calculation:** subject to supervisory approval, a bank may calculate stress scenario capital **at the bucket level** — using the same buckets used to disprove modellability under `MAR31.16` — for risk factors belonging to **curves, surfaces or cubes**, giving a single SES for all NMRFs in a bucket.

### 7.2 The liquidity horizon (`MAR33.16(1)`)

> For each NMRF, the liquidity horizon of the stress scenario must be **the greater of** the liquidity horizon assigned to the risk factor in `MAR33.12` **and 20 days**. The supervisory authority **may require a higher liquidity horizon**.

**Worked implication:**

| Risk factor | `MAR33.12` LH | **NMRF LH** |
|---|---|---|
| USD interest rate | 10 | **20** ← floored |
| Large-cap equity price | 10 | **20** ← floored |
| Corporate credit spread (IG) | 40 | **40** |
| Credit spread volatility | 120 | **120** |

**For the most liquid factor categories the NMRF floor doubles the horizon** — which, under a broadly square-root scaling, increases the stress loss by roughly √2.

### 7.3 Idiosyncratic concessions (`MAR33.16(2)`)

For NMRFs arising from **idiosyncratic credit spread risk**, and separately for those arising from **idiosyncratic equity risk** (spot, futures and forward prices, equity repo rates, dividends and volatilities), a bank may:

- apply a **common 12-month stress period**; and
- use a **zero correlation assumption** when aggregating gains and losses — **provided the bank conducts analysis demonstrating to its supervisor that this is appropriate**.

Footnote 2 to `MAR33.16` describes the expected evidence in unusual technical detail: tests *"generally done on the residuals of panel regressions where the dependent variable is the change in issuer spread while the independent variables can be either a change in a market factor or a dummy variable for sector and/or region."* If the model is missing systematic explanatory factors or the data suffer measurement error, the residuals would exhibit **heteroscedasticity** (testable via White or Breusch-Pagan tests) and/or **serial correlation** (Durbin-Watson, Lagrange multiplier tests) and/or **cross-sectional correlation (clustering)**.

Correlation or diversification effects between **other, non-idiosyncratic** NMRFs are recognised only through the `MAR33.17` formula.

### 7.4 The backstop (`MAR33.16(3)`)

> In the event that a bank cannot provide a stress scenario which is acceptable for the supervisor, **the bank will have to use the maximum possible loss as the stress scenario.**

**There is no "we could not calibrate it" outcome.** The alternative to an acceptable stress scenario is the worst conceivable loss.

### 7.5 The aggregation formula (`MAR33.17`)

```
              ┌                                                                          ┐ ½
              │   I                J                 ⎛     K            ⎞²         K     │
   SES  =     │   Σ  ISES²_NM,i +  Σ  ISES²_NM,j  +  ⎜ ρ · Σ  SES_NM,k ⎟   + (1−ρ²)· Σ SES²_NM,k │
              │  i=1              j=1               ⎝    k=1           ⎠        k=1     │
              └                                                                          ┘
```

| Term | Meaning |
|---|---|
| `ISES_NM,i` | SES for idiosyncratic **credit spread** NMRF *i*, from the *I* factors demonstrated appropriate to aggregate with **zero correlation** |
| `ISES_NM,j` | SES for idiosyncratic **equity** NMRF *j*, from the *J* such factors |
| `SES_NM,k` | SES for the remaining *K* non-modellable factors in model-eligible desks |
| **ρ** | **0.6** |

**Reading the three terms:**

1. **Idiosyncratic credit** — sum of **squares**. Full diversification, because genuinely independent idiosyncratic risks do diversify.
2. **Idiosyncratic equity** — sum of squares, same logic.
3. **Everything else** — `(ρ·Σ)² + (1−ρ²)·Σ(²)`. At ρ = 0 this collapses to the sum of squares (full diversification); at ρ = 1 it collapses to `(Σ)²` (none). **At ρ = 0.6 it sits deliberately between the two.**

> **There is no path by which a non-idiosyncratic NMRF obtains the diversification a modellable factor obtains.** That asymmetry is the entire economic content of the regime — it is what makes evidencing a factor worth the data investment.

### 7.6 Worked example

A desk has:

| NMRF | Category | SES ($m) |
|---|---|---|
| Issuer X idiosyncratic spread | Idio. credit | 1.20 |
| Issuer Y idiosyncratic spread | Idio. credit | 0.90 |
| Issuer Z idiosyncratic equity | Idio. equity | 0.70 |
| 40y EM swap point | Other | 2.10 |
| Illiquid vol surface wing | Other | 1.40 |
| Exotic basis | Other | 0.80 |

```
   Term 1 (idio credit)  =  1.20² + 0.90²                  =  1.4400 + 0.8100  =  2.2500
   Term 2 (idio equity)  =  0.70²                          =                       0.4900

   Σ SES_other           =  2.10 + 1.40 + 0.80             =  4.3000
   Σ SES²_other          =  4.41 + 1.96 + 0.64             =  7.0100

   Term 3  =  (0.6 × 4.30)²  +  (1 − 0.36) × 7.0100
           =  2.58²          +  0.64 × 7.0100
           =  6.6564         +  4.4864                     =  11.1428

   SES  =  √( 2.2500 + 0.4900 + 11.1428 )  =  √13.8828     =  $3.726m
```

**For comparison:** a simple sum of all six would be $7.10m; a full sum-of-squares (complete diversification) would be √(2.25 + 0.49 + 7.01) = $3.122m. **The prescribed formula gives $3.726m — 19% above full diversification and 48% below no diversification.** That gap is exactly what ρ = 0.6 is purchasing.

---

## 8. Reducing NMRF capital — what actually works

| Approach | Effect | Caution |
|---|---|---|
| **Source more real prices** | The direct fix — buy vendor data with supervisor-evidenceable transactions and committed quotes | Must meet `MAR31.12` criteria; indicative quotes do not count |
| **Improve observation capture** | Many banks fail the RFET on record-keeping, not on liquidity | Own transactions are the easiest criterion to satisfy and the most often unrecorded |
| **Use regulatory bucketing well** | Aggregating across a sensible bucket can push a factor over the threshold | Buckets must be non-overlapping; one observation, one bucket |
| **Reduce the factor set** | Fewer, better-observed factors | Must remain consistent with PLA/RTPL mapping (`MAR31.26(1)(a)`) |
| **Bucket-level SES** | One scenario for a whole curve bucket rather than each point | Requires supervisory approval |
| **Demonstrate idiosyncratic independence** | Unlocks zero-correlation aggregation | Requires the `MAR33.16(2)` statistical evidence |
| **Trade the exposure out** | Removes the factor entirely | The commercial decision the regime is designed to prompt |
| ~~Replace the NMRF with a modellable proxy plus a basis~~ | **Does not work** | The basis is itself non-modellable (`MAR31.13` fn 3) |

---

## 9. Pseudocode

```
FUNCTION rfet(risk_factor, observations, assessment_date):
    # Only real prices per MAR31.12; max ONE per day
    real = [o for o in observations
              if o.is_real_price                    # transaction / verifiable /
                                                    # committed quote / qualifying vendor
             AND NOT o.is_collateral_valuation]     # explicitly excluded
    daily = deduplicate_by_day(real)                # MAR31.13

    window = one_year_ending(assessment_date)       # may finish up to 1 month
                                                    # earlier if data is lagged (fn 2)
    obs = [o for o in daily if o.date IN window]

    # Criterion 2 — 100 in 12 months
    IF len(obs) >= 100:
        RETURN MODELLABLE

    # Criterion 1 — 24 per year AND no 90-day window with fewer than 4
    IF len(obs) >= 24:
        worst_gap = min( count_in_window(obs, d, d + 90_days)
                         for d in window.days )
        IF worst_gap >= 4:
            RETURN MODELLABLE

    RETURN NON_MODELLABLE


FUNCTION classify_derived_factor(factor):
    # MAR31.13 footnote 3 — contamination flows ONE WAY
    IF any(component.is_non_modellable for component in factor.components):
        RETURN NON_MODELLABLE
    IF factor.spans_distinct_buckets:
        RETURN MODELLABLE IF rfet(factor) == MODELLABLE ELSE NON_MODELLABLE
    RETURN MODELLABLE                                # MAR31.26(1)


FUNCTION nmrf_liquidity_horizon(factor):
    RETURN max( mar33_12_horizon(factor), 20 )       # MAR33.16(1)


FUNCTION ses_aggregate(nmrfs, rho = 0.6):
    idio_credit = [n for n in nmrfs
                     if n.is_idiosyncratic_credit_spread
                    AND n.zero_correlation_demonstrated]   # MAR33.16(2)
    idio_equity = [n for n in nmrfs
                     if n.is_idiosyncratic_equity
                    AND n.zero_correlation_demonstrated]
    rest = [n for n in nmrfs if n NOT IN idio_credit + idio_equity]

    t1 = sum(n.ses**2 for n in idio_credit)
    t2 = sum(n.ses**2 for n in idio_equity)
    s  = sum(n.ses for n in rest)
    t3 = (rho*s)**2 + (1 - rho**2)*sum(n.ses**2 for n in rest)

    RETURN sqrt(t1 + t2 + t3)                        # MAR33.17
```

---

## 10. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Real price definition** | Only `MAR31.12` categories counted; collateral valuations excluded |
| 2 | **Committed quotes verified** | Through a vendor, platform or exchange — not indicative |
| 3 | **Vendor evidence** | Vendor agrees to provide evidence **to supervisors** on request |
| 4 | **One observation per day** | Deduplication enforced |
| 5 | **Both criteria tested** | 24/4 **and** 100-in-12-months |
| 6 | **90-day gap** | Rolling windows tested, monitored **monthly** |
| 7 | **Data lag** | RFET window within one month of the ES calibration window |
| 8 | **Basis rule** | Any combination touching an NMRF is non-modellable |
| 9 | **Buckets non-overlapping** | And each observation counted in **one** bucket only |
| 10 | **Correct bucketing row** | (A)/(B)/(C)/(D) per `MAR31.17(2)`, including the swaption-vol special case |
| 11 | **Parametric functions** | RFET at the **market data** level, not the parameter level |
| 12 | **Idiosyncratic residual** | Treated as NMRF unless the issuer itself has sufficient observations |
| 13 | **Interpolation consistency** | Matches PLA/RTPL mapping (`MAR31.26(1)(a)`) |
| 14 | **Extrapolation** | Approved; uses more than one modellable factor; reflected in RTPL |
| 15 | **Volatility not understated** | Averaging and proxy choices reviewed against Principle three |
| 16 | **NMRF horizon floor** | max(`MAR33.12` LH, **20 days**) |
| 17 | **Common stress period** | Per risk class (`MAR33.16`) |
| 18 | **Zero-correlation evidence** | Panel-regression residual diagnostics performed |
| 19 | **SES ρ** | 0.6 — not 0.5 (that is the IMCC weight) |
| 20 | **Backstop implemented** | Maximum possible loss where no acceptable scenario exists |
| 21 | **Quarterly reassessment** | RFET run quarterly, monitored monthly |

---

## 11. Common implementation errors

| Error | Consequence |
|---|---|
| Counting indicative quotes as real prices | RFET passed on evidence that does not exist |
| Counting collateral valuations | Explicitly prohibited (`MAR31.12`) |
| Multiple observations per day counted | Inflates counts; RFET invalid |
| Testing only the 100-observation criterion | Misses factors that qualify under 24/4, and vice versa |
| Ignoring the 90-day gap condition | Passes seasonally-active factors that should fail |
| Proxying an NMRF into a modellable factor plus basis | The basis is non-modellable; nothing is gained |
| RFET at the parameter level of a fitted curve | Contradicts `MAR31.19` |
| Treating issuer idiosyncratic risk as covered by a sector proxy | The residual is an NMRF (`MAR31.20`) |
| NMRF liquidity horizon below 20 days | Contradicts `MAR33.16(1)` |
| Full diversification across all NMRFs | Contradicts `MAR33.17` |
| Confusing ρ = 0.6 (SES) with ρ = 0.5 (IMCC) | Wrong capital in both formulas |
| Assuming zero correlation for idiosyncratic NMRFs without evidence | Requires demonstrated analysis (`MAR33.16(2)`) |
| Interpolating in RFET differently from RTPL | Contradicts `MAR31.26(1)(a)` |
| Smoothing sparse data to stabilise it | Understates volatility; contradicts Principle three |

---

## 12. Limitations

- **The RFET is a data-sourcing problem, not a modelling problem.** Passing it depends on the bank's ability to *evidence* observations, which is an infrastructure and vendor-contract capability. Many failures are record-keeping failures rather than genuine illiquidity.
- **It is procyclical by construction.** A liquidity shock reduces observations, converting factors to NMRFs and raising capital exactly when the bank is under stress. `MAR31.24` exists to allow supervisory relief, but only in extraordinary systemic circumstances.
- **Bucketing is a blunt instrument.** A single observation in a wide bucket can support a factor across a broad maturity range where liquidity is in fact concentrated at one point.
- **SES stress scenarios are model-dependent.** "A 97.5% loss over a period of stress" is not a fully specified calculation, and banks will implement it differently.
- **The regime is expensive by design.** The capital differential is the incentive, and it prices data infrastructure as much as it prices risk.

---

## 13. Related Concepts

- [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [05 — Credit Spread Risk](05_Credit_Spread_Risk.md) — proxy mapping and idiosyncratic residuals
- [23 — Market Data and Curves](23_Market_Data_and_Curves.md) · [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR31.12`–`MAR31.26` RFET and principles; `MAR33.16`–`MAR33.17` SES |
| BCBS | *Explanatory note on the minimum capital requirements for market risk* | Jan 2019 | https://www.bis.org/bcbs/publ/d457_note.pdf | Rationale for the NMRF regime |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR31/MAR33 text |

*Accessed 25 August 2026.*
