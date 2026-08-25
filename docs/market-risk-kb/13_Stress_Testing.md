# 13 — Stress Testing

**Level:** 8 · **Prerequisites:** [11](11_VaR.md), [12](12_Expected_Shortfall.md) · **Feeds:** [20](20_NMRF_and_Modellability.md), [21](21_Market_Risk_Limits.md), [29](29_Regulatory_Framework.md)

---

## 1. Plain English

**Stress testing asks: what happens to us if something specific and terrible occurs?**

It is the deliberate opposite of VaR and ES. Those measures ask *what does the distribution say?* Stress testing asks *what if the distribution is wrong?*

| | VaR / ES | Stress testing |
|---|---|---|
| Basis | Statistical distribution | A **named scenario** |
| Question | What is the loss at probability *p*? | What is the loss **if this happens**? |
| Probability attached | Yes — that is the definition | **Usually none, deliberately** |
| Source of severity | The data window | History, judgement, or reverse-engineering |
| Handles the unprecedented | **No** | **Yes** — that is the point |
| Can be gamed by pushing loss past a threshold | Yes (VaR) | No |

> **Stress testing exists because every statistical risk measure is conditional on a model, and models are calibrated on the past. The events that destroy banks are, with some regularity, the ones that were not in the sample.**

---

## 2. Banking example

A desk holds a $500m portfolio of investment-grade corporate bonds.

- **99% 1-day VaR:** $4.2m
- **97.5% 1-day ES:** $4.3m
- **Stress test — "2008 credit crisis" scenario:** IG spreads widen 350bp, Treasury yields fall 150bp (flight to quality).

```
   Spread loss  =  500,000,000 × 4.5 (spread duration) × 350bp   =  −$78,750,000
   Rate gain    =  500,000,000 × 4.6 (rate duration)   × 150bp   =  +$34,500,000
   Net stressed loss                                              =  −$44,250,000
```

**$44m under stress against a $4.2m VaR — a factor of ten.** Neither is wrong. VaR describes a normal bad day; the stress test describes a specific catastrophe. A risk framework that reports only the first is telling management the truth about ordinary conditions and nothing about the conditions that matter.

Note also the **hedge that isn't**: the rate rally offsets 44% of the spread loss in *this* scenario. In a 2022-style scenario — spreads widen *and* rates rise — there is no offset at all and the loss is larger. **This is precisely why multi-factor scenarios must specify every factor jointly, and why single-factor sensitivities cannot be added into a scenario.**

---

## 3. The taxonomy of stress tests

| Type | Construction | Answers |
|---|---|---|
| **Historical** | Replay an actual observed episode | "What if 2008 happened again?" |
| **Hypothetical** | Expert-designed plausible scenario | "What if a major sovereign defaulted?" |
| **Sensitivity / single-factor** | Move one factor by a set amount | "What if rates +200bp?" |
| **Multi-factor** | Move many factors coherently | "What if there is a risk-off shock?" |
| **Reverse** | Start from an outcome, find the cause | "What would it take to lose $500m?" |
| **Supervisory** | Prescribed by a regulator | "What does the Fed's severely adverse scenario cost us?" |

---

## 4. Historical scenarios

### 4.1 The method

```
1. Choose an episode and a precise date range.
2. Extract the ACTUAL observed changes in every risk factor over that range,
   from the institution's own market data history.
3. Apply that shock vector to TODAY's portfolio.
4. Revalue in full.
5. Report the P&L, decomposed by risk factor and desk.
```

> **Step 2 is not negotiable, and it is where the discipline of this document lives.** The shock vector must be *extracted from data*, not copied from a summary document (including this one). A scenario is a vector of hundreds or thousands of factor moves specific to the institution's own factor set, curve construction and bucketing. Two banks running "2008" will and should have different vectors. **Any shock magnitude that cannot be traced to an observation is a fabricated number and must not be used.**

### 4.2 The canonical episodes

The headline facts below are well-documented and serve to *identify* each episode. They are **not** the shock vector — see §4.1.

