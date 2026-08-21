"""Does the Domain Expert actually change its mind when the MCP Agent speaks?

That is the whole question. A negotiation loop that runs is not evidence of
collaboration — the previous implementation had one, ran it, and reached
agreement on round one every single time because the expert had already
normalised its plan before the data layer ever saw it. The loop was real and
the conversation was theatre.

So these tests assert *state change*, never message count. A single round in
which the expert genuinely dropped a requirement on evidence is worth more than
five in which it restated itself, and the assertions are written that way:

    initial hypothesis  ≠  final requirement,
    and the difference is traceable to something the MCP agent said.

Deterministic and offline. The two specialists are scripted so the *negotiation
rules* are under test rather than a model's mood; the transport, the executors,
the guardrails and the ledger are all real.
"""

from __future__ import annotations

import pytest

from agents.contracts import (
    KnowledgeChunk,
    Requirement,
    ResultValidation,
    ServeResponse,
    TemporalScope,
    ToolCatalogue,
    ToolSpec,
)
from agents.planning import MAX_NEGOTIATION_ROUNDS, DataPlanner

CHUNK = KnowledgeChunk("market_risk", "var.md", "Observation window",
                       "Historical simulation reads a fixed lookback window of "
                       "250 trading days.", 0.1)

CATALOGUE = ToolCatalogue(
    tools=[ToolSpec("get_rate_history", "history", "data", executable=False),
           ToolSpec("compute_var", "VaR and ES", "risk", executable=True)],
    fields=["observation_date", "rate_percent", "quote_basis", "tenor"],
    tenors=["y2", "y10"], can_calculate=True)


def hypothesis(**kw) -> Requirement:
    """The expert's opening move: theory, including inputs it may not get."""
    base = dict(
        task="10-day 99% historical VaR on the demo book", answerable=True,
        fields=["observation_date", "rate_percent", "quote_basis"],
        candidate_fields=["observation_date", "rate_percent", "quote_basis",
                          "cusip", "issuer_name", "settlement_date"],
        rows=250, row_quote="250 trading days", grounded=True,
        tenors=["y2", "y10"], calculation="compute_var",
        open_questions=["Are cusip, issuer_name and settlement_date available?",
                        "Does the VaR tool need them?"],
        is_hypothesis=True, decision=None, citations=[CHUNK.as_dict()])
    base.update(kw)
    return Requirement(**base)


class ScriptedDataLayer:
    """An MCP agent with a fixed opinion, so the *rules* are what is tested."""

    def __init__(self, *assessments: ServeResponse) -> None:
        self._assessments = list(assessments)
        self.calls = 0
        self.phases: list[tuple[int, str]] = []

    def catalogue(self) -> ToolCatalogue:
        return CATALOGUE

    def assess(self, requirement, catalogue) -> ServeResponse:
        index = min(self.calls, len(self._assessments) - 1)
        self.calls += 1
        return self._assessments[index]

    def set_phase(self, round_: int, phase: str) -> None:
        self.phases.append((round_, phase))


class ScriptedExpert:
    """A domain expert whose revisions are written down, not improvised."""

    def __init__(self, opening: Requirement, *revisions: Requirement) -> None:
        self._opening = opening
        self._revisions = list(revisions)
        self.saw: list[ServeResponse] = []

    def derive(self, question, task, catalogue, fields, rows, **kw):
        return self._opening, [CHUNK]

    def revise(self, question, task, catalogue, proposal, assessment, chunks,
               rows, fields=None):
        self.saw.append(assessment)
        index = min(len(self.saw) - 1, len(self._revisions) - 1)
        return self._revisions[index]


EVIDENCE = ServeResponse(
    feasible=True,
    available_fields=["observation_date", "rate_percent", "quote_basis"],
    unsupported_fields=["cusip", "issuer_name", "settlement_date"],
    unnecessary_fields=["cusip", "issuer_name", "settlement_date"],
    available_tools=["compute_var"],
    constraints=["history caps at 251 rows for this selection"],
    answered_questions=["compute_var reads only the curve history"],
    counter_proposal="Run compute_var on the nominal curve; the instrument "
                     "identifiers are neither held nor read by it.")


# --- the central claim ------------------------------------------------------


