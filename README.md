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