| Episode | Period | Defining characteristic | Primary risk classes hit |
|---|---|---|---|
| **Black Monday** | 19 Oct 1987 | Single-day equity crash; the origin of the modern equity volatility skew | Equity, equity vol |
| **Bond massacre** | 1994 | Rapid Fed tightening; large global bond sell-off; MBS convexity feedback | Rates, MBS |
| **LTCM / Russia** | Aug–Sep 1998 | Correlations converged; relative-value spreads blew out; liquidity vanished | Rates, credit, basis |
| **Dot-com unwind** | 2000–02 | Slow, sector-concentrated equity decline | Equity |
| **Global Financial Crisis** | 2007–09 | Broad, correlated; credit spreads to record wides; funding markets froze; CDS-bond basis to extreme negatives | **All**, especially credit and basis |
| **Euro sovereign crisis** | 2010–12 | Sovereign spread dispersion; redenomination risk priced | Credit, rates, FX |
| **Taper tantrum** | May–Sep 2013 | Sharp global rate rise on a communication shock | Rates, EM FX |
| **CHF de-peg** | 15 Jan 2015 | A managed currency stopped being managed, without warning | FX, FX vol |
| **Brexit referendum** | 24 Jun 2016 | Overnight FX and rate gap on a binary political outcome | FX, rates, equity |
| **Volmageddon** | 5 Feb 2018 | VIX complex dislocation; short-volatility products destroyed | Equity vol |
| **COVID crash** | Feb–Mar 2020 | Fastest major drawdown on record, then unprecedented policy reversal | **All** |
| **Negative WTI** | 20 Apr 2020 | Front-month crude settled **below zero**; storage capacity bound | Commodity |
| **UK gilt / LDI** | Sep–Oct 2022 | Collateral-call feedback loop in liability-driven investment; central bank intervened | Rates, rate vol |
| **Rate normalisation** | 2022–23 | Largest sustained rate rise in decades; **rates and credit widened together** | Rates, credit |
| **Regional bank stress** | Mar 2023 | Duration losses on HTM portfolios met deposit flight | Rates, credit, equity |

### 4.3 What the model-breaking episodes teach

Three of these are qualitatively different from the rest, because they invalidated a *modelling assumption* rather than merely producing a large draw:

| Episode | Assumption destroyed |
|---|---|
| **CHF de-peg** | That a stable historical series implies a stable process. The peg's near-zero volatility *was* the risk. |
| **Negative WTI** | That prices are lognormal and bounded below by zero. A physical constraint (storage) bound and the process changed character. |
| **LME nickel, Mar 2022** | That executed trades are final. The exchange **cancelled trades** — a risk with no representation in any price series. |

> **A statistical model cannot be repaired to cover these.** Widening the distribution does not help when the failure is structural. They can only be addressed by scenario design and by governance — which is the strongest single argument for stress testing as an independent discipline rather than a supplement to VaR.

---

## 5. Hypothetical scenarios

### 5.1 Design principles

| Principle | Meaning |
|---|---|
| **Severe but plausible** | Extreme enough to matter; defensible enough to act on |
| **Internally coherent** | Factor moves must be economically consistent with one another |
| **Portfolio-relevant** | It must hit *this* book's actual exposures |
| **Fully specified** | Every material factor gets a move, including the ones that don't move |
| **Documented and owned** | Rationale, approval, and a named owner |

### 5.2 Coherence — the hardest part

A scenario is not a list of independent shocks. If equities fall 30%, then:

- Credit spreads must widen (equity and credit are both claims on the same firms)
- Government yields probably fall (flight to quality) — **but not necessarily**, as 2022 showed
- Volatility must rise across asset classes
- The dollar probably strengthens (funding demand)
- Correlations rise toward 1
- Bid-offer widens; liquidity horizons extend

> **An incoherent scenario produces a loss number nobody believes and nobody acts on.** The most common incoherence in practice is shocking each asset class to its own historical worst simultaneously — which produces a scenario that has never occurred and could not occur, because those worsts happened in different regimes for different reasons.

