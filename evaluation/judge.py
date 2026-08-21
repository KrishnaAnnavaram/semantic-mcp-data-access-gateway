"""LLM-as-judge: score the prose a user actually reads.

`evaluation/run.py` scores *behaviour* — the route taken, whether the window was
cited, whether impossible fields were refused. All of that can be true while the
answer itself is unreadable, over-long, or quietly leaking an internal
identifier. This module reads the finished text and judges it.

Two deliberate design choices:

**The judge never sees which system produced the answer**, and is given the
requirement and the retrieved evidence rather than a reference answer. Market
data moves; a golden answer would be wrong by Thursday.

**The leak check is not left to the judge.** Whether `compute_dv01` appears in
prose is a regex question with a right answer, so it is computed
deterministically and reported alongside the model's scores. A judge that can be
argued out of a factual finding is not a control.

    python -m evaluation.judge              # the full case set
    python -m evaluation.judge --case var_10k_rows
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

RUBRIC = {
    "grounded": "Every number is attributed to retrieved evidence or a tool result. "
                "No figure appears that the material does not support.",
    "honest": "Limits are stated plainly. Synthetic data is labelled synthetic. "
              "Nothing unavailable is quietly substituted or implied.",
    "answers_the_question": "The user's actual question is addressed, not an "
                            "adjacent one the system found easier.",
    "readable": "A market-risk analyst could act on this. No internal jargon, no "
                "function names, no field names presented as if they were prose.",
    "concise": "No padding, no restating the question, no narrating its own process.",
}

JUDGE_SYSTEM = """\
You are grading the written answer of a market-risk data assistant. You are \
given the user's question, the evidence the system retrieved, what it planned to \
fetch, and the answer it produced.

Score each criterion 1-5, where 3 is acceptable and 5 is exemplary. Judge only \
what is in front of you: you have no market data of your own, so never mark an \
answer down for a figure you cannot check, and never mark one up for confidence.

Penalise heavily:
- a number with no support in the evidence or the fetched result
- presenting synthetic or model-implied values as real or executable
- an internal identifier (a function or column name) shown to the user as prose
- claiming something was computed that the plan says was unavailable

Reward:
- saying plainly that something is not available
- attributing a window or threshold to the document that states it
- brevity that loses no substance

`verdict` is "pass" only if no criterion scored below 3."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "object",
            "properties": {k: {"type": "integer", "minimum": 1, "maximum": 5}
                           for k in RUBRIC},
            "required": list(RUBRIC),
            "additionalProperties": False,
        },
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "strongest": {"type": "string"},
        "weakest": {"type": "string"},
        "leaked_identifiers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Internal function or column names shown as prose. "
                           "Empty if none.",
        },
    },
    "required": ["scores", "verdict", "strongest", "weakest", "leaked_identifiers"],
    "additionalProperties": False,
}


@dataclass
class Judgement:
    case_id: str
    scores: dict[str, int] = field(default_factory=dict)
    verdict: str = "fail"
    strongest: str = ""
    weakest: str = ""
    judge_leaks: list[str] = field(default_factory=list)
    actual_leaks: list[str] = field(default_factory=list)
    answer: str = ""
    error: str = ""

    @property
    def mean(self) -> float:
        return sum(self.scores.values()) / len(self.scores) if self.scores else 0.0

    @property
    def clean(self) -> bool:
        """The deterministic finding, which outranks the model's opinion."""
        return not self.actual_leaks


def find_identifiers(text: str, names) -> list[str]:
    """Bare internal identifiers in user-facing prose.

    The evaluator's own rule, character for character, so the judge and the
    behavioural suite can never disagree about what counts as a leak. A name
    inside backticks is deliberate - developer surfaces quote identifiers.
    """
    return [n for n in names
            if re.search(rf"(?<![\w`]){re.escape(n)}(?![\w`])", text or "")]


