# A2A payloads and record volume — research report

**Status: research only. No A2A code was changed for this document.** It answers
what A2A actually transmits, whether the protocol defines a record limit, what
this system's real limits are and where they come from, and how the gateway
should carry large results if it ever needs to.

Every version, field name and byte count below was read from the installed SDK
or measured against this repository's own payloads, not recalled.

---

## A. What A2A actually transmits

Installed here: **`a2a-sdk` 1.1.2**, protocol revision **1.0**, proto-derived
types (`a2a.types.a2a_pb2`), JSON-RPC binding, in-process ASGI transport
(`A2A_TRANSPORT=inprocess`).

### The five things on the wire

| Concept | Proto fields | What this system puts in it |
|---|---|---|
| **Message** | `message_id`, `context_id`, `task_id`, `role`, `parts`, `metadata`, `extensions`, `reference_task_ids` | One skill request or one agent reply. The skill id, caller, call chain, handoff budget and LangSmith headers travel in `metadata` (`agents/a2a/envelope.py`). |
| **Part** | `text`, `raw`, `url`, `data`, `metadata`, `filename`, `media_type` | Prose goes in `text`; every structured payload goes in `data`. |
| **Artifact** | `artifact_id`, `name`, `description`, `parts`, `metadata`, `extensions` | The named results: `requirement`, `negotiation`, `catalogue`, `citations`, `dataset`, `calculation`, `completeness`, `error`, … |
| **Task** | `id`, `context_id`, `status`, `artifacts`, `history`, `metadata` | One unit of work with a lifecycle. `context_id` is the conversation; `id` is the correlation an interrupted plan resumes on. |
| **TaskState** | 9 values | `SUBMITTED`, `WORKING`, `COMPLETED`, `FAILED`, `CANCELED`, `INPUT_REQUIRED`, `REJECTED`, `AUTH_REQUIRED`, `UNSPECIFIED`. |

### The one fact that shapes every payload decision

`Part.data` is a **`google.protobuf.Value`**. That is JSON's type system, not
Python's, and it has three consequences this repo has already been bitten by:

1. **There is no integer type.** `250` returns as `250.0`. `agents/a2a/envelope.py`
   re-integers count-like keys (`COUNT_KEYS`) for exactly this reason, and
   forgetting to add a new key surfaces as "250.0 observations" in a sentence a
   user reads.
2. **There is no binary type.** `Part.raw` is `bytes` and `Part.url` is a
   reference, but a `data` part cannot carry binary — a large array becomes a
   list of JSON numbers, which is roughly 3–5× the size of the same data packed.
3. **Structure costs.** Every row of a table repeats its own list brackets and
   separators.

### Streaming

`AgentCapabilities` has a `streaming` field, and **this system sets it `false`**
(`agents/a2a/cards.py`) because streaming is not implemented. That is the correct
pairing: a card advertising a stream no server produces leaves a subscribing
client waiting forever. `ClientConfig(streaming=False)` in
`agents/a2a/runtime.py` matches it.

So A2A *supports* streamed task updates; **this deployment does not use them**,
and the live progress the UI now shows travels over SSE from the FastAPI service
instead — a separate, one-directional channel that does not require changing the
agent contract.

---

## B. Does A2A define a record limit?

**No. The A2A specification defines no record count, no row count, and no
payload size limit of any kind.** There is nothing in the protocol that says
1,000 records is legal and 10,000 is not. The word "record" does not appear in
its data model: A2A carries *messages, parts, artifacts and tasks*, and a
"record" is whatever an application chooses to put inside a `data` part.

Any limit you hit is therefore contributed by one of six layers, and they fail
differently. Naming which one is what makes a limit fixable:

| Layer | Limit | Where it comes from | Fails as |
|---|---|---|---|
| **A2A specification** | **none** | — | — |
| **SDK** | none imposed by `a2a-sdk` 1.1.2 | proto serialisation cost only | slow, then memory |
| **Transport** | none in-process; gRPC's default 4 MiB receive cap and any proxy `client_max_body_size` apply over a socket | `httpx.ASGITransport` today | `RESOURCE_EXHAUSTED` or HTTP 413 |
| **Serialisation** | practical | `google.protobuf.Value`: JSON types, no binary | CPU and memory, not an error |
| **Memory** | practical | every artifact is fully materialised in the sending and receiving process | OOM, or GC pressure |
| **Application** | **real, and the binding one here** | `MAX_DISPLAY_ROWS = 500`, `SAMPLE_ROWS = 60` (`agents/mcp_agent.py`) | a truncated table, honestly labelled |
| **Model context** | **the actual ceiling** | a table pasted into a prompt | truncation, or nonsense |

**The binding constraint in this system is the application one, and it is
deliberate.** `_table()` caps the rows carried at 500 and sets
`truncated: true` with the real `row_count` beside it, so the calculation reads
every row while the artifact carries a reviewable sample. The full count is
never misrepresented.

