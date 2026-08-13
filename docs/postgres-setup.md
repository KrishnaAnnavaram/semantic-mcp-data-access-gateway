# PostgreSQL setup

From a fresh clone to a verified database. Four commands if nothing goes wrong,
and this document covers the cases where something does.

## Prerequisites

| | Version used | Check |
|---|---|---|
| Docker Desktop | 27.3.1 | `docker --version` |
| Docker Compose | v2.30.3 | `docker compose version` |
| Python | 3.11 | `python --version` |
| `psycopg2` | 2.9.11 | `pip install psycopg2-binary` |
| `requests` | 2.32.5 | Only needed to re-download source data |

No PostgreSQL client installation is required — `psql` is used through the
container.

## 1. Configure

```bash
cp .env.example .env
```

Edit `.env` and set a real `POSTGRES_PASSWORD`. Keep `DATABASE_URL` in sync
with it; the loader reads either, preferring `DATABASE_URL`.

`.env` is git-ignored and must stay that way.

> If a native PostgreSQL already owns port 5432, set `POSTGRES_PORT=5433` in
> `.env` rather than stopping that service.

## 2. Start the database

```bash
docker compose up -d
docker compose ps          # wait for: Up (healthy)
```

PostgreSQL 17 Alpine, container `smdag-postgres`, data in the `postgres-data`
volume. `db/init/01_bootstrap.sql` runs once on an empty volume and sets UTC,
ISO dates and the read-only role.

## 3. Apply the schema

```bash
python -m treasury_db.migrate
```

```
applying V001 V001__schemas.sql          ok
applying V002 V002__meta.sql             ok
applying V003 V003__staging.sql          ok
applying V004 V004__treasury_core.sql    ok
applying V005 V005__reference_data.sql   ok
applying V006 V006__analytics_views.sql  ok
applying V007 V007__grants.sql           ok
migrated to V007
```

Safe to re-run: applied migrations are skipped.

## 4. Load

The repository ships with the acquired data, so this works immediately:

```bash
python -m treasury_db.load
```

If `data/processed/us_treasury/*.csv` is missing, acquire it first
(~60 MB, ~4 minutes, 140 requests to Treasury):

```bash
python -m acquisition.download_us_treasury
```

Expected: 52 series, 267,517 observations, 140 source files verified.

## 5. Verify

```bash
python tools/verify_load.py --self-test
```

```
self-test OK: corruption detected on BC_1YEAR 1990-01-02, and rolled back cleanly
Verification PASS: 58/58 checks passed
```

**Both lines matter.** A PASS without the self-test line means the suite ran,
not that it works — the self-test plants a corruption and requires the checks
to catch it.

## Connect

Through the container, no client needed:

```bash
docker exec -it smdag-postgres psql -U gateway -d gateway
```

From the host:

```bash
psql "$DATABASE_URL"
```

From a GUI (DBeaver, pgAdmin, DataGrip):

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` (or your `POSTGRES_PORT`) |
| Database | `gateway` |
| Username | `gateway` |
| Password | from `.env` |

First query:

```sql
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;
```

Query `analytics`, not `treasury.observation` — the views are where the source
traps are already excluded.

## Driving it from Claude Code

The repository ships a harness so this is one command rather than five:

| Command | Does |
|---|---|
| `/db-setup` | Preflight, provision, migrate, load, verify, report |
| `/db-refresh` | Pull the latest Treasury business day and reload |
| `/db-check` | Read-only health check; changes nothing |

Skills carrying the detail: `postgres-provisioning`, `postgres-loading`,
`load-verification`, `treasury-acquisition`. Agents: `treasury-acquisition`
(stage 0), `treasury-database-loader` (stages 1-3).

`.claude/settings.json` pre-approves the read-only and routine commands, asks
before `docker compose down` and `git push`, and denies writes to
`data/raw/**` — raw source files are immutable.

## Rebuilding from nothing

```bash
docker compose down -v          # destroys the volume and all data
docker compose up -d
python -m treasury_db.migrate
python -m treasury_db.load
python tools/verify_load.py --self-test
```

This is the exercised path, not a hopeful one — it is how the current database
was built.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `port is already allocated` | Native PostgreSQL owns 5432 | `POSTGRES_PORT=5433` in `.env`, then `docker compose up -d` |
| `password authentication failed` | `.env` changed after the volume was initialised | `POSTGRES_PASSWORD` is read only on first init. Either `ALTER USER gateway WITH PASSWORD '…'` inside the container, or `docker compose down -v` and start over (destroys data) |
| `could not connect to server` | Container not healthy yet | `docker compose ps`; `docker compose logs postgres` |
| `No module named psycopg2` | Driver missing | `pip install psycopg2-binary` |
| `applied migrations have been edited` | A `V00N` file changed after running | Revert it and add a new migration. Migrations are forward-only by design |
| `dataset(s) not registered in treasury.dataset` | Migrations not applied | `python -m treasury_db.migrate` |
| `staging column(s) with no registered series` | Treasury published a new maturity | Working as intended — see [loading-contract.md](loading-contract.md) |
| `raw source files do not match the manifest` | Raw XML edited or truncated | Re-acquire: `python -m acquisition.download_us_treasury --refresh` |
| Verification fails | Something genuinely diverged | Do **not** adjust the expectation. Work outward: staging vs CSV, CSV vs raw XML, then the model |

## What runs where

| | Talks to Treasury | Talks to PostgreSQL |
|---|---|---|
| `data/acquisition/download_us_treasury.py` | yes | no |
| `.claude/src/postgres/src/treasury_db/migrate.py` | no | yes |
| `.claude/src/postgres/src/treasury_db/load_us_treasury.py` | no | yes |
| `tools/verify_load.py` | no | yes (read-only, except its own audit rows) |

That split is why a database problem can never be mistaken for a data problem.
