# semantic-mcp-data-access-gateway

Semantic MCP data access gateway for intent-aware request understanding, intelligent data
requirement planning, filtering, and optimized retrieval across enterprise data sources.

**Current state:** the market-risk **data foundation** is built and verified —
36 years of official U.S. Treasury interest-rate data, acquired from
`home.treasury.gov`, validated, and loaded into PostgreSQL with row-level
lineage. The MCP gateway itself is not built yet.

**Input:** the official Treasury XML feed.
**Output:** a PostgreSQL database where every row traces to a checksummed source file.
**Shape:** four stages, two agents, four skills, one contract per boundary.

---

# Architecture

## Data flow

Each stage owns one job and hands off a documented artifact. Nothing downstream
re-reads what an upstream stage already interpreted.

```
  home.treasury.gov
        │
        ▼
┌──────────────────┐   agent: treasury-acquisition
│  0. ACQUIRE      │   .claude/acquisition/download_us_treasury.py
└──────────────────┘   140 GETs · one immutable XML per dataset-year · SHA-256
        │
        ▼  data/raw/  data/processed/  data/metadata/
        │                                  contract: docs/data-contract.md
        ▼
┌──────────────────┐   agent: treasury-database-loader
│  1. PROVISION    │   docker compose up -d ; .claude/loading/migrate.py
└──────────────────┘   PostgreSQL 17 · V001-V007 · forward-only, checksummed
        │
        ▼
┌──────────────────┐
│  2. LOAD         │   .claude/loading/load_us_treasury.py
└──────────────────┘   COPY → staging · generic unpivot → treasury · lineage → meta
        │
        ▼  52 series · 267,517 observations
        │                               contract: docs/loading-contract.md
        ▼
┌──────────────────┐
│  3. VERIFY       │   tools/verify_load.py --self-test
└──────────────────┘   58 checks · expectations recounted from the CSVs
```

**Stage 0 never opens a database connection. Stages 1-3 never contact
Treasury.** That line is why a wrong number can always be localised: if staging
matches the CSV and the CSV matches the raw XML, the load is not at fault.

## Directory map

```
semantic-mcp-data-access-gateway/
│
├── CLAUDE.md                       Project memory. Loaded into every Claude Code
│                                   session: commands, conventions, the rules.
├── README.md                       This file.
├── docker-compose.yml              PostgreSQL 17 Alpine, container smdag-postgres
│
├── .claude/                        ⚠ Contains PRODUCT CODE, not just tool config
│   │
│   ├── settings.json               Shared permissions. Denies writes to data/raw/
│   │                               and all access to the nested harness repo.
│   │
│   ├── agents/                     WHO orchestrates
│   │   ├── 0_acquisition_agent.md    name: treasury-acquisition
│   │   └── 1_database_agent.md       name: treasury-database-loader
│   │
│   ├── rules/                      Path-scoped instructions. Load only when
│   │   ├── source-data.md            touching acquisition code or data/
│   │   └── database-code.md          touching SQL, the loader or the verifier
│   │
│   ├── commands/                   /db-setup  /db-refresh  /db-check
│   │
│   ├── skills/                     WHAT each stage is, and WHEN to use it
│   │   ├── treasury-acquisition/SKILL.md
│   │   ├── postgres-provisioning/SKILL.md
│   │   ├── postgres-loading/SKILL.md
│   │   └── load-verification/SKILL.md
│   │
│   ├── acquisition/                Stage 0                     ← product code
│   │   └── download_us_treasury.py
│   │
│   └── loading/                    Stages 1-2                  ← product code
│       ├── _db.py                  Connection plumbing, .env reader
│       ├── migrate.py              Forward-only migration runner
│       └── load_us_treasury.py     CSV → staging → core
│
├── db/
│   ├── init/01_bootstrap.sql       Once, on an empty volume: UTC, ISO, readonly role
│   └── migrations/                 V001 schemas · V002 meta · V003 staging
│                                   V004 core · V005 series registry
│                                   V006 analytics views · V007 grants
│
├── data/                           The source of record
│   ├── raw/us_treasury/            140 immutable Treasury XML files (1990-2026)
│   ├── processed/us_treasury/      5 normalised CSVs
│   ├── metadata/us_treasury/       manifest · schema · validation · load verification
│   └── README.md                   Data provenance and known limitations
│
├── docs/
│   ├── system-overview.md          Start here
│   ├── data-contract.md            What Treasury publishes, and the traps
│   ├── database-schema.md          Tables, views, worked queries
│   ├── postgres-setup.md           Fresh clone → verified database
│   ├── loading-contract.md         How to add a maturity or a dataset
│   └── architecture-decisions.md   Why it is built this way, and what would reverse it
│
└── tools/
    └── verify_load.py              58 checks, recounted from source, with a self-test
```

