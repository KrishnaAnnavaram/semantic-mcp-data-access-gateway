# 15 — Backtesting and the P&L Attribution Test

**Level:** 8 · **Prerequisites:** [11](11_VaR.md), [14](14_PnL_and_PnL_Explain.md) · **Feeds:** [18](18_FRTB_Internal_Models_Approach.md), [26](26_Model_Risk_and_Validation.md)

---

## 1. Plain English

**Backtesting asks: did the model's predictions match what actually happened?**

A 99% VaR model claims losses will exceed the VaR figure on about 1% of days. Count the days it was exceeded. If the count is close to 1%, the model looks sound. If losses exceeded VaR on 8% of days, the model is understating risk, and no amount of theoretical elegance rescues it.

> **Backtesting is the only part of market risk measurement that is genuinely falsifiable.** Everything else — the choice of distribution, the lookback window, the correlation assumptions — is a modelling judgement. The exception count is a fact.

---

## 2. Banking example

A desk's 99% 1-day VaR over 250 trading days, compared with each day's loss.

| Outcome | Exceptions | Reading |
|---|---|---|
| 2 | Expected 2.5 | Model looks well-calibrated |
| 6 | | Concerning — investigate |
| 15 | | Model is badly understating risk |
| 0 | | **Also a problem** — the model is over-conservative, wasting capital and distorting limits |

**Zero exceptions is not a good result.** A model that never gets exceeded is not measuring 99%; it is measuring something much higher, consuming capital that could support business and producing limits that bind on the wrong things. Backtesting is a **two-sided** test in substance, even where the regulatory response is one-sided.

---

## 3. The statistics

### 3.1 The distribution of exceptions

Under a correct model, exceptions are Bernoulli trials with probability `p = 1 − α`. Over *N* days:

```
   X  ~  Binomial(N, p)

   E[X]    =  N · p
   SD[X]   =  √( N · p · (1−p) )
```

**For N = 250, p = 0.01:**

```
   E[X]   =  2.5
   SD[X]  =  √(250 × 0.01 × 0.99)  =  √2.475  =  1.573
```

### 3.2 Why a single year cannot settle the question

The standard deviation (1.573) is **63% of the mean (2.5)**. The signal-to-noise ratio at 250 observations is poor.

`MAR99` sets out the cumulative probabilities on a 250-observation sample, at a true coverage level of 99%:

| Exceptions | Cumulative probability |
|---|---|
| 0 | 8.11% |
| 1 | 28.58% |
| 2 | 54.32% |
| 3 | 75.81% |
| 4 | 89.22% |
| 5 | 95.88% |
| 6 | 98.63% |
| 7 | 99.60% |
| 8 | 99.89% |
| 9 | 99.97% |
| 10 or more | 99.99% |

**Read the 4-exception row.** Getting four or fewer exceptions has probability 89.22% — so getting *five or more* has probability 10.78%, even from a perfectly calibrated model. **A correct model produces an "amber" outcome roughly one year in ten.** That is why the zones are a graduated supervisory response rather than a pass/fail verdict.

`MAR99` states the general rule for other sample sizes: **the amber zone begins where the cumulative probability equals or exceeds 95%, and the red zone where it equals or exceeds 99.99%.**

### 3.3 Two kinds of test

| Test | Question | Method |
|---|---|---|
| **Coverage (unconditional)** | Is the *number* of exceptions right? | Kupiec proportion-of-failures / binomial test |
| **Independence (conditional)** | Are exceptions *clustered*? | Christoffersen test; runs tests |

**Independence matters as much as count.** Three exceptions spread across a year is a well-behaved model. Three exceptions on three consecutive days is a model that fails to react to a volatility regime change — the same count, a very different defect. Basel's zones test coverage; a competent internal validation programme tests both.

---

## 4. FRTB backtesting — bank-wide level

### 4.1 The specification

`MAR32.4`: backtesting compares the **VaR measure calibrated to a one-day holding period** against **each of the actual P&L (APL) and hypothetical P&L (HPL)** over the prior 12 months.

`MAR32.5`: bank-wide backtesting uses a VaR measure at the **99th percentile**.

**The exception rule (`MAR32.5(1)`):**

