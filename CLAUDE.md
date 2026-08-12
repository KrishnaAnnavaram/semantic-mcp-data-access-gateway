# semantic-mcp-data-access-gateway

Project memory for Claude Code working in this repository. Read this first.

Semantic MCP data access gateway for intent-aware request understanding, intelligent data
requirement planning, filtering, and optimized retrieval across enterprise data sources.

## One gateway, three layers

```
   user ──► UI LAYER          chatbot/                    Streamlit + LangSmith
              │
              ▼
            REASONING LAYER   src/ + knowledge/           SmartAgent (Claude) + ChromaDB
              │
              ▼  ⚠ DataProvider is still a mock — this seam is not connected yet
            DATA LAYER        .claude/ + db/ + data/      PostgreSQL 17, Treasury rates
```

The reasoning layer decides *what data a question needs*; the data layer is *where that data
truthfully lives*; the UI layer is *how a human sees the answer and how it was reached*.

Each layer is built and runnable on its own. **They are not wired together yet.** The seam that
joins reasoning to data is `DataProvider` in `src/data_provider.py`, currently a mock.
Connecting it to `analytics.v_observation` is the next piece of work and touches one file.

| Layer | Owns | Status | Its own docs |
|---|---|---|---|
| `chatbot/` | Streamlit chat UI + LangSmith | In progress | `chatbot/CLAUDE.md` |
| `src/` + `knowledge/` | Smart agent + vector knowledge base | Built (Phases 3–4) | this file |
| `.claude/` + `db/` + `data/` | Treasury data foundation | Built and verified | `docs/` |

## Commands

```bash
pip install -r requirements.txt        # one venv at the root serves all three layers
```

**Data layer**

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

Expected: `self-test OK: corruption detected ...` then `Verification PASS: 58/58 checks passed`.

**MCP layer** — two stdio servers plus the host that drives them

```bash
python -m src.mcp_data.bootstrap       # once: set the mcp_reader password
python -m src.host --tools             # discover both servers' tools
python -m src.host --demo              # full chain: curve -> price -> DV01 -> VaR -> stress
python -m src.host --isolation         # prove the risk engine cannot reach the database
python tools/verify_mcp.py --self-test # 35 checks; 3 canaries must be caught
pytest tests/                          # SDK contract + risk-engine golden tests
```

The servers are never run by hand — the host launches them as child processes
over stdio. If you do run one directly, remember **stdout is the protocol
channel**: a stray `print()` corrupts the stream and the failure looks like a
mysterious client disconnect. Diagnostics go to stderr.

**Reasoning layer**

```bash
python src/knowledge_base.py           # Phase 3 only, no API key needed
$env:ANTHROPIC_API_KEY = "sk-ant-..."  # Phases 3+4 live
python demo.py
```

Re-ingest after changing any knowledge doc:

```bash
python -c "import sys; sys.path.insert(0,'src'); from knowledge_base import KnowledgeBase; KnowledgeBase(rebuild=True)"
```

**UI layer**

```bash
cd chatbot && cp .env.example .env && streamlit run app.py
```

## Layout

| Path | What it holds |
|---|---|
| `.claude/agents/` | Agent definitions — the orchestrators |
| `.claude/skills/` | Stage skills: **what** each is and **when** to use it |
| `.claude/commands/` | `/db-setup`, `/db-refresh`, `/db-check` |
| `.claude/rules/` | Path-scoped instructions, loaded only when touching those files |
| `.claude/acquisition/` | **Product code.** Treasury downloader |
| `.claude/loading/` | **Product code.** Migration runner and loader |
| `db/migrations/` | V001–V007. Forward-only, checksummed |
| `data/` | Source of record: raw XML, processed CSVs, reports |
| `docs/` | Data-layer contracts and architecture decisions |
| `tools/` | `verify_load.py`, `verify_mcp.py` — reconciliation, each with a self-test |
| `src/mcp_data/` | **Product code.** market-risk-data-mcp: 12 tools, read-only |
| `src/mcp_risk/` | **Product code.** risk-engine-mcp: curves, pricing, VaR. No DB, no LLM |
| `src/host/` | **Product code.** MCP host + client; launches both servers over stdio |
| `src/` (rest) | VectorStore, KnowledgeBase, DataProvider, SmartAgent |
| `knowledge/<domain>/*.md` | RAG source docs. **Subfolder name = domain tag** |
| `chatbot/` | Streamlit UI, its own README and CLAUDE.md |
| `chroma_db/` | Local vector store, auto-created — do not edit by hand |

> `.claude/acquisition/` and `.claude/loading/` are the **deliverable**, not editor
> configuration. Do not delete `.claude/` assuming it is tooling.

## Cross-layer contract

`chatbot` calls the smart agent over a simple REST contract:

```
POST {AGENT_API_URL}/chat
  { "query": "<user question>", "session_id": "<uuid>" }
  -> { "answer": "<text>", "sources": ["..."] }
```

