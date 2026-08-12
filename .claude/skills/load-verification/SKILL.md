---
name: load-verification
description: >
  Reconcile the loaded PostgreSQL database against the CSVs it was built from,
  with every expectation recounted from the source rather than read back from
  the database. Use after any load or migration, before sharing the database,
  or when a number is disputed. Includes a self-test that plants a corruption
  and requires the checks to catch it.
---

# Load verification

## What it is

Stage 3. Fifty-eight checks across lineage, row counts, coverage, sampled
values, placeholder handling, referential integrity and constraint presence.
Results are written to `meta.reconciliation` so the evidence outlives the
terminal.

```bash
python tools/verify_load.py --self-test
python tools/verify_load.py --sample-size 1000
```

Reference result:

```
self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
Verification PASS: 58/58 checks passed
```

## The property that makes it worth running

**Every expected value is recounted from the processed CSVs. The database is
never asked what it should contain.**

A check that reads a count from the database and compares it to a count from
the database will pass on a database that is entirely wrong. So
`verify_load.py` re-parses the CSVs, counts the non-null rate cells itself, and
compares that to what was loaded. When it says 108,339 observations, that
number was derived twice by two different routes.

## What is checked

| Group | Asks |
|---|---|
| `lineage` | Is every manifest file registered, checksum-verified, and did the run succeed? |
| `staging` | Does the staging row count equal the CSV row count? |
| `observations` | Does the core row count equal the non-null rate cells counted from the CSV? |
| `coverage` | Do first date, last date and distinct dates match? |
| `values` | Byte-compare a random sample of cells, CSV to database |
| `placeholders` | Are the `BC_30YEARDISPLAY` zeros stored as placeholders, absent from analytics, and is there no 0.00% 30-year yield anywhere in the curve view? |
| `integrity` | Duplicate keys, future dates, orphan rows, series that loaded nothing, rates outside the plausible band, bills maturing before their quote date, every view queryable |
| `constraints` | Are the primary keys, foreign keys and checks actually present? |

## The self-test, and why it exists

`--self-test` opens a transaction, adds 1.25 to one stored rate, runs the value
check against that cell, requires it to **fail**, then rolls back and confirms
the original value is restored.

A suite that has only ever reported PASS is equally consistent with a suite
that cannot detect anything. The self-test is how you tell the difference. Run
it whenever you change a check — a check you have never seen fail is a check
you have not tested.

It is honest about its scope: it proves the value-comparison path detects a
real divergence. It does not prove every one of the fifty-eight checks can
fail.

## When a check fails

Do not adjust the expectation to match the database. Work outward:

1. Is `staging` equal to the CSV? If not, the load is at fault.
2. Is the CSV equal to the raw XML? Re-run acquisition validation. If the CSV
   is wrong, the database is faithfully reproducing a bad input.
3. Only if both agree is the model wrong — and then it is a migration, not an
   edit.

## Reading the output

- `data/metadata/us_treasury/load_verification.md` — table of every check.
- `meta.reconciliation` — same, queryable, tied to the load run it belongs to:

```sql
SELECT check_name, data_key, expected, actual, passed
FROM meta.reconciliation
WHERE load_run_id = (SELECT max(load_run_id) FROM meta.load_run)
  AND NOT passed;
```

An empty result is the answer you want.
