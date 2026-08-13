---
description: Stand up PostgreSQL from nothing, migrate, load Treasury data, and verify
---

Set up this project's PostgreSQL database end to end and report the result.

Work through these steps in order. Stop and report at the first failure rather
than continuing — a half-built database that reports success is the outcome
this project exists to prevent.

## 1. Preflight

- Confirm Docker is running: `docker --version && docker compose version`
- Confirm `.env` exists. If it does not, copy `.env.example` to `.env` and tell
  the user to set a real `POSTGRES_PASSWORD` before continuing. Never invent a
  password and never read `.env` back to them.
- Confirm the acquired data is present:
  `data/processed/us_treasury/*.csv` and
  `data/metadata/us_treasury/download_manifest.json`.
  If missing, run `python -m acquisition.download_us_treasury` first
  and say that you are doing so — it fetches ~60 MB from Treasury.
- Confirm `psycopg2` is importable; if not, `pip install psycopg2-binary`.

## 2. Provision

```bash
docker compose up -d
docker compose ps
```

Wait for `Up (healthy)`. If port 5432 is already taken by a native PostgreSQL,
tell the user to set `POSTGRES_PORT=5433` in `.env` rather than stopping their
service for them.

## 3. Migrate

```bash
python -m treasury_db.migrate --status
python -m treasury_db.migrate
```

If it reports that applied migrations were edited, **stop**. That is schema
drift, and the fix is to revert the edit and add a new migration — never to
force it through.

## 4. Load

```bash
python -m treasury_db.load
```

If it aborts naming an unmapped column, Treasury has published a new series.
Report the column name and stop; registering it needs a new migration and a
deliberate `quote_basis` decision, which is not a judgement to make silently.

## 5. Verify

```bash
python tools/verify_load.py --self-test
```

Both must hold:
- `self-test OK: corruption detected ...`
- `Verification PASS: 58/58 checks passed`

A PASS without the self-test line is not evidence.

## 6. Report

Give the user:

- container status and the connection string with the password redacted
- migrations applied
- per dataset: series, observations, date range
- total observations, placeholder rows, source files verified, database size
- the verification result, and any failed check verbatim

Then show one working query as proof the database answers questions:

```sql
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;
```
