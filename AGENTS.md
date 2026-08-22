# AGENTS.md — Agent Architecture

Vendor-neutral description of the agents in this project: what they are, how they
reason, what they can call, and how the pieces fit. (`CLAUDE.md` holds
Claude-Code-specific repo instructions; this file describes the runtime agents.)

## Three runtime agents, in one order, over A2A

Each of the three is an independently addressable **A2A agent**: an Agent Card,
a set of skills, a JSON-RPC endpoint, and a task lifecycle. Every arrow below is
an A2A task, not a Python method call. Full design: [`docs/a2a.md`](docs/a2a.md).

`POST /chat` sends one A2A message to the orchestrator and nothing else. It is
the only agent whose card admits the user boundary; the other two reject a
request from it by name.

```
    User question
       │  FastAPI, acting for the user  ──A2A: handle_user_turn──┐
       ▼                                                         │
    ORCHESTRATOR  classify  ◄────────────────────────────────────┘
       ├─ normal question ─────────────────────► reply, stop
       ├─ missing detail ──A2A──► MCP AGENT: list_data_choices ──► ask once
       └─ data request
            │
            │ A2A: derive_data_requirement
            ▼
       DOMAIN EXPERT  Qdrant vector search → requirement
            │
            ├──A2A──► MCP AGENT: describe_data_capabilities
            │◄──────  catalogue
            │
            │  ╔═══════ NEGOTIATION (bounded, 5 rounds, over A2A) ══════╗
            │  ║  domain proposes  ⇄  assess_data_requirement           ║
            │  ║  domain revises   ⇄  ...                               ║
            │  ╚════════════════════════════════════════════════════════╝
            │
            ▼  requirement · negotiation · catalogue · citations (artifacts)
    ORCHESTRATOR
            │ A2A: execute_data_plan
            ▼
       MCP AGENT  fetch + calculate  ──► dataset · calculation · summary
            │                        └─► or task state: input-required
            ▼
    ORCHESTRATOR  reflect → reply    (or relay the question to the user)
```

**A2A carries agents; MCP carries data.** Neither replaced the other. The MCP
agent still reaches PostgreSQL and the risk engine through the two MCP servers
as `mcp_reader`, and no other agent has a road to the database at all.

| Agent | Module | A2A address | Job | Model is |
|---|---|---|---|---|
| **Orchestrator** | `agents/orchestrator_agent.py` | `/a2a/orchestrator` | Routing, and the only agent a user reaches. Runs on *every* turn, including "hi". | configuration |
| **Domain Expert** | `agents/domain_expert_agent.py` | `/a2a/domain-expert` | The thinking. Retrieval, requirement, citation, and the discussion. | configuration |
| **MCP Agent** | `agents/mcp_agent.py` | `/a2a/mcp-agent` | Judging what a source can serve, and serving it. | configuration |

There are **three**, and a fourth would be a design change rather than a
convenience. `mcp_servers/host/agent.py`, `RiskWorkflows`, `KnowledgeBase`, the
`DataProvider` implementations, the sampling callback and `McpHost` are
services, adapters and helpers — none of them has a card, and none should.

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

**Why it is bounded.** Two agents that can always reply will always reply. The
loop stops when a **decision** is reached, after `MAX_UNCHANGED_ROUNDS = 2`
consecutive rounds that change nothing (see below), or after
`MAX_NEGOTIATION_ROUNDS = 5`. There are four decisions, and which one it was
decides what the user is told:

| Decision | Meaning | The user gets |
|---|---|---|
| `AGREED` | An executable plan both agents accept. | The answer. |
| `NEEDS_USER_INPUT` | A choice neither agent may make. | One clarifying question. |
| `UNSUPPORTED` | The data layer genuinely cannot serve this. | A plain refusal and what it *can* do. |
| `CANNOT_REACH_AGREEMENT` | The rounds ran out, or the conversation stalled. | That fact, and no number. |

A boolean `converged` could not distinguish the last three, so all three
arrived as the same flat "declined" — including the case where one more
sentence from the user would have unblocked it. `converged` is now derived
(`decision == "AGREED"`), so the flag cannot drift from the decision.

**A revision is verified, not claimed.** The planner diffs the two requirements
rather than trusting the expert's account of what it changed. A round that
reports a revision and produces an identical requirement is a round that did
nothing, and the loop does not spend another one on it: two consecutive
no-change rounds end the conversation as `CANNOT_REACH_AGREEMENT`, naming the
stall.

