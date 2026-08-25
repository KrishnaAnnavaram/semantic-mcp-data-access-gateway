# 40 — Implementation Pseudocode and Data Contracts

**Level:** Implementation reference · **Prerequisites:** [24](24_Risk_Data_Model.md), [31](31_Master_Calculation_Catalog.md), [32](32_Master_Formula_Handbook.md)

> **Consolidated reference.** Each algorithm below also appears in the document where its theory is established; this document collects them so an implementer can work from one place. The **invariants** — the `ASSERT` lines — are not optional: each corresponds to a defect that has occurred in production somewhere.

---

## 1. The universal invariants

Six rules that apply to every algorithm in this document.

```
   1.  A failed computation returns FAILED, never zero.
   2.  Absence is never silently equivalent to zero.
   3.  Every sensitivity carries method, bump size and sign convention.
   4.  Every risk measure carries confidence, horizon and quantile convention.
   5.  Every derived number carries the identifiers of its inputs.
   6.  Every regulatory parameter carries its paragraph citation.
```

---

## 2. Pricing and curves

### 2.1 Bootstrap

```
FUNCTION bootstrap(instruments, conventions, interpolation):
    curve = { 0.0: 1.0 }                       # DF(0) = 1
    FOR inst IN sort_by_maturity(instruments):
        unknown = DF at inst.maturity
        SOLVE price_model(inst, curve, unknown) == inst.market_quote
        curve[inst.maturity] = unknown

    # MANDATORY post-build gates
    FOR inst IN instruments:
        ASSERT abs(price_model(inst, curve) - inst.market_quote) < tolerance
    ASSERT forwards_positive_and_non_oscillating(curve, interpolation)

    RETURN Curve(nodes=curve, interpolation=interpolation,
                 build_version=VERSION, input_ids=[i.id for i in instruments])
```

> **Where instruments overlap in maturity, prefer a global simultaneous solve.** A sequential bootstrap forces an arbitrary ordering.

### 2.2 Valuation, with the failure path

```
FUNCTION value(position, curves, surfaces, valuation_date):
    TRY:
        model  = model_for(position.product_type)
        curve  = select_discount_curve(position.csa_id, curves)   # CSA-AWARE
        proj   = select_projection_curves(position, curves)
        pv     = model.price(position, curve, proj, surfaces, valuation_date)
        RETURN Valuation(pv=pv, status="SUCCESS",
                         model_version=model.version,
                         curve_ids=[curve.id] + [p.id for p in proj])
    CATCH error:
        # NEVER return 0. A failed valuation is UNKNOWN.
        ESCALATE(position, error)
        RETURN Valuation(pv=NULL, status="FAILED", failure_reason=str(error))
```

---

## 3. Sensitivities

### 3.1 DV01

```
FUNCTION dv01(position, curve, bump_bp = 1.0, method = "BUMP_CENTRAL"):
    IF method == "BUMP_CENTRAL":
        up   = value(position, shift_parallel(curve, +bump_bp))
        down = value(position, shift_parallel(curve, -bump_bp))
        v = (down.pv - up.pv) / (2 * bump_bp)
    ELIF method == "ANALYTIC":
        v = modified_duration(position, curve) * value(position, curve).pv * 1e-4

    RETURN Sensitivity(value=v, measure="DV01",
                       unit="CCY_PER_BP", currency=position.currency,
                       computation_method=method, bump_size_bp=bump_bp,
                       sign_convention="LOSS_ON_RISE")   # positive = long duration
```

### 3.2 Key-rate DV01, with the completeness gate

