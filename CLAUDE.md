# semantic-mcp-data-access-gateway
Market-risk data foundation: official U.S. Treasury interest-rate publications,
acquired, validated and loaded into PostgreSQL with full lineage. The semantic
MCP gateway the repository is named for is not built yet — this is its data
layer.

## Pipeline

```
home.treasury.gov ──0_acquire──► data/raw + data/processed + data/metadata
                                          │
                                 1_provision (docker compose + migrate.py)
                                          ▼
                                 2_load ──► staging ─► treasury ─► analytics
                                          │
                                 3_verify ──► 58 checks, meta.reconciliation
```

Stage 0 never opens a database. Stages 1-3 never contact Treasury.

## Commands

```bash
# stage 0 - acquire source data (140 requests, ~60 MB, ~4 min)
python .claude/acquisition/download_us_treasury.py
python .claude/acquisition/download_us_treasury.py --dataset daily_treasury_yield_curve
python .claude/acquisition/download_us_treasury.py --refresh

# stage 1 - provision
docker compose up -d
python .claude/loading/migrate.py
python .claude/loading/migrate.py --status

# stage 2 - load
python .claude/loading/load_us_treasury.py

# stage 3 - verify. ALWAYS run before opening a PR
python tools/verify_load.py --self-test
```

Expected: `self-test OK: corruption detected ...` then
`Verification PASS: 58/58 checks passed`.

## Layout

| Path | What it holds |
|---|---|
| `.claude/agents/` | Agent definitions — the orchestrators |
| `.claude/skills/` | 4 skills: **what** each stage is and **when** to use it |
| `.claude/commands/` | `/db-setup`, `/db-refresh`, `/db-check` |
| `.claude/rules/` | Path-scoped instructions, loaded only when touching those files |
| `.claude/acquisition/` | **Product code.** Treasury downloader |
| `.claude/loading/` | **Product code.** Migration runner and loader |
| `db/migrations/` | V001-V007. Forward-only, checksummed |
| `data/` | Source of record: raw XML, processed CSVs, reports |
| `docs/` | Contracts and architecture decisions |
| `tools/` | `verify_load.py` — reconciliation with a self-test |

> `.claude/acquisition/` and `.claude/loading/` are the **deliverable**, not
> editor configuration. Do not delete `.claude/` assuming it is tooling.

## The rule everything rests on

**A missing observation is NULL. Never zero, never the previous day's rate,
never an interpolation.**

Absence of a rate and a rate of zero are different facts. Collapse them and you
get a curve that looks complete and is wrong, with nothing downstream able to
tell. Enforced at every layer: the downloader emits NULL, the loader writes no
row, and the schema has no default that could invent one.

The harder half: **an exact 0 is not automatically missing.** Short tenors
genuinely printed 0.00% in 2008-12, 2011, 2015 and 2020-21. Exactly one column
is a placeholder — `BC_30YEARDISPLAY`, a literal `0` on all 5,256 dates before
2011-01-03 — and that judgement lives in
`treasury.series.placeholder_zero_before`, as data, not code.

## Conventions

- **Preserve Treasury's terminology exactly.** `BC_1MONTH` stays `BC_1MONTH`.
  Renaming is how a discount rate ends up labelled a yield.
- **`data/raw/` is immutable.** Only `--refresh` replaces a whole file. Never
  patch one in place.
- **Never hardcode a field list.** Treasury has added six par maturities since
  1990. Parse what the feed returns.
- **Quoting basis is mandatory.** Every series declares `quote_basis`. A bill
  discount rate is not a yield; they must never share a curve.
- **Semantics live in the data.** Placeholder rules, exclusions and quoting
  bases are columns in `treasury.series`. Adding one is an `UPDATE`.
- **Fail loudly, mid-load.** An unmapped column aborts the run naming it. A
  half-loaded database reporting success is the worst available outcome.
- **Expectations are recounted from source.** A check that asks the database
  what it should contain proves nothing.
- **No financial transformation anywhere.** No returns, DV01, VaR, spreads,
  breakevens or bootstrapped curves. This repository ends at trustworthy facts.

## Adding a maturity Treasury has started publishing

The loader will already have stopped and named the column — it refuses to drop
one silently. Add the staging column and the `treasury.series` row in a **new**
migration, then re-run load and verify. Nothing else changes: the unpivot
discovers columns and holds no list.
Contract: @docs/loading-contract.md

## Never commit

`adaptive-legacy-code-complexity-harness/` is a **separate repository** sitting
inside this working directory with its own `.git`. It is in `.gitignore` and in
`.claude/settings.json`'s deny list and must stay in both. Committing it
produces a broken submodule reference or absorbs its history — neither is
cleanly recoverable once pushed.

## Before opening a PR

1. `python .claude/loading/migrate.py --status` — no unexpected pending
2. `python .claude/loading/load_us_treasury.py`
3. `python tools/verify_load.py --self-test`
4. Confirm `git status` shows no `adaptive-legacy-code-complexity-harness/`,
   no `.env`

There is no CI. These checks are manual and are the only thing standing between
a defect and `main`.
=======
Semantic MCP data access gateway for intent-aware request understanding, intelligent data
requirement planning, filtering, and optimized retrieval across enterprise data sources.

## Structure

This is a monorepo with three independent workstreams, each in its own top-level folder:

- **`chatbot/`** — Streamlit chatbot front-end with LangSmith observability. Sends user
  questions to the smart agent and renders the returned answer. See `chatbot/CLAUDE.md`.
- **Smart agent + vector database** — (folder TBD by owning teammate) resolves a question into
  the specific tools/data required and retrieves the answer.
- **MCP server + PostgreSQL** — (folder TBD by owning teammate) exposes tools/data sources over
  MCP, backed by Postgres in Docker.

Each subfolder has its own `CLAUDE.md` with implementation-specific context; this root file only
covers what's shared across all three.

## Cross-team contract

`chatbot` calls the smart agent over a simple REST contract:

```
POST {AGENT_API_URL}/chat
  { "query": "<user question>", "session_id": "<uuid>" }
  -> { "answer": "<text>", "sources": ["..."] }
```

This is an interim contract for the demo — treat it as negotiable, not fixed, if the agent/MCP
side needs a different shape.

## Conventions

- No Docker is assumed for local dev of `chatbot` — it's a plain Python app. Docker is used by
  the agent/MCP-server workstreams for Postgres.
- Each subfolder is expected to be runnable and testable independently of the others.
