# semantic-mcp-data-access-gateway

Semantic MCP data access gateway for intent-aware request understanding, intelligent data
requirement planning, filtering, and optimized retrieval across enterprise data sources.

Instead of a client blindly calling every tool an MCP server exposes, this project adds an AI
layer that reads the incoming question, consults a knowledge base of what each tool and data
source is actually for, and invokes only what is needed to answer it.

---

## One gateway, three layers

```
            ┌─────────────────────────────────────────────┐
   user ───►│  UI LAYER          chatbot/                 │  Streamlit chat +
            │                    chat left, trace right   │  LangSmith tracing
            └──────────────────────┬──────────────────────┘
                                   │  question
                                   ▼
            ┌─────────────────────────────────────────────┐
            │  REASONING LAYER   src/ + knowledge/        │  SmartAgent (Claude)
            │                    ChromaDB vector store    │  + decision trace
            └──────────────────────┬──────────────────────┘
                                   │  "I need these rates"
                                   ▼   ⚠ DataProvider is still a mock
            ┌─────────────────────────────────────────────┐
            │  DATA LAYER        .claude/ db/ data/       │  PostgreSQL 17
            │                    Treasury → PostgreSQL    │  267,517 observations
            └─────────────────────────────────────────────┘
```

The reasoning layer decides *what data a question needs*; the data layer is *where that data
truthfully lives*; the UI layer is *how a human sees both the answer and how it was reached*.

**The layers are not wired together yet.** Each is built and runnable on its own, and the seam
between reasoning and data — `DataProvider` — is deliberately a mock. Replacing that mock with a
provider that reads the PostgreSQL tables below is the next piece of work, and it is a change to
one file rather than to the agent.

| Layer | Owns | Status |
|---|---|---|
| [`chatbot/`](chatbot/) | Streamlit chat UI + LangSmith observability | In progress |
| [`src/`](src/) + [`knowledge/`](knowledge/) | Smart agent + vector knowledge base | Built (Phases 3–4) |
| [`.claude/`](.claude/) + [`db/`](db/) + [`data/`](data/) | Treasury data foundation in PostgreSQL | **Built and verified** |

Each area is runnable and testable on its own. `chatbot/` carries its own `README.md` and
`CLAUDE.md`; the data layer is documented in [`docs/`](docs/); the root
[`CLAUDE.md`](CLAUDE.md) is the shared project memory.

---

## Getting started

One venv at the root serves all three layers.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Then work in whichever layer you own.

### Data layer — Treasury → PostgreSQL

```bash
cp .env.example .env          # set a real POSTGRES_PASSWORD
docker compose up -d
python .claude/loading/migrate.py
python .claude/loading/load_us_treasury.py
python tools/verify_load.py --self-test
```

```
self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
Verification PASS: 58/58 checks passed
```

### Reasoning layer — knowledge base and agent

```bash
python src/knowledge_base.py           # Phase 3 only, no API key needed

$env:ANTHROPIC_API_KEY = "sk-ant-..."  # Phases 3+4 end to end
python demo.py
python demo.py "What is my RWA against GLOBEX?"
```

### UI layer — chatbot

```bash
cd chatbot
cp .env.example .env
streamlit run app.py
```

---

# Data layer — Treasury market-risk foundation

36 years of official U.S. Treasury interest-rate data, acquired from `home.treasury.gov`,
validated, and loaded into PostgreSQL with row-level lineage. A clone plus four commands yields
a verified database.

## Four stages

```
  home.treasury.gov
        │
        ▼
┌──────────────────┐   agent: treasury-acquisition
│  0. ACQUIRE      │   .claude/acquisition/download_us_treasury.py
└──────────────────┘   140 GETs · one immutable XML per dataset-year · SHA-256
        │
        ▼  data/raw/  data/processed/  data/metadata/
        │                                  contract: docs/data-contract.md
┌──────────────────┐   agent: treasury-database-loader
│  1. PROVISION    │   docker compose up -d ; .claude/loading/migrate.py
└──────────────────┘   PostgreSQL 17 · V001–V007 · forward-only, checksummed
        │
┌──────────────────┐
│  2. LOAD         │   .claude/loading/load_us_treasury.py
└──────────────────┘   COPY → staging · generic unpivot → treasury · lineage → meta
        │
        ▼  52 series · 267,517 observations
        │                               contract: docs/loading-contract.md
┌──────────────────┐
│  3. VERIFY       │   tools/verify_load.py --self-test
└──────────────────┘   58 checks · expectations recounted from the CSVs
```