```
FUNCTION key_rate_dv01(position, curve, key_tenors, bump_bp = 1.0):
    ladder = {}
    FOR k IN key_tenors:
        up   = value(position, apply_tent(curve, k, key_tenors, +bump_bp))
        down = value(position, apply_tent(curve, k, key_tenors, -bump_bp))
        ladder[k] = (down.pv - up.pv) / (2 * bump_bp)

    # MANDATORY: the tents must sum to a parallel shift
    ASSERT abs(sum(ladder.values()) - dv01(position, curve).value) < tolerance
    RETURN ladder


FUNCTION apply_tent(curve, tenor, key_tenors, bump_bp):
    i  = key_tenors.index(tenor)
    lo = key_tenors[i-1] if i > 0 else NULL
    hi = key_tenors[i+1] if i < len(key_tenors)-1 else NULL
    out = []
    FOR (t, r) IN curve.nodes:
        IF   lo IS NULL AND t <= tenor:  w = 1.0        # FLAT below the first
        ELIF hi IS NULL AND t >= tenor:  w = 1.0        # FLAT above the last
        ELIF t == tenor:                 w = 1.0
        ELIF lo IS NOT NULL AND lo <= t < tenor:  w = (t - lo) / (tenor - lo)
        ELIF hi IS NOT NULL AND tenor < t <= hi:  w = (hi - t) / (hi - tenor)
        ELSE:                            w = 0.0
        out.append((t, r + w * bump_bp / 10000.0))
    RETURN Curve(out, curve.interpolation)
```

> **The flat outer tents are what make the completeness identity hold.** Without them, cash flows shorter than the first key rate and longer than the last are covered by no tent, and the ladder silently under-sums ([30 §3](30_Worked_Examples.md)).

### 3.3 CS01 — separate from DV01

```
FUNCTION cs01(position, rf_curve, spread_curve, bump_bp = 1.0):
    up   = value(position, rf_curve, shift(spread_curve, +bump_bp))
    down = value(position, rf_curve, shift(spread_curve, -bump_bp))
    # The RISK-FREE curve is held FIXED. That separation is the point.
    RETURN (down.pv - up.pv) / (2 * bump_bp)
```

### 3.4 Greeks

```
FUNCTION greeks_bsm(S, K, r, q, sigma, tau, is_call):
    d1 = (ln(S/K) + (r - q + 0.5*sigma^2)*tau) / (sigma*sqrt(tau))
    d2 = d1 - sigma*sqrt(tau)
    dq, dr, pdf1 = exp(-q*tau), exp(-r*tau), normpdf(d1)

    gamma = dq*pdf1 / (S*sigma*sqrt(tau))          # SAME for call and put
    vega  = S*dq*pdf1*sqrt(tau)                    # SAME for call and put
    IF is_call:
        delta = dq*normcdf(d1)
        theta = -S*dq*pdf1*sigma/(2*sqrt(tau)) - r*K*dr*normcdf(d2) + q*S*dq*normcdf(d1)
        rho   = K*tau*dr*normcdf(d2)
    ELSE:
        delta = dq*(normcdf(d1) - 1)
        theta = -S*dq*pdf1*sigma/(2*sqrt(tau)) + r*K*dr*normcdf(-d2) - q*S*dq*normcdf(-d1)
        rho   = -K*tau*dr*normcdf(-d2)

    RETURN { delta, gamma,
             vega:  vega/100,        # per 1 VOL POINT
             theta: theta/365,       # per DAY
             rho:   rho/100,         # per 1%
             vanna: -dq*pdf1*d2/sigma,
             volga: vega*d1*d2/sigma }
```

### 3.5 Jump-to-default — computed, never bumped

```
FUNCTION gross_jtd(position):
    IF position.can_unwind_without_default_exposure: RETURN 0     # MAR22.13

    lgd = 0.25 IF position.is_covered_bond
     ELSE 0.75 IF position.is_senior_debt
     ELSE 1.00                                                    # MAR22.12
    IF NOT position.price_linked_to_recovery: lgd = 1.0           # MAR22.12(4)

    notional = notional_for_jtd(position)      # bond CALL -> ZERO (MAR22.14)
    IF position.direction == SHORT: notional = -abs(notional)
    pnl = position.market_value - abs(notional)

    raw = lgd*notional + pnl
    RETURN max(raw, 0) IF position.direction == LONG ELSE min(raw, 0)
```

---

## 4. Risk measures

### 4.1 Historical simulation

