---
paths:
  - "mcp/src/mcp_servers/data/**/*.py"
  - "mcp/src/mcp_servers/risk/**/*.py"
  - "mcp/src/mcp_servers/host/**/*.py"
  - "tools/verify_mcp.py"
  - "tests/test_sdk_contract.py"
  - "tests/test_risk_engine.py"
---

# Rules for the MCP layer

Two stdio servers and the host that drives them. Protocol revision **2026-07-28**,
SDK `mcp>=2.0.0`. Full contract: `docs/mcp-contract.md`. Numerical methodology:
`docs/risk-methodology.md`.

## All six primitives are live

Tools, resources and prompts flow client-to-server. Elicitation, roots and sampling
flow the other way, mid-call, and share one mechanism: a tool parameter annotated
`Annotated[T, Resolve(fn)]` is filled by running `fn` before the tool body, and `fn`
may return `Elicit[T]`, `ListRoots` or `Sample` instead of a value.

| Primitive | Implemented by |
|---|---|
| Elicitation | `search_series` — `'30 year'` spans BC_30YEAR and TC_30YEAR |
| Roots | `export_curve_csv` — writes only inside a client-granted directory |
| Sampling | `brief_dataset_caveat` — the data server has no model of its own |

On 2026-07-28 all three ride `InputRequiredResult` and are answered by **retrying the
original call** with `input_responses` + `request_state`. There is no server-initiated
`elicitation/create`, no `elicitationId`. SEP-2577 deprecated the *standalone
server-to-client request* and the client capability declarations around sampling and
roots — not the resolver path, which is the SDK's supported way to use them.

**Connect with `session.discover()`, never `session.initialize()`.** `initialize` is the
pre-2026 handshake and caps at 2025-11-25, where these three silently fall back to the
deprecated transport. `verify_mcp.py` asserts the negotiated revision.

**Never combine a `Resolve(...)` parameter with a hand-rolled `InputRequiredResult`
return on one tool.** A call has a single `input_responses`/`request_state` channel; the
two flows overwrite each other and the call can never converge. The SDK rejects it at
registration.

Resolver bodies **re-run on every round**, so they must be cheap and side-effect-free.
A resolver that returns a plain value asks nothing and costs no round trip — keep the
common path on that branch, or the feature becomes too expensive to leave switched on.

## stdout is the protocol channel

A stray `print()` in a server corrupts the JSON-RPC stream, and the failure
presents as a mysterious client disconnect rather than as an error. All
diagnostics go to **stderr**.

## Par yields are not zero rates

Treasury publishes a par curve and no zero-coupon curve. The risk engine
bootstraps discount factors before pricing anything. Using a 4.25% 10-year CMT
as a discount rate is the single most common way to get bond analytics wrong,
and it fails silently — prices look plausible and are off by an amount that
grows with maturity and slope.

The guard is `test_sloped_curve_par_bond_still_prices_to_par`. It uses a sloped
curve deliberately: on a flat curve, par-as-spot happens to give roughly the
right answer.

## The boundaries, and what enforces each

| Boundary | Mechanism |
|---|---|
| Only the host reasons | Neither server imports an LLM client; a server needing prose borrows the host's model via sampling |
| The server never picks a destination | `export_curve_csv` writes only inside a client-granted root, and refuses a name that would escape it |
| Only the data server reads PostgreSQL | The risk child's env has no `DATABASE_URL`, no `POSTGRES_*`, no `MCP_READER_*` |
| `mcp_reader` cannot see raw tables | `REVOKE` on `treasury`/`staging`; views run with owner privileges |
| Only the risk engine calculates | The data server contains no pricing code |
| Bulk arrays bypass model context | Routed through the result's `_meta` |
| Real vs synthetic is unambiguous | `CHECK` constraints in `demo.*`, classification on every payload |

`sanitised_env()` builds child environments by **allow-list, not deny-list**. A
deny-list silently leaks the next credential someone adds to `.env`.

## Non-negotiables

- **No `run_sql`, ever**, and no parameter named `columns`, `table`, `schema`,
  `order_by` or `where`. SQL templates live in `repository.py`; caller input
  supplies values only. `verify_mcp.py` asserts none exists.
- **`quote_basis` on every rate**, not just the catalogue.
- **Missing history is refused by default.** `intersection` is opt-in and must
  report `excluded_dates`. The 30-year has a real 994-business-day hole from
  2002–2006; silently dropping it changes any number computed from that window.
- **Bulk arrays go through `_meta`.** It is a context-efficiency channel, not a
  security boundary — nothing secret in it.
- **Numerical conventions are versioned** in `mcp/src/mcp_servers/risk/manifest.py`.
  Changing the quantile rule changes the run fingerprint, by design.
- **Limits are refusals, not truncations.** Exceeding one is `ROW_LIMIT_EXCEEDED`.
  A caller who asked for 5,000 rows and silently got 2,000 has a wrong answer,
  not a partial one.

## Errors are part of the contract

Malformed arguments stay protocol errors. A well-formed request that cannot be
satisfied is a **tool execution error** — `is_error: true` with structured JSON —
because clients feed those back to the model to self-correct. Every error must
name its own fix: candidate dates, a suggested `date_policy`, an alternative
series.

## Verify

```bash
python tools/verify_mcp.py --self-test   # 48 checks; 4 canaries MUST be caught
python -m mcp_servers.host --isolation
python -m mcp_servers.host --demo
python -m mcp_servers.host --primitives   # all six, with a client that answers
```

The three client-directed primitives cannot be checked through the in-process
`server.call_tool()` the rest of the verifier uses — without a request context a
resolver cannot run, and every one of them fails with "Context is not available outside
of a request". That is a fact about the harness, not the contract, so those checks spawn
real child processes and answer from a preset written down in the verifier.

The canaries are payloads that must be **rejected**: a rate missing
`quote_basis`, a leaked `BC_30YEARDISPLAY` placeholder, an unlabelled demo
position. A suite that has only ever passed is equally consistent with a suite
that cannot detect anything.
