"""The road a stated parameter travels, from the planner's schema to a workflow.

A capability can be routed to perfectly and still be unanswerable. Every stress
capability was: the planner named `run_rate_stress` correctly and returned
`calculation_params: {}`, because `calculation_params` was a closed schema
holding exactly `confidence_level` and `horizon_days` and there was nowhere
legal to put `scenario`. The adapter then asked for the scenario, every time,
for a question that had already named it in so many words.

Routing tests could not see this - the routing was right. Adapter tests could
not see it either - handed a scenario, the adapter worked. It lived in the seam,
so the tests for it live here, and they check the seam in both directions:

* every input an adapter *requires* has somewhere legal to arrive from;
* every property the schema declares is read by some adapter;
* the vocabularies restated in `agents` still match the ones `backend` accepts.

That last one is the price of `agents` sitting below `backend`: the scenario
names cannot be imported without closing a cycle, so they are duplicated, and
this file is what makes the duplication safe.
"""
from __future__ import annotations

import inspect
import pathlib
import re

import mcp_servers.risk.tools_analytics
import pytest

from agents.domain_expert_agent import (
    CRISIS_IDS,
    RISK_MEASURES,
    SCENARIO_NAMES,
    SCHEMA,
    DomainExpertAgent,
)
from agents.contracts import Requirement, TemporalScope
from agents.mcp_agent import McpAgent
from agents.redaction import humanise
from backend.workflows.risk_workflows import (
    CRISIS_WINDOWS,
    CURVATURE_SHAPES,
    TEMPLATE_SCENARIOS,
    RiskWorkflows,
)

#: Filled by `McpAgent._calculate` from what it already knows, so a planner is
#: never asked to state them and the schema deliberately has no slot for them.
INJECTED = frozenset({"portfolio_id", "scenario_id", "trading_days",
                      "curve_date", "start_date", "end_date", "lookback_days"})

#: Read by an adapter but withheld from the planner on purpose. Each is a
#: choice a model should not be making: a seed the model invents would make an
#: arbitrary draw look deliberate, `key_rates` is an internal presentation
#: toggle, and the two collection parameters have named-scenario capabilities
#: that cover the same ground with a vocabulary instead of free-form numbers.
WITHHELD = {
    "random_seed": "a model-chosen seed makes an arbitrary draw look chosen",
    "key_rates": "an internal breakdown toggle, not a question the user asks",
    "observations": "overlaps `trading_days`, which is injected from `rows`",
    "shocks_bp_by_tenor_months": "`run_rate_stress` names the shape instead",
    "tenors_months": "a refinement the adapter already defaults sensibly",
}

PARAMS_SCHEMA = SCHEMA["properties"]["calculation_params"]
DECLARED = PARAMS_SCHEMA["properties"]


class _Provider:
    """Enough of a provider to build the catalogue; it is never called."""

    def call_tool(self, name, arguments=None):
        return {}

    def call_tool_with_meta(self, name, arguments=None):
        return {}, {}


@pytest.fixture(scope="module")
def catalogue():
    return McpAgent(_Provider()).catalogue()


def _parameters(capability: str) -> set[str]:
    method = getattr(RiskWorkflows, capability, None)
    if method is None:
        return set()
    return set(inspect.signature(method).parameters) - {"self"}


# --------------------------------------------------------------------------
# The seam, in both directions.
# --------------------------------------------------------------------------

def test_every_adapter_input_can_be_stated_or_is_deliberately_withheld(catalogue):
    """No capability may read an input the planner has no way to supply.

    This is the defect itself, generalised. A parameter that is neither
    declared, injected, nor listed in WITHHELD is one a user can ask for in
    words and the system will still say it was not given.
    """
    unreachable = {}
    for capability in catalogue.executable_tools:
        for name in _parameters(capability) - INJECTED - set(DECLARED):
            if name not in WITHHELD:
                unreachable.setdefault(name, []).append(capability)
    assert not unreachable, (
        "adapter inputs with no legal home in `calculation_params`: "
        f"{unreachable}. Declare each in the schema and in "
        "`_calculation_params`, or record in WITHHELD why a planner must not "
        "state it.")


def test_no_schema_property_is_read_by_nothing(catalogue):
    """The other direction: a slot nothing reads teaches the planner a fiction.

    A model that fills `severity_bp` believes it changed the answer. If no
    capability takes it, it did not, and nothing says so.
    """
    read = set().union(*(_parameters(c) for c in catalogue.executable_tools))
    assert not set(DECLARED) - read - INJECTED, (
        f"declared but read by no capability: {sorted(set(DECLARED) - read)}")


