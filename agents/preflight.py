"""The requirement completeness gate: cheap validation before expensive intelligence.

A question that cannot be answered without a detail nobody supplied used to cost
the full path anyway - four Qdrant queries, a reasoning-model call to derive a
requirement, a capability read over A2A, and up to five negotiation rounds of two
model calls each - before anything noticed that the user had not said which
period to compare. That is minutes of latency and a fistful of reasoning tokens
spent to discover a missing date.

So the domain expert now answers a cheaper question first:

    question ─► deterministic extraction ─► intent schema ─► complete?
                                                              │
                                              ┌───────────────┴────────────┐
                                              ▼                            ▼
                                        continue                 ClarificationRequest
                                    (retrieve, derive,            (to the ORCHESTRATOR,
                                     negotiate, execute)           which asks the user)

**It runs on regular expressions and a lexicon, not on a model.** Deciding
whether `2026-08-20` is a date does not need a frontier model, and a model call
to find out would reintroduce most of the cost this gate exists to avoid. The
whole check is sub-millisecond.

**It is deliberately reluctant to ask.** This is a tool for senior quants, and a
question with a legitimate system default is not a missing requirement: a
confidence level, a holding period, an observation window and an as-of date all
have documented defaults, so asking for them would interrupt someone to tell
them something they already know. Only fields with **no defensible default** can
block - a comparison with no second date, a stress test with no scenario, a
reverse stress with no target loss, a subject-less request. Everything else
proceeds and the answer states which default it used.

    "Show me the 10Y Treasury yield."       -> complete (latest observation)
    "10-day 99% VaR on the book."           -> complete
    "Calculate VaR."                        -> complete for this gate; the
                                               orchestrator's own router already
                                               refuses a compute request with no
                                               target, and two agents asking the
                                               same question is worse than one.
    "Compare the curve and show the moves." -> INCOMPLETE: which period?
    "Run a stress test on the demo book."   -> INCOMPLETE: which scenario?

**The expert never speaks to the user.** The verdict travels to the orchestrator
as structured data - the intent, the missing field names, the questions, and why
they matter - and the orchestrator is what turns that into a sentence with
clickable options. Nothing in this module writes to a terminal or composes
user-facing prose beyond the question text the orchestrator is free to rewrite.
"""

from __future__ import annotations

import calendar
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("agents.preflight")

#: How many questions one clarification may carry. Three is the default because
#: a fourth is almost always a field with a default that should not have been
#: asked about at all; five is the hard ceiling, because past that the user is
#: filling in a form rather than having a conversation.
DEFAULT_MAX_QUESTIONS = 3
HARD_MAX_QUESTIONS = 5

#: How many times in a row this gate may stop a conversation before it proceeds
#: on defaults and says so. One ask is a good trade; an unbounded sequence of
#: them is the user-facing twin of an unbounded agent loop, and the third
#: question in a row is how a user learns to stop using a system.
DEFAULT_MAX_ROUNDS = 2


def max_questions() -> int:
    try:
        value = int(os.environ.get("PREFLIGHT_MAX_QUESTIONS", "").strip()
                    or DEFAULT_MAX_QUESTIONS)
    except ValueError:
        return DEFAULT_MAX_QUESTIONS
    return max(1, min(HARD_MAX_QUESTIONS, value))


def max_rounds() -> int:
    try:
        value = int(os.environ.get("PREFLIGHT_MAX_ROUNDS", "").strip()
                    or DEFAULT_MAX_ROUNDS)
    except ValueError:
        return DEFAULT_MAX_ROUNDS
    return max(0, min(4, value))


def enabled() -> bool:
    """The gate can be switched off without touching the pipeline.

    Present because a behaviour change this visible needs a way back that does
    not involve a deploy: `PREFLIGHT_ENABLED=false` restores exactly the old
    flow, which is the difference between a rollout and a commitment.
    """
    raw = os.environ.get("PREFLIGHT_ENABLED", "").strip().lower()
    return raw not in {"false", "0", "no", "off"}


# --- what the deterministic layer can find -----------------------------------

