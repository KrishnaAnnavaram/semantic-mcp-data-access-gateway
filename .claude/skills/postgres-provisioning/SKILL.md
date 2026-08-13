---
name: postgres-provisioning
description: >
  Stand up the project's PostgreSQL 17 instance with Docker Compose and bring
  the schema to the current version with the migration runner. Use when setting
  up a fresh machine, recovering a broken database, adding a migration, or
  diagnosing a connection or port conflict. Covers the four-schema layout, the
  forward-only migration contract, and the checksum guard that stops two
  developers' databases from silently diverging.
---

# PostgreSQL provisioning

## What it is

Stage 1. A container and a schema — nothing about it is specific to Treasury
data, which is why it is a separate stage from loading.

```
docker-compose.yml ──► smdag-postgres (postgres:17-alpine, :5432)
                              │
                              ▼
db/init/01_bootstrap.sql   once, on an empty volume: UTC, ISO dates, readonly role
.claude/src/postgres/migrations/V001..V007   every run: schemas, tables, series registry, views, grants
```

## Run it

```bash
cp .env.example .env          # then set a real password
docker compose up -d
docker compose ps             # expect: Up (healthy)

python -m treasury_db.migrate            # apply pending
python -m treasury_db.migrate --status   # what is applied, what is pending
python -m treasury_db.migrate --dry-run  # list pending, change nothing
```

## The four schemas

| Schema | Holds | Who reads it |
|---|---|---|
| `meta` | Load runs, source files + SHA-256, reconciliation results | Anyone asking "where did this come from" |
| `staging` | One table per CSV, Treasury's own column names | Nobody, routinely. It is the arbiter when a number is disputed |
| `treasury` | `dataset`, `series`, `observation` + reference tables | The loader, and anything that needs unfiltered truth |
| `analytics` | Views only | **Consumers. Start here.** |

## The migration contract

1. **Applied exactly once**, in filename order, `V<number>__<name>.sql`.
2. **One transaction each.** A failure rolls that migration back completely.
3. **Checksummed.** Every applied file's SHA-256 is recorded. Edit an applied
   migration and the next run **fails** rather than ignoring the change —
   editing an applied migration is the most common way a team's databases drift
   apart, and the failure is the feature.
4. **Forward only.** To change something, add `V00N+1`. There is no downgrade
   path and adding one would be a lie: dropping a column does not restore the
   data it held.

## Adding a migration

```bash
# next free number, descriptive name
$EDITOR .claude/src/postgres/migrations/V008__add_bc_2_5month.sql
python -m treasury_db.migrate
```

Write it idempotently — `IF NOT EXISTS`, `ON CONFLICT DO UPDATE`, guarded
`CREATE TYPE`. Re-running the suite against a current database must be a no-op,
not an error. Add `COMMENT ON` for anything a reader could misread; those
comments are the only documentation that reaches someone browsing the database
in DBeaver.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| Container will not start, port in use | A native PostgreSQL already owns 5432 | Set `POSTGRES_PORT=5433` in `.env`, or stop the service |
| `password authentication failed` | `.env` edited after the volume was initialised | `POSTGRES_PASSWORD` is only read on first init — `ALTER USER`, or `docker compose down -v` to start over (destroys data) |
| `applied migrations have been edited` | Someone changed a `V00N` file that already ran | Revert the edit; add a new migration instead |
| `dataset(s) not registered` from the loader | Migrations not applied | `python -m treasury_db.migrate` |

## Rebuilding from nothing

```bash
docker compose down -v      # destroys the volume and all data
docker compose up -d
python -m treasury_db.migrate
python -m treasury_db.load
python tools/verify_load.py --self-test
```

Four commands from empty to verified. That path is exercised, not assumed — it
is how the current database was built.

Schema reference: @docs/database-schema.md
