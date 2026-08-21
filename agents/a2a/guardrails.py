"""What stops three agents that can always reply from replying forever.

Two agents with A2A endpoints can call each other. Nothing in the protocol says
they must ever stop, and a model asked to keep collaborating will keep
collaborating — so the bounds live here, in code, where they can be tested and
where a reader can find all of them in one place rather than inferring them from
prompts.

**Five bounds, because they fail differently.** The important word is *five*: an
earlier version used one flat integer for three of these, and it was wrong in
both directions at once — it refused a legitimate fourth hop while doing nothing
at all about an agent that called the same peer two hundred times at depth two.

| Bound | Stops | Config |
|---|---|---|
| Call chain | runaway nesting: A→B→C→D→E→… | `A2A_MAX_CHAIN` |
| Re-entry | a *cycle*: A→B→A→B→A→… | `A2A_MAX_REENTRY` |
| Handoff budget | breadth: one agent calling a peer forever | `A2A_MAX_HANDOFFS` |
| Duplicate | the same question asked twice in a turn | (always on) |
| Time | an agent that hangs | `A2A_CALL_TIMEOUT_SECONDS` |

Two more live outside this module because they are domain concepts rather than
transport ones: `MAX_NEGOTIATION_ROUNDS` in `agents/planning.py` bounds the
Domain ↔ MCP conversation, and `A2A_MAX_CLARIFICATIONS` in
`agents/a2a/elicitation.py` bounds how often a user may be re-asked.

**Why chain length is not the same as recursion.** A bounded negotiation of five
rounds issues five sibling calls from one worker thread — each at the *same*
chain length, none nested inside another. Counting messages as depth made a
legitimate conversation look like a stack overflow. What actually needs stopping
is a chain that keeps growing (nesting) or one that keeps revisiting the same
(agent, skill) pair (a cycle), and those are the two things measured here.

**Duplicate suppression is loop prevention, not a cache.** Identity is `(this
turn, target agent, skill, canonical input)`; the store lives on the
`TurnLedger`, which is created when a user turn starts and discarded when it
ends. **Nothing survives a turn**, so a later independent question can never be
answered with an earlier one's data. Within a turn only skills their card tags
`idempotent` are eligible — fetching data, running a calculation and resuming an
interrupted plan are repeated rather than replayed, because their answer is
about *now*.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger("agents.a2a.guardrails")

#: How deeply calls may nest before the chain is refused. The longest legitimate
#: chain in this system is service → orchestrator → domain-expert → mcp-agent,
#: which is four. Eight leaves room for a callback the architecture may grow
#: without leaving room for unbounded recursion.
DEFAULT_MAX_CHAIN = 8

#: How many times one `(agent, skill)` pair may appear in a single chain. Three
#: permits a genuine there-and-back-again — a specialist consulted, answering,
#: and consulted once more within the same nested call — while stopping
#: A→B→A→B→A→B dead. A cycle is a chain that keeps revisiting; that is what this
#: counts, and it is the guard the flat depth counter never provided.
DEFAULT_MAX_REENTRY = 3

#: Worst case for one fully negotiated risk request:
#:   user turn (1) + derive (1) + catalogue (1) + 5 negotiation rounds (5)
#:   + execute (1) + result validation (1) + a resumed elicitation (2) = 12.
#: Twenty leaves genuine headroom for a re-opened negotiation after a material
#: clarification without leaving room for a runaway.
DEFAULT_MAX_HANDOFFS = 20

#: How long one whole *user turn* may take, and the only deadline this layer
#: enforces. Every call is bounded by whatever remains of it.
#:
#: There used to be a flat per-call deadline applied identically at every depth,
#: and it was structurally wrong rather than merely mistuned. A call **contains**
#: every call made beneath it, so one flat number makes the outermost call the
#: tightest bound in the system: it expires first by construction. That is
#: exactly what happened — `derive` took 80s and `assess` took 78s, both
#: legitimately (the provider retried a broken output contract each time), and
#: the orchestrator's own 300s deadline then fired mid-revision and reported a
#: turn that was proceeding normally as hung. Raising the number would only have
#: moved the same failure further out.
#:
#: Hang detection did not need that guard and is not weakened by removing it: an
#: agent hangs where it waits on the network, and the model layer already bounds
#: every provider request with `LLM_TIMEOUT_SECONDS`. Each guard now sits at the
#: level where the fault it catches actually occurs — the model layer bounds a
#: model call, this layer bounds a turn — instead of one guard trying to do both
#: and misfiring on nesting.
#:
#: Deliberately generous. Its job is to stop a wedged turn, not to enforce
#: latency; a user waiting on a real negotiation is being served, not stalled.
DEFAULT_TURN_TIMEOUT_S = 900.0

#: Kept so an existing `A2A_CALL_TIMEOUT_SECONDS` in someone's `.env` still has
#: an effect and still means something honest: the floor under the turn budget.
DEFAULT_CALL_TIMEOUT_S = 300.0


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


def max_chain() -> int:
    return _env_int("A2A_MAX_CHAIN", DEFAULT_MAX_CHAIN)


def max_reentry() -> int:
    return _env_int("A2A_MAX_REENTRY", DEFAULT_MAX_REENTRY)


def max_handoffs() -> int:
    return _env_int("A2A_MAX_HANDOFFS", DEFAULT_MAX_HANDOFFS)


def call_timeout_s() -> float:
    return _env_float("A2A_CALL_TIMEOUT_SECONDS", DEFAULT_CALL_TIMEOUT_S)


def turn_timeout_s() -> float:
    """The whole-turn budget, never below the configured single-call floor.

    Clamped rather than trusted: a turn budget under the floor is always a
    misconfiguration, and honouring it would reintroduce the failure this
    separation exists to remove.
    """
    return max(_env_float("A2A_TURN_TIMEOUT_SECONDS", DEFAULT_TURN_TIMEOUT_S),
               call_timeout_s())


class HandoffRefused(RuntimeError):
    """A handoff was refused by a guardrail rather than by the target agent.

    Carries `reason` so the refusal reaches the user as a stated limit rather
    than as a generic failure — "the agents did not converge within their
    handoff budget" is actionable; "internal error" is not.
    """

    def __init__(self, reason: str, kind: str = "handoff_limit") -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind


@dataclass(frozen=True)
class CallChain:
    """The path of nested calls from the user boundary to right now.

    Passed down in message metadata and extended by one entry at each nested
    call. It is the difference between "this is the fifth message this turn"
    (fine) and "this is the fifth agent on one stack" (not fine).
    """

    steps: tuple[str, ...] = ()

    @classmethod
    def parse(cls, raw: Any) -> CallChain:
        if isinstance(raw, str):
            raw = [part for part in raw.split(">") if part]
        if not isinstance(raw, (list, tuple)):
            return cls()
        return cls(tuple(str(step) for step in raw if step))

    def extend(self, agent: str, skill: str) -> CallChain:
        return CallChain((*self.steps, f"{agent}.{skill}"))

    def encode(self) -> str:
        return ">".join(self.steps)

    @property
    def length(self) -> int:
        return len(self.steps)

    def reentries(self, agent: str, skill: str) -> int:
        """How many times this exact `(agent, skill)` already sits on the chain."""
        return self.steps.count(f"{agent}.{skill}")

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return self.encode() or "(root)"


@dataclass
class Handoff:
    """One recorded A2A call, for the trace and for the log."""

    sequence: int
    requesting_agent: str
    target_agent: str
    skill: str
    chain_length: int
    task_id: str = ""
    context_id: str = ""
    state: str = ""
    duplicate: bool = False
    #: Whether this call was eligible for duplicate suppression at all — i.e.
    #: whether its card tags it idempotent. Recorded so a reader of the ledger
    #: can tell "not a repeat" from "never replayable".
    repeatable: bool = False
    #: Which Domain ↔ MCP negotiation round this call belongs to, and what it
    #: was for. Zero and empty outside a negotiation. Without these the trail
    #: reads as an undifferentiated list of calls and the collaboration is
    #: invisible, which is what made the earlier negotiation impossible to
    #: review.
    negotiation_round: int = 0
    negotiation_phase: str = ""
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "from": self.requesting_agent,
                "to": self.target_agent, "skill": self.skill,
                "chain_length": self.chain_length,
                "task_id": self.task_id, "context_id": self.context_id,
                "state": self.state, "duplicate": self.duplicate,
                "repeatable": self.repeatable,
                "negotiation_round": self.negotiation_round,
                "negotiation_phase": self.negotiation_phase,
                "duration_ms": self.duration_ms}


@dataclass
class TurnLedger:
    """The budget and the record for one user turn.

    Shared by every agent taking part in that turn, which is what makes the
    count a *turn* budget rather than a per-agent one. Guarded by a lock because
    a turn's handoffs run on the A2A event loop while the domain logic that
    issues them runs on worker threads.
    """

    user_request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    context_id: str = ""
    chain_limit: int = field(default_factory=max_chain)
    reentry_limit: int = field(default_factory=max_reentry)
    handoff_limit: int = field(default_factory=max_handoffs)
    timeout_s: float = field(default_factory=call_timeout_s)
    #: The budget for the whole turn. Every call is bounded by what remains of
    #: it, so a child can never outlive its parent. See `DEFAULT_TURN_TIMEOUT_S`.
    turn_timeout_s: float = field(default_factory=turn_timeout_s)
    #: When the turn started, so `remaining_seconds()` can answer honestly.
    started_at: float = field(default_factory=time.monotonic)

    def remaining_seconds(self) -> float:
        """How much of the turn budget is left, never zero or negative.

        A floor of one second rather than zero: a call granted no time at all
        fails with a deadline error that reads like a hang, when what actually
        happened is that the turn ran out. The turn-level report says that.
        """
        return max(1.0, self.turn_timeout_s - (time.monotonic() - self.started_at))
    handoffs: list[Handoff] = field(default_factory=list)
    _seen: dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # -- admission ----------------------------------------------------------

    def authorise(self, *, requesting_agent: str, target_agent: str, skill: str,
                  chain: CallChain, digest: str, repeatable: bool = False,
                  negotiation_round: int = 0,
                  negotiation_phase: str = "") -> tuple[Handoff, Any | None]:
        """Admit or refuse one handoff, and report a duplicate if it is one.

        Three independent refusals, in the order a runaway would trip them:
        the chain is too deep (nesting), this pair is already on the chain too
        often (a cycle), or the turn has spent its budget (breadth).

        Returns `(handoff, cached_result)`. A non-None cached result means this
        exact request already ran *in this turn* and must not run again.
        """
        with self._lock:
            if chain.length >= self.chain_limit:
                raise HandoffRefused(
                    f"{requesting_agent} tried to call {target_agent}.{skill} on a "
                    f"call chain already {chain.length} deep, at the limit of "
                    f"{self.chain_limit}. The chain was stopped rather than "
                    f"allowed to nest further: {chain}",
                    kind="chain_limit")

            seen_before = chain.reentries(target_agent, skill)
            if seen_before >= self.reentry_limit:
                raise HandoffRefused(
                    f"{target_agent}.{skill} already appears {seen_before} times "
                    f"on this call chain, at the re-entry limit of "
                    f"{self.reentry_limit}. This is a cycle, not progress: {chain}",
                    kind="reentry_limit")

            if len(self.handoffs) >= self.handoff_limit:
                raise HandoffRefused(
                    f"This turn has already made {len(self.handoffs)} agent-to-"
                    f"agent calls, its limit. {requesting_agent} was not allowed "
                    f"to call {target_agent} again.",
                    kind="handoff_limit")

            handoff = Handoff(sequence=len(self.handoffs) + 1,
                              requesting_agent=requesting_agent,
                              target_agent=target_agent, skill=skill,
                              chain_length=chain.length + 1,
                              context_id=self.context_id,
                              negotiation_round=negotiation_round,
                              negotiation_phase=negotiation_phase)
            self.handoffs.append(handoff)
            cached = self._seen.get(digest) if repeatable else None
            handoff.duplicate = cached is not None
            handoff.repeatable = repeatable
            return handoff, cached

    def record(self, handoff: Handoff, digest: str, result: Any,
               started: float) -> None:
        with self._lock:
            handoff.duration_ms = int((time.perf_counter() - started) * 1000)
            handoff.state = getattr(result, "state", "") or ""
            handoff.task_id = getattr(result, "task_id", "") or ""
            # Only a finished answer to a repeatable question is worth keeping.
            # Storing an `input-required` would answer a resumed request with
            # the question that stopped it; storing a freshness-sensitive result
            # would turn this ledger into the cache it must not be.
            if handoff.repeatable and handoff.state == "completed":
                self._seen.setdefault(digest, result)

    # -- reporting ----------------------------------------------------------

    @property
    def used(self) -> int:
        return len(self.handoffs)

    @property
    def remaining(self) -> int:
        return max(0, self.handoff_limit - len(self.handoffs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_request_id": self.user_request_id,
            "context_id": self.context_id,
            "handoffs_used": self.used,
            "handoff_limit": self.handoff_limit,
            "chain_limit": self.chain_limit,
            "reentry_limit": self.reentry_limit,
            "max_chain_reached": max((h.chain_length for h in self.handoffs),
                                     default=0),
            "negotiation_rounds": max((h.negotiation_round for h in self.handoffs),
                                      default=0),
            "duplicates_suppressed": sum(1 for h in self.handoffs if h.duplicate),
            "handoffs": [h.as_dict() for h in self.handoffs],
        }


class LedgerRegistry:
    """The turn ledgers currently in flight, keyed by `user_request_id`.

    A budget that is only enforced at one hop is not a turn budget. The
    orchestrator opens the ledger; the domain expert, reached over A2A, has to
    find the *same* one or its calls to the MCP agent would each start from
    zero and the loop it is supposed to bound would be unbounded again.

    Every agent in this system shares a process, so the lookup is a dictionary.
    The chain also travels in message metadata, so an agent moved to another
    host still carries its nesting and its cycle history with it — it simply
    cannot see how much of the *budget* its siblings have spent, which is the
    honest limit of a design with no shared store, and the reason the chain and
    re-entry bounds are enforced independently of it.

    Bounded and FIFO-evicted: a ledger is worthless once its turn ends, and an
    unbounded dictionary keyed by request id is a slow leak.
    """

    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._ledgers: dict[str, TurnLedger] = {}
        self._lock = threading.Lock()

    def open(self, context_id: str) -> TurnLedger:
        ledger = TurnLedger(context_id=context_id)
        with self._lock:
            self._ledgers[ledger.user_request_id] = ledger
            self._evict()
        return ledger

    def find(self, user_request_id: str, context_id: str = "") -> TurnLedger:
        """The turn's ledger, or a fresh one if the turn is not local.

        A miss is not an error — it is what happens when the caller is on
        another host. The replacement inherits the budget from configuration,
        so the bound still holds; only the shared count is lost.
        """
        with self._lock:
            existing = self._ledgers.get(user_request_id)
            if existing is not None:
                return existing
            ledger = TurnLedger(
                user_request_id=user_request_id or TurnLedger().user_request_id,
                context_id=context_id)
            self._ledgers[ledger.user_request_id] = ledger
            self._evict()
            return ledger

    def close(self, ledger: TurnLedger) -> None:
        with self._lock:
            self._ledgers.pop(ledger.user_request_id, None)

    def _evict(self) -> None:
        while len(self._ledgers) > self._capacity:
            self._ledgers.pop(next(iter(self._ledgers)))