_MONTHS = {name.lower(): index
           for index, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): index
                for index, name in enumerate(calendar.month_abbr) if name})

_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_US_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_YEAR = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{4})\b",
    re.IGNORECASE)
_BARE_YEAR = re.compile(r"\b(19[7-9]\d|20[0-4]\d)\b")

#: "last 30 days", "past six months", "previous 2 years", "trailing 250 days".
_RELATIVE_PERIOD = re.compile(
    r"\b(?:last|past|previous|trailing|prior|recent)\s+"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve)?\s*"
    r"(day|week|month|quarter|year)s?\b", re.IGNORECASE)

_NAMED_PERIOD = re.compile(
    r"\b(ytd|year[- ]to[- ]date|month[- ]to[- ]date|this year|last year|"
    r"this month|last month|this quarter|last quarter|today|yesterday|"
    r"latest|most recent|current)\b", re.IGNORECASE)

_SINCE = re.compile(r"\b(?:since|from|after)\s+(\d{4}(?:-\d{1,2}-\d{1,2})?)\b",
                    re.IGNORECASE)
_BETWEEN = re.compile(r"\bbetween\b.*?\band\b", re.IGNORECASE | re.DOTALL)

#: "10Y", "2 year", "30-year", "3 month", "6mo". Deliberately not matching a
#: bare number: "compare 2 and 10" is a tenor pair only in context, and this
#: layer does not guess.
_TENOR = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(y|yr|yrs|year|years|m|mo|mos|month|months|"
    r"w|wk|week|weeks|d|day|days)\b", re.IGNORECASE)
#: "2s10s", "5s30s" - a spread names both of its legs, so it is a period-free
#: subject that needs no tenor question.
_SPREAD = re.compile(r"\b(\d+)s(\d+)s\b", re.IGNORECASE)

#: A confidence level, written as a percentage or as a fraction.
#:
#: The trailing boundary is per-alternative on purpose. A single `\b` after the
#: whole group never matches the `%` form: `%` is a non-word character and so is
#: the space after it, so there is no boundary between them and `99% VaR` was
#: silently read as having no confidence level at all. The word forms keep their
#: boundary so `percentage` does not match `percent`.
_CONFIDENCE = re.compile(
    r"\b(\d{2}(?:\.\d+)?)\s*(?:%|percent\b|pct\b)|\b(0\.9\d+)\b", re.IGNORECASE)