def test_the_expert_reassesses_on_the_data_layers_evidence():
    """The defect this whole change exists to fix, asserted as state change."""
    opening = hypothesis()
    agreed = hypothesis(
        candidate_fields=opening.candidate_fields,
        open_questions=[], is_hypothesis=False, decision="AGREED")
    expert = ScriptedExpert(opening, agreed)
    planner = DataPlanner(expert, ScriptedDataLayer(EVIDENCE))

    plan = planner.plan("…", "10-day 99% VaR")

    # It saw the evidence, rather than being handed an already-servable plan.
    assert expert.saw, "the expert was never shown a capability assessment"
    assert expert.saw[0].unnecessary_fields == [
        "cusip", "issuer_name", "settlement_date"]

    # And the plan genuinely moved.
    assert plan.negotiation.decision == "AGREED"
    assert plan.requirement.is_hypothesis is False
    assert not plan.requirement.open_questions
    changes = [t.payload.get("changes") for t in plan.negotiation.turns
               if t.speaker == "domain_expert" and t.round > 0]
    assert changes and changes[0], "no change was recorded from the revision"
    assert any("open question" in c or "hypothesis" in c for c in changes[0])


def test_the_hypothesis_keeps_inputs_the_data_layer_may_not_have():
    """If the expert pre-drops them, the MCP agent has nothing to assess."""
    opening = hypothesis()
    assert "cusip" in opening.candidate_fields
    assert opening.is_hypothesis is True
    assert opening.decision is None
    assert opening.open_questions


def test_the_conversation_is_labelled_so_it_can_be_read():
    expert = ScriptedExpert(hypothesis(),
                            hypothesis(open_questions=[], is_hypothesis=False,
                                       decision="AGREED"))
    layer = ScriptedDataLayer(EVIDENCE)
    plan = DataPlanner(expert, layer).plan("…", "VaR")

    phases = [t.phase for t in plan.negotiation.turns]
    assert phases[0] == "INITIAL_HYPOTHESIS"
    assert "CAPABILITY_ASSESSMENT" in phases
    assert phases[-1] == "FINAL_DECISION"
    assert (1, "CAPABILITY_ASSESSMENT") in layer.phases


# --- bounded, in both directions --------------------------------------------


def test_agreement_reached_early_stops_the_conversation():
    """One good assessment is often enough. Length is not the goal."""
    expert = ScriptedExpert(hypothesis(),
                            hypothesis(open_questions=[], is_hypothesis=False,
                                       decision="AGREED"))
    layer = ScriptedDataLayer(EVIDENCE)
    plan = DataPlanner(expert, layer).plan("…", "VaR")

    assert plan.negotiation.rounds_used == 1
    assert layer.calls == 1, "it kept talking after agreeing"


def test_an_unresolved_question_earns_another_round():
    """Still asking means still thinking; the data layer gets another turn."""
    still_asking = hypothesis(open_questions=["what is the coverage?"])
    settled = hypothesis(open_questions=[], is_hypothesis=False, decision="AGREED")
    expert = ScriptedExpert(hypothesis(), still_asking, settled)
    layer = ScriptedDataLayer(EVIDENCE)

    plan = DataPlanner(expert, layer).plan("…", "VaR")

    assert plan.negotiation.rounds_used == 2
    assert layer.calls == 2
    assert plan.negotiation.decision == "AGREED"


def test_a_negotiation_that_never_settles_ends_as_cannot_reach_agreement():
    never = hypothesis(open_questions=["still unresolved"])
    expert = ScriptedExpert(hypothesis(), never)
    layer = ScriptedDataLayer(EVIDENCE)

    plan = DataPlanner(expert, layer).plan("…", "VaR")

    assert plan.negotiation.rounds_used == MAX_NEGOTIATION_ROUNDS
    assert plan.negotiation.decision == "CANNOT_REACH_AGREEMENT"
    assert plan.negotiation.converged is False
    assert "No agreement" in plan.negotiation.outcome


@pytest.mark.parametrize("decision", ["NEEDS_USER_INPUT", "UNSUPPORTED"])
def test_the_expert_can_stop_for_reasons_other_than_agreement(decision):
    committed = hypothesis(open_questions=["nominal or real?"],
                           is_hypothesis=False, decision=decision)
    plan = DataPlanner(ScriptedExpert(hypothesis(), committed),
                       ScriptedDataLayer(EVIDENCE)).plan("…", "VaR")

    assert plan.negotiation.decision == decision
    assert plan.negotiation.converged is False
    assert plan.negotiation.rounds_used == 1


