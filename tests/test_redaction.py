"""Internal identifiers must never reach a user.

The observed defect: a scope refusal that named seven functions from this
repository. Every fact in it was true; it was still the wrong sentence.
"""

from __future__ import annotations

import re

import pytest

from agents.redaction import humanise, scrub_identifiers

# The live catalogue, as the pipeline supplies it.
TOOLS = [
    "list_datasets", "list_series", "search_series", "get_series_coverage",
    "get_curve", "get_rate_history", "get_curve_history_matrix", "explain_number",
    "list_portfolios", "get_portfolio", "list_scenarios", "get_scenario",
    "export_curve_csv", "brief_dataset_caveat", "price_portfolio_tool",
    "compute_dv01_tool", "compute_key_rate_dv01_tool", "run_stress_tool",
    "compute_historical_risk_tool", "compute_var", "compute_dv01",
    "price_portfolio", "run_stress", "get_yield_curve", "get_curve_slope",
]


@pytest.mark.parametrize("name,expected", [
    ("compute_dv01", "DV01"),
    ("compute_var", "VaR"),
    ("get_rate_history", "rate history"),
    ("get_curve_slope", "curve slope"),
    ("compute_key_rate_dv01_tool", "key rate DV01"),
    ("export_curve_csv", "curve CSV"),
    ("price_portfolio", "portfolio valuation"),
    ("run_stress", "a stress scenario"),
])
def test_identifiers_become_readable_phrases(name, expected):
    assert humanise(name) == expected


def test_the_observed_leak_is_repaired():
    leaked = ("I cannot compute CVA without counterparty data, but I can still run "
              "compute_dv01, compute_var, run_stress and price_portfolio on the "
              "SYNTHETIC_DEMO book.")
    cleaned = scrub_identifiers(leaked, TOOLS)
    assert not _bare_names(cleaned)
    # Substitution, not deletion: the sentence still reads.
    assert "DV01" in cleaned and "VaR" in cleaned
    assert "SYNTHETIC_DEMO" in cleaned      # a data label, not an identifier
    assert len(cleaned.split()) > 15


def test_a_backticked_identifier_is_left_alone():
    """The trace and data-plan panels quote identifiers on purpose."""
    text = "the `compute_var` tool returned 250 rows"
    assert scrub_identifiers(text, TOOLS) == text


def test_longest_name_wins():
    """`compute_key_rate_dv01_tool` must not be half-eaten by a shorter prefix."""
    cleaned = scrub_identifiers("ran compute_key_rate_dv01_tool today", TOOLS)
    assert "key rate DV01" in cleaned
    assert "_tool" not in cleaned


def test_ordinary_prose_is_untouched():
    prose = ("The 2s10s slope is +48.0 bp as of 2026-08-11, quoted on a "
             "par_coupon_semiannual basis.")
    assert scrub_identifiers(prose, TOOLS) == prose


@pytest.mark.parametrize("empty", ["", None])
def test_empty_input_is_safe(empty):
    assert scrub_identifiers(empty, TOOLS) == ""


def test_every_catalogue_name_has_a_readable_form():
    for name in TOOLS:
        phrase = humanise(name)
        assert phrase and phrase != name, name
        assert "_" not in phrase, name


def _bare_names(text: str) -> list[str]:
    """The evaluator's own rule, so the two cannot disagree about a leak."""
    return [n for n in TOOLS
            if re.search(rf"(?<![\w`]){re.escape(n)}(?![\w`])", text)]