> An exception occurs when **either** the actual loss **or** the hypothetical loss exceeds the corresponding daily VaR. Exceptions for actual losses are counted **separately** from exceptions for hypothetical losses; **the overall number of exceptions is the greater of these two amounts.**

`MAR32.5(2)`: if **either the P&L or the daily VaR measure is not available or impossible to compute, it counts as an outlier.** A system failure is a model failure for this purpose — there is no "no data" category.

### 4.2 The one permitted exclusion

`MAR32.6` allows an outlier to be disregarded **only** if all of the following hold:

1. The bank can show it relates to a **non-modellable risk factor**;
2. The **capital requirement for that NMRF exceeds** the actual or hypothetical loss for that day;
3. The supervisory authority is **notified and does not object**;
4. The bank **documents the history of the movement** of that NMRF and has supporting evidence that it caused the loss.

This is a narrow, evidenced carve-out, not a general discretion. The logic is sound: if the bank has already been charged capital for the factor in excess of the loss it caused, counting the loss again as a model failure would double-penalise.

### 4.3 The traffic-light zones — retained, not retired

A widespread misconception holds that FRTB abolished the traffic-light framework. It did not. `MAR32.8`–`MAR32.9` retain it for **bank-wide** backtesting:

| Zone | Exceptions | Backtesting-dependent multiplier | Supervisory response |
|---|---|---|---|
| **Green** | 0 | **1.50** | `MAR32.10`: generally **no** capital increase for backtesting |
| | 1 | 1.50 | |
| | 2 | 1.50 | |
| | 3 | 1.50 | |
| | 4 | 1.50 | |
| **Amber** | 5 | **1.70** | `MAR32.11`: supervisor **will** impose a higher capital requirement as a backtesting add-on |
| | 6 | 1.76 | |
| | 7 | 1.83 | |
| | 8 | 1.88 | |
| | 9 | 1.92 | |
| **Red** | **10 or more** | **2.00** | `MAR32.15`: supervisor **automatically** increases the multiplier, or may disallow the model |

Basel's characterisation of the three zones (`MAR32.8`):

- **Green** — *"results that do not themselves suggest a problem with the quality or accuracy of a bank's model."*
- **Amber** — *"results that do raise questions in this regard, for which such a conclusion is not definitive."*
- **Red** — *"a result that almost certainly indicates a problem with a bank's risk model."*

**What changed from the earlier framework is the scale, not the structure.** Under the 1996 Amendment and Basel 2.5 the multiplication factor was 3 plus an add-on. Under FRTB `m_c` is **fixed at 1.5** plus a backtesting add-on of **0 to 0.5** (`MAR33.42`), which is where the 1.50–2.00 range above comes from.

`MAR32.14` adds that even within the amber zone, *"in the case of severe problems with the basic integrity of the model,"* the supervisor may disallow the model entirely.

### 4.4 Other requirements

- `MAR32.12`: the bank must **document every exception**, including an explanation for each.
- `MAR32.13`: a bank **may** additionally backtest at other confidence levels or run other statistical tests. Basel sets a floor, not a ceiling.
- `MAR32.7`: the scope of the bank-wide backtesting portfolio is **updated quarterly**, based on the latest desk-level backtesting, RFET and PLA results.

---

## 5. FRTB backtesting — trading desk level

This is the genuinely new regime, and its consequence is far harder than a multiplier.

### 5.1 The specification (`MAR32.18`)

Desk-level backtesting compares each desk's **one-day VaR** — calibrated to the **most recent 12 months' data, equally weighted** — at **both the 97.5th and the 99th percentile**, using at least one year of current observations of the desk's one-day P&L.

The same exception rule applies: either actual or hypothetical loss exceeding VaR is an exception; the two are counted separately; **the overall number is the greater of the two**. Unavailable P&L or VaR counts as an outlier.

### 5.2 The consequence (`MAR32.19`)

> If any given trading desk experiences **more than 12 exceptions at the 99th percentile** or **more than 30 exceptions at the 97.5th percentile** in the most recent 12-month period, **the capital requirement for all of the positions in that trading desk must be determined using the standardised approach.**

**Compare the thresholds to expectation:**

| Level | Expected exceptions in 250 days | Threshold | Ratio |
|---|---|---|---|
| 99% | 2.5 | **>12** | ~4.8× |
| 97.5% | 6.25 | **>30** | ~4.8× |