```
FUNCTION historical_scenarios(market_today, history, lookback_n, factor_types):
    scenarios = []
    FOR t IN 1..lookback_n:
        shock = {}
        FOR f IN factors:
            IF NOT history.has(f, t) OR NOT history.has(f, t+1):
                RECORD_MISSING(f, t)                  # NEVER silently skip
                CONTINUE
            IF factor_types[f] IN {RATE, SPREAD}:
                shock[f] = history[f, t] - history[f, t+1]        # ABSOLUTE
            ELSE:
                shock[f] = history[f, t] / history[f, t+1] - 1    # RELATIVE
        scenarios.append(shock)
    RETURN scenarios, MISSING_LOG


FUNCTION historical_var_es(portfolio, market_today, scenarios, alpha,
                           quantile_convention):
    v0 = value_portfolio(portfolio, market_today)
    pnl = []
    FOR s IN scenarios:
        v = value_portfolio(portfolio, apply_shock(market_today, s))   # FULL reval
        pnl.append(v - v0)
    pnl = sort_ascending(pnl)

    n   = len(pnl)
    idx = (1 - alpha) * n
    IF   quantile_convention == "ROUND_UP":    var = -pnl[ceil(idx) - 1]
    ELIF quantile_convention == "ROUND_DOWN":  var = -pnl[floor(idx) - 1]
    ELSE:
        lo = floor(idx); frac = idx - lo
        var = -(pnl[lo-1] + frac*(pnl[lo] - pnl[lo-1]))

    full = floor(idx); frac = idx - full
    tot  = sum(-x for x in pnl[:full])
    IF frac > 0 AND full < n: tot += frac * (-pnl[full])
    es = tot / idx

    ASSERT es >= var                       # always true, at the same alpha
    RETURN { var, es, quantile_convention, scenario_count: n,
             scenarios_missing: count(MISSING_LOG) }
```

### 4.2 FRTB liquidity-adjusted ES

```
FUNCTION frtb_es(positions, factors, horizons, T = 10):
    # Computed DIRECTLY at the 10-day horizon. NO sqrt-T scaling. MAR33.4(5)
    es_all = es_97_5(positions, factors, horizon=T, scale_from_shorter=FALSE)
    total  = es_all ** 2
    LH = { 1:10, 2:20, 3:40, 4:60, 5:120 }

    FOR j IN [2,3,4,5]:
        Q_j  = [ f for f in factors if horizons[f] >= LH[j] ]   # NESTED subset
        ASSERT is_subset(Q_j, Q_{j-1})
        es_j = es_97_5(positions, Q_j, horizon=T, scale_from_shorter=FALSE)
        total += ( es_j * sqrt((LH[j] - LH[j-1]) / T) ) ** 2

    RETURN sqrt(total)
```

### 4.3 Stress and reverse stress

```
FUNCTION historical_stress(portfolio, market_today, history, start_date, end_date):
    shock, unmapped = {}, []
    FOR f IN portfolio.risk_factors:
        IF NOT history.has(f, start_date) OR NOT history.has(f, end_date):
            unmapped.append(f)                    # REPORTED, never zeroed
            CONTINUE
        shock[f] = ( history[f,end] - history[f,start] IF f.type IN {RATE,SPREAD}
                     ELSE history[f,end]/history[f,start] - 1 )

    v0 = value_portfolio(portfolio, market_today)
    v1 = value_portfolio(portfolio, apply_shock(market_today, shock))   # FULL
    RETURN { pnl: v1 - v0,
             by_desk: decompose(portfolio, shock, "desk"),
             top_drivers: largest_contributors(portfolio, shock, 10),
             unmapped_factor_count: len(unmapped) }


FUNCTION reverse_stress(portfolio, target_loss, cov):
    delta  = sensitivity_vector(portfolio)
    x      = (target_loss * (cov @ delta)) / (delta.T @ cov @ delta)   # seed
    x      = newton_refine(lambda z: pnl_full_reval(portfolio, z) + target_loss, x)
    RETURN { shock_vector: x,
             implausibility_sigma: sqrt(x.T @ inverse(cov) @ x),
             narrative: interpret(x) }
```

---

## 5. FRTB

### 5.1 SBM delta / vega

