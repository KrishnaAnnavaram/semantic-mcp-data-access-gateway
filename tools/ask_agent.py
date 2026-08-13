"""End-to-end demo of the quant agent + knowledge layer.

Usage:
    python demo.py                     # runs a couple of sample queries
    python demo.py "your question"     # ask your own

Requires ANTHROPIC_API_KEY in the environment (the agent calls Claude).
The vector DB alone needs no key:  python src/knowledge_base.py

Set DATA_BACKEND=postgres (and QDRANT_URL) to run against the real data.
"""

import os
import sys

from backend.agent.quant_agent import QuantAgent, render_trace

SAMPLES = [
    "What is the current 2s10s slope of the yield curve?",
    "What's the 10-year Treasury yield, and how has it moved over the past year?",
]


def run(agent: QuantAgent, question: str) -> None:
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

    agent = QuantAgent()  # builds/loads the vector DB, wires the mock data provider
    for q in sys.argv[1:] or SAMPLES:
        run(agent, q)


if __name__ == "__main__":
    main()