### 5.3 Standard hypothetical families

| Family | Shape |
|---|---|
| **Risk-off / flight to quality** | Equity ↓, credit ↑, govt yields ↓, vol ↑, USD ↑, correlations → 1 |
| **Inflation shock / stagflation** | Rates ↑, credit ↑, equity ↓, commodities ↑ — **no flight-to-quality offset** |
| **Policy shock** | Sharp parallel or curve move on a central bank surprise |
| **Sovereign event** | One sovereign's curve dislocates; contagion to banks and its currency |
| **Liquidity freeze** | Bid-offer widens by multiples; basis relationships break; horizons extend |
| **Correlation breakdown** | Historical relationships fail; every hedge underperforms simultaneously |

**The inflation-shock family deserves particular attention** because it removes the rate/credit offset that flatters most risk-off scenarios — as §2 demonstrated numerically. A book that looks well-hedged under "2008" can be badly exposed under "2022."

---

## 6. Sensitivity (single-factor) stress tests

The simplest form: move one factor, hold everything else, revalue.

### 6.1 Standard grids

| Risk class | Typical shock grid |
|---|---|
| Interest rates | ±25, ±50, ±100, ±200, ±300bp parallel; plus steepener/flattener/butterfly |
| Credit spreads | ±25, ±50, ±100, ±200, ±400bp by rating band |
| Equity | ±5%, ±10%, ±20%, ±30% |
| FX | ±5%, ±10%, ±20% per pair |
| Commodity | ±10%, ±25%, ±50% |
| Volatility | ±10%, ±25%, ±50% relative, or absolute vol-point moves |

### 6.2 The two-dimensional grid — indispensable for options

For any book with optionality, a one-dimensional grid is inadequate. The standard tool is a **spot × volatility matrix**:

P&L ($m) for an options book:

| | **Vol −25%** | **Vol −10%** | **Vol flat** | **Vol +10%** | **Vol +25%** |
|---|---|---|---|---|---|
| **Spot −20%** | −18.2 | −22.4 | −26.1 | −29.8 | −35.3 |
| **Spot −10%** | −4.1 | −6.8 | −9.2 | −11.6 | −15.2 |
| **Spot flat** | +6.3 | +2.7 | **0.0** | −2.7 | −6.8 |
| **Spot +10%** | +3.8 | +0.9 | −1.7 | −4.3 | −8.2 |
| **Spot +20%** | −5.6 | −9.1 | −12.2 | −15.4 | −20.1 |

**Read the corners, not the centre.** This book is short gamma (losses on large moves in *both* directions) and short vega (losses as vol rises). Its worst corner is −$35.3m. Its VaR, computed from delta and a normal distribution, would show almost none of this — the position is nearly delta-flat, which is exactly why the one-dimensional view is dangerous. See [09 §10.2](09_Options_and_Greeks.md).

---

## 7. Reverse stress testing

### 7.1 The inversion

Ordinary stress testing: **scenario → loss.**
Reverse stress testing: **loss → scenario.**

> **Question: "What set of market moves would cause us to lose $500m — or to breach our capital requirement — and how plausible is it?"**

### 7.2 Why it is uniquely valuable

Forward stress tests are limited by the imagination of the person designing them. **Reverse stress tests are limited only by the portfolio's own vulnerabilities**, which is a much better constraint. They routinely surface exposures nobody had thought to test, precisely because the search is driven by the position rather than by a narrative.

### 7.3 Method

```
INPUT: portfolio P, target loss L*, factor covariance Σ (for plausibility metric)

FORMULATION:
   find shock vector  x
   minimising         xᵀ Σ⁻¹ x        (Mahalanobis distance — "least unlikely")
   subject to         PnL(P, x)  =  −L*

INTERPRETATION:
   The Mahalanobis distance of the solution is the scenario's implausibility
   in standard-deviation units. A solution at distance 2.5 is a routine market
   event. A solution at distance 12 requires a genuinely extraordinary market.
```

**For a linear portfolio there is a closed form.** The least-unlikely shock achieving loss `L*` given sensitivity vector `δ` is:

