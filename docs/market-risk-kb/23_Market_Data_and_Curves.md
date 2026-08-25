# 23 — Market Data, Curves and Surfaces

**Level:** 7 · **Prerequisites:** [03](03_Pricing_Fundamentals.md) · **Feeds:** [20](20_NMRF_and_Modellability.md), [24](24_Risk_Data_Model.md), [25](25_Risk_System_Architecture.md), [27](27_Controls_and_Governance.md)

> **Everything downstream inherits this document's failures.** A stale price at 06:00 becomes a wrong curve at 07:00, a wrong DV01 at 08:00, a wrong VaR at 17:00 and a wrong regulatory return at 18:00 — and at no point does anything look broken. Market data is the one layer where errors are silent by default.

---

## 1. The pipeline

```
   SOURCES                    exchanges · brokers · vendors · internal trades
      │
      ▼
   CAPTURE                    snapshot at a defined time, per market
      │
      ▼
   VALIDATION                 completeness · staleness · outliers · arbitrage
      │                       ├─► FAIL → escalate. NEVER silently substitute.
      ▼
   NORMALISATION              conventions · day counts · quoting bases · units
      │
      ▼
   CURVE / SURFACE BUILD      bootstrap · interpolate · calibrate
      │
      ▼
   RISK FACTORS               the modelled observables
      │
      ▼
   PRICING & RISK ENGINES     PV · sensitivities · scenarios · VaR · ES · capital
      │
      ▼
   STORAGE & LINEAGE          every number reproducible, with its inputs
```

---

## 2. The market data taxonomy

| Category | Examples | Typical source |
|---|---|---|
| **Prices** | Bond prices, equity prices, futures settlements | Exchanges, brokers, vendors |
| **Yields** | Government yields, corporate yields | Vendors, official sources |
| **Rates** | Deposit rates, RFR fixings, IBOR fixings | Benchmark administrators |
| **Swap rates** | Par swap rates by tenor and index | Brokers, vendors, platforms |
| **Basis spreads** | Tenor basis, cross-currency basis | Brokers |
| **Credit** | CDS spreads, bond spreads, index levels | Vendors, platforms |
| **FX** | Spot rates, forward points, NDF fixings | Platforms, vendors, central banks |
| **Volatility** | Vol surfaces and cubes; ATM, RR, BF for FX | Brokers, vendors |
| **Dividends** | Forecast dividends, dividend futures | Vendors, exchanges |
| **Repo / borrow** | GC and special repo rates, stock borrow | Internal, brokers |
| **Correlations** | Implied correlation, historical estimates | Derived, vendors |
| **Commodity** | Futures curves, location differentials, freight | Exchanges, price reporting agencies |
| **Reference data** | Ratings, sectors, ISINs, calendars, maturities | Vendors, agencies |

### 2.1 Reference data is market data

**Reference data errors are as damaging as price errors and far harder to detect.** A bond loaded with the wrong maturity prices plausibly and hedges wrongly. An issuer with the wrong sector lands in the wrong FRTB bucket at the wrong risk weight. A missing holiday shifts a cash flow by a day. **None of these produces an error message.**

---

## 3. Snapshot timing

### 3.1 The problem

A global bank's positions span markets that are never all open at once. "End of day" is not a single moment.

| Market | Typical close (local) |
|---|---|
| Tokyo | 15:00 JST |
| London | 16:30 GMT |
| New York | 16:00 EST |
| Sydney | 16:00 AEST |

### 3.2 The two approaches

| Approach | Method | Trade-off |
|---|---|---|
| **Single global snapshot** | One time (e.g. 16:00 NY), all markets | **Internally consistent**; some prices are hours stale |
| **Regional snapshots** | Each market at its own close | Each price is fresh; **cross-market relationships are inconsistent** |

> **Neither is right, and the choice matters more than it appears.** Under regional snapshots, an Asian equity marked at Tokyo close and its US-listed hedge marked at NY close will show P&L that is purely a timing artefact — a "loss" on a perfectly matched pair. Under a single global snapshot, Asian positions carry a stale mark that reverses the next morning.

