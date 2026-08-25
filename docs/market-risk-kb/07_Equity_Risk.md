# 07 — Equity Market Risk

**Level:** 4 · **Prerequisites:** [02](02_Financial_Instruments.md), [03](03_Pricing_Fundamentals.md) · **Feeds:** [09](09_Options_and_Greeks.md), [17](17_FRTB_Standardised_Approach.md)

---

## 1. Plain English

**Equity risk is the risk of loss because share prices moved.**

It is the most intuitive market risk — everyone understands that a stock can go down — and for that reason its subtleties are the most often skipped. The subtleties are: *which* stocks, *whose* fault (market or company), the **dividends** that are forecast rather than contracted, the **borrow cost** that makes a short possible, and the **volatility surface** that prices the options.

---

## 2. Banking example

A bank's equity desk holds:

| Position | Market value |
|---|---|
| Long single-name technology stock | +$50,000,000 |
| Short index futures (hedge) | −$45,000,000 |

The desk describes itself as "roughly hedged, $5m net long."

The technology stock misses earnings and falls **12%**. The index falls **1%**.

```
Stock:   50,000,000 × (−12%)  =  −$6,000,000
Hedge:  −45,000,000 × (−1%)   =    +$450,000
Net                            =  −$5,550,000
```

The desk lost **$5.55m on a "$5m net long" position.** The index hedge removed *market* risk and left *idiosyncratic* risk entirely intact — and idiosyncratic risk is precisely what an earnings miss delivers.

> **Net exposure is not risk.** It is one number about risk, and for a book with single-name concentration it is the wrong one.

---

## 3. The exposure measures

### 3.1 Definitions

| Measure | Formula | What it tells you |
|---|---|---|
| **Long exposure** | Σ market value of long positions | Capital at risk on the long side |
| **Short exposure** | Σ \|market value\| of short positions | Borrow requirement; short squeeze risk |
| **Net exposure** | Long − Short | Directional market bet |
| **Gross exposure** | Long + Short | **Total capital at work; the leverage measure** |
| **Beta-adjusted net** | Σ (MVᵢ × βᵢ) | Directional bet in index-equivalent terms |

### 3.2 Numerical example

| Position | Market value | β |
|---|---|---|
| Stock A (long) | +$100,000,000 | 1.40 |
| Stock B (long) | +$60,000,000 | 0.70 |
| Stock C (short) | −$80,000,000 | 1.10 |
| Stock D (short) | −$40,000,000 | 0.50 |

```
Long exposure          =  $160,000,000
Short exposure         =  $120,000,000
Net exposure           =   $40,000,000
Gross exposure         =  $280,000,000

Beta-adjusted net      =  100×1.40 + 60×0.70 − 80×1.10 − 40×0.50
                       =  140 + 42 − 88 − 20
                       =  $74,000,000  index-equivalent
```

**Read the three numbers together.** Net exposure says $40m. Beta-adjusted net says the market bet is really $74m — nearly double, because the longs are higher-beta than the shorts. Gross exposure says $280m of capital is at work, which is what determines idiosyncratic and financing risk. **A book can be beta-neutral and still lose severely** if its single names move against it, which is exactly what happened in §2.

---

## 4. Beta

### 4.1 Plain English

How much a stock tends to move when the market moves.

### 4.2 Formula

```
            Cov(rᵢ, r_m)
   βᵢ  =  ────────────────
              Var(r_m)
```

Equivalently `βᵢ = ρ(i,m) · σᵢ / σ_m`.

### 4.3 Worked example

Stock returns have σᵢ = 32% annualised; the index has σ_m = 18%; their correlation is 0.62.

```
   β  =  0.62 × 32 / 18  =  1.102
```

A 1% index move corresponds, on average, to a 1.10% move in the stock.

**Decomposing the variance:**