```
FUNCTION sbm_charge(sensitivities, risk_class, scenario):
    K, S = {}, {}
    FOR b IN buckets(risk_class):
        net = net_sensitivities_by_factor(sensitivities, risk_class, b)  # NET FIRST
        WS  = { k: net[k] * risk_weight(risk_class, b, k) for k in net }

        IF is_no_offset_bucket(risk_class, b):        # CSR 16, CSR-sec 25
            K[b] = sum(abs(w) for w in WS.values())
        ELSE:
            q = sum(w*w for w in WS.values())
            FOR each unordered pair (k, l), k != l:
                rho = adjust(correlation(risk_class, b, k, l), scenario)
                q += 2 * rho * WS[k] * WS[l]
            K[b] = sqrt(max(q, 0))                   # FLOORED — MAR21.4(4)
        S[b] = sum(WS.values())

    q = sum(K[b]**2 for b in K)
    FOR each unordered pair (b, c):
        q += 2 * adjust(cross_bucket_gamma(risk_class,b,c), scenario) * S[b]*S[c]

    IF q < 0:                                        # MAR21.4(5)(b) FALLBACK
        S = { b: max(min(S[b], K[b]), -K[b]) for b in S }
        q = sum(K[b]**2 for b in K)
        FOR each unordered pair (b, c):
            q += 2 * adjust(cross_bucket_gamma(risk_class,b,c), scenario) * S[b]*S[c]

    RETURN sqrt(max(q, 0))


FUNCTION adjust(rho, scenario):
    IF scenario == "MEDIUM": RETURN rho                             # MAR21.6(1)
    IF scenario == "HIGH":   RETURN min(rho * 1.25, 1.0)            # MAR21.6(2)
    IF scenario == "LOW":    RETURN max(2*rho - 1.0, 0.75*rho)      # MAR21.6(3)
```

### 5.2 Curvature

```
FUNCTION curvature(instruments, factor_k, rw_curv, deltas, risk_class):
    base = sum(price(i, base_market) for i in instruments)
    up   = sum(price(i, shock(base_market, factor_k, +rw_curv)) for i in instruments)
    dn   = sum(price(i, shock(base_market, factor_k, -rw_curv)) for i in instruments)

    # MAR21.5(2)(f): FX/equity -> instrument delta;
    #                GIRR/CSR/commodity -> SUM across ALL tenors of the curve
    s_k = ( sum(deltas[i][factor_k] for i in instruments) IF risk_class IN {FX, EQ}
            ELSE sum(deltas[i][t] for i in instruments for t in tenors(factor_k)) )

    RETURN ( -(up - base - rw_curv * s_k),        # CVR+
             -(dn - base + rw_curv * s_k) )       # CVR-


FUNCTION psi(x, y):
    RETURN 0 IF (x < 0 AND y < 0) ELSE 1          # ZERO only if BOTH negative
```

### 5.3 DRC and RRAO

```
FUNCTION drc_bucket(net_jtds, risk_weights):
    longs  = { o:v for o,v in net_jtds.items() if v > 0 }
    shorts = { o:v for o,v in net_jtds.items() if v < 0 }
    sum_l  = sum(longs.values())                  # NOT risk-weighted
    sum_s  = abs(sum(shorts.values()))            # NOT risk-weighted
    hbr    = sum_l / (sum_l + sum_s) IF (sum_l + sum_s) > 0 ELSE 0   # MAR22.23
    wl = sum(risk_weights[o]*v      for o,v in longs.items())
    ws = sum(risk_weights[o]*abs(v) for o,v in shorts.items())
    RETURN max(wl - hbr*ws, 0)                    # MAR22.25


FUNCTION rrao(portfolio):
    charge = 0
    FOR i IN portfolio.instruments:
        IF i.is_listed OR i.is_ccp_eligible: CONTINUE            # MAR23.7
        IF i.is_exactly_matched_back_to_back: CONTINUE           # MAR23.7
        IF   i.has_exotic_underlying:   charge += i.gross_notional * 0.010
        ELIF i.bears_other_residual_risk: charge += i.gross_notional * 0.001
    RETURN charge


FUNCTION sa_total(portfolio):
    sbm = max( sum(sbm_charge(s, rc, sc) + vega_charge(rc, sc) + curv_charge(rc, sc)
                   for rc in SEVEN_RISK_CLASSES)
               for sc in ["MEDIUM","HIGH","LOW"] )                # MAR21.7
    RETURN sbm + total_drc(portfolio) + rrao(portfolio)           # SIMPLE SUM
```

