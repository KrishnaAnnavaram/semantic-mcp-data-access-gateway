# Architecture decisions

Why it is built this way, and what would reverse each decision.

---

## ADR-001 — Acquisition and loading are separate stages

**Decision.** Stage 0 talks to Treasury and the filesystem, never a database.
Stages 1-3 talk to the database, never Treasury.

**Why.** When a number is disputed, the first question is always "is the source
wrong or is our pipeline wrong". If one process did both, that question has no
clean answer. With the split, staging is compared to the CSV and the CSV to the
raw XML, and the fault localises to one side of the line in two queries.

It also means a Treasury outage cannot break a database rebuild, and a database
outage cannot cost you a day's source data.

**Cost.** Two commands instead of one, and the CSVs exist as an intermediate
that some would call redundant.

**Reversed if.** Never, realistically. This is the load-bearing decision.

---

## ADR-002 — A missing observation is NULL, and no row is written

**Decision.** A NULL cell produces no row in `treasury.observation`. Absence of
a row means Treasury published nothing.

**Why.** Absence of a rate and a rate of zero are different facts about the
world. A zero-filled curve looks complete and is wrong, and nothing downstream
can tell. The alternative — a dense row per series per date with a status
column — was rejected because it invites `COALESCE(rate, 0)`, and because the
sparse form makes "we have no data here" the structurally obvious reading.

**Cost.** A consumer wanting a dense grid must generate the date spine
themselves. `analytics.v_series_coverage` tells them what to expect.

**Reversed if.** A consumer genuinely needs dense output — then add a view, not
storage.

---

## ADR-003 — Placeholder zeros are preserved, flagged, and excluded — not deleted

**Decision.** `BC_30YEARDISPLAY`'s 5,256 pre-2011 zeros load with
`value_status = 'source_placeholder'`, `rate_percent = NULL`, the published `0`
kept in `source_value_percent`, and the series excluded from analytics.

**Why.** Three options were available. Load them as rates — puts a 0% 30-year
yield into 21 years of history. Drop them — the pipeline silently disagrees
with the source and nobody can reconcile it. Keep them, mark them, exclude
them — the source is reproducible, the trap is queryable, and no consumer can
hit it by accident.

The rule lives in `treasury.series.placeholder_zero_before` rather than in the
loader, so recognising a placeholder is a property of the series. Registering
another one is an `UPDATE`.

**Cost.** An extra column and a status enum that most rows never use.

**Reversed if.** Treasury restates the column with real values.

---

## ADR-004 — Rates carry their quoting basis in the schema

**Decision.** `treasury.series.quote_basis` is a non-null enum:
`par_coupon_semiannual`, `bank_discount_act360`, `coupon_equivalent`,
`average_real_yield`.

**Why.** A bill discount rate and a par coupon yield are different quantities.
On 2026-08-11 the 4-week bill quotes 3.64 on a discount basis and 3.70
coupon-equivalent. Stored as bare numbers in adjacent columns they look
interchangeable, and eventually someone plots them on one curve. This is the
most common way Treasury data is misused, and it survives code review because
the numbers are individually correct.

Making the basis a required column means the mistake requires ignoring an
explicit label rather than merely not knowing.

**Cost.** Every new series forces a decision that could otherwise be deferred.
That is the point.

**Reversed if.** Never.

---

## ADR-005 — Normalised core, not wide tables

**Decision.** `observation(series_id, observation_date, rate_percent, …)`
rather than one wide table per dataset.

**Why.** Treasury has added six par maturities since 1990 and will add more.
Wide tables make each one a DDL change, a migration and an application change.
Here `BC_1_5MONTH` arriving in 2025 is one row in `treasury.series`. It also
lets the 28 bill series carry per-series quoting metadata, which a wide table
cannot express at all.

**Cost.** Pivoting for human consumption. Handled once in the analytics views.

**Reversed if.** Query patterns become overwhelmingly wide-curve reads and the
pivot cost shows up in profiling — then materialise the views, keeping the core
as it is.

---

## ADR-006 — Four schemas: meta, staging, treasury, analytics

