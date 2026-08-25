# Capability gaps

What this system **cannot** compute, why, and what each capability would
require.

This document exists because of one rule that runs through the whole engine:
**an absent capability is reported as absent, never as zero.** A risk or capital
figure that silently omits a risk class the book actually runs is not
conservative — it is understated, and it is understated invisibly. So the
unsupported list is published as a resource (`risk://capability-gaps`), asserted
in tests, and written out here in enough detail that anyone deciding whether to
close a gap can cost it.

Nothing below is a criticism of the current scope. The system holds US Treasury
fixed-rate bonds and a Treasury par yield curve, and it does that completely.
The gaps are what would be needed to hold something else.

---

## What is supported today

| | |
|---|---|
| **Instruments** | `FIXED_RATE_BOND` — semiannual, ACT/ACT ICMA, USD |
| **Market data** | US Treasury par yield curve, nominal and real, 1990 to present |
| **Risk factors** | Par yields at the published tenors |
| **Regulatory** | FRTB SA GIRR delta and curvature, one currency bucket |

Everything below is outside that.

---

## FRTB: what is and is not implemented

`risk-engine-mcp` implements **GIRR delta** and **GIRR curvature** under the
sensitivities-based method, for a single USD bucket. That is the whole of it.

| Risk class | Implemented | Why not |
|---|---|---|
| GIRR delta | ✅ | — |
| GIRR curvature | ✅ | — |
| GIRR vega | ❌ | No optionality in the book, so no volatility sensitivity exists to weight |
| CSR non-securitisation | ❌ | No credit-sensitive instruments and no credit spread curves |
| CSR securitisation (CTP and non-CTP) | ❌ | No securitisation exposures |
| Equity | ❌ | No equity positions or prices |
| Commodity | ❌ | No commodity positions or curves |
| FX | ❌ | Single currency; no FX rates |
| Default Risk Charge | ❌ | No issuer, rating, seniority or LGD data |
| Residual Risk Add-On | ❌ | No exotic instruments to add on for |

Also **not** implemented, and not claimed:

* **RFET / NMRF** — the risk factor eligibility test and the non-modellable
  capital add-on need real-price observation counts per risk factor, which this
  system does not hold. Treasury CMT quotes are indicative, not transactions.
* **PLA** — P&L attribution *as a regulatory test* needs a front-office and a
  risk-engine P&L series to compare. `compute_pnl_attribution_tool` decomposes a
  P&L; it does not run the Basel test, which requires the Spearman correlation
  and the Kolmogorov-Smirnov statistic between two independently produced series.
* **IMA expected shortfall** — the internal-model approach uses ES at 97.5% with
  five liquidity horizons and a stressed-period calibration. None of that is
  implemented; `compute_historical_risk_tool` is an analytical demonstration.

**The capital figure this system does produce is not a reported regulatory
capital requirement.** No supervisor has reviewed it, the positions are
synthetic, and it covers only the risk classes that can actually be measured.

---

## The cross-asset gaps

Each section states the same six things, because they are what a gap actually
costs: data in, position fields, a pricing model, sensitivities, tests, and the
change on each side of the MCP boundary.

### Credit

**Missing:** CS01, spread VaR, spread stress, jump-to-default (gross and net),
LGD and recovery assumptions, the Default Risk Charge.

| | |
|---|---|
| Market data | Credit spread curves per issuer or rating/sector bucket; recovery rates; a default probability source |
| Portfolio fields | Issuer id, seniority, rating, sector, notional, reference obligation |
| Pricing model | Survival-probability discounting, or a Z-spread/asset-swap-spread pricer on top of the existing bootstrap |
| Sensitivities | CS01 by spread tenor bucket, JTD per issuer, net JTD after offsetting long and short in the same name |
| Tests | Golden CS01 against a hand-computed risky annuity; JTD netting under the Basel offsetting rules; a spread curve that goes negative must be refused |
| Data MCP | Spread curve retrieval and history; issuer reference data; a recovery-rate table |
| Risk MCP | `credit_spread.py` for the risky discounting, `jtd.py` for default risk, and CSR tables in `regulatory/constants.py` |

Note that CS01 shares almost nothing with DV01 in implementation: the discounting
is survival-weighted and the sensitivity is to a *different* curve.

### Options

**Missing:** delta, gamma, vega, theta, rho, vanna, volga, implied volatility,
volatility surfaces, smile and skew, option curvature stress.

| | |
|---|---|
| Market data | An implied volatility surface — swaption cube or cap/floor vols — by expiry, tenor and strike |
| Portfolio fields | Option type, strike, expiry, underlying, exercise style, settlement |
| Pricing model | Black-76 or SABR for swaptions and caps; a numerical method for anything path-dependent |
| Sensitivities | Greeks by bump-and-reprice, plus vega by volatility bucket. Gamma and vega need a *second* order pass, which the current bump machinery does not do |
| Tests | Put-call parity; Black-76 against published values; a zero-volatility option must equal its forward intrinsic; delta must approach 0 and 1 at the extremes |
| Data MCP | Volatility surface retrieval with its own quote-basis labelling — normal versus lognormal vol is exactly the same category error as discount versus coupon-equivalent |
| Risk MCP | `options/black76.py`, `options/sabr.py`, `options/greeks.py`; GIRR vega tables |