_HORIZON = re.compile(r"\b(\d+)\s*[- ]?\s*day\b", re.IGNORECASE)
#: An amount of money, in the four forms a person actually writes one. A bare
#: number is deliberately not enough: "10 year" and "2008" are numbers, and
#: reading either as a loss limit would satisfy a requirement nobody stated.
#: So it takes a currency symbol, a magnitude suffix, thousands separators, or
#: five digits - and a bare four-digit year is excluded by the digit floor.
_MONEY = re.compile(
    r"[$£€]\s?\d[\d,]*(?:\.\d+)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s*(?:k|m|mm|bn|b|million|billion)\b"
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\b\d{5,}(?:\.\d+)?\b", re.IGNORECASE)

#: Portfolio references. One book exists (`SYNTHETIC_DEMO`), so naming any of
#: these settles the target; the gate never asks *which* portfolio when there is
#: only one to choose.
_PORTFOLIO_WORDS = (
    "portfolio", "book", "demo book", "synthetic_demo", "the book", "my book",
    "my portfolio", "positions", "holdings", "trades",
)

_CURVE_FAMILY = {
    "nominal": ("nominal", "par yield", "treasury yield", "bc_"),
    "real": ("real", "tips", "inflation-linked", "inflation linked",
             "real yield"),
    "bill": ("bill", "discount rate", "coupon equivalent"),
}

#: Restated here rather than imported from `domain_expert_agent`, which imports
#: heavy machinery this gate must stay clear of - the whole point is that the
#: check costs nothing. `tests/test_preflight.py` fails if the two disagree.
SCENARIO_WORDS: tuple[str, ...] = (
    "parallel", "parallel_up", "parallel_down", "twist", "bear_steepener",
    "bull_steepener", "bear_flattener", "bull_flattener", "belly_selloff",
    "belly_rally", "wings_selloff", "wings_rally",
)
CRISIS_WORDS: tuple[str, ...] = (
    "1994_bond_selloff", "2008_gfc_lehman", "2013_taper_tantrum",
    "2020_covid_shock", "2022_fed_tightening", "2023_regional_bank_stress",
)
#: How a human names those crises. A user says "the 2008 crisis", never
#: `2008_GFC_LEHMAN`, and a gate that only recognised the identifier would ask
#: for a scenario the user had already given.
CRISIS_PHRASES = (
    "gfc", "lehman", "global financial crisis", "taper tantrum", "covid",
    "pandemic", "fed tightening", "regional bank", "bond selloff", "svb",
)


@dataclass
class ExtractedFacts:
    """What the deterministic layer could find in the user's own words."""

    dates: list[str] = field(default_factory=list)
    years: list[str] = field(default_factory=list)
    has_period: bool = False
    period_phrase: str = ""
    tenors: list[str] = field(default_factory=list)
    has_spread: bool = False
    confidence_level: float | None = None
    horizon_days: int | None = None
    has_portfolio: bool = False
    curve_family: str = ""
    scenario: str = ""
    has_amount: bool = False
    shock_bp: float | None = None

    @property
    def date_count(self) -> int:
        """Distinct anchors in time the user actually named."""
        return len({*self.dates, *self.years})

    @property
    def has_when(self) -> bool:
        return bool(self.dates or self.years or self.has_period)

    def as_dict(self) -> dict[str, Any]:
        return {"dates": self.dates, "years": self.years,
                "has_period": self.has_period,
                "period_phrase": self.period_phrase, "tenors": self.tenors,
                "has_spread": self.has_spread,
                "confidence_level": self.confidence_level,
                "horizon_days": self.horizon_days,
                "has_portfolio": self.has_portfolio,
                "curve_family": self.curve_family, "scenario": self.scenario,
                "has_amount": self.has_amount, "shock_bp": self.shock_bp}


def extract(text: str) -> ExtractedFacts:
    """Pull the deterministically-decidable facts out of a question.

    Everything here is a fact about the *string*, never an interpretation of it.
    Whether "2020" means the calendar year or a rate of 2020 basis points is a
    semantic question; whether the characters `2020` are present is not, and
    only the second kind is decided here.
    """
    facts = ExtractedFacts()
    lowered = (text or "").lower()

    for year, month, day in _ISO_DATE.findall(text or ""):
        facts.dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    for month, day, year in _US_DATE.findall(text or ""):
        facts.dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    for name, year in _MONTH_YEAR.findall(text or ""):
        index = _MONTHS.get(name.lower().rstrip("."))
        if index:
            facts.dates.append(f"{int(year):04d}-{index:02d}")
    # A year already inside a full date is not a second anchor in time.
    consumed = " ".join(facts.dates)
    for year in _BARE_YEAR.findall(text or ""):
        if year not in consumed:
            facts.years.append(year)

    relative = _RELATIVE_PERIOD.search(text or "")
    named = _NAMED_PERIOD.search(text or "")
    since = _SINCE.search(text or "")
    between = _BETWEEN.search(text or "")
    if relative or named or since or between:
        facts.has_period = True
        match = relative or named or since or between
        facts.period_phrase = (match.group(0) or "").strip()

    facts.has_spread = bool(_SPREAD.search(text or ""))
    for value, unit in _TENOR.findall(text or ""):
        unit = unit.lower()
        # "10-day VaR" and "the last 30 days" are horizons and windows, not
        # points on a curve. Treating them as tenors made a VaR question look
        # as though it had already named its maturities.
        if unit.startswith(("d", "w")):
            continue
        suffix = "Y" if unit.startswith("y") else "M"
        number = value.rstrip("0").rstrip(".") if "." in value else value
        facts.tenors.append(f"{number}{suffix}")

    confidence = _CONFIDENCE.search(text or "")
    if confidence:
        percent, fraction = confidence.group(1), confidence.group(2)
        if fraction:
            facts.confidence_level = float(fraction)
        elif percent:
            value = float(percent) / 100.0
            # Only the range a confidence level lives in. "up 50%" is not one.
            if 0.80 <= value < 1.0:
                facts.confidence_level = value

    horizon = _HORIZON.search(text or "")
    if horizon:
        days = int(horizon.group(1))
        if 1 <= days <= 260:
            facts.horizon_days = days

    facts.has_portfolio = any(word in lowered for word in _PORTFOLIO_WORDS)
    for family, markers in _CURVE_FAMILY.items():
        if any(marker in lowered for marker in markers):
            facts.curve_family = family
            break

    for word in (*SCENARIO_WORDS, *CRISIS_WORDS):
        if word.replace("_", " ") in lowered or word in lowered:
            facts.scenario = word
            break
    if not facts.scenario:
        for phrase in CRISIS_PHRASES:
            if phrase in lowered:
                facts.scenario = phrase
                break

    facts.has_amount = bool(_MONEY.search(text or ""))
    shock = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:bp|bps|basis points?)\b",
                      text or "", re.IGNORECASE)
    if shock:
        facts.shock_bp = float(shock.group(1))
    return facts


