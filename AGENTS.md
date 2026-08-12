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
2. **Clarify if ambiguous** — ask ONE question when the metric, portfolio,
   counterparty, confidence, or horizon is missing, instead of guessing.
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
| `retrieve_knowledge(query, domain?)` | KnowledgeBase → VectorStore | RAG over quant docs; optional domain scope |
| `get_assets()` | DataProvider | book assets (id, class, currency) |
| `get_historical_prices(asset_id, days?)` | DataProvider | price series for VaR/ES |
| `get_portfolio_positions()` | DataProvider | current positions |
| `get_counterparty_exposure(counterparty?)` | DataProvider | exposure + credit inputs |

### Interfaces (swap seams)
- **KnowledgeBase** depends on a **`VectorStore`** interface — ChromaDB today,
  pgvector (Postgres) for the Docker target.
- Data tools depend on a **`DataProvider`** interface — `MockDataProvider` today,
  MCP/DB-backed later. The agent never imports a concrete implementation.

### Decision trace
A list of typed steps: `intent`, `knowledge` (with domain + source of each
chunk), `decision`, `tool_call`, `answer`, `clarification`. Rendered by
`render_trace()`; consumed by the future chatbot UI.

## Knowledge layer
- Source docs: `knowledge/<domain>/*.md`, tagged by desk (subfolder name).
- Domains: `market_risk`, `xva`, `regulatory_capital`, `credit_risk`.
- Pipeline: chunk on markdown headings → tag (domain, source, heading) → embed →
  store → semantic retrieve with optional domain filter.

## Build / support agents (Claude Code subagents)
Defined in `.claude/agents/`. These help *develop* the project; they are not part
of the runtime.
- **knowledge-author** — writes/reviews `knowledge/` docs in the house format.

## Not yet built
Risk database + seed data, MCP server (tools/resources/prompts), chatbot UI.
Each wires in behind an existing seam without changing the agent.
