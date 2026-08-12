# Credit Ratings & PD Estimation

## Definition
Probability of Default (PD) is the key credit-risk input (see `pd_lgd_ead.md`).
This doc covers *how PD is actually estimated* — the three standard routes that
turn creditworthiness into a number.

## Three routes to PD
1. **Ratings-based (through-the-cycle)**: map an external rating (S&P/Moody's) or
   internal grade to a long-run average default rate. Stable; used for capital.
2. **Model / scoring-based (point-in-time)**: a statistical model (logistic
   regression, scorecard) on financials and behaviour outputs a PD. Responsive to
   the cycle; used for IFRS 9 provisioning and origination.
3. **Market-implied**: back out PD from the counterparty's CDS spread or bond
   spread. Forward-looking; used for pricing (CVA) and monitoring.

## Rating → PD (indicative 1-year)
| Rating | Approx PD |
|--------|-----------|
| AAA–AA | ~0.02% |
| A      | ~0.05% |
| BBB    | ~0.20% |
| BB     | ~1.0%  |
| B      | ~4.0%  |
| CCC    | ~20%+  |

## Market-implied PD (dry approximation)
PD ≈ credit_spread / LGD   (per year, credit-triangle approximation)

e.g. a 180 bp spread with LGD 0.60 → PD ≈ 0.018 / 0.60 ≈ 3.0% per year.

## Data required
1. **Counterparty exposure** — rating and credit_spread_bps per counterparty,
   plus recovery_rate for LGD (`counterparty_exposure`).
2. **Portfolio positions** — exposures by counterparty for portfolio-level PD
   aggregation (`portfolio_positions`).

## Notes
- Through-the-cycle PD is stable (capital); point-in-time PD moves with the cycle
  (provisioning) — the same name, two calibrations.
- Market-implied PD reacts fastest but embeds a risk premium, so it overstates
  the "real-world" default probability.
- PD feeds Expected Loss (PD × LGD × EAD) and credit RWA.