def test_an_unanswerable_task_never_opens_a_negotiation():
    blocked = hypothesis(answerable=False,
                         unanswerable_reason="no counterparty data exists")
    layer = ScriptedDataLayer(EVIDENCE)
    plan = DataPlanner(ScriptedExpert(blocked), layer).plan("…", "CVA")

    assert plan.negotiation.held is False
    assert plan.negotiation.decision == "UNSUPPORTED"
    assert layer.calls == 0, "it argued about a task it had already declined"


def test_a_failed_reasoning_step_is_not_reported_as_unanswerable():
    """The two look identical downstream and mean opposite things.

    A structured call that comes back unusable tells you nothing whatsoever
    about the user's data. Reporting it as "this cannot be answered from the
    available data" is a confident claim the system has no grounds for — the
    same error as writing a missing observation as zero — and it sends the user
    to check their data instead of asking again.
    """
    from agents.domain_expert_agent import DomainExpertAgent

    blocked = DomainExpertAgent._blocked("VaR", "no structured requirement",
                                         blocked_by="model")
    layer = ScriptedDataLayer(EVIDENCE)
    plan = DataPlanner(ScriptedExpert(blocked), layer).plan("…", "VaR")

    assert plan.requirement.blocked_by == "model"
    assert layer.calls == 0
    assert "reasoning step failed" in plan.negotiation.outcome

    # And the data layer is not implicated in the outcome text.
    assert "available data" not in plan.negotiation.outcome


def test_the_two_kinds_of_block_produce_different_sentences():
    from agents.domain_expert_agent import DomainExpertAgent

    layer = ScriptedDataLayer(EVIDENCE)
    outcomes = {}
    for kind in ("model", "data"):
        blocked = DomainExpertAgent._blocked("VaR", "stopped", blocked_by=kind)
        outcomes[kind] = DataPlanner(ScriptedExpert(blocked),
                                     layer).plan("…", "VaR").negotiation.outcome
    assert outcomes["model"] != outcomes["data"]


def test_the_orchestrator_has_a_branch_for_a_failed_reasoning_step():
    import inspect

    from agents.pipeline import AgentPipeline

    source = inspect.getsource(AgentPipeline._not_agreed)
    assert 'requirement.blocked_by == "model"' in source
    # It must be reached before the decision branches, since the decision on
    # that path is UNSUPPORTED and would otherwise answer for it.
    assert source.index('blocked_by == "model"') < source.index('"UNSUPPORTED"')


def test_the_derive_schema_asks_for_only_what_cannot_be_defaulted():
    """Eighteen required properties was a contract GLM-5.2 could not meet.

    Pinned because the failure was expensive and silent: two and a half minutes
    of retries, then a refusal that blamed the data. Anything added to `required`
    from here has to be a field `_build` genuinely cannot default.
    """
    from agents.domain_expert_agent import REVISE_SCHEMA, SCHEMA

    assert SCHEMA["required"] == ["task_understood", "answerable", "fields",
                                 "calculation"]
    # A revision has exactly one further obligation: say whether you committed.
    assert set(REVISE_SCHEMA["required"]) - set(SCHEMA["required"]) == {"decision"}


def test_every_optional_schema_property_survives_being_absent():
    """The rebuilder must be total, since the schema no longer compels anything."""
    from agents.contracts import ToolCatalogue
    from agents.domain_expert_agent import DomainExpertAgent

    built = DomainExpertAgent(knowledge=None)._build(
        {"task_understood": "minimal", "answerable": True, "fields": []},
        [], ToolCatalogue(), None, [])
    assert built.task == "minimal"
    assert built.rows is None            # silence, not a fabricated window
    assert built.decision is None        # not committed, not agreed
    assert built.curve_family == "nominal"
    assert built.temporal.as_dict()["start_date"] is None
    assert built.calculation is None


def test_naming_a_retrieval_capability_warns_rather_than_declines():
    """Retrieval is not a tool you schedule, and confusing the two cost a turn.

    The `executable` flag exists so a plan cannot name a capability the
    execution layer will not dispatch. Read as *availability*, it produced the
    opposite error: told `get_rate_history` was "not executable", the expert
    declined a plain 30-year history outright and asserted the data server was
    down — in a turn where retrieval had already succeeded twice.

    Naming one is a category error, not a failed request. The rows come back
    regardless, so the plan continues with a warning.
    """
    from agents.contracts import ToolCatalogue, ToolSpec
    from agents.domain_expert_agent import DomainExpertAgent

    catalogue = ToolCatalogue(
        tools=[ToolSpec("get_rate_history", "daily series", "data", executable=False),
               ToolSpec("compute_var", "historical VaR", "risk", executable=True)],
        fields=["observation_date", "rate_percent"], tenors=["y30"],
        can_calculate=True)
    built = DomainExpertAgent(knowledge=None)._build(
        {"task_understood": "30 year history", "answerable": True,
         "fields": ["observation_date", "rate_percent"], "tenors": ["y30"],
         "calculation": "get_rate_history"},
        [], catalogue, None, [])

    assert built.answerable is True, "a plain retrieval was declined"
    assert built.calculation is None
    assert built.tenors == ["y30"], "the rows it would return were dropped too"
    assert any("returned anyway" in w for w in built.warnings), built.warnings


