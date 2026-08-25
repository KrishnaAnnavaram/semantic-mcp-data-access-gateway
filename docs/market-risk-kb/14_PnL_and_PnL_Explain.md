# 14 — P&L and P&L Explain

**Level:** 6 · **Prerequisites:** [04](04_Interest_Rate_Risk.md)–[09](09_Options_and_Greeks.md) · **Feeds:** [15](15_Backtesting.md), [18](18_FRTB_Internal_Models_Approach.md), [27](27_Controls_and_Governance.md)

---

## 1. Plain English

**P&L explain answers: "we made or lost this much today — why?"**

It decomposes the day's profit or loss into contributions from each risk factor and each business activity, and then measures what is left over. **The leftover — the unexplained residual — is the most informative number in the whole exercise.**

> A large unexplained residual means one of three things, and all three are serious: the risk model is missing a factor, a position is mis-booked, or a valuation is wrong. P&L explain is the daily control that catches all three, and it is the only routine process that reconciles the front office's valuation to the risk department's model.

---

## 2. The five flavours of P&L — and why FRTB depends on three of them

The word "P&L" is used loosely on a trading floor and precisely in a regulation. The Basel definitions govern.

| Term | Definition | Includes new trades? | Includes fees? | Regulatory use |
|---|---|---|---|---|
| **Actual P&L (APL)** | The real, booked daily P&L | **Yes** | **No** — excluded by `MAR32.26` | Backtesting |
| **Hypothetical P&L (HPL)** | Revaluation of the *previous day's* end-of-day positions using *today's* market data | **No** | **No** | Backtesting **and** PLA benchmark |
| **Risk-theoretical P&L (RTPL)** | P&L produced by the **valuation engine of the trading desk's risk management model** | No | No | PLA candidate |
| **Clean P&L** | Loosely, P&L excluding fees/commissions/reserves — institution-specific | Varies | No | Internal only |
| **Carry P&L** | The component arising purely from the passage of time | n/a | n/a | Attribution |

### 2.1 The Basel definitions, precisely

**HPL** (`MAR32.25`): *"must be calculated by revaluing the positions held at the end of the previous day using the market data of the present day (ie using static positions). As HPL measures changes in portfolio value that would occur when end-of-day positions remain unchanged, it must not take into account intraday trading nor new or modified deals, in contrast to the APL."*

Both APL and HPL **include** foreign-denominated positions and commodities included in the banking book.

**RTPL** (`MAR32.22`): *"the daily trading desk-level P&L that is produced by the valuation engine of the trading desk's risk management model."* Two constraints follow:

1. The risk management model **must include** all risk factors in the bank's ES model with supervisory parameters, **and** any risk factors deemed non-modellable by the supervisor (and therefore capitalised through NMRF rather than ES).
2. The RTPL **must not** take into account any risk factor that the bank does **not** include in the desk's risk management model.

> **That second constraint is the entire mechanism of the PLA test.** A bank cannot pass by quietly adding factors to the P&L calculation that its risk model does not actually carry. If a factor is not in the model, its P&L contribution must be absent from RTPL — and will therefore show up as a divergence from HPL, which does contain it.

### 2.2 What must be excluded, and from which measure

`MAR32.26`–`MAR32.28` are specific, and implementations frequently get these wrong:

| Item | APL | HPL |
|---|---|---|
| Fees and commissions | **Excluded** | **Excluded** |
| Valuation adjustments with their own capital treatment (e.g. CVA and its eligible hedges) | Excluded | Excluded |
| Valuation adjustments deducted from CET1 (e.g. DVA) | Excluded | Excluded |
| Other market-risk-related valuation adjustments | **Included, regardless of update frequency** | **Only if updated daily** (unless the supervisor agrees otherwise) |
| Smoothing of non-daily valuation adjustments | **Not allowed** | Not allowed |
| P&L due to the passage of time | **Included**, and treated **consistently in both HPL and RTPL** | Consistent with APL and RTPL |
| Valuation adjustments not computable at desk level | Not required at desk level; **included for bank-wide backtesting** | Same |

**Time effects** are defined in footnote 2 to `MAR32.28` as including *"the sensitivity to time, or theta effect … and carry or costs of funding."*

`MAR32.29`: both APL and HPL must be computed on **the same pricing models** — the same pricing functions, configurations, parametrisation, market data and systems — as those used to produce the reported daily P&L. This closes the loophole of running a friendlier pricer for the regulatory measure than for the books.

### 2.3 The relationship

```
   APL   =   HPL   +   intraday trading   +   new and modified deals
                    (fees and excluded valuation adjustments already removed from both)

   HPL   −   RTPL   =   what the market did that the risk model does not represent
```

