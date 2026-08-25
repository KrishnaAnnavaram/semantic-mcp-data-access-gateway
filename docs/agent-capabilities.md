# Agent-reachable capabilities

Two inventories exist in this project and they are deliberately different sizes.

| | Count | What it is |
|---|---|---|
| **MCP-registered tools** | **42** on `risk-engine-mcp`, 14 on `market-risk-data-mcp` | The protocol surface. Callable by any MCP client, including `python -m mcp_servers.host --ask`. |
| **Agent-reachable capabilities** | **30 executable**, 4 informational | What the domain expert may schedule through `/chat`. |

They are not meant to match. A capability catalogue is something a planner
chooses from under uncertainty, and every entry it holds is one more chance to
choose wrong. Forty-two entries would buy a handful of rarely asked questions at
the cost of ambiguity on the common ones. So the 42 tools are classified, and
only what a market-risk user would genuinely ask for is advertised.

Reachability today: **34 of 42** risk tools are reached by some capability.
Eight are deliberately withheld - see the classification below.

---

## How a capability reaches the engine

```
user question
  -> POST /chat
  -> orchestrator           routes; the only agent a user reaches
  -> domain expert          plans, names ONE capability from available_calculations
  -> MCP agent              getattr(RiskWorkflows, name) and dispatches
  -> RiskWorkflows          adapter: prepare, retrieve, call, shape
  -> MCP host
  -> market-risk-data-mcp   curve, book, history, provenance
  -> risk-engine-mcp        the mathematics
  -> orchestrator           writes the reply
```

**The `ToolSpec` name is the `RiskWorkflows` method name.** That is an existing
project contract, not a convention: `McpAgent._calculate` resolves the
capability with `getattr`, so a name that does not resolve becomes a plan that
fails at the last step. Contract tests enforce it in both directions - nothing
advertised without an executor, and no executor left unreachable.

**`RiskWorkflows` is an adapter and computes nothing.** It prepares inputs,
calls the data server for market data, calls the risk server for mathematics and
shapes the reply. A test asserts this against the module's syntax tree:
arithmetic in a workflow method fails the build unless the method is on a short
allow-list of label formatting and calendar helpers.

**A required input is asked for, never assumed.** A capability whose description
says `NEEDS x` and does not receive `x` returns a structured `needs` block; the
MCP agent passes it up and the orchestrator asks. It does not substitute a
plausible value - a reverse stress that assumes a target loss answers a
different question with the same confidence as a right answer, and a
limit-breach capability that assumes a limit invents desk policy.

**And a required input must have somewhere to arrive from.** That is the other
half, and it was missing for every capability added here. `calculation_params`
is a closed schema on the domain expert's structured output; it declared
`confidence_level` and `horizon_days`, because VaR was once the only
parameterised calculation. A planner asked to run a bear steepener routed to
`run_rate_stress` perfectly and returned `calculation_params: {}` - there was no
legal field for `scenario` - and the adapter then asked for the scenario the
question had already named.

Nothing could see it from one side. The routing tests passed, because the
routing was right; the adapter tests passed, because an adapter handed a
scenario works. It lived in the seam between them, so the schema now declares
every parameter a capability reads, each `ToolSpec` names its own in a `PARAMS`
clause, and `tests/test_calculation_params_contract.py` checks the seam in both
directions - no required input without a declared home, no declared field that
nothing reads.

The schema stays **closed**. The fix for a closed schema missing a field is the
field: an open one would accept `scenarioo` just as willingly and lose it
silently at dispatch instead. Values are validated on the way through and
dropped rather than clamped, because rewriting a confidence level of 99 to 0.99
is a guess about the number the whole figure is defined by.

Three inputs are *not* declared and are filled by `McpAgent._calculate` from
what the requirement already holds: `curve_date` from `as_of_date`, and
`start_date`/`end_date`/`lookback_days` from the period the planner recorded in
`temporal`. Asking a planner to state the same date twice, once per
destination, invites it to state it once.

---

## The mapping