**Whichever is chosen must be documented, applied consistently across pricing, P&L and risk, and — critically — used identically for APL, HPL and RTPL.** `MAR32.29` requires APL and HPL to use the same market data as the reported daily P&L; a timing mismatch between them shows up as PLA failure that is a systems artefact rather than a model deficiency ([15 §6.8](15_Backtesting.md)).

---

## 4. Validation

### 4.1 The checks

| Check | Test | Detects |
|---|---|---|
| **Completeness** | Every required point present | Feed failures, new instruments |
| **Staleness** | Value unchanged for *n* periods | Dead feeds, illiquid points |
| **Outlier / spike** | Move exceeds *k* × recent volatility | Fat-finger, bad ticks, decimal errors |
| **Cross-source** | Vendor A vs vendor B | Source-specific errors |
| **Bid-offer sanity** | Bid ≤ mid ≤ offer; spread within tolerance | Crossed or inverted quotes |
| **Arbitrage — rates** | Forwards implied by the curve are sane | Bad nodes, bad interpolation |
| **Arbitrage — vol** | Calendar and butterfly conditions | Surface inconsistency |
| **Triangular — FX** | `EUR/USD × USD/JPY ≈ EUR/JPY` | Inconsistent crosses |
| **Put-call parity** | `C − P = S·e^(−qτ) − K·e^(−rτ)` | Option data inconsistency |
| **Sign / bounds** | Volatility > 0; probability ∈ [0,1] | Data corruption |
| **Negative-value tolerance** | Rates and some commodity prices **may** be negative | Systems that reject valid negatives |

### 4.2 The rule that matters most

> **A failed validation must escalate. It must never silently substitute.**

The tempting fixes — carry yesterday forward, interpolate from neighbours, take the other vendor — all produce a number that looks fine and is not. Each is legitimate **only** as a documented, flagged, time-limited proxy, visible in the output.

| Response | Acceptable? |
|---|---|
| Escalate to a named owner | **Always** |
| Apply a documented, flagged proxy | Yes, with an audit record and an expiry |
| Silently carry forward yesterday's value | **No** — creates artificial zero volatility |
| Silently interpolate | **No** |
| Silently drop the position | **No** — removes both value and risk |
| Default a failed price to zero | **Never** |

**The carry-forward case deserves special emphasis.** A stale price produces a *zero* return for that day. Zero returns entering a VaR history **reduce measured volatility** — so a data failure makes the risk number look *better*. The failure mode is self-concealing and biased in the dangerous direction.

### 4.3 Four-eyes on overrides

Any manual override must carry: the value, the reason, the approver, a timestamp and an **expiry**. Overrides without expiry dates become permanent, and a permanent override is an undocumented model change.

---

## 5. Normalisation

Raw data arrives in the market's conventions, which differ. The classic traps:

| Trap | Example | Consequence if missed |
|---|---|---|
| **Quoting basis** | T-bills quoted on a **discount** basis; notes on a **coupon-equivalent** basis | Short end of the curve wrong |
| **Compounding** | Annual vs semiannual vs continuous | Basis-point-scale errors in DV01 |
| **Day count** | ACT/360 vs ACT/365 vs 30/360 | ~1.4% error on every accrual |
| **Vol convention** | **Normal (bp) vs lognormal (%)** | **Order-of-magnitude** errors |
| **Price vs yield** | Some feeds send one, some the other | Sign and scale errors |
| **Units** | bp vs %; barrels vs tonnes; per-share vs per-contract | Order-of-magnitude position errors |
| **Sign** | Payer/receiver, buy/sell protection | Hedge becomes a doubling |
| **Percent scale** | 4.5 vs 0.045 | 100× error |

> **The normal-versus-lognormal volatility trap is the single most expensive one on this list**, and it became common only after rates went negative and the rates options market moved predominantly to normal quoting. A 60bp normal volatility and a 60% lognormal volatility are both "60", and they are not remotely the same number.

