# Rules for the A2A layer

`agents/a2a/` — the protocol boundary between the three runtime agents.
Background: `docs/a2a.md`. The agents' own behaviour is `.claude/rules/reasoning-layer.md`.

## There are three agents

Orchestrator, domain expert, MCP agent. Adding a fourth is a design change, not
a convenience — a router, a planner, a supervisor or a judge would each split a
responsibility one of these three already owns, and a card is the only thing
that makes something an agent here.

Not agents, and must not acquire cards: `mcp_servers/host/agent.py` (a
standalone loop for exercising MCP without the backend), `McpHost`,
`RiskWorkflows`, `KnowledgeBase`, the `DataProvider` implementations, the
sampling callback.

## Protocol stays out of behaviour

Only `agents/a2a/` may import `a2a.types`, `a2a.client` or `a2a.server`. An
agent module takes and returns the dataclasses in `agents/contracts.py`.

`agents/pipeline.py` may not import `DomainExpertAgent` or `McpAgent`. A test
asserts this against the parsed import graph, because A2A is decorative if the
caller can still reach the callee directly.

That is the weaker half. The stronger half is `ExecutionContext`: each executor
publishes the task it is running before handing work to a worker thread, and an
integration test requires every specialist execution to carry one whose task id
appears in the handoff ledger. Keep it working — if you add a path that runs
specialist domain code, it has to run inside an executor.

The specialists are not public attributes of `AgentNetwork`. Reaching one means
sending it a message.

Rules that govern a conversation live in `agents/planning.py` against
`DataLayerPort`; the A2A implementation of that port is `agents/a2a/ports.py`.
Keeping them apart is what makes the round limit testable without a network.

## The card is the contract

A skill id is checked against the target's card before an executor sees it. So:

- Add a skill to `cards.py` **and** handle it in `executors.py`, in the same
  change. Half of that pair is a request that fails at the boundary or a branch
  nothing can reach.
- Describe what the skill actually does. "Can answer questions" is not a
  contract; a test rejects skill descriptions under 80 characters and skills
  with no tags.
- Never advertise a capability the server does not implement. `streaming` is
  `false` because streaming is not implemented, and a client that subscribes to
  a stream nobody produces waits forever.

## Only the orchestrator speaks to a user

Every skill names its permitted callers in `executors.py`. `user-boundary` — the
FastAPI service acting for the human — appears on the orchestrator's skills and
nowhere else.

A specialist that needs a decision returns `input-required` carrying the field
names and the allowed answers as structured data. It does not ask, does not
print, and does not call the orchestrator. The MCP host's `prompt` elicitation
mode is for the standalone CLI only; the agent stack runs `relay`.

**An answer that settles nothing is not a refusal.** Ask again, on the same
task, up to `A2A_MAX_CLARIFICATIONS` times; then run the tool's own declined
path and finish. Terminating on the first unmatched reply throws away a request
the user still wants; asking without a bound is the user-facing twin of an
unbounded agent loop. Refusal is an explicit word list matched on word
boundaries — never inferred from vagueness.

Every clarification path must end in a terminal state. If you add one, add the
bound with it.

## Bounds are code, not prompts

Chain length, re-entry, handoff budget, duplicate suppression, clarification
retries, negotiation rounds, consecutive no-change rounds, turn deadline. Each
is checked by the *receiving* agent against its own configuration, never
against a number the caller supplied — a caller is not a trustworthy source for
the limit it is being held to.

**Bound progress, not only length.** `MAX_NEGOTIATION_ROUNDS` caps how long a
conversation may run; `MAX_UNCHANGED_ROUNDS` caps how long it may run *without
getting anywhere*. `_describe_changes` already diffs each revision to prove a
round did something — read that answer rather than only recording it, or a
stalled negotiation spends its full ceiling to end where it began.

**Do not collapse chain length and re-entry back into one depth counter.** They
stop different faults. Length bounds how far a collaboration goes; re-entry
bounds how often the same agent and skill appear on the same path, which is
what a cycle actually looks like. One number tuned to catch `A→B→A→B` refuses
honest four-step negotiations, and one tuned to permit those lets the cycle run
to the limit. The chain is carried as the path itself, so a refusal can name
the loop rather than reporting that some number was reached.

**Do not reintroduce a flat per-call deadline.** A call contains every call
beneath it, so one number applied at every depth makes the outermost the
tightest bound and it expires first by construction. Bound the turn; let each
call take what remains of it. Hangs are caught where they happen — the model
layer bounds every provider request.

Duplicate suppression is loop prevention, **not a cache**. Its store lives on
the `TurnLedger` and dies with the turn, and only skills tagged `idempotent` on
their own card are eligible. Tagging a data fetch or a calculation idempotent to
save a call is the moment it becomes a cache and starts serving one user's
numbers to another.

**Send a skill only what it reads.** The digest covers the whole input, so a
field the callee ignores still breaks the match — `assess_data_requirement` was
tagged idempotent and never once fired, because it was handed the full
requirement including `warnings`, which grows every round. Add a projection
(`Requirement.as_capability_request`) rather than widening the digest.

Projections must stay honest: the receiver rebuilds the dataclass, so a dropped
field comes back as its **default**, not as absent. Omitting `warnings` says
"none shown"; omitting `grounded` would assert `False` about an expert that had
grounded its citation. Drop what is unread *and* harmless as a default; keep
the rest.

Caller allow-lists are **internal caller authorization** — a logical boundary
inside one trusted process, from caller-supplied metadata. Do not describe them
as authentication, and do not add OAuth, JWT or mTLS to make the description
true; a local system does not need it.

The turn ledger is opened once, at the user boundary, and found by id everywhere
else. An agent that opens its own resets the count and makes the turn limit
unenforceable at the point it matters.

## Nothing raw reaches the browser

An exception becomes a `failed` task with a structured `error` artifact. The
user-facing sentence is written from the error *kind*, never from its message —
an exception string carries hosts, ports and internal identifiers.

A task that comes back still `working` is not an answer. Treat a non-settled
state as a failure; reporting it as success is how an empty result looks like a
successful one.

## Integers do not survive JSON

`Part.data` is a `google.protobuf.Value`, so `250` returns as `250.0`. Every
typed rebuilder in `envelope.py` coerces its own integer fields, and
`restore_counts` handles the free-form structures. If you add a count-like key,
add it to `COUNT_KEYS` — otherwise it reaches a user-visible sentence as
"250.0 observations".

## Domain work never runs on the event loop

Executors hand their agent's work to a worker thread. That is what makes the
nested call possible: while the domain expert thinks, the loop must be free to
serve the MCP agent call it is about to make. An executor that awaits blocking
work directly deadlocks the discussion.
