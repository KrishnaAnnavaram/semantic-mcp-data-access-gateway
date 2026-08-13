# System overview

Start here.

This repository turns official U.S. Treasury interest-rate publications into a
PostgreSQL database that a market-risk system can trust — where "trust" means
every row traces to a checksummed source file, and the claim is verified rather
than asserted.

## Four stages

Each stage owns one job and hands off a documented artifact. Nothing downstream
ever re-reads what an upstream stage already interpreted.

```
  home.treasury.gov
        │
        ▼
┌──────────────────┐   agent: treasury-acquisition
│  0. ACQUIRE      │   data/acquisition/download_us_treasury.py
└──────────────────┘   140 GETs, one immutable XML per dataset-year
        │
        ▼  data/raw/           immutable, SHA-256 in the manifest
        │  data/processed/     5 normalised CSVs
        │  data/metadata/      manifest + schema + validation reports
        │                                     contract: docs/data-contract.md
        ▼
┌──────────────────┐   agent: treasury-database-loader
│  1. PROVISION    │   docker compose up -d ; migrate.py
└──────────────────┘   PostgreSQL 17, schemas meta/staging/treasury/analytics
        │
        ▼
┌──────────────────┐
│  2. LOAD         │   .claude/src/postgres/src/treasury_db/load_us_treasury.py
└──────────────────┘   COPY to staging, generic unpivot to core
        │
        ▼  52 series, 267,517 observations
        │                                  contract: docs/loading-contract.md
        ▼
┌──────────────────┐
│  3. VERIFY       │   tools/verify_load.py --self-test
└──────────────────┘   58 checks, expectations recounted from the CSVs
        │
        ▼  meta.reconciliation + data/metadata/us_treasury/load_verification.md
```

Stage 0 never opens a database connection. Stages 1-3 never contact Treasury.
That separation is deliberate: it means a wrong number can always be localised
to one side of the line. If staging matches the CSV and the CSV matches the raw
XML, the load is not at fault.

## The rule everything rests on

**A missing observation is NULL. Never zero, never the previous day's rate,
never an interpolation.**

Absence of a rate and a rate of zero are different facts about the world.
Collapse them and you get a curve that looks complete and is wrong, with
nothing downstream able to tell the difference. This is enforced at every
layer: the downloader emits NULL, the loader writes no row, and the core schema
has no default that could invent one.

Its mirror image is the harder half: **an exact 0 is not automatically
missing.** Short Treasury tenors genuinely printed 0.00% in 2008-12, 2011, 2015
and 2020-21. Treating those as absent would erase the zero-rate era. Exactly
one column in this data is a placeholder — `BC_30YEARDISPLAY`, whose entire
pre-2011 history is a literal `0` — and that judgement is recorded as data
(`treasury.series.placeholder_zero_before`), not buried in code.

## The four database layers

| Layer | Answers | Rebuilt |
|---|---|---|
| `meta` | Where did this number come from? | Append-only |
| `staging` | What exactly did the CSV say? | Truncated each run |
| `treasury` | What is the modelled fact? | Delete-then-insert per dataset |
| `analytics` | What should a consumer see? | Views, always current |

Consumers query `analytics`. Not for secrecy — `treasury` is granted to the
read-only role too — but because `analytics` is where the source traps are
already excluded, once, instead of in every consumer.

## What this repository deliberately does not do

No returns, durations, DV01, VaR, expected shortfall, spreads, breakevens,
bootstrapped zero curves, PCA or stress scenarios. Those are modelling
decisions with their own assumptions, and mixing them into an acquisition
pipeline makes the source data impossible to audit. This project ends at
trustworthy facts.

This is the data foundation. The reasoning layer that consumes it — the quant
agent, its Qdrant knowledge base, and the `/chat` service — is built on top; see
[reasoning-layer.md](reasoning-layer.md). Both MCP servers and the host that
drives them are built and verified; see [mcp-contract.md](mcp-contract.md).

## Reference figures

| | |
|---|---|
| Datasets | 5 |
| Raw source files | 140 (1990-2026) |
| Series registered | 52 |
| Observations | 267,517 |
| Placeholder rows | 5,256 (NULL rate, retained for audit) |
| Database size | 64 MB |
| Verification | 58/58 checks pass, self-test confirms the checks can fail |

## Where to go next

| Question | Document |
|---|---|
| **What is this data, and what is actually in it?** | **[data-guide.md](data-guide.md)** — start here for the data itself |
| What did Treasury publish, and what are the traps? | [data-contract.md](data-contract.md) |
| What do the tables look like? | [database-schema.md](database-schema.md) |
| How do I get this running? | [postgres-setup.md](postgres-setup.md) |
| How do I add a dataset or a maturity? | [loading-contract.md](loading-contract.md) |
| Why is it built this way? | [architecture-decisions.md](architecture-decisions.md) |
| How does the agent use this data? | [reasoning-layer.md](reasoning-layer.md) |
