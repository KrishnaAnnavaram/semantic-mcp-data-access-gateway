# A2A — how the three agents talk to each other

The three runtime agents are independently addressable A2A services. Every call
between them is an A2A task over JSON-RPC, not a Python method call.

**A2A and MCP solve different problems and both are load-bearing.** A2A carries
*agent-to-agent* traffic: a request for a capability another agent advertises,
and the task that answers it. MCP carries *tools, resources and data*: the
Treasury database and the risk engine, behind a privilege boundary the agents
cannot cross. Neither replaced the other, and the MCP layer is untouched below
its own agent.

```
                              USER
                                │
                                ▼
                       React frontend
                                │  POST /chat   (unchanged contract)
                                ▼
                             FastAPI
                                │  A2A: handle_user_turn
                                ▼
                         ORCHESTRATOR ─────────────────────┐
                                │                          │
                                │ A2A                      │ A2A
                                ▼                          ▼
                         DOMAIN EXPERT ────── A2A ────► MCP AGENT
                                │      catalogue,           │
                          Qdrant │      assess               │ MCP
                                ▼                           ▼
                          knowledge/                  market-risk-data-mcp
                                                      risk-engine-mcp
                                                            │
                                                            ▼
                                                       PostgreSQL
```

SDK: **`a2a-sdk>=1.1.2`**, protocol version **1.0**, JSON-RPC binding.

## Addresses

| Agent | Mount | Card | JSON-RPC |
|---|---|---|---|
| `orchestrator` | `/a2a/orchestrator` | `/a2a/orchestrator/.well-known/agent-card.json` | `POST /a2a/orchestrator/` |
| `domain-expert` | `/a2a/domain-expert` | `…/.well-known/agent-card.json` | `POST /a2a/domain-expert/` |
| `mcp-agent` | `/a2a/mcp-agent` | `…/.well-known/agent-card.json` | `POST /a2a/mcp-agent/` |

Mounted on the existing FastAPI service. One process, one port, three real
addresses. `GET /health` reports the mounts, the protocol version and the
guardrail limits.

```bash
curl -s localhost:8000/a2a/mcp-agent/.well-known/agent-card.json | jq '.name, [.skills[].id]'
```

The endpoints are registered at startup and the agents behind them are built on
the first request that arrives — so a card is fetchable from a service that has
not yet answered a `/chat`, without paying vector-store and MCP child-process
startup at import.

**Transport is configuration.** `A2A_TRANSPORT=inprocess` (default) dials the
mounted apps through httpx's ASGI transport — real JSON-RPC, real serialisation,
real task lifecycle, no second port. `A2A_TRANSPORT=http` with `A2A_BASE_URL`,
or a per-agent `A2A_ORCHESTRATOR_URL` / `A2A_DOMAIN_EXPERT_URL` /
`A2A_MCP_URL`, dials over the network instead. The client code is identical
either way; moving one agent onto its own host is an environment variable.

## Skills

Skill ids are load-bearing: a request names one, and `envelope.py` refuses any
skill the target's card does not advertise. A card cannot drift from the code
without a request failing loudly.

| Agent | Skill | Callable by | Returns |
|---|---|---|---|
| orchestrator | `handle_user_turn` | the service, for the user | `outcome` |
| orchestrator | `relay_user_input` | the service, for the user | `outcome` |
| orchestrator | `summarise_session` | the service, for the user | `title` |
| domain-expert | `derive_data_requirement` | orchestrator | `requirement`, `negotiation`, `catalogue`, `citations` |
| mcp-agent | `describe_data_capabilities` | domain-expert, orchestrator | `catalogue` |
| mcp-agent | `assess_data_requirement` | domain-expert | `serve_response` |
| mcp-agent | `execute_data_plan` | orchestrator | `dataset`, `calculation`, `summary` |
| mcp-agent | `list_data_choices` | orchestrator | `choices` |
| mcp-agent | `provide_input` | orchestrator | `dataset`, `calculation`, `summary` |

**Only the orchestrator accepts the user boundary.** Each executor checks the
calling agent against a per-skill allow-list, so a browser that finds
`/a2a/mcp-agent/` is rejected rather than served:

