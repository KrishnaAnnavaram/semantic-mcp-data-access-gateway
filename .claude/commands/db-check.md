---
description: Health-check the database and report what it actually contains
---

Report the current state of the Treasury database. Read-only — change nothing.

## 1. Is it up?

```bash
docker compose ps
python .claude/loading/migrate.py --status
```

## 2. What does it hold?

```bash
docker exec smdag-postgres psql -U gateway -d gateway -c \
  "SELECT data_key, series, observations, first_observation, last_observation FROM analytics.v_dataset_summary ORDER BY data_key;"
```

## 3. Is it consistent with the source?

```bash
python tools/verify_load.py --self-test
```

## 4. Anything odd?

```bash
docker exec smdag-postgres psql -U gateway -d gateway -c \
  "SELECT check_name, data_key, expected, actual FROM meta.reconciliation WHERE load_run_id = (SELECT max(load_run_id) FROM meta.load_run) AND NOT passed;"
```

An empty result is the answer you want.

## 5. Report

State plainly:

- container health, schema version, last load run and its status
- observations per dataset and the latest date held
- verification result, including whether the self-test caught its planted
  corruption
- any failed check, verbatim

If the latest observation is more than a few business days behind today, say so
and suggest `/db-refresh` — but do not run it. This command does not write.
