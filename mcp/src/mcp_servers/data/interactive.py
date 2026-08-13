"""The three client-directed primitives: elicitation, roots and sampling.

Tools, resources and prompts flow one way — the client asks, the server answers.
These three run the other way: mid-call, the server needs something only the
client can supply. A choice only a human can make, a filesystem boundary only
the client knows, a completion only the client's model can produce.

All three use one mechanism. A tool parameter annotated
``Annotated[T, Resolve(fn)]`` is filled by running ``fn`` *before* the tool body,
and a resolver may return a request marker instead of a value:

    Elicit[T]    ask the user a structured question   -> ElicitationResult[T]
    ListRoots    ask for the client's roots           -> ListRootsResult
    Sample       ask the client's LLM                 -> CreateMessageResult

On protocol revision 2026-07-28 the framework batches those requests into an
``InputRequiredResult`` and the client answers by **retrying the original call**
with ``input_responses`` and ``request_state`` — multi-round tool response
(MRTR). There is no server-initiated ``elicitation/create`` any more, and no
``elicitationId``. Correlation is by resolver key across retries.

Two consequences worth stating plainly, because both are easy to get wrong:

* **Resolver bodies re-run on every round.** They must be cheap and
  side-effect-free. Every read here is an idempotent catalogue lookup.
* **A resolver that returns a plain value never asks anything.** That is the
  common path and it costs no round trip — `search_series` only elicits when the
  query genuinely spans two rate kinds.

Never combine a ``Resolve(...)`` parameter with a hand-rolled
``InputRequiredResult`` return on the same tool. A call has a single
``input_responses``/``request_state`` channel; the two flows would overwrite each
other's state and the call could never converge. The SDK rejects it at
registration, and that rejection is a feature.
"""

from __future__ import annotations

import datetime as dt
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import Elicit, ListRoots, Sample
from mcp.types import SamplingMessage, TextContent
from pydantic import BaseModel, Field

from . import repository as repo
from ._db import connect

# --- elicitation ------------------------------------------------------------


class RateKindChoice(BaseModel):
    """The answer to 'nominal or real?'.

    Deliberately one field. An elicitation schema is a form a human fills in
    under time pressure; every extra field is another chance to answer the
    wrong question.
    """

    rate_kind: Literal["nominal", "real"] = Field(
        description=(
            "'nominal' is the standard Treasury par yield curve. 'real' is the "
            "TIPS-derived curve, whose negative values are normal and correct. "
            "These are different quantities and must never share a curve."
        )
    )


def resolve_rate_kind(query: str, data_key: str | None = None) -> Elicit[RateKindChoice] | RateKindChoice:
    """Ask which curve family, but only when the query genuinely spans both.

    '30 year' matches BC_30YEAR and TC_30YEAR — a nominal par yield and a real
    yield. No amount of server-side cleverness can pick correctly, because
    the information needed is in the caller's head, not in the database. The old
    behaviour was to refuse with `AMBIGUOUS_SERIES`; asking is strictly better,
    and it is the case that justifies elicitation existing at all.

    When the query already resolves to one rate kind, that kind is returned
    directly and **no round trip happens** — the framework wraps a plain return
    value as an accepted outcome. This is the overwhelmingly common path, and
    keeping it free is what makes elicitation affordable to have switched on.
    """
    with connect() as conn:
        rows = repo.search_series(conn, query, data_key, 20)
    kinds = sorted({r["rate_kind"] for r in rows})
    if len(kinds) < 2:
        # One kind, or none at all. Nothing to ask; a query that matched nothing
        # returns an empty match list regardless of what goes here.
        only = kinds[0] if kinds else "nominal"
        return RateKindChoice(rate_kind=only)  # type: ignore[arg-type]
    examples = {k: [r["series_code"] for r in rows if r["rate_kind"] == k][:3] for k in kinds}
    detail = "; ".join(f"{k}: {', '.join(codes)}" for k, codes in examples.items())
    return Elicit(
        f"{query!r} matches both nominal and real series ({detail}). "
        "A nominal par yield and a real yield are different quantities and must "
        "not be combined on one curve. Which do you want?",
        RateKindChoice,
    )