**Decision.** Landing, model and read layers are separate schemas, with a
lineage schema written at every step.

**Why.** `staging` is the arbiter when a number is disputed: it is the CSV,
unmodelled. `treasury` is the interpretation. `analytics` is what a consumer
should see, with the traps already excluded. Collapsing them means every
consumer must remember which columns are safe.

`meta` exists because "where did this number come from" should be answerable in
SQL, months later, in front of a reviewer — file, URL, SHA-256, timestamp, run.

**Cost.** More objects. Data stored roughly twice (staging + core).

**Reversed if.** The database grows to where duplicating staging matters. At
64 MB it does not.

---

## ADR-007 — Generic unpivot with an explicit unmapped-column guard

**Decision.** `jsonb_each_text(to_jsonb(row) - ignored)` joined to
`treasury.series`, preceded by a check that every rate column maps.

**Why.** The generic form means a new maturity needs no loader change. But the
join that makes it generic would also silently discard an unregistered column,
and — this is the dangerous part — every remaining number would still be
correct. A silently narrower curve is not visibly broken.

So the guard runs first and aborts naming the column. Loud failure, mid-load,
over quiet loss.

**Cost.** A new maturity fails the first load after it appears. Intended.

**Reversed if.** Never. This is ADR-002's enforcement in a different place.

---

## ADR-008 — Forward-only, checksummed migrations, no framework

**Decision.** `V<n>__<name>.sql`, applied once, one transaction each, SHA-256
recorded. Editing an applied migration fails the next run. No Alembic, no
Flyway.

**Why.** The whole contract is four rules and about 150 lines. A framework
would add a dependency, a config file and a mental model for a problem this
project does not have. The checksum guard is the part that earns its keep:
editing an applied migration is the single most common way a team's databases
drift apart, and it is invisible until two developers get different answers.

No downgrade path, because writing one would be a lie — dropping a column does
not restore the data it held.

**Reversed if.** Multiple environments with independent release trains appear.
Then adopt Flyway, which uses the same file convention.

---

## ADR-009 — Verification recounts from source, and can fail on purpose

**Decision.** Every expected value in `verify_load.py` is recomputed from the
CSVs. `--self-test` corrupts a row inside a rolled-back transaction and
requires the check to catch it.

**Why.** A check that reads a count from the database and compares it to a
count from the database passes on a database that is entirely wrong. And a
suite that has only ever reported PASS is equally consistent with a suite that
cannot detect anything — the planted corruption is how you tell the difference.

**Cost.** The verifier re-parses ~5 MB of CSV on every run. Four seconds.

**Reversed if.** Never.

---

## ADR-010 — Pipeline code lives under `.claude/`

**Decision.** `data/acquisition/` and `.claude/src/postgres/src/treasury_db/` hold product code,
alongside `agents/`, `skills/`, `rules/` and `commands/`.

**Why.** House convention, matching `adaptive-legacy-code-complexity-harness`
and `plsql_to_brd`. These pipelines are Claude-orchestrated: the agent
definitions, the skills that describe when to run each stage, and the
implementations are one deliverable, and splitting them across `.claude/` and
`src/` would separate the description from the thing described.

> **`.claude/` is not editor configuration here.** It holds the product.
> Deleting it deletes the pipeline.

`src/` is reserved for the MCP gateway runtime, which is a long-running service
rather than a pipeline stage and is not built yet.

**Cost.** Surprises anyone who assumes `.claude/` is disposable tooling. Hence
the warning in CLAUDE.md, the README and here.

**Reversed if.** The pipeline is ever consumed as a library by something
outside this repository.

---

## ADR-011 — Committed data, and one directory that must never be committed

**Decision.** `data/` — all 61 MB, raw XML included — is committed. The nested
`adaptive-legacy-code-complexity-harness/` is git-ignored.

**Why.** Data is committed so a teammate gets a working database from a clone
plus four commands, with the immutable source of record versioned alongside the
code that produced it. The manifest's checksums are only meaningful if the
files they describe are actually there.

The nested directory is a **separate git repository** with its own `.git`.
Committing it produces either a broken submodule reference or an absorbed
history — neither cleanly recoverable once pushed. It is in `.gitignore` and in
`.claude/settings.json`'s deny list, and must stay in both.