Both thresholds sit at roughly **4.8× the expected count** — a deliberately consistent calibration, and a genuinely high bar. A desk does not lose its model for bad luck; it loses it for a model that is systematically wrong.

**The two-stage rule for default risk.** Footnote 1 to `MAR32.19`: desks with exposure to issuer default risk must pass a **two-stage approval process** — first the market risk model must pass backtesting and PLA; only then, conditional on that approval, may the desk apply to model default risk. **Desks that fail either test must be capitalised under the standardised approach.**

### 5.3 The 10% floor

`MAR32.2`: for a bank to **remain eligible** to use the IMA at all, a minimum of **10% of the bank's aggregated market risk capital requirement** must be based on positions held in desks that qualify for internal models by satisfying backtesting and PLA. This is assessed **quarterly**, when calculating the aggregate capital requirement per `MAR33.43`.

> This is an anti-cherry-picking provision. Without it, a bank could seek IMA approval for one small, well-behaved desk, claim to be an internal-models bank, and run everything else on the standardised approach. The 10% floor requires the internal model to carry a meaningful share of the firm's actual risk.

### 5.4 Approval

`MAR32.3`: the backtesting and PLA programmes must begin on the date the internal models capital requirement becomes effective. **For supervisory approval of a model, the bank must provide a one-year backtesting and PLA test report** to confirm the model's quality, and the supervisor may require results before that date.

---

## 6. The P&L Attribution (PLA) test

### 6.1 What it tests, and why backtesting is not enough

Backtesting asks whether the model's *distribution* is wide enough. PLA asks a different and more searching question: **does the risk model actually describe this portfolio?**

`MAR32.24`: the PLA test compares a desk's **RTPL** with its **HPL**, *"to determine whether the risk factors included and the valuation engines used in the trading desk's risk management model capture the material drivers of the bank's P&L by determining if there is a significant degree of association between the two P&L measures."*

**The HPL used for PLA must be identical to the HPL used for backtesting.**

> A model can pass backtesting and fail PLA. Suppose the risk model omits a risk factor but is calibrated wide enough that losses rarely exceed VaR. Backtesting sees few exceptions and is satisfied. PLA sees that the model's day-to-day P&L does not track the portfolio's actual day-to-day P&L, and correctly concludes that the model is not describing the book. **PLA catches the model that is right by accident.**

`MAR32.21`: the test must be performed **on a standalone basis for each trading desk** in scope for the IMA.

### 6.2 The data

`MAR32.35`: both metrics use the time series of the **most recent 250 trading days** of RTPL and HPL observations.

### 6.3 Metric 1 — Spearman rank correlation (`MAR32.36`–`MAR32.38`)

**Method:**

1. Rank the HPL series by size — **lowest value gets rank 1**, next lowest rank 2, and so on (`MAR32.36`).
2. Rank the RTPL series the same way (`MAR32.37`).
3. Compute the correlation coefficient of the two rank series (`MAR32.38`).

**Why ranks rather than values?** Rank correlation is robust to outliers and to monotone scaling differences. It asks whether the model *orders* the days correctly — whether the days it thinks are bad are the days that were bad — rather than whether it gets magnitudes exactly right.

### 6.4 Metric 2 — Kolmogorov-Smirnov (`MAR32.39`–`MAR32.41`)

**Method:**

1. Compute the empirical CDF of RTPL. For any value, this is **0.004 × the number of RTPL observations less than or equal to it** (`MAR32.39`). *(0.004 = 1/250.)*
2. Compute the empirical CDF of HPL the same way (`MAR32.40`).
3. **The KS metric is the largest absolute difference observed between the two empirical CDFs at any P&L value** (`MAR32.41`).

Where Spearman tests *ordering*, KS tests *distributional shape*. A model could rank days perfectly and still produce a P&L distribution that is systematically too narrow — KS catches that; Spearman does not.

### 6.5 Worked example

*Illustrated on 10 observations for legibility. The actual test requires 250 (`MAR32.35`), where each ECDF step is 0.004 rather than 0.1.*

