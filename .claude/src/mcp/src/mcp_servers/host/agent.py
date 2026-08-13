"""The host's reasoning loop — the only component in the MCP layer that thinks.

Neither server imports an LLM client, and neither should. The data server holds
a database credential; the risk engine holds neither a credential nor a model,
which is what makes "was the input wrong or the maths?" mechanically answerable.
Putting reasoning in either would collapse a boundary the rest of the design
spends real effort maintaining. So the model lives here, in the host, and the
servers stay dumb and honest.

## What this loop gets from each primitive

* **Tools** are the actions. Both servers' tools are merged into one namespace
  and handed to the model as its tool list.
* **Resources** are context the model should not have to ask for. The dataset
  caveats and the risk engine's methodology are attached to the system prompt up
  front, because a caveat discovered after a number has been quoted is too late.
* **Prompts** are the workflows the servers themselves recommend. They are
  advertised by name so the model can follow a server's intended tool ordering
  rather than improvising one.
* **Elicitation**, **roots** and **sampling** need nothing here at all. They are
  answered by the host's callbacks inside `McpHost.call`, so a tool that stops
  mid-way to ask a question looks, from this loop, exactly like a tool that took
  slightly longer to return. That is the point of putting the retry driver at
  the seam.

Run: ``python -m mcp_servers.host --ask "..."`` (add ``--interactive`` to answer
elicitations yourself rather than declining them).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .interaction import InteractionPolicy
from .mcp_clients import McpHost

LOGGER = logging.getLogger("host.agent")

MODEL = "claude-opus-5"
MAX_TOKENS = 32_000
MAX_STEPS = 24

SYSTEM = """\
You are a quantitative market-risk analyst working over U.S. Treasury interest-rate data.
You reach data only through the tools provided. You never state a rate, price or risk
figure you did not obtain from a tool call.

How the two servers divide the work:

* market-risk-data retrieves facts. It does not price, interpolate, or compute
  DV01, VaR, spreads or curve slopes.
* risk-engine calculates. It has no database, so every input must be fetched
  first and passed to it explicitly.

Rules you must not break:

* Par yields are not zero rates. The risk engine bootstraps discount factors
  before pricing; never treat a 10-year CMT as a discount rate.
* quote_basis travels with every rate. A bank-discount rate and a
  coupon-equivalent yield are different quantities and must never share a curve.
  Check it before combining series.
* Never present synthetic data as real. The demo book is SYNTHETIC_DEMO; the
  curve is REAL_MARKET_DATA. Both labels must appear in your answer when the
  data does.
* Bond values are model-implied from the par curve, not executable prices.
  Reported VaR is an analytical demonstration, not a regulatory figure.
* Scope is interest-rate market risk. CVA, RWA and PD/LGD/EAD can be explained
  but not computed here - there is no counterparty or portfolio-credit data. Say
  so rather than improvising a number.
* A tool error is information, not a dead end. Each one names its own fix -
  candidate dates, a suggested date_policy, an alternative series. Read it and
  retry accordingly.
* If a tool reports that a question was declined or an export refused, say so
  plainly. Do not fill the gap with an assumption.

