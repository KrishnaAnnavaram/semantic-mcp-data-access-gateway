# MCP contract

Two servers, fifty-six tools, one host. This is the API — treat it as one, not
as a collection of LLM-friendly functions.

Protocol revision **2026-07-28**, SDK `mcp>=2.0.0`. Transport is **stdio**: the
host launches each server as a child process.

---

## Topology

```
host (mcp/src/mcp_servers/host) — MCP host + client, the only component that reasons
  ├── stdio ──► market-risk-data-mcp   14 tools · 4 resources · 3 prompts
  │                └── PostgreSQL as mcp_reader (SELECT on analytics + demo)
  └── stdio ──► risk-engine-mcp        42 tools · 7 resources · 8 prompts
                   └── no database, no model, no network
```

Six boundaries, each enforced by mechanism rather than intent:

| Boundary | Enforced by |
|---|---|
| Only the host reasons | Neither server imports an LLM client |
| Only the data server reads PostgreSQL | The risk child's environment has no `DATABASE_URL`, no `POSTGRES_*`, no `MCP_READER_*` |
| `mcp_reader` cannot see raw tables | `REVOKE` on `treasury`/`staging`; views run with owner privileges |
| Only the risk engine calculates | The data server contains no pricing code |
| Bulk arrays bypass model context | Routed through the result's `_meta` channel |
| Real vs synthetic is unambiguous | `CHECK` constraints in `demo.*`, classification on every payload |

Verify the second one: `python -m mcp_servers.host --isolation`.

---

## The semantic envelope

Every rate the data server returns carries its meaning:

```json
{
  "series_code": "BC_10YEAR",
  "display_name": "10 Year Par Yield",
  "rate_kind": "nominal",
  "quote_basis": "par_coupon_semiannual",
  "tenor_label": "10 Year",
  "tenor_months": "120.0000",
  "observation_date": "2026-08-11",
  "rate_percent": "4.7000",
  "unit": "percent",
  "data_classification": "REAL_MARKET_DATA"
}
```

`quote_basis` is on **every** rate, not just the catalogue. On 2026-08-11 the
4-week bill quotes 3.64 bank-discount and 3.70 coupon-equivalent; both are
correct and they are not interchangeable. Carrying the basis makes mixing them
require ignoring an explicit label.

`tenor_months` is fractional. `BC_1_5MONTH` is genuinely 1.5 months and a 4-week
bill is 0.92; rounding to integer would merge distinct curve points.

Rates and money serialise as **decimal strings**, so nothing acquires binary
floating-point noise in transit.

Every result also carries an envelope with `dataset_snapshot_id` — a
content-addressed hash of the loaded source files. It changes if and only if the
data changes, so results may be cached against it. A Treasury restatement mints
a new id rather than silently reusing the old one.

---

## `market-risk-data-mcp`

| Tool | Purpose |
|---|---|
| `list_datasets` | Five datasets with coverage and **caveats** |
| `list_series` | Filter by dataset, kind, basis, tenor range; keyset paginated |
| `search_series` | "thirty year real" → `TC_30YEAR`. Deterministic, flags ambiguity |
| `get_series_coverage` | First/last/count per series |
| `get_curve` | Full par curve for one date |
| `get_rate_history` | ≤16 series over a range, paginated |
| `get_curve_history_matrix` | Aligned history for risk; **matrix in `_meta`** |
| `explain_number` | One value plus its Treasury file, URL and SHA-256 |
| `list_portfolios` · `get_portfolio` | The synthetic demo book |
| `list_scenarios` · `get_scenario` | Stress definitions |

Resources: `market-risk://catalog/datasets`, `catalog/series`,
`caveats/{data_key}`, `docs/data-contract`, `docs/provenance`.
Prompts: `curve_snapshot`, `explain_series`, `coverage_report`.

**Absent by design:** `run_sql`, and any parameter named `columns`, `table`,
`schema`, `order_by` or `where`. SQL templates live in `repository.py` and
caller input supplies values only. A SQL escape hatch would move schema
knowledge into the model's prompt and make row limits unenforceable — the
opposite of a semantic gateway. `verify_mcp.py` asserts none exists.

### Deliberate omissions

