# AGENTS.md — Agent Architecture

Vendor-neutral description of the agents in this project: what they are, how they
reason, what they can call, and how the pieces fit. (`CLAUDE.md` holds
Claude-Code-specific repo instructions; this file describes the runtime agents.)

## Three runtime agents, in one order

Everything the UI asks for goes through [`agents/pipeline.py`](agents/pipeline.py).
There is no other path: `POST /chat` calls `AgentPipeline.handle()` and nothing else.

```
    User question
       │
       ▼
    ORCHESTRATOR  classify
       ├─ normal question ─────────────────────► reply, stop
       └─ data request
            │
            ▼
       DOMAIN EXPERT  Qdrant vector search → requirement
            │
            ├──► MCP AGENT: what tools and data do you have?
            │◄── catalogue
            │
            │  ╔════════════ DISCUSSION (bounded, 3 rounds) ═══╗
            │  ║  domain proposes  ⇄  mcp says what it serves ║
            │  ║  domain revises   ⇄  ...                     ║
            │  ╚══════════════════════════════════════════════╝
            │
            ▼  final requirement
       MCP AGENT  fetch + calculate
            │
            ▼
    ORCHESTRATOR  reflect → reply
```

| Agent | Module | Job | Model is |
|---|---|---|---|
| **Orchestrator** | `agents/orchestrator_agent.py` | Routing. Runs on *every* turn, including "hi". | configuration |
| **Domain Expert** | `agents/domain_expert_agent.py` | The thinking. Retrieval, requirement, citation. | configuration |
| **MCP Agent** | `agents/mcp_agent.py` | Judging what a source can serve. | configuration |

**No agent names a model.** Each declares a *call site*; which model serves it
is decided by `LLM_BACKEND` and the per-call-site variables, exactly as
`DATA_BACKEND` decides which `DataProvider` serves a fetch. See
[`docs/model-provider.md`](docs/model-provider.md) for the allocation and the
measurements behind it.

### 1. Orchestrator — the front door

Classifies into one of three routes, as a **structured output**, never parsed prose.
A model asked to reply with the word `QUANT` will eventually reply `QUANT.` or
`Route: quant`, and a string comparison will send a risk question to the small-talk path.

| Route | Meaning | Cost |
|---|---|---|
| `direct` | Small talk, or a question about the system itself. | One routing turn. |
| `clarify` | A missing detail that would change the result. | One routing turn + a catalogue read for real choices. |
| `data_request` | A real question for the data layer. | The full path below. |

It also writes the **final reply**, after the work is done — so the expensive agents
produce structure and evidence, and the cheap one turns that into prose.

Two guarantees live in code rather than in the prompt:

- **A user who has just answered a clarification is never asked another.** The
  pipeline forces `route = data_request` on the next turn. A model instruction is
  not a bound; a loop with no exit is worse than a wrong guess.
- **Clarifying questions carry real choices.** The orchestrator reads the MCP
  catalogue before asking, so the options are actual portfolios and scenarios —
  clicking one *ends* the ambiguity instead of restating it.

### 2. Domain Expert — what does this task actually need?

Retrieves from Qdrant and emits a `Requirement`: the fields, the row window, the
tenors, the calculation, and the citations behind each.

**It holds no numbers of its own.** Every figure must be quoted verbatim from a
chunk it actually retrieved, and the quote is verified against the retrieved text:

```python
if rows is not None and not quote_is_grounded(quote, context):
    rows, quote = None, None      # discarded — and the user is told why
```

A window recalled from training is rejected exactly like a constant in the source:
both are unfalsifiable. You cannot change them by editing a document, and you
cannot audit them by reading one. When the corpus is silent, `rows` comes back
`None` and the answer says so rather than supplying a plausible default.

**Retrieval runs two queries, not one.** "What is expected shortfall" and "how many
observations does it read" are different questions, and one embedding cannot be
near both. Results are merged by best distance.

### 3. MCP Agent — what can actually be served?

Owns the tool surface. `catalogue()` advertises it, `assess()` judges a proposed
requirement against it, `execute()` fetches and calculates, `choices()` supplies
the real portfolios and scenarios the orchestrator needs to ask a grounded question.

It reaches the data through the **`DataProvider` seam**, never a driver directly.

### Why a discussion rather than a handoff

Neither agent knows enough alone. The domain expert knows what the *method*
requires — historical VaR reads 250 trading days, because it read that in the
knowledge base. The MCP agent knows what the *source* holds — a par yield curve has
no CUSIPs, no issuer names, no settlement dates.

A one-way handoff produces requirements nobody can serve (six fields, three of
which do not exist) or fetches nobody asked for. Each round is a real model call
and a real trace span, so the negotiation is auditable rather than implied.

**Why it is bounded.** Two agents that can always reply will always reply. The loop
stops when the MCP agent reports the requirement feasible, or after `MAX_ROUNDS = 3`
— and if it never converges, that fact is recorded and reported instead of hidden
behind a last-ditch answer.

### Scope and honesty rules

Interest-rate market risk: curve level, slope and history; rate VaR, ES, DV01 and
stress. No portfolio or counterparty data, so CVA, EE/EPE/PFE, RWA and PD/LGD/EAD
are explained from knowledge but **not computed**.

- The demo book is `SYNTHETIC_DEMO`; the curve is `REAL_MARKET_DATA`. Both labels
  survive into the answer.
- Bond values are **model-implied** from the par curve, not executable prices.
- Reported VaR is an **analytical demonstration**, not a regulatory figure.
- If a provider cannot supply something, the answer is "I don't have that", not a
  plausible number.

## Interfaces (swap seams)

