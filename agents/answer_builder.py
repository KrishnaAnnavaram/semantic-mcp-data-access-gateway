"""The reply, as sections rather than as one paragraph.

A senior quant reviewing a risk figure wants to know six things at once: what the
answer is, what it was computed *over*, what the numbers are, what the data
looked like, how it was calculated, and what not to trust about it. Three
sentences of prose can carry the first and gesture at the rest. It cannot be
skimmed, cannot be diffed against yesterday's run, and buries the caveat that
matters in a subordinate clause.

So the orchestrator's reply is assembled here into a small, typed document:

    StructuredAnswer
      headline      one or two sentences - the executive answer
      shape         which document this is, which decides the sections
      sections[]    scope | metrics | table | chart | interpretation |
                    methodology | assumptions | caveats | sources

**Assembled from facts, not generated.** Every section below is built from
material already established elsewhere in the turn - the agreed requirement, the
negotiation outcome, the calculation the risk engine returned, the table's
provenance, the validation verdict, the citations. Only two fields are prose the
model wrote (`headline` and `interpretation`), and both come from the single
`reflect` call that was already being made. Nothing here asks a model to list
metrics or restate parameters, because a model asked to restate a number will
eventually restate it differently, and a figure that disagrees with the table
beside it is worse than no figure.

**The shape adapts.** A rate lookup gets three sections; a stress test gets the
scenario, the baseline, the stressed result and the delta. Forcing ten headings
onto "what is the 10-year yield" would bury a one-line answer under nine empty
ones, so `_SHAPES` decides which sections a given turn may even have, and any
section with nothing in it is dropped rather than rendered empty.

**`answer` stays a string.** The plain-text reply is unchanged and still carries
the whole executive answer, so a client that ignores `structured` is not
degraded - it simply does not get the extra structure.
"""

from __future__ import annotations

from typing import Any

from agents.redaction import humanise

#: Which document a turn produces. The shape decides the sections, and a
#: question that changes shape changes what the reader is shown - a stress test
#: is not a smaller analysis, it is a different report.
SHAPE_DIRECT = "direct"
SHAPE_CLARIFICATION = "clarification"
SHAPE_REFUSAL = "refusal"
SHAPE_LOOKUP = "lookup"
SHAPE_ANALYSIS = "analysis"
SHAPE_STRESS = "stress"

#: Section ids each shape may carry, in reading order. A section not listed here
#: is never built for that shape, even when the material for it exists: the
#: point of the shape is that it decides what this kind of answer is *for*.
_SHAPES: dict[str, tuple[str, ...]] = {
    SHAPE_DIRECT: ("answer",),
    SHAPE_CLARIFICATION: ("answer", "missing"),
    SHAPE_REFUSAL: ("answer", "scope", "sources"),
    SHAPE_LOOKUP: ("answer", "scope", "table", "chart", "caveats", "sources"),
    SHAPE_ANALYSIS: ("answer", "scope", "metrics", "table", "chart",
                     "interpretation", "methodology", "assumptions", "caveats",
                     "sources"),
    SHAPE_STRESS: ("answer", "scenario", "metrics", "table", "chart",
                   "interpretation", "methodology", "assumptions", "caveats",
                   "sources"),
}

#: Calculations that produce a stress report rather than an analysis.
_STRESS_TOOLS = frozenset({
    "run_stress", "run_rate_stress", "run_key_rate_stress", "run_shock_ladder",
    "run_stress_matrix", "run_historical_stress", "run_reverse_stress",
    "find_worst_historical_stresses", "compute_stress_contributions",
    "compute_stress_thresholds", "find_limit_breach_stress",
})

#: Result keys that describe the calculation rather than report a figure. They
#: belong in Scope or Methodology, not in the metric tiles, and promoting them
#: would put "USD per basis point, full revaluation" in a slot sized for a
#: number.
_NOT_A_METRIC = frozenset({
    "units", "unit", "valuation_date", "curve_date", "as_of_date",
    "portfolio_id", "portfolio", "scenario_id", "method", "methodology",
    "basis", "currency", "note", "notes", "warning", "warnings", "source",
    "classification", "observation_window", "start_date", "end_date",
})

#: Where a currency figure should be recognisable as one. Used only for
#: display; the value itself is never rescaled.
_MONEY_HINTS = ("dv01", "var", "es", "loss", "pnl", "p_and_l", "value",
                "price", "notional", "exposure", "carry", "roll", "limit",
                "shortfall", "gain")


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _fmt_number(value: float) -> str:
    """A number a human can read, without changing what it is.

    No rounding that loses information a reader would act on: four significant
    decimals for a rate-sized quantity, thousands separators above one, and the
    raw repr for anything that would otherwise be shown as `0.00`.
    """
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if magnitude >= 1:
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if magnitude == 0:
        return "0"
    if magnitude >= 0.0001:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return repr(value)


