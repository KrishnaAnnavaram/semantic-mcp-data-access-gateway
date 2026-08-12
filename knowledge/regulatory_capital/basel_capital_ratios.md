# Basel Capital Ratios

## Definition
Basel capital ratios measure whether a bank holds enough loss-absorbing capital
against its risk-weighted assets (RWA). They are the headline solvency metrics
regulators enforce under Basel III/IV.

## The core ratios
- **CET1 ratio** = Common Equity Tier 1 capital / RWA. The highest-quality
  capital (ordinary shares + retained earnings). Minimum 4.5%.
- **Tier 1 ratio** = Tier 1 capital / RWA. Minimum 6%.
- **Total capital ratio** = (Tier 1 + Tier 2) / RWA. Minimum 8%.

On top of the minimums sit **buffers**: a capital conservation buffer (2.5%), a
countercyclical buffer (0–2.5%), and surcharges for systemically important banks.

## Formula (dry)
CET1 ratio = CET1 capital / RWA

Where RWA aggregates credit RWA (incl. the CVA capital charge), market risk RWA,
and operational risk RWA. See `rwa.md` for how RWA itself is built.

## Data required
1. **RWA** — computed from `counterparty_exposure` + `portfolio_positions` +
   `assets` (see `rwa.md`).
2. **Capital figures** — CET1 / Tier 1 / Tier 2 amounts (bank-level capital
   ledger; not in the trade tables — supplied as a parameter or reference).

## Notes
- The ratios move inversely with RWA: raising RWA (riskier book) lowers every
  ratio for the same capital.
- A ratio below the minimum-plus-buffer triggers restrictions on dividends and
  bonuses before outright breach.
