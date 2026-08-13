# chatbot

Streamlit chatbot front-end for the semantic-mcp-data-access-gateway project. Sends a user's question to the quant
agent and shows the answer.

## Setup

Run from the repo root (dependencies for all workstreams live in one `requirements.txt` there):

```bash
cd ..
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd chatbot
cp .env.example .env
```

## Run

```bash
streamlit run app.py
```

By default `AGENT_BACKEND=mock` in `.env.example`, so the app runs standalone with canned
responses — no other services required. Once the quant agent is available, set in `.env`:

```
AGENT_BACKEND=rest
AGENT_API_URL=http://<agent-host>:<port>
```

## Observability

Set these in `.env` to enable [LangSmith](https://smith.langchain.com) tracing of every
question/answer round-trip:

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=<your key>
LANGCHAIN_PROJECT=semantic-mcp-data-access-gateway
```

## Test

```bash
pytest
```

## Lint

```bash
ruff check .
```

See `CLAUDE.md` for architecture notes and the agent API contract.