The second line is the PLA test.

---

## 3. Worked example — a full daily P&L explain

**Book:** a mixed rates and credit desk.

| | |
|---|---|
| Opening PV (previous EOD) | $125,400,000 |
| Closing PV (today EOD) | $126,150,000 |
| **Actual P&L (APL)** | **+$750,000** |

**Market moves observed today:**

| Factor | Move |
|---|---|
| 10-year rate | **−4bp** |
| Credit spreads (IG) | **−2bp** (tightening) |
| Implied volatility | **−0.3 vol points** |

**Book sensitivities (previous EOD):**

| Sensitivity | Value |
|---|---|
| DV01 | $95,000 /bp |
| CS01 | $48,000 /bp |
| Vega | $210,000 /vol point |

### 3.1 The decomposition

| # | Component | Calculation | P&L ($000s) |
|---|---|---|---|
| 1 | **Carry** (coupon accrual net of funding) | — | **+85** |
| 2 | **Roll-down** | — | **+22** |
| 3 | **Rates — delta** | 95,000 × 4bp | **+380** |
| 4 | **Rates — curve/KRD residual** | non-parallel component | **+18** |
| 5 | **Rates — convexity/gamma** | second order | **+12** |
| 6 | **Credit spread — delta** | 48,000 × 2bp | **+96** |
| 7 | **Vega** | 210,000 × (−0.3) | **−63** |
| 8 | **Theta** | option time decay | **−41** |
| 9 | **New trades** | intraday execution | **+215** |
| 10 | **Amendments / cancellations** | — | **−8** |
| 11 | **Fees and commissions** | — | **+22** |
| 12 | **Reserves / valuation adjustments** | — | **−15** |
| | **Total explained** | | **+723** |
| | **Actual P&L** | | **+750** |
| | **Unexplained residual** | | **+27** |

### 3.2 Assessing the residual

Two ratios are used, and they answer different questions:

```
   Residual / |Total P&L|      =   27 / 750   =   3.6%
   Residual / Σ|components|    =   27 / 977   =   2.8%
```

**Prefer the second.** The first has a fatal flaw: on a day when total P&L happens to be near zero — because a large gain and a large loss offset — the denominator collapses and the ratio explodes, generating an alarm that means nothing. The gross measure is stable.

Typical internal thresholds sit in the low single digits of the gross measure, escalating above that. **The threshold matters far less than the trend.** A residual that is small but *persistently the same sign* is worse than a larger random one: a systematic bias means something is structurally missing, whereas noise around zero is a tolerable measurement limit.

### 3.3 Deriving HPL and RTPL from the same day

**HPL** — static previous-day positions, today's market data, no new trades, no fees:

```
   HPL  =  APL  −  new trades  −  amendments  −  fees  −  reserves*
        =  750   −  215        −  (−8)       −  22    −  (−15)
        =  536
```

*(Reserves and valuation adjustments are removed here on the assumption that they are not updated daily; per `MAR32.27` those updated daily would remain in HPL. This is exactly the kind of institution-specific determination that must be documented.)*

HPL of **+$536k** contains carry, roll, all three market-move components, convexity, vega and theta — everything the market did to a frozen book.

**RTPL** — the same static book and the same market move, but valued by the *risk model's* valuation engine, using only the risk factors that model contains:

```
   RTPL  =  512
```

**The PLA divergence:**

```
   HPL − RTPL  =  536 − 512  =  +24
```

$24k of what the market did to this book is **not represented in the risk model**. In this case the desk investigated and found the risk model carried a single blended credit curve where the book actually had exposure to a bond-CDS basis. That basis moved; HPL captured it because HPL uses the front-office pricer; RTPL did not, because the basis is not a factor in the risk model.

> **This is exactly what the PLA test is designed to detect, and the remedy is to add the risk factor to the model — not to adjust the P&L.** See [15](15_Backtesting.md).

---

## 4. The components in detail

### 4.1 Market-driven components

| Component | How computed | Watch for |
|---|---|---|
| **Delta / rates** | `Σ DV01ᵢ × Δyᵢ` over buckets | Use the *bucketed* ladder, not total DV01 — [04 §7.2](04_Interest_Rate_Risk.md) |
| **Credit spread** | `Σ CS01ᵢ × Δsᵢ` | Separate from rates, always |
| **FX** | Position × ΔFX | Include the rate legs of forwards |
| **Equity** | Delta × ΔS | Single-name vs index split |
| **Vega** | `Σ νᵢ × Δσᵢ` by bucket | Bucketed by expiry and strike |
| **Convexity / gamma** | `½ Γ (ΔS)²` | Grows fast on large-move days |
| **Cross terms** | Vanna, cross-gamma | Material in FX and convertibles |

