# CLAUDE.md — Quant Risk Smart Agent

Project memory for Claude Code working in this repository. Read this first.

## What this project is
A **server-side smart agent** for quantitative risk analysis (VaR, Expected
Shortfall, stress, sensitivities, CVA, exposure, RWA, Basel ratios, PD/LGD/EAD),
grounded in a **vector-database knowledge layer** (RAG). The agent understands a
user's intent, retrieves the right quant knowledge, decides which risk data it
actually needs, fetches only that, and answers — emitting a decision trace at
every step.

Current scope: **Phases 3 (knowledge/vector layer) and 4 (smart agent)** are
built. The real database, MCP server, and chatbot UI are deliberately deferred.

## Architecture (and the two swap seams)
```
User → SmartAgent (Claude) → KnowledgeBase → VectorStore (ChromaDB)
                           → DataProvider (mock stub)
       → answer + decision trace
```
The agent talks only to interfaces, so implementations swap without touching it:
- **`VectorStore`** (`src/vector_store.py`) — ChromaDB now (embedded, no Docker);
  a `PgVectorStore` (Postgres + pgvector) is the Dockerized target.
- **`DataProvider`** (`src/data_provider.py`) — `MockDataProvider` now; an
  MCP/DB-backed provider reads the real risk tables later.

Do not make the agent import a concrete engine directly. Keep the seams.

## Layout
- `knowledge/<domain>/*.md` — RAG source docs. **Subfolder name = domain tag.**
  Domains: `market_risk`, `xva`, `regulatory_capital`, `credit_risk`.
- `src/vector_store.py` — VectorStore interface + ChromaVectorStore.
- `src/knowledge_base.py` — chunk → domain-tag → ingest → retrieve.
- `src/data_provider.py` — DataProvider interface + MockDataProvider.
- `src/smart_agent.py` — Claude tool-calling loop + decision trace.
- `demo.py` — end-to-end CLI runner.
- `chroma_db/` — local vector store, auto-created (do not edit by hand).

## Commands
- Install: `pip install -r requirements.txt`
- Phase 3 only (no API key): `python src/knowledge_base.py`
- Phases 3+4 live (needs key): set `ANTHROPIC_API_KEY`, then `python demo.py`

## Conventions
- **Model:** default to `claude-opus-5` with adaptive thinking. Do not downgrade
  without being asked.
- **Knowledge docs** follow a fixed house style — see the `risk-analysis` skill
  in `.claude/skills/`. Every doc: Definition → Formula (dry) → Data required
  (naming the risk tables) → Notes. Keep them concise and accurate.
- **Adding a domain** = new subfolder under `knowledge/` + docs; the ingest picks
  it up automatically. Add the domain to `DOMAINS` in `src/smart_agent.py`.
- After changing any knowledge doc, re-ingest:
  `python -c "import sys; sys.path.insert(0,'src'); from knowledge_base import KnowledgeBase; KnowledgeBase(rebuild=True)"`
- Keep it "basic and dry" — no Docker, no heavy infra unless explicitly asked.

## Guardrails
- Don't commit or push unless asked.
- Don't invent risk data — the mock lives in `src/data_provider.py`; real data
  comes later via the DataProvider seam.
- Don't bloat the knowledge base; add only risk-analysis-essential docs.
