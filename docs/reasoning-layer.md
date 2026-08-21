# Reasoning layer — the three agents

How the middle layer works: it turns a natural-language risk question into a
grounded, data-backed answer with a visible decision trace. It owns no data of
its own — it *retrieves knowledge* from a vector DB and *fetches facts* from the
data layer, through two swap seams.

Full agent architecture: [`AGENTS.md`](../AGENTS.md). This document covers the
seams, the service and the knowledge base underneath them.

## The flow

```
  question
     │
     ▼
  ORCHESTRATOR (Haiku)  classify                agents/orchestrator_agent.py
     ├─ direct ──────────────────────────────► reply, stop
     └─ data_request
          │
          ▼
  DOMAIN EXPERT (Opus)                          agents/domain_expert_agent.py
     └─► KnowledgeBase ─► Qdrant                backend/knowledge/knowledge_base.py
          "what does this metric mean, and how many rows does it read?"
          │                                     backend/knowledge/vector_store.py
          ▼  Requirement — fields, rows, citations, verified quote
          │
          │  ⇄  MCP AGENT: what can you serve?  agents/mcp_agent.py
          │     (bounded negotiation, 5 rounds)
          ▼
  MCP AGENT (Opus)  execute
     └─► DataProvider ─► MCP servers ─► PostgreSQL   backend/providers/base.py
          get_yield_curve / get_rate_history / ...   backend/providers/mcp.py
          risk workflows                             backend/workflows/risk_workflows.py
          │
          ▼
  ORCHESTRATOR (Haiku)  reflect → reply
     │
     ▼
  answer + trace (intent → tool_call → knowledge → decision → answer)
        + data_plan (the requirement and its citations)
        + negotiation (what the two agents said to each other)
```

## The two seams (why the engines are swappable)

The agent imports **interfaces**, never a concrete engine. Both are chosen by
environment variable:

| Seam | Interface | Implementations | Chosen by |
|---|---|---|---|
| Knowledge | `VectorStore` | `QdrantVectorStore` (embedded dev / Docker server) | `QDRANT_URL` |
| Data | `DataProvider` | `PostgresDataProvider` (real) · `MockDataProvider` (dev) | `DATA_BACKEND` |

`QDRANT_URL` set → talk to the Docker Qdrant server; unset → embedded local store
at `./data/qdrant`. `DATA_BACKEND=postgres` → read the real `analytics.*` views;
otherwise the synthetic mock (Treasury-shaped, seeded from the real 2026-08-11
curve).

## The tools the agent can call

| Tool | Backed by | Returns |
|---|---|---|
| `retrieve_knowledge(query, domain?)` | Qdrant | relevant knowledge chunks |
| `list_series()` | `analytics.v_series` | available tenors/series |
| `get_latest_rates()` | `analytics.v_par_yield_curve` | most recent rate per tenor |
| `get_yield_curve(curve_date?, kind?)` | `v_par_yield_curve` / `v_real_yield_curve` | one day's curve, wide |
| `get_rate_history(tenor, start?, end?)` | the wide views | a tenor's daily history |
| `get_curve_slope(short?, long?, curve_date?)` | derived | slope in basis points (e.g. 2s10s) |

## Scope

The agent answers **interest-rate market-risk** questions — curve level, slope,
history, and rate-based VaR/ES/DV01/stress. It has no portfolio or counterparty
data, so CVA/RWA/PD-LGD-EAD it can *explain* from the knowledge base but not
compute. The knowledge base spans `market_risk`, `xva`, `regulatory_capital`,
`credit_risk`; only the rate-backed metrics have live data tools today.

## The `/chat` service

`backend/src/backend/api/api.py` (FastAPI) exposes the agent over the contract the chatbot
expects:

```
POST /chat  { "query": "...", "session_id": "..." }
  -> { "answer": "...", "sources": [...], "trace": [...], "awaiting_clarification": false }
GET  /health -> { "status": "ok", "api_key_configured": true|false }
```

`session_id` keeps per-session conversation history, so the agent can ask a
clarifying question and continue on the next turn. `trace` is the ordered list of
steps for the UI's decision-trace panel; `sources` are the `domain/source`
knowledge docs the answer leaned on.

## Running it

```bash
docker compose up -d qdrant postgres          # both databases
$env:QDRANT_URL = "http://localhost:6333"; python -m backend.knowledge.knowledge_base   # ingest knowledge
$env:ANTHROPIC_API_KEY = "sk-ant-..."; $env:DATA_BACKEND = "postgres"
python -m backend.api.service                    # POST /chat on :8000
```

Or the whole stack — Postgres, Qdrant, and the agent container — with
`docker compose up -d` (set `ANTHROPIC_API_KEY` in `.env` first).

## Not built yet

The named **MCP server** — exposing these data tools over the MCP *protocol* —
is still to come; today the agent calls `PostgresDataProvider` in-process behind
the same `DataProvider` seam, so the MCP server slots in without changing the
agent.