# --- roots ------------------------------------------------------------------


def resolve_export_roots() -> ListRoots:
    """Ask the client where it is willing to have files written.

    The server does not get to choose a destination. Roots exist so a client can
    say 'these directories, and nowhere else', and the server confines itself to
    that answer. Without it an export tool is an arbitrary-file-write primitive
    wearing a CSV hat.
    """
    return ListRoots()


def root_paths(roots_result) -> list[tuple[Path, str]]:
    """Local filesystem paths for the client's declared roots.

    Roots arrive as ``file://`` URLs. Non-file schemes are skipped rather than
    guessed at, and an unresolvable URL is skipped rather than allowed — this
    list is a permission boundary, so anything not positively understood is
    excluded.
    """
    out: list[tuple[Path, str]] = []
    for root in getattr(roots_result, "roots", None) or []:
        parsed = urllib.parse.urlparse(str(root.uri))
        if parsed.scheme != "file":
            continue
        try:
            local = Path(urllib.request.url2pathname(parsed.path)).resolve()
        except (OSError, ValueError):
            continue
        out.append((local, root.name or str(root.uri)))
    return out


def contained_target(roots_result, filename: str) -> tuple[Path | None, list[str]]:
    """Resolve ``filename`` inside the first declared root, or refuse.

    Two separate defences, because they fail differently:

    * ``filename`` may not contain a path separator or a parent reference at
      all — rejected before it is ever joined to a root.
    * The resolved path is then re-checked for containment, which catches a
      symlink inside the root pointing out of it. The first check alone would
      not.

    Returns ``(None, names)`` when there is no usable root, so the caller can
    report what the client actually offered.
    """
    roots = root_paths(roots_result)
    names = [f"{name} -> {path}" for path, name in roots]
    if not roots:
        return None, names
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return None, names
    base = roots[0][0]
    target = (base / filename).resolve()
    if base not in target.parents and target.parent != base:
        return None, names
    return target, names


# --- sampling ---------------------------------------------------------------

_BRIEFING_SYSTEM = (
    "You brief a market-risk desk. You are given a dataset's verbatim caveat and "
    "its coverage. Rewrite it as guidance a trader can act on in under 120 words: "
    "what the data is, the single trap most likely to cause a wrong number, and "
    "what it must not be combined with. Never invent a fact that is not in the "
    "material you were given. Never soften a caveat."
)


def resolve_caveat_briefing(data_key: str) -> Sample | None:
    """Ask the client's LLM to turn a terse caveat into desk-ready guidance.

    This server has no model and no API key, and should not acquire either — it
    is a data server, and an LLM credential inside it would be a second
    privilege boundary to defend. Sampling is the protocol's answer to exactly
    that: the *client* already has a model, so the server borrows it for the one
    step that needs language, and keeps the facts under its own control.

    The verbatim caveat is returned alongside the drafted prose, so a reader can
    always check the rewrite against the source. A briefing that cannot be
    checked is worse than no briefing.
    """
    with connect() as conn:
        rows = [d for d in repo.list_datasets(conn) if d["data_key"] == data_key]
    if not rows:
        return None
    d = rows[0]
    material = (
        f"Dataset: {d['title']} (`{d['data_key']}`)\n"
        f"Coverage: {d['first_observation']} to {d['last_observation']}\n"
        f"Series count: {d['series_count']}\n\n"
        f"Verbatim caveat:\n{d['caveat']}\n"
    )
    return Sample(
        messages=[SamplingMessage(role="user", content=TextContent(type="text", text=material))],
        max_tokens=400,
        system_prompt=_BRIEFING_SYSTEM,
    )


def caveat_source(data_key: str) -> dict[str, object] | None:
    """The verbatim material behind a briefing, for side-by-side checking."""
    with connect() as conn:
        rows = [d for d in repo.list_datasets(conn) if d["data_key"] == data_key]
    if not rows:
        return None
    d = rows[0]
    return {
        "data_key": d["data_key"],
        "title": d["title"],
        "caveat": d["caveat"],
        "first_observation": d["first_observation"],
        "last_observation": d["last_observation"],
    }


def today() -> dt.date:
    return dt.date.today()