`get_latest_rates` — `get_curve(observation_date=null)` says the same thing and
keeps the model's tool-selection problem smaller.

`find_series` became `search_series`, matching on aliases and tokens rather than
a model. An LLM inside the data server would put reasoning on the wrong side of
the boundary and make identical queries return different answers on different
days.

### Limits

| | Default | Hard |
|---|---|---|
| History page | 500 | 2,000 |
| Series per history request | — | 16 |
| Catalogue page | 100 | 500 |
| History matrix | 250 days | 60–1,250 |

Exceeding a limit is `ROW_LIMIT_EXCEEDED`, never a silent truncation. A caller
who asked for 5,000 rows and got 2,000 without being told has a wrong answer,
not a partial one.

### Cursors

Self-contained and HMAC-signed. The protocol is stateless — there is no session
to hold a database cursor in — so the token carries `{v, tool, query_fingerprint,
last_key}`. It is rejected if the signature fails, if it is replayed against a
different tool, or if the filters changed since it was issued. Without the last
check, editing `series_codes` mid-scan would silently paginate a different
result set.

---

## Bulk routing: `_meta`

`get_curve_history_matrix` splits its answer in two.

```
structured_content  →  the model    789 bytes: shape, completeness, provenance
_meta               →  the host  16,730 bytes: the numeric matrix
```

A 250-day × 5-tenor history is 1,250 yields. The model does not reason over
individual yields — it decides *that* a history is needed and hands it to the
engine — so putting them in model context spends tokens to no purpose and
invites truncation. The summary still lets the model verify the request was
satisfied: days returned, tenors, point count, excluded dates, snapshot id.

**21× smaller**, and no rate is ever visible to a model.

---

## Missing data

`missing_policy` defaults to **`reject`**.

The 30-year has a genuine 994-business-day hole from 2002 to 2006 — the bond did
not exist. A 250-day VaR window spanning it, under an `intersection` policy,
silently drops those dates and returns a number computed from a different
history than the one requested. Nothing fails; the answer is just wrong.

So the default refuses, naming the count and offering the alternative.
`intersection` remains available and reports `excluded_dates` in the result.

---

## Errors

Two kinds, and the distinction matters. Malformed arguments stay **protocol
errors**. A well-formed request that cannot be satisfied is a **tool execution
error** — `is_error: true` with the structured error as JSON text — because the
spec says clients should feed those back to the model to self-correct.

So every error names the fix:

```json
{
  "error_code": "DATE_NO_DATA",
  "category": "DATA_AVAILABILITY",
  "retryable": true,
  "message": "No nominal curve was published on 2026-07-04. Treasury does not publish on weekends, federal holidays or Good Friday.",
  "suggested_action": "Retry with one of the nearest available dates, or set date_policy='previous' or 'next' to accept a shift explicitly.",
  "candidates": [{"observation_date": "2026-07-02"}, {"observation_date": "2026-07-07"}]
}
```

Codes: `UNKNOWN_SERIES`, `AMBIGUOUS_SERIES`, `UNKNOWN_DATASET`,
`UNKNOWN_PORTFOLIO`, `UNKNOWN_SCENARIO`, `DATE_NO_DATA`, `DATE_OUT_OF_RANGE`,
`INVALID_DATE_RANGE`, `ROW_LIMIT_EXCEEDED`, `INVALID_CURSOR`,
`INSUFFICIENT_HISTORY`, `CURVE_INCOMPLETE`, `MISSING_OBSERVATIONS`.

The SDK prefixes the text with `Error executing tool <name>: `; the JSON begins
at the first `{`.

---

## `risk-engine-mcp`

Forty-two tools in nine families. Every one takes the curve and the portfolio as
typed arguments; the engine holds no market data of its own. The complete
surface, with formulas, units and every sign convention, is
[risk-tool-reference.md](risk-tool-reference.md).

