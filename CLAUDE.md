# semantic-mcp-data-access-gateway

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
