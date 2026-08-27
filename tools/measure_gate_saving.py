"""Measure what the requirement gate avoids, in calls rather than in claims.

Wall-clock latency needs the whole stack up (PostgreSQL, Qdrant, the MCP
children and a live model provider), and a number measured on one machine on one
afternoon is weak evidence anyway. What *is* measurable anywhere, deterministic,
and the dominant term in this system's latency is the **count of calls a turn
makes** - because each model call on the reasoning seat runs tens of seconds and
each Qdrant query is a network round trip plus an embedding.

So this script runs the real A2A network with the model calls stubbed and counts
what actually happened, from the same handoff ledger the UI reads:

    python tools/measure_gate_saving.py

It reports A2A handoffs, Qdrant queries and reasoning-model call sites reached,
for a complete question and for an incomplete one, with the gate on and off. The
difference between the last two is the saving, and it is counted rather than
estimated.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The repo root, found by walking up for a marker - never by counting parents.
_here = Path(__file__).resolve()
for _candidate in (_here, *_here.parents):
    if (_candidate / "docker-compose.yml").exists():
        sys.path.insert(0, str(_candidate))
        break

from backend.providers.base import MockDataProvider  # noqa: E402

from agents.a2a.runtime import AgentNetwork  # noqa: E402

COMPLETE = "What is the 2s10s history?"
INCOMPLETE = "Compare the Treasury curve and show the biggest movements."

#: Model call sites each skill reaches, per invocation, in the shipping code.
#: Counted from the source rather than sampled: `derive` is one structured call,
#: `assess` one per negotiation round, `revise` one per round, `reflect` one.
#: Stated here because the harness stubs those calls out - stubbing is what
#: makes the count deterministic, and this table is what keeps it honest about
#: what the stub replaced.
MODEL_CALLS_PER_SKILL = {
    "handle_user_turn": 1,                    # orchestrator.classify
    "check_requirement_completeness": 0,      # deterministic - the whole point
    "derive_data_requirement": 1,             # domain_expert.derive
    "describe_data_capabilities": 0,          # reads the live provider
    "assess_data_requirement": 1,             # mcp_agent.assess, per round
    "execute_data_plan": 0,                   # fetch + deterministic workflow
    "list_data_choices": 0,
    "validate_result": 1,
    "provide_input": 0,
}

#: Vector queries `derive` issues before it can produce anything: two against
#: the executable corpus and two against the reference corpus
#: (`DomainExpertAgent._retrieve` and `._retrieve_market_risk`).
QDRANT_QUERIES_PER_DERIVE = 4


def _network(gate: bool):
    from tests.test_a2a import StubKnowledge, wire  # noqa: PLC0415

    os.environ["PREFLIGHT_ENABLED"] = "true" if gate else "false"
    return wire(AgentNetwork(StubKnowledge(), MockDataProvider()))


def _measure(question: str, gate: bool) -> dict:
    net = _network(gate)
    try:
        outcome = net.handle(question, session_id=f"measure-{gate}")
    finally:
        net.shutdown()

    skills = [h["skill"] for h in outcome.handoffs["handoffs"]]
    # `PREFLIGHT_ENABLED=false` makes the check always pass, but the A2A hop
    # still happens - so "gate off" is not the same thing as "before the gate
    # existed". The pre-change baseline is this turn without that hop, and
    # excluding it here is what makes the comparison honest rather than
    # flattering.
    if not gate:
        skills = [s for s in skills if s != "check_requirement_completeness"]
    derives = skills.count("derive_data_requirement")
    # `revise` runs inside derive_data_requirement, once per negotiation round,
    # so it is counted from the rounds the ledger recorded rather than from the
    # skill list, which cannot see it.
    rounds = outcome.handoffs.get("negotiation_rounds", 0)
    return {
        "route": outcome.route,
        "handoffs": len(skills),
        "skills": skills,
        "qdrant_queries": derives * QDRANT_QUERIES_PER_DERIVE,
        "model_calls": sum(MODEL_CALLS_PER_SKILL.get(s, 0) for s in skills) + rounds,
        "negotiation_rounds": rounds,
    }


def _row(label: str, measured: dict) -> str:
    return (f"{label:<34} {measured['route']:<14} {measured['handoffs']:>9} "
            f"{measured['qdrant_queries']:>8} {measured['model_calls']:>12}")


def main() -> int:
    print("Requirement gate - measured cost of one turn\n")
    print(f"{'question':<34} {'route':<14} {'handoffs':>9} {'qdrant':>8} "
          f"{'model calls':>12}")
    print("-" * 82)

    complete_on = _measure(COMPLETE, gate=True)
    complete_off = _measure(COMPLETE, gate=False)
    incomplete_on = _measure(INCOMPLETE, gate=True)
    incomplete_off = _measure(INCOMPLETE, gate=False)

    print(_row("complete, before the gate", complete_off))
    print(_row("complete, with the gate", complete_on))
    print(_row("incomplete, before the gate", incomplete_off))
    print(_row("incomplete, with the gate", incomplete_on))

    print("\nSaving on an incomplete question:")
    for key, unit in (("handoffs", "A2A calls"),
                      ("qdrant_queries", "vector queries"),
                      ("model_calls", "model calls")):
        before, after = incomplete_off[key], incomplete_on[key]
        # Signed as a change, not as a magnitude: a reduction reads `-4`.
        print(f"  {unit:<16} {before:>3} -> {after:<3} ({after - before:+d})")

    print("\nCost on a complete question:")
    extra = complete_on["handoffs"] - complete_off["handoffs"]
    print(f"  {extra} extra A2A call(s), 0 extra model calls, 0 extra vector "
          f"queries.")
    print("\nThe gate's own check is deterministic: regular expressions and a "
          "lexicon over\nthe user's words, no model call and no retrieval.")
    print("\nWall-clock latency is NOT reported here. It needs PostgreSQL, "
          "Qdrant, the MCP\nchildren and a live provider, and this harness stubs "
          "the model calls to make the\ncounts deterministic. Run a real turn "
          "against a live stack and read the Latency\ntab, which is measured "
          "from the same events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