```
   σᵢ²  =  β² σ_m²  +  σ_ε²           (systematic + idiosyncratic)

   Systematic     =  1.102² × 0.18²  =  0.03934      → σ = 19.8%
   Total          =  0.32²           =  0.10240
   Idiosyncratic  =  0.10240 − 0.03934 = 0.06306     → σ = 25.1%
```

**Idiosyncratic volatility (25.1%) exceeds systematic volatility (19.8%).** For a typical single name this is the normal state of affairs, and it is the quantitative form of the §2 lesson: an index hedge removes the smaller half of the risk.

### 4.4 Limitations of beta

- **Estimation-window dependent.** Beta on 1-year daily data, 2-year weekly data and 5-year monthly data will differ materially for the same stock.
- **Unstable.** Betas drift with capital structure, business mix and market regime.
- **Rises in crises.** Correlations converge in stress, so the beta that mattered historically understates the beta that matters when it counts.
- **A single-factor summary.** Sector, size, value, momentum and quality exposures are invisible to it.

---

## 5. Dividend risk

**Dividends are forecast, not contracted.** An equity forward, future, swap or option prices off *expected* dividends over its life. A dividend cut moves every one of them without the spot price moving at all.

```
   F  =  S · e^((r − q)·τ)         where q is the expected dividend yield
```

**Worked example.** A 2-year equity forward on a stock at $100, `r` = 4%, expected `q` = 3%:

```
   F  =  100 × e^((0.04−0.03)×2)  =  100 × e^0.02  =  $102.02
```

The company halves its dividend, so `q` → 1.5%:

```
   F  =  100 × e^((0.04−0.015)×2)  =  100 × e^0.05  =  $105.13
```

The forward rose **$3.11**, or 3.05%, with the spot unchanged. A short forward position lost that amount on a dividend announcement.

Dividend risk is separately traded (there are listed dividend futures and dividend swaps) and separately limited on most equity derivatives desks. Under FRTB it is an Equity risk factor in its own right.

---

## 6. Equity repo / borrow risk

To short a stock you must borrow it, and the borrow fee is a market variable.

| Situation | Typical borrow cost | Risk |
|---|---|---|
| General collateral name | A few bp | Negligible |
| Moderately tight | 50–200bp | Erodes carry |
| Hard to borrow | Hundreds of bp or more | Repricing of every derivative on the name |
| **Recall** | — | **Forced buy-in at any price** |

Recall risk is the tail: the lender demands the stock back, the short must cover into a rising market, and the loss is unbounded in principle. Short squeezes are this mechanism operating at scale.

Under FRTB, **equity repo rates are Equity delta risk factors alongside spot prices** (`MAR21`), with their own risk weights — see §8.3. Note two explicit carve-outs: `MAR21` states there is **no vega risk capital requirement for equity repo rates**, and **no curvature risk capital requirement for equity repo rates** either.

---

## 7. Equity volatility, skew and correlation

### 7.1 The surface

Equity implied volatility varies systematically by strike and expiry. The dominant empirical feature is a **downward skew**: out-of-the-money puts trade at higher implied volatility than out-of-the-money calls.

**Why.** Equity markets fall faster than they rise, correlations rise in falls, and there is structural demand for downside protection from institutional holders. The skew is the price of that asymmetry, and it has been a persistent feature since 1987.

### 7.2 Sticky strike vs sticky delta

When spot moves, does the surface move with it?

| Regime | Assumption | Implied delta |
|---|---|---|
| **Sticky strike** | `σ(K)` unchanged as S moves | Lower than Black-Scholes delta for a put on a skewed surface |
| **Sticky delta (sticky moneyness)** | `σ(K/S)` unchanged | Different, and often closer to observed behaviour in FX |
| **Local volatility** | Surface implies a unique local vol function | A third answer again |

> **This is a modelling choice, not an observation, and it changes the reported delta of every option on the book.** Two banks with identical positions and identical surfaces will report different equity deltas if they assume different stickiness. Any equity derivatives risk report should state its regime.

### 7.3 Correlation and dispersion

