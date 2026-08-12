# Value at Risk (VaR)

## Definition
Value at Risk (VaR) estimates the maximum expected loss of a portfolio over a
given time horizon at a specified confidence level, under normal market
conditions. A "1-day 99% VaR of $1M" means: on 99% of days, losses are not
expected to exceed $1M over one day.

## Key parameters
- **Confidence level**: typically 95% or 99%.
- **Horizon**: 1-day (trading/market risk) or 10-day (Basel regulatory).
- **Method**: historical simulation, parametric (variance-covariance), or
  Monte Carlo.

## Data required to compute VaR
To compute portfolio VaR you need:
1. **Portfolio positions** — quantity held per asset (from `portfolio_positions`).
2. **Historical prices** — a price time series per asset to derive returns
   (from `historical_prices`). Historical simulation typically uses 250–500
   trading days.
3. **Asset metadata** — currency, asset class (from `assets`) for aggregation.

## Historical simulation method (simplest, dry)
1. Pull the price series for each held asset.
2. Compute daily returns r_t = (P_t - P_{t-1}) / P_{t-1}.
3. Revalue the current portfolio under each historical return scenario to get a
   distribution of hypothetical P&L.
4. VaR at confidence c = the (1 - c) percentile of the P&L distribution
   (e.g. the 1st percentile for 99% VaR), reported as a positive loss number.

## Notes
- VaR does not describe losses beyond the threshold — use Expected Shortfall
  (CVaR) for tail severity.
- Scaling: a 1-day VaR is often scaled to 10-day by multiplying by sqrt(10)
  under the square-root-of-time rule.