```
'user-boundary' may not call mcp-agent.execute_data_plan;
that skill is served to ['orchestrator'].
```

A specialist calling `orchestrator.handle_user_turn` — the shape a "let me just
ask the user" bypass would take — is rejected by the same mechanism.

Be precise about what this check is. It is **internal caller authorization**: a
logical boundary between components inside one trusted process, read from
metadata the caller supplied. It is *not* authentication — nothing verifies that
a message claiming to come from the orchestrator did. For a local-development
system where the three agents share a process behind one developer's service,
that is the right weight: it makes the architecture enforceable and reviewable
without claiming a security property it does not have. Exposing an agent on a
host other people can reach is the point at which real authentication would be
required, and that is a deployment change.

## Task lifecycle

States are the SDK's own: `submitted`, `working`, `input-required`, `completed`,
`failed`, `canceled`, `rejected`. Each hop is its own task with its own id;
every task in one user turn shares the **context id**, which is the chat
session, so a whole multi-agent turn is recoverable from a task listing.

A caller may act only on a *settled* state. A task that comes back still
`working` is a progress report, and treating it as an answer is how an empty
result gets reported as a successful one — so it is turned into a failure with
the reason attached.

## Elicitation, mediated by the orchestrator

MCP elicitation exists because some choices cannot be made by a server: the
query `'30 year'` matches `BC_30YEAR` and `TC_30YEAR`, a nominal par yield and a
real yield, and the information needed to choose is in the caller's head.

Previously the MCP host answered that question itself — declining when headless,
or prompting on a terminal when a human happened to be at one. Both bypass the
orchestrator, and the terminal prompt is a channel to the user the system cannot
see. Now:

```
  data server ──elicitation──► MCP host ──relay──► MCP AGENT
                                                       │
                                     A2A task state: input-required
                                          (+ required_information, schema)
                                                       ▼
                                                ORCHESTRATOR
                                                       │
                                        /chat: question + clickable options
                                                       ▼
                                                     USER
                                                       │
                                                ORCHESTRATOR
                                                       │
                                    A2A: provide_input on the SAME task id
                                                       ▼
                                                   MCP AGENT ──► resumes
```

* `InteractionPolicy.elicitation = "relay"` records the server's question and
  declines that round so the call ends cleanly, leaving the session healthy.
* `McpDataProvider.input_scope()` collects any question raised anywhere inside a
  block of work — including tool calls made three frames down by
  `RiskWorkflows` — and supplies the user's earlier answer when there is one.
* The MCP agent's task stops in `input-required`; the orchestrator turns it into
  an ordinary clarifying question and holds the task id against the session.
* The user's reply is matched against the schema's enum **deterministically**,
  not by a model: the allowed answers are a list the server supplied, and asking
  a model to pick from a list it was given is a way to occasionally get
  something that is not on the list.

### An answer that settles nothing is not a refusal

A user who answers `30 year Treasury` to "nominal or real?" has said something
true that does not answer the question. Terminating there discards a request
they still want served, so the reply is sorted into one of four cases, in order:

| Reply | What happens |
|---|---|
| `cancel`, `never mind`, `stop` | task → `canceled`; nothing fetched, nothing chosen |
| names an allowed value | task resumes → `working` → `completed` |
| answers nothing, retries left | task stays `input-required`; the question is put again |
| answers nothing, retries spent | the plan runs on the tool's own labelled declined path → `completed` |

The re-ask is written from facts, not repeated verbatim: it names the field
still needed, quotes the reply that did not settle it, and lists the allowed
answers. `A2A_MAX_CLARIFICATIONS` (default **3**) bounds it — four chances in
all. An unbounded clarification loop is the same defect as an unbounded agent
loop; it just wears the user down instead of the budget.

Refusal is matched on an explicit word list, on word boundaries. Vagueness is
never read as consent to stop — inferring refusal from "I am not sure" would
kill exactly the conversations the retry exists for.

`prompt` mode is still there for the standalone host CLI
(`python -m mcp_servers.host --ask`), where there is no orchestrator and the
terminal genuinely is the user.