A basket or index option depends on the correlation between constituents:

```
   σ_index²  =  Σ wᵢ² σᵢ²  +  Σ Σ  wᵢ wⱼ σᵢ σⱼ ρᵢⱼ
                              i≠j
```

**Dispersion trading** — short index volatility, long constituent volatility — is a direct bet that realised correlation will be lower than implied. It is short correlation, and it loses precisely in a systemic sell-off when everything moves together. This is a textbook example of a strategy whose risk is invisible in normal times and concentrated entirely in the tail.

---

## 8. FRTB treatment

### 8.1 Risk factors

- **Delta:** equity **spot prices** and equity **repo rates**
- **Vega:** implied volatilities of equity options
- **Curvature:** equity **spot prices only** — repo rates are excluded

### 8.2 Buckets (`MAR21.72`, Table 9)

Buckets are set along **three dimensions — market capitalisation, economy and sector**:

| Bucket | Market cap | Economy | Sector |
|---|---|---|---|
| 1 | Large | Emerging market | Consumer goods & services, transportation & storage, admin & support services, healthcare, utilities |
| 2 | Large | Emerging market | Telecommunications, industrials |
| 3 | Large | Emerging market | Basic materials, energy, agriculture, manufacturing, mining & quarrying |
| 4 | Large | Emerging market | Financials incl. government-backed financials, real estate activities, technology |
| 5 | Large | Advanced | Consumer goods & services, transportation & storage, admin & support services, healthcare, utilities |
| 6 | Large | Advanced | Telecommunications, industrials |
| 7 | Large | Advanced | Basic materials, energy, agriculture, manufacturing, mining & quarrying |
| 8 | Large | Advanced | Financials incl. government-backed financials, real estate activities, technology |
| 9 | Small | Emerging market | All sectors of buckets 1–4 |
| 10 | Small | Advanced | All sectors of buckets 5–8 |
| 11 | — | — | **Other sector** |
| 12 | Large | Advanced | Equity **indices** (non-sector specific) |
| 13 | — | — | Other equity **indices** (non-sector specific) |

**Definitions that matter (`MAR21.74`–`MAR21.76`):**

- **Large market cap** = market capitalisation **≥ USD 2 billion**; small = < USD 2 billion. Market cap is the total outstanding shares of the same listed legal entity (or group where the listed entity is a parent) **across all stock markets globally**. The standard is explicit: *"Under no circumstances should the sum of the market capitalisations of multiple related listed entities be used"* to make this determination.
- **Advanced economies** are enumerated exhaustively: *Canada, the United States, Mexico, the euro area, the non-euro area western European countries (the United Kingdom, Norway, Sweden, Denmark and Switzerland), Japan, Oceania (Australia and New Zealand), Singapore and Hong Kong SAR.*
- An issuer that cannot be assigned to a sector goes to **bucket 11**. For multinational, multi-sector issuers, allocation is by **the most material region and sector in which the issuer operates**.

### 8.3 Risk weights (`MAR21.77`, Table 10)

| Bucket | Equity spot price RW | Equity repo rate RW |
|---|---|---|
| 1 | 55% | 0.55% |
| 2 | 60% | 0.60% |
| 3 | 45% | 0.45% |
| 4 | 55% | 0.55% |
| 5 | 30% | 0.30% |
| 6 | 35% | 0.35% |
| 7 | 40% | 0.40% |
| 8 | 50% | 0.50% |
| 9 | 70% | 0.70% |
| 10 | 50% | 0.50% |
| 11 | 70% | 0.70% |
| 12 | 15% | 0.15% |
| 13 | 25% | 0.25% |

Three things to notice:

1. **The repo-rate risk weight is exactly the spot risk weight divided by 100** in every bucket. This is a deliberate structural relationship, not a coincidence.
2. **Bucket 12 (large-cap advanced-economy indices) at 15% is by far the lowest.** Diversified index exposure is treated as fundamentally less risky than any single name — which it is.
3. **Bucket 9 (small-cap EM) and bucket 11 (other sector) both carry 70%**, the highest weights. Unclassifiable issuers are charged as though they were small-cap emerging-market names.

