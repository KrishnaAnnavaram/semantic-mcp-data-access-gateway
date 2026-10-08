# The writing standard: ASD-STE100 Simplified Technical English

Use these rules for every README and for `docs/ste-style-guide.md` in each repository. Copy this file
into the repository as `docs/ste-style-guide.md` and add a **project vocabulary** section (Section 3)
with the technical names and technical verbs of that project.

## 1. The writing rules

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, `test` is a noun or a verb, `check` is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: `prepare`, `do`, `find`, `get`, `make`.
4. Do not use an `-ing` form as a noun or an adjective (`the running job`, `after indexing`).
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write `A, B or both`.
7. Do not use `should`, `could`, `would` or `may` for instructions. Use `must` for a rule, the
   imperative for a step and `can` for a possibility.
8. Keep the articles `a`, `an` and `the` in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: `Run the tests.` Not `The tests should be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: `If the index is stale, build it again.`
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase (`The cost model`) or an imperative (`Run the demo`).
   Do not start a heading with an `-ing` form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or `check that` |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |

## 3. Project vocabulary

This section gives the technical names and the technical verbs of SMCP Gateway. The README uses each term with only this meaning.

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **turn** | One user question and its reply, from `POST /chat` to `ChatResponse` | request (for the full cycle), round |
| **agent** | One of the three A2A participants with a card, an endpoint and a task life cycle: orchestrator, domain expert, MCP agent | bot, worker, service (for an agent) |
| **orchestrator** | Agent 1. Routes each turn and writes each reply | router, supervisor, coordinator |
| **domain expert** | Agent 2. Reads Qdrant and derives the requirement | planner, knowledge agent |
| **MCP agent** | Agent 3. Owns the tool surface and executes the plan | data agent, tool agent |
| **specialist** | The domain expert or the MCP agent | sub-agent, helper |
| **skill** | One named capability on an Agent Card. There are 11 | endpoint (for a skill), action |
| **task** | One A2A unit of work with a life cycle and artifacts | job, call (for A2A) |
| **artifact** | One named typed result on an A2A task | output, payload |
| **route** | The decision of the orchestrator: `direct`, `clarify` or `data_request` | intent (for the route), path |
| **pre-flight gate** | The deterministic completeness check before retrieval | validator, filter |
| **requirement** | The `Requirement` dataclass: the structured data plan | spec, query plan |
| **hypothesis** | The opening requirement, before the negotiation | draft, proposal (for the requirement) |
| **negotiation** | The bounded discussion between the domain expert and the MCP agent | conversation, handshake |
| **round** | One assess-and-revise exchange of the negotiation | iteration, step |
| **decision** | `AGREED`, `NEEDS_USER_INPUT`, `UNSUPPORTED` or `CANNOT_REACH_AGREEMENT` | verdict (for the negotiation), outcome |
| **capability** | One entry of the `ToolCatalogue` that the domain expert can schedule. There are 34 | tool (for a capability), function |
| **tool** | One MCP tool on a server. There are 56 | capability (for a tool), endpoint |
| **seam** | An interface with more than one implementation, selected by a setting | adapter layer, plug-in point |
| **grounding** | The check that a quote is in the retrieved text | citation check, fact check |
| **corpus** | One of the two knowledge sets: executable (`quant_knowledge`) or reference (`market_risk_kb`) | knowledge base (for one corpus), docs |
| **collection** | One Qdrant collection | index (for Qdrant), table |
| **chunk** | One retrieval unit in a collection | passage, snippet |
| **observation** | One rate of one series on one date | data point, record |
| **series** | One Treasury rate column, for example `BC_10YEAR` | column (for a rate), ticker |
| **quote basis** | The quotation convention of a rate | quoting convention, unit |
| **demo book** | The synthetic portfolio `TREASURY_DEMO_001` | real portfolio, sample book |
| **call site** | One `CallSite` value that selects a model | model slot, role |
| **token floor** | The minimum token budget of a call site | token limit, max tokens |
| **bound** | A limit in code that the receiver enforces | guard (for a number), cap |
| **turn ledger** | The budget and duplicate store of one turn | session, context |
| **user boundary** | The FastAPI service as the caller `user-boundary` | gateway (for the caller), front end |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **route** | Classify a turn as `direct`, `clarify` or `data_request` |
| **derive** | Make the requirement from the retrieved chunks |
| **ground** | Check a quoted figure against the retrieved text |
| **assess** | Compare a requirement with what the data layer can serve |
| **revise** | Change the requirement after an assessment |
| **execute** | Fetch the agreed data and run the agreed calculation |
| **validate** | Check a model object against its strict schema, or a result against the agreed plan |
| **relay** | Send a question of a specialist to the user, through the orchestrator |
| **elicit** | Ask a question from an MCP server during a tool call |
| **ingest** | Chunk, embed and store a corpus in Qdrant |
| **load** | Put the validated CSVs into PostgreSQL |
| **verify** | Run `tools/verify_load.py` or `tools/verify_mcp.py` |
| **redact** | Replace an internal identifier or a sensitive value |
| **trace** | Record a span in LangSmith |
| **emit** | Publish an execution event to the `EventBus` |