### 4.2 Time-driven components

| Component | Meaning |
|---|---|
| **Carry** | Coupon or dividend accrual, net of funding cost |
| **Roll-down** | Value change from moving down a sloped curve as maturity shortens |
| **Theta** | Option time decay |

`MAR32.28` requires that P&L due to the passage of time be **included in APL and treated consistently in both HPL and RTPL** — the treatment must match across the three measures, or the PLA test measures a convention difference rather than a model deficiency.

### 4.3 Activity-driven components

| Component | Meaning | In HPL? |
|---|---|---|
| **New trades** | Positions executed today | **No** |
| **Amendments / cancellations** | Changes to existing trades | **No** |
| **Fees and commissions** | Transaction revenue | **No** — excluded from both APL and HPL |
| **Reserves and valuation adjustments** | Bid-offer, model, concentration, funding | APL yes; HPL only if updated daily |

---

## 5. Order of decomposition — the path-dependence problem

**The decomposition is path-dependent, and the residual depends on the order in which factors are applied.**

Consider a book with rate and volatility exposure on a day when both moved. Applying the rate shock first and then the vol shock gives a different split than the reverse, because the cross term (vanna, or rate-vol cross-gamma) has to be assigned to one of them.

| Approach | Method | Trade-off |
|---|---|---|
| **Sequential (waterfall)** | Apply shocks one at a time, cumulatively | Simple; assigns cross terms to whichever comes later |
| **Independent (one-at-a-time)** | Each factor shocked alone from base | Symmetric; components do **not** sum to the total |
| **Shapley / average over orderings** | Average the marginal contribution over all orders | Fair and additive; expensive |
| **Explicit cross terms** | Report cross terms as their own line | Most transparent; more lines to explain |

**Recommendation for a production system: sequential with explicit cross-term reporting for the material pairs.** The important discipline is that the order is *fixed, documented and stable over time* — a decomposition whose ordering changes between days produces trends that are artefacts of methodology.

---

## 6. Interpreting the residual

| Residual pattern | Likely cause | Action |
|---|---|---|
| **Small, random, mean-zero** | Normal approximation error | None — this is the healthy state |
| **Small, persistently one-signed** | Missing systematic factor; a convention error | **Investigate — worse than a larger random residual** |
| **Large on high-volatility days only** | Second-order effects unmodelled; linearisation failing | Add convexity/gamma terms |
| **Large on one desk only** | Mis-booking; wrong pricing model; missing factor |Trace to position |
| **Large after a system change** | Regression | Roll back or fix |
| **Spikes on specific dates** | Fixings, expiries, roll dates, dividend dates | Calendar handling |
| **Growing over weeks** | Model drift; stale calibration | Recalibrate; validation review |

---

## 7. Pseudocode

```
FUNCTION pnl_explain(positions_t0, market_t0, market_t1,
                     positions_t1, actual_pnl, factor_order):

    components = {}
    m = copy(market_t0)
    v = value(positions_t0, m)

    # --- 1. Time effects first (they are not market moves) ---
    m_aged  = age_market(m, one_day)          # accrual, roll, theta
    v_aged  = value(positions_t0, m_aged)
    components["carry_roll_theta"] = v_aged - v
    v, m = v_aged, m_aged

    # --- 2. Market factors, in a FIXED, DOCUMENTED order ---
    FOR factor IN factor_order:               # order must be stable over time
        m_next = apply_factor_move(m, factor, market_t1[factor])
        v_next = value(positions_t0, m_next)  # FULL revaluation
        components[factor] = v_next - v
        v, m = v_next, m_next

    # --- 3. HPL is now complete: static book, full market move ---
    hpl = v - value(positions_t0, market_t0)

    # --- 4. Activity effects ---
    components["new_trades"]   = value_of_new_trades(positions_t1, market_t1)
    components["amendments"]   = value_of_amendments(positions_t0, positions_t1)
    components["fees"]         = booked_fees()
    components["reserves"]     = reserve_movement()

    explained  = sum(components.values())
    residual   = actual_pnl - explained
    gross      = sum(abs(c) for c in components.values())

    RETURN {
        "components":     components,
        "hpl":            hpl,
        "explained":      explained,
        "residual":       residual,
        "residual_ratio": residual / gross if gross > 0 else 0,   # gross basis
        "breach":         abs(residual) / gross > threshold
    }


FUNCTION compute_rtpl(positions_t0, market_t0, market_t1, risk_model):
    # RTPL uses ONLY the factors the risk model contains (MAR32.22(2))
    m1_restricted = market_t0.copy()
    FOR f IN risk_model.risk_factors:          # deliberately NOT all factors
        m1_restricted[f] = market_t1[f]

    RETURN ( risk_model.valuation_engine.value(positions_t0, m1_restricted)
           - risk_model.valuation_engine.value(positions_t0, market_t0) )
```