### 5.4 RFET and SES

```
FUNCTION rfet(factor, observations, assessment_date):
    real  = [o for o in observations
               if o.is_real_price AND NOT o.is_collateral_valuation]   # MAR31.12
    daily = deduplicate_by_day(real)                                    # max 1/day
    obs   = [o for o in daily if o.date IN one_year_ending(assessment_date)]

    IF len(obs) >= 100: RETURN MODELLABLE                          # criterion 2
    IF len(obs) >= 24:                                             # criterion 1
        worst = min(count_in_window(obs, d, d+90) for d in window.days)
        IF worst >= 4: RETURN MODELLABLE
    RETURN NON_MODELLABLE


FUNCTION classify_derived(factor):
    # MAR31.13 fn 3 — contamination flows ONE WAY
    IF any(c.is_non_modellable for c in factor.components): RETURN NON_MODELLABLE
    IF factor.spans_distinct_buckets: RETURN rfet(factor)
    RETURN MODELLABLE


FUNCTION ses(nmrfs, rho = 0.6):                                     # MAR33.17
    ic = [n for n in nmrfs if n.is_idio_credit AND n.zero_corr_demonstrated]
    ie = [n for n in nmrfs if n.is_idio_equity AND n.zero_corr_demonstrated]
    rest = [n for n in nmrfs if n NOT IN ic + ie]
    s = sum(n.ses for n in rest)
    RETURN sqrt( sum(n.ses**2 for n in ic)
               + sum(n.ses**2 for n in ie)
               + (rho*s)**2 + (1 - rho**2)*sum(n.ses**2 for n in rest) )


FUNCTION nmrf_horizon(factor):
    RETURN max(mar33_12_horizon(factor), 20)                       # MAR33.16(1)
```

---

## 6. P&L, backtesting and PLA

```
FUNCTION pnl_suite(pos_t0, pos_t1, mkt_t0, mkt_t1, actual_pnl,
                   pricing_model_set, risk_model, decomposition_order):
    # HPL — static book, today's market, SAME pricers as reported P&L (MAR32.29)
    hpl = value_all(pos_t0, mkt_t1, pricing_model_set) \
        - value_all(pos_t0, mkt_t0, pricing_model_set)

    # RTPL — ONLY the risk model's factors (MAR32.22(2))
    m1 = mkt_t0.copy()
    FOR f IN risk_model.risk_factors: m1[f] = mkt_t1[f]
    rtpl = risk_model.engine.value(pos_t0, m1) - risk_model.engine.value(pos_t0, mkt_t0)

    comp = {}; m = mkt_t0; v = value_all(pos_t0, m, pricing_model_set)
    m_aged = age_market(m, 1_day); v_aged = value_all(pos_t0, m_aged, pricing_model_set)
    comp["carry_roll_theta"] = v_aged - v; v, m = v_aged, m_aged
    FOR f IN decomposition_order:                    # FIXED, VERSIONED order
        m_next = apply_factor_move(m, f, mkt_t1[f])
        v_next = value_all(pos_t0, m_next, pricing_model_set)
        comp[f] = v_next - v; v, m = v_next, m_next
    comp["new_trades"] = value_of_new_trades(pos_t1, mkt_t1)
    comp["amendments"] = value_of_amendments(pos_t0, pos_t1)
    comp["fees"]       = booked_fees()
    comp["reserves"]   = reserve_movement()

    gross = sum(abs(c) for c in comp.values())
    resid = actual_pnl - sum(comp.values())
    RETURN { apl: actual_pnl, hpl, rtpl, components: comp,
             residual: resid,
             residual_ratio_gross: resid/gross IF gross > 0 ELSE 0 }  # GROSS basis


FUNCTION backtest(var_series, apl, hpl, confidence):
    e_apl = e_hpl = unavailable = 0
    FOR t IN range(len(var_series)):
        IF var_series[t] IS NULL OR apl[t] IS NULL OR hpl[t] IS NULL:
            unavailable += 1; CONTINUE                              # MAR32.5(2)
        IF -apl[t] > var_series[t]: e_apl += 1
        IF -hpl[t] > var_series[t]: e_hpl += 1
    total = max(e_apl, e_hpl) + unavailable                         # MAR32.5(1)
    RETURN { e_apl, e_hpl, unavailable, total,
             expected: len(var_series)*(1-confidence),
             zone: bankwide_zone(total), multiplier: bankwide_multiplier(total) }


FUNCTION desk_eligibility(exc_99, exc_975):
    RETURN "SA" IF (exc_99 > 12 OR exc_975 > 30) ELSE "IMA"         # MAR32.19


FUNCTION pla(rtpl, hpl):
    ASSERT len(rtpl) == 250 AND len(hpl) == 250                     # MAR32.35
    spearman = pearson(rank_ascending(rtpl), rank_ascending(hpl))   # MAR32.36-38
    ks = 0.0
    FOR x IN sorted(set(rtpl) UNION set(hpl)):                      # MAR32.39-41
        ks = max(ks, abs(0.004*count(v <= x for v in rtpl)
                       - 0.004*count(v <= x for v in hpl)))
    zone = ( "GREEN" IF (spearman > 0.80 AND ks < 0.09)             # BOTH
        ELSE "RED"   IF (spearman < 0.70 OR  ks > 0.12)             # EITHER
        ELSE "AMBER" )                                              # MAR32.42
    RETURN { spearman, ks, zone }
```