> **`.claude/` is not editor configuration here.** It holds the deliverable.
> Deleting it deletes the pipeline. This matches the house convention used by
> `adaptive-legacy-code-complexity-harness`; see
> [docs/architecture-decisions.md](docs/architecture-decisions.md) ADR-010.

## The three layers, and why they are separate

| Layer | Answers | Lives in | Changes when |
|---|---|---|---|
| **Agent** | How do I run the whole thing? | `.claude/agents/` | The workflow changes |
| **Skill** | What is this stage, when do I use it? | `.claude/skills/` | The concept changes |
| **Implementation** | How is it actually done? | `.claude/acquisition/`, `.claude/loading/`, `db/` | The mechanism changes |

## The four database layers

| Schema | Holds | Rebuilt |
|---|---|---|
| `meta` | Load runs, source files + SHA-256, reconciliation | Append-only |
| `staging` | One table per CSV, Treasury's own column names | Truncated each run |
| `treasury` | `dataset` · `series` · `observation` + reference tables | Delete-then-insert |
| `analytics` | Views only — source traps already excluded | Always current |

Consumers query `analytics`. Not for secrecy — `treasury` is readable too — but
because that is where the traps are handled once, instead of in every consumer.

---

## The data

| Dataset | Data key | Range | Series | Observations |
|---|---|---|---|---|
| Par Yield Curve | `daily_treasury_yield_curve` | 1990-01-02 → 2026-08-11 | 15 | 108,339 |
| Bill Rates | `daily_treasury_bill_rates` | 2002-01-02 → 2026-08-11 | 28 | 105,204 |
| Long-Term Rates | `daily_treasury_long_term_rate` | 2000-01-03 → 2026-08-11 | 3 | 19,965 |
| Par Real Yield Curve | `daily_treasury_real_yield_curve` | 2003-01-02 → 2026-08-11 | 5 | 27,354 |
| Real Long-Term Rates | `daily_treasury_real_long_term` | 2000-01-03 → 2026-08-11 | 1 | 6,655 |
| **Total** | | | **52** | **267,517** |

140 raw files · 0 failed downloads · 0 unexplained business-day gaps · 64 MB.

Source: **U.S. Department of the Treasury** only. No Kaggle, no FRED, no Yahoo,
no mirror — not even for a single missing day.

---

## Run it

```bash
cp .env.example .env          # set a real password
docker compose up -d
python .claude/loading/migrate.py
python .claude/loading/load_us_treasury.py
python tools/verify_load.py --self-test
```

Reference run:

```
self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
Verification PASS: 58/58 checks passed
```

First query:

```sql
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;
```

```
 observation_date |  m1  | m1_5 |  m2  |  m3  |  m6  |  y1  |  y2  |  y10 |  y30
------------------+------+------+------+------+------+------+------+------+------
 2026-08-11       | 3.79 | 3.82 | 3.83 | 3.89 | 3.99 | 4.03 | 4.22 | 4.70 | 5.24
```

From Claude Code, `/db-setup` does all of it and reports the result.
Full instructions: [docs/postgres-setup.md](docs/postgres-setup.md).

---

## The rule everything rests on

**A missing observation is NULL. Never zero, never the previous day's rate,
never an interpolation.**

