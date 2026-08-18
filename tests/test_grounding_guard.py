"""The guard that makes "no hardcoded thresholds" checkable rather than promised.

It must reject a recalled number and accept an honest citation. Both halves
matter: a guard that rejects honest quotes pushes the agent toward inventing
numbers, which is the failure the whole design exists to prevent.
"""

from __future__ import annotations

import pytest

from agents.domain_expert_agent import quote_is_grounded

# Verbatim from knowledge/market_risk/var.md, markdown emphasis included.
CORPUS = (
    "## Observation window\n\n"
    "Historical simulation reads a fixed lookback window of **250 trading days** "
    "of daily observations. Shorter windows understate tail risk.\n"
)


def test_a_quote_reproducing_the_markdown_is_grounded():
    assert quote_is_grounded(
        "Historical simulation reads a fixed lookback window of **250 trading "
        "days** of daily observations.", CORPUS)


def test_the_same_sentence_without_markdown_is_also_grounded():
    """The regression. A faithful plain-text citation was being discarded.

    Observed on glm-5.2: the correct sentence, the correct number, rejected
    because the model did not reproduce two asterisks.
    """
    assert quote_is_grounded(
        "Historical simulation reads a fixed lookback window of 250 trading "
        "days of daily observations.", CORPUS)


@pytest.mark.parametrize("paraphrase", [
    "Historical simulation uses a 250-day lookback window.",
    "The window is 250 trading days.",
    "Historical VaR reads 500 trading days of daily observations.",
    "Simulation historically reads a window of 250 days, fixed.",
])
def test_a_paraphrase_is_still_rejected(paraphrase):
    """Stripping emphasis must not have loosened the check."""
    assert not quote_is_grounded(paraphrase, CORPUS)


def test_a_number_recalled_from_training_is_rejected():
    """The case the guard exists for: a plausible sentence absent from the source."""
    assert not quote_is_grounded(
        "Basel requires a 250-day historical window for VaR backtesting.", CORPUS)


@pytest.mark.parametrize("empty", ["", None, "   "])
def test_an_absent_quote_is_never_grounded(empty):
    assert not quote_is_grounded(empty, CORPUS)


def test_a_fragment_too_short_to_be_evidence_is_rejected():
    assert not quote_is_grounded("250 days", CORPUS)


def test_whitespace_and_wrapping_do_not_break_a_fair_quote():
    """Chunks wrap mid-sentence; that is not a paraphrase."""
    assert quote_is_grounded(
        "Historical simulation reads a fixed\n   lookback window of 250 trading "
        "days\nof daily observations.", CORPUS)