---

## 8. Data contract

**Input**

```
pnl_explain_input:
    business_date            date
    desk_id                  string
    positions_prev_eod       list<position>
    positions_curr_eod       list<position>
    market_prev_eod          market_snapshot
    market_curr_eod          market_snapshot
    actual_pnl               decimal          # from the books
    factor_decomposition_order  list<string>  # FIXED and versioned
```

**Output**

```
pnl_explain_output:
    business_date            date
    desk_id                  string
    apl                      decimal
    hpl                      decimal
    rtpl                     decimal
    components               map<string, decimal>
    explained_total          decimal
    unexplained_residual     decimal
    residual_ratio_gross     decimal
    residual_ratio_net       decimal
    threshold_breached       boolean
    decomposition_version    string           # methodology changes are visible
    commentary               string           # required when breached
```

> `decomposition_version` is not optional metadata. A change in the ordering or the component definitions changes every number in the series, and a residual trend that coincides with a version change is a methodology artefact, not a model failure.

---

## 9. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **APL ties to the books** | Reconciles exactly to the general ledger / product control P&L |
| 2 | **Same pricing models** | APL and HPL use the same pricers, config, data and systems as the reported P&L (`MAR32.29`) |
| 3 | **HPL is static** | No intraday trading, no new or modified deals (`MAR32.25`) |
| 4 | **Fees excluded** | From both APL and HPL (`MAR32.26`) |
| 5 | **CVA/DVA excluded** | Where separately capitalised or CET1-deducted (`MAR32.26`) |
| 6 | **Valuation adjustment frequency** | Daily-updated in HPL; all in APL; no smoothing (`MAR32.27`) |
| 7 | **Time effects consistent** | Same treatment in APL, HPL and RTPL (`MAR32.28`) |
| 8 | **RTPL factor discipline** | Contains **only** the risk model's factors (`MAR32.22(2)`) |
| 9 | **RTPL factor completeness** | Contains all ES-model factors **and** NMRFs (`MAR32.22(1)`) |
| 10 | **Residual on gross basis** | Ratio computed against Σ\|components\|, not net P&L |
| 11 | **Sign persistence test** | Runs of same-signed residuals flagged, not just magnitude |
| 12 | **Decomposition order fixed** | Versioned; changes reported |
| 13 | **Commentary on breach** | Every threshold breach carries a written explanation (`MAR32.12` requires documenting every backtesting exception) |

---

## 10. Common implementation errors

| Error | Consequence |
|---|---|
| Residual ratio on net P&L | False alarms whenever the day's P&L nets to near zero |
| HPL including new trades | PLA test measures trading activity, not model quality |
| Fees left in APL or HPL | Systematic bias in backtesting exceptions |
| RTPL computed with factors the risk model lacks | PLA passes while the model is deficient — defeats the test |
| Different pricers for APL and HPL | Divergence that is a systems artefact |
| Time effects treated differently across the three measures | PLA measures a convention, not a model gap |
| Decomposition order changed silently | Spurious trends in the residual series |
| Smoothing non-daily valuation adjustments | Explicitly prohibited (`MAR32.27`) |
| Ignoring small persistent residuals | The most informative signal, discarded |

---

## 11. Limitations

- P&L explain is **approximate by construction** for any non-linear book; some residual is the price of decomposition rather than evidence of error.
- The decomposition is **path-dependent** (§5); the split between factors is a convention, though the total is not.
- It detects *that* something is missing, not always *what* — investigation is a human process.
- It operates at desk level; valuation adjustments assessed only bank-wide cannot be attributed down (`MAR32.28`).
- A clean residual proves the model reproduces the front-office valuation. It does **not** prove either is right — both can be wrong in the same way.

---

## 12. Related Concepts

- [15 — Backtesting](15_Backtesting.md) — where HPL and RTPL are put to regulatory use
- [18 — FRTB Internal Models Approach](18_FRTB_Internal_Models_Approach.md) — the PLA test in full
- [27 — Controls and Governance](27_Controls_and_Governance.md) · [28 — Reporting and Dashboards](28_Reporting_and_Dashboards.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR32.22`–`MAR32.31` APL/HPL/RTPL definitions, exclusions, alignment |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR32 text |

*Accessed 25 August 2026.*
