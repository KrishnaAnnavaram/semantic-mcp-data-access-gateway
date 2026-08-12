# Database schema

PostgreSQL 17. Four schemas, sixteen tables, nine views, 267,517 observations,
64 MB.

Every table and most columns carry `COMMENT ON`, so this document and the
database agree by construction. In psql: `\d+ treasury.observation`.

## Layers

```
                    ┌──────────────────────────────────────┐
 CSV ──COPY──►      │  staging   one table per CSV,        │  truncated
                    │            Treasury's column names   │  every run
                    └──────────────────┬───────────────────┘
                                       │ generic unpivot
                    ┌──────────────────▼───────────────────┐
                    │  treasury  dataset ─┬─ series ─┬─ observation
                    │                     │          ├─ bill_security
                    │                     │          ├─ long_term_extrapolation
                    │                     └──────────┴─ market_note
                    └──────────────────┬───────────────────┘
                                       │ views only
                    ┌──────────────────▼───────────────────┐
   consumers ◄──────│  analytics  traps already excluded   │
                    └──────────────────────────────────────┘

  meta   load_run ─ load_step ─ source_file ─ reconciliation ─ schema_migration
         written at every step; answers "where did this number come from"
```

## `treasury.observation` — the fact table

267,517 rows, 46 MB.

| Column | Type | |
|---|---|---|
| `series_id` | `integer` | PK, FK → `series` |
| `observation_date` | `date` | PK |
| `data_key` | `text` | Denormalised; composite FK makes drift impossible |
| `rate_percent` | `numeric(9,4)` | **In percent.** NULL only for a placeholder |
| `value_status` | `treasury.value_status` | `observed` \| `source_placeholder` |
| `source_value_percent` | `numeric(9,4)` | What the source printed, when it is not a rate |
| `source_file` | `text` | The raw XML this row came from |
| `load_run_id` | `bigint` | FK → `meta.load_run` |

Constraints that matter:

```sql
CHECK (rate_percent IS NULL OR rate_percent BETWEEN -25 AND 100)
CHECK ( (value_status = 'observed'           AND rate_percent IS NOT NULL)
     OR (value_status = 'source_placeholder' AND rate_percent IS NULL
                                             AND source_value_percent IS NOT NULL) )
```

The band is deliberately wide enough that it can only fire on corruption —
**negative rates are legitimate** and permitted. The second check is the one
doing real work: it makes it structurally impossible for a placeholder to
present itself as a rate.

Indexes: PK `(series_id, observation_date)`, btree on `observation_date`, btree
on `(data_key, observation_date)`, BRIN on `observation_date` for full-history
scans.

> **The absence of a row is the data.** No row for a series on a date means
> Treasury published nothing. It is never a zero, never a carry-forward.

## `treasury.series` — 52 rows, the registry

The table that carries the market-risk semantics.

| Column | Why it exists |
|---|---|
| `series_code` | Treasury's own identifier, exactly: `BC_1MONTH`, `ROUND_B1_CLOSE_4WK_2`, `Real_Rate`. Renaming is how a discount rate ends up labelled a yield |
| `rate_kind` | `nominal` \| `real` |
| `quote_basis` | `par_coupon_semiannual` \| `bank_discount_act360` \| `coupon_equivalent` \| `average_real_yield` |
| `tenor_years` | Canonical ordering key: months/12, weeks×7/365. Lets a 4-week bill (0.0767) sort against a 1-month par point (0.0833) |
| `is_composite` | True where there is no point tenor (`Over_10_Years`) |
| `excluded_from_analytics` + `exclusion_reason` | Loaded in full, withheld from views, with the reason attached |
| `placeholder_zero_before` | Date before which a `0` in this series is filler, not a rate |

`quote_basis` is the single most important column in the schema. Stored as bare
numbers in adjacent columns, a bill discount rate and a par coupon yield look
interchangeable, and eventually someone plots them on one curve. Here that
mistake requires ignoring an explicit label.

`placeholder_zero_before` puts the `BC_30YEARDISPLAY` rule in the data rather
than in code: registering another placeholder is an `UPDATE`, not a release.

Series by dataset: 15 par curve (14 maturities + 1 display variant), 28 bill
(7 tenors × 4 measures), 3 long-term, 5 real curve, 1 real long-term.