---

## 6. Curve construction in depth

### 6.1 The multi-curve framework

Post-LIBOR, a single currency requires several curves:

| Curve | Built from | Used for |
|---|---|---|
| **RFR / OIS discount curve** | OIS swaps on the currency's risk-free rate | Discounting collateralised trades |
| **Projection curves** | Basis swaps vs the RFR, one per index and tenor | Forecasting floating coupons |
| **Cross-currency basis curves** | XCCY basis swaps | Discounting under a foreign-currency CSA |
| **Government curve** | Sovereign bonds | Benchmark; government-linked products |
| **Credit curves** | CDS, bond spreads | Credit-risky discounting |

**The CSA determines the discount curve**, which makes the cross-currency basis a risk factor on a book containing no FX product at all ([06 §5.4](06_FX_Risk.md)).

### 6.2 Instrument selection

| Segment | Instruments | Watch for |
|---|---|---|
| Overnight to 3M | O/N rate, deposits, RFR futures | Turn-of-year and quarter-end effects |
| 3M–2Y | Futures or FRAs, short swaps | **Convexity adjustment** on futures |
| 2Y–30Y+ | Par swaps | Liquidity thins at the long end |

**The futures convexity adjustment** is the classic subtlety: a futures contract is margined daily and a FRA is not, so the futures rate exceeds the forward rate by an amount that grows with maturity and volatility. Omitting it biases the 1–5 year segment of the curve.

### 6.3 The bootstrap

```
INPUT: sorted instruments, conventions, calendars, interpolation rule
DF[0] = 1.0
FOR each instrument i in increasing maturity:
    SOLVE  price_model(instrument_i, known_DFs, unknown_DF) = market_quote_i
    STORE  DF[maturity_i]
RETURN discount curve + interpolation rule
```

**A global (simultaneous) solve** is preferred where instruments overlap in maturity — a sequential bootstrap forces an arbitrary ordering when two instruments cover the same span.

### 6.4 Interpolation and its consequences

| Method | Interpolates | Character |
|---|---|---|
| Linear on zero rates | `z(t)` | Simple; **discontinuous forwards** |
| Linear on `log DF` | `ln DF(t)` | Piecewise-constant forwards; stable, common |
| Cubic spline on zeros | `z(t)` | Smooth zeros; **can oscillate in forwards** |
| Monotone convex | forwards | Designed to keep forwards positive and non-oscillating |

> **Always plot the implied forward curve when validating a build.** A curve can be visually smooth in zero-rate space and imply oscillating or negative forwards. Since forwards are what a floating leg actually projects, oscillating forwards produce oscillating key-rate sensitivities and unstable hedge ratios.

**Interpolation determines the key-rate ladder.** Two banks with identical positions and identical market data will report different KRD distributions if they interpolate differently, while agreeing on total DV01 ([04 §5.6](04_Interest_Rate_Risk.md)). Reconcile totals across institutions, never buckets.

### 6.5 The node-set alignment rule

**Keep the risk system's bump nodes aligned with the curve build's nodes.** Bumping a node the curve does not have forces an interpolation nobody specified, and the resulting sensitivity is an artefact of the interpolation rather than a property of the portfolio.

For regulatory purposes `MAR21.8` fixes the GIRR vertices at **0.25, 0.5, 1, 2, 3, 5, 10, 15, 20 and 30 years**, which removes the choice for capital but not for internal risk management.

---

## 7. Volatility surfaces

### 7.1 What must be modelled

`MAR33.12` is explicit for IMA banks: those with relatively large and/or complex options portfolios *"must have detailed specifications of the relevant volatilities"* and **must model the volatility surface across both strike price and vertex (ie tenor)**.

| Market | Dimensions | Quoting convention |
|---|---|---|
| Equity | Strike × expiry | Absolute or percentage strike |
| **FX** | **Delta** × expiry | **ATM, risk reversal, butterfly** ([06 §6.1](06_FX_Risk.md)) |
| Rates (swaptions) | Expiry × underlying tenor × strike — **a cube** | Normal (bp) or lognormal |
| Commodity | Strike × expiry, per contract month | Absolute strike |