Answer with the figure first, then the reasoning, then the caveats. State the
observation date and the dataset_snapshot_id for any number you quote.
"""


def _anthropic_tools(host: McpHost) -> list[dict[str, Any]]:
    """Both servers' tools as one Anthropic tool list.

    Names are already unique across servers (the host logs and drops a
    collision), so the model sees a flat namespace and the host maps each call
    back to its owning server.
    """
    tools = []
    for tool in host.all_tools():
        schema = tool.input_schema or {"type": "object", "properties": {}}
        tools.append({
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "input_schema": schema,
        })
    return tools


async def _grounding(host: McpHost) -> str:
    """Resources and prompts, folded into the system prompt.

    This is the resources primitive doing its actual job: the caveats are the
    material most likely to prevent a wrong number, and making the model ask for
    them first would mean sometimes it doesn't.
    """
    parts: list[str] = []
    for server_name, connected in host.servers.items():
        session = connected.session
        try:
            listed = await session.list_resources()
        except Exception as exc:  # noqa: BLE001 - grounding is best-effort
            LOGGER.warning("%s: could not list resources: %s", server_name, exc)
            continue
        names = ", ".join(f"{r.uri} ({r.name})" for r in listed.resources)
        parts.append(f"{server_name} resources: {names}")
        try:
            prompts = await session.list_prompts()
            parts.append(f"{server_name} recommended workflows: "
                         + ", ".join(p.name for p in prompts.prompts))
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("%s: could not list prompts: %s", server_name, exc)

    # The caveats are worth their tokens; they are the single most common cause
    # of a confidently wrong Treasury number.
    try:
        data = host.servers["market-risk-data"].session
        read = await data.read_resource("market-risk://catalog/datasets")
        body = "".join(getattr(c, "text", "") for c in read.contents)
        rows = json.loads(body)
        caveats = "\n".join(
            f"  - {r['data_key']}: {r['caveat']}" for r in rows if r.get("caveat"))
        parts.append("Dataset caveats you must respect:\n" + caveats)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("could not attach dataset caveats: %s", exc)

    return "\n\n".join(parts)


def _result_text(result: Any) -> str:
    """A tool result as text for the model, error or not.

    Errors are returned rather than raised on purpose: every MCP error names its
    own fix, and handing that to the model lets it self-correct where an
    exception would end the turn.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return json.dumps(structured, default=str)[:20_000]
    text = "".join(getattr(c, "text", "") for c in (getattr(result, "content", None) or []))
    return text[:20_000] or "(tool returned no content)"


async def answer(host: McpHost, question: str) -> str:
    """Run the tool-calling loop until the model stops asking for tools."""
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic()
    tools = _anthropic_tools(host)
    system = SYSTEM + "\n\n" + await _grounding(host)
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]

    for step in range(MAX_STEPS):
        # Streaming, because adaptive thinking plus a 32k ceiling is exactly the
        # shape that trips the SDK's non-streaming timeout guard.
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            return (f"[refused by the model's safety classifiers"
                    f"{': ' + detail.category if detail else ''}]")

        messages.append({"role": "assistant", "content": response.content})

        calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if not calls:
            return "".join(b.text for b in response.content
                           if getattr(b, "type", None) == "text").strip()

        results = []
        for call in calls:
            LOGGER.info("step %d: %s(%s)", step + 1, call.name,
                        json.dumps(call.input, default=str)[:160])
            print(f"  -> {call.name}({json.dumps(call.input, default=str)[:120]})", flush=True)
            try:
                # Any elicitation, roots or sampling request the tool raises is
                # answered and retried inside here; this loop never sees it.
                raw = await host.call(call.name, dict(call.input))
                content, is_error = _result_text(raw), bool(getattr(raw, "is_error", False))
            except Exception as exc:  # noqa: BLE001 - surfaced to the model
                content, is_error = f"tool call failed: {type(exc).__name__}: {exc}", True
            results.append({
                "type": "tool_result", "tool_use_id": call.id,
                "content": content, "is_error": is_error,
            })
        # All results in one user message: splitting them teaches the model to
        # stop making parallel calls.
        messages.append({"role": "user", "content": results})

    return "[stopped: reached the maximum number of tool-calling steps]"


async def run_ask(question: str, *, interactive: bool = False) -> int:
    # .env is what actually holds the key; without this the check below fails on
    # a machine that is correctly configured, which is a confusing way to
    # discover nothing is wrong.
    from treasury_db.db import load_dotenv  # noqa: PLC0415

    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY is not set; the host cannot reason without it.")
        return 2
    policy = InteractionPolicy.default(elicitation="prompt" if interactive else "decline")
    async with McpHost(policy=policy) as host:
        print(f"question: {question}\n")
        result = await answer(host, question)
        print(f"\n{'-' * 72}\n{result}")
    return 0