def test_the_catalogue_tells_the_expert_that_retrieval_always_happens():
    """A boolean was not enough; the split has to be stated in words."""
    from agents.contracts import ToolCatalogue, ToolSpec

    catalogue = ToolCatalogue(
        tools=[ToolSpec("get_rate_history", "daily series", "data"),
               ToolSpec("compute_var", "historical VaR", "risk", executable=True)])
    payload = catalogue.as_dict()

    assert payload["available_calculations"] == ["compute_var"]
    assert payload["retrieval_always_available"] == ["get_rate_history"]
    assert "ALWAYS" in payload["how_to_read_this"]
    # And a tool says what it is, rather than carrying a flag to be interpreted.
    kinds = {t["name"]: t["kind"] for t in payload["tools"]}
    assert kinds == {"get_rate_history": "retrieval", "compute_var": "calculation"}


def test_the_expert_cannot_withdraw_its_own_ambiguity():
    """Only the user settles which curve they meant.

    "What is the 30 year?" opened as `ambiguous` — correctly, both curves
    publish that maturity — and the next round revised it to `nominal`. The
    transcript recorded `curve family ambiguous -> nominal`, which reads like a
    resolution and was a guess, and the user was served a nominal par yield
    having never been asked.

    A capability assessment answers what the source holds, not what was meant,
    so no evidence it can offer settles this.
    """
    from agents.contracts import Requirement
    from agents.domain_expert_agent import DomainExpertAgent

    proposal = Requirement(task="30 year", answerable=True,
                           curve_family="ambiguous")
    revised = Requirement(task="30 year", answerable=True,
                          curve_family="nominal")
    kept = DomainExpertAgent._keep_ambiguity(proposal, revised)

    assert kept.curve_family == "ambiguous"
    assert any("only the user" in w for w in kept.warnings), kept.warnings


def test_a_family_the_expert_stated_from_the_start_is_left_alone():
    """The guard must not turn a clear request into a question."""
    from agents.contracts import Requirement
    from agents.domain_expert_agent import DomainExpertAgent

    for stated in ("nominal", "real"):
        kept = DomainExpertAgent._keep_ambiguity(
            Requirement(task="t", answerable=True, curve_family=stated),
            Requirement(task="t", answerable=True, curve_family=stated))
        assert kept.curve_family == stated
        assert not kept.warnings


def test_the_agents_own_field_names_never_reach_the_user():
    """Tool names were scrubbed; the payload's field names were not.

    A real decline ended "...and available_calculations is empty" — an internal
    key quoted back at the user, and false besides (four calculations exist;
    none of them computes CVA). A model shown a JSON structure will quote its
    keys, so the keys have to be scrubbed with the same brush as tool names.
    """
    from agents.redaction import CONTRACT_KEYS, scrub_identifiers

    text = ("The CVA method needs counterparty_exposure, and "
            "available_calculations is empty, so unsupported_fields covers it.")
    cleaned = scrub_identifiers(text, list(CONTRACT_KEYS))

    for leaked in ("available_calculations", "unsupported_fields"):
        assert leaked not in cleaned, cleaned
    assert "the calculations this system can run" in cleaned


def test_a_deliberate_quotation_in_the_trace_is_left_alone():
    """Backticked identifiers are a developer surface and stay verbatim."""
    from agents.redaction import CONTRACT_KEYS, scrub_identifiers

    text = "The plan carries `candidate_fields` and `curve_family`."
    assert scrub_identifiers(text, list(CONTRACT_KEYS)) == text