**The quote-basis trap repeats here.** A normal (bp) vol and a lognormal (%) vol
for the same option are different numbers, both correct, and not interchangeable
— exactly the relationship between a bill discount rate and a coupon-equivalent
yield. Any surface entering this system must carry its basis.

### FX

**Missing:** FX delta, FX VaR, FX stress, cross-currency basis.

| | |
|---|---|
| Market data | Spot rates, forward points or FX swap curves, cross-currency basis curves |
| Portfolio fields | Currency per position; a reporting currency for the book |
| Pricing model | Conversion at spot, plus discounting on each currency's own curve. `price_portfolio` currently *refuses* to sum across currencies, which is the correct behaviour until this exists |
| Sensitivities | FX delta per currency pair; cross-gamma with rates |
| Tests | Triangular arbitrage consistency; covered interest parity between the FX forward and the two rate curves |
| Data MCP | FX rate retrieval and history with a stated fixing source and time |
| Risk MCP | Multi-currency `CompiledBook`; FX risk class in `regulatory/constants.py` |

### Equity and commodity

**Missing:** delta, VaR, beta, index-versus-component basis; commodity curve,
basis and location risk.

Both need a price source, position fields naming the instrument, and a spot or
futures curve model. Neither shares any machinery with the rate engine beyond
the scenario and aggregation framework, which is deliberately generic enough to
take them.

### Liquidity

**Missing:** bid/ask widening, liquidation cost, price impact, market depth,
liquidity horizons, liquidity-adjusted VaR and ES.

| | |
|---|---|
| Market data | Bid/ask spreads by instrument and tenor; traded volume or depth |
| Portfolio fields | Position size relative to typical daily volume |
| Pricing model | A cost function mapping size and depth to execution cost |
| Sensitivities | Liquidity-adjusted VaR = VaR + a liquidation cost term |
| Tests | Cost must be monotone in size; a zero position must cost zero |
| Data MCP | Bid/ask history. Treasury publishes none, so this needs a new source |
| Risk MCP | `liquidity.py`; liquidity horizons per risk factor for the IMA path |

Worth stating plainly: Treasury CMT quotes are **indicative bid-side
quotations**, not transactions. There is no bid/ask in this dataset at all.

### Fixed income beyond fixed-rate bonds

**Missing:** SOFR/OIS curves, swaps, futures, floating-rate notes, TIPS,
swaptions, caps and floors, basis curves, repo and funding.

| | |
|---|---|
| Market data | OIS and SOFR curves; basis spreads between them and Treasury; repo rates; for TIPS, a CPI series and seasonal adjustment |
| Portfolio fields | Floating index and spread, reset and fixing schedule, day count per leg, inflation lag and index ratio |
| Pricing model | Dual-curve discounting — OIS for discounting, the projection curve for forecasting. This is a structural change: the current engine has one curve doing both jobs |
| Sensitivities | DV01 split by curve (discount versus projection); basis DV01 |
| Tests | A par swap must value to zero; an FRN at its own spread must price to par on a reset date; a TIPS with zero realised inflation must match its nominal equivalent |
| Data MCP | New datasets, each with its own `treasury.dataset` row and caveat; the loader already discovers columns generically |
| Risk MCP | `MultiCurveSet` replacing the single `DiscountCurve`; new instrument types alongside `FixedRateBond` |

**Dual-curve discounting is the largest single change on this list.** It touches
the bootstrap, the pricer, every sensitivity, and the meaning of "the curve" in
every tool signature. It is not an addition; it is a generalisation.

---

## What would have to change on each side

The boundary holds for every gap above, and stating how is part of costing them:

| Layer | Change |
|---|---|
| `market-risk-data-mcp` | New datasets, new typed retrieval methods, new reference tables. **No arithmetic** — the data server stays a source of facts |
| `risk-engine-mcp` | New pricing modules, new sensitivity passes, new scenario families, new regulatory tables. **No database, no model, no network** |
| The host | New workflows joining the two, in `backend/workflows/risk_workflows.py` |

No gap on this page requires a third MCP server. The two-server split — facts on
one side, mathematics on the other — is what makes "was the input wrong, or the
maths?" answerable, and every capability above fits inside it.

---

## How to read an absent number

If a tool does not return a figure, one of three things is true, and the result
says which:

1. **It is out of scope.** `UNSUPPORTED_REGULATORY_SCOPE` or a `null` field with
   a stated reason. `vega_capital` is `null`, never `0.0`.
2. **The data was insufficient.** `INSUFFICIENT_HISTORY`,
   `MISSING_REQUIRED_MARKET_DATA`, `MISSING_CURVE_TENOR` — with what was missing
   named.
3. **The calculation was not truthful.** `INVALID_CURVE`,
   `NO_REVERSE_STRESS_SOLUTION`, `SOLVER_DID_NOT_CONVERGE` — the inputs were
   fine, the answer was not available.

None of them is a zero.