| Day | HPL | RTPL | Rank(HPL) | Rank(RTPL) | d | d² |
|---|---|---|---|---|---|---|
| 1 | −3.2 | −2.9 | 1 | 1 | 0 | 0 |
| 2 | −1.8 | −2.1 | 2 | 2 | 0 | 0 |
| 3 | −0.9 | −0.6 | 3 | **4** | −1 | 1 |
| 4 | −0.4 | −0.7 | 4 | **3** | +1 | 1 |
| 5 | 0.2 | 0.4 | 5 | 5 | 0 | 0 |
| 6 | 0.7 | 0.5 | 6 | 6 | 0 | 0 |
| 7 | 1.1 | 1.3 | 7 | 7 | 0 | 0 |
| 8 | 1.6 | 1.4 | 8 | 8 | 0 | 0 |
| 9 | 2.4 | 2.8 | 9 | 9 | 0 | 0 |
| 10 | 3.9 | 3.5 | 10 | 10 | 0 | 0 |
| | | | | | **Σd²** | **2** |

**Spearman correlation** (rank form, valid with no ties):

```
                 6 · Σd²                6 × 2              12
   ρ_s  =  1 − ─────────────  =  1 − ───────────  =  1 − ──────  =  0.98788
                n(n² − 1)             10 × 99             990
```

**KS metric** — the maximum gap between the two empirical CDFs, which occurs at P&L = 0.5:

| At P&L = 0.5 | |
|---|---|
| HPL observations ≤ 0.5 | 5 → ECDF = 0.5 |
| RTPL observations ≤ 0.5 | 6 → ECDF = 0.6 |
| **Absolute difference** | **0.10** |

**Evaluation:** ρ_s = 0.988 is comfortably above 0.80. The KS of 0.10 sits between 0.09 and 0.12 — but note that with only 10 observations the ECDF moves in steps of 0.1, so the metric is far too granular to be meaningful. **This is exactly why the standard fixes the sample at 250.** At 250 observations the step is 0.004 and the statistic is well-resolved.

### 6.6 The zones (`MAR32.42`, Table 2)

| Zone | Condition |
|---|---|
| **Green** | Spearman correlation **above 0.80** **AND** KS **below 0.09** (p-value = 0.264) |
| **Red** | Spearman correlation **less than 0.70** **OR** KS **above 0.12** (p-value = 0.055) |
| **Amber** | Neither green nor red |

Note the asymmetry in the logic: green requires **both** conditions; red is triggered by **either**. The framework is deliberately easier to fail than to pass.

### 6.7 Consequences

**Red zone (`MAR32.43`):** the desk is **ineligible to use the IMA** and must use the standardised approach. Its risk exposures are included with the out-of-scope desks for SA purposes. It remains out of scope until **both**:

1. it produces outcomes in the PLA test **green** zone; and
2. it has satisfied the **backtesting exceptions requirements over the past 12 months**.

**Amber zone (`MAR32.44`):** the desk is **not** out of scope for the IMA, but:

1. it cannot return to green until it produces green-zone outcomes **and** has satisfied its backtesting requirements over the prior 12 months; and
2. **amber-zone desks are subject to a capital surcharge** as specified in `MAR33.43`.

> **The return path is the same for amber and red: green PLA results *plus* 12 months of clean backtesting.** A desk cannot buy its way back with one good quarter.

### 6.8 Data alignment — the anti-gaming rules

`MAR32.30`–`MAR32.33` govern how far a bank may reconcile the inputs of the two measures, and the asymmetry is deliberate:

| Permitted | Not permitted |
|---|---|
| Aligning **RTPL** input data to the data used in HPL, where documented, justified to the supervisor, and validated (`MAR32.30`) | Aligning **HPL** input data to RTPL inputs (`MAR32.33`) |
| Alignment where inputs differ due to different market-data providers, time fixing, or transformations (`MAR32.31`) | Aligning post-transformation where the transformation is part of the RTPL valuation process (`MAR32.32`) |
| | Adjustments to RTPL **or** HPL to address **"residual operational noise"** (`MAR32.33`) |

**"Residual operational noise"** is defined in `MAR32.33` as arising from computing HPL and RTPL in two different systems at two different points in time — data transitions, aggregation gaps below intervention tolerance, small differences in static/reference data and configuration. **Banks may not adjust it away.** If two systems disagree, that disagreement is part of the test result.