Absence of a rate and a rate of zero are different facts about the world.
Collapse them and you get a curve that looks complete and is wrong, with
nothing downstream able to tell the difference.

The harder half is the mirror image: **an exact 0 is not automatically
missing.** Short Treasury tenors genuinely printed 0.00% in 2008-12, 2011, 2015
and 2020-21 — erasing those would delete the zero-rate era.

Exactly one column in this data is a placeholder. Treasury publishes
`BC_30YEARDISPLAY` as a literal `0` on all **5,256** dates from 1990-01-02 to
2010-12-31. Loaded naively it puts a 0% thirty-year yield into 21 years of
history — and because every other point on the curve is correct, the result
looks entirely plausible. It is stored with a NULL rate, the published `0`
retained for audit, and excluded from every analytics view. The rule lives in
`treasury.series.placeholder_zero_before` — as data, not code, so registering
the next one is an `UPDATE`.

---

## Quoting basis is part of the schema

A bill discount rate and a par coupon yield are different quantities. On
2026-08-11 the 4-week bill quotes **3.64** on a bank-discount actual/360 basis
and **3.70** coupon-equivalent. Stored as bare numbers in adjacent columns they
look interchangeable, and eventually someone plots them on one curve — a
mistake that survives review because each number is individually correct.

Every series therefore declares a non-null `quote_basis`:
`par_coupon_semiannual`, `bank_discount_act360`, `coupon_equivalent` or
`average_real_yield`. `analytics.v_bill_rates_quoted` puts the two in
separately named columns. Making that mistake now requires ignoring an explicit
label.

---

## Audited, not asserted

```bash
python tools/verify_load.py --self-test
# self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
# Verification PASS: 58/58 checks passed
```

Every expected value is **recounted from the processed CSVs**. The database is
never asked what it should contain — a check that compares a database count to
a database count passes on a database that is entirely wrong. When the report
says 108,339 observations, that number was derived twice by two routes.

`--self-test` adds 1.25 to one stored rate inside a transaction, requires the
value check to **fail**, then rolls back and confirms the original is restored.
A suite that has only ever reported PASS is equally consistent with a suite
that cannot detect anything; the planted corruption is how you tell.

Checks cover lineage and checksums, staging vs CSV row counts, core counts,
date coverage, sampled values, placeholder handling, duplicate keys, future
dates, orphan rows, series that loaded nothing, plausibility bands, bills
maturing before their quote date, every view being queryable, and the presence
of the primary keys, foreign keys and check constraints themselves.

---

## Add a maturity Treasury has started publishing

The loader will already have stopped and named the column:

```
daily_treasury_yield_curve: staging column(s) with no registered series:
['bc_2_5month']. Treasury has published a series this database does not know
about. Add it in a migration - do not let the load drop it.
```

That failure is the feature. The generic unpivot would otherwise discard the
column silently, and every remaining number would still look right. Add the
staging column and the `treasury.series` row in a new migration, re-run, verify.
Full contract: [docs/loading-contract.md](docs/loading-contract.md).

---

## Known limits

- **Published curve, not tradable prices.** End-of-day indicative quotes, no
  bid/ask, not executable. Any risk number derived from them inherits that.
- **No analytics.** No returns, duration, DV01, VaR, expected shortfall,
  spreads, breakevens, bootstrapped zero curves, PCA or stress scenarios.
  Deliberate — mixing modelling into acquisition makes source data
  unauditable. This repository ends at trustworthy facts.
- **Revisions are not auto-detected.** Treasury can restate prior days, and a
  routine rerun will not re-fetch a closed year without `--refresh`. When a
  revision is loaded, `meta.source_file` records it as a new row rather than
  overwriting, so the change stays visible.
- **Sparse by design.** No row means Treasury published nothing. A consumer
  wanting a dense grid must generate the date spine;
  `analytics.v_series_coverage` says what to expect.
- **The nested `adaptive-legacy-code-complexity-harness/`** is a separate git
  repository. It is ignored and must stay ignored — see CLAUDE.md.

## License

Released under the [MIT License](LICENSE).
