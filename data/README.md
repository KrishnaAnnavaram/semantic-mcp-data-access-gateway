# U.S. Treasury interest-rate source data

The source of record for this repository. Everything here is produced by stage 0
(acquisition) and consumed by stage 2 (loading) — see
[docs/system-overview.md](../docs/system-overview.md).

No financial metric (return, duration, DV01, VaR, ES, spread, breakeven,
interpolated curve, PCA, stress scenario) is calculated anywhere in this pipeline,
at any stage. It ends at trustworthy facts.

> **`raw/` is immutable.** Once written, a raw Treasury XML file is never edited
> or patched. Only `--refresh` replaces one, in full. `.claude/settings.json`
> denies write access to `raw/` for exactly this reason.

Last successful refresh (UTC): **2026-08-12T04:48:42Z**
Overall validation status: **WARNING** (2 of 5 datasets carry reviewable warnings;
0 failures, 0 failed downloads — see [Validation](#8-validation-performed)).

---

## 1. Official source

Everything here comes from the U.S. Department of the Treasury and nowhere else.
No Kaggle, FRED, Yahoo, GitHub mirror, third-party API or scraped copy is involved.

| | |
| --- | --- |
| Organisation | U.S. Department of the Treasury |
| Base URL | `https://home.treasury.gov` |
| Endpoint | `/resource-center/data-chart-center/interest-rates/pages/xml` |
| Request pattern | `?data=<data_key>&field_tdr_date_value=<yyyy>` |
| Feed format | Atom/OData XML (`text/xml`), OData EDM primitive types |
| Authentication | none required |

Documentation verified live on 2026-08-11 before the downloader was written:

- <https://home.treasury.gov/treasury-daily-interest-rate-xml-feed>
- <https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rate-archives>

The endpoint, the five data keys and the per-dataset start years used by the
downloader were all read from that documentation rather than assumed. The feed
also documents `field_tdr_date_value=all&page=<n>` (paginated, 300 rows/page) and
`field_tdr_date_value_month=<yyyymm>`; the per-year form is used here because it
gives one immutable raw artefact per year, retryable in isolation.

**Deviations from the original task brief:** none. The endpoint pattern and all
five data keys in the brief match the current official documentation exactly. The
brief's illustrative maturity list is *not* what the feed returns — the actual
column names are Treasury's internal codes (`BC_1MONTH`, `TC_5YEAR`,
`ROUND_B1_CLOSE_4WK_2`, …) and every field returned is preserved verbatim rather
than mapped to a fixed list.

## 2. Datasets downloaded

| Data key | Dataset | Raw dir | Processed file | First year (per Treasury) |
| --- | --- | --- | --- | --- |
| `daily_treasury_yield_curve` | Daily Treasury Par Yield Curve Rates | `raw/us_treasury/par_yield_curve/` | `processed/us_treasury/par_yield_curve.csv` | 1990 |
| `daily_treasury_bill_rates` | Daily Treasury Bill Rates | `raw/us_treasury/bill_rates/` | `processed/us_treasury/bill_rates.csv` | 2002 |
| `daily_treasury_long_term_rate` | Daily Treasury Long-Term Rates | `raw/us_treasury/long_term_rates/` | `processed/us_treasury/long_term_rates.csv` | 2000 |
| `daily_treasury_real_yield_curve` | Daily Treasury Par Real Yield Curve Rates | `raw/us_treasury/real_yield_curve/` | `processed/us_treasury/real_yield_curve.csv` | 2003 |
| `daily_treasury_real_long_term` | Daily Treasury Real Long-Term Rates | `raw/us_treasury/real_long_term_rates/` | `processed/us_treasury/real_long_term_rates.csv` | 2000 |

## 3. Dataset descriptions

### Daily Treasury Par Yield Curve Rates (`daily_treasury_yield_curve`)

Par yields on the most recently auctioned Treasury securities, on a
bond-equivalent, semi-annual coupon basis, from Treasury's monotone-convex
par-yield curve methodology. One row per business day; date field `NEW_DATE`.

Maturity columns actually returned: `BC_1MONTH`, `BC_1_5MONTH`, `BC_2MONTH`,
`BC_3MONTH`, `BC_4MONTH`, `BC_6MONTH`, `BC_1YEAR`, `BC_2YEAR`, `BC_3YEAR`,
`BC_5YEAR`, `BC_7YEAR`, `BC_10YEAR`, `BC_20YEAR`, `BC_30YEAR`, plus
`BC_30YEARDISPLAY` and `Id`.

> **Par, not spot.** These are par yields — not zero-coupon/spot rates, not
> forward rates, and not executable trade prices. Bootstrapping a zero curve is a
> downstream modelling decision, deliberately not done here.

### Daily Treasury Bill Rates (`daily_treasury_bill_rates`)

Closing market bid quotes for the most recently auctioned bill at each benchmark
tenor (4, 6, 8, 13, 17, 26, 52 weeks), with the CUSIP and maturity date of the
bill actually quoted. One row per business day; date field `INDEX_DATE`
(`QUOTE_DATE` and `CF_NEW_DATE` carry the same day in other representations).

> **Discount rate ≠ coupon-equivalent yield.** `ROUND_B1_CLOSE_*` and
> `CS_*_CLOSE_AVG` are **discount rates** on a bank-discount, actual/360 basis.
> `ROUND_B1_YIELD_*` and `CS_*_YIELD_AVG` are **coupon-equivalent yields**. They
> are different quantities and must never be placed on the same curve as the
> coupon-basis par yields above.

### Daily Treasury Long-Term Rates (`daily_treasury_long_term_rate`)

Published in **tall/long format**: one row per `(QUOTE_DATE, RATE_TYPE)`. Three
rate types are present for every day of the history — `BC_20year`,
`Over_10_Years` and `Real_Rate` (6,655 rows each). `EXTRAPOLATION_FACTOR` is
populated only between 2002-02-19 and 2006-02-08, the window in which the 30-year
bond was unavailable and Treasury extrapolated the long-term rate; it is untyped
in the source XML and therefore preserved as text.

> The `Real_Rate` rows sit inside this otherwise nominal feed. Do not merge them
> with `BC_20year` / `Over_10_Years` into a single nominal series.

### Daily Treasury Par Real Yield Curve Rates (`daily_treasury_real_yield_curve`)

Par **real** yield curve rates derived from TIPS: `TC_5YEAR`, `TC_7YEAR`,
`TC_10YEAR`, `TC_20YEAR`, `TC_30YEAR`. One row per business day; date field
`NEW_DATE`.

> Negative values are normal and correct for real yields. They are not errors and
> must never be clipped, floored or treated as missing. Nominal minus real is a
> breakeven-inflation calculation and is not performed here.

### Daily Treasury Real Long-Term Rates (`daily_treasury_real_long_term`)

Treasury's long-term real rate average: the unweighted average of bid real yields
on TIPS with more than 10 years remaining maturity. Two columns only —
`QUOTE_DATE` and `RATE`.

## 4. Historical coverage actually obtained

| Dataset | Requested years | Downloaded | Failed | First obs. | Last obs. | Rows | Cols | Raw files | Processed size |
| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: |
| Par Yield Curve | 1990–2026 | 37 | 0 | 1990-01-02 | 2026-08-11 | 9,159 | 17 | 37 | 1.01 MB |
| Bill Rates | 2002–2026 | 25 | 0 | 2002-01-02 | 2026-08-11 | 6,157 | 48 | 25 | 1.61 MB |
| Long-Term Rates | 2000–2026 | 27 | 0 | 2000-01-03 | 2026-08-11 | 19,965 | 5 | 27 | 1.49 MB |
| Par Real Yield Curve | 2003–2026 | 24 | 0 | 2003-01-02 | 2026-08-11 | 5,906 | 7 | 24 | 0.48 MB |
| Real Long-Term Rates | 2000–2026 | 27 | 0 | 2000-01-03 | 2026-08-11 | 6,655 | 2 | 27 | 0.38 MB |
| **Total** | | **140** | **0** | | | **47,842** | | **140** | **~59.6 MB incl. raw** |

Coverage starts exactly at each dataset's documented first year and runs to the
latest published business day. No year was skipped and no year returned zero
observations.

## 5. Exact download process

1. One HTTP `GET` per `(dataset, year)`:
   `…/pages/xml?data=<data_key>&field_tdr_date_value=<yyyy>`
2. Response accepted only on HTTP 200 with an XML content type that parses into
   an Atom `<feed>`; anything else is retried.
3. Retries: up to 5 attempts on transport errors, timeouts and HTTP
   408/425/429/5xx, with exponential backoff plus jitter (cap 60 s). Non-retryable
   HTTP statuses fail the year and are recorded as such rather than silently
   skipped. Timeouts: 15 s connect, 180 s read. A 0.4 s courtesy delay separates
   successful requests.
4. Raw bytes are written verbatim to
   `raw/us_treasury/<dataset>/<data_key>_<year>.xml` via a `.part` temp file and
   an atomic replace, so a partial write can never masquerade as a valid raw file.
5. Each raw file is parsed, normalised and appended to the per-dataset table,
   then the manifest, schema report and validation reports are regenerated.

Every request is recorded in `metadata/us_treasury/download_manifest.json` with:
source organisation, dataset name, data key, request URL, requested year, UTC
download timestamp, HTTP status, content type, attempt count, elapsed seconds,
bytes, output filename, SHA-256 checksum, record count, columns returned, feed
`<updated>` timestamp, earliest/latest observation date and success/failure.

## 6. How to rerun the downloader

```bash
pip install requests           # only third-party dependency; run on Python 3.11

# everything, all history, all five datasets
python .claude/acquisition/download_us_treasury.py

# one dataset
python .claude/acquisition/download_us_treasury.py --dataset daily_treasury_yield_curve

# a year range (clamped to each dataset's documented first year)
python .claude/acquisition/download_us_treasury.py --start-year 2020 --end-year 2026

# force re-download of every year, ignoring cached raw files
python .claude/acquisition/download_us_treasury.py --refresh

# write the tree somewhere else
python .claude/acquisition/download_us_treasury.py --output-dir /path/to/data
```

Reruns are safe and idempotent. A year whose raw file already exists and still
parses is not re-fetched; the current year **is** always re-fetched because
Treasury appends to it daily (disable with `--no-refresh-current-year`).

`--dataset` and the year range restrict what is *fetched*, never what is
*written*: every processed CSV and every report is rebuilt from all raw files
present on disk. A targeted run therefore refreshes its slice without truncating
that dataset's history or dropping the other four from the manifest and reports.
The process exits non-zero only if a dataset validates as `FAIL`.

## 7. Raw vs processed data

**`raw/us_treasury/`** — the exact bytes Treasury returned, one XML file per
dataset-year, checksummed in the manifest. These are the source of record and are
**never overwritten or edited** after download (`--refresh` replaces a whole file
with a freshly downloaded one; nothing is patched in place).

**`processed/us_treasury/`** — one CSV per dataset, rebuilt from the raw files.
Only representational changes are applied:

- XML parsed; every field Treasury returned is kept, under its original name;
- dates standardised to `YYYY-MM-DD` (source `Edm.DateTime` literals are all
  midnight; the `MM/DD/YYYY` string field `CF_NEW_DATE` is standardised too);
- Treasury's missing tokens (`N/A`, empty element, `m:null="true"`) → **NULL**;
- values declared numeric by the feed's OData type are parsed as numbers, and any
  that fail to parse are reported as errors rather than dropped;
- rows sorted chronologically by the dataset's natural key;
- exact duplicate source records removed **only after being logged** (0 found);
- two lineage columns appended, `_source_year` and `_source_file`, prefixed with
  `_` to keep them clearly distinct from Treasury fields.

Nothing is renamed, rescaled, converted between quoting conventions, or derived.
Rates are in percent exactly as published (`3.72` means 3.72%).

## 8. Validation performed

Reports: `metadata/us_treasury/validation_report.json` and
`validation_report.md`; per-column schema history in `schema_report.json`.

- **Completeness** — every requested year downloaded; no year empty; earliest and
  latest observation recorded; expected business days derived from the U.S.
  federal holiday calendar, Good Friday (bond market closed) and a list of ad-hoc
  closures (9/11, Reagan and Nixon mourning days, Hurricane Sandy, G.H.W. Bush,
  Carter). **Result: 0 unexplained business-day gaps in any dataset.**
- **Duplicates** — exact duplicate records and natural-key duplicates counted
  separately. **Result: 0 and 0.** Natural keys observed: `NEW_DATE` (par and real
  yield curves), `INDEX_DATE` (bills), `QUOTE_DATE` (real long-term), and
  `(QUOTE_DATE, RATE_TYPE)` (long-term rates — a date legitimately has 3 rows).
- **Numeric** — every value in a Treasury-typed numeric field parses as a number
  (0 parse failures). Levels outside −10 %…+25 % and day-over-day moves above
  1.50 pp are **flagged for review, never removed**; negative rates are not
  treated as errors.
- **Dates** — all dates are valid calendar dates, chronologically ordered, with no
  observation later than the run date and none on a weekend.
- **Missing values** — total / non-null / null / null % reported for every column.
  Missing stays missing: no zero-fill, forward-fill, interpolation or averaging
  anywhere.
- **Cross-year continuity** — per-year record counts, plus columns appearing and
  disappearing between consecutive years.

### Warnings raised (nothing was corrected in the data)

| Dataset | Status | Warning |
| --- | --- | --- |
| Par Yield Curve | WARNING | `BC_30YEARDISPLAY` is a literal `0` for 5,256 rows (1990-01-02 → 2010-12-31) — a placeholder, not a rate. One day-over-day flag, the 2011-01-03 transition out of that placeholder run. |
| Par Real Yield Curve | WARNING | Two flagged moves on 2008-12-01 (`TC_5YEAR` −2.14 pp, `TC_7YEAR` −1.59 pp) — the genuine post-Lehman TIPS dislocation, retained as published. |
| Bill Rates / Long-Term / Real Long-Term | PASS | — |

## 9. Known data limitations

1. **`BC_30YEARDISPLAY` placeholder zeros.** Treasury publishes `0` for this
   display column on every date before 2011-01-03. Loading it as a rate puts a 0 %
   30-year yield into 21 years of history. Use `BC_30YEAR`; treat the pre-2011
   `BC_30YEARDISPLAY` zeros as absent.
2. **Genuine 0.00 % prints exist and are not missing values.** `BC_1MONTH` (100
   rows), `BC_3MONTH` (18), `BC_2MONTH` (2), several bill and TIPS columns hit
   exactly 0.00 during 2008-12, 2011, 2015 and 2020–21. These are real
   observations.
3. **Maturities appear and disappear over time.** `BC_20YEAR` from 1993;
   `BC_1MONTH` from 2001; `BC_30YEAR` present to 2002, **absent 2003–2005** (bond
   discontinued), back from 2006; `BC_2MONTH` from 2018; `BC_4MONTH` from 2022;
   `BC_1_5MONTH` from 2025. Bills: 52-week columns present in 2002, absent
   2003–2007, back from 2008; 8-week from 2018; 17-week from 2022; 6-week from
   2025. Real curve: `TC_20YEAR` from 2004, `TC_30YEAR` from 2010. This is why the
   par yield curve is 19 % null and bill rates 36 % null — the tenor did not exist,
   not a data defect.
4. **The `Id` / `DailyTreasuryBillRateDataId` /
   `DailyTreasuryRealYieldCurveRateDataId` columns are unreliable.** They are
   Treasury internal row identifiers, are not ordered by date, restart across
   years, and were **omitted entirely from the 2023 and 2024 responses** before
   returning in 2025. They are not a usable key.
5. **`EXTRAPOLATION_FACTOR`** is null for 85 % of long-term rows because it only
   applies to 2002-02-19 → 2006-02-08. It is untyped in the source and kept as
   text.
6. **Published curve, not tradable prices.** These are Treasury's end-of-day
   indicative quotes; they are not executable levels and carry no bid/ask.
7. **The current year is a moving target.** The current-year file is re-downloaded
   on every run; the manifest timestamp and checksum tell you which vintage a
   given CSV was built from.
8. **Revisions.** Treasury can restate prior days. Raw files are only replaced by
   an explicit `--refresh`, so a rerun without it will not pick up a revision to a
   closed year.

## 10. Layout

```
data/
├── raw/us_treasury/<dataset>/<data_key>_<year>.xml   140 immutable source files
├── processed/us_treasury/<dataset>.csv               5 normalised tables
├── metadata/us_treasury/
│   ├── download_manifest.json     per-request lineage + SHA-256
│   ├── schema_report.json         per-column history, types, null counts
│   ├── validation_report.json     machine-readable validation      ← stage 0
│   ├── validation_report.md       human-readable validation        ← stage 0
│   ├── load_verification.json     database reconciliation          ← stage 3
│   └── load_verification.md       database reconciliation          ← stage 3
└── README.md
```

## 11. Where this data goes

| Stage | Tool | Produces |
| --- | --- | --- |
| 0 — acquire | [`.claude/acquisition/download_us_treasury.py`](../.claude/acquisition/download_us_treasury.py) | everything in this directory |
| 2 — load | [`.claude/loading/load_us_treasury.py`](../.claude/loading/load_us_treasury.py) | `staging` → `treasury` → `analytics` in PostgreSQL |
| 3 — verify | [`tools/verify_load.py`](../tools/verify_load.py) | `load_verification.*` and `meta.reconciliation` |

The loader re-verifies every raw file's SHA-256 against `download_manifest.json`
before staging anything, and recounts the non-null rate cells in each CSV
independently to check what was loaded. The two documents in this directory that
begin `load_verification` are the evidence that the database matches these files.

Setup instructions: [docs/postgres-setup.md](../docs/postgres-setup.md).
