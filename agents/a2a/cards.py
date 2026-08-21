"""Agent Cards — what each agent actually does, published for discovery.

A card is a contract, not marketing. "Can answer questions" tells a caller
nothing it can act on; "judges a proposed data requirement against what the
source truly holds, and returns the unsupported fields by name" tells it exactly
what to send and exactly what comes back.

So the skill ids here are load-bearing rather than descriptive. A request names
a skill, and the envelope refuses any skill the target's card does not
advertise — which means the card cannot drift away from the code without a
request failing loudly. The same list is what a caller reads to know which agent
to address at all.

Three cards, one per existing agent. There is deliberately no card for the
`DataProvider`, `RiskWorkflows`, the knowledge base or the MCP host: those are
services and adapters this system calls, not agents that reason.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentProvider, AgentSkill
from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, TransportProtocol

from agents.a2a.identity import (
    AGENT_VERSION,
    PROVIDER_ORGANISATION,
    PROVIDER_URL,
    AgentId,
    base_url,
)

#: Every agent here speaks structured JSON. Prose travels too, but as a status
#: message beside the data, never instead of it.
JSON_MODE = "application/json"
TEXT_MODE = "text/plain"

#: A skill tagged `idempotent` returns the same answer for the same input for as
#: long as one user turn lasts, so a repeat inside that turn is a loop rather
#: than a request and may be answered from the first result.
#:
#: Everything untagged is treated as freshness-sensitive and is **never**
#: answered from a previous result — it is only counted against the turn's
#: handoff budget. Fetching data, running a calculation and resuming an
#: interrupted plan all belong in that group: they read the market, they cost
#: something, and their answer is about *now*. Marking one of them idempotent to
#: save a call would be the moment duplicate suppression turned into a cache.
IDEMPOTENT_TAG = "idempotent"

# --- skills -----------------------------------------------------------------

ORCHESTRATOR_SKILLS = [
    AgentSkill(
        id="handle_user_turn",
        name="Handle a user turn",
        description=(
            "The only entry point a user's words reach. Classifies the turn as "
            "small talk, a missing-detail clarification, or a data request; "
            "delegates planning and execution to the specialist agents over "
            "A2A; and writes the final reply under the system's honesty rules "
            "(no ungrounded figures, no internal identifiers, real-versus-"
            "synthetic labels preserved)."
        ),
        tags=["routing", "user-facing", "reflection", "market-risk"],
        examples=[
            "What is the DV01 of the demo book?",
            "What is the current 2s10s slope?",
            "hi",
        ],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE, TEXT_MODE],
    ),
    AgentSkill(
        id="relay_user_input",
        name="Relay a user's answer to a waiting agent",
        description=(
            "Carries an answer the user gave back to the specialist task that "
            "asked for it, so an interrupted A2A task resumes where it stopped "
            "instead of a fresh workflow starting. This is the return leg of "
            "orchestrator-mediated elicitation."
        ),
        tags=["elicitation", "user-facing", "task-continuation"],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE, TEXT_MODE],
    ),
    AgentSkill(
        id="summarise_session",
        name="Name a conversation",
        description=(
            "Titles a transcript in two to five words for the chat sidebar. "
            "Routing-grade work with no data access: it reads only the messages "
            "it is given."
        ),
        tags=["routing", "user-facing", IDEMPOTENT_TAG],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
]

DOMAIN_EXPERT_SKILLS = [
    AgentSkill(
        id="validate_result",
        name="Validate an execution result against the agreed plan",
        description=(
            "Checks a completed calculation against the analytical contract "
            "that was agreed before it ran: the portfolio, the method, the "
            "confidence level, the horizon, the lookback, the valuation date, "
            "the curve family and the units. Returns VALID, "
            "VALID_WITH_WARNINGS or INVALID with the mismatches named. This is "
            "the gate that stops a true number reaching a user under a false "
            "label — a one-day figure described as ten-day is arithmetically "
            "correct and completely wrong."
        ),
        tags=["market-risk", "validation", "assurance", IDEMPOTENT_TAG],
        examples=[
            "Agreed 10-day 99% VaR; the engine returned horizon_days=1.",
            "Agreed DV01 on the demo book; confirm units and valuation date.",
        ],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
    AgentSkill(
        id="derive_data_requirement",
        name="Derive a grounded data requirement",
        description=(
            "Interprets a market-risk question, retrieves the governing method "
            "from the Qdrant knowledge corpus, and emits the data requirement "
            "it implies: which fields the calculation reads, how many "
            "observations, which tenors, and which risk calculation. Every "
            "number carries a verbatim quote from a retrieved chunk, and a "
            "quote that is not in the retrieved text is discarded rather than "
            "used. Then negotiates that requirement with the data-layer agent "
            "over A2A for up to three bounded rounds and returns the final, "
            "servable version with the full transcript."
        ),
        tags=["market-risk", "knowledge-retrieval", "requirements", "citations",
              "negotiation", IDEMPOTENT_TAG],
        examples=[
            "How many observations does a 99 percent historical VaR read?",
            "What does a DV01 calculation on the demo book require?",
            "Which fields does a 2s10s slope need?",
        ],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
]

MCP_AGENT_SKILLS = [
    AgentSkill(
        id="describe_data_capabilities",
        name="Advertise the live data and tool surface",
        description=(
            "Reports the MCP tools, rate fields and tenors that are actually "
            "connected right now, read from the live provider rather than "
            "declared. Under a backend with no risk engine the risk tools are "
            "absent from the answer, so no caller can plan a calculation that "
            "cannot run."
        ),
        tags=["mcp", "capability-discovery", "catalogue", IDEMPOTENT_TAG],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
    AgentSkill(
        id="assess_data_requirement",
        name="Judge a proposed requirement against the source",
        description=(
            "Given a requirement, says what this data source can and cannot "
            "serve: unsupported fields by name, an unsupported calculation, the "
            "rows actually available, and a counter-proposal. Never offers a "
            "substitute for a missing field — a par yield curve holds no "
            "CUSIPs, issuers or settlement dates, and saying so is the correct "
            "answer."
        ),
        tags=["mcp", "feasibility", "negotiation", IDEMPOTENT_TAG],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
    AgentSkill(
        id="execute_data_plan",
        name="Fetch the agreed data and run the agreed calculation",
        description=(
            "Executes an agreed requirement through the MCP data server and the "
            "risk engine: reads the curve or the history, runs pricing, DV01, "
            "VaR or stress through the deterministic workflow layer, and "
            "returns the table, the calculation and the provenance as separate "
            "artifacts. Rows requested and rows delivered are reported "
            "separately; a short fetch is never padded. If the data layer needs "
            "a decision only a human can make, this skill stops the task in "
            "input-required and hands the question up — it never asks the user "
            "itself."
        ),
        tags=["mcp", "data-access", "risk-calculation", "provenance"],
        examples=[
            "Fetch 250 observations of the 2y and 10y par yields.",
            "Compute DV01 on the demo book from the latest nominal curve.",
        ],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
    AgentSkill(
        id="list_data_choices",
        name="List the real portfolios, scenarios and curve families",
        description=(
            "The concrete things a user could actually pick, straight from the "
            "connected servers, so a clarifying question offers choices that "
            "end the ambiguity instead of restating it."
        ),
        tags=["mcp", "catalogue", "clarification-support", IDEMPOTENT_TAG],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
    AgentSkill(
        id="provide_input",
        name="Resume a task with input supplied by the orchestrator",
        description=(
            "Continues a task previously stopped in input-required, using the "
            "answer the orchestrator collected from the user. Correlated by "
            "task id, so the original request resumes rather than a new one "
            "starting."
        ),
        tags=["mcp", "task-continuation", "elicitation"],
        input_modes=[JSON_MODE],
        output_modes=[JSON_MODE],
    ),
]

SKILLS: dict[AgentId, list[AgentSkill]] = {
    AgentId.ORCHESTRATOR: ORCHESTRATOR_SKILLS,
    AgentId.DOMAIN_EXPERT: DOMAIN_EXPERT_SKILLS,
    AgentId.MCP: MCP_AGENT_SKILLS,
}

DESCRIPTIONS: dict[AgentId, str] = {
    AgentId.ORCHESTRATOR: (
        "Front door of a U.S. Treasury market-risk data gateway. The only agent "
        "that speaks to a human: it routes each turn, delegates the work to the "
        "specialist agents over A2A, mediates any question they need answered, "
        "and writes the reply."
    ),
    AgentId.DOMAIN_EXPERT: (
        "Market-risk domain expert. Decides what data a task requires by "
        "reading a quant knowledge corpus, cites the sentence it relied on, and "
        "argues the requirement out with the data layer until it is servable."
    ),
    AgentId.MCP: (
        "The data layer's representative. Owns the MCP connection to the "
        "Treasury database and the risk engine: advertises what is really "
        "connected, judges what can be served, and executes the agreed plan."
    ),
}


def skill_ids(agent: AgentId) -> set[str]:
    return {s.id for s in SKILLS[agent]}


def is_idempotent(agent: AgentId, skill: str) -> bool:
    """May a repeat of this exact call, inside one turn, be answered from the first?

    Read from the card rather than from a list kept beside it, so the property a
    caller can discover and the property the guardrail enforces cannot disagree.
    An unknown skill is treated as freshness-sensitive: the safe default is to
    do the work again, not to hand back something old.
    """
    for entry in SKILLS.get(agent, []):
        if entry.id == skill:
            return IDEMPOTENT_TAG in entry.tags
    return False


def agent_card(agent: AgentId) -> AgentCard:
    """Build this agent's card against the currently configured address.

    Built on demand rather than at import, because the URL is configuration and
    a card frozen at import time would advertise the wrong address the moment an
    agent is moved.
    """
    url = base_url(agent)
    return AgentCard(
        name=agent.value,
        description=DESCRIPTIONS[agent],
        version=AGENT_VERSION,
        provider=AgentProvider(organization=PROVIDER_ORGANISATION, url=PROVIDER_URL),
        # Streaming is advertised false because it is not implemented. A card
        # that claims a capability the server does not honour is worse than a
        # thin card: the client builds a subscription that never yields.
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=[JSON_MODE],
        default_output_modes=[JSON_MODE, TEXT_MODE],
        supported_interfaces=[AgentInterface(
            url=f"{url}/",
            protocol_binding=TransportProtocol.JSONRPC,
            protocol_version=PROTOCOL_VERSION_CURRENT,
        )],
        skills=SKILLS[agent],
    )


def all_cards() -> dict[AgentId, AgentCard]:
    return {agent: agent_card(agent) for agent in AgentId}
