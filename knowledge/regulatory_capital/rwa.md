# Risk-Weighted Assets (RWA)

## Definition
Risk-Weighted Assets (RWA) express a bank's assets weighted by their risk, used
to determine minimum regulatory capital under the Basel framework. Capital
required = capital ratio (e.g. 8%) × RWA.

## Simplified formula (dry — standardised approach)
RWA = Σ_i ( EAD_i × RiskWeight_i )

Where:
- **EAD_i** — Exposure at Default for exposure i.
- **RiskWeight_i** — regulatory risk weight for that exposure's asset class /
  counterparty rating (e.g. 20% for high-grade, 100% for corporate,
  150% for sub-investment-grade).

## Data required to compute RWA
1. **Counterparty exposure** — EAD and counterparty rating (from
   `counterparty_exposure`).
2. **Portfolio positions** — exposures / notionals by asset class
   (from `portfolio_positions`).
3. **Asset metadata** — asset class used to map the correct risk weight
   (from `assets`).

## Indicative standardised risk weights
- Cash / sovereign (AAA–AA): 0%
- High-grade corporate (A): 50%
- Corporate (BBB): 100%
- Sub-investment-grade (BB and below): 150%

## Notes
- RWA feeds the capital ratio: CET1 ratio = CET1 capital / RWA.
- CVA itself carries a capital charge (the "CVA risk capital charge") that adds
  to credit RWA.
