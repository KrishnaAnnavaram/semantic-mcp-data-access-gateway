# Expected Shortfall (ES / CVaR)

## Definition
Expected Shortfall (ES), also called Conditional VaR (CVaR), is the average loss
*given that* the loss has exceeded the VaR threshold. Where VaR answers "how bad
can it get on a normal day", ES answers "if it goes past that, how bad on
average". ES is the Basel-mandated market-risk measure under FRTB, replacing VaR,
because it captures tail severity that VaR ignores.

## Key parameters
- **Confidence level**: FRTB uses 97.5% ES (calibrated to be close to 99% VaR).
- **Horizon**: 1-day, scaled to regulatory liquidity horizons.

## Formula (historical simulation, dry)
1. Build the P&L distribution exactly as for VaR (revalue positions under
   historical return scenarios).
2. Find VaR at confidence c = the (1 - c) percentile loss.
3. ES = the average of all losses that are worse than (beyond) the VaR level.

ES_c = average( losses where loss > VaR_c )

## Data required to compute ES
Same inputs as VaR:
1. **Portfolio positions** — quantities held (`portfolio_positions`).
2. **Historical prices** — return series per asset (`historical_prices`).
3. **Asset metadata** — currency / class for aggregation (`assets`).

## Notes
- ES is always >= VaR at the same confidence level.
- ES is a *coherent* risk measure (it is sub-additive: diversification never
  increases it), which VaR is not.
- Report ES as a positive loss number, same convention as VaR.