@pytest.mark.parametrize(
    "capability,supplied,missing",
    [("run_rate_stress", {}, "scenario"),
     ("run_key_rate_stress", {}, "tenor_months"),
     ("run_key_rate_stress", {"tenor_months": 120.0}, "shock_bp"),
     ("compute_stress_contributions", {}, "scenario"),
     ("run_reverse_stress", {}, "target_loss"),
     ("find_limit_breach_stress", {}, "limit_amount"),
     ("analyze_hypothetical_trade", {}, "tenor_months"),
     ("analyze_hypothetical_trade", {"tenor_months": 120.0}, "notional"),
     ("evaluate_risk_limits", {}, "dv01_limit")],
    ids=lambda v: v if isinstance(v, str) else "")
def test_a_required_input_is_declared_in_the_schema(capability, supplied, missing):
    """A guard that asks for an input the planner cannot state is a dead end.

    Each of these capabilities refuses to run without the named input - that is
    correct, and `test_risk_workflow_adapters.py` proves it. This asserts the
    other half: that the input has a declared home, so the refusal is a
    question the user can answer rather than one nobody can.
    """
    assert missing in DECLARED, (
        f"{capability} requires `{missing}` and the planner has no field to "
        f"state it in; the guard can never be satisfied")


def test_every_capability_that_takes_parameters_documents_them(catalogue):
    """The planner reads descriptions, so a parameter unnamed there is unused.

    The schema makes a parameter legal; the PARAMS clause is what tells the
    planner it exists. Both are needed - the closed schema was only half the
    defect, and a legal field nobody mentions stays empty.
    """
    undocumented = []
    for spec in catalogue.tools:
        if not spec.executable:
            continue
        statable = _parameters(spec.name) & set(DECLARED)
        if statable and "PARAMS:" not in spec.description:
            undocumented.append((spec.name, sorted(statable)))
    assert not undocumented, (
        f"capabilities that read stateable parameters but never name them in a "
        f"PARAMS clause: {undocumented}")


def test_a_params_clause_names_only_parameters_that_capability_reads(catalogue):
    """A clause naming a neighbour's parameter teaches a plan that gets filtered.

    `_calculate` drops what the signature does not name, silently and
    correctly. The loss is upstream: the planner spent a field on it and did
    not state the one that would have worked.
    """
    wrong = {}
    for spec in catalogue.tools:
        if "PARAMS:" not in spec.description:
            continue
        clause = spec.description[spec.description.index("PARAMS:"):]
        reads = _parameters(spec.name) | INJECTED
        words = set(re.findall(r"[a-z_]+", clause))
        named = {word for word in DECLARED if word in words}
        if named - reads:
            wrong[spec.name] = sorted(named - reads)
    assert not wrong, f"PARAMS clauses naming parameters the capability ignores: {wrong}"


def test_a_clause_never_asks_for_a_field_the_schema_would_reject(catalogue):
    """`calculation_params.x` must be an `x` the closed schema declares.

    The injected fields are the trap. `start_date` is a real input to two
    capabilities, so a clause naming it looks right - but it arrives from
    `temporal`, and a plan that puts it in `calculation_params` fails
    validation on the whole object and costs a corrective retry. Anything
    written after `calculation_params.` has to be a declared property.
    """
    asked = {}
    for spec in catalogue.tools:
        for name in re.findall(r"calculation_params\.([a-z_]+)", spec.description):
            if name not in DECLARED:
                asked.setdefault(spec.name, []).append(name)
    assert not asked, (
        f"PARAMS clauses asking for undeclared fields: {asked}. A field filled "
        f"from `temporal` must be named as `temporal.<field>`.")


# --------------------------------------------------------------------------
# The injected inputs.
# --------------------------------------------------------------------------

class _Recorder:
    """Stands in for `RiskWorkflows`, recording what `_calculate` passes."""

    def __init__(self):
        self.kwargs = None

    def compute_pnl_attribution(self, portfolio_id, start_date=None,
                                end_date=None, lookback_days=None,
                                curve_date=None):
        self.kwargs = dict(portfolio_id=portfolio_id, start_date=start_date,
                           end_date=end_date, lookback_days=lookback_days,
                           curve_date=curve_date)
        return {}

    def compute_concentration(self, portfolio_id, top_n=5):
        self.kwargs = dict(portfolio_id=portfolio_id, top_n=top_n)
        return {}


