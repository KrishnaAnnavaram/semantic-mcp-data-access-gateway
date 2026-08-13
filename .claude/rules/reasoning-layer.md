---
paths:
  - "backend/src/backend/agent/**/*.py"
  - "backend/src/backend/providers/**/*.py"
  - "backend/src/backend/api/**/*.py"
  - "knowledge/**/*.md"
  - "src/frontend/**/*.py"
---

# Rules for the reasoning, provider and service layers

The agent that answers questions, the seam it gets facts through, and the HTTP
service the chatbot calls. Background: `docs/reasoning-layer.md`.

## Keep the seams

`QuantAgent` talks only to two interfaces — `KnowledgeBase` and `DataProvider`.
Do not let it import a concrete engine, a database driver, or an MCP client
directly. Swapping the vector store or the data backend must require no change
in the agent.

That is why there are three providers behind one Protocol:

| `DATA_BACKEND` | Class | Notes |
|---|---|---|
| `mcp` | `providers/mcp.py` | Through both MCP servers as `mcp_reader`. Default for the full stack. |
| `postgres` | `providers/postgres.py` | Direct psycopg2 as the **owner** role — it can write to the source of record. |
| `mock` | `providers/base.py` | Synthetic, Treasury-shaped. The default when nothing is set. |

Add a fourth by implementing the Protocol and extending `make_data_provider()`.
Nothing else changes.

## Capability is detected, never assumed

Portfolio and risk tools are offered only when the provider can actually reach
them (`hasattr(self.data, "call_tool")`). Under `mock` or `postgres` the agent
never sees those tools and states plainly that it has no positions. An agent
that advertises a capability it cannot honour will confabulate one.

## The async/sync bridge

MCP is asyncio and owns two stdio child processes; `DataProvider` is synchronous
and called from FastAPI handlers. The bridge runs **one event loop on a daemon
thread for the process lifetime** — not a loop per call, and not servers per
call. Two reasons: child-process startup is expensive, and `mcp_reader` has
`CONNECTION LIMIT 5`, so a bridge per agent instance exhausts the pool under
concurrency.

## Orchestration belongs here, not in the model

Marshalling a portfolio into the risk engine's input shape, and differencing two
observed curves into a replay shock, live in `service/risk_workflows.py`. This
is mechanical work with exactly one right answer; a model asked to improvise it
will eventually improvise it differently. The model chooses *which* workflow to
call, not how to reshape a payload.

## Honesty rules for answers

- **Never present synthetic data as real.** The demo book is `SYNTHETIC_DEMO`;
  the curve is `REAL_MARKET_DATA`. Both labels must survive into the answer.
- Bond values are **model-implied** from the par curve, not executable prices.
- Reported VaR is an **analytical demonstration**, not a regulatory figure.
- **Scope is interest-rate market risk.** CVA, EE/EPE/PFE, RWA and PD/LGD/EAD can
  be explained from the knowledge base but **not computed** — there is no
  counterparty or portfolio-credit data. Say so and offer what can be computed.
- **Don't invent risk data.** If a provider cannot supply it, the answer is "I
  don't have that", not a plausible number.

## Knowledge base

- **Subfolder name under `knowledge/` is the domain tag.** Adding a domain means
  a new subfolder plus its docs, then adding it to `DOMAINS` in
  `reasoning/quant_agent.py`. Ingest discovers the rest.
- Docs follow the house style in the `risk-analysis` skill: Definition → Formula
  (dry) → Data required (naming the risk tables) → Notes.
- **Don't bloat it.** Only risk-analysis-essential docs. Retrieval quality falls
  as the corpus fills with material nothing ever asks for.
- Re-ingest after any edit: `KnowledgeBase(rebuild=True)`.

## Service

`service/api.py` loads `.env` at import, before the Anthropic client resolves its
key. Without that the service starts healthy and dies on the first `/chat`,
which is a confusing way to discover a missing key.