```
              L*  ·  Σ δ
   x*  =  ─────────────────
              δᵀ Σ δ
```

This is worth internalising: **the least-unlikely path to any given loss is proportional to `Σδ`** — the covariance matrix applied to the sensitivity vector. The scenario that hurts most efficiently is the one aligned with the portfolio's own dominant risk direction.

### 7.4 Regulatory status

Reverse stress testing is an established supervisory expectation in several jurisdictions — notably the **UK PRA**, where it is a long-standing requirement for firms to identify scenarios that would render their business model unviable. It is a **risk-management** requirement rather than a capital calculation: it produces understanding and action, not a number that is added to capital.

---

## 8. Supervisory stress testing

Supervisory stress tests are prescribed, mandatory and consequential — the results can constrain a bank's capital distributions.

### 8.1 The U.S. framework — the Global Market Shock

For U.S. banks with significant trading activity, the market-risk element of the Federal Reserve's supervisory stress test is the **Global Market Shock (GMS)**: a set of hypothetical shocks to a large set of risk factors reflecting general market distress and heightened uncertainty.

**Structural features of the GMS, from the Federal Reserve's own documentation:**

| Feature | Specification |
|---|---|
| Applies to | Banks **with significant trading activity** |
| Applied to | Positions held on a specified **as-of date** |
| Timing of loss recognition | Recognised in the **first quarter** of the scenario and **carried through all subsequent quarters** |
| Relationship to the macro scenario | A component of the supervisory **severely adverse** scenario in the company-run test |

**For the 2026 cycle specifically:**

| Item | Value |
|---|---|
| Scenarios finalised | **4 February 2026** |
| Scenario horizon | **Q1 2026 through Q1 2029** |
| GMS **as-of date** | **17 October 2025** |
| Notable calibration changes vs 2025 | Reduced shock magnitudes for **agency pass-through securities** and for **certain commodities** |
| Direction changes vs 2025 | The dollar **appreciates** against the yen (it depreciated in 2025); **gold, oil and natural gas prices increase** on inflationary pressure (commodity prices fell in 2025) |
| Consistent across both cycles | **Credit spreads widen and equity prices fall** |

> **The as-of date matters more than practitioners expect.** The GMS is applied to the positions held on one specific historical date, not to today's book. A desk that materially changed its risk profile after 17 October 2025 will nonetheless be assessed on what it held then. Managing to the as-of date is a recognised — and supervisorily scrutinised — behaviour.

### 8.2 The 2026 direction reversal is instructive

Between the 2025 and 2026 cycles, the *sign* of the FX and commodity shocks flipped. This is a deliberate feature of scenario design: **a supervisory scenario that repeats itself becomes a hedging target rather than a test.** Varying the shape year to year is how the exercise stays informative about resilience rather than about scenario-specific positioning.

### 8.3 Other jurisdictions

| Jurisdiction | Exercise | Character |
|---|---|---|
| **EU** | EBA EU-wide stress test | Biennial; constrained bottom-up; market risk component applied to trading book |
| **UK** | Bank of England stress testing | Concurrent scenario-based exercise for major UK banks |
| **Global** | Basel Pillar 2 stress testing expectations | Bank's own programme, supervisory review |

Precise scope, frequency and calibration change between cycles in every jurisdiction. **Always confirm the current cycle's published scenario documentation** — see [29](29_Regulatory_Framework.md).

---

## 9. Stress testing inside FRTB

Stress testing is not only a management tool under FRTB; it is embedded in the capital calculation itself.

| Mechanism | Where | What it does |
|---|---|---|
| **Stressed calibration of ES** | `MAR33.5` | The ES measure must replicate an outcome generated *if the relevant risk factors were experiencing a period of stress* — a joint assessment capturing stressed correlations |
| **Reduced-set 75% test** | `MAR33.5(2)(b)` | The reduced risk-factor set used for stress calibration must explain ≥75% of the full ES model's variation, over the preceding 12-week period |
| **NMRF stress scenario capital (SES)** | `MAR31`/`MAR33` | Non-modellable factors are capitalised by a **stress scenario** calibrated to a 97.5% confidence threshold over a period of stress, with a liquidity horizon of at least **20 days** |
| **IMA stress testing programme** | `MAR30` | A qualitative requirement on banks using internal models |
| **Three correlation scenarios** | `MAR21.6` | The SBM's built-in stress on the correlation assumption itself |

