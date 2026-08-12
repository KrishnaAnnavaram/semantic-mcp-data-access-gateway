# Counterparty Exposure Metrics (EE / EPE / PFE)

## Definition
Exposure metrics quantify how much a bank stands to lose if a counterparty
defaults, at different points in the life of a derivative trade. They are the
building blocks for CVA (pricing) and for counterparty credit risk capital.

## The core measures
- **Current Exposure (CE)**: max(mark-to-market, 0) today — what you'd lose if
  the counterparty defaulted right now.
- **Expected Exposure (EE(t))**: the average exposure at future time t across
  simulated market paths.
- **Expected Positive Exposure (EPE)**: the time-average of EE(t) over the life
  of the trade — a single summary number.
- **Potential Future Exposure (PFE)**: a high percentile (e.g. 95%/99%) of the
  exposure distribution at time t — the "bad case" exposure, analogous to VaR
  but for counterparty exposure.

## Method (dry)
1. Simulate market risk factors forward over many paths.
2. Revalue the netting set of trades with the counterparty at each future date.
3. Apply netting and collateral, floor at zero (you only lose when they owe you).
4. EE(t) = mean over paths; PFE(t) = chosen percentile over paths;
   EPE = average of EE(t) over t.

## Data required
1. **Counterparty exposure** — current/expected exposure, EPE, netting terms
   (`counterparty_exposure`).
2. **Portfolio positions** — the trades facing the counterparty
   (`portfolio_positions`).
3. **Historical prices** — to drive the forward market-factor simulation
   (`historical_prices`).

## Notes
- Exposure is one-sided: floored at zero because you have no credit loss when you
  owe the counterparty.
- EE/EPE feed CVA; PFE feeds credit-limit monitoring and regulatory EAD.
