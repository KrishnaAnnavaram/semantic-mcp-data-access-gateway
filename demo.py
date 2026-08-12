"""End-to-end demo of the smart server-side agent + knowledge layer.

Usage:
    python demo.py                     # runs a couple of sample queries
    python demo.py "your question"     # ask your own

Requires ANTHROPIC_API_KEY in the environment (Phase 4 uses Claude).
Phase 3 alone (the vector DB) needs no key:  python src/knowledge_base.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from smart_agent import SmartAgent, render_trace  # noqa: E402

SAMPLES = [
    "What's my 1-day 99% VaR on the equity book?",
    "Show me the CVA for counterparty ACME_BANK.",
]


def run(agent: SmartAgent, question: str) -> None:
    print("=" * 72)
    print(f"USER: {question}\n")
    result = agent.answer(question)
    print("-- SERVER-AGENT / DECISION TRACE " + "-" * 38)
    print(render_trace(result.trace))
    print("\n-- ANSWER " + "-" * 61)
    print(result.answer)
    print()


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set - Phase 4 needs it to call Claude.")
        print("Set it, then re-run. (Phase 3 alone: python src/knowledge_base.py)")
        sys.exit(1)

    agent = SmartAgent()  # builds/loads the vector DB, wires the mock data provider
    for q in sys.argv[1:] or SAMPLES:
        run(agent, q)


if __name__ == "__main__":
    main()