> **`MAR21.6` is worth recognising as a stress test in disguise.** It requires the entire SBM aggregation to be run three times — medium, high (ρ × 1.25, capped at 100%) and low (`max(2ρ−1, 0.75ρ)`) correlations — with capital set to the worst. That is a correlation-breakdown stress test hard-wired into the standardised approach.

---

## 10. Sensitivity-based versus full revaluation

| | Sensitivity-based | Full revaluation |
|---|---|---|
| Method | `ΔV ≈ Σ sᵢ · Δxᵢ` (+ second order) | Reprice every position under the shocked market |
| Cost | Trivial | High |
| Accuracy for small shocks | Good | Exact |
| **Accuracy for stress shocks** | **Poor** | Exact |
| Optionality | Misrepresented | Correct |
| Barriers, digitals, path-dependence | **Fails** | Correct |

> **Stress shocks are, by definition, large. Full revaluation is therefore the default for stress testing, and the sensitivity shortcut requires explicit justification** — typically only for a demonstrably linear book, or for an intraday indicative run that is later confirmed.

---

## 11. Pseudocode

```
FUNCTION historical_stress(portfolio, market_today, history, start_date, end_date):
    m_start = history.snapshot(start_date)
    m_end   = history.snapshot(end_date)

    shock = {}
    FOR each factor f IN portfolio.risk_factors:
        IF NOT history.has(f, start_date) OR NOT history.has(f, end_date):
            # Never silently zero a missing factor: that removes real risk.
            RECORD_PROXY_OR_ESCALATE(f)
            CONTINUE
        IF f.type IN {RATE, SPREAD}:
            shock[f] = m_end[f] - m_start[f]                 # absolute
        ELSE:
            shock[f] = m_end[f] / m_start[f] - 1             # relative

    stressed = apply_shock(market_today, shock)
    v0 = value(portfolio, market_today)
    v1 = value(portfolio, stressed)                          # FULL revaluation

    RETURN {
        "pnl":            v1 - v0,
        "by_desk":        decompose(portfolio, shock, by="desk"),
        "by_risk_class":  decompose(portfolio, shock, by="risk_class"),
        "top_10_drivers": largest_contributors(portfolio, shock, n=10),
        "unmapped_factors": proxied_or_missing_factors     # ALWAYS reported
    }


FUNCTION reverse_stress(portfolio, target_loss, cov):
    delta = sensitivity_vector(portfolio)
    # least-unlikely shock achieving the target loss, linear approximation
    x_star = (target_loss * (cov @ delta)) / (delta.T @ cov @ delta)

    # refine against full revaluation, since the linear solution is only a seed
    x_star = newton_refine(lambda x: pnl_full_reval(portfolio, x) + target_loss,
                           seed = x_star)

    mahalanobis = sqrt(x_star.T @ inverse(cov) @ x_star)
    RETURN {
        "shock_vector":   x_star,
        "implausibility": mahalanobis,          # in standard deviations
        "narrative":      interpret(x_star)     # human-readable scenario
    }


FUNCTION spot_vol_grid(portfolio, spot_shocks, vol_shocks):
    grid = {}
    v0 = value(portfolio, market_today)
    FOR s IN spot_shocks:
        FOR v IN vol_shocks:
            m = apply_shock(market_today, {"spot": s, "vol": v})
            grid[s, v] = value(portfolio, m) - v0
    RETURN grid
```

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Shocks traceable to data** | Every historical shock reproducible from the market-data archive |
| 2 | **Full revaluation** | Used for all optioned and path-dependent positions |
| 3 | **Coherence** | Factor moves economically consistent; reviewed by a named owner |
| 4 | **Completeness** | Every material factor shocked; unmapped factors **reported, never zeroed** |
| 5 | **Decomposition** | Loss attributable to desk, risk class and top individual drivers |
| 6 | **Stress ≥ VaR** | A severe scenario producing less loss than VaR indicates an error |
| 7 | **Two-dimensional grids** | Run for every book with material optionality |
| 8 | **Reverse stress** | Run at least annually; results acted upon, not merely filed |
| 9 | **Scenario library governance** | Owner, rationale, approval date and review date for each scenario |
| 10 | **Supervisory reconciliation** | Internal severely-adverse results reconcile to the supervisory submission |
| 11 | **As-of date discipline** | Supervisory GMS applied to the correct as-of positions |
| 12 | **Liquidity assumptions** | Bid-offer widening and horizon extension included where material |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| Fabricating shock magnitudes | Numbers with no evidential basis; indefensible to a supervisor |
| Sensitivity-based P&L for large shocks | Loss materially misstated (see [09 §10.2](09_Options_and_Greeks.md)) |
| Zeroing unmapped factors | Real exposure silently removed from the result |
| Combining each asset class's worst historical move | A scenario that has never occurred and could not |
| Omitting the rate/credit joint case | Books look hedged under 2008 and are exposed under 2022 |
| One-dimensional grids on options books | Short-gamma and short-vega corners invisible |
| Attaching a probability to a hypothetical scenario | Misrepresents a judgemental construct as statistical |
| Never refreshing the scenario library | Tests the last crisis, not the next one |
| Managing to the supervisory as-of date | Passes the test without reducing the risk |
| Treating reverse stress results as a filing exercise | Forfeits the main benefit of the technique |

