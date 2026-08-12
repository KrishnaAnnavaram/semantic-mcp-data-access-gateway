# PostgreSQL load verification

- Target: `postgresql://gateway:***@localhost:5432/gateway`
- Load run: **4**
- Generated (UTC): **2026-08-12T06:09:58+00:00**
- Result: **PASS** (58/58 checks passed)

Every expected value below is recounted from the processed CSVs, not read back from the database.

| Check | Dataset | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| `manifest_files_registered` | - | 140 | 140 | PASS |
| `all_checksums_verified` | - | 0 | 0 | PASS |
| `load_run_succeeded` | - | succeeded | succeeded | PASS |
| `no_failed_load_steps` | - | 0 | 0 | PASS |
| `staging_rows` | daily_treasury_bill_rates | 6157 | 6157 | PASS |
| `observations` | daily_treasury_bill_rates | 105204 | 105204 | PASS |
| `distinct_dates` | daily_treasury_bill_rates | 6157 | 6157 | PASS |
| `first_observation` | daily_treasury_bill_rates | 2002-01-02 | 2002-01-02 | PASS |
| `last_observation` | daily_treasury_bill_rates | 2026-08-11 | 2026-08-11 | PASS |
| `value_sample_mismatches` | daily_treasury_bill_rates | 0 | 0 | PASS |
| `staging_rows` | daily_treasury_long_term_rate | 19965 | 19965 | PASS |
| `observations` | daily_treasury_long_term_rate | 19965 | 19965 | PASS |
| `distinct_dates` | daily_treasury_long_term_rate | 6655 | 6655 | PASS |
| `first_observation` | daily_treasury_long_term_rate | 2000-01-03 | 2000-01-03 | PASS |
| `last_observation` | daily_treasury_long_term_rate | 2026-08-11 | 2026-08-11 | PASS |
| `value_sample_mismatches` | daily_treasury_long_term_rate | 0 | 0 | PASS |
| `staging_rows` | daily_treasury_real_long_term | 6655 | 6655 | PASS |
| `observations` | daily_treasury_real_long_term | 6655 | 6655 | PASS |
| `distinct_dates` | daily_treasury_real_long_term | 6655 | 6655 | PASS |
| `first_observation` | daily_treasury_real_long_term | 2000-01-03 | 2000-01-03 | PASS |
| `last_observation` | daily_treasury_real_long_term | 2026-08-11 | 2026-08-11 | PASS |
| `value_sample_mismatches` | daily_treasury_real_long_term | 0 | 0 | PASS |
| `staging_rows` | daily_treasury_real_yield_curve | 5906 | 5906 | PASS |
| `observations` | daily_treasury_real_yield_curve | 27354 | 27354 | PASS |
| `distinct_dates` | daily_treasury_real_yield_curve | 5906 | 5906 | PASS |
| `first_observation` | daily_treasury_real_yield_curve | 2003-01-02 | 2003-01-02 | PASS |
| `last_observation` | daily_treasury_real_yield_curve | 2026-08-11 | 2026-08-11 | PASS |
| `value_sample_mismatches` | daily_treasury_real_yield_curve | 0 | 0 | PASS |
| `staging_rows` | daily_treasury_yield_curve | 9159 | 9159 | PASS |
| `observations` | daily_treasury_yield_curve | 108339 | 108339 | PASS |
| `distinct_dates` | daily_treasury_yield_curve | 9159 | 9159 | PASS |
| `first_observation` | daily_treasury_yield_curve | 1990-01-02 | 1990-01-02 | PASS |
| `last_observation` | daily_treasury_yield_curve | 2026-08-11 | 2026-08-11 | PASS |
| `value_sample_mismatches` | daily_treasury_yield_curve | 0 | 0 | PASS |
| `placeholder_rows_recorded` | daily_treasury_yield_curve | 5256 | 5256 | PASS |
| `placeholders_have_no_rate` | - | 0 | 0 | PASS |
| `placeholders_excluded_from_analytics` | - | 0 | 0 | PASS |
| `no_zero_30y_in_analytics` | - | 0 | 0 | PASS |
| `future_dated_observations` | - | 0 | 0 | PASS |
| `observations_without_series` | - | 0 | 0 | PASS |
| `data_key_disagreements` | - | 0 | 0 | PASS |
| `duplicate_observation_keys` | - | 0 | 0 | PASS |
| `series_without_observations` | - | 0 | 0 | PASS |
| `rates_outside_plausible_band` | - | 0 | 0 | PASS |
| `bill_securities_mature_after_quote` | - | 0 | 0 | PASS |
| `view_queryable:v_series` | - | True | True | PASS |
| `view_queryable:v_observation` | - | True | True | PASS |
| `view_queryable:v_par_yield_curve` | - | True | True | PASS |
| `view_queryable:v_real_yield_curve` | - | True | True | PASS |
| `view_queryable:v_bill_rates_quoted` | - | True | True | PASS |
| `view_queryable:v_long_term_rates` | - | True | True | PASS |
| `view_queryable:v_latest_rates` | - | True | True | PASS |
| `view_queryable:v_series_coverage` | - | True | True | PASS |
| `view_queryable:v_dataset_summary` | - | True | True | PASS |
| `constraint:treasury.observation:p` | - | >=1 | 1 | PASS |
| `constraint:treasury.observation:f` | - | >=2 | 2 | PASS |
| `constraint:treasury.series:f` | - | >=1 | 1 | PASS |
| `check_constraints_on_observation` | - | >=2 | 2 | PASS |