### 8.4 Correlations (`MAR21.78`)

Within a bucket, the correlation parameter ρ is:

- **99.90%** where one sensitivity is to an equity **spot price** and the other to an equity **repo rate**, and both relate to the **same issuer**.
- Otherwise, per the schedule in `MAR21.78(2)` for two spot-price sensitivities, which differentiates by bucket (large-cap advanced buckets receive higher within-bucket correlations than small-cap or emerging buckets, and the index buckets higher still).

As always, all of this is run under the **three correlation scenarios** of `MAR21.6` — medium, high (×1.25, capped at 100%) and low (`max(2ρ−1, 0.75ρ)`) — with capital set to the maximum (`MAR21.7`).

### 8.5 IMA liquidity horizons (`MAR33.12`, Table 2)

| Risk factor category | Liquidity horizon (days) |
|---|---|
| Equity price (**large cap**) | **10** |
| Equity price (**small cap**) | **20** |
| Equity price (large cap): **volatility** | **20** |
| Equity price (small cap): **volatility** | **60** |
| Equity: **other types** | **60** |

Note the pattern that recurs throughout the framework: **volatility always carries a longer horizon than the price it is the volatility of.** Volatility markets are thinner, and unwinding a vega position takes longer than unwinding the equivalent delta.

### 8.6 Default risk

Equities are subject to the **DRC** as well. `MAR22.8` addresses equity investments in funds treated as unrated "other sector" equity under `MAR21.36(3)`: they are treated as unrated equity instruments, and where the fund's mandate permits investment in primarily high-yield or distressed names, the bank must apply the **maximum risk weight achievable under that mandate** — computed by assuming the fund invests first in defaulted instruments to the maximum extent, then CCC, then B, then BB. **Neither offsetting nor diversification is allowed** between these generated exposures and other exposures.

---

## 9. Stress scenarios

| Scenario | Date | Character |
|---|---|---|
| **Black Monday** | 19 Oct 1987 | Single-day crash; the origin of the modern equity skew |
| **Dot-com unwind** | 2000–02 | Slow, sector-concentrated, prolonged |
| **GFC** | 2008–09 | Broad, correlated, with financials worst and correlations → 1 |
| **Volmageddon** | 5 Feb 2018 | VIX complex dislocation; short-vol products destroyed |
| **COVID crash** | Feb–Mar 2020 | Fastest major drawdown on record, then policy-driven reversal |
| **Meme squeeze** | Jan 2021 | Idiosyncratic short squeeze; borrow cost and recall risk realised |
| **Dispersion break** | generic | Realised correlation → 1; short-correlation books fail |

---

## 10. Pseudocode

```
FUNCTION equity_exposures(positions, betas, spot_prices):
    long_e = sum(p.qty * spot_prices[p.name] for p in positions if p.qty > 0)
    short_e = sum(abs(p.qty * spot_prices[p.name]) for p in positions if p.qty < 0)
    RETURN {
        "long":  long_e,
        "short": short_e,
        "net":   long_e - short_e,
        "gross": long_e + short_e,
        "beta_adjusted_net":
            sum(p.qty * spot_prices[p.name] * betas[p.name] for p in positions)
    }


FUNCTION sbm_equity_delta_capital(sensitivities, scenario):
    # sensitivities carry (bucket, issuer, factor_type in {SPOT, REPO})
    total_sq = 0
    Sb_list  = []
    FOR each bucket b:
        WS = [ s.value * rw(b, s.factor_type) for s in sensitivities if s.bucket == b ]

        IF b == 11:                              # other sector
            K_b = sum(abs(ws) for ws in WS)      # simple sum of absolutes
        ELSE:
            K_sq = sum(ws*ws for ws in WS)
            FOR each pair (k, l), k != l:
                rho = equity_rho(k, l, b)        # 99.90% for same-issuer spot/repo
                rho = apply_scenario(rho, scenario)
                K_sq += 2 * rho * WS[k] * WS[l]
            K_b = sqrt(max(K_sq, 0))

        total_sq += K_b * K_b
        Sb_list.append(clamp(sum(WS), -K_b, +K_b))    # S_b, capped per MAR21.4

    FOR each bucket pair (b, c):
        gamma = apply_scenario(equity_gamma(b, c), scenario)
        total_sq += 2 * gamma * Sb_list[b] * Sb_list[c]

    RETURN sqrt(max(total_sq, 0))
```