**Cost.** Every clone pulls 61 MB, growing with each refresh of the current
year.

**Reversed if.** History growth becomes painful. Then move `data/raw/` to
object storage or Git LFS, keeping the manifest in git — the checksums make
that migration verifiable.

---

## ADR-012 — Two MCP servers, split by failure attribution

**Decision.** `market-risk-data-mcp` retrieves trusted facts; `risk-engine-mcp`
performs deterministic mathematics and has no database credential. The host
reasons and routes. Not one combined server.

**Why.** When a VaR number looks wrong there are exactly two causes: bad input or
bad maths. With the split, each is checkable in isolation — replay the same
payload through the engine, or query the data server's provenance. Combined,
you are guessing, and "the model is fine, the input was wrong" is a very
different conversation from its opposite.

This is the same rule the data pipeline already lives by — stage 0 never touches
the database, stages 1–3 never touch Treasury — extended one layer up.

The two halves also have nothing operationally in common. The data server is I/O
bound, cacheable, and changes when Treasury publishes; the engine is CPU bound,
uncacheable (every call has different inputs), and changes when a quant changes
methodology. Bundled, every one of those becomes a compromise.

**Cost.** Two processes, and results must be carried between them by the host.

**Reversed if.** Never for this workload. The boundary is the product.

---

## ADR-013 — Build on the existing schema rather than the proposed one

**Decision.** The reviewed design document proposed a PostgreSQL schema
(`treasury.dataset`, `series`, `source_batch`, `observation`,
`analytics.v_rate_observation`). That schema already existed here under
different names. Map to it; add only what is genuinely missing.

**Why.** Rebuilding would have meant rewriting V001–V007 and reloading 267,517
verified rows to gain nothing but a naming convention. The mapping is total:
`curve_family` → `rate_kind`, `tenor_months` → `tenor_years`,
`quality_status` → `value_status`, `source_batch` → `meta.source_file`.

Genuinely missing, and added: the `demo` schema (V008), the `mcp_reader` role
(V009), and MCP-shaped read views (V010–V013).

**What made it cheap.** `security_invoker` is unset on the analytics views, so
they execute with the owner's privileges. Granting `SELECT` on views while
revoking `treasury.*` gives the intended "the MCP role cannot reach raw data"
boundary with no schema change at all.

**Reversed if.** Never; the alternative was churn.

---

## ADR-014 — Bulk numeric data bypasses model context via `_meta`

**Decision.** `get_curve_history_matrix` returns a summary in
`structured_content` and the numeric matrix in the result's `_meta`. The host
lifts the matrix and passes it to the risk engine directly.

**Why.** A 250-day × 5-tenor history is 1,250 yields — 21× larger than the
summary. The model does not reason over individual yields; it decides *that* a
history is needed and hands it to the engine. Putting them in context spends
tokens for nothing and invites truncation partway through a matrix, which would
corrupt a VaR silently.

The summary still carries shape, completeness, excluded dates and provenance, so
the model can verify the request was satisfied without seeing a single rate.

**Cost.** The host must know to look in `_meta`. Verified by
`bulk_rates_absent_from_model_view` in `verify_mcp.py`.

**Note.** `_meta` is not a security boundary — the SDK says so explicitly. It is
a context-efficiency channel, and nothing secret goes in it.

---

## ADR-015 — Missing history is refused by default

**Decision.** `missing_policy` defaults to `reject`. `intersection` is available
but must report `excluded_dates`.

**Why.** The 30-year has a real 994-business-day hole from 2002 to 2006 — the
bond did not exist. Under `intersection`, a VaR window spanning it silently
drops those dates and returns a number computed from a different history than
the one requested. Nothing fails. The answer is simply wrong, and there is no
signal that anything was lost.

Refusing by default makes the gap a decision rather than an accident. It is also
a better demonstration than any number: the system declining to answer is
evidence it knows what it does not know.

**Cost.** A caller must opt in to accept gaps.

**Reversed if.** Never. This is ADR-002's rule — absence is not zero — at the
query layer.