Interim contract for the demo — treat it as negotiable, not fixed, if the agent side needs a
different shape.

## The rule everything rests on (data layer)

**A missing observation is NULL. Never zero, never the previous day's rate, never an
interpolation.**

Absence of a rate and a rate of zero are different facts. Collapse them and you get a curve that
looks complete and is wrong, with nothing downstream able to tell. Enforced at every layer: the
downloader emits NULL, the loader writes no row, and the schema has no default that could invent
one.

The harder half: **an exact 0 is not automatically missing.** Short tenors genuinely printed
0.00% in 2008-12, 2011, 2015 and 2020-21. Exactly one column is a placeholder —
`BC_30YEARDISPLAY`, a literal `0` on all 5,256 dates before 2011-01-03 — and that judgement
lives in `treasury.series.placeholder_zero_before`, as data, not code.

## Conventions — data layer

- **Preserve Treasury's terminology exactly.** `BC_1MONTH` stays `BC_1MONTH`. Renaming is how a
  discount rate ends up labelled a yield.
- **`data/raw/` is immutable.** Only `--refresh` replaces a whole file. Never patch one in place.
- **Never hardcode a field list.** Treasury has added six par maturities since 1990. Parse what
  the feed returns.
- **Quoting basis is mandatory.** Every series declares `quote_basis`. A bill discount rate is
  not a yield; they must never share a curve.
- **Semantics live in the data.** Placeholder rules, exclusions and quoting bases are columns in
  `treasury.series`. Adding one is an `UPDATE`.
- **Fail loudly, mid-load.** An unmapped column aborts the run naming it. A half-loaded database
  reporting success is the worst available outcome.
- **Expectations are recounted from source.** A check that asks the database what it should
  contain proves nothing.
- **No financial transformation in this layer.** No returns, DV01, VaR, spreads, breakevens or
  bootstrapped curves. The data layer ends at trustworthy facts; those calculations belong to the
  reasoning layer.

## Conventions — MCP layer

- **Par yields are not zero rates.** Treasury publishes a par curve and no
  zero-coupon curve. The risk engine bootstraps discount factors before pricing
  anything; using a 4.25% 10-year CMT as a discount rate is the most common way
  to get bond analytics wrong, and it fails silently.
- **`quote_basis` travels with every rate**, not just the catalogue. A bill
  discount rate and a par coupon yield are different quantities.
- **No `run_sql`, ever.** SQL templates live in `repository.py`; caller input
  supplies values only.
- **The risk engine gets no database credential.** Its child process is launched
  with a sanitised environment. That is what makes "bad input or bad maths?" a
  question with a mechanical answer.
- **Bulk arrays go through `_meta`**, never model context. `_meta` is a
  context-efficiency channel, not a security boundary — nothing secret in it.
- **Missing history is refused by default.** `intersection` must report
  `excluded_dates`.
- **Numerical conventions are versioned**, in `src/mcp_risk/manifest.py`.
  Changing the quantile rule changes the run fingerprint, by design.

## Conventions — reasoning layer

- **Model:** default to `claude-opus-5` with adaptive thinking. Do not downgrade without being
  asked.
- **Knowledge docs** follow a fixed house style — see the `risk-analysis` skill in
  `.claude/skills/`. Every doc: Definition → Formula (dry) → Data required (naming the risk
  tables) → Notes. Concise and accurate.
- **Adding a domain** = new subfolder under `knowledge/` + docs; ingest picks it up
  automatically. Add the domain to `DOMAINS` in `src/smart_agent.py`.
- **Keep the seams.** The agent talks only to interfaces — do not let it import a concrete engine
  directly. `VectorStore` (ChromaDB now, `PgVectorStore` later) and `DataProvider` (mock now,
  PostgreSQL-backed later) must stay swappable.
- **Don't invent risk data.** The mock lives in `src/data_provider.py`; real data arrives through
  the `DataProvider` seam.
- **Don't bloat the knowledge base** — add only risk-analysis-essential docs.

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

1. `python .claude/loading/migrate.py --status` — no unexpected pending
2. `python .claude/loading/load_us_treasury.py`
3. `python tools/verify_load.py --self-test`
4. Confirm `git status` shows no `adaptive-legacy-code-complexity-harness/`, no `.env`
5. **`git grep -nE '^(<<<<<<<|=======|>>>>>>>)' -- ':!data/'` returns nothing.** Conflict markers
   have reached `main` once already, in four files, breaking `pip install` for everyone.

There is no CI. These checks are manual and are the only thing standing between a defect and
`main`.

## Merging

`main` requires a pull request and **2 approving reviews from reviewers who hold write access**.
An approval from someone with only read access, or whose collaborator invitation is still
pending, shows in the approval count but does **not** satisfy the rule — check
Settings → Collaborators before assuming a review counts.