# --- what each kind of question actually requires ----------------------------

#: Keyword sets that decide the intent, tested in this order. The first match
#: wins, so the more specific intents come first: a reverse stress mentions
#: "stress", and a limit breach mentions both "stress" and "limit".
_INTENT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reverse_stress", ("reverse stress", "what shock would", "what move would",
                        "how big a move", "what rate move", "break the book")),
    ("limit_check", ("limit", "breach", "utilisation", "utilization",
                     "within appetite", "risk appetite")),
    ("backtest", ("backtest", "back-test", "exception rate", "kupiec")),
    ("stress_test", ("stress", "scenario", "shock", "crisis", "what if",
                     "what-if")),
    ("var", ("var", "value at risk", "value-at-risk", "expected shortfall",
             "cvar", "tail loss")),
    ("dv01", ("dv01", "pv01", "key rate", "key-rate", "sensitivity",
              "sensitivities", "duration", "convexity", "bpv")),
    ("attribution", ("attribution", "p&l", "pnl", "carry", "roll-down",
                     "rolldown", "roll down")),
    ("pricing", ("price", "value the", "worth", "valuation", "present value",
                 "mark to market", "npv")),
    ("curve_comparison", ("compare", "comparison", "versus", " vs ", "change in",
                          "changed", "moved", "movement", "moves", "shift",
                          "difference between", "widened", "steepened",
                          "flattened", "biggest mover")),
    ("rate_history", ("history", "historical", "over time", "time series",
                      "trend", "evolution", "volatility", "since", "during")),
    ("curve_snapshot", ("curve", "yield", "rate", "slope", "spread",
                        "term structure", "tenor", "maturity")),
    ("methodology", ("how do i", "how would i", "what data", "which data",
                     "what inputs", "which calculation", "what is the method",
                     "methodology", "how is", "explain")),
)


@dataclass(frozen=True)
class FieldSpec:
    """One thing an intent needs, and whether the system may decide it alone.

    `defaultable` is the field that keeps this gate usable. A parameter with a
    documented default is never a reason to interrupt someone: the answer states
    which default it used, and the user can override it in their next sentence.
    Only a field where no default is defensible - a scenario, a comparison
    window, a target loss - is allowed to stop the turn.
    """

    name: str
    question: str
    reason: str
    defaultable: bool = False
    #: What the orchestrator should offer as clickable choices, when the answer
    #: comes from a list the data layer holds. Empty means free text.
    options_from: str = ""