### 7.2 Arbitrage constraints

| Constraint | Test | Violation implies |
|---|---|---|
| **Calendar spread** | Total variance `σ²τ` non-decreasing in τ at fixed moneyness | Arbitrage across expiries |
| **Butterfly** | Implied risk-neutral density non-negative | Arbitrage across strikes |
| **Monotonicity** | `∂C/∂K ≤ 0`; price increasing in σ | Basic no-arbitrage failure |
| **Put-call parity** | `C − P = S·e^(−qτ) − K·e^(−rτ)` | Inconsistent call/put surfaces |

**An arbitrageable surface produces negative probabilities and nonsensical Greeks**, and the failure typically appears far downstream as an unexplained P&L or a failed validation on a different system.

### 7.3 Interpolation and extrapolation

Interpolation in **total variance** space is generally preferred to interpolation in volatility, because it preserves the calendar-arbitrage condition naturally.

**Extrapolation beyond the quoted region is a modelling choice with capital consequences.** `MAR31.26(1)(b)` permits extrapolation for modellability purposes only **subject to supervisory approval**, **up to a reasonable distance** from the closest modellable risk factor, and it **must not rely solely on the closest factor** but on more than one. Where used, it **must be considered in the determination of RTPL**.

---

## 8. Market data and the RFET

Market data quality is not only an operational concern — **under FRTB it directly determines capital**.

| Requirement | Implication for the data function |
|---|---|
| **Real price observations** (`MAR31.12`) | The bank must **capture and retain evidence** of transactions and committed quotes |
| **Vendor evidence** | The vendor must agree to provide evidence **to supervisors on request** — a contractual requirement, negotiated before it is needed |
| **Collateral valuations excluded** | Margin-agreed values do not count, however numerous |
| **One observation per day** | Deduplication logic required |
| **Quarterly RFET, monthly monitoring** | An operational cadence, not an annual exercise |

> **Many RFET failures are record-keeping failures rather than genuine illiquidity.** A bank's own executed transactions are the easiest of the four real-price criteria to satisfy and among the most commonly unrecorded in a form that can be mapped to a risk factor. **The data architecture decision — capture trade prices tagged to risk factors from the outset — has direct capital consequences.** See [20](20_NMRF_and_Modellability.md).

---

## 9. Storage, versioning and lineage

### 9.1 Requirements

| Requirement | Why |
|---|---|
| **Immutable snapshots** | Yesterday's number must be reproducible exactly |
| **Bi-temporal storage** | Both *as-of* date and *knowledge* date, so a restatement is visible as a restatement |
| **Full lineage** | Every risk number traceable to its inputs |
| **Override audit** | Who, what, why, when, expiry |
| **Version pinning** | The curve build version used for a given date is recorded |

### 9.2 Why bi-temporal matters

A price is corrected three days after the fact. Two legitimate questions arise:

1. *What did we report on that day?* — needs the data **as it was known then**
2. *What was actually true on that day?* — needs the **corrected** data

**A single-temporal store can answer only one**, and the choice of which typically surfaces during a regulatory review of a backtesting exception. This is a design decision, not a nice-to-have — and BCBS 239's principles on accuracy, completeness and adaptability point directly at it.

---

## 10. Pseudocode