def _metric(name: str, value: Any, units: str = "") -> dict[str, Any] | None:
    if isinstance(value, bool):
        return {"label": humanise(name), "value": "yes" if value else "no"}
    if isinstance(value, (int, float)):
        money = any(hint in name.lower() for hint in _MONEY_HINTS)
        return {"label": humanise(name), "value": _fmt_number(float(value)),
                "unit": units if money and units else "",
                "numeric": float(value)}
    if isinstance(value, str) and value.strip():
        return {"label": humanise(name), "value": value.strip()[:120]}
    return None


def _metrics_from(calculation: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Top-level figures the risk engine reported, in the order it reported them.

    Nested structures (a key-rate ladder, a scenario matrix) are deliberately
    not flattened into tiles: they are tables, and a table squeezed into a row
    of metric cards is unreadable. They stay in the calculation payload, which
    the Data view already renders in full.
    """
    result = (calculation or {}).get("result")
    if not isinstance(result, dict):
        return []
    units = str(result.get("units") or result.get("unit") or "")
    metrics: list[dict[str, Any]] = []
    for name, value in result.items():
        if name in _NOT_A_METRIC or not _is_scalar(value):
            continue
        entry = _metric(name, value, units)
        if entry is not None:
            metrics.append(entry)
    return metrics[:8]


def _scope_items(requirement: Any, result: dict[str, Any] | None,
                 calculation: dict[str, Any] | None) -> list[dict[str, str]]:
    """What the answer was computed over - the half of a figure that is not the number.

    Every entry is read from what was actually agreed or actually returned. A
    parameter the user asked for but the engine did not honour is not shown
    here: the arguments the calculation reports are the ones it used, and
    showing the requested value instead is how a one-day figure ends up
    labelled ten-day.
    """
    items: list[dict[str, str]] = []
    table = (result or {}).get("table") or {}
    provenance = table.get("provenance") or {}
    arguments = (calculation or {}).get("arguments") or {}
    engine = (calculation or {}).get("result") or {}

    def add(label: str, value: Any) -> None:
        if value is None or value == "" or value == []:
            return
        items.append({"label": label, "value": str(value)})

    add("Portfolio", arguments.get("portfolio_id"))
    observed = (provenance.get("curve_date")
                or engine.get("valuation_date")
                or arguments.get("curve_date"))
    add("As-of date", observed)
    if provenance.get("observed_from") or provenance.get("observed_to"):
        add("Observation window",
            f"{provenance.get('observed_from') or '?'} to "
            f"{provenance.get('observed_to') or '?'}")
    elif requirement is not None and not requirement.temporal.is_empty:
        add("Observation window", requirement.temporal.describe())
    add("Curve", provenance.get("rate_kind")
        or (requirement.curve_family if requirement is not None else None))
    add("Quoting basis", provenance.get("quote_basis"))
    if requirement is not None and requirement.tenors:
        add("Tenors", ", ".join(requirement.tenors[:12]))
    add("Observations read", arguments.get("trading_days")
        or (requirement.rows if requirement is not None else None))
    add("Confidence level", arguments.get("confidence_level")
        or engine.get("confidence_level"))
    add("Holding period (days)", arguments.get("horizon_days")
        or engine.get("horizon_days"))
    add("Scenario", arguments.get("scenario_id") or arguments.get("scenario")
        or engine.get("scenario_id"))
    add("Classification", provenance.get("classification"))
    return items


def _caveats(requirement: Any, result: dict[str, Any] | None,
             validation: Any) -> list[str]:
    """Everything a reader should not take on trust, gathered in one place.

    These were already produced - by the loader's window note, by the
    negotiation's warnings, by the field verdicts, by result validation - and
    were previously scattered across a panel, a warning list and one clause of
    the prose. A caveat that has to be found is a caveat that is not read.
    """
    notes: list[str] = []
    for note in (result or {}).get("notes") or []:
        if isinstance(note, str) and note.strip():
            notes.append(note.strip())
    if requirement is not None:
        if requirement.rows is not None and not requirement.grounded:
            notes.append(
                "The observation window is not grounded in a citation from the "
                "knowledge corpus, so it is a sample rather than a methodology "
                "figure.")
        unavailable = [n.name for n in requirement.field_notes
                       if n.verdict == "unavailable"]
        if unavailable:
            notes.append(
                "Not published by this source, and nothing was substituted: "
                + ", ".join(humanise(name) for name in unavailable) + ".")
        for warning in requirement.warnings:
            if isinstance(warning, str) and warning.strip():
                notes.append(warning.strip())
    if validation is not None:
        for mismatch in getattr(validation, "mismatches", []) or []:
            notes.append(str(mismatch))
    seen: set[str] = set()
    unique = []
    for note in notes:
        if note not in seen:
            seen.add(note)
            unique.append(note)
    return unique[:8]


def _methodology(requirement: Any, calculation: dict[str, Any] | None,
                 negotiation: Any) -> list[str]:
    lines: list[str] = []
    tool = (calculation or {}).get("tool")
    if tool:
        lines.append(f"Method: {humanise(str(tool))}, run through the "
                     "deterministic workflow layer over the MCP risk engine.")
    engine = (calculation or {}).get("result") or {}
    units = engine.get("units") or engine.get("unit")
    if units:
        lines.append(f"Units: {units}.")
    if requirement is not None and requirement.row_quote:
        lines.append(f'Observation window, quoted from the corpus: '
                     f'"{requirement.row_quote}"')
    if negotiation is not None and getattr(negotiation, "held", False):
        lines.append(
            f"Agreed with the data layer in {negotiation.rounds_used} "
            f"round(s): {negotiation.outcome}")
    return lines[:6]


def _shape_for(route: str, requirement: Any, result: dict[str, Any] | None,
               calculation: dict[str, Any] | None) -> str:
    if route == "direct":
        return SHAPE_DIRECT
    if route == "clarify":
        return SHAPE_CLARIFICATION
    if requirement is not None and not requirement.answerable:
        return SHAPE_REFUSAL
    tool = str((calculation or {}).get("tool") or "")
    if tool in _STRESS_TOOLS:
        return SHAPE_STRESS
    if calculation and (calculation.get("result") or calculation.get("error")):
        return SHAPE_ANALYSIS
    if result and (result.get("table") or {}).get("columns"):
        return SHAPE_LOOKUP
    return SHAPE_REFUSAL if not result else SHAPE_LOOKUP


def build(*, route: str, answer: str, requirement: Any = None,
          negotiation: Any = None, result: dict[str, Any] | None = None,
          validation: Any = None, citations: list[dict[str, Any]] | None = None,
          interpretation: str = "", missing: list[dict[str, Any]] | None = None,
          request_id: str = "", langsmith_url: str | None = None,
          trace_id: str | None = None) -> dict[str, Any]:
    """Assemble the structured reply for one turn.

    `answer` is the prose the orchestrator wrote and remains the headline
    verbatim - this function never rewrites it, so the structured document and
    the plain-text reply can never disagree about what the answer was.
    """
    calculation = (result or {}).get("calculation")
    shape = _shape_for(route, requirement, result, calculation)
    allowed = _SHAPES[shape]
    sections: list[dict[str, Any]] = []

    def section(sid: str, title: str, kind: str, **payload: Any) -> None:
        if sid not in allowed:
            return
        # An empty section is worse than an absent one: it tells the reader a
        # heading exists and that this system had nothing to put under it.
        # `table_index` is checked for presence rather than truth, because
        # index 0 is the first table and is exactly the case that matters.
        has_content = ("table_index" in payload
                       or any(payload.get(key) for key in
                              ("body", "items", "metrics", "chart")))
        if not has_content:
            return
        sections.append({"id": sid, "title": title, "kind": kind, **payload})

    section("answer", "Executive answer", "text", body=answer)

    if missing:
        section("missing", "What I need", "list",
                items=[m.get("question") or m.get("name") for m in missing
                       if isinstance(m, dict)])

    scope = _scope_items(requirement, result, calculation)
    section("scope", "Analysis scope", "keyvalue", items=scope)
    section("scenario", "Scenario", "keyvalue", items=scope)

    section("metrics", "Key metrics", "metrics",
            metrics=_metrics_from(calculation))

    table = (result or {}).get("table") or {}
    if table.get("columns"):
        section("table", table.get("title") or "Results", "table",
                table_index=0,
                body=(f"{table.get('row_count', 0):,} row(s) x "
                      f"{len(table.get('columns') or [])} column(s)."))
        section("chart", "Chart", "chart", chart={"table_index": 0})

    section("interpretation", "Interpretation", "text", body=interpretation)
    section("methodology", "Methodology", "list",
            items=_methodology(requirement, calculation, negotiation))
    section("assumptions", "Assumptions", "list",
            items=list(getattr(requirement, "assumptions", []) or [])[:6])
    section("caveats", "Data quality and caveats", "list",
            items=_caveats(requirement, result, validation))

    sources = [str(c.get("label") or "") for c in (citations or [])
               if isinstance(c, dict) and c.get("label")]
    section("sources", "Sources and lineage", "list", items=sources[:8])

    return {
        "shape": shape,
        "headline": answer,
        "sections": sections,
        "lineage": {
            "request_id": request_id,
            "trace_id": trace_id or "",
            "langsmith_url": langsmith_url or "",
            "calculation": str((calculation or {}).get("tool") or ""),
            "validation": (getattr(validation, "verdict", "")
                           if validation is not None else ""),
        },
    }