`MAR32.30(4)` requires the bank to quantify the effect of any permitted alignment by comparing RTPL on HPL-aligned market data against RTPL on unaligned data — when the process is designed or changed, and on supervisory request.

### 6.9 Exceptional situations (`MAR32.45`)

Basel acknowledges that *"on very rare occasions"* accurate models across many banks may simultaneously produce many exceptions or track P&L poorly — during significant cross-border financial market stress or a major regime shift. A possible supervisory response is to permit continued IMA use while requiring the models to take account of the regime shift *"as quickly as practicable."*

The standard is explicit that supervisors *"should only pursue such a response under the most extraordinary, systemic circumstances."* **This is not a routine appeal mechanism.**

---

## 7. Backtesting versus PLA — the comparison

| | **Backtesting** | **PLA test** |
|---|---|---|
| Compares | VaR vs APL and HPL | **RTPL vs HPL** |
| Question | Is the distribution wide enough? | Does the model **describe** this portfolio? |
| Level | Bank-wide **and** desk | **Desk only** |
| Metric | Exception count | Spearman correlation + KS |
| Sample | 250 days (12 months) | **250 days** |
| Confidence levels | 99% (bank-wide); 97.5% **and** 99% (desk) | n/a |
| Failure threshold | >12 @99% or >30 @97.5% (desk) | ρ<0.70 or KS>0.12 |
| Bank-wide consequence | Multiplier 1.50 → 2.00 | n/a |
| Desk consequence | Standardised approach | Standardised approach (red); surcharge (amber) |
| Catches | Model too narrow | **Missing risk factors; valuation differences** |

---

## 8. Pseudocode

```
FUNCTION backtest(var_series, apl_series, hpl_series, confidence):
    n = len(var_series)
    exceptions_apl, exceptions_hpl, unavailable = 0, 0, 0
    log = []

    FOR t IN range(n):
        # MAR32.5(2): missing P&L or missing VaR counts as an outlier
        IF var_series[t] IS NULL OR apl_series[t] IS NULL
                                 OR hpl_series[t] IS NULL:
            unavailable += 1
            log.append((t, "UNAVAILABLE"))
            CONTINUE

        IF -apl_series[t] > var_series[t]:
            exceptions_apl += 1
            log.append((t, "APL", -apl_series[t], var_series[t]))
        IF -hpl_series[t] > var_series[t]:
            exceptions_hpl += 1
            log.append((t, "HPL", -hpl_series[t], var_series[t]))

    # MAR32.5(1): counted separately; the overall count is the GREATER
    total = max(exceptions_apl, exceptions_hpl) + unavailable

    RETURN {
        "exceptions_apl": exceptions_apl,
        "exceptions_hpl": exceptions_hpl,
        "unavailable":    unavailable,
        "total":          total,
        "expected":       n * (1 - confidence),
        "zone":           bankwide_zone(total),          # MAR32.9 Table 1
        "multiplier":     bankwide_multiplier(total),
        "log":            log                            # MAR32.12: explain each
    }


FUNCTION desk_backtest_outcome(exc_99, exc_975):
    # MAR32.19 — strictly "more than"
    IF exc_99 > 12 OR exc_975 > 30:
        RETURN "FAIL — desk moves to the standardised approach"
    RETURN "PASS"


FUNCTION pla_test(rtpl, hpl):
    ASSERT len(rtpl) == 250 AND len(hpl) == 250        # MAR32.35

    # --- Spearman (MAR32.36-38): rank ascending, lowest = 1 ---
    rank_h = rank_ascending(hpl)
    rank_r = rank_ascending(rtpl)
    spearman = pearson_correlation(rank_h, rank_r)

    # --- KS (MAR32.39-41): step is exactly 0.004 = 1/250 ---
    ks = 0.0
    FOR x IN sorted(set(rtpl) UNION set(hpl)):
        ecdf_r = 0.004 * count(v <= x for v in rtpl)
        ecdf_h = 0.004 * count(v <= x for v in hpl)
        ks = max(ks, abs(ecdf_r - ecdf_h))

    # --- Zones (MAR32.42): green needs BOTH; red triggers on EITHER ---
    IF spearman > 0.80 AND ks < 0.09:
        zone = "GREEN"
    ELIF spearman < 0.70 OR ks > 0.12:
        zone = "RED"
    ELSE:
        zone = "AMBER"

    RETURN { "spearman": spearman, "ks": ks, "zone": zone }
```