## Guardrails

Five independent bounds, because five different things run away.

| Bound | Default | Variable |
|---|---|---|
| Call-chain length | 8 | `A2A_MAX_CHAIN` |
| Re-entries of one agent+skill | 3 | `A2A_MAX_REENTRY` |
| A2A calls per user turn | 20 | `A2A_MAX_HANDOFFS` |
| Whole-turn deadline | 900s | `A2A_TURN_TIMEOUT_SECONDS` |
| Negotiation rounds | 5 | `agents/planning.py: MAX_NEGOTIATION_ROUNDS` |

### Why a turn budget and not a per-call deadline

There used to be a flat 300s deadline applied identically at every depth, and
it was structurally wrong rather than mistuned. A call **contains** every call
beneath it, so a flat number makes the outermost call the tightest bound in the
system — it expires first, by construction.

That is not hypothetical. In a real turn `derive` took 80s and `assess` took
78s, both legitimately (the provider retried a broken output contract each
time). The orchestrator's own 300s deadline then fired mid-revision and
reported a turn that was proceeding normally as hung. Raising the number would
only have moved the same failure further out.

Every call is now bounded by **what remains of the turn**, which nests
correctly: a child is always granted less than its parent, because time has
passed. Hang detection is not weakened — an agent hangs where it waits on the
network, and `LLM_TIMEOUT_SECONDS` already bounds every provider request. Each
guard now sits at the level where the fault it catches actually occurs.

### Why a chain and not a depth

A single depth counter was doing two jobs and doing neither well.

The **call chain** is the path a request has actually taken, recorded step by
step and carried in the envelope:

```
orchestrator.plan > domain-expert.derive > mcp-agent.assess > domain-expert.revise
```

Its **length** bounds how far a legitimate collaboration may go. Its **repeats**
bound how often the same agent and skill may appear on that one path, and that
is what catches a cycle. The two are genuinely different faults: a four-step
negotiation that never revisits an agent is healthy and a flat `max_depth=3`
refused it, while `A→B→A→B` is a cycle that a depth counter permits until the
number runs out. Recording the path instead of a count also means the refusal
can *name the loop* rather than reporting that some limit was reached.

Each agent checks the bound against **its own** configuration, never against the
number the caller declared. A caller that under-reports its chain is refused by
the receiver, which is the only place the check is worth anything.

Neither bounds breadth — one agent calling a peer with a fresh chain each time
stays under both — so the turn ledger caps total calls per user turn.

**Duplicate suppression is loop prevention, not a cache**, and its scope is
where that distinction lives. Identity is `(this turn, target agent, skill,
canonical input)`. The store is a field on the `TurnLedger`, which is created
when a user turn starts and discarded when it ends — so **nothing survives a
turn**, and a later independent question can never be answered with an earlier
one's data. Within a turn, only skills their own card tags `idempotent` are
eligible at all:

| Replayable within a turn | Always re-executed |
|---|---|
| `describe_data_capabilities` | `execute_data_plan` |
| `assess_data_requirement` | `provide_input` |
| `list_data_choices` | `handle_user_turn` |
| `derive_data_requirement` | `relay_user_input` |
| `summarise_session` | *(anything untagged)* |

The right-hand column reads the market, spends money, or continues a live task;
its answer is about *now*. Those calls are repeated however identical the
request, and a loop of them is bounded by the handoff budget rather than by
replay. The tag is read from the Agent Card, so what a caller can discover and
what the guardrail enforces cannot drift apart.

Suppressing a repeat is also the cheapest detector for a negotiation that has
stopped converging: a revision that changes nothing produces the same digest.

A call that overruns is cancelled (`tasks/cancel`) and reported. An unreachable
agent, a malformed reply, a rejected request and a failed task all arrive as the
same `SkillResult` shape, so a caller cannot mistake a transport fault for a
domain refusal.

Nothing raw reaches the browser. A specialist's exception becomes a `failed`
task with a structured `error` artifact; the orchestrator writes a sentence from
the *kind*, never from the message — `qdrant refused the connection at
10.0.0.1:6333` is an internal address, and it stays in the decision trace where
whoever debugs it will look.