That diff was computed and written into the transcript for a long time before
anything *read* it, so a stalled conversation ran its full five rounds to
finish exactly where round one left it — eight further model calls for nothing.
Two rather than one, because the first dead round can still be followed by a
genuine convergence; by the second the data layer is answering the identical
capability question (the input fingerprints the same, so the assessment is the
turn's own cached reply) and there is no new information left in the loop.

Under A2A the discussion crosses a real agent boundary, so it carries three
further bounds that do not depend on either agent behaving: the **call chain**
(`A2A_MAX_CHAIN=8` steps, with `A2A_MAX_REENTRY=3` repeats of one agent+skill
on the same path — the pair is what refuses A→B→A→B while still permitting a
long honest negotiation), **budget** (`A2A_MAX_HANDOFFS=20` calls per user
turn), and **duplicate suppression** (the same skill with the same input twice
in one turn is answered from the first result). Each is enforced by the
receiving agent against its own configuration, never against the number the
caller declared.

Time is bounded on the **turn**, not on each call: `A2A_TURN_TIMEOUT_SECONDS`
(900s), with every call granted whatever remains of it. A flat per-call
deadline made the outermost call the tightest bound in the system and killed
negotiations that were running normally.

### Elicitation belongs to the orchestrator

When the MCP servers raise a question only a human can answer — `'30 year'`
matches a nominal *and* a real series — the MCP agent does not ask. It stops its
task in `input-required`, carrying the required field names and the allowed
answers as structured data. The orchestrator turns that into one clarifying
question with clickable options, and the user's reply is relayed back into the
**same task id**, which resumes rather than restarting.

A reply that settles nothing — "30 year Treasury" to "nominal or real?" — is
neither an answer nor a refusal, so the task stays `input-required` and the
question is put again, up to `A2A_MAX_CLARIFICATIONS` times before the plan runs
on the tool's own labelled declined path. An explicit "cancel" ends the task
immediately. See [`docs/a2a.md`](docs/a2a.md).

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
| `DataLayerPort` | `A2ADataLayer` — the MCP agent, over A2A | — |
| A2A transport | in-process ASGI · HTTP | `A2A_TRANSPORT` |

`DataLayerPort` is what keeps the discussion's *rules* apart from the transport
that carries it: `agents/planning.py` holds the round limit and the convergence
test and knows nothing about tasks, cards or protobufs.

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
      tables, data_plan, negotiation, catalogue, calculation, langsmith_url,
      handoffs}
POST /summarise {messages} -> {title}
GET  /health    -> {..., a2a: {transport, protocol_version, agents, limits}}

GET  /a2a/<agent>/.well-known/agent-card.json     discovery
POST /a2a/<agent>/                                JSON-RPC (agents only)
```

The service reaches the agents only by sending an A2A message to the
orchestrator. The three agent endpoints are mounted here so each agent is
genuinely addressable and discoverable; they are not a second route to the data,
because the specialists' caller allow-lists reject the user boundary.

The agents are stateless between turns; **the service owns session memory** —
the last twelve turns, a `clarified` flag that stops a second consecutive
question, and the id of any specialist task left waiting on a human, which is
the correlation a resumed A2A task needs.

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
- Docs are **executable analytical contracts**: Definition → When to use →
  Required inputs (canonical concepts) → Observation window → Calculation (the
  real MCP tool) → Assumptions → Output → Limitations → **Mapping status**. The
  `market_risk` docs follow this, aligned to the real data (`analytics.*`,
  `demo.*`) and the real risk tools (`compute_historical_risk_tool`,
  `compute_dv01_tool`, `run_stress_tool`). The *Mapping status* table records, per
  capability, whether every required input resolves — and therefore whether the
  mode is **Calculate + Explain** or **Explain-only** (e.g. CVA/RWA have no
  counterparty data, so they explain but never compute).
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

- **A2A layer** — `a2a-sdk` 1.1.2, protocol 1.0. Three cards, nine skills, real
  JSON-RPC endpoints, the full task lifecycle including `input-required`, and
  guardrails on depth, budget, duplicates, timeout and cancellation.
- **Data layer** — PostgreSQL with the real Treasury rates (267,517 rows), verified.
- **Knowledge layer** — Qdrant with 71 chunks, running in Docker.
- **MCP layer** — two stdio servers plus the host, on protocol revision 2026-07-28,
  exercising **all six primitives**: tools, resources, prompts, elicitation, roots
  and sampling. `DATA_BACKEND=mcp` routes the agents through them.
- **Reasoning layer** — the three agents above, behind `/chat`, reading through both
  seams.
- **Evaluation** — 13 cases × 11 scorers on LangSmith, scoring behaviour rather than
  answers.
