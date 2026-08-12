# PD / LGD / EAD — Credit Risk Parameters

## Definition
The three core parameters of credit loss. Together they give **Expected Loss**,
the anticipated average loss on a credit exposure, and they feed both accounting
provisions and regulatory capital (RWA).

- **PD — Probability of Default**: likelihood the counterparty defaults over a
  horizon (typically 1 year). Derived from ratings, credit scores, or CDS
  spreads.
- **LGD — Loss Given Default**: fraction of exposure lost if default occurs =
  1 − Recovery Rate. Senior unsecured is often ~60% (40% recovery).
- **EAD — Exposure at Default**: expected amount outstanding at the moment of
  default (for derivatives, derived from exposure metrics — see
  `exposure_metrics.md`).

## Formula (dry)
Expected Loss (EL) = PD × LGD × EAD

## Mapping ratings to PD (indicative)
- AAA–AA: ~0.02%
- A: ~0.05%
- BBB: ~0.20%
- BB: ~1.0%
- B: ~4.0%

## Data required
1. **Counterparty exposure** — rating, credit spread, recovery rate, exposure
   (`counterparty_exposure`) → gives PD (from rating/spread), LGD (from
   recovery), and EAD (from exposure).
2. **Portfolio positions** — exposures / notionals by counterparty
   (`portfolio_positions`).

## Notes
- Expected Loss is the *provision* (priced in); Unexpected Loss (the volatility
  of losses) is what capital/RWA covers.
- PD can be "through-the-cycle" (stable, for capital) or "point-in-time"
  (responsive, for IFRS 9 provisioning).
- These same three parameters drive the RWA credit calculation (see `rwa.md`).
