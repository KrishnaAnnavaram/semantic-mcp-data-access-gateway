---
name: treasury-acquisition
description: >
  Download and validate the official U.S. Treasury daily interest-rate
  datasets. Use when source data must be refreshed, backfilled, or when
  deciding whether a suspect number is a source fact or a pipeline defect.
  Covers the five data keys, the year-by-year XML feed, and the known traps
  (placeholder zeros, maturities that appear and disappear, discount rates vs
  coupon-equivalent yields).
---

# Treasury acquisition

## What it is

Stage 0. One HTTP GET per dataset-year against Treasury's official Atom/OData
feed, one immutable raw XML file per response, then five normalised CSVs and
three reports derived from those files.

```
home.treasury.gov ──GET──► data/raw/…/<data_key>_<year>.xml   (immutable)
                                        │
                                        ▼
                           data/processed/…/<dataset>.csv
                           data/metadata/…/download_manifest.json
                                        …/schema_report.json
                                        …/validation_report.{json,md}
```

## When to use it

- The latest business day is missing and you need today's curve.
- A year failed and needs a retry.
- Someone asks "is this number wrong, or did Treasury publish it that way?"
- Treasury may have changed the feed and you need the schema report to say so.

## When not to use it

- To load the database — that is `postgres-loading`.
- To compute anything. No returns, no DV01, no VaR, no breakevens, no
  bootstrapped zero curve. This stage produces facts, not analytics.

## Endpoint

Verified against Treasury's documentation, which is the source of truth:

```
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml
    ?data=<data_key>&field_tdr_date_value=<yyyy>
```

| Data key | Available from |
|---|---|
| `daily_treasury_yield_curve` | 1990 |
| `daily_treasury_bill_rates` | 2002 |
| `daily_treasury_long_term_rate` | 2000 |
| `daily_treasury_real_yield_curve` | 2003 |
| `daily_treasury_real_long_term` | 2000 |

Year-by-year rather than `field_tdr_date_value=all`: a failure retries in
isolation, a missing year is visible, and each year is one immutable artifact
with its own checksum.

## Run it

```bash
python .claude/acquisition/download_us_treasury.py
python .claude/acquisition/download_us_treasury.py --dataset daily_treasury_yield_curve
python .claude/acquisition/download_us_treasury.py --start-year 2020 --end-year 2026
python .claude/acquisition/download_us_treasury.py --refresh
```

The current year is always re-fetched; Treasury appends to it daily. Cached
years are not. `--dataset` and the year range restrict fetching only — outputs
are always rebuilt from every raw file on disk.

## The rule everything rests on

**A missing observation is NULL. Never zero, never carried forward, never
interpolated.**

And its mirror image, which is easier to get wrong: **an exact 0 is not
automatically missing.** Short tenors genuinely printed 0.00% in 2008-12, 2011,
2015 and 2020-21. Only `BC_30YEARDISPLAY`, whose entire pre-2011 history is an
unbroken run of literal zeros, is a placeholder — and that judgement is
recorded as data, not code.

## What to read afterwards

`data/metadata/us_treasury/validation_report.md`. Failed years must be `0`.
Every warning must be explained, not merely present. A new column in
`schema_report.json` means Treasury has added a series, and the database loader
will refuse to run until that series is registered — by design.

Full contract: @docs/data-contract.md
