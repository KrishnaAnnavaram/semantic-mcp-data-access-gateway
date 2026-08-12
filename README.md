
# Quant Risk Smart Agent — Phases 3 & 4

A **server-side smart agent** for quantitative risk analysis, grounded in a
**vector-database knowledge layer**. This slice is the "brains" of the larger
project; the risk database + MCP server are deliberately stubbed for now and get
wired in later (no Docker required to run this).

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

## What's built

| Phase | Piece | File |
|------|-------|------|
| 3 | Vector store interface + Chroma impl (swap seam) | `src/vector_store.py` |
| 3 | Knowledge layer: chunk → domain-tag → ingest → retrieve | `src/knowledge_base.py` |
| 3 | Domain-tagged knowledge docs (10 docs, 4 desks) | `knowledge/<domain>/*.md` |
| 4 | Smart server-side agent (Claude loop + decision trace) | `src/smart_agent.py` |
| 4 | Risk-data seam (interface + mock stub) | `src/data_provider.py` |
| — | Runnable CLI demo | `demo.py` |

## Knowledge coverage (per desk)

- **market_risk** — var, expected_shortfall, stress_testing, sensitivities_greeks
- **xva** — cva, exposure_metrics (EE/EPE/PFE)
- **regulatory_capital** — rwa, basel_capital_ratios
- **credit_risk** — pd_lgd_ead, credit_ratings_pd

## Setup

```bash
pip install -r requirements.txt
```

## Run

**Phase 3 only** (no API key needed — proves the vector DB works):
```bash
python src/knowledge_base.py
```

**Phases 3 + 4 end-to-end** (needs Claude):
```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python demo.py
python demo.py "What is my RWA against GLOBEX?"
```

## The decision trace
Every step the agent takes is recorded — intent, knowledge retrieved (with the
domain + source of each chunk), data decided, tools called, and the final
answer. That trace is what the chatbot UI's right-hand panel will render.

## Design seams (why swapping is cheap later)
The agent only ever talks to interfaces:
- **`VectorStore`** — ChromaDB today (embedded, no Docker). A `PgVectorStore`
  (Postgres + pgvector) slots in for the Dockerized target with no agent change.
- **`DataProvider`** — `MockDataProvider` (hardcoded sample risk data) today. An
  MCP/DB-backed provider reading the real `assets` / `historical_prices` /
  `portfolio_positions` / `counterparty_exposure` tables slots in later.

## Not built yet (next)
- PostgreSQL/SQLite risk database + seed data
- MCP server exposing the data tools + resources/prompts
- Chatbot UI (chat left, decision trace right)

## Layout
```
mcp agents/
├── knowledge/<domain>/*.md   RAG source docs, tagged by desk
├── src/
│   ├── vector_store.py       VectorStore interface + ChromaVectorStore
│   ├── knowledge_base.py     chunk + domain-tag + ingest + retrieve
│   ├── data_provider.py      DataProvider interface + MockDataProvider
│   └── smart_agent.py        Claude loop + decision trace
├── demo.py
├── requirements.txt
└── chroma_db/                local vector store (auto-created)
```
=======
# semantic-mcp-data-access-gateway

Semantic MCP data access gateway for intent-aware request understanding, intelligent data
requirement planning, filtering, and optimized retrieval across enterprise data sources.

## Status

Early scaffold. The repository currently contains project metadata only — no runtime code
has landed yet. Structure, interfaces, and setup steps below will be filled in as the
implementation takes shape.

## Overview

The gateway sits between a client and one or more enterprise data sources, exposed over the
[Model Context Protocol](https://modelcontextprotocol.io). Rather than passing queries
straight through, it aims to:

- **Understand intent** — interpret what a request is actually asking for, not just its literal form.
- **Plan data requirements** — determine which sources and fields are needed to answer it.
- **Filter** — narrow results to the relevant subset before they leave the gateway.
- **Retrieve efficiently** — fetch across sources with as little redundant work as possible.

## Getting started

Clone the repository:

```bash
git clone https://github.com/KrishnaAnnavaram/semantic-mcp-data-access-gateway.git
cd semantic-mcp-data-access-gateway
```

Build and run instructions will be added once the initial implementation lands.

## License

Released under the [MIT License](LICENSE).