```
FUNCTION market_data_pipeline(business_date, config):
    raw = {}
    FOR source IN config.sources:
        raw[source] = capture(source, config.snapshot_time[source.region])

    # --- VALIDATE ---
    issues = []
    FOR point IN required_points(config):
        v = resolve(raw, point, config.source_priority)

        IF v IS MISSING:
            issues.append(("MISSING", point));  CONTINUE
        IF unchanged_for(point, v, config.staleness_periods):
            issues.append(("STALE", point))
        IF abs(move(point, v)) > config.k * recent_vol(point):
            issues.append(("OUTLIER", point, move(point, v)))
        IF NOT within_bounds(point, v):
            issues.append(("BOUNDS", point, v))

    blocking = [i for i in issues if is_blocking(i, config)]
    IF blocking:
        ESCALATE(blocking)
        HALT                       # do NOT proceed on substituted data
        # Any proxy applied later must be explicit, approved, flagged and dated.

    # --- NORMALISE ---
    norm = { p: normalise(v, config.conventions[p]) for p, v in resolved }

    # --- BUILD ---
    curves = {}
    FOR ccy IN config.currencies:
        curves[ccy, "DISCOUNT"] = bootstrap_ois(norm, ccy)
        FOR index IN config.indices[ccy]:
            curves[ccy, index] = bootstrap_projection(norm, ccy, index,
                                                      curves[ccy, "DISCOUNT"])

    surfaces = { u: calibrate_surface(norm, u) for u in config.underlyings }

    # --- POST-BUILD VALIDATION: the build must reprice its own inputs ---
    FOR c IN curves.values():
        ASSERT max_abs_repricing_error(c) < config.tolerance
        ASSERT forwards_are_sane(c)                 # positivity, no oscillation
    FOR s IN surfaces.values():
        ASSERT no_calendar_arbitrage(s)
        ASSERT no_butterfly_arbitrage(s)

    persist_immutable(business_date, raw, norm, curves, surfaces,
                      overrides, config.version)
    RETURN curves, surfaces, issues
```

---

## 11. Data contract

```
market_data_point:
    point_id              string          # e.g. "USD.SOFR.OIS.10Y"
    business_date         date
    knowledge_date        date            # bi-temporal
    value                 decimal
    unit                  enum {PERCENT, BP, PRICE, RATIO, ABSOLUTE}
    quote_basis           enum {DISCOUNT, COUPON_EQUIVALENT, PAR, ZERO, SPREAD}
    compounding           enum {SIMPLE, ANNUAL, SEMIANNUAL, CONTINUOUS}
    day_count             enum
    vol_convention        enum {NORMAL, LOGNORMAL} | null
    source                string
    source_priority       int
    capture_timestamp     timestamp
    snapshot_region       string
    validation_status     enum {PASS, WARN, PROXY, OVERRIDE, FAIL}
    proxy_reason          text | null
    override_approver     string | null
    override_expiry       date | null
    is_real_price         boolean         # MAR31.12 — for RFET
    real_price_criterion  enum {OWN_TRANSACTION, THIRD_PARTY_TRANSACTION,
                                COMMITTED_QUOTE, QUALIFYING_VENDOR} | null

curve:
    curve_id, currency, curve_type {DISCOUNT, PROJECTION, XCCY_BASIS,
                                    GOVERNMENT, CREDIT}
    business_date, knowledge_date
    index                 string | null
    csa_currency          string | null   # determines the discount basis
    node_tenors           list<decimal>
    node_values           list<decimal>
    interpolation         enum
    compounding           enum
    build_version         string          # pinned, for reproducibility
    input_point_ids       list<string>    # full lineage
    max_repricing_error   decimal
```

> `quote_basis`, `compounding` and `vol_convention` are **mandatory**, not optional metadata. A number without them is not interpretable, and the majority of cross-system reconciliation breaks resolve to one of these three fields.

---

