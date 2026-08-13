@AGENTS.md

# semantic-mcp-data-access-gateway

Semantic MCP gateway for intent-aware request understanding, data-requirement planning, and
optimised retrieval over enterprise data. Today's domain is U.S. Treasury interest rates.

Per-layer conventions live in `.claude/rules/` and load when you touch that layer's files.
This file holds only what applies to every session.

Seven subagents in `.claude/agents/` mirror the tiers, one per concern —
`acquisition-agent`, `database-agent`, `mcp-agent`, `backend-agent`, `frontend-agent`,
`knowledge-author`, `verification-agent`. Each states what it must **not** do, because the
boundaries between tiers are the part worth protecting.

## Four layers, one road between them

```
  user ─► frontend/          Streamlit + LangSmith            AGENT_BACKEND=rest
            │ POST /chat
            ▼
          agents/            orchestrator → domain expert ⇄ mcp agent
            │                              (Qdrant knowledge)
          backend/           /chat service, seams, workflows
            │ DataProvider seam                             DATA_BACKEND=mcp
            ▼
          mcp/               market-risk-data-mcp ──┐   as mcp_reader
                             risk-engine-mcp        │   no DB, no LLM
            │                                       ▼
          postgres/ + data/  PostgreSQL 17, Treasury rates
```

One directory per runtime tier, dependencies strictly downward. Three are installable
distributions; the frontend is a Streamlit app run in place.

| Directory | Distribution | Import package |
|---|---|---|
| `postgres/` | `treasury-db` | `treasury_db` — migrations, loader, DB access |
| `mcp/` | `mcp-servers` | `mcp_servers` — `.data`, `.risk`, `.host` |
| `backend/` | `gateway-backend` | `backend` — `.api`, `.agent`, `.knowledge`, `.providers` |
| `frontend/` | — | Streamlit app |
| `data/` | — | source of record, plus the `acquisition/` that fills it |
| `knowledge/` | — | RAG corpus the vector store ingests |

The MCP package is `mcp_servers`, deliberately **not** `mcp` — that name belongs to the MCP
SDK on PyPI, and shadowing it breaks every server with an import error that looks like a
corrupted install.

All four tiers are wired and verified end to end. The reasoning layer decides *what data a
question needs*; the data layer is *where that truthfully lives*; the MCP layer is *the only
road between them*; the UI is *how a human sees the answer and how it was reached*.

`DataProvider` has three implementations, chosen by `DATA_BACKEND`:

| Value | Route | Trade-off |
|---|---|---|
| `mcp` | both MCP servers as `mcp_reader` | privilege boundary holds; risk engine included |
| `postgres` | direct psycopg2 as owner | fewer moving parts; agent can write to the source of record |
| `mock` | synthetic, Treasury-shaped | no database needed |

## Setup

```bash
python tools/setup.py                # fresh system, end to end
python tools/setup.py --check        # report state, change nothing
```

Or by hand:

```bash
pip install -r requirements.txt
pip install -e ./postgres -e ./mcp -e ./backend
```

All three must be installed — they import each other (`backend` uses `mcp_servers`, the
data server uses `treasury_db`). **There are no `sys.path` hacks anywhere; do not add one.**
Modules find the repo root by walking up for a marker (`paths.py` in each package), never by
counting `parents[N]` — three packages sit at three depths and a count is wrong the moment a
file moves.

**`.claude/` holds both configuration and the four source distributions.** Configuration
lives in `agents/`, `commands/`, `rules/`, `skills/` and `settings.json`; product code lives
under ``. This is unusual — most tooling assumes `.claude/` is configuration only
— so the split is a rule rather than a convention: nothing outside `` is
importable code, and nothing inside it is Claude Code configuration.

## Commands

**Data layer**

```bash
python data/acquisition/download_us_treasury.py   # ~140 requests, ~60 MB, ~4 min
docker compose up -d postgres
python -m treasury_db.migrate                     # --status to inspect
python -m treasury_db.load
python tools/verify_load.py --self-test           # ALWAYS before a PR
```

Expected: `self-test OK: corruption detected …` then `Verification PASS: 74/74 checks passed`.

**MCP layer** — two stdio servers plus the host that drives them

```bash
python -m mcp_servers.data.bootstrap     # once: set the mcp_reader password
python -m mcp_servers.host --tools       # discover both servers' tools
python -m mcp_servers.host --demo        # curve -> price -> DV01 -> VaR -> stress
python -m mcp_servers.host --isolation   # prove the risk engine cannot reach the database
python -m mcp_servers.host --primitives  # exercise all six MCP primitives
python -m mcp_servers.host --ask "..."   # the host's own agent, driving both servers
python tools/verify_mcp.py --self-test   # 48 checks; 4 canaries must be caught
pytest                                   # 68 tests (frontend: cd frontend && pytest)
```

## All six MCP primitives are live

Protocol revision **2026-07-28**, SDK `mcp>=2.0.0`. Three primitives flow client-to-server;
three flow the other way, mid-call.

| Primitive | Where it lives | What it does here |
|---|---|---|
| **Tools** | both servers | 14 data tools, 5 risk tools |
| **Resources** | both servers | catalogues, caveats, provenance, risk methodology |
| **Prompts** | both servers | recommended tool orderings, as slash-commands |
| **Elicitation** | `search_series` | `'30 year'` matches BC_30YEAR *and* TC_30YEAR — the server asks rather than picking |
| **Roots** | `export_curve_csv` | the client grants a directory; the server writes only inside it |
| **Sampling** | `brief_dataset_caveat` | the data server has no model, so it borrows the host's |