---

## 11. Validation checklist

| # | Check | Pass criterion |
|---|---|---|
| 1 | Exposure identity | `gross = long + short`; `net = long − short` |
| 2 | Beta source | Estimation window, frequency and index documented |
| 3 | Idiosyncratic risk reported | Not only beta-adjusted net |
| 4 | Dividend sensitivity | Present for all forwards, futures, swaps and options |
| 5 | Borrow cost | Modelled as a risk factor; hard-to-borrow names flagged |
| 6 | Surface arbitrage | No calendar or butterfly arbitrage in the fitted surface |
| 7 | Sticky regime | Delta convention (sticky strike / sticky delta / local vol) documented |
| 8 | Put-call parity | Holds on the fitted surface to within bid-offer |
| 9 | Market cap test | Applied to the single listed entity, **not** summed across related entities |
| 10 | Advanced-economy list | Exactly the `MAR21.75` enumeration, no local extensions |
| 11 | Bucket 11 population | Reviewed and challenged — it carries a 70% weight |
| 12 | Repo carve-outs | No vega or curvature charge computed on equity repo rates |
| 13 | Index look-through | Applied where required by `MAR21.36` |

---

## 12. Common implementation errors

| Error | Consequence |
|---|---|
| Reporting net exposure only | Idiosyncratic concentration invisible (see §2) |
| Beta from an inappropriate window | Hedge ratios systematically wrong |
| Ignoring dividend risk | Forwards and options move unexplained |
| Ignoring borrow/repo | Short book carry and recall risk unmeasured |
| Summing related listed entities for the market-cap test | Wrong bucket, wrong risk weight |
| Extending the advanced-economy list | Non-compliant bucketing |
| Charging vega or curvature on equity repo rates | Overstates capital; contradicts the standard |
| Ignoring correlation exposure in basket products | Dispersion risk unmeasured until it realises |
| Assuming a stickiness regime silently | Deltas not comparable, hedges drift |

---

## 13. Limitations

- Beta is a one-factor summary of a multi-factor world; it captures neither style exposures nor regime change.
- Equity return distributions are strongly negatively skewed and fat-tailed; normal-based approaches understate downside.
- Correlations rise in stress, so diversification is weakest exactly when it is needed.
- Single-name idiosyncratic risk is by construction unhedgeable with index instruments, and it typically exceeds systematic risk in magnitude.

---

## 14. Related Concepts

- [09 — Options and Greeks](09_Options_and_Greeks.md) · [10 — Portfolio Risk Mathematics](10_Portfolio_Risk_Mathematics.md)
- [17 — FRTB Standardised Approach](17_FRTB_Standardised_Approach.md) · [19 — Default Risk and DRC](19_Default_Risk_and_DRC.md)

---

## Sources

| Organisation | Document | Date | URL | Relevance |
|---|---|---|---|---|
| BCBS | *Minimum capital requirements for market risk* (d457) | Jan 2019, rev. Feb 2019 | https://www.bis.org/bcbs/publ/d457.pdf | `MAR21.72`–`MAR21.78` buckets, weights, correlations; `MAR22.8`; `MAR33.12` |
| BCBS | Consolidated Basel Framework | ongoing | https://www.bis.org/basel_framework/ | Current MAR21 text |

*Accessed 25 August 2026.*
