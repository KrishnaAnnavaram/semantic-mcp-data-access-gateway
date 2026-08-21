# Supported Question & Use-Case Catalog

**semantic-mcp-data-access-gateway**

What a user can actually ask this gateway, derived from what the stores actually
hold — not from what a Treasury dataset sounds like it ought to support.

Every question here was written *after* inspecting the live PostgreSQL database,
the live Qdrant collection, both MCP servers over the wire, and the agents' own
code. The machine-readable source of truth is
[`tests/use_cases/question_catalog.json`](../tests/use_cases/question_catalog.json);
the coverage matrix is
[`question-test-coverage.md`](question-test-coverage.md).

**The document checks itself.** Every number below is asserted against the live
stores by `tests/use_cases/test_question_catalog.py`. Reload the database with
different coverage and this catalog fails rather than going quietly out of date.

---

## 1. Data capability summary

### PostgreSQL — the facts

`gateway@localhost:5432`, five schemas. **267,517 observations**, **52 series**,
**1990-01-02 → 2026-08-11**.

| Dataset | Since | Shape | What it is |
|---|---|---|---|
| `daily_treasury_yield_curve` | 1990 | wide | Nominal par yields, 14 live tenors + 1 excluded display duplicate |
| `daily_treasury_real_yield_curve` | 2003 | wide | TIPS-derived real par yields, 5 tenors |
| `daily_treasury_bill_rates` | 2002 | wide | Bills, in **two quoting bases** (bank discount act/360 **and** coupon-equivalent) |
| `daily_treasury_long_term_rate` | 2000 | long | 20-year composite + long-term average |
| `daily_treasury_real_long_term` | 2000 | wide | Long-term real average |

Coverage is **per series, not uniform** — this is what makes the boundary
questions real rather than decorative:

| Series | From | Rows |
|---|---|---:|
| `BC_2YEAR`, `BC_10YEAR`, `BC_5YEAR`, `BC_7YEAR`, `BC_1YEAR`, `BC_3YEAR`, `BC_6MONTH` | 1990-01-02 | 9,158 |
| `BC_30YEAR` | 1990-01-02 | 8,164 *(gap: discontinued 2002–2006)* |
| `BC_20YEAR` | 1993-10-01 | 8,219 |
| `BC_1MONTH` | 2001-07-31 | 6,259 |
| `TC_5/7/10YEAR` | 2003-01-02 | 5,906 |
| `TC_20YEAR` | 2004-07-27 | 5,515 |
| `TC_30YEAR` | 2010-02-22 | 4,121 |
| `BC_2MONTH` | 2018-10-16 | 1,954 |
| `BC_4MONTH` | 2022-10-19 | 952 |
| `BC_1_5MONTH` | 2025-02-18 | 371 |

**Portfolio data exists, and it is one synthetic book.** `demo.portfolio` holds
exactly `TREASURY_DEMO_001` (`SYNTHETIC_DEMO`), five fixed-rate bonds
(2y/5y/10y/20y/30y, $30m face), and seven scenarios — four tenor-vector shocks
and three historical replays (1994, 2009, 2020).

**What PostgreSQL does *not* hold:** no equities, no FX, no credit, no options,
no counterparty or exposure data, no note/bond instrument records beyond the five
demo positions. `treasury.bill_security` carries CUSIPs, but only for bills, and
no MCP tool exposes it.

### Qdrant — the domain knowledge

One collection, `quant_knowledge`: **71 chunks**, 384-dimensional, cosine,
11 documents across 4 domains.

| Domain | Documents | Chunks |
|---|---|---:|
| `market_risk` | var, expected_shortfall, sensitivities_greeks, stress_testing, yield_curve | 35 |
| `credit_risk` | pd_lgd_ead, credit_ratings_pd | 13 |
| `regulatory_capital` | rwa, basel_capital_ratios | 12 |
| `xva` | cva, exposure_metrics | 11 |

Every document is chunked on markdown headings, and every one carries an
`Observation window` and a `Data required` section — which is what lets the
domain expert quote a row count verbatim instead of recalling one.

