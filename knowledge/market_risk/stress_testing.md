# Stress Testing & Scenario Analysis

## Definition
Stress testing estimates portfolio loss under severe but plausible market moves,
independent of historical probability. Where VaR/ES describe normal-distribution
tails, stress tests apply specific shocks — historical (e.g. 2008, COVID March
2020) or hypothetical (e.g. "rates +200bp, equities -30%") — to see what the book
loses if that scenario recurs.

## Observation window — how many rows a stress test reads
A historical replay reads exactly **2 observation dates**: the start and end of
the episode being replayed. The shock is the difference between those two
observed curves, so the dates between them are never read. A hypothetical
scenario reads **1 observation date** — the base curve the hand-specified shock
is applied to. Neither form consumes a time series.

## Types
- **Historical scenarios**: replay a real crisis's market moves.
- **Hypothetical scenarios**: hand-specified shocks to risk factors.
- **Reverse stress tests**: start from a loss the firm cannot survive and find
  the scenario that produces it.

## Method (dry)
1. Define a scenario as a set of shocks per risk factor / asset (e.g.
   equity -30%, credit spread +150bp, FX +10%).
2. Revalue every position under the shocked market.
3. Stress P&L = shocked portfolio value - current portfolio value.
4. Aggregate by desk, asset class, and counterparty.

## Data required
1. **Portfolio positions** — what is held and its current value
   (`portfolio_positions`).
2. **Asset metadata** — asset class, to map the right shock to each position
   (`assets`).
3. **Historical prices** — to source or calibrate historical-scenario shocks
   (`historical_prices`).

## Notes
- Stress tests are *deterministic*: a scenario has no probability attached, so
  results are a "what-if" loss, not a percentile.
- They complement VaR/ES by capturing correlations and moves that break under
  stress but look benign in normal-period data.
