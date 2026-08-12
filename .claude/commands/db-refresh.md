---
description: Pull the latest Treasury business day and reload it into PostgreSQL
---

Bring both the source data and the database up to the latest published
business day.

Treasury posts each business day's rates around 4:15 PM ET. If it is earlier
than that, the latest available data is the previous business day and there
will be nothing new — say so plainly rather than presenting an unchanged run as
a refresh.

## 1. Refresh the source

```bash
python .claude/acquisition/download_us_treasury.py
```

The current year is always re-fetched; cached prior years are not. Note the
`Historical range` line for each dataset and whether the last date advanced.

If nothing advanced, stop here and report that the data was already current,
including the date it is current to.

## 2. Reload

```bash
python .claude/loading/load_us_treasury.py
```

The load is delete-then-insert per dataset, so this is a full, consistent
reload rather than an append — reruns are safe.

## 3. Verify

```bash
python tools/verify_load.py --self-test
```

## 4. Report

- previous latest date → new latest date, per dataset
- rows added
- verification result

If the loader aborts naming an unmapped column, Treasury has started publishing
a new series. Report the column and stop — registering it requires a migration
and a deliberate `quote_basis` decision.

If any prior year's checksum has changed, Treasury has restated history. Do not
work around it: report it, because a silent revision to a closed period is
something a market-risk owner needs to know about explicitly.