**Note the asymmetry.** Three of the four domains (`xva`, `regulatory_capital`,
`credit_risk`, 36 of 71 chunks) describe measures this database **cannot
compute**. That is deliberate: the system explains CVA and RWA from the corpus
and declines to compute them, which is a supported behaviour and a tested one.

### MCP — what is reachable

| Server | Tools | Resources | Prompts |
|---|---:|---:|---:|
| `market-risk-data` | 14 | 4 | 3 |
| `risk-engine` | 5 | 2 | 3 |

Protocol `2026-07-28`, all six primitives live.

### Agents — what is *actually* reachable through `/chat`

This is the layer that decides whether a question is answerable, and it is
narrower than MCP:

| Capability | Status |
|---|---|
| Curve snapshot (any day's full curve, nominal or real) | available |
| Multi-tenor history, most recent N | available, **capped at ~251 rows** |
| `price_portfolio`, `compute_dv01`, `compute_var`, `run_stress` | available |
| Knowledge retrieval with verbatim citation | available |
| Orchestrator-mediated elicitation | available |
| Aggregation (mean, min, max, percentile, volatility) | **absent** |
| Date-range selection | **absent** (see DEF-002) |
| Curve slope as a computed value | **advertised but broken** (see DEF-001) |
| Cross-family comparison (nominal vs real in one answer) | **absent** |

---

## 2. The mapping that matters

```
PostgreSQL                MCP tool                   Agent capability        Questions
──────────────────────    ───────────────────────    ────────────────────    ─────────
analytics.v_mcp_curve  →  get_curve               →  curve snapshot       →  Q-DATA-001..005
v_mcp_observation      →  get_rate_history        →  history (≤251 rows)  →  Q-HIST-001..003
v_mcp_series_catalogue →  list_series             →  tool catalogue       →  Q-META-001
                       →  search_series           →  elicitation trigger  →  Q-ELICIT-001
v_mcp_portfolio_...    →  list_portfolios         →  clarify options      →  Q-ELICIT-002/003
                       →  get_portfolio           →  (inside risk calls)  →  Q-PORT-002
demo.scenario          →  list_scenarios          →  clarify options      →  Q-META-005
                       →  compute_dv01_tool       →  compute_dv01         →  Q-RISK-001
                       →  compute_historical_...  →  compute_var          →  Q-RISK-002/003
                       →  run_stress_tool         →  run_stress           →  Q-RISK-004/005
Qdrant quant_knowledge →  (not MCP — VectorStore) →  domain expert        →  Q-KNOW-*
```

**Reachable by MCP but never called by an agent:** `list_datasets`,
`get_series_coverage`, `explain_number`, `export_curve_csv`,
`brief_dataset_caveat`, `get_scenario`, `compute_key_rate_dv01_tool`. Data
existing in PostgreSQL does not make it answerable — that gap is the single most
useful thing this exercise surfaced.

---

## 3. Question categories

**66 questions, 17 categories: 36 supported, 13 partial, 17 unsupported.**
Full per-question detail lives in the JSON; this is the shape of it.

| Category | n | YES | PARTIAL | NO |
|---|---:|---:|---:|---:|
| A — Basic data lookup | 5 | 5 | 0 | 0 |
| B — Metadata / catalogue | 5 | 2 | 3 | 0 |
| C — Historical | 5 | 2 | 1 | 2 |
| D — Comparative | 3 | 0 | 1 | 2 |
| E — Aggregation / statistics | 3 | 0 | 0 | **3** |
| F — Yield-curve analysis | 3 | 0 | 3 | 0 |
| G — Portfolio / positions | 2 | 1 | 1 | 0 |
| H — Risk calculation | 6 | 5 | 1 | 0 |
| I — Domain explanation | 6 | 5 | 1 | 0 |
| J — Hybrid knowledge + data | 3 | 3 | 0 | 0 |
| K — Multi-step analytical | 2 | 1 | 1 | 0 |
| L — Clarification / elicitation | 5 | 5 | 0 | 0 |
| M — Ambiguous | 3 | 3 | 0 | 0 |
| N — Unsupported | 7 | 0 | 0 | **7** |
| O — Error / edge case | 4 | 0 | 1 | 3 |
| P — Conversational follow-up | 2 | 2 | 0 | 0 |
| — Small talk | 2 | 2 | 0 | 0 |

### Representative questions

**A — Basic data lookup** *(supported)*
> `Q-DATA-001` What is the current nominal Treasury par yield curve?
> `Q-DATA-003` Show me the real (TIPS) yield curve.

Full path, curve snapshot artifact, quoting basis carried in provenance.

**E — Aggregation** *(all unsupported, and worth knowing)*
> `Q-AGG-001` What is the average 10-year yield over the last year?

There is no aggregation anywhere in the agent path. `McpAgent.execute` returns a
snapshot or a history table; nothing computes a mean, and no MCP tool offers
one. A user would reasonably expect this to work. It does not.

**H — Risk calculation** *(supported, with deterministic ground truth)*
> `Q-RISK-001` What is the DV01 of the demo book?
> `Q-RISK-002` Compute the 10-day 99% historical VaR on the demo book.

`Q-RISK-002` is worth singling out: the stated horizon and confidence must reach
the engine, and the answer must describe the horizon that was **computed**, not
the one that was asked for.

**I — Domain explanation** *(supported, Qdrant only)*
> `Q-KNOW-002` How many observations does a historical VaR calculation read, and why?

Requires a verbatim quote from `market_risk/var`, verified against the retrieved
text before it is accepted.

**L — Elicitation** *(supported, the architecture's hardest path)*
> `Q-ELICIT-001` Give me the 30-year rate. → *nominal or real?*
> `Q-ELICIT-004` …answered with "30 year Treasury", then "whatever you think", then correctly.

`BC_30YEAR` and `TC_30YEAR` both exist, so the ambiguity is real, not contrived.

**N — Unsupported** *(the honesty tests)*
> `Q-UNSUP-001` What is the CVA on our counterparty exposure? — corpus knows it, data cannot support it
> `Q-UNSUP-006` What is the 15-year Treasury yield? — Treasury publishes no such tenor
> `Q-UNSUP-003` Show me EUR/USD FX rates. — wrong asset class entirely

These must produce no figure. The corpus *knowing* CVA makes it more dangerous,
not less: a model with the definition in context is exactly the situation where
a plausible number gets invented.

---

## 4. Known defects found by this exercise

Both were discovered by deriving questions from the data, both are reproduced by
a test, and **neither has been fixed** — they are reported here as findings.

### DEF-001 — the catalogue advertises tools that cannot be dispatched

`AGENT_ROUTING_BUG`. `McpAgent.catalogue()` advertises `get_yield_curve`,
`get_rate_history`, `get_curve_slope` and `list_series` as tools the domain
expert may name as a `calculation`. But `_calculate` dispatches only to
`RiskWorkflows` methods, which are `price_portfolio`, `compute_dv01`,
`compute_var`, `run_stress`. Naming `get_curve_slope` — the natural choice for
"what is the 2s10s slope?" — returns:

```
{"tool": "get_curve_slope", "error": "no workflow named 'get_curve_slope'"}
```

Affects `Q-CURVE-002`, `Q-CURVE-003`. Pinned by an `xfail(strict=True)` so a fix
flips the test rather than passing unnoticed.

### DEF-002 — a requirement cannot express a date range

`DATA_GAP`. MCP's `get_rate_history` accepts `start_date`/`end_date` and
`get_curve` accepts `observation_date`. `Requirement` carries only `rows`, so
`McpAgent._history` always reads the provider's default one-year window. **A
question about 2008 is answered with 2025–2026 data.** The row shortfall is
reported honestly; the date substitution is not.

Affects `Q-HIST-004`, `Q-HIST-005`. This is the more serious of the two: it is
silent.

---

## 5. How to use this catalog

```bash
# Deterministic — no model needed. Re-derives every fact from the live stores.
pytest tests/use_cases/test_question_catalog.py

# Representative slice through the running service on :8000.
pytest tests/use_cases/test_catalog_e2e.py

# Regenerate the coverage matrix after editing the catalog.
python tests/use_cases/build_coverage.py
```

If a store moves, the deterministic suite fails first and names the fact that
changed. That is the intended failure mode: a catalog that lies is worse than no
catalog.
