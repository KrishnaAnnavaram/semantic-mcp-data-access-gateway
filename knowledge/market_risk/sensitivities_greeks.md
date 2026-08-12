# Sensitivities & Greeks

## Definition
Sensitivities (a.k.a. "the Greeks") measure how much a position's value changes
for a small move in an underlying risk factor. Where VaR/ES give a loss
distribution, sensitivities give the *slope* — the day-to-day market-risk numbers
desks watch to know their directional exposure and to hedge it.

## The core measures
- **Delta**: change in value per unit change in the underlying price (equities,
  FX). A $1M delta means +$1M P&L per +1 unit move.
- **DV01 / PV01**: change in value for a 1 basis-point move in interest rates
  (rates, bonds). The primary interest-rate sensitivity.
- **Vega**: change in value per 1% change in volatility (options).
- **Gamma**: change in delta per unit move in the underlying (convexity).
- **Theta**: change in value per day of time decay (options).

## Method (dry)
Sensitivity to factor f ≈ ( V(f + Δf) − V(f − Δf) ) / (2 · Δf)

i.e. revalue the position with the factor bumped up and down by a small Δf and
take the central difference. Aggregate sensitivities across positions by risk
factor to see net desk exposure.

## Data required
1. **Portfolio positions** — instruments and quantities to bump-and-revalue
   (`portfolio_positions`).
2. **Asset metadata** — asset class, to know which Greek applies (delta for
   equity/FX, DV01 for rates, vega for options) (`assets`).
3. **Historical prices** — current levels of the underlying factors
   (`historical_prices`).

## Notes
- Sensitivities are *local* (first-order): valid for small moves. VaR/ES and
  stress tests cover large moves.
- Hedging works by offsetting net sensitivities to (near) zero per factor.
- Sensitivities also feed the FRTB standardised capital charge.