The agents talk only to interfaces. Swapping an engine must require no change in
an agent.

| Seam | Implementations | Chosen by |
|---|---|---|
| `VectorStore` | `QdrantVectorStore` (embedded for dev, or Docker via `QDRANT_URL`) | `QDRANT_URL` |
| `DataProvider` | `McpDataProvider` · `PostgresDataProvider` · `MockDataProvider` | `DATA_BACKEND` |
| `ModelProvider` | `AnthropicProvider` · `ZaiProvider` | `LLM_BACKEND` |

**Structured output is validated, never trusted.** A provider returns an object
only after it has passed strict schema and type checking, because valid JSON is
not the same as a valid answer: a renamed field or a whole float where an
integer was required parses cleanly and then becomes `None` three layers later.
Grounding is checked *separately and afterwards* — a structurally perfect result
can still be factually ungrounded, and is rejected.

**Capability is detected, never assumed.** Portfolio and risk tools are offered only
when the provider can actually reach them (`hasattr(self.data, "call_tool")`). Under
`mock` or `postgres` the agents never see those tools and say plainly that there are
no positions. An agent that advertises a capability it cannot honour will
confabulate one.

## Deterministic orchestration is not the model's job

Marshalling a portfolio into the risk engine's input shape, and differencing two
observed curves into a replay shock, live in
[`backend/src/backend/workflows/risk_workflows.py`](backend/src/backend/workflows/risk_workflows.py).
This is mechanical work with exactly one right answer; a model asked to improvise
it will eventually improvise it differently. The agents choose *which* workflow to
call, not how to reshape a payload.

## Serving — the `/chat` service

`backend/src/backend/api/service.py` (FastAPI):

```
POST /chat      {query, session_id}
  -> {answer, sources, trace, awaiting_clarification, elicitation, route,
      tables, data_plan, negotiation, catalogue, calculation, langsmith_url}
POST /summarise {messages} -> {title}
GET  /health
```

The pipeline is stateless; **the service owns session memory** — the last twelve
turns plus a `clarified` flag, which is what stops a second consecutive question.

`awaiting_clarification` follows the **route**, never the prose. Inferring it from
the text was a real defect: a finished 2,302-character answer ending "Want me to
run DV01?" was reported as a pending question, while the same answer ending "Say
which and I'll run it." was not — identical intent, opposite classification,
decided by the final character. The orchestrator now decides before anything is
composed, so there is nothing left to infer.

## Decision trace

Typed steps — `intent`, `knowledge`, `decision`, `tool_call`, `answer`,
`clarification` — recorded by the pipeline as it goes, and carried to the UI's
right-hand panel. Alongside it travel the `data_plan` (the requirement and its
citations) and the `negotiation` transcript, so a reader can see that the row
count was *argued* rather than assumed.

## Knowledge layer

- Source docs: `knowledge/<domain>/*.md`. **The subfolder name is the domain tag.**
- Domains: `market_risk`, `xva`, `regulatory_capital`, `credit_risk`.
- Pipeline: chunk on markdown headings → tag (domain, source, heading) → embed →
  store → semantic retrieve with optional domain filter.
- Docs follow Definition → Formula (dry) → Data required → Notes.
- **Don't bloat it.** Retrieval quality falls as the corpus fills with material
  nothing ever asks for.
- Re-ingest after any edit: `KnowledgeBase(rebuild=True)`.

## A fourth agent: the host's own loop

[`mcp_servers/host/agent.py`](mcp/src/mcp_servers/host/agent.py) is a separate,
smaller reasoning loop that drives both MCP servers directly:

```bash
python -m mcp_servers.host --ask "..."
```

It exists so the MCP layer can be exercised and demonstrated **without the backend,
Qdrant or the UI running**. It shares the model layer (`HOST_AGENT_MODEL`)
and the honesty rules, but has no knowledge base, no discussion and no decision
trace. It is not in the `/chat` path.

Sampling makes the division of labour explicit: neither server may hold a model, so
when the data server needs prose it asks the *host* for a completion. The
credential and the reasoning stay on one side of the boundary; the database
credential stays on the other.

## Build / support agents (Claude Code subagents)

Defined in `.claude/agents/`. These help *develop* the project; they are not part of
the runtime. One per concern, and each states what it must **not** do — the
boundaries between tiers are the part worth protecting.

| Agent | Owns | Explicitly does not |
|---|---|---|
| **acquisition-agent** | `data/acquisition/`, raw Treasury XML, manifests | load PostgreSQL |
| **database-agent** | migrations, loader, analytics views, grants | download source data |
| **mcp-agent** | both MCP servers, the host, curve/risk maths | provision databases, author knowledge |
| **backend-agent** | the three runtime agents, provider seam, `/chat` service | build MCP servers |
| **frontend-agent** | the React app and artifact panel | change the agents or the `/chat` contract |
| **knowledge-author** | the `knowledge/` corpus | change retrieval code |
| **verification-agent** | the gates between a defect and `main` | quietly fix the code under test |

## Built and wired

- **Data layer** — PostgreSQL with the real Treasury rates (267,517 rows), verified.
- **Knowledge layer** — Qdrant with 71 chunks, running in Docker.
- **MCP layer** — two stdio servers plus the host, on protocol revision 2026-07-28,
  exercising **all six primitives**: tools, resources, prompts, elicitation, roots
  and sampling. `DATA_BACKEND=mcp` routes the agents through them.
- **Reasoning layer** — the three agents above, behind `/chat`, reading through both
  seams.
- **Evaluation** — 13 cases × 11 scorers on LangSmith, scoring behaviour rather than
  answers.
