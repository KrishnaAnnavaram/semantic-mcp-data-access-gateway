# AGENTS.md — Agent Architecture

Vendor-neutral description of the agent(s) in this project: what they are, how
they reason, what they can call, and how the pieces fit. (`CLAUDE.md` holds
Claude-Code-specific repo instructions; this file describes the runtime agent.)

## The runtime agent: SmartAgent
A **server-side quantitative risk agent**. It is the "smart" tier that sits
behind the client and does the actual reasoning.

- **Model:** `claude-opus-5`, adaptive thinking.
- **Loop:** manual tool-calling loop (`src/smart_agent.py`) — chosen over the
  SDK tool runner so every step can be captured in a decision trace.
- **Location in the system:** server-side, behind (eventually) an MCP boundary.
  The client is thin; the intelligence is here.

### Responsibilities (in order)
1. **Understand intent** — parse the client request.
2. **Clarify if ambiguous** — ask ONE question when the metric, tenor, date,
   confidence, or horizon is missing, instead of guessing.
3. **Ground in knowledge** — call `retrieve_knowledge` (RAG) before computing, to
   get the correct definition and the exact data inputs a metric needs.
4. **Decide required data** — pick only the data tools the metric actually needs.
5. **Fetch data** — call the data tools (via the DataProvider interface).
6. **Compose the answer** — high-level calculation + result with units and
   stated assumptions.
7. **Emit a decision trace** — every step is recorded for the UI's right panel.

### Tools the agent can call
| Tool | Backed by | Purpose |
|---|---|---|
| `retrieve_knowledge(query, domain?)` | KnowledgeBase → Qdrant | RAG over quant docs; optional domain scope |
| `list_series()` | DataProvider | available tenors/series |
| `get_latest_rates()` | DataProvider | most recent rate per tenor |
| `get_yield_curve(curve_date?, kind?)` | DataProvider | one day's curve, wide (nominal/real) |
| `get_rate_history(tenor, start?, end?)` | DataProvider | a tenor's daily history |
| `get_curve_slope(short?, long?, curve_date?)` | DataProvider | slope in bps, e.g. 2s10s |

Scope: interest-rate market risk (curve level/slope/history, rate VaR/ES/DV01/
stress). No portfolio or counterparty data, so CVA/RWA/PD-LGD-EAD are explained
from knowledge but not computed.

### Interfaces (swap seams)
- **KnowledgeBase** depends on a **`VectorStore`** interface — `QdrantVectorStore`
  (embedded for dev, or a Docker server via `QDRANT_URL`).
- Data tools depend on a **`DataProvider`** interface — `PostgresDataProvider`
  (reads `analytics.*` views) when `DATA_BACKEND=postgres`, else
  `MockDataProvider`. The agent never imports a concrete implementation.

### Serving — the `/chat` service
`src/agent_service.py` (FastAPI) exposes the agent to the UI:
`POST /chat {query, session_id} -> {answer, sources, trace, awaiting_clarification}`
plus `GET /health`. Per-`session_id` history lets a clarifying question continue
on the next turn.

### Decision trace
A list of typed steps: `intent`, `knowledge` (with domain + source of each
chunk), `decision`, `tool_call`, `answer`, `clarification`. Serialized by
`trace_as_dicts()` for the `/chat` response; also `render_trace()` for the CLI.

## Knowledge layer
- Source docs: `knowledge/<domain>/*.md`, tagged by desk (subfolder name).
- Domains: `market_risk`, `xva`, `regulatory_capital`, `credit_risk`.
- Pipeline: chunk on markdown headings → tag (domain, source, heading) → embed →
  store → semantic retrieve with optional domain filter.

## Build / support agents (Claude Code subagents)
Defined in `.claude/agents/`. These help *develop* the project; they are not part
of the runtime.
- **knowledge-author** — writes/reviews `knowledge/` docs in the house format.

## Built and wired
- Data layer: PostgreSQL with the real Treasury rates (267,517 rows), verified.
- Knowledge layer: Qdrant with the knowledge chunks, running in Docker.
- Reasoning: the agent + `/chat` service, reading both via the two seams.

## Not yet built
The **MCP protocol server** (exposing the data tools/resources/prompts over MCP)
— today the agent calls `PostgresDataProvider` in-process behind the same seam.
The chatbot's decision-trace panel. Both slot in without changing the agent.
