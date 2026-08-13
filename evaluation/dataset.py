"""The evaluation set: questions whose *correct handling* is known in advance.

Not a list of expected answers. Market data moves, so pinning "the 2s10s slope
is 48 bp" would make the suite fail every time Treasury publishes. What is
stable is the **behaviour** each question should provoke:

* which route the orchestrator should take,
* whether the row count must be grounded in a citation,
* which requested fields cannot exist and must be refused rather than filled.

Those properties hold whatever the rates do, so a red result means a regression
in reasoning rather than a change in the market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Case:
    """One question, plus what a correct system must do with it."""

    id: str
    question: str
    expect_route: str                      # direct | clarify | data_request
    why: str                               # what this case is probing
    expect_grounded: bool = False          # the corpus must justify the row count
    expect_rows: int | None = None         # only where the corpus states one
    impossible_fields: list[str] = field(default_factory=list)
    expect_citations: bool = False
    max_sentences: int | None = None

    def as_inputs(self) -> dict[str, Any]:
        return {"question": self.question}

    def as_outputs(self) -> dict[str, Any]:
        return {"expect_route": self.expect_route,
                "expect_grounded": self.expect_grounded,
                "expect_rows": self.expect_rows,
                "impossible_fields": self.impossible_fields,
                "expect_citations": self.expect_citations,
                "max_sentences": self.max_sentences}


CASES: list[Case] = [
    # --- routing: the cheap path must stay cheap ---------------------------
    Case("greeting", "hi", "direct",
         "A greeting must never reach the vector store or an Opus call."),
    Case("capability", "what can you do?", "direct",
         "Self-description needs no data."),
    Case("concept_only", "what does an inverted yield curve mean?", "direct",
         "A concept question is answerable without reading any rates."),

    # --- routing: ask rather than guess -------------------------------------
    Case("vague_stress", "i want to run a stress test", "clarify",
         "Which scenario and which book decide the entire result."),
    Case("vague_var", "calculate VaR", "clarify",
         "Portfolio, confidence and horizon are all missing."),
    Case("vague_table", "show me a table", "clarify",
         "A table of what? Guessing wastes the expensive path."),

    # --- the core case: grounded reduction ----------------------------------
    Case("var_10k_rows",
         "Give me 10,000 rows of Treasury yield data with observation_date, "
         "rate_percent, quote_basis, cusip, issuer_name and settlement_date. "
         "I need it to compute 10-day 99% historical VaR on the book.",
         "data_request",
         "The headline case: the window must come from the corpus with a quote, "
         "and three impossible fields must be refused, not filled.",
         expect_grounded=True, expect_rows=250,
         impossible_fields=["cusip", "issuer_name", "settlement_date"],
         expect_citations=True, max_sentences=4),

    Case("es_window",
         "I need data for a 97.5% expected shortfall calculation.",
         "data_request",
         "ES shares the VaR window; the corpus states it, so it must be grounded.",
         expect_grounded=True, expect_rows=250, expect_citations=True),

    Case("dv01_single_curve",
         "Give me the data to compute DV01 on the demo book.",
         "data_request",
         "A sensitivity reads one curve. Asking for history would be the wrong "
         "shape, and the corpus says so.",
         expect_grounded=True, expect_rows=1, expect_citations=True),

    Case("curve_snapshot",
         "Show me the nominal Treasury yield curve as a table.",
         "data_request",
         "A snapshot is one observation date across tenors.",
         expect_grounded=True, expect_rows=1, expect_citations=True),

    # --- refusal ------------------------------------------------------------
    Case("counterparty_out_of_scope",
         "Compute CVA on our counterparty exposures.",
         "data_request",
         "There is no counterparty data. The system must say so rather than "
         "improvise a number from rates.",
         expect_citations=True),

    Case("instrument_detail",
         "Give me the CUSIP and issuer for every bond in the 10-year sector.",
         "data_request",
         "A par yield curve holds no instrument records; nothing may be "
         "substituted for them.",
         impossible_fields=["cusip", "issuer"], expect_citations=True),

    # --- specific enough to act on -----------------------------------------
    Case("slope_specific", "What is the 2s10s slope today?", "data_request",
         "Named metric, sensible default date - no clarification owed.",
         expect_citations=True),
]


def by_id(case_id: str) -> Case:
    for case in CASES:
        if case.id == case_id:
            return case
    raise KeyError(case_id)