| Agent capability | Data MCP calls | Risk MCP tool(s) | Purpose |
|---|---|---|---|
| `price_portfolio` | `get_portfolio`, `get_curve` | `price_portfolio_tool` | present value of the demo book on a par curve |
| `compute_bond_analytics` | `get_portfolio`, `get_curve` | `compute_bond_analytics_tool` | per-bond valuation analytics - clean and dirty price, accrued interest, yield to maturity, current yield, Maca... |
| `compute_carry_roll` | `get_portfolio`, `get_curve` | `compute_carry_roll_tool` | what the book earns if the curve does not move - carry and roll-down, separately |
| `compute_curve_analytics` | `get_curve` | `compute_curve_analytics_tool` | curve shape - zero and forward rates, named spreads (2s5s, 2s10s, 5s10s, 5s30s, 10s30s), butterflies and inver... |
| `compute_rate_volatility` | `get_curve_history_matrix` | `compute_rate_volatility_tool` | realised volatility of published par yields, per tenor, with rolling windows and correlations |
| `compute_dv01` | `get_portfolio`, `get_curve` | `compute_dv01_tool`, `compute_key_rate_dv01_tool` | portfolio DV01 by full revaluation, with a key-rate breakdown |
| `compute_rate_sensitivities` | `get_portfolio`, `get_curve` | `compute_rate_sensitivities_tool` | the full sensitivity picture in one pass - DV01, key-rate DV01, maturity-bucket exposure, effective duration a... |
| `compute_risk_contributions` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compute_risk_contributions_tool` | component, marginal and incremental VaR or ES per position |
| `compute_concentration` | `get_portfolio`, `get_curve` | `compute_concentration_tool` | where risk is bunched up - largest positions, DV01 and key-rate concentration, maturity buckets, with shares a... |
| `run_stress` | `get_portfolio`, `get_curve`, `get_scenario` | `run_stress_tool` | revalue the book under a stored scenario or an explicit tenor shock vector |
| `run_rate_stress` | `get_portfolio`, `get_curve` | `run_rate_stress_tool`, `run_curve_twist_stress_tool`, `run_curve_curvature_stress_tool` | standard named interest-rate scenarios by full revaluation - parallel moves, bear/bull steepener, bear/bull fl... |
| `run_key_rate_stress` | `get_portfolio`, `get_curve` | `run_key_rate_stress_tool` | move exactly one curve node and leave every other node still |
| `run_shock_ladder` | `get_portfolio`, `get_curve` | `run_shock_ladder_tool` | portfolio P&L across a ladder of parallel shocks, with the duration-approximation error at each rung so convex... |
| `run_stress_matrix` | `get_portfolio`, `get_curve` | `run_stress_matrix_tool` | the whole standard scenario pack in one pass - parallel, steepeners, flatteners, twists, curvature and key-rat... |
| `compute_stress_contributions` | `get_portfolio`, `get_curve` | `compute_stress_contributions_tool` | decompose one stress loss across positions and across the curve, with the unexplained residual stated |
| `run_historical_stress` | `get_portfolio`, `get_curve` | `run_historical_crisis_stress_tool`, `run_historical_stress_tool` | replay a curve move that REALLY HAPPENED against today's book, by named crisis or by two dates. The shock is m... |
| `find_worst_historical_stresses` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `find_worst_historical_stresses_tool` | search observed history for the rate moves that would hurt today's book most, ranked, each fully revalued |
| `run_reverse_stress` | `get_portfolio`, `get_curve` | `run_reverse_stress_tool` | solve for the rate move that produces a stated loss. The LOSS is the input and the SHOCK is the answer - the o... |
| `compute_stress_thresholds` | `get_portfolio`, `get_curve` | `compute_stress_thresholds_tool` | the rate move needed to reach EACH of several loss levels, as a table |
| `find_limit_breach_stress` | `get_portfolio`, `get_curve` | `find_limit_breach_stress_tool` | the stress severity at which a stated loss LIMIT turns amber and then breaches |
| `compute_var` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compute_historical_risk_tool` | HISTORICAL-SIMULATION VaR and Expected Shortfall - observed past moves, full revaluation |
| `compute_parametric_risk` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compute_parametric_risk_tool` | PARAMETRIC (delta-normal) VaR and ES - a linear key-rate approximation under an assumed normal distribution, w... |
| `compute_monte_carlo_risk` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compute_monte_carlo_risk_tool` | MONTE CARLO VaR and ES - correlated simulated curve moves with full revaluation on every path, reproducible fr... |
| `compare_risk_methods` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compare_risk_methods_tool` | historical, parametric and Monte Carlo VaR and ES computed on identical inputs and shown side by side |
| `backtest_var` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `compute_historical_risk_tool`, `find_worst_historical_stresses_tool`, `backtest_var_tool` | judge whether a VaR forecast has been ACCURATE - exception count and dates, Kupiec unconditional coverage, Chr... |
| `compute_pnl_attribution` | `get_portfolio`, `get_curve` | `compute_pnl_attribution_tool` | explain P&L already earned - carry, roll-down, rate move, and the unexplained residual, which is always shown |
| `evaluate_risk_limits` | `get_portfolio`, `get_curve`, `get_curve_history_matrix` | `evaluate_risk_limits_tool`, `compute_dv01_tool`, `compute_historical_risk_tool`, `run_rate_stress_tool` | compare measured risk against limits the USER supplies, with utilisation, headroom and a GREEN/AMBER/RED statu... |
| `compare_portfolio_risk` | `get_portfolio`, `get_curve` | `compare_portfolio_risk_tool` | two EXISTING portfolios measured on identical inputs and differenced - PV, DV01, duration, convexity, key rate... |
| `analyze_hypothetical_trade` | `get_portfolio`, `get_curve` | `analyze_hypothetical_trade_tool` | incremental risk of ADDING a Treasury position - the book before and after, differenced. Nothing stored is mod... |
| `compute_frtb_girr` | `get_portfolio`, `get_curve` | `compute_frtb_girr_tool` | the FRTB standardised-approach GENERAL INTEREST RATE RISK charge (delta and curvature) for the supported Treas... |

---

## Classification of the 42 risk tools

**USER_FACING.** A market-risk user asks for these directly; each has an adapter
and a `ToolSpec`. Two capabilities fold several tools behind one name:
`run_rate_stress` dispatches to the parallel/template, twist and curvature
tools, and `run_historical_stress` dispatches to the plain replay or the
named-crisis tool.

**COMPOSITE_SUPPORT.** `compute_key_rate_dv01_tool` is reached inside
`compute_dv01` and `compute_rate_sensitivities`;
`run_historical_crisis_stress_tool` inside `run_historical_stress`. Useful, but
not a separate question.

**INTERNAL_ONLY, withheld.**

| Tool | Why withheld |
|---|---|
| `explain_stress_loss_tool` | Returns the same facts as `compute_stress_contributions_tool` in a different arrangement. Two names for one question is exactly the ambiguity to avoid. |
| `compare_stress_scenarios_tool` | `run_stress_matrix_tool` already returns its own ranked comparison. |

**SPECIALIZED, withheld.**

| Tool | Why withheld |
|---|---|
| `run_extreme_tail_simulation_tool` | Four tail methodologies behind one name; choosing between them needs a model-validation conversation, not a routing guess. |
| `run_volatility_regime_stress_tool` | A specific calibration of the Monte Carlo path. |
| `run_rate_correlation_stress_tool` | Isolating the correlation assumption is a research question. |
| `run_scenario_severity_pack_tool` | `run_stress_matrix` already covers ranked severity. |
| `run_concentration_stress_tool` | Sits between `compute_concentration` and `run_key_rate_stress`, and would be chosen instead of either. |
| `analyze_rate_hedge_tool` | Hedge sizing reads as advice. Available at the MCP layer for anyone who wants it. |

Every withheld tool remains fully callable through MCP directly and through
`python -m mcp_servers.host --ask`. Withheld means "not offered to the planner",
never "unavailable".

---

## Adding a capability

1. Add a method to `RiskWorkflows`. It may retrieve and shape; it may not
   calculate.
2. Add a `ToolSpec` with the **same name**, following the
   PURPOSE / USE WHEN / NOT WHEN / NEEDS / OPTIONAL / ASKS LIKE shape. The
   NOT WHEN clause must name the neighbouring capability it is confused with.
3. If it reads a parameter no capability reads yet, declare that parameter in
   `calculation_params` **and** validate it in
   `DomainExpertAgent._calculation_params`, then name it in the ToolSpec's
   `PARAMS` clause. All three: the schema makes it legal, the rebuilder makes
   it trustworthy, and the clause is what tells the planner it exists.
4. Add routing questions to `tests/use_cases/routing_catalog.json`.
5. Add the readable phrase to `agents/redaction.py` so the identifier cannot
   reach a user - including any new parameter name, which appears in a warning
   the reply is written from.

The contract tests then require the rest: dispatchability both ways, a
registered MCP tool behind the adapter, no silent default on a
declared-required input, a declared home for every required input, and routing
coverage for the new capability.

Full MCP surface and quantitative conventions:
[risk-tool-reference.md](risk-tool-reference.md).