---

## 7. Data contracts — consolidated

Full field definitions in [24](24_Risk_Data_Model.md). The contracts an implementer needs first:

```
sensitivity:
    position_id, business_date, knowledge_date
    risk_factor_id                          # e.g. "USD.SOFR.ZERO.10Y"
    measure                enum {PV, DV01, KRD01, CS01, DELTA, GAMMA, VEGA,
                                 THETA, RHO, VANNA, VOLGA, CONVEXITY,
                                 CVR_UP, CVR_DOWN, JTD}
    value                  decimal
    currency               ISO-4217
    unit                   enum {CCY, CCY_PER_BP, CCY_PER_VOL_PT, CCY_PER_DAY,
                                 SHARES, YEARS, DIMENSIONLESS}
    computation_method     enum {ANALYTIC, BUMP_1SIDED, BUMP_CENTRAL, FULL_REVAL}   # REQUIRED
    bump_size              decimal | null                                           # REQUIRED
    sign_convention        enum {LOSS_ON_RISE, SIGNED_DERIVATIVE}                    # REQUIRED

risk_measure_result:
    business_date, knowledge_date, scope_type, scope_id
    measure                enum {VAR, ES}
    confidence_level       decimal                                   # REQUIRED
    horizon_days           int                                       # REQUIRED
    method                 enum {HISTORICAL, PARAMETRIC, MONTE_CARLO,
                                 DELTA_NORMAL, DELTA_GAMMA}
    quantile_convention    enum {ROUND_UP, ROUND_DOWN, INTERPOLATED}  # REQUIRED
    weighting_scheme       enum {EQUAL, AGE_WEIGHTED, VOL_SCALED, FILTERED}
    value                  decimal
    lookback_days          int
    scenario_count         int
    scenarios_missing      int                                       # REQUIRED

stress_result:
    business_date, scope_id, scenario_id, scenario_name
    scenario_type          enum {HISTORICAL, HYPOTHETICAL, SENSITIVITY,
                                 REVERSE, SUPERVISORY}
    revaluation_method     enum {FULL, SENSITIVITY_BASED}            # REQUIRED
    pnl                    decimal
    unmapped_factor_count  int                                       # REQUIRED
    shock_source           text                                      # traceable to data

frtb_sa_result:
    business_date, scope_id
    component              enum {SBM_DELTA, SBM_VEGA, SBM_CURVATURE, DRC, RRAO}
    risk_class             enum | null
    correlation_scenario   enum {MEDIUM, HIGH, LOW} | null           # store ALL THREE
    is_binding_scenario    boolean
    value                  decimal
    regulatory_citation    text                                      # e.g. "MAR21.4(4)"
```

> **The fields marked REQUIRED are the ones whose omission makes a number uninterpretable.** A DV01 without its bump size and sign convention, or a VaR without its quantile convention, cannot be reconciled against anyone else's.

---

## 8. Test suite

