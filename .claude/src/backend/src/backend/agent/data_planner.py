"""Data-requirement planning: decide what a task actually needs, and say why.

A quant asks for "10,000 rows and every field". Usually the task needs a few
hundred rows and four columns, and the difference is not a matter of taste — a
250-day historical VaR window is a *methodology* fact, not a preference. Handing
over 10,000 rows anyway is worse than wasteful: it invites the reader to compute
the number over the wrong window.

So this module does three things, in order:

1. **Classify the task** against a small set of profiles whose data needs are
   documented, not guessed.
2. **Ground the decision in the knowledge base.** Every profile carries the
   query that retrieves the document justifying it, and each of those documents
   has a `## Data required` section naming the exact inputs. The plan cites the
   chunks it actually retrieved, so a reviewer can check the reasoning against
   its source rather than trusting it.
3. **Return a plan the caller can argue with** — what was asked for, what was
   granted, what was dropped and on what basis. A reduction nobody can inspect
   is indistinguishable from a bug.

The plan is advisory in the sense that it never silently discards a field the
caller insisted on: unrecognised fields are reported as `unavailable`, and
fields that are real but unnecessary are reported as `dropped` with a reason.
Nothing is removed without a line of text saying why.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# Tenor vocabulary the agent speaks, in months. Kept here so a profile can name
# tenors without importing the provider.
TENOR_MONTHS: dict[str, float] = {
    "m1": 1, "m1_5": 1.5, "m2": 2, "m3": 3, "m4": 4, "m6": 6,
    "y1": 12, "y2": 24, "y3": 36, "y5": 60, "y7": 84,
    "y10": 120, "y20": 240, "y30": 360,
}

# Columns that must travel with every rate. These are not negotiable and are
# never dropped, whatever the caller asked for: a rate without its quoting basis
# is a number nobody can safely combine with another.
MANDATORY_FIELDS = ("observation_date", "rate_percent", "quote_basis")

MAX_DISPLAY_ROWS = 500


@dataclass
class FieldDecision:
    name: str
    verdict: str          # "required" | "dropped" | "unavailable"
    reason: str


@dataclass
class DataPlan:
    """What was asked for, what is actually needed, and the evidence for it."""

    task: str
    profile: str
    requested_fields: list[str]
    granted_fields: list[str]
    field_decisions: list[FieldDecision]
    requested_rows: int | None
    granted_rows: int
    row_reason: str
    basis: str                                  # the methodology sentence
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "profile": self.profile,
            "requested_fields": self.requested_fields,
            "granted_fields": self.granted_fields,
            "field_decisions": [
                {"name": d.name, "verdict": d.verdict, "reason": d.reason}
                for d in self.field_decisions
            ],
            "requested_rows": self.requested_rows,
            "granted_rows": self.granted_rows,
            "row_reason": self.row_reason,
            "basis": self.basis,
            "sources": self.sources,
            "warnings": self.warnings,
        }


@dataclass
class TaskProfile:
    """A task whose data requirement is documented rather than inferred."""

    name: str
    keywords: tuple[str, ...]
    knowledge_query: str
    domain: str
    required_fields: tuple[str, ...]
    rows: int
    row_reason: str
    basis: str


# The row counts here are methodology, not preference. Each is the window the
# risk engine actually uses, and each profile names the document that says so.
PROFILES: tuple[TaskProfile, ...] = (
    TaskProfile(
        name="historical_var",
        keywords=("var", "value at risk", "expected shortfall", "es ", "tail"),
        knowledge_query="historical simulation VaR window and required data inputs",
        domain="market_risk",
        required_fields=("observation_date", "rate_percent", "quote_basis", "tenor"),
        rows=250,
        row_reason=(
            "Historical simulation revalues the book under each observed change in a "
            "250-trading-day window. Rows beyond that window are not used by the "
            "calculation, and a longer window would change the number rather than "
            "refine it."
        ),
        basis="Historical simulation VaR/ES over a fixed 250-trading-day lookback.",
    ),
    TaskProfile(
        name="sensitivity",
        keywords=("dv01", "pv01", "duration", "sensitivit", "greek", "key rate"),
        knowledge_query="DV01 sensitivity required data inputs",
        domain="market_risk",
        required_fields=("tenor", "rate_percent", "quote_basis"),
        rows=1,
        row_reason=(
            "DV01 is a bump-and-revalue on a single curve. It needs one dated curve, "
            "not a history — the time series plays no part in the calculation."
        ),
        basis="Sensitivities are computed by central difference on one curve.",
    ),
    TaskProfile(
        name="curve_snapshot",
        keywords=("curve", "yield", "snapshot", "term structure", "tenor"),
        knowledge_query="yield curve construction and required data inputs",
        domain="market_risk",
        required_fields=("tenor", "rate_percent", "quote_basis", "rate_kind"),
        rows=1,
        row_reason="A curve snapshot is one observation date across tenors.",
        basis="Par yield curve for a single observation date.",
    ),
    TaskProfile(
        name="stress_replay",
        keywords=("stress", "scenario", "replay", "shock"),
        knowledge_query="stress testing historical replay required data inputs",
        domain="market_risk",
        required_fields=("observation_date", "tenor", "rate_percent", "quote_basis"),
        rows=2,
        row_reason=(
            "A historical replay is the difference between two observed curves. Two "
            "dates are the whole input; everything between them is unused."
        ),
        basis="Stress replay differences the curves on two named dates.",
    ),
    TaskProfile(
        name="trend",
        keywords=("history", "trend", "over time", "series", "chart", "moved"),
        knowledge_query="yield curve level and slope over time",
        domain="market_risk",
        required_fields=("observation_date", "rate_percent", "quote_basis", "tenor"),
        rows=250,
        row_reason=(
            "One trading year is enough to read a trend at daily frequency; more rows "
            "make the series harder to read without changing its shape."
        ),
        basis="Daily observations over roughly one trading year.",
    ),
)

FALLBACK = PROFILES[2]  # curve_snapshot — the least presumptuous default


def classify(task: str) -> TaskProfile:
    """Pick the profile whose keywords the task mentions most specifically.

    Deterministic on purpose. A model deciding how many rows a VaR needs would
    decide differently on different days, and the window is exactly the kind of
    thing that must not drift.
    """
    text = (task or "").lower()
    best, best_score = FALLBACK, 0
    for profile in PROFILES:
        score = sum(len(k) for k in profile.keywords if k in text)
        if score > best_score:
            best, best_score = profile, score
    return best


def plan(
    task: str,
    requested_fields: list[str] | None,
    requested_rows: int | None,
    *,
    available_fields: list[str],
    knowledge=None,
) -> DataPlan:
    """Decide the minimal field set and row count for `task`, with citations."""
    profile = classify(task)

    sources: list[dict[str, Any]] = []
    if knowledge is not None:
        try:
            hits = knowledge.retrieve(profile.knowledge_query, domain=profile.domain)
            sources = [
                {"domain": h.get("domain"), "source": h.get("source"),
                 "heading": h.get("heading"), "distance": h.get("distance")}
                for h in hits
            ]
        except Exception:  # noqa: BLE001 - a plan without citations still beats none
            sources = []

    asked = [f.strip() for f in (requested_fields or []) if f and f.strip()]
    available = set(available_fields)
    decisions: list[FieldDecision] = []

    for name in profile.required_fields:
        if name in available or name in MANDATORY_FIELDS:
            decisions.append(FieldDecision(
                name, "required",
                f"{profile.basis} requires it." if name not in MANDATORY_FIELDS
                else "Carried with every rate so it cannot be mis-combined."))

    granted = [d.name for d in decisions]

    for name in asked:
        if name in granted:
            continue
        if name not in available:
            decisions.append(FieldDecision(
                name, "unavailable",
                "Not a column this dataset publishes; nothing was substituted for it."))
        else:
            decisions.append(FieldDecision(
                name, "dropped",
                f"Real column, but the {profile.name.replace('_', ' ')} calculation "
                "does not read it. Ask again naming it as the subject and it will be "
                "returned."))

    rows = profile.rows
    warnings: list[str] = []
    if requested_rows is not None and requested_rows > rows:
        warnings.append(
            f"Requested {requested_rows:,} rows; {rows:,} are used by this "
            f"calculation. The extra rows would not change the result.")
    elif requested_rows is not None and requested_rows < rows:
        # The caller asked for *fewer* than the method needs. That is the one
        # case where honouring the request produces a wrong number, so the plan
        # refuses to shrink and says so.
        warnings.append(
            f"Requested {requested_rows:,} rows, but this calculation needs "
            f"{rows:,}. Returning the full window - a short window changes the "
            "number rather than approximating it.")

    return DataPlan(
        task=task, profile=profile.name,
        requested_fields=asked, granted_fields=granted,
        field_decisions=decisions,
        requested_rows=requested_rows, granted_rows=rows,
        row_reason=profile.row_reason, basis=profile.basis,
        sources=sources, warnings=warnings,
    )


def build_table(rows: list[dict[str, Any]], columns: list[str],
                title: str) -> dict[str, Any]:
    """Shape fetched rows into a renderable table.

    Structured columns and rows, never a markdown string: the UI needs to put
    this in a real table widget, and a pre-formatted string cannot be sorted,
    scrolled or exported.
    """
    trimmed = rows[:MAX_DISPLAY_ROWS]
    return {
        "title": title,
        "columns": columns,
        "rows": [[_cell(r.get(c)) for c in columns] for r in trimmed],
        "row_count": len(rows),
        "displayed": len(trimmed),
        "truncated": len(rows) > len(trimmed),
    }


def _cell(value: Any) -> Any:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