#: Per-intent requirements. Everything absent from a list is, by construction,
#: something this system can decide for itself.
_REQUIREMENTS: dict[str, tuple[FieldSpec, ...]] = {
    "curve_comparison": (
        FieldSpec(
            "comparison_period",
            "Which dates or period should I compare?",
            "A comparison needs two points in time; with only one, there is "
            "nothing to difference.",
            options_from="periods"),
    ),
    "stress_test": (
        FieldSpec(
            "scenario",
            "Which scenario should I run?",
            "A stress result is defined by its scenario, and choosing one for "
            "you would put a number under a shock you never asked for.",
            options_from="scenarios"),
    ),
    "reverse_stress": (
        FieldSpec(
            "target_loss",
            "What loss level should I solve back from?",
            "A reverse stress searches for the move that produces a stated "
            "loss; without the loss there is nothing to solve for."),
    ),
    "limit_check": (
        FieldSpec(
            "limit_amount",
            "What limit should I test against?",
            "A breach is defined relative to a limit, and this system holds no "
            "limit framework of its own to read one from."),
    ),
    "rate_history": (
        FieldSpec(
            "observation_period", "Which period should I cover?",
            "A history is a window; the knowledge base states one for a "
            "methodology, but a plain history request has no default length.",
            defaultable=True, options_from="periods"),
    ),
    "var": (
        FieldSpec("portfolio", "Which portfolio?",
                  "A loss figure is a property of a book.", defaultable=True),
        FieldSpec("confidence_level", "Which confidence level?",
                  "Documented default applies.", defaultable=True),
        FieldSpec("horizon_days", "Which holding period?",
                  "Documented default applies.", defaultable=True),
    ),
    "dv01": (
        FieldSpec("portfolio", "Which portfolio or instrument?",
                  "A sensitivity is a property of a position.",
                  defaultable=True),
    ),
}

#: Intents with nothing that can block. Listed rather than left to fall through
#: so that adding an intent is a deliberate decision about whether it may ever
#: stop a turn.
_NEVER_BLOCKS = frozenset({"curve_snapshot", "methodology", "pricing",
                           "attribution", "backtest", "unknown"})


def classify_intent(text: str) -> str:
    lowered = f" {(text or '').lower()} "
    for intent, markers in _INTENT_MARKERS:
        if any(marker in lowered for marker in markers):
            return intent
    return "unknown"


@dataclass
class MissingField:
    name: str
    question: str
    reason: str
    options_from: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "question": self.question,
                "reason": self.reason, "options_from": self.options_from}


@dataclass
class CompletenessVerdict:
    """The gate's answer: proceed, or ask the orchestrator to ask the user."""

    complete: bool
    intent: str
    facts: ExtractedFacts = field(default_factory=ExtractedFacts)
    missing: list[MissingField] = field(default_factory=list)
    reason: str = ""
    #: True when the gate would have asked but has already asked as often as it
    #: is allowed to. The turn proceeds, and the answer says which defaults it
    #: fell back on rather than pretending nothing was missing.
    proceeded_on_defaults: bool = False
    defaults_applied: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "complete" if self.complete else "clarification_required"

    @property
    def questions(self) -> list[str]:
        return [m.question for m in self.missing]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "complete": self.complete,
            "intent": self.intent, "facts": self.facts.as_dict(),
            "missing_fields": [m.name for m in self.missing],
            "missing": [m.as_dict() for m in self.missing],
            "questions": self.questions, "reason": self.reason,
            "proceeded_on_defaults": self.proceeded_on_defaults,
            "defaults_applied": self.defaults_applied,
        }


def _satisfied(field_name: str, facts: ExtractedFacts, text: str) -> bool:
    """Has the user already supplied this field, in any form they might use?"""
    if field_name == "comparison_period":
        # Two anchors, or one relative window ("last 30 days" is both ends).
        return facts.date_count >= 2 or facts.has_period
    if field_name == "observation_period":
        return facts.has_when
    if field_name == "scenario":
        # A named date is a scenario too. "The 2008 crisis" and "replay March
        # 2020" select a historical stress by when it happened, which is how
        # people name those events - insisting on a `crisis_id` here would ask
        # for something the user had already given in their own vocabulary.
        return (bool(facts.scenario) or facts.shock_bp is not None
                or bool(facts.dates or facts.years))
    if field_name == "target_loss":
        return facts.has_amount
    if field_name == "limit_amount":
        return facts.has_amount
    if field_name == "portfolio":
        return facts.has_portfolio
    if field_name == "confidence_level":
        return facts.confidence_level is not None
    if field_name == "horizon_days":
        return facts.horizon_days is not None
    return True