---

## 14. Limitations

1. **Scenarios have no probability.** A stress loss of $500m is not comparable to a VaR of $10m without a judgement about likelihood — and that judgement is not supplied by the exercise.
2. **Forward stress testing is bounded by imagination.** This is the specific gap reverse stress testing exists to close.
3. **Historical replay assumes today's portfolio would behave as the old market implies** — but market structure changes. Instruments that were liquid in 2008 may not exist; instruments that dominate today did not exist then.
4. **Second-round effects are usually omitted.** Forced deleveraging, margin spirals, counterparty failure and the bank's own market impact are hard to model and were central to 1998, 2008 and the 2022 LDI episode.
5. **Structural risks have no price series at all** — trade cancellation, capital controls, market closure. Governance, not modelling, is the only response.

---

## 15. Related Concepts

- [11 — VaR](11_VaR.md) · [12 — Expected Shortfall](12_Expected_Shortfall.md)
- [20 — NMRF and Modellability](20_NMRF_and_Modellability.md) · [21 — Market Risk Limits](21_Market_Risk_Limits.md)
- [29 — Regulatory Framework](29_Regulatory_Framework.md) · [30 — Worked Examples](30_Worked_Examples.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| Federal Reserve | *2026 Stress Test Scenarios* | 4 Feb 2026 | https://www.federalreserve.gov/publications/2026-stress-test-scenarios.htm | 2026 scenario horizon, GMS as-of date, calibration changes |
| Federal Reserve | *Supervisory Stress Test Documentation: Final 2026 Global Market Shock Component* | 2026 | https://www.federalreserve.gov/supervisionreg/files/2026-final-gms-model.pdf | GMS construction and scope |
| Federal Reserve | Board finalizes hypothetical scenarios for its annual stress test | 4 Feb 2026 | https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260204a.htm | Finalisation date |
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.6`, `MAR30`, `MAR31`, `MAR33.5` stress requirements |
| CME Group | WTI crude oil April 2020 settlement | 2020 | https://www.cmegroup.com/ | Negative price event |
| LME | Nickel market events, March 2022 | 2022 | https://www.lme.com/ | Trade cancellation event |
| SNB | Discontinuation of the minimum exchange rate | 15 Jan 2015 | https://www.snb.ch/ | CHF de-peg event |

*Accessed 25 August 2026.*
