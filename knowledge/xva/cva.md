# Credit Valuation Adjustment (CVA)

## Definition
Credit Valuation Adjustment (CVA) is the market price of counterparty credit
risk — the expected loss from a counterparty defaulting before a derivative
contract matures. It is the difference between the risk-free value of a
portfolio and its value accounting for the counterparty's default risk.

## Simplified formula (dry / unilateral)
CVA ≈ LGD × Σ_t [ EE(t) × PD(t) × DF(t) ]

Where, per time bucket t:
- **LGD** — Loss Given Default = 1 − Recovery Rate.
- **EE(t)** — Expected Exposure to the counterparty at time t.
- **PD(t)** — marginal Probability of Default in bucket t (from the credit
  curve / spread).
- **DF(t)** — risk-free discount factor.

A common closed-form proxy:
CVA ≈ LGD × EPE × (1 − exp(−spread × T / LGD))
where EPE is Expected Positive Exposure and spread is the counterparty CDS
spread.

## Data required to compute CVA
1. **Counterparty exposure** — current and expected exposure, plus the credit
   spread and recovery rate (from `counterparty_exposure`).
2. **Portfolio positions** — the trades facing that counterparty (from
   `portfolio_positions`), to build the exposure profile.
3. **Historical prices** — to simulate future exposure paths for EE(t)
   (from `historical_prices`); a dry version may use the reported EPE directly.

## Notes
- Recovery rate for senior unsecured claims is often assumed 40% (LGD = 60%).
- Higher counterparty spread → higher PD → higher CVA.
- Wrong-way risk: exposure and default probability rising together increases CVA.