**Stage 0 never opens a database connection. Stages 1–3 never contact Treasury.** That line is
why a wrong number can always be localised: if staging matches the CSV and the CSV matches the
raw XML, the load is not at fault.

## The data

| Dataset | Data key | Range | Series | Observations |
|---|---|---|---|---|
| Par Yield Curve | `daily_treasury_yield_curve` | 1990-01-02 → 2026-08-11 | 15 | 108,339 |
| Bill Rates | `daily_treasury_bill_rates` | 2002-01-02 → 2026-08-11 | 28 | 105,204 |
| Long-Term Rates | `daily_treasury_long_term_rate` | 2000-01-03 → 2026-08-11 | 3 | 19,965 |
| Par Real Yield Curve | `daily_treasury_real_yield_curve` | 2003-01-02 → 2026-08-11 | 5 | 27,354 |
| Real Long-Term Rates | `daily_treasury_real_long_term` | 2000-01-03 → 2026-08-11 | 1 | 6,655 |
| **Total** | | | **52** | **267,517** |

140 raw files · 0 failed downloads · 0 unexplained business-day gaps · 64 MB.

Source: **U.S. Department of the Treasury** only. No Kaggle, no FRED, no Yahoo, no mirror — not
even for a single missing day.

Four schemas: `meta` (lineage), `staging` (CSV mirror), `treasury` (normalised core),
`analytics` (views only). **Consumers query `analytics`** — that is where the source traps are
already excluded. Full reference: [docs/database-schema.md](docs/database-schema.md).

```sql
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;
```

```
 observation_date |  m1  | m1_5 |  m2  |  m3  |  m6  |  y1  |  y2  |  y10 |  y30
------------------+------+------+------+------+------+------+------+------+------
 2026-08-11       | 3.79 | 3.82 | 3.83 | 3.89 | 3.99 | 4.03 | 4.22 | 4.70 | 5.24
```

## The rule everything rests on

**A missing observation is NULL. Never zero, never the previous day's rate, never an
interpolation.**

Absence of a rate and a rate of zero are different facts about the world. Collapse them and you
get a curve that looks complete and is wrong, with nothing downstream able to tell the
difference.

The harder half is the mirror image: **an exact 0 is not automatically missing.** Short Treasury
tenors genuinely printed 0.00% in 2008-12, 2011, 2015 and 2020-21 — erasing those would delete
the zero-rate era.

Exactly one column is a placeholder. Treasury publishes `BC_30YEARDISPLAY` as a literal `0` on
all **5,256** dates from 1990-01-02 to 2010-12-31. Loaded naively it puts a 0% thirty-year yield
into 21 years of history — and because every other point on the curve is correct, the result
looks entirely plausible. It is stored with a NULL rate, the published `0` retained for audit,
and excluded from every analytics view. The rule lives in
`treasury.series.placeholder_zero_before` — as data, not code.

## Quoting basis is part of the schema

A bill discount rate and a par coupon yield are different quantities. On 2026-08-11 the 4-week
bill quotes **3.64** on a bank-discount actual/360 basis and **3.70** coupon-equivalent. Stored
as bare numbers in adjacent columns they look interchangeable, and eventually someone plots them
on one curve — a mistake that survives review because each number is individually correct.

Every series therefore declares a non-null `quote_basis`. Making that mistake now requires
ignoring an explicit label.

## Audited, not asserted

Every expected value in the verifier is **recounted from the processed CSVs**. The database is
never asked what it should contain — a check that compares a database count to a database count
passes on a database that is entirely wrong.

`--self-test` adds 1.25 to one stored rate inside a transaction, requires the value check to
**fail**, then rolls back and confirms the original is restored. A suite that has only ever
reported PASS is equally consistent with a suite that cannot detect anything.

---

# Reasoning layer — knowledge base and smart agent

A server-side agent for quantitative risk analysis, grounded in a vector-database knowledge
layer. It understands intent, retrieves the right quant knowledge, decides which risk data it
actually needs, fetches only that, and answers — emitting a decision trace at every step.