def _dispatch(tool, requirement, recorder):
    agent = McpAgent(_Provider())
    agent._risk_workflows = recorder
    agent._first_portfolio = lambda _: "TREASURY_DEMO_001"
    return agent._calculate(tool, requirement)


def test_a_named_period_reaches_the_capability_that_reads_it():
    """`temporal` is where a period is recorded; the capability reads dates.

    Without this the planner would have to state the same window twice, once
    per destination, and a model that states it once leaves the other empty.
    """
    requirement = Requirement(
        task="attribute P&L", answerable=True, calculation="compute_pnl_attribution",
        temporal=TemporalScope(as_of_date=None, start_date=None,
                               end_date=None, lookback_days=60))
    recorder = _Recorder()
    _dispatch("compute_pnl_attribution", requirement, recorder)
    assert recorder.kwargs["lookback_days"] == 60


def test_a_stated_parameter_still_wins_over_an_injected_one():
    """Injection fills a gap; it must never overwrite what the plan stated."""
    requirement = Requirement(
        task="rank", answerable=True, calculation="compute_concentration",
        calculation_params={"top_n": 3})
    recorder = _Recorder()
    _dispatch("compute_concentration", requirement, recorder)
    assert recorder.kwargs["top_n"] == 3


def test_an_unread_period_is_not_forced_on_a_capability():
    """`compute_concentration` has no date parameters; passing one would raise."""
    requirement = Requirement(
        task="rank", answerable=True, calculation="compute_concentration",
        temporal=TemporalScope(as_of_date=None, start_date="2020-01-01",
                               end_date="2020-06-01", lookback_days=250))
    recorder = _Recorder()
    result = _dispatch("compute_concentration", requirement, recorder)
    assert "error" not in result, result
    assert set(recorder.kwargs) == {"portfolio_id", "top_n"}


# --------------------------------------------------------------------------
# The duplicated vocabularies.
# --------------------------------------------------------------------------

def test_scenario_names_match_what_the_adapter_dispatches_on():
    """`agents` restates this list; `backend` is where it is true."""
    accepted = ({"parallel", "parallel_up", "parallel_down", "twist"}
                | {name.lower() for name in TEMPLATE_SCENARIOS}
                | {name.lower() for name in CURVATURE_SHAPES})
    assert set(SCENARIO_NAMES) == accepted, (
        "the planner's scenario vocabulary has drifted from the one "
        "`run_rate_stress` accepts; a name in one and not the other is either "
        "an unreachable scenario or a plan that fails at the last step")


def test_crisis_ids_match_the_dated_windows():
    assert set(CRISIS_IDS) == set(CRISIS_WINDOWS)


def test_every_offered_scenario_is_actually_dispatchable():
    """Reachability, not just spelling: each name must reach an engine tool."""
    source = inspect.getsource(RiskWorkflows.run_rate_stress)
    for name in SCENARIO_NAMES:
        assert name in source or name.upper() in source or name in {
            key.lower() for key in TEMPLATE_SCENARIOS} | set(CURVATURE_SHAPES), name


def test_risk_measures_are_the_ones_the_engine_accepts():
    """The adapter passes `risk_measure` through, so the engine is the authority.

    Asserting against the adapter would only prove the string travels. The tool
    annotates `Literal["var", "es"]`, and that is what actually constrains it.
    Read from the syntax tree because the tools are nested inside their
    registration function and are not module attributes.
    """
    import ast

    source = pathlib.Path(
        mcp_servers.risk.tools_analytics.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.FunctionDef)
                and node.name == "compute_risk_contributions_tool"):
            annotation = next(a.annotation for a in node.args.args
                              if a.arg == "risk_measure")
            declared = {literal.value for literal in annotation.slice.elts}
            break
    else:
        raise AssertionError("compute_risk_contributions_tool not found")
    assert set(RISK_MEASURES) == declared, (
        f"the planner offers {sorted(RISK_MEASURES)} and the engine accepts "
        f"{sorted(declared)}")


# --------------------------------------------------------------------------
# The rebuilder: validated, never trusted.
# --------------------------------------------------------------------------

