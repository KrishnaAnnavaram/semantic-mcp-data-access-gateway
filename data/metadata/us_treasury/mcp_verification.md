# MCP server verification

- Result: **PASS** (48/48 checks passed)
- Generated (UTC): 2026-08-13T14:08:07+00:00

| Check | Expected | Actual | Result |
| --- | --- | --- | --- |
| `tools_advertised` | True | True | PASS |
| `all_have_output_schema` | 0 | 0 | PASS |
| `no_undeclared_writers` | set() | set() | PASS |
| `database_tools_all_read_only` | 0 | 0 | PASS |
| `none_destructive` | 0 | 0 | PASS |
| `all_described` | 0 | 0 | PASS |
| `tool_order_deterministic` | ['list_datasets', 'list_series', 'search_series', 'get_series_coverage', 'get_curve', 'get_rate_history', 'get_curve_history_matrix', 'explain_number', 'list_portfolios', 'get_portfolio', 'list_scenarios', 'get_scenario', 'export_curve_csv', 'brief_dataset_caveat'] | ['list_datasets', 'list_series', 'search_series', 'get_series_coverage', 'get_curve', 'get_rate_history', 'get_curve_history_matrix', 'explain_number', 'list_portfolios', 'get_portfolio', 'list_scenarios', 'get_scenario', 'export_curve_csv', 'brief_dataset_caveat'] | PASS |
| `no_sql_escape_hatch` | [] | [] | PASS |
| `no_sql_fragment_parameters` | [] | [] | PASS |
| `curve_returns_points` | True | True | PASS |
| `envelope_complete:get_curve` | 0 | 0 | PASS |
| `no_placeholder_series:get_curve` | 0 | 0 | PASS |
| `curve_has_provenance` | True | True | PASS |
| `curve_tenors_unique` | 14 | 14 | PASS |
| `curve_tenors_ordered` | True | True | PASS |
| `envelope_complete:get_rate_history` | 0 | 0 | PASS |
| `no_placeholder_series:get_rate_history` | 0 | 0 | PASS |
| `history_paginates` | True | True | PASS |
| `cursor_bound_to_query` | True | True | PASS |
| `cursor_tamper_evident` | True | True | PASS |
| `bulk_matrix_in_meta` | True | True | PASS |
| `bulk_rates_absent_from_model_view` | False | False | PASS |
| `bulk_matrix_shape` | 1000 | 1000 | PASS |
| `synthetic_labelled:get_portfolio` | 0 | 0 | PASS |
| `portfolio_classified_synthetic` | SYNTHETIC_DEMO | SYNTHETIC_DEMO | PASS |
| `explain_number_has_sha256` | True | True | PASS |
| `holiday_error_code` | DATE_NO_DATA | DATE_NO_DATA | PASS |
| `holiday_error_offers_dates` | True | True | PASS |
| `unknown_series_error_code` | UNKNOWN_SERIES | UNKNOWN_SERIES | PASS |
| `unknown_series_suggests_alternatives` | True | True | PASS |
| `missing_history_refuses_by_default` | MISSING_OBSERVATIONS | MISSING_OBSERVATIONS | PASS |
| `reversed_range_rejected` | INVALID_DATE_RANGE | INVALID_DATE_RANGE | PASS |
| `sql_injection_rejected` | UNKNOWN_SERIES | UNKNOWN_SERIES | PASS |
| `catalogue_resources_present` | True | True | PASS |
| `caveat_resource_warns_on_quote_basis` | True | True | PASS |
| `prompts_present` | True | True | PASS |
| `modern_protocol_negotiated` | 2026-07-28 | 2026-07-28 | PASS |
| `ambiguous_query_elicits` | elicited | elicited | PASS |
| `elicited_answer_filters_matches` | ['TC_30YEAR'] | ['TC_30YEAR'] | PASS |
| `unambiguous_query_does_not_elicit` | unambiguous | unambiguous | PASS |
| `export_uses_client_root` | True | True | PASS |
| `export_reports_roots_offered` | True | True | PASS |
| `export_refuses_root_escape` | None | None | PASS |
| `export_escape_states_reason` | True | True | PASS |
| `briefing_names_drafting_model` | True | True | PASS |
| `briefing_carries_verbatim_caveat` | True | True | PASS |
| `root_containment_refuses_escape` | [] | [] | PASS |
| `root_containment_allows_bare_name` | True | True | PASS |
