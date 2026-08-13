# chatbot

Streamlit chatbot front-end for the semantic-mcp-data-access-gateway project. See the repo root `CLAUDE.md` for how this
fits into the overall system; see `README.md` for human-oriented setup instructions.

## What this service does

Takes a user's question, forwards it to the quant agent (owned by another teammate) over the REST
contract below, and renders the answer directly in the chat thread. It has no reasoning logic of
its own — that all lives in the agent.

## Architecture

- `app.py` — Streamlit UI: sidebar chat-session list, chat input/history rendered as custom bubbles.
- `styles.py` — custom CSS (dark theme, bubbles, header, empty state) injected via `inject_custom_css()`.
- `agent_client.py` — talks to the quant agent. `AgentClient` is a `Protocol` with two
  implementations: `RestAgentClient` (real HTTP calls) and `MockAgentClient` (canned responses,
  used when `AGENT_BACKEND=mock`, the default — lets the UI run standalone before the real agent
  exists). Swapping the transport to an MCP client later means adding a new implementation here
  and updating `_build_client`; `app.py` doesn't need to change.
- `observability.py` — validates LangSmith env config and logs whether tracing is active.
  Tracing itself happens via the `@traceable` decorator on `agent_client.ask_agent`.
- `config.py` — typed `Settings`, loaded once from `.env` / the environment via `get_settings()`.

## Agent contract

```
POST {AGENT_API_URL}/chat
  { "query": "<user question>", "session_id": "<uuid>" }
  -> { "answer": "<text>", "sources": ["..."] }
```

This is interim for the demo — if the agent/MCP side lands on a different shape, update
`RestAgentClient.ask` accordingly.

## Running

Dependencies for all workstreams live in one `requirements.txt` at the repo root — install from
there, then run the app from here:

```
pip install -r ../requirements.txt
cp .env.example .env
streamlit run app.py
```

Defaults to the mock agent, so it runs standalone. Set `AGENT_BACKEND=rest` and `AGENT_API_URL`
in `.env` to point at a real quant agent.

## Testing

```
pytest
```

## Conventions

- No Docker for this service — it's a plain Python app, run directly.
- Keep the agent transport behind `AgentClient` — don't call `requests` or an MCP client directly
  from `app.py`.