def test_the_rebuilder_and_the_schema_agree_on_the_field_list():
    """A field in one and not the other is a field that silently disappears.

    Declared but not rebuilt is the worse half: the model states it, the
    schema accepts it, and it is dropped without a word between them.
    """
    handled = (set(DomainExpertAgent._NUMBER_RULES)
               | set(DomainExpertAgent._INTEGER_RULES)
               | set(DomainExpertAgent._ENUM_RULES)
               | {"target_losses", "other_portfolio_id"})
    assert handled == set(DECLARED), (
        f"schema only: {sorted(set(DECLARED) - handled)}; "
        f"rebuilder only: {sorted(handled - set(DECLARED))}")


def test_the_schema_stays_closed():
    """An open object would have taken `scenarioo` as readily as `scenario`.

    The fix for a closed schema missing a field is the field. Opening it moves
    the failure from a validation error to a parameter that vanishes at
    `_calculate`, which is much further from the cause.
    """
    assert PARAMS_SCHEMA["additionalProperties"] is False


def test_required_stays_small_and_every_property_is_nullable():
    """Two required, because a question states two or three of these, never all.

    This file already records eighteen required properties failing on glm-5.2.
    Nullability is what lets the other eighteen stay optional without the
    planner having to invent a value it was never given.
    """
    assert PARAMS_SCHEMA["required"] == ["confidence_level", "horizon_days"]
    for name, spec in DECLARED.items():
        nullable = ("null" in (spec.get("type") or [])
                    or None in (spec.get("enum") or []))
        assert nullable, f"{name} cannot express 'not stated'"


@pytest.mark.parametrize(
    "raw,expected",
    [({"scenario": "BEAR_STEEPENER"}, {"scenario": "bear_steepener"}),
     ({"scenario": "  Twist "}, {"scenario": "twist"}),
     ({"crisis_id": "2020_covid_shock"}, {"crisis_id": "2020_COVID_SHOCK"}),
     ({"risk_measure": "ES"}, {"risk_measure": "es"})],
    ids=["template", "whitespace", "crisis", "measure"])
def test_a_stated_word_is_canonicalised_not_rejected(raw, expected):
    """Case is not a judgement about risk; a range is."""
    warnings: list[str] = []
    assert DomainExpertAgent._calculation_params(raw, warnings) == expected
    assert not warnings


@pytest.mark.parametrize(
    "raw,dropped",
    [({"scenario": "sideways"}, "scenario"),
     ({"crisis_id": "2019_NOTHING_HAPPENED"}, "crisis_id"),
     ({"risk_measure": "median"}, "risk_measure"),
     ({"confidence_level": 99}, "confidence_level"),
     ({"horizon_days": 2.5}, "horizon_days"),
     ({"top_n": 0}, "top_n"),
     ({"target_loss": -2_000_000}, "target_loss"),
     ({"amber_utilisation_percent": 150}, "amber_utilisation_percent"),
     ({"shock_bp": 20_000}, "shock_bp"),
     ({"scenario_count": 3}, "scenario_count"),
     ({"target_losses": [1_000_000, -5]}, "target_losses")],
    ids=lambda v: v if isinstance(v, str) else "")
def test_a_value_outside_its_meaning_is_dropped_and_reported(raw, dropped):
    """Dropped, never clamped, and never silently.

    Rewriting 99 to 0.99 is a guess about the number the whole figure is
    defined by. Dropping it lets a documented default stand - or, where there
    is none, makes the adapter ask, which is the honest end of the path.
    """
    warnings: list[str] = []
    assert dropped not in DomainExpertAgent._calculation_params(raw, warnings)

    readable = humanise(dropped)
    assert any(readable.lower() in warning.lower() for warning in warnings), warnings
    if readable != dropped:
        # The warning is written into the material the orchestrator composes
        # the reply from, so the identifier must not survive into it.
        assert not any(dropped in warning for warning in warnings), warnings


def test_a_bad_entry_drops_the_whole_list_not_just_that_entry():
    """A threshold table quietly missing a row reads as complete."""
    warnings: list[str] = []
    out = DomainExpertAgent._calculation_params(
        {"target_losses": [1_000_000, 0, 3_000_000]}, warnings)
    assert "target_losses" not in out and warnings


def test_nothing_is_invented_from_an_empty_plan():
    warnings: list[str] = []
    assert DomainExpertAgent._calculation_params({}, warnings) == {}
    assert DomainExpertAgent._calculation_params(None, warnings) == {}
    assert not warnings


def test_booleans_are_not_numbers():
    """`True` is an `int` in Python, and `top_n=True` would rank one entry."""
    warnings: list[str] = []
    assert DomainExpertAgent._calculation_params(
        {"top_n": True, "notional": False}, warnings) == {}
