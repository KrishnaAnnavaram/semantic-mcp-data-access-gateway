---
paths:
  - "db/**/*.sql"
  - ".claude/loading/**/*.py"
  - "tools/verify_load.py"
---

# Rules for the schema and the loading stage

These load only when working on the files above.

## Migrations

- **Forward only, and applied exactly once.** Never edit a migration that has
  been applied — `migrate.py` records each file's SHA-256 and will refuse to run
  if one changes. To alter something, add `V00N+1`.
- **One transaction per migration.** A failure must roll back completely. The
  database is never left half-migrated.
- **Idempotent by construction.** `CREATE ... IF NOT EXISTS`, `ON CONFLICT DO
  UPDATE`, guarded `CREATE TYPE`. Re-running the suite against a current
  database must be a no-op, not an error.
- **Comment the intent, not the syntax.** `COMMENT ON` is part of the
  deliverable: it is the only documentation that travels with the database into
  a client tool.

## The loader

- **Never write a row Treasury did not publish.** A NULL cell produces no
  observation. Absence of a row means absence of a publication — it is never a
  zero and never a carry-forward.
- **Never silently drop a column.** Every rate-bearing staging column must
  resolve to a registered series *before* any insert runs. An unmapped column
  aborts the load naming the column. A JOIN that quietly discards a new
  maturity is the most expensive defect this pipeline can have, because the
  numbers that remain still look right.
- **Never load unverified bytes.** Re-compute every raw file's SHA-256 and
  compare it to the manifest before staging anything.
- **Staging is truncated and rebuilt; core is delete-then-insert per dataset.**
  This makes a rerun produce a database identical to a first run. Idempotency
  is a property to verify, not to hope for.
- **Semantics live in the data, not the code.** Placeholder rules, quoting
  bases and exclusions are columns in `treasury.series`. Adding another one is
  an `UPDATE`, not a code change.

## Verification

- **Expectations are recounted from the CSVs, never read back from the
  database.** A check that asks the database what it should contain proves
  nothing.
- **The suite must be able to fail.** `--self-test` corrupts a row inside a
  rolled-back transaction and requires the value check to catch it. A suite
  that only ever reports PASS tells you about the suite, not the data.

After any change here:

```bash
python .claude/loading/migrate.py --status
python .claude/loading/load_us_treasury.py
python tools/verify_load.py --self-test
```

Expected: `Verification PASS: 58/58 checks passed` and `self-test OK`.