def test_an_exhausted_account_is_not_reported_as_a_retryable_blip():
    """"Asking again usually works" must not be said when it cannot come true.

    Z.AI answered `429 / Insufficient balance` for every call. The gateway told
    the user the reasoning step had failed and to ask again — advice that sends
    them round a loop that cannot terminate, because no retry adds balance to an
    account. `None` from a structured call cannot distinguish a blip from a
    wall, so the *kind* has to survive the failure.
    """
    from agents.observability import TERMINAL_FAILURES
    from agents.pipeline import AgentPipeline
    import inspect

    assert TERMINAL_FAILURES == {"balance", "auth"}
    source = inspect.getsource(AgentPipeline._not_agreed)
    assert 'requirement.blocked_by == "account"' in source
    # Reached before the retryable branch, or that branch answers for it.
    assert source.index('"account"') < source.index('"model"')
    # And the retry invitation belongs only to the recoverable case.
    account, model = source.split('blocked_by == "model"')[0], source
    assert "Asking again" not in account
    assert "needs an operator" in account


def test_the_failure_kind_does_not_leak_between_turns():
    """Thread-local and cleared per call: a stale kind must never describe a
    later success, and two turns on two worker threads must not read each
    other's."""
    import threading

    from agents.observability import last_failure_kind

    seen: list[str] = []
    t = threading.Thread(target=lambda: seen.append(last_failure_kind()))
    t.start()
    t.join()
    assert seen == [""]


def test_settings_for_a_calculation_nobody_named_are_reported():
    """A plan that says *how* to compute while naming nothing to compute.

    glm-5.2 returned `calculation_params: {horizon_days: 10,
    confidence_level: 0.99}` with `calculation` absent, and the result was a
    plain table presented for a question that asked for VaR. The parameters are
    the tell: nobody states a 10-day horizon for a retrieval.
    """
    from agents.contracts import ToolCatalogue, ToolSpec
    from agents.domain_expert_agent import DomainExpertAgent

    catalogue = ToolCatalogue(
        tools=[ToolSpec("compute_var", "historical VaR", "risk", executable=True)],
        fields=["observation_date", "rate_percent"], can_calculate=True)
    built = DomainExpertAgent(knowledge=None)._build(
        {"task_understood": "10-day 99% VaR", "answerable": True,
         "fields": ["rate_percent"], "calculation": None,
         "calculation_params": {"horizon_days": 10, "confidence_level": 0.99}},
        [], catalogue, None, [])

    assert built.calculation is None
    assert any("names no calculation" in w for w in built.warnings), built.warnings


def test_a_plain_retrieval_carries_no_such_warning():
    """The check must not fire on the normal case."""
    from agents.contracts import ToolCatalogue
    from agents.domain_expert_agent import DomainExpertAgent

    built = DomainExpertAgent(knowledge=None)._build(
        {"task_understood": "the curve", "answerable": True,
         "fields": ["rate_percent"], "calculation": None},
        [], ToolCatalogue(fields=["rate_percent"]), None, [])
    assert not any("names no calculation" in w for w in built.warnings)


# --- the decision drives what the user is told ------------------------------


def test_every_decision_is_one_the_orchestrator_knows_how_to_handle():
    from agents.pipeline import AgentPipeline

    handled = {"AGREED", "NEEDS_USER_INPUT", "UNSUPPORTED",
               "CANNOT_REACH_AGREEMENT"}
    import inspect
    source = inspect.getsource(AgentPipeline._not_agreed)
    for decision in handled - {"AGREED"}:
        assert decision in source, f"{decision} has no branch in the orchestrator"


def test_needing_user_input_without_a_question_is_not_a_clarification():
    """A live turn asked "Which option did you mean?" with no options at all.

    The plan beside it was complete — compute_var, 250 grounded rows, a 10-day
    99% horizon — so the user was stopped and asked to choose between nothing.
    The orchestrator's standing rule is that a clarifying question carries real
    choices; a decision that names no question cannot satisfy it, so it is not
    a decision to clarify.
    """
    from agents.contracts import Requirement

    settled = Requirement(task="VaR", answerable=True, calculation="compute_var",
                          decision="NEEDS_USER_INPUT", open_questions=[])
    assert DataPlanner._decision_of(settled) == "AGREED"
    assert any("named no question" in w for w in settled.warnings), settled.warnings


def test_a_real_question_still_reaches_the_user():
    from agents.contracts import Requirement

    asking = Requirement(task="VaR", answerable=True, decision="NEEDS_USER_INPUT",
                         open_questions=["Which book — the demo or your own?"])
    assert DataPlanner._decision_of(asking) == "NEEDS_USER_INPUT"


def test_an_unanswerable_task_asking_nothing_is_unsupported_not_a_question():
    from agents.contracts import Requirement

    stuck = Requirement(task="CVA", answerable=False,
                        decision="NEEDS_USER_INPUT", open_questions=[])
    assert DataPlanner._decision_of(stuck) == "UNSUPPORTED"