| Family | Tools | Returns |
|---|---|---|
| Valuation and bond analytics | `price_portfolio_tool`, `compute_bond_analytics_tool`, `compute_carry_roll_tool` | PV, the clean/dirty/accrued split, YTM, both duration families, convexity, carry and roll |
| Curve analytics | `compute_curve_analytics_tool`, `compute_rate_volatility_tool` | Zero rates, forwards, spreads, butterflies, inversion; realised rate volatility and covariance |
| Sensitivities | `compute_dv01_tool`, `compute_key_rate_dv01_tool`, `compute_rate_sensitivities_tool`, `compute_risk_contributions_tool` | DV01, key-rate DV01, buckets, and an explicit reconciliation block |
| Single-scenario stress | `run_stress_tool`, `run_rate_stress_tool`, `run_key_rate_stress_tool`, `run_curve_twist_stress_tool`, `run_curve_curvature_stress_tool`, `run_shock_ladder_tool` | Shocked value, P&L, and **always** the resolved shock vector |
| Stress suites | `run_stress_matrix_tool`, `compare_stress_scenarios_tool`, `compute_stress_contributions_tool`, `explain_stress_loss_tool`, `compute_stress_thresholds_tool`, `run_concentration_stress_tool`, `run_scenario_severity_pack_tool` | A ranked 21-scenario pack; position and tenor attribution with its residual |
| Historical stress | `run_historical_stress_tool`, `run_historical_crisis_stress_tool`, `find_worst_historical_stresses_tool` | Shocks **measured** from published curves, never stored |
| Reverse stress | `run_reverse_stress_tool`, `find_limit_breach_stress_tool` | The move that costs a stated amount, with convergence reported |
| Distribution risk | `compute_historical_risk_tool`, `compute_parametric_risk_tool`, `compute_monte_carlo_risk_tool`, `run_extreme_tail_simulation_tool`, `run_volatility_regime_stress_tool`, `run_rate_correlation_stress_tool`, `compare_risk_methods_tool`, `backtest_var_tool`, `compute_pnl_attribution_tool` | VaR and ES under four labelled methodologies; coverage tests; P&L decomposition |
| Portfolio and regulatory | `compute_concentration_tool`, `evaluate_risk_limits_tool`, `compare_portfolio_risk_tool`, `analyze_hypothetical_trade_tool`, `analyze_rate_hedge_tool`, `compute_frtb_girr_tool` | Concentration, limit utilisation, paired comparison, incremental trade risk, FRTB SA GIRR |

Resources: `risk://model/manifest`, `risk://methodology/curve-construction`,
`risk://scenarios/templates`, `risk://scenarios/historical-crises`,
`risk://methodology/risk-measures`, `risk://methodology/regulatory-girr`,
`risk://capability-gaps`.

Three rules govern the whole surface:

* **The shock vector always travels with the result.** A scenario whose shape
  cannot be inspected is a number nobody can check.
* **Nothing is silently approximated.** A convention the engine does not
  implement is refused by name, with the fix in the message.
* **An absent capability is absent, not zero.** `vega_capital` is `null`; a
  scenario the bootstrap refuses is listed as not run, with its reason.

Accepts **par yields only**. Passing bill discount rates as a curve is a
category error the input schema rejects.

Every result carries the model manifest and a reproducibility block:

```json
{
  "input_sha256": "...", "model_manifest_sha256": "...",
  "run_fingerprint": "4c5a0bc67ea6d09156ece7da45a09966",
  "portfolio_snapshot_sha256": "...", "market_snapshot_sha256": "...",
  "dataset_snapshot_id": "treasury-b075397a4af661cf"
}
```

The fingerprint hashes inputs **and** the manifest. Same inputs under a changed
quantile convention is a different calculation and must not collide with the
original.

`backtest_var_tool` was deliberately absent from v1 on the grounds that a
multi-thousand-day rolling computation is a different workload. It is present
now, and takes the forecast and outcome series as arguments rather than
generating them - so the workload stays with whoever owns the history, and the
engine stays a calculator.

---

## Verification

```bash
python tools/verify_mcp.py --self-test    # 35 checks; 3 canaries must be caught
python -m mcp_servers.host --isolation            # risk engine has no DB reachability
python -m mcp_servers.host --demo                 # full chain
```

The canaries are payloads that must be **rejected**: a rate missing
`quote_basis`, a leaked `BC_30YEARDISPLAY` placeholder, an unlabelled demo
position. A suite that has only ever passed is equally consistent with a suite
that cannot detect anything.
