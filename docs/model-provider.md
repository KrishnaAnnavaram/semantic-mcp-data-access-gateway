# The model layer — one interface, many engines

How the reasoning layer reaches a model, why structured output is obtained the
way it is, and what was measured to decide the model allocation.

## The seam

```
    Agent / MCP host
         │
         ▼
    ModelProvider              structured_call · tool_turn · complete
         ├── AnthropicProvider     output_config.format.json_schema
         └── ZaiProvider           forced function call (OpenAI-compatible)
```

Selected by `LLM_BACKEND`, which **defaults to `zai`** — this project runs on
open weights unless told otherwise. `LLM_BACKEND=anthropic` returns it to
Claude, and that path is maintained, tested and evaluated rather than
decorative (72/73 on the same suite).

A checkout with only an `ANTHROPIC_API_KEY` therefore refuses to start the model
layer instead of quietly billing a different vendor than the one configured; the
error names both ways out.

Chosen exactly as the repository's two existing seams are:

| Seam | Implementations | Chosen by |
|---|---|---|
| `DataProvider` | Mcp · Postgres · Mock | `DATA_BACKEND` |
| `VectorStore` | Qdrant server · embedded | `QDRANT_URL` |
| **`ModelProvider`** | **Anthropic · Zai** | **`LLM_BACKEND`** |

`llm/` is the **lowest distribution in the repository** and imports none of the
others. That is deliberate: `python -m mcp_servers.host --ask` must keep working
with no backend, no Qdrant and no UI, which it could not if the model seam sat
above it. `tests/qa/test_qa_tier1_foundations.py` asserts the direction, and it
is the reason `llm/config.py` carries its own fifteen-line `.env` reader rather
than importing `treasury_db`.

## Model allocation

Per call site, not per provider. Routing a greeting and grounding a market-risk
requirement are different problems.

| Call site | `LLM_BACKEND=zai` *(default)* | `LLM_BACKEND=anthropic` | Override |
|---|---|---|---|
| Orchestrator | `glm-5.2` | `claude-haiku-4-5` | `ORCHESTRATOR_MODEL` |
| Sampling | `glm-5.2` | `claude-opus-5` | `SAMPLING_MODEL` |
| MCP agent | `glm-5.2` | `claude-opus-5` | `MCP_AGENT_MODEL` |
| Host agent | `glm-5.2` | `claude-opus-5` | `HOST_AGENT_MODEL` |
| Domain expert | `glm-5.2` | `claude-opus-5` | `DOMAIN_EXPERT_MODEL` |

### Why the orchestrator is not on the cheap model

The migration specified `glm-4.5-air` for routing. Measured against the
orchestrator's real eight-field schema it scored **2/8**, versus **8/8** for
`glm-5.2`, and the two "passes" were only the safe default firing.

The cause is not reasoning. `glm-4.5-air` chose the right route and then could
not serialise `requested_rows: integer | null`:

```
0.0            where null was meant
10000.0        where 10000 was meant
1.25e-08       noise
5034904145...  a 1,000-digit integer
```

A corrective retry did not change it. Every failure collapsed into
`data_request` — safe, but it destroys the cheap path the split exists to
protect: a greeting would reach Qdrant and frontier-tier reasoning. `glm-5.2` is
also *faster* here (60s vs 82s over eight calls) because it needs no retries.

### Sampling runs the same model, and needs a bigger floor for it

`glm-4.5-air` is the cheaper fit for sampling on paper — plain prose, no schema,
and **no reasoning tokens at all**, so a small server-set ceiling is never eaten
by thinking. The shipped default is nevertheless `glm-5.2` everywhere: one model
to reason about, one latency profile, one set of quirks.

That choice has a measured consequence. The MCP data server sets the sampling
ceiling at **400 tokens** and cannot know what the client's model costs to
*think*. With the floor at 1024:

```
glm-5.2 → 755 reasoning, 278 visible     ok
glm-5.2 → 1022 reasoning,  0 visible     EMPTY
```

An empty completion is not a short answer — the tool falls back to
`[no briefing returned by the client's model]`. `_MIN_TOKENS[SAMPLING]` is
therefore **2048**, verified over four consecutive runs with reasoning peaking at
1,317 tokens and no empty completion. **Do not lower it without re-measuring.**

## Structured output: forced tool calls, not `response_format`

**Z.AI's `response_format={"type": "json_schema", "strict": true}` is not
treated as a guarantee in this project.** Measured against the live endpoint, it
answers HTTP 200 and then ignores the field names:

```
asked for : {"rows": int, "grounded": bool, "quote": str}
received  : {"rows_required": 250, "quoted_sentence": "..."}
```

Valid JSON. `json.loads` succeeds, nothing raises, two fields are renamed and
one is dropped, every `.get()` downstream returns `None`, and the system reports
that the corpus is silent while the model had in fact found and quoted the
answer. **A silent wrong answer is the worst outcome available.**

So `ZaiProvider` obtains structure the way GLM actually honours it:

```
schema
  ↓  forced function definition   tools=[…], tool_choice={"name": …}
GLM tool call
  ↓  arguments
sanitise (leaked stop tokens, unbalanced brackets)
  ↓  json.loads
STRICT SCHEMA + TYPE VALIDATION      ← the guarantee
  ↓
grounding validation                 ← separate, and still the agent's job
  ↓
trusted result
```

### Parsing is not validation

`llm/validation.py` rejects everything below. Each one is valid JSON:

| Sent | Rejected because |
|---|---|
| `{"rows": 250}` | required fields missing |
| `{"rows_required": 250, …}` | renamed field (`additionalProperties: false`) |
| `{"rows": 250.0125}` | float where integer required |
| `{"rows": 250.0}` | **whole float** where integer required |
| `{"rows": "250"}` | string where integer required |
| `{"rows": true}` | bool is not an integer |
| `{"route": "quant"}` | outside the enum |
| prose, no tool call | the forced call was not made |

The whole-float case matters more than it looks. JSON Schema treats `250.0` as a
valid integer because its fractional part is zero — correct by the specification
and wrong here, because the value continues into the application as a Python
`float` and a row count of `0.0` is not the `None` the model meant. `llm`
therefore redefines `integer` to mean a Python `int`, `bool` excluded.

### One corrective retry, and only one

A **deterministic** contract failure — a schema violation, or prose where a call
was forced — gets exactly one retry carrying the validator's message. Transport
failures are never retried here; the SDK already does that, and retrying an
expensive reasoning request on a timeout is how a retry storm starts. If the
second attempt fails, the violation stands and the caller degrades visibly.

### The serialisation defect that is repaired

`glm-4.5-air` was observed leaking its own stop token into the arguments string
and losing the closing brace:

```
{"route":"direct","requested_rows":-1.0
</tool_call>
```

`sanitise_arguments()` truncates at the sentinel and closes open brackets,
respecting string literals so a `}` inside a string is not mistaken for a
closer. It repairs **structure only and can never add a value**; a repaired
object that is still wrong is rejected by the validator like any other.

## Three defects this migration exposed

None was a prompt problem, and none would have been visible without strict
validation — each produced syntactically valid output that was semantically
wrong, which is exactly the failure mode the seam exists to catch.

### 1. The string `"null"`

`unsupported_calculation`, declared `["string","null"]`, came back from glm-5.2
as the four-character string `"null"` — on every attempt, deterministically. A
valid string, so validation passed it. Then:

```python
if response.feasible and not blocking and not response.unsupported_calculation:
```

`"null"` is truthy, so **the discussion could never converge on any question**.
One bug, five failing evaluation cases, and a negotiation that always ran to the
round limit.

Fixed by `normalise_nullables()`, scoped to fields whose schema actually permits
null: a string field that cannot be null keeps the word verbatim, and `""` is
never collapsed because an empty counter-proposal is a real value.

### 2. Internal identifiers in user-facing prose

A scope refusal named seven functions from this repository. Every fact in the
sentence was true; it was still the wrong sentence. Both agents are shown the
tool catalogue — the domain expert to judge what the source can hold — so both
*can* copy an identifier into prose.

Fixed in `agents/redaction.py`, applied at the pipeline's three user-facing
exits. Substitution rather than deletion (`compute_dv01` → "DV01"), so the
sentence the model built still reads. Names are taken from the **live**
catalogue, so a tool added tomorrow is covered without anyone remembering.

### 3. The grounding guard failing on markdown

The corpus is markdown, and the sentence to cite is written
`**250 trading days**`. A model that reproduced the asterisks was grounded; one
that quoted the identical sentence as plain prose had its correct citation
**discarded as ungrounded**.

That is the guard failing on typography rather than substance, and it fails
*toward* the outcome the design exists to prevent — an agent whose honest quotes
keep being rejected has no way left to justify a number. `_normalise()` now
strips emphasis from both sides, which leaves the check exactly as strict: a
paraphrase still does not appear in the source. `tests/test_grounding_guard.py`
pins both halves.

## Grounding is a separate layer

Structural validity and semantic grounding are different questions, and
collapsing them into one check loses both.

```
model output → schema/type validation → quote/value grounding → business logic
```

`quote_is_grounded()` is untouched by this migration and still discards a row
count whose citation is not present in the retrieved text. During the migration
evaluation it fired against `glm-5.2` and logged
`ungrounded row count 250 discarded` — the honesty contract holding under a new
engine, which is exactly what it is for.

**No domain value is assumed anywhere.** `250` was a smoke-test number, not an
architectural constant; the corpus states the window and the corpus can change
it. `tests/test_model_provider.py` asserts the integer literal `250` appears
nowhere in `llm/`, and parameterises the carry-through test over
30 · 60 · 90 · 125 · 250 · 365 · 500 · 750.

## Timeouts and token budgets

`LLM_TIMEOUT_SECONDS` (default **300**) is the wall clock for **one model
call**. It is not the same thing as `AGENT_TIMEOUT_SECONDS`, which lives in the
frontend and bounds the **entire** `/chat` request — orchestrator, retrieval,
the bounded discussion and execution together. Raising the per-call timeout to
300s is safe because the call is still bounded, the discussion is still capped
at three rounds, and the host loop is still capped at `MAX_STEPS`.

`max_tokens` has a per-call-site **floor**, raised toward but never lowered from
what a caller asks for. Reasoning models bill thinking against the same budget:
`glm-5.2` spent 13 of 16 tokens, and 100 of 200, on reasoning, so a tight
ceiling returns an *empty* completion rather than a short one. This matters most
for MCP sampling, where the **server** sets the ceiling (400) and cannot know
what the client's model costs to think.

## Adding a third provider

Implement the Protocol in `llm/base.py`, add one line to `llm/factory.py`, and
add its defaults to `_DEFAULT_MODELS`. Nothing in any agent changes — that is
the test of whether the seam is real.