## Reference tables

| Table | Rows | Holds |
|---|---|---|
| `treasury.dataset` | 5 | Title, natural key, shape, and the market-risk **caveat**, carried into the database so it survives being copied out of the README |
| `treasury.bill_security` | 26,300 | CUSIP + maturity of the bill actually quoted at each tenor each day. `CHECK (maturity_date > observation_date)` |
| `treasury.long_term_extrapolation` | 994 | Per-date extrapolation factor, 2002-02-19 → 2006-02-08 |
| `treasury.market_note` | 1 | `BOND_MKT_UNAVAIL_REASON` — rare, but the explanation for a gap beats the gap |

## `meta` — lineage

| Table | Holds |
|---|---|
| `load_run` | One row per loader invocation. Failures are recorded, not just successes |
| `load_step` | Per dataset, per phase: `rows_in`, `rows_out`, timing. First thing to read when a count looks wrong |
| `source_file` | 140 rows mirrored from the manifest: URL, SHA-256, records, download timestamp. Unique on `(data_key, year, sha256)`, so a Treasury revision is a **new row**, not an overwrite |
| `reconciliation` | Every verification check with expected vs actual, stored rather than printed |
| `schema_migration` | Version, SHA-256, applied timestamp. The checksum is what turns an edited migration into a loud failure |

## `analytics` — the read layer

Views only, no storage. All filter `value_status = 'observed'` and
`NOT excluded_from_analytics`.

| View | Rows | Use for |
|---|---|---|
| `v_observation` | 258,358 | **Start here.** Tidy: one row per series per day |
| `v_par_yield_curve` | 9,158 | Nominal curve, wide: `m1 m1_5 m2 m3 m4 m6 y1 y2 y3 y5 y7 y10 y20 y30` |
| `v_real_yield_curve` | 5,906 | TIPS curve, wide |
| `v_bill_rates_quoted` | 26,299 | Discount rate and coupon-equivalent yield in **separately named** columns, with CUSIP |
| `v_long_term_rates` | 6,655 | Three long-term series pivoted, real kept distinct from nominal |
| `v_latest_rates` | 51 | Most recent value per series |
| `v_series_coverage` | 52 | When each series starts, stops, and how many zeros it holds |
| `v_dataset_summary` | 5 | Per dataset, with the caveat attached |
| `v_series` | 52 | Catalogue, **including** excluded series so a consumer can see what was withheld and why |

## Grants

`gateway_readonly` (NOLOGIN, grant it to a real user) can read `analytics`,
`meta`, and `treasury.dataset` / `treasury.series`. It cannot read
`treasury.observation` or `staging` — not for secrecy, but because those layers
still contain the placeholder rows, and the views are where that is handled.

## Worked queries

```sql
-- Latest nominal par curve
SELECT * FROM analytics.v_par_yield_curve ORDER BY observation_date DESC LIMIT 1;

-- 2s10s slope
SELECT observation_date, y2, y10, round(y10 - y2, 2) AS slope_2s10s
FROM analytics.v_par_yield_curve
WHERE observation_date >= CURRENT_DATE - 30 ORDER BY 1 DESC;

-- Bill quotes with the two bases kept apart
SELECT observation_date, tenor_label, discount_rate_act360, coupon_equivalent_yield, cusip
FROM analytics.v_bill_rates_quoted
WHERE tenor_label = '4 Week' ORDER BY 1 DESC LIMIT 5;

-- Full curve for one day, tidy and correctly ordered
SELECT series_code, tenor_label, rate_percent
FROM analytics.v_observation
WHERE data_key = 'daily_treasury_yield_curve' AND observation_date = '2026-08-11'
ORDER BY tenor_years;

-- Where did this number come from?
SELECT o.observation_date, o.rate_percent, o.source_file, f.source_url, f.sha256
FROM treasury.observation o
JOIN treasury.series s USING (series_id)
JOIN meta.source_file f ON f.file_name = o.source_file
WHERE s.series_code = 'BC_10YEAR' AND o.observation_date = '2026-08-11';
```

## Adding a maturity

The loader will already have stopped and named the column — it refuses to drop
one silently. See [loading-contract.md](loading-contract.md).