## 12. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | **Completeness** | Every required point present or explicitly flagged |
| 2 | **Staleness** | Unchanged values detected and reported |
| 3 | **Outliers** | Spikes flagged against recent volatility |
| 4 | **Cross-source** | Material vendor disagreements investigated |
| 5 | **Negatives supported** | Rates and commodity prices accepted below zero |
| 6 | **Conventions carried** | Quote basis, compounding, day count, vol convention on every point |
| 7 | **Snapshot policy** | Documented; identical for pricing, P&L and risk |
| 8 | **APL/HPL/RTPL alignment** | Same market data, per `MAR32.29` |
| 9 | **No silent substitution** | Every proxy flagged, approved and dated |
| 10 | **Override expiry** | Every override has one, and it is enforced |
| 11 | **Curve reprices inputs** | Bootstrapping instruments reprice within tolerance |
| 12 | **Forwards sane** | Plotted; positive; non-oscillating |
| 13 | **Futures convexity** | Adjustment applied where futures are used |
| 14 | **Node alignment** | Risk bump nodes match curve build nodes |
| 15 | **Regulatory vertices** | GIRR sensitivities at the `MAR21.8` ten tenors |
| 16 | **Surface arbitrage** | Calendar and butterfly tests pass |
| 17 | **Put-call parity** | Holds within bid-offer |
| 18 | **Triangular FX** | Crosses consistent |
| 19 | **Real price tagging** | Observations tagged to risk factors for the RFET |
| 20 | **Bi-temporal storage** | As-of and knowledge dates both retained |
| 21 | **Lineage** | Every curve traceable to its input points |
| 22 | **Build version pinned** | Recorded per business date |

---

## 13. Common implementation errors

| Error | Consequence |
|---|---|
| **Silently carrying forward a stale price** | Zero return enters the VaR history and **reduces** measured risk |
| Defaulting a failed price to zero | Value and risk both silently removed |
| Mixing discount-basis bills with coupon-equivalent notes | Short end of the curve wrong |
| Normal vs lognormal vol confused | Order-of-magnitude pricing errors |
| Omitting the futures convexity adjustment | 1–5 year curve segment biased |
| Single-curve pricing post-LIBOR | Systematic mispricing; basis risk invisible |
| Ignoring the CSA currency | Cross-currency basis exposure unreported |
| Cubic spline without checking forwards | Oscillating forwards, unstable hedge ratios |
| Bumping nodes the curve does not have | Sensitivities that are interpolation artefacts |
| Different snapshot times for P&L and risk | PLA failures that are systems artefacts |
| Overrides with no expiry | Undocumented permanent model changes |
| Single-temporal storage | Cannot reconstruct what was known on the day |
| Not tagging real price observations | Avoidable RFET failures, and avoidable NMRF capital |
| Reference data treated as static | Wrong FRTB buckets, wrong maturities, wrong calendars |

---

## 14. Limitations

- **Illiquid points have no good price**, only a range of defensible marks. Validation can detect implausibility; it cannot manufacture a market.
- **Vendor data is a model output for much of the curve**, not an observation — a distinction that matters enormously for the RFET.
- **Arbitrage tests detect inconsistency, not error.** A perfectly arbitrage-free surface can be uniformly wrong.
- **Snapshot timing is an unavoidable compromise** for any bank operating across time zones.
- **Reference data quality depends on external providers** and on corporate-action processing that sits outside the market risk function's control.

---

## 15. Related Concepts

- [03 — Pricing Fundamentals](03_Pricing_Fundamentals.md) · [04 — Interest Rate Risk](04_Interest_Rate_Risk.md)
- [09 — Options and Greeks](09_Options_and_Greeks.md) · [20 — NMRF and Modellability](20_NMRF_and_Modellability.md)
- [24 — Risk Data Model](24_Risk_Data_Model.md) · [27 — Controls and Governance](27_Controls_and_Governance.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.8` vertices; `MAR31.12`–`MAR31.26` RFET and data principles; `MAR32.29`; `MAR33.12` |
| BCBS | *Principles for effective risk data aggregation and risk reporting* (BCBS 239) | Jan 2013 | https://www.bis.org/publ/bcbs239.pdf | Accuracy, completeness, timeliness, adaptability principles |
| ARRC | SOFR conventions and transition materials | ongoing | https://www.newyorkfed.org/arrc | RFR conventions and multi-curve construction |
| ISDA | 2021 ISDA Interest Rate Derivatives Definitions | 2021 | https://www.isda.org/ | Day counts, business day conventions, fixing conventions |

*Accessed 25 August 2026.*