## Observability

One `turn=<user_request_id>` correlates every hop:

```
a2a --> | turn=13ee69fb95db seq=1 depth=1 user-boundary -> orchestrator.handle_user_turn ctx=e2e-dv01
a2a exec | turn=13ee69fb95db orchestrator.handle_user_turn task=b0a0f7d6 depth=1 caller=user-boundary
a2a --> | turn=13ee69fb95db seq=2 depth=2 orchestrator -> domain-expert.derive_data_requirement
a2a --> | turn=13ee69fb95db seq=3 depth=3 domain-expert -> mcp-agent.describe_data_capabilities
a2a <-- | turn=13ee69fb95db seq=3 mcp-agent.describe_data_capabilities state=completed task=c2bd67f4 170ms
...
```

Set `A2A_LOG_LEVEL` (default `INFO`) when running
`python -m backend.api.service`; without a root handler uvicorn's logging
configuration swallows these.

The same ledger travels back on `/chat` as `handoffs` — an additive, optional
field the frontend can ignore — so a turn can be followed without reading logs.
No payload is logged; the existing redaction layer is untouched.

## Layout

Protocol and transport are kept apart from agent behaviour and from data access,
and the separation is visible in the tree:

```
agents/
  orchestrator_agent.py     domain behaviour  — imports no a2a
  domain_expert_agent.py    domain behaviour  — imports no a2a
  mcp_agent.py              domain behaviour  — imports no a2a
  planning.py               the bounded discussion, against a DataLayerPort
  pipeline.py               the orchestrator's workflow, over A2A only
  contracts.py              what the agents say to each other
  a2a/
    identity.py             agent ids, mount paths, transport selection
    cards.py                Agent Cards: skills and capabilities
    envelope.py             contracts <-> A2A messages and artifacts
    guardrails.py           depth, handoff budget, dedupe, timeouts, ledgers
    client.py               AgentLink: the calling half
    executors.py            AgentExecutors: the hosting half
    server.py               one ASGI app per agent
    ports.py                A2ADataLayer — DataLayerPort over A2A
    elicitation.py          input-required <-> a question a user can answer
    runtime.py              the network: agents, apps, clients, one loop
```

No agent module imports `a2a.types`. `agents/pipeline.py` imports neither
`DomainExpertAgent` nor `McpAgent` — a test asserts this against the parsed
import graph, because A2A is not A2A if the caller can still reach the callee
directly.

### Proving the absence of a bypass

An import test proves the caller cannot *name* the callee. It does not prove
that specialist work never ran through some other path, so there is a second,
stronger check.

Each executor sets an `ExecutionContext` — agent, skill, task id, context id,
correlation id — before handing its agent's work to a worker thread.
`asyncio.to_thread` copies the calling task's context, so the value is visible
exactly where the domain code runs and nowhere else; a nested A2A call runs in a
new task and sets its own.

The integration test then wraps every specialist domain method, runs a real
turn, and requires of each recorded execution that it had a context, that the
context names the right agent, and that its **task id appears in the turn's
handoff ledger** against that agent. A hidden direct call would execute with no
context at all, and fails on the spot. A companion test calls a specialist
directly and shows there is no context to find — the other half of the same
argument.

## Threading

One event loop on a daemon thread for the life of the process, mirroring the MCP
bridge and for the same reason: the agents are synchronous and called from
FastAPI's thread pool, while A2A is asyncio.

Each executor hands its agent's work to a **worker thread** (`asyncio.to_thread`).
That is what makes the nested call work — while the domain expert is thinking on
a worker thread, the loop is free to serve the MCP agent call that thinking is
about to make. The loop's default executor is sized explicitly, because one turn
can hold three worker threads at once.

## Running and checking

```bash
python -m backend.api.service                       # :8000, agents mounted
curl -s localhost:8000/health | jq .a2a             # transport, limits, mounts
curl -s localhost:8000/a2a/domain-expert/.well-known/agent-card.json
pytest tests/test_a2a.py                            # 30 tests, offline
```