def judge_answer(case_id: str, question: str, outcome: dict,
                 tool_names) -> Judgement:
    from agents.observability import structured_call  # noqa: PLC0415
    from llm import CallSite  # noqa: PLC0415

    answer = outcome.get("answer") or ""
    plan = outcome.get("data_plan") or {}
    material = {
        "question": question,
        "answer": answer,
        "planned_fields": plan.get("fields"),
        "planned_rows": plan.get("rows"),
        "row_grounded": plan.get("grounded"),
        "row_quote": plan.get("row_quote"),
        "fields_refused": [n.get("name") for n in plan.get("field_notes") or []
                           if n.get("verdict") == "unavailable"],
        "evidence": [c.get("label") for c in outcome.get("citations") or []],
        "calculation": outcome.get("calculation"),
    }
    judgement = Judgement(case_id=case_id, answer=answer,
                          actual_leaks=find_identifiers(answer, tool_names))
    payload = structured_call(
        call_site=CallSite.DOMAIN_EXPERT, system=JUDGE_SYSTEM,
        prompt=json.dumps(material, default=str, indent=2)[:12_000],
        schema=JUDGE_SCHEMA, max_tokens=4000, result_name="emit_judgement")
    if not payload:
        judgement.error = "judge did not return a usable verdict"
        return judgement
    judgement.scores = payload.get("scores") or {}
    judgement.verdict = payload.get("verdict", "fail")
    judgement.strongest = payload.get("strongest", "")
    judgement.weakest = payload.get("weakest", "")
    judgement.judge_leaks = payload.get("leaked_identifiers") or []
    return judgement


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="judge one case by id")
    args = parser.parse_args()

    from backend.knowledge.knowledge_base import KnowledgeBase  # noqa: PLC0415
    from backend.providers.base import make_data_provider  # noqa: PLC0415

    from agents import get_network  # noqa: PLC0415
    from evaluation.dataset import CASES  # noqa: PLC0415
    from evaluation.evaluators import TOOL_NAMES  # noqa: PLC0415

    cases = [c for c in CASES if not args.case or c.id == args.case]
    if not cases:
        print(f"no case matching {args.case!r}")
        return 2

    pipeline = get_network(KnowledgeBase(), make_data_provider())
    judgements: list[Judgement] = []
    for case in cases:
        print(f"  judging {case.id} ...", flush=True)
        outcome = pipeline.handle(case.question, None, False)
        as_dict = {
            "answer": outcome.answer,
            "data_plan": outcome.requirement.as_dict() if outcome.requirement else {},
            "citations": outcome.citations,
            "calculation": outcome.calculation,
        }
        judgements.append(judge_answer(case.id, case.question, as_dict, TOOL_NAMES))

    _report(judgements)
    leaked = [j for j in judgements if not j.clean]
    failed = [j for j in judgements if j.verdict != "pass" and not j.error]
    return 1 if leaked or failed else 0


def _report(judgements: list[Judgement]) -> None:
    width = 96
    print("\n" + "=" * width)
    header = f"{'case':<26}{'mean':>6}  " + "".join(
        f"{k[:9]:>10}" for k in RUBRIC) + f"{'leaks':>8}"
    print(header)
    print("=" * width)
    for j in judgements:
        if j.error:
            print(f"{j.case_id:<26}{'--':>6}  {j.error}")
            continue
        row = f"{j.case_id:<26}{j.mean:>6.1f}  " + "".join(
            f"{j.scores.get(k, 0):>10}" for k in RUBRIC)
        print(row + f"{('CLEAN' if j.clean else 'LEAK'):>8}")
    print("=" * width)

    scored = [j for j in judgements if j.scores]
    if scored:
        print(f"mean across {len(scored)} case(s): "
              f"{sum(j.mean for j in scored) / len(scored):.2f} / 5")
        for key in RUBRIC:
            values = [j.scores.get(key, 0) for j in scored]
            print(f"  {key:<22} {sum(values) / len(values):>4.2f}   "
                  f"low={min(values)}")

    leaked = [j for j in judgements if not j.clean]
    print("\nIDENTIFIER LEAK AUDIT (deterministic, not the judge's opinion)")
    if leaked:
        for j in leaked:
            print(f"  {j.case_id}: {j.actual_leaks}")
    else:
        print(f"  no internal identifier reached the user in "
              f"{len(judgements)} answer(s)")

    weak = [j for j in judgements if j.scores and j.mean < 4]
    if weak:
        print("\nWEAKEST POINTS")
        for j in sorted(weak, key=lambda x: x.mean)[:5]:
            print(f"  {j.case_id} ({j.mean:.1f}): {j.weakest[:110]}")


if __name__ == "__main__":
    sys.exit(main())