def assess(question: str, *, rounds_used: int = 0,
           already_clarified: bool = False) -> CompletenessVerdict:
    """Can this question be executed as it stands?

    `rounds_used` is how many times this gate has already stopped the current
    conversation. Past its bound the verdict is `complete` with
    `proceeded_on_defaults` set, so a user is never trapped in a question loop -
    the same discipline the elicitation retry budget applies one layer down.
    """
    facts = extract(question)
    intent = classify_intent(question)

    if not enabled():
        return CompletenessVerdict(complete=True, intent=intent, facts=facts,
                                   reason="the completeness gate is disabled")

    specs = _REQUIREMENTS.get(intent, ())
    blocking = [
        MissingField(spec.name, spec.question, spec.reason, spec.options_from)
        for spec in specs
        if not spec.defaultable and not _satisfied(spec.name, facts, question)
    ]
    defaults = [spec.name for spec in specs
                if spec.defaultable and not _satisfied(spec.name, facts, question)]

    if intent in _NEVER_BLOCKS or not blocking:
        return CompletenessVerdict(
            complete=True, intent=intent, facts=facts,
            defaults_applied=defaults,
            reason=("every field this question needs is either stated or has a "
                    "documented default"))

    if already_clarified and rounds_used >= max_rounds():
        LOGGER.info("preflight would ask for %s but has already asked %d "
                    "time(s); proceeding on defaults",
                    [m.name for m in blocking], rounds_used)
        return CompletenessVerdict(
            complete=True, intent=intent, facts=facts,
            proceeded_on_defaults=True,
            defaults_applied=defaults + [m.name for m in blocking],
            reason=("the clarification budget for this conversation is spent, "
                    "so the turn proceeded on defaults and the reply says so"))

    blocking = blocking[:max_questions()]
    return CompletenessVerdict(
        complete=False, intent=intent, facts=facts, missing=blocking,
        defaults_applied=defaults,
        reason="; ".join(m.reason for m in blocking))


def verdict_from_dict(data: Any) -> CompletenessVerdict | None:
    """Rebuild a verdict that travelled as an A2A artifact."""
    if not isinstance(data, dict):
        return None
    raw_facts = data.get("facts") or {}
    facts = ExtractedFacts(
        dates=[str(d) for d in (raw_facts.get("dates") or [])],
        years=[str(y) for y in (raw_facts.get("years") or [])],
        has_period=bool(raw_facts.get("has_period")),
        period_phrase=str(raw_facts.get("period_phrase") or ""),
        tenors=[str(t) for t in (raw_facts.get("tenors") or [])],
        has_spread=bool(raw_facts.get("has_spread")),
        confidence_level=raw_facts.get("confidence_level"),
        horizon_days=(int(raw_facts["horizon_days"])
                      if raw_facts.get("horizon_days") is not None else None),
        has_portfolio=bool(raw_facts.get("has_portfolio")),
        curve_family=str(raw_facts.get("curve_family") or ""),
        scenario=str(raw_facts.get("scenario") or ""),
        has_amount=bool(raw_facts.get("has_amount")),
        shock_bp=raw_facts.get("shock_bp"))
    missing = [MissingField(name=str(m.get("name") or ""),
                            question=str(m.get("question") or ""),
                            reason=str(m.get("reason") or ""),
                            options_from=str(m.get("options_from") or ""))
               for m in (data.get("missing") or []) if isinstance(m, dict)]
    return CompletenessVerdict(
        complete=bool(data.get("complete")),
        intent=str(data.get("intent") or "unknown"), facts=facts,
        missing=missing, reason=str(data.get("reason") or ""),
        proceeded_on_defaults=bool(data.get("proceeded_on_defaults")),
        defaults_applied=[str(d) for d in (data.get("defaults_applied") or [])])
