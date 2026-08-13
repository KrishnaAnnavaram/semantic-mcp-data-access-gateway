# Loading contract — how to extend the pipeline

What to change, and what deliberately does not need changing, when Treasury
publishes something new.

## The shape of the loader

One declarative spec per dataset. Everything else is generic.

```python
LOAD_SPECS["daily_treasury_yield_curve"] = LoadSpec(
    data_key="daily_treasury_yield_curve",
    csv_name="par_yield_curve.csv",
    staging_table="par_yield_curve",
    date_column="new_date",
    shape="wide",                      # or "long"
    ignore_columns=("id",),            # non-rate columns
    ignore_patterns=(r"cusip_\w+",),   # regex, for families of them
    extras=("bill_security",),         # dataset-specific side tables
)
```

There is no list of maturities anywhere in the loader. Wide datasets are
unpivoted generically:

```sql
FROM staging.<table> st
CROSS JOIN LATERAL jsonb_each_text(to_jsonb(st) - <ignored>) AS kv(key, value)
JOIN treasury.series s ON s.data_key = :key AND lower(s.series_code) = kv.key
WHERE kv.value IS NOT NULL
```

Every column becomes a key/value pair, and the join to `treasury.series`
decides which are rates.

## The guard that makes that safe

That join is also the hazard: an unregistered column would simply vanish, and
every number that remained would still look correct. Nobody notices a maturity
that is missing from a curve they have never seen complete.

So before any insert runs:

```
staging columns − ignored  ⊆  registered series codes
```

Violation aborts the load naming the column:

```
daily_treasury_yield_curve: staging column(s) with no registered series:
['bc_2_5month']. Treasury has published a series this database does not know
about. Add it in a migration - do not let the load drop it.
```

For tall datasets the same check runs over `SELECT DISTINCT rate_type`.

**This failure is the feature.** Silence would be the defect.

## Adding a maturity Treasury has started publishing

Say `BC_2_5MONTH` appears. Acquisition picks it up with no change at all — it
never hard-codes fields — and `schema_report.json` will show a new column. Then
the loader stops. Three edits:

**1. Staging column** — a **new** migration, never an edit to an applied one:

```sql
-- .claude/src/postgres/migrations/V008__add_bc_2_5month.sql
ALTER TABLE staging.par_yield_curve
    ADD COLUMN IF NOT EXISTS bc_2_5month numeric(9,4);
```

**2. Register the series:**

```sql
INSERT INTO treasury.series (
    data_key, series_code, display_name, rate_kind, quote_basis,
    tenor_label, tenor_value, tenor_unit, tenor_years
) VALUES (
    'daily_treasury_yield_curve', 'BC_2_5MONTH', '2.5 Month Par Yield',
    'nominal', 'par_coupon_semiannual', '2.5 Month', 2.5, 'month', 2.5/12.0
)
ON CONFLICT (data_key, series_code) DO UPDATE
    SET display_name = EXCLUDED.display_name;
```

**3. If a consumer needs it in the wide view**, add the pivot column in the
same migration. The tidy `v_observation` needs nothing.

```bash
python -m treasury_db.migrate
python -m treasury_db.load
python tools/verify_load.py --self-test
```

### The decision that actually matters

`quote_basis`. Getting `rate_kind` wrong is visible — a real yield among
nominals looks odd immediately. Getting `quote_basis` wrong is not: a discount
rate registered as `coupon_equivalent` sits quietly in a curve until someone
prices off it. If you are unsure, read what Treasury calls the field and match
it; do not infer from the values.

## Adding a sixth dataset

1. **Acquisition** — add a `DatasetSpec` in `download_us_treasury.py` with the
   data key, documented first year, date field, natural key, shape, and the
   market-risk `caveat`. Run it and read the schema report.
2. **Staging table** — new migration, one column per CSV column, typed.
3. **`treasury.dataset` row** — including the caveat, which travels into the
   database on purpose.
4. **`treasury.series` rows** — one per rate-bearing column.
5. **`LOAD_SPECS` entry** — the declarative spec above.
6. **Analytics view** if consumers need a pivoted form.
7. **Nothing in the verifier.** It iterates `LOAD_SPECS` and recounts from the
   CSV; a new dataset is checked automatically.

## Extras

A dataset can carry facts that are not rates — a CUSIP, a maturity date, an
extrapolation factor, a market-closure note. Those get their own table and an
entry in `EXTRA_LOADERS`, keyed by name in `LoadSpec.extras`. They are not
squeezed into `observation`; a CUSIP is not a rate.

Where they can be discovered rather than listed, they are:
`load_bill_security` finds its tenors by scanning staging for `cusip_(\w+)`, so
a new bill tenor needs no code change.

## Rules that hold for any extension

| Rule | Why |
|---|---|
| Never write a row Treasury did not publish | Absence of a rate is not a rate |
| Never drop an unmapped column | The remaining numbers still look right, so nobody notices |
| Never load unverified bytes | Those are not the bytes that were validated upstream |
| Never edit an applied migration | It is how two developers' databases silently diverge |
| Semantics live in the data, not the code | A new placeholder should be an `UPDATE`, not a release |
| Expectations are recounted from source | A check that asks the database what it should contain proves nothing |
| Fail loudly, mid-load, and record it | A half-loaded database reporting success is the worst outcome available |

## Verify before you commit

```bash
python -m treasury_db.migrate --status
python -m treasury_db.load
python tools/verify_load.py --self-test
```

Expected: `self-test OK`, then `Verification PASS: 58/58 checks passed`. There
is no CI. These three commands are the only thing between a defect and `main`.
