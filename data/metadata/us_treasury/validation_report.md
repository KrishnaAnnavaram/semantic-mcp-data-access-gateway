# U.S. Treasury interest-rate data - validation report

- Source: **U.S. Department of the Treasury** (https://home.treasury.gov)
- Generated (UTC): **2026-08-12T06:09:33+00:00**
- Feed endpoint: `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml`
- Overall status: **WARNING**

## Totals

| Metric | Value |
| --- | --- |
| Total datasets | 5 |
| Total raw files | 140 |
| Total records | 47842 |
| Total disk size (bytes) | 62493917 |
| Total disk size | 59.6 MB |
| Successful year downloads | 140 |
| Failed year downloads | 0 |

## Daily Treasury Par Yield Curve Rates

- Data key: `daily_treasury_yield_curve`
- Source: U.S. Department of the Treasury
- Historical period: **1990-01-02 -> 2026-08-11**
- Rows: **9,159**
- Columns: **17**
- Raw files: 37
- Processed file: `par_yield_curve.csv`
- Years downloaded: 37 (1990-2026)
- Failed years: none
- Natural key: `NEW_DATE` - duplicates: 0
- Exact duplicate records removed: 0
- Missing expected business days: 0
- Schema changes detected: added {'1993': ['BC_20YEAR'], '2001': ['BC_1MONTH'], '2006': ['BC_30YEAR'], '2018': ['BC_2MONTH'], '2022': ['BC_4MONTH'], '2025': ['BC_1_5MONTH', 'Id']}; removed {'2003': ['BC_30YEAR'], '2023': ['Id']}
- Validation status: **WARNING**

> These are PAR yields, not zero-coupon/spot rates and not executable market prices. BC_30YEAR is absent 2003-2005 because the 30-year bond was discontinued in 2002 and reintroduced in 2006. BC_30YEARDISPLAY is Treasury's display variant and is published as a literal 0 for every date before 2011-01-03 - that 0 is a placeholder, not a 0.00% yield. Use BC_30YEAR as the 30-year series.

### Missing values by column

| Column | Type | Total rows | Non-null | Null | Null % |
| --- | --- | ---: | ---: | ---: | ---: |
| `NEW_DATE` | date | 9,159 | 9,159 | 0 | 0.00 |
| `Id` | integer | 9,159 | 8,501 | 658 | 7.18 |
| `BC_3MONTH` | numeric | 9,159 | 9,155 | 4 | 0.04 |
| `BC_6MONTH` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_1YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_2YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_3YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_5YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_7YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_10YEAR` | numeric | 9,159 | 9,158 | 1 | 0.01 |
| `BC_30YEAR` | numeric | 9,159 | 8,164 | 995 | 10.86 |
| `BC_30YEARDISPLAY` | numeric | 9,159 | 9,159 | 0 | 0.00 |
| `BC_20YEAR` | numeric | 9,159 | 8,219 | 940 | 10.26 |
| `BC_1MONTH` | numeric | 9,159 | 6,259 | 2,900 | 31.66 |
| `BC_2MONTH` | numeric | 9,159 | 1,954 | 7,205 | 78.67 |
| `BC_4MONTH` | numeric | 9,159 | 952 | 8,207 | 89.61 |
| `BC_1_5MONTH` | numeric | 9,159 | 371 | 8,788 | 95.95 |

### Zero-valued rate observations

| Column | Zeros | First | Last | Suspected placeholder |
| --- | ---: | --- | --- | --- |
| `BC_3MONTH` | 18 | 2011-09-22 | 2020-03-26 | no |
| `BC_30YEARDISPLAY` | 5,256 | 1990-01-02 | 2010-12-31 | YES |
| `BC_1MONTH` | 100 | 2008-12-10 | 2021-06-03 | no |
| `BC_2MONTH` | 2 | 2020-03-25 | 2021-05-26 | no |

- `BC_30YEARDISPLAY`: Suspected PLACEHOLDER: the column opens with an unbroken run of 5256 zeros ending 2010-12-31 and holds no other zeros. Treat these as 'no observation', not as a 0.00% rate. Values are preserved exactly as published - the correction belongs in the load/modelling layer, not in the source of record.

### Warnings

- 1 rate observations flagged for review (out-of-band level or large day-over-day move); none removed
- columns whose leading zeros look like placeholders rather than 0.00% rates (preserved as published - must be treated as 'no observation' when loading): BC_30YEARDISPLAY (5256 rows through 2010-12-31)

## Daily Treasury Bill Rates

- Data key: `daily_treasury_bill_rates`
- Source: U.S. Department of the Treasury
- Historical period: **2002-01-02 -> 2026-08-11**
- Rows: **6,157**
- Columns: **48**
- Raw files: 25
- Processed file: `bill_rates.csv`
- Years downloaded: 25 (2002-2026)
- Failed years: none
- Natural key: `INDEX_DATE` - duplicates: 0
- Exact duplicate records removed: 0
- Missing expected business days: 0
- Schema changes detected: added {'2008': ['CS_52WK_CLOSE_AVG', 'CS_52WK_YIELD_AVG', 'CUSIP_52WK', 'MATURITY_DATE_52WK', 'ROUND_B1_CLOSE_52WK_2', 'ROUND_B1_YIELD_52WK_2'], '2018': ['CS_8WK_CLOSE_AVG', 'CS_8WK_YIELD_AVG', 'CUSIP_8WK', 'MATURITY_DATE_8WK', 'ROUND_B1_CLOSE_8WK_2', 'ROUND_B1_YIELD_8WK_2'], '2022': ['CS_17WK_CLOSE_AVG', 'CS_17WK_YIELD_AVG', 'CUSIP_17WK', 'MATURITY_DATE_17WK', 'ROUND_B1_CLOSE_17WK_2', 'ROUND_B1_YIELD_17WK_2'], '2025': ['CS_6WK_CLOSE_AVG', 'CS_6WK_YIELD_AVG', 'CUSIP_6WK', 'DailyTreasuryBillRateDataId', 'MATURITY_DATE_6WK', 'ROUND_B1_CLOSE_6WK_2', 'ROUND_B1_YIELD_6WK_2']}; removed {'2003': ['CS_52WK_CLOSE_AVG', 'CS_52WK_YIELD_AVG', 'CUSIP_52WK', 'MATURITY_DATE_52WK', 'ROUND_B1_CLOSE_52WK_2', 'ROUND_B1_YIELD_52WK_2'], '2023': ['DailyTreasuryBillRateDataId']}
- Validation status: **PASS**

> ROUND_B1_CLOSE_* / CS_*_CLOSE_AVG are DISCOUNT rates on a bank-discount (actual/360) basis. ROUND_B1_YIELD_* / CS_*_YIELD_AVG are COUPON-EQUIVALENT yields. The two are not interchangeable and must not be mixed on one curve.

### Missing values by column

| Column | Type | Total rows | Non-null | Null | Null % |
| --- | --- | ---: | ---: | ---: | ---: |
| `INDEX_DATE` | date | 6,157 | 6,157 | 0 | 0.00 |
| `DailyTreasuryBillRateDataId` | integer | 6,157 | 5,497 | 660 | 10.72 |
| `ROUND_B1_CLOSE_4WK_2` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `ROUND_B1_YIELD_4WK_2` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `ROUND_B1_CLOSE_13WK_2` | numeric | 6,157 | 6,156 | 1 | 0.02 |
| `ROUND_B1_YIELD_13WK_2` | numeric | 6,157 | 6,156 | 1 | 0.02 |
| `ROUND_B1_CLOSE_26WK_2` | numeric | 6,157 | 6,156 | 1 | 0.02 |
| `ROUND_B1_YIELD_26WK_2` | numeric | 6,157 | 6,156 | 1 | 0.02 |
| `BOND_MKT_UNAVAIL_REASON` | string | 6,157 | 1 | 6,156 | 99.98 |
| `MATURITY_DATE_4WK` | date | 6,157 | 6,156 | 1 | 0.02 |
| `MATURITY_DATE_13WK` | date | 6,157 | 6,156 | 1 | 0.02 |
| `MATURITY_DATE_26WK` | date | 6,157 | 6,156 | 1 | 0.02 |
| `CUSIP_4WK` | string | 6,157 | 6,156 | 1 | 0.02 |
| `CUSIP_13WK` | string | 6,157 | 6,156 | 1 | 0.02 |
| `CUSIP_26WK` | string | 6,157 | 6,156 | 1 | 0.02 |
| `QUOTE_DATE` | date | 6,157 | 6,157 | 0 | 0.00 |
| `CF_NEW_DATE` | date | 6,157 | 6,157 | 0 | 0.00 |
| `CS_4WK_CLOSE_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CS_4WK_YIELD_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CS_13WK_CLOSE_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CS_13WK_YIELD_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CS_26WK_CLOSE_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CS_26WK_YIELD_AVG` | numeric | 6,157 | 6,155 | 2 | 0.03 |
| `CF_WEEK` | integer | 6,157 | 6,157 | 0 | 0.00 |
| `CS_52WK_CLOSE_AVG` | numeric | 6,157 | 4,561 | 1,596 | 25.92 |
| `CS_52WK_YIELD_AVG` | numeric | 6,157 | 4,561 | 1,596 | 25.92 |
| `ROUND_B1_CLOSE_52WK_2` | numeric | 6,157 | 4,555 | 1,602 | 26.02 |
| `ROUND_B1_YIELD_52WK_2` | numeric | 6,157 | 4,555 | 1,602 | 26.02 |
| `MATURITY_DATE_52WK` | date | 6,157 | 4,555 | 1,602 | 26.02 |
| `CUSIP_52WK` | string | 6,157 | 4,555 | 1,602 | 26.02 |
| `ROUND_B1_CLOSE_8WK_2` | numeric | 6,157 | 1,954 | 4,203 | 68.26 |
| `ROUND_B1_YIELD_8WK_2` | numeric | 6,157 | 1,954 | 4,203 | 68.26 |
| `MATURITY_DATE_8WK` | date | 6,157 | 1,954 | 4,203 | 68.26 |
| `CUSIP_8WK` | string | 6,157 | 1,954 | 4,203 | 68.26 |
| `CS_8WK_CLOSE_AVG` | numeric | 6,157 | 1,954 | 4,203 | 68.26 |
| `CS_8WK_YIELD_AVG` | numeric | 6,157 | 1,954 | 4,203 | 68.26 |
| `ROUND_B1_CLOSE_17WK_2` | numeric | 6,157 | 952 | 5,205 | 84.54 |
| `ROUND_B1_YIELD_17WK_2` | numeric | 6,157 | 952 | 5,205 | 84.54 |
| `MATURITY_DATE_17WK` | date | 6,157 | 952 | 5,205 | 84.54 |
| `CUSIP_17WK` | string | 6,157 | 952 | 5,205 | 84.54 |
| `CS_17WK_CLOSE_AVG` | numeric | 6,157 | 952 | 5,205 | 84.54 |
| `CS_17WK_YIELD_AVG` | numeric | 6,157 | 952 | 5,205 | 84.54 |
| `ROUND_B1_CLOSE_6WK_2` | numeric | 6,157 | 371 | 5,786 | 93.97 |
| `ROUND_B1_YIELD_6WK_2` | numeric | 6,157 | 371 | 5,786 | 93.97 |
| `MATURITY_DATE_6WK` | date | 6,157 | 371 | 5,786 | 93.97 |
| `CUSIP_6WK` | string | 6,157 | 371 | 5,786 | 93.97 |
| `CS_6WK_CLOSE_AVG` | numeric | 6,157 | 371 | 5,786 | 93.97 |
| `CS_6WK_YIELD_AVG` | numeric | 6,157 | 371 | 5,786 | 93.97 |

### Zero-valued rate observations

| Column | Zeros | First | Last | Suspected placeholder |
| --- | ---: | --- | --- | --- |
| `ROUND_B1_CLOSE_4WK_2` | 64 | 2008-12-10 | 2021-06-03 | no |
| `ROUND_B1_YIELD_4WK_2` | 64 | 2008-12-10 | 2021-06-03 | no |
| `ROUND_B1_CLOSE_13WK_2` | 13 | 2008-12-10 | 2015-10-22 | no |
| `ROUND_B1_YIELD_13WK_2` | 13 | 2008-12-10 | 2015-10-22 | no |
| `CS_4WK_CLOSE_AVG` | 49 | 2011-08-15 | 2021-05-21 | no |
| `CS_4WK_YIELD_AVG` | 49 | 2011-08-15 | 2021-05-21 | no |
| `CS_13WK_CLOSE_AVG` | 8 | 2015-09-22 | 2020-03-25 | no |
| `CS_13WK_YIELD_AVG` | 8 | 2015-09-22 | 2020-03-25 | no |
| `ROUND_B1_CLOSE_8WK_2` | 1 | 2021-05-26 | 2021-05-26 | no |
| `ROUND_B1_YIELD_8WK_2` | 1 | 2021-05-26 | 2021-05-26 | no |


## Daily Treasury Long-Term Rates

- Data key: `daily_treasury_long_term_rate`
- Source: U.S. Department of the Treasury
- Historical period: **2000-01-03 -> 2026-08-11**
- Rows: **19,965**
- Columns: **5**
- Raw files: 27
- Processed file: `long_term_rates.csv`
- Years downloaded: 27 (2000-2026)
- Failed years: none
- Natural key: `QUOTE_DATE, RATE_TYPE` - duplicates: 0
- Exact duplicate records removed: 0
- Missing expected business days: 0
- Schema changes detected: none after the first populated year
- Validation status: **PASS**

> The natural key is (QUOTE_DATE, RATE_TYPE) - a date legitimately carries several rows. The Real_Rate rows inside this nominal feed are Treasury's long-term real rate average; do not merge them with the nominal series.

### Missing values by column

| Column | Type | Total rows | Non-null | Null | Null % |
| --- | --- | ---: | ---: | ---: | ---: |
| `QUOTE_DATE` | date | 19,965 | 19,965 | 0 | 0.00 |
| `Id` | integer | 19,965 | 19,965 | 0 | 0.00 |
| `EXTRAPOLATION_FACTOR` | string | 19,965 | 2,982 | 16,983 | 85.06 |
| `RATE_TYPE` | string | 19,965 | 19,965 | 0 | 0.00 |
| `RATE` | numeric | 19,965 | 19,965 | 0 | 0.00 |

### Zero-valued rate observations

| Column | Zeros | First | Last | Suspected placeholder |
| --- | ---: | --- | --- | --- |
| `RATE` | 15 | 2012-06-05 | 2022-04-01 | no |


## Daily Treasury Par Real Yield Curve Rates

- Data key: `daily_treasury_real_yield_curve`
- Source: U.S. Department of the Treasury
- Historical period: **2003-01-02 -> 2026-08-11**
- Rows: **5,906**
- Columns: **7**
- Raw files: 24
- Processed file: `real_yield_curve.csv`
- Years downloaded: 24 (2003-2026)
- Failed years: none
- Natural key: `NEW_DATE` - duplicates: 0
- Exact duplicate records removed: 0
- Missing expected business days: 0
- Schema changes detected: added {'2004': ['TC_20YEAR'], '2010': ['TC_30YEAR'], '2025': ['DailyTreasuryRealYieldCurveRateDataId']}; removed {'2023': ['DailyTreasuryRealYieldCurveRateDataId']}
- Validation status: **WARNING**

> REAL yields (TIPS-based), not nominal. Negative values are normal and correct - they must never be treated as errors or clipped. The nominal-minus-real difference is a breakeven-inflation calculation and is deliberately not computed here.

### Missing values by column

| Column | Type | Total rows | Non-null | Null | Null % |
| --- | --- | ---: | ---: | ---: | ---: |
| `NEW_DATE` | date | 5,906 | 5,906 | 0 | 0.00 |
| `DailyTreasuryRealYieldCurveRateDataId` | integer | 5,906 | 5,246 | 660 | 11.18 |
| `TC_5YEAR` | numeric | 5,906 | 5,906 | 0 | 0.00 |
| `TC_7YEAR` | numeric | 5,906 | 5,906 | 0 | 0.00 |
| `TC_10YEAR` | numeric | 5,906 | 5,906 | 0 | 0.00 |
| `TC_20YEAR` | numeric | 5,906 | 5,515 | 391 | 6.62 |
| `TC_30YEAR` | numeric | 5,906 | 4,121 | 1,785 | 30.22 |

### Zero-valued rate observations

| Column | Zeros | First | Last | Suspected placeholder |
| --- | ---: | --- | --- | --- |
| `TC_5YEAR` | 15 | 2010-11-16 | 2017-06-06 | no |
| `TC_7YEAR` | 16 | 2010-10-12 | 2022-08-01 | no |
| `TC_10YEAR` | 15 | 2011-08-09 | 2022-04-19 | no |
| `TC_20YEAR` | 12 | 2012-07-12 | 2020-03-31 | no |
| `TC_30YEAR` | 9 | 2020-03-25 | 2022-04-01 | no |


### Warnings

- 2 rate observations flagged for review (out-of-band level or large day-over-day move); none removed

## Daily Treasury Real Long-Term Rates

- Data key: `daily_treasury_real_long_term`
- Source: U.S. Department of the Treasury
- Historical period: **2000-01-03 -> 2026-08-11**
- Rows: **6,655**
- Columns: **2**
- Raw files: 27
- Processed file: `real_long_term_rates.csv`
- Years downloaded: 27 (2000-2026)
- Failed years: none
- Natural key: `QUOTE_DATE` - duplicates: 0
- Exact duplicate records removed: 0
- Missing expected business days: 0
- Schema changes detected: none after the first populated year
- Validation status: **PASS**

> REAL (TIPS) rate. Coverage is interrupted where Treasury suspended publication; missing days are genuinely absent, not zero.

### Missing values by column

| Column | Type | Total rows | Non-null | Null | Null % |
| --- | --- | ---: | ---: | ---: | ---: |
| `QUOTE_DATE` | date | 6,655 | 6,655 | 0 | 0.00 |
| `RATE` | numeric | 6,655 | 6,655 | 0 | 0.00 |

### Zero-valued rate observations

| Column | Zeros | First | Last | Suspected placeholder |
| --- | ---: | --- | --- | --- |
| `RATE` | 15 | 2012-06-05 | 2022-04-01 | no |


## Interpretation notes

- Missing observations are NULL. They were never replaced with zero, a previous day's rate, an interpolation or an average.
- Flagged values are reported for human review only; no statistical outlier was removed.
- Business-day expectations use the U.S. federal holiday calendar, Good Friday and a list of known ad-hoc market closures; remaining gaps are surfaced rather than filled.
- An exact 0 is not automatically a missing value: short Treasury tenors genuinely printed 0.00% in 2008-2015 and 2020-2021. Only columns marked 'suspected placeholder' above should be read as absent rather than zero.
- Rates are quoted in percent as published (3.72 means 3.72%), not in decimals or basis points.