---

## C. Measured payload sizes for this system

Measured against this repo's own contracts, not estimated:

| Payload | Size |
|---|---|
| `requirement` artifact (realistic VaR plan, 6 citations) | **1,536 B** |
| `as_capability_request()` projection of the same | **889 B** |
| `dataset` artifact, 3 columns | **~53 B/row** |

Extrapolating that per-row cost:

| Rows | JSON size | Verdict |
|---:|---:|---|
| 10 | ~0.5 KB | inline |
| 100 | ~5 KB | inline |
| 1,000 | ~53 KB | inline, comfortably |
| 10,000 | ~0.5 MB | inline works; already too big for a prompt |
| 100,000 | ~5 MB | over gRPC's 4 MiB default; needs a reference |
| 1,000,000 | ~51 MB | must be a reference |

A useful sense of scale: **the entire Treasury dataset is 267,517 rows**, so
"one million records" is not a real workload for this gateway — it is more rows
than exist.

---

## D. How large data *should* travel, per volume

The principle: **A2A coordinates agents; it is not a bulk data bus.** An agent
message should carry the *decision* and a *reference*, because that is what the
receiving agent reasons over. A model cannot read 100,000 rows, so shipping them
to an agent buys nothing and costs everything.

| Rows | Strategy | Why |
|---|---|---|
| ≤ 1,000 | **Inline** in a `data` part | Under ~53 KB. Simple, and every agent can act on it directly. |
| 1,000 – 10,000 | **Inline a summary + a bounded sample** | What the code already does: 500 rows carried, true `row_count` beside them, `truncated` set. The agent reasons about the summary; the human reviews the sample. |
| 10,000 – 100,000 | **Reference, not payload** — an artifact carrying a snapshot id, a row count, a schema and a fetch handle | Past this point the receiving agent cannot use the rows and the transport starts to. |
| > 100,000 | **Reference only, computed at the source** | Move the computation to the data, not the data to the computation. The risk engine already works this way. |

### What that would look like here, concretely

The gateway is already shaped for it and does not need an A2A change:

- **`_meta` already exists.** `call_tool_with_meta` in
  `backend/src/backend/providers/mcp.py` returns MCP `_meta` separately —
  that is where bulk arrays already travel, *outside* the agent conversation.
- **The risk engine already takes the reference path.** `compute_var` sends a
  curve-history *matrix* to a tool and gets a *figure* back; the 250×N history
  never enters an agent message.
- **The missing piece is snapshot identity.** `docs/redis.md` already records
  why MCP execution is not cached: providers expose no immutable snapshot id.
  The same gap is what a reference-passing artifact would need — a
  `dataset_snapshot_id` a second agent could resolve and be certain it read the
  same bytes.

**Recommendation: do not build reference-passing yet.** The largest real result
is 267,517 rows and no current question asks for more than a few thousand. The
prerequisite is snapshot identity, and adding a reference scheme without it
would let two agents disagree about what "that dataset" means — a worse failure
than a big payload, because it is silent.

---

## E. Current project constraints, named by layer

| Constraint | Value | Layer | Assessment |
|---|---|---|---|
| Transport | in-process ASGI | application | No socket, no proxy, no body cap. Over `A2A_TRANSPORT=http` a proxy body limit would appear. |
| `httpx` timeout | `None` | application | Correct: the deadline is the turn's, enforced by the ledger. |
| Turn deadline | 900 s | application | `A2A_TURN_TIMEOUT_SECONDS`. |
| Handoff budget | 20 | application | Worst measured real turn: 13 with the new gate hop. Headroom is real. |
| Chain / re-entry | 8 / 3 | application | Unrelated to payload size. |
| Rows carried | 500 | application | `MAX_DISPLAY_ROWS`. The binding limit, and deliberate. |
| Integer fidelity | `COUNT_KEYS` | serialisation | A count-like key not on that list reaches a user as `250.0`. |
| Model context | provider-dependent | LLM | The real ceiling on how much data an *agent* can use. |

### Recommendations

1. **Keep A2A for coordination.** Nothing measured suggests moving bulk data
   into agent messages; every payload here is under 2 KB except the dataset,
   which is capped on purpose.
2. **Before enabling `A2A_TRANSPORT=http`**, set an explicit body limit at the
   proxy and decide what a 413 should say to a user. In-process today hides this.
3. **Add snapshot identity first** if reference-passing is ever wanted. It is
   the prerequisite for both this and the MCP result caching `docs/redis.md`
   defers.
4. **Keep `streaming: false`** until a streaming server exists. The live
   progress requirement was met with SSE from the service, which needed no
   change to any agent card.
5. **When adding a count-like key to any artifact, add it to `COUNT_KEYS`.**
   This is the one payload defect that reaches a user as a wrong-looking number
   rather than as an error.
