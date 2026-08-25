"""Tool-selection tests for the expanded market-risk capability set.

Two modes, because they answer different questions and cost different amounts.

**Structural (always runs, offline).** Every question in the catalogue names a
capability that exists, is executable, and dispatches. Every executable
capability has questions covering it. The near-miss pairs that a planner is most
likely to confuse are checked for the discriminating clause that separates them.
Cheap, deterministic, and it catches the whole class of "we advertised something
that cannot run".

**Live (opt-in, `RISK_ROUTING_LIVE=1`).** Drives the real domain expert against
each question and asserts which calculation it actually scheduled. This is the
only thing that proves a description is *discriminating* rather than merely
present, but it costs one model call per question and needs a knowledge base, so
it is not part of the default suite.

The ambiguous rows matter as much as the concrete ones. A question like "run a
stress test" names no scenario, and the correct behaviour is to leave the
calculation unset so the orchestrator asks - not to pick one of nine stress
capabilities and hope.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

from agents.mcp_agent import McpAgent
from backend.workflows.risk_workflows import RiskWorkflows

CATALOG = json.loads(
    (pathlib.Path(__file__).with_name("routing_catalog.json"))
    .read_text(encoding="utf-8"))
QUESTIONS = CATALOG["questions"]
LIVE = os.environ.get("RISK_ROUTING_LIVE") == "1"


class _Calculating:
    """Minimal provider that looks capable, so the catalogue includes risk tools."""

    def call_tool(self, name, arguments=None):
        return {}

    def call_tool_with_meta(self, name, arguments=None):
        return {}, {}


@pytest.fixture(scope="module")
def catalogue():
    return McpAgent(_Calculating()).catalogue()


# --- structural --------------------------------------------------------------


def test_the_catalogue_is_well_formed():
    ids = [q["id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    questions = [q["question"] for q in QUESTIONS]
    assert len(questions) == len(set(questions)), "duplicate question text"
    assert len(QUESTIONS) >= 100, (
        f"{len(QUESTIONS)} questions; the catalogue is meant to be broad enough "
        "that a routing regression shows up somewhere")


@pytest.mark.parametrize("row", QUESTIONS, ids=lambda r: r["id"])
def test_every_expected_capability_is_executable_and_dispatchable(row, catalogue):
    expected = row["expected_capability"]
    if expected is None:
        assert row["ambiguous"] and row["note"], (
            "an ambiguous row must say why it is ambiguous")
        return
    assert expected in catalogue.executable_tools, (
        f"{row['id']} expects {expected!r}, which is not an executable capability")
    assert callable(getattr(RiskWorkflows, expected, None)), (
        f"{expected} is advertised but not dispatchable")


def test_every_executable_capability_has_routing_questions(catalogue):
    """A capability nobody wrote a question for is a capability nobody tested."""
    covered = {q["expected_capability"] for q in QUESTIONS}
    uncovered = sorted(set(catalogue.executable_tools) - covered)
    assert not uncovered, f"no routing question exercises: {uncovered}"


#: The pairs a planner is most likely to confuse, and the clause in the first
#: tool's description that must send it to the second. Each of these is a real
#: near-miss: same domain, same vocabulary, different question.
NEAR_MISSES = [
    ("run_rate_stress", "run_historical_stress", "actually happened"),
    ("run_rate_stress", "run_key_rate_stress", "only one curve point"),
    ("run_rate_stress", "run_reverse_stress", "target LOSS"),
    ("run_stress_matrix", "find_worst_historical_stresses", "worst HISTORICAL"),
    ("run_historical_stress", "find_worst_historical_stresses", "SEARCH history"),
    ("compute_var", "compute_parametric_risk", "parametric"),
    ("compute_var", "compute_monte_carlo_risk", "Monte"),
    ("compute_var", "backtest_var", "ACCURATE"),
    ("run_reverse_stress", "compute_stress_thresholds", "several loss levels"),
    ("evaluate_risk_limits", "find_limit_breach_stress", "BREACH"),
    ("compute_risk_contributions", "compute_stress_contributions", "STRESS loss"),
    ("compute_concentration", "compute_risk_contributions", "contribution"),
    ("compute_dv01", "compute_rate_sensitivities", "duration"),
    ("compute_bond_analytics", "compute_dv01", "per basis point"),
    ("compare_portfolio_risk", "analyze_hypothetical_trade", "proposed trade"),
    ("compute_pnl_attribution", "compute_carry_roll", "expected future carry"),
]


@pytest.mark.parametrize("source,alternative,marker", NEAR_MISSES,
                         ids=lambda v: v if isinstance(v, str) else "")
def test_confusable_capabilities_name_each_other(source, alternative, marker,
                                                 catalogue):
    """The NOT WHEN clause must name the right alternative, in words.

    A description that only says what a tool does leaves the planner to infer
    the boundary. Naming the neighbouring capability, and the phrase that
    distinguishes it, is what turns a guess into a decision.
    """
    spec = next(t for t in catalogue.tools if t.name == source)
    assert alternative in spec.description, (
        f"{source} does not point at {alternative}")
    assert marker.lower() in spec.description.lower(), (
        f"{source} does not carry the distinguishing phrase {marker!r}")


def test_the_frtb_capability_refuses_the_bank_wide_reading(catalogue):
    spec = next(t for t in catalogue.tools if t.name == "compute_frtb_girr")
    assert "NOT a complete bank-wide" in spec.description


def test_rate_volatility_is_distinguished_from_implied_volatility(catalogue):
    spec = next(t for t in catalogue.tools if t.name == "compute_rate_volatility")
    assert "option-implied" in spec.description


# --- live --------------------------------------------------------------------


@pytest.fixture(scope="module")
def expert():
    if not LIVE:
        pytest.skip("set RISK_ROUTING_LIVE=1 to drive the real domain expert")
    from backend.knowledge.knowledge_base import KnowledgeBase
    from agents.domain_expert_agent import DomainExpertAgent
    return DomainExpertAgent(knowledge=KnowledgeBase())


@pytest.fixture(scope="module")
def live_catalogue():
    if not LIVE:
        pytest.skip("set RISK_ROUTING_LIVE=1 to drive the real domain expert")
    from backend.providers.mcp import McpDataProvider
    return McpAgent(McpDataProvider()).catalogue()


@pytest.mark.parametrize("row", QUESTIONS, ids=lambda r: r["id"])
def test_the_domain_expert_schedules_the_expected_capability(row, expert,
                                                             live_catalogue):
    """The real planner, against the real catalogue, on one real question."""
    requirement, _ = expert.derive(
        question=row["question"], task=row["question"],
        catalogue=live_catalogue, requested_fields=None, requested_rows=None)
    chosen = requirement.calculation
    if row["expected_capability"] is None:
        assert chosen is None, (
            f"{row['id']} is ambiguous ({row['note']}) but the planner chose "
            f"{chosen!r} instead of leaving it for the orchestrator to ask")
    else:
        assert chosen == row["expected_capability"], (
            f"{row['id']} {row['question']!r}: expected "
            f"{row['expected_capability']!r}, planner chose {chosen!r}")
