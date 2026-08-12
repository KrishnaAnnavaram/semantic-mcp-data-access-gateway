# semantic-mcp-data-access-gateway
Semantic MCP data access gateway for intent-aware request understanding, intelligent data requirement planning, filtering, and optimized retrieval across enterprise data sources.

Instead of a client blindly calling every tool an MCP server exposes, this project adds an AI
layer that reads the incoming question, consults a knowledge base of what each tool/data source
is actually for, and only invokes what's needed to answer it.

## Structure

Monorepo with three independent workstreams:

| Folder | Owns | Status |
|---|---|---|
| [`chatbot/`](chatbot/) | Streamlit chat UI + LangSmith observability | In progress |
| _(TBD)_ | Smart agent + vector database | Not started |
| _(TBD)_ | MCP server + PostgreSQL (Docker) | Not started |

Each subfolder is runnable and testable on its own, and has its own `README.md` (setup/usage) and
`CLAUDE.md` (architecture notes for whoever — human or Claude Code — works in that folder next).
See the root [`CLAUDE.md`](CLAUDE.md) for how the three pieces fit together and the API contract
between them.

## Getting started

Dependencies for all workstreams are aggregated in one root-level `requirements.txt`. Set up one
venv here, then work from whichever subfolder you own:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cd chatbot
cp .env.example .env
streamlit run app.py
```
=======
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