Every implementation should carry these as automated tests.

| # | Test | Expected |
|---|---|---|
| 1 | Zero-coupon bond Macaulay duration | **= maturity**, exactly |
| 2 | Coupon > yield | Price **> par** |
| 3 | Par swap at inception | PV ≈ 0 |
| 4 | Curve reprices its inputs | Within tolerance |
| 5 | Implied forwards | Positive, non-oscillating |
| 6 | Analytic vs bumped DV01 | Agree within tolerance |
| 7 | Bump-size stability | DV01 at 0.5/1/2bp stable |
| 8 | **`Σ KRD01 = parallel DV01`** | **Exact** |
| 9 | Duration + convexity at ±100bp | Within tolerance of full revaluation |
| 10 | Put-call parity | `C − P = S·e^(−qτ) − K·e^(−rτ)` |
| 11 | Gamma and vega | **Identical** for call and put |
| 12 | Delta bounds | Call ∈ [0,1]; put ∈ [−1,0] |
| 13 | Black-Scholes PDE | `Θ + ½σ²S²Γ + rSΔ − rV = 0` |
| 14 | Surface arbitrage | Calendar and butterfly pass |
| 15 | FRN signature | Near-zero DV01, full CS01 |
| 16 | Covariance matrix | PSD; Cholesky succeeds |
| 17 | Euler identity | `Σ CCR = σ_p` |
| 18 | Diversification bound | `σ_p ≤ Σ wᵢσᵢ` |
| 19 | All ρ = 1 | `σ_p = Σ wᵢσᵢ` |
| 20 | `ES_α ≥ VaR_α` | At the same α |
| 21 | ES fractional tail | Interpolated, not truncated |
| 22 | FRTB `Q(pᵢ,j)` | Nested subsets verified |
| 23 | SBM three scenarios | All computed; maximum taken |
| 24 | `S_b` clamping fallback | Triggers on a negative aggregate |
| 25 | ψ function | Returns 0 **only** when both negative |
| 26 | Curvature | `RW·s` subtracted |
| 27 | CSR bucket 16 | Simple sum of absolutes, no netting |
| 28 | Non-CTP securitisation γ | 0% across buckets 1–24 |
| 29 | Equity repo | **No** vega, **no** curvature |
| 30 | RRAO exclusions | Listed/cleared and matched back-to-back excluded |
| 31 | Bond call notional for JTD | **Zero** |
| 32 | HBR | Computed on **unweighted** net JTD |
| 33 | DRC cross-bucket | Simple sum, no offset |
| 34 | Backtest exception count | **max**(APL, HPL), not the sum |
| 35 | Desk thresholds | `>12` and `>30`, strictly |
| 36 | PLA sample | Exactly 250; KS step 0.004 |
| 37 | PLA zones | Green needs both; red triggers on either |
| 38 | Failed valuation | Returns `FAILED`, never 0 |
| 39 | Missing scenario | Counted and reported |
| 40 | Reproducibility | A historical date reruns to the published number |

---

## 9. Limitations

- **This is pseudocode, not code.** Numerical stability, precision, error handling and performance are implementation concerns not addressed here.
- **The algorithms are the common case.** Exotic products require product-specific pricing and, frequently, product-specific sensitivity definitions.
- **Performance is not addressed.** [25 §5](25_Risk_System_Architecture.md) covers the compute problem; the naive loops above will not run at scale without AAD, grid pricing or parallelism.
- **The test suite is necessary, not sufficient.** Passing all forty tests means the implementation is self-consistent and convention-compliant. It does not mean the model is right for the portfolio — that is [26](26_Model_Risk_and_Validation.md)'s question.

---

## 10. Related Concepts

- [24 — Risk Data Model](24_Risk_Data_Model.md) · [25 — Risk System Architecture](25_Risk_System_Architecture.md)
- [32 — Master Formula Handbook](32_Master_Formula_Handbook.md) · [37 — Calculation Dependency Graph](37_Calculation_Dependency_Graph.md)
- [30 — Worked Examples](30_Worked_Examples.md) — the numbers these algorithms should reproduce

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | Every `MAR` citation inline in the pseudocode |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current text |

*Accessed 25 August 2026.*