```
User → request
        │
        ▼
  SmartAgent (Claude)      understands intent, asks to clarify if needed
        │
        ├─►  KnowledgeBase ──► VectorStore (ChromaDB)   retrieve VaR/CVA/RWA/... docs
        │
        └─►  DataProvider (mock stub)                   fetch only the data the metric needs
        │
        ▼
   answer  +  decision trace
```

| Phase | Piece | File |
|---|---|---|
| 3 | Vector store interface + Chroma impl (swap seam) | `src/vector_store.py` |
| 3 | Knowledge layer: chunk → domain-tag → ingest → retrieve | `src/knowledge_base.py` |
| 3 | Domain-tagged knowledge docs (10 docs, 4 desks) | `knowledge/<domain>/*.md` |
| 4 | Smart server-side agent (Claude loop + decision trace) | `src/smart_agent.py` |
| 4 | Risk-data seam (interface + mock stub) | `src/data_provider.py` |
| — | Runnable CLI demo | `demo.py` |

**Knowledge coverage per desk**

- **market_risk** — var, expected_shortfall, stress_testing, sensitivities_greeks
- **xva** — cva, exposure_metrics (EE/EPE/PFE)
- **regulatory_capital** — rwa, basel_capital_ratios
- **credit_risk** — pd_lgd_ead, credit_ratings_pd

**The decision trace.** Every step is recorded — intent, knowledge retrieved (with the domain and
source of each chunk), data decided, tools called, and the final answer. That trace is what the
chatbot's right-hand panel renders.

**Design seams.** The agent only ever talks to interfaces, so implementations swap without
touching it:

- **`VectorStore`** — ChromaDB today (embedded, no Docker). A `PgVectorStore` (Postgres +
  pgvector) slots in with no agent change.
- **`DataProvider`** — `MockDataProvider` (hardcoded sample risk data) today. **This is the seam
  that connects to the data layer above**: a provider reading `analytics.v_observation` and the
  real risk tables replaces the mock without the agent knowing.

---

# UI layer — chatbot

Streamlit chat interface with LangSmith observability: chat on the left, decision trace on the
right. Setup and usage in [`chatbot/README.md`](chatbot/README.md); architecture notes in
[`chatbot/CLAUDE.md`](chatbot/CLAUDE.md).

---

## Not built yet

- **Wiring `DataProvider` to PostgreSQL** — the single highest-value next step; the data exists
  and the seam exists, they are simply not connected.
- **MCP server** exposing the data tools, resources and prompts.
- **Risk tables beyond Treasury rates** — positions, counterparty exposure, historical prices.

## Known limits of the data layer

- **Published curve, not tradable prices.** End-of-day indicative quotes, no bid/ask, not
  executable. Any risk number derived from them inherits that.
- **No analytics in the data layer.** No returns, duration, DV01, VaR, expected shortfall,
  spreads, breakevens, bootstrapped zero curves, PCA or stress scenarios. Deliberate — mixing
  modelling into acquisition makes source data unauditable. Those calculations belong to the
  reasoning layer.
- **Revisions are not auto-detected.** Treasury can restate prior days; a routine rerun will not
  re-fetch a closed year without `--refresh`. When a revision is loaded, `meta.source_file`
  records it as a new row rather than overwriting, so the change stays visible.
- **Sparse by design.** No row means Treasury published nothing. `analytics.v_series_coverage`
  says what to expect.
- **The nested `adaptive-legacy-code-complexity-harness/`** is a separate git repository. It is
  ignored and must stay ignored — see [CLAUDE.md](CLAUDE.md).

## Documentation

| Question | Document |
|---|---|
| How does the whole data pipeline fit together? | [docs/system-overview.md](docs/system-overview.md) |
| What did Treasury publish, and what are the traps? | [docs/data-contract.md](docs/data-contract.md) |
| What do the tables and views look like? | [docs/database-schema.md](docs/database-schema.md) |
| How do I get PostgreSQL running? | [docs/postgres-setup.md](docs/postgres-setup.md) |
| How do I add a maturity or a dataset? | [docs/loading-contract.md](docs/loading-contract.md) |
| Why is it built this way? | [docs/architecture-decisions.md](docs/architecture-decisions.md) |
| Where does the source data come from? | [data/README.md](data/README.md) |

## License

Released under the [MIT License](LICENSE).