---

## 9. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Both P&L measures tested** | APL and HPL counted separately; overall = greater (`MAR32.5(1)`) |
| 2 | **Missing data counted** | Unavailable P&L or VaR counts as an outlier (`MAR32.5(2)`) |
| 3 | **Fees excluded** | From both APL and HPL (`MAR32.26`) |
| 4 | **HPL is static** | No intraday trading, no new or modified deals (`MAR32.25`) |
| 5 | **Desk levels correct** | Desk backtesting at **both** 97.5% and 99% (`MAR32.18`) |
| 6 | **VaR calibration** | Most recent 12 months, **equally weighted** (`MAR32.18`) |
| 7 | **Thresholds strict** | ">12" and ">30", not "≥" (`MAR32.19`) |
| 8 | **PLA sample** | Exactly 250 trading days (`MAR32.35`) |
| 9 | **KS constant** | 0.004, matching a 250-day sample (`MAR32.39`) |
| 10 | **Zone logic** | Green requires both conditions; red triggers on either (`MAR32.42`) |
| 11 | **Alignment direction** | RTPL may be aligned to HPL; **never the reverse** (`MAR32.33`) |
| 12 | **No noise adjustment** | Residual operational noise not adjusted away (`MAR32.33`) |
| 13 | **Every exception explained** | Documented with a written cause (`MAR32.12`) |
| 14 | **NMRF exclusions evidenced** | All four `MAR32.6` conditions met and supervisor notified |
| 15 | **10% floor** | Assessed quarterly (`MAR32.2`) |
| 16 | **Independence tested** | Clustering examined, not only the count |

---

## 10. Common implementation errors

| Error | Consequence |
|---|---|
| Backtesting against APL only | Fees and intraday trading contaminate the test |
| Adding APL and HPL exceptions together | Overstates the count; the rule is the **greater** of the two |
| Treating missing data as "not tested" | Understates exceptions; contradicts `MAR32.5(2)` |
| Desk backtesting at 99% only | Misses the 97.5% threshold entirely |
| Using "≥12" instead of ">12" | Fails a desk that passes |
| Aligning HPL to RTPL | Prohibited; makes the test circular |
| Adjusting away operational noise | Prohibited; hides a real systems difference |
| Ranking HPL descending | Inverts the Spearman metric |
| Using 1/n with n ≠ 250 for the KS constant | Metric not comparable to the thresholds |
| Green zone declared on one metric | Green requires **both** |
| Assuming a good quarter restores green | Requires green PLA **plus** 12 months of clean backtesting |
| Treating traffic lights as superseded | They are retained bank-wide (`MAR32.8`–`MAR32.9`) |
| Zero exceptions treated as success | Over-conservative model, wasted capital |

---

## 11. Limitations

1. **Low statistical power.** 250 observations cannot distinguish a 99% model from a 98% model with any confidence. This is a property of the data, not of the test design.
2. **Backtesting validates VaR, not ES.** ES is not directly backtestable in the same way ([12 §9.1](12_Expected_Shortfall.md)); FRTB validates the ES model indirectly, through VaR backtesting and PLA.
3. **Exception counts say nothing about severity.** Twelve exceptions of $1 over VaR and twelve of $100m over VaR score identically.
4. **The portfolio changes.** A year of backtesting a desk whose strategy changed halfway through is testing two different books with one statistic.
5. **PLA can fail for benign reasons** — genuine systems differences, market-data timing, legitimate valuation differences — which is exactly why `MAR32.30` permits *documented* RTPL alignment while forbidding the reverse.
6. **A passing model can still be wrong** about anything not exercised by the 250 days observed.

---

## 12. Related Concepts

- [11 — VaR](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md) · [14 — P&L and P&L Explain](14_PnL_and_PnL_Explain.md)
- [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md) · [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)
- [26 — Model Risk and Validation](26_Model_Risk_and_Validation.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR32` in full; `MAR99` backtesting zone boundaries and cumulative probabilities |
| BCBS | *Supervisory framework for the use of backtesting* | Jan 1996 | https://www.bis.org/publ/bcbs22.pdf | Origin of the traffic-light framework |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR32 and MAR99 text |

*Accessed 25 August 2026.*