The last three share one mechanism: a tool parameter annotated
`Annotated[T, Resolve(fn)]` is filled by running `fn` before the tool body, and `fn` may
return `Elicit[T]`, `ListRoots` or `Sample` instead of a value. The framework then returns an
`InputRequiredResult`, and the client answers by **retrying the original call** with
`input_responses` + `request_state` (MRTR). `McpHost.call` runs that retry loop, so the
provider seam and the reasoning agent never see it.

**The host must connect with `session.discover()`, not `session.initialize()`.** `initialize`
is the pre-2026 handshake and negotiates at most 2025-11-25, on which those three fall back to
deprecated standalone server-to-client requests. `discover()` is the stateless 2026-07-28
entry point. `verify_mcp.py` asserts the negotiated revision so this cannot regress silently.

Servers are never run by hand — the host launches them as child processes. If you do run one,
**stdout is the protocol channel**: a stray `print()` corrupts the stream and shows up as a
mysterious client disconnect. Diagnostics go to stderr.

**Reasoning + UI**

```bash
docker compose up -d qdrant
python -m backend.knowledge.knowledge_base   # ingest; no API key needed
python -m backend.api.service                # POST /chat on :8000
cd frontend && streamlit run app.py                               # :8501
python -m evaluation.run                     # 13 cases x 11 scorers, offline table
```

There is no CLI for the agents. `/chat` is the only entry point, deliberately —
a second path is a second thing to keep in step, and the first one to drift.
Use `python -m mcp_servers.host --ask "..."` to exercise the MCP layer alone.

Re-ingest after editing any knowledge doc:

```bash
python -c "from backend.knowledge.knowledge_base import KnowledgeBase; KnowledgeBase(rebuild=True)"
```

Set `AGENT_BACKEND=rest` in `frontend/.env` or the UI silently serves canned mock answers, and
raise `AGENT_TIMEOUT_SECONDS` — one turn runs several MCP round trips behind an Opus loop, and
the 30s default expires mid-answer.

## The rule everything rests on

**A missing observation is NULL. Never zero, never the previous day's rate, never an
interpolation.**

Absence of a rate and a rate of zero are different facts. Collapse them and you get a curve that
looks complete and is wrong, with nothing downstream able to tell. Enforced at every layer: the
downloader emits NULL, the loader writes no row, the schema has no default that could invent one.

The harder half: **an exact 0 is not automatically missing.** Short tenors genuinely printed
0.00% in 2008-12, 2011, 2015 and 2020-21. Exactly one column is a placeholder —
`BC_30YEARDISPLAY`, a literal `0` on all 5,256 dates before 2011-01-03 — and that judgement lives
in `treasury.series.placeholder_zero_before`, as data, not code.

## Conventions that cross every layer

- **Preserve Treasury's terminology exactly.** `BC_1MONTH` stays `BC_1MONTH`. Renaming is how a
  discount rate ends up labelled a yield.
- **Quoting basis is mandatory** and travels with every rate, not just the catalogue. A bill
  discount rate is not a par yield; they must never share a curve.
- **Semantics live in the data**, not in code. Placeholder rules, exclusions and quoting bases are
  columns in `treasury.series`. Adding one is an `UPDATE`, not a release.
- **Never hardcode a field list.** Treasury has added six par maturities since 1990. Parse what
  the feed returns.
- **Fail loudly.** A half-loaded database reporting success is the worst available outcome.
- **Expectations are recounted from source.** A check that asks the database what it should
  contain proves nothing.
- **Keep the seams.** The agent talks only to interfaces — `VectorStore` and `DataProvider` must
  stay swappable. Never let it import a concrete engine directly.
- **Model:** default to `claude-opus-5` with adaptive thinking. Do not downgrade unless asked.

## Adding a maturity Treasury has started publishing

The loader will already have stopped and named the column — it refuses to drop one silently. Add
the staging column and the `treasury.series` row in a **new** migration, then re-run load and
verify. Nothing else changes: the unpivot discovers columns and holds no list.
Contract: @docs/loading-contract.md

## Never commit

`adaptive-legacy-code-complexity-harness/` is a **separate repository** sitting inside this
working directory with its own `.git`. It is in `.gitignore` and in `.claude/settings.json`'s
deny list and must stay in both. Committing it produces a broken submodule reference or absorbs
its history — neither is cleanly recoverable once pushed.

## Before opening a PR

1. `python -m treasury_db.migrate --status` — no unexpected pending
2. `python -m treasury_db.load`
3. `python tools/verify_load.py --self-test` — 74/74
4. `python tools/verify_mcp.py --self-test` — 48/48 (spawns real child processes)
5. `pytest` — 68 passed (plus `cd frontend && pytest` — 4 passed)
6. `git status` shows no `adaptive-legacy-code-complexity-harness/`, no `.env`
7. **`git grep -nE '^(<<<<<<<|=======|>>>>>>>)' -- ':!data/'` returns nothing.** Conflict markers
   have reached `main` once already, in four files, breaking `pip install` for everyone.

There is no CI. These checks are manual and are the only thing between a defect and `main`.

## Merging

`main` requires a pull request and **2 approving reviews from reviewers who hold write access**.
An approval from someone with only read access, or whose collaborator invitation is still
pending, shows in the approval count but does **not** satisfy the rule — check
Settings → Collaborators before assuming a review counts.
