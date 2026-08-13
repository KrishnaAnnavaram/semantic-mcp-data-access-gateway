"""Run the evaluation suite.

    python -m evaluation.run              # local: run every case, print a table
    python -m evaluation.run --langsmith  # also upload the dataset and results
    python -m evaluation.run --case var_10k_rows

Works with or without a LangSmith key. Locally it is a pass/fail harness you can
run in a terminal; with `--langsmith` the same cases and the same scorers are
pushed as a dataset and an experiment, so runs are comparable over time.

Deliberately driven through `AgentPipeline` rather than HTTP: the properties
being scored belong to the agents, and going through the service would make a
red result ambiguous between a reasoning regression and a serving bug.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from evaluation.dataset import CASES, Case
from evaluation.evaluators import ALL_EVALUATORS


def build_pipeline():
    from treasury_db.db import load_dotenv  # noqa: PLC0415

    load_dotenv()
    from agents import AgentPipeline  # noqa: PLC0415

    from backend.knowledge.knowledge_base import KnowledgeBase  # noqa: PLC0415
    from backend.providers.base import make_data_provider  # noqa: PLC0415

    return AgentPipeline(KnowledgeBase(), make_data_provider())


def run_case(pipeline, case: Case) -> dict[str, Any]:
    """Run one question and flatten the outcome into what the scorers read."""
    started = time.perf_counter()
    outcome = pipeline.handle(case.question)
    elapsed = time.perf_counter() - started

    requirement = outcome.requirement
    intent = outcome.intent
    return {
        "answer": outcome.answer,
        "route": outcome.route,
        "data_plan": requirement.as_dict() if requirement else None,
        "negotiation": outcome.negotiation.as_dict() if outcome.negotiation else None,
        "citations": outcome.citations,
        "elicitation": ({"question": intent.question, "options": intent.options}
                        if intent and outcome.route == "clarify" else None),
        "tables": outcome.tables,
        "latency_s": round(elapsed, 2),
    }


def score(outcome: dict[str, Any], case: Case) -> list[dict[str, Any]]:
    expected = case.as_outputs()
    return [evaluator(outcome, expected) for evaluator in ALL_EVALUATORS]


def run_local(cases: list[Case]) -> int:
    pipeline = build_pipeline()
    rows: list[tuple[Case, list[dict[str, Any]], dict[str, Any]]] = []

    for case in cases:
        print(f"  running {case.id} ...", flush=True)
        try:
            outcome = run_case(pipeline, case)
        except Exception as exc:  # noqa: BLE001 - a crash is a result too
            outcome = {"answer": f"ERROR: {type(exc).__name__}: {exc}",
                       "route": "error", "citations": []}
        rows.append((case, score(outcome, case), outcome))

    print(f"\n{'=' * 96}")
    print(f"{'case':22} {'route':14} {'score':>7}  {'sec':>5}  failing checks")
    print("=" * 96)

    total = passed_total = 0
    hard_failures: list[str] = []
    for case, results, outcome in rows:
        # "Not applicable" checks are excluded rather than counted as passes, so
        # a suite of mostly-inapplicable cases cannot look green by dilution.
        applicable = [r for r in results if r["comment"] != "not applicable"]
        passed = [r for r in applicable if r["score"] == 1.0]
        failed = [r for r in applicable if r["score"] != 1.0]
        total += len(applicable)
        passed_total += len(passed)
        if failed:
            hard_failures.extend(f"{case.id}/{r['key']}: {r['comment']}" for r in failed)
        print(f"{case.id:22} {outcome.get('route', '?'):14} "
              f"{len(passed):>3}/{len(applicable):<3} {outcome.get('latency_s', 0):>5}  "
              f"{', '.join(r['key'] for r in failed) or '-'}")

    print("=" * 96)
    pct = (100.0 * passed_total / total) if total else 0.0
    print(f"{passed_total}/{total} checks passed ({pct:.0f}%)")
    if hard_failures:
        print("\nfailures:")
        for line in hard_failures:
            print(f"  - {line}")
    print()
    return 0 if passed_total == total else 1


def run_langsmith(cases: list[Case]) -> int:
    """Push the same cases and scorers to LangSmith as a dataset + experiment."""
    from agents.observability import langsmith_status  # noqa: PLC0415

    status = langsmith_status()
    if not status["enabled"]:
        print(f"LangSmith is not configured: {status['reason']}")
        print("Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY, then retry.")
        return 2

    from langsmith import Client  # noqa: PLC0415
    from langsmith.evaluation import evaluate  # noqa: PLC0415

    client = Client()
    dataset_name = "semantic-mcp-gateway-agents"

    existing = list(client.list_datasets(dataset_name=dataset_name))
    dataset = existing[0] if existing else client.create_dataset(
        dataset_name=dataset_name,
        description="Behavioural properties the three-agent pipeline must hold: "
                    "routing, grounded row counts, refusal of impossible fields.")
    if not existing:
        client.create_examples(
            inputs=[c.as_inputs() for c in cases],
            outputs=[c.as_outputs() for c in cases],
            dataset_id=dataset.id)
        print(f"created dataset {dataset_name!r} with {len(cases)} example(s)")
    else:
        print(f"using existing dataset {dataset_name!r}")

    pipeline = build_pipeline()

    def target(inputs: dict) -> dict:
        case = next((c for c in cases if c.question == inputs["question"]), None)
        return run_case(pipeline, case or Case("adhoc", inputs["question"],
                                               "data_request", "ad hoc"))

    def make_scorer(evaluator):
        def scorer(run, example):
            return evaluator(run.outputs or {}, example.outputs or {})
        scorer.__name__ = evaluator.__name__
        return scorer

    results = evaluate(
        target, data=dataset_name,
        evaluators=[make_scorer(e) for e in ALL_EVALUATORS],
        experiment_prefix="agents", max_concurrency=1,
    )
    print(f"\nexperiment complete: {getattr(results, 'experiment_name', 'see LangSmith')}")
    print(f"project: {status['project']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--langsmith", action="store_true",
                        help="upload dataset and results to LangSmith")
    parser.add_argument("--case", help="run a single case by id")
    args = parser.parse_args()

    cases = [c for c in CASES if c.id == args.case] if args.case else CASES
    if not cases:
        print(f"no such case: {args.case}")
        return 2

    print(f"evaluating {len(cases)} case(s) over {len(ALL_EVALUATORS)} scorer(s)\n")
    return run_langsmith(cases) if args.langsmith else run_local(cases)


if __name__ == "__main__":
    sys.exit(main())
