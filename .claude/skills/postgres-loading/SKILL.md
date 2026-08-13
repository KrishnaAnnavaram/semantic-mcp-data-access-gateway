---
name: postgres-loading
description: >
  Load the acquired Treasury CSVs into PostgreSQL - staging via COPY, then a
  generic unpivot into the normalised core, plus lineage in meta. Use when
  populating the database, reloading after a data refresh, or diagnosing a row
  count that does not match the source. Explains the unmapped-column guard, the
  placeholder-zero handling, and why a rerun produces a byte-identical result.
---

# PostgreSQL loading

## What it is

Stage 2. Reads `data/processed/*.csv` and `download_manifest.json`. Contacts
nothing. Writes three schemas.

```
manifest ──verify SHA-256──► meta.source_file
   CSV   ──────COPY────────► staging.<table>  ──unpivot──► treasury.observation
                                                       └──► bill_security,
                                                            long_term_extrapolation,
                                                            market_note
```

## Run it

```bash
python -m treasury_db.load
python -m treasury_db.load --dataset daily_treasury_yield_curve
python -m treasury_db.load --dry-run     # check inputs, write nothing
```

Reference result: 52 series, 267,517 observations, 140 source files verified.

## How the unpivot works, and why it is generic

A wide CSV becomes tall rows without the loader holding a list of maturities:

```sql
FROM staging.par_yield_curve st
CROSS JOIN LATERAL jsonb_each_text(to_jsonb(st) - <non-rate columns>) AS kv(key, value)
JOIN treasury.series s ON lower(s.series_code) = kv.key
WHERE kv.value IS NOT NULL
```

Every column becomes a key/value pair; the join to `treasury.series` decides
which are rates. Treasury adding `BC_2_5MONTH` needs no change here — only a
staging column and a series row.

**That join is also the danger.** A column with no matching series would simply
vanish, and every remaining number would still look right. So before any insert
runs, the loader compares the staging columns against the registry and **aborts
naming the column**. Loud failure beats quiet loss.

## Placeholder zeros

`BC_30YEARDISPLAY` is a literal `0` on every date before 2011-01-03. Loading it
as a rate puts a 0% 30-year yield into 21 years of history. It is handled as
data, not as a special case in code:

```sql
treasury.series.placeholder_zero_before = '2011-01-03'
```

Rows matching it are stored with `value_status = 'source_placeholder'`,
`rate_percent = NULL`, and the published `0` retained in
`source_value_percent`. The value is never destroyed, never presented as a
rate, and the analytics views exclude it. Registering another placeholder is an
`UPDATE`, not a code change.

## Idempotency

Staging is truncated and rebuilt. Core is delete-then-insert per dataset inside
one transaction. A second run against unchanged CSVs produces an identical
database. This is verified rather than assumed — rerun the loader and then
`verify_load.py`; the counts must be unchanged.

## What the loader refuses to do

| It will not | Because |
|---|---|
| Load a file whose SHA-256 differs from the manifest | Those bytes are not the bytes that were validated |
| Insert a row for a NULL cell | Absence of a rate is not a rate |
| Drop an unmapped rate column | The remaining numbers would still look correct |
| Load a `rate_type` with no registered series | Same reason |
| Continue past a failed step | A half-loaded database that reports success is worse than a failed run |

Every one of those aborts the run and records the failure in `meta.load_run`.

## Diagnosing a count that looks wrong

1. `meta.load_step` — `rows_in` vs `rows_out` per dataset per phase.
2. `analytics.v_series_coverage` — per series, when it starts and stops. A
   maturity that did not exist yet is the usual answer.
3. `staging.<table>` against the CSV. Staging is the arbiter; if they agree,
   the question is about the model, not the load.

Full contract: @docs/loading-contract.md