# --- result validation ------------------------------------------------------


def _expert():
    from agents.domain_expert_agent import DomainExpertAgent
    return DomainExpertAgent(knowledge=None)


def test_a_result_matching_the_agreed_plan_is_valid():
    expert = _expert()
    requirement = hypothesis(calculation="compute_var",
                             calculation_params={"confidence_level": 0.99,
                                                 "horizon_days": 10})
    calculation = {"tool": "compute_var",
                   "result": {"var": 494556.09, "horizon_days": 10,
                              "confidence_level": 0.99, "units": "USD"}}
    validation = expert.validate_result(requirement, calculation, {})

    assert validation.verdict in {"VALID", "VALID_WITH_WARNINGS"}
    assert not validation.mismatches


def test_a_ten_day_plan_returning_a_one_day_figure_is_rejected():
    """The live defect that motivated this gate, pinned as a test."""
    expert = _expert()
    requirement = hypothesis(calculation="compute_var",
                             calculation_params={"confidence_level": 0.99,
                                                 "horizon_days": 10})
    calculation = {"tool": "compute_var",
                   "result": {"var": 165729.86, "horizon_days": 1,
                              "confidence_level": 0.99, "units": "USD"}}
    validation = expert.validate_result(requirement, calculation, {})

    assert validation.verdict == "INVALID"
    assert validation.blocking is True
    assert any("horizon_days" in m for m in validation.mismatches)
    assert "10" in validation.interpretation or "horizon" in validation.interpretation


def test_a_missing_calculation_is_rejected_rather_than_ignored():
    """Observed live: the plan agreed a DV01 and nothing came back."""
    expert = _expert()
    validation = expert.validate_result(
        hypothesis(calculation="compute_dv01"), None, {})

    assert validation.verdict == "INVALID"
    assert any("no calculation came back" in m for m in validation.mismatches)


def test_a_result_for_the_wrong_day_is_rejected():
    expert = _expert()
    requirement = hypothesis(calculation="compute_dv01",
                             temporal=TemporalScope(as_of_date="2020-03-17"))
    calculation = {"tool": "compute_dv01",
                   "result": {"dv01": 20653.25, "units": "USD per bp"}}
    validation = expert.validate_result(
        requirement, calculation, {"observation_date": "2026-08-11"})

    assert validation.verdict == "INVALID"
    assert any("as_of_date" in m for m in validation.mismatches)


def test_an_unreadable_verdict_is_never_treated_as_a_pass():
    from agents.a2a.envelope import validation_from_dict

    assert validation_from_dict({"verdict": "probably fine"}).verdict == "INVALID"
    assert validation_from_dict({"verdict": "VALID"}).verdict == "VALID"
    assert validation_from_dict(None) is None


# --- temporal intent --------------------------------------------------------


def test_a_temporal_scope_describes_itself_honestly():
    assert TemporalScope().describe() == "the latest available observation"
    assert TemporalScope().is_historical is False
    assert TemporalScope(as_of_date="2008-09-15").is_historical is True
    assert "2008" in TemporalScope(start_date="2008-01-01",
                                   end_date="2008-12-31").describe()
    assert TemporalScope(lookback_days=250).is_historical is False


def test_a_temporal_scope_survives_the_wire():
    from agents.a2a.envelope import requirement_from_dict

    original = hypothesis(temporal=TemporalScope(start_date="2008-01-01",
                                                 end_date="2008-12-31",
                                                 lookback_days=250))
    rebuilt = requirement_from_dict(original.as_dict())
    assert rebuilt.temporal.start_date == "2008-01-01"
    assert rebuilt.temporal.end_date == "2008-12-31"
    assert rebuilt.temporal.lookback_days == 250
    assert isinstance(rebuilt.temporal.lookback_days, int)


# --- materiality ------------------------------------------------------------


def test_a_curve_family_answer_is_material_only_when_a_method_depends_on_it():
    from agents.a2a.elicitation import is_domain_material

    answer = {"rate_kind": "real"}
    # Selecting rows for a plain history question changes nothing analytical.
    assert is_domain_material(answer, has_methodology=False) is False
    # The same answer while a calculation is planned changes what it measures.
    assert is_domain_material(answer, has_methodology=True) is True


def test_choosing_a_book_is_execution_only():
    from agents.a2a.elicitation import is_domain_material

    assert is_domain_material({"portfolio_id": "TREASURY_DEMO_001"},
                              has_methodology=True) is False
