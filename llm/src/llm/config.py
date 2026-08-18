"""One place that reads the environment for the model layer.

Every model-related setting is resolved here and nowhere else. An
`os.environ["ZAI_API_KEY"]` inside an agent is the beginning of two
configuration systems that disagree, so agents receive a `ModelConfig` and
never look at the environment themselves.

Selection mirrors the seams the repository already has:

    DATA_BACKEND   -> DataProvider     (mcp | postgres | mock)
    QDRANT_URL     -> VectorStore      (server | embedded)
    LLM_BACKEND    -> ModelProvider    (anthropic | zai)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from llm.contracts import CallSite

ANTHROPIC = "anthropic"
ZAI = "zai"

ZAI_DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"

# Per-call-site defaults, per backend. The split is deliberate: routing and
# grounded reasoning are different problems, and the cheap path must stay cheap.
_DEFAULT_MODELS: dict[str, dict[CallSite, str]] = {
    ANTHROPIC: {
        CallSite.ORCHESTRATOR:  "claude-haiku-4-5",
        CallSite.SAMPLING:      "claude-opus-5",
        CallSite.MCP_AGENT:     "claude-opus-5",
        CallSite.HOST_AGENT:    "claude-opus-5",
        CallSite.DOMAIN_EXPERT: "claude-opus-5",
    },
    # One model for every call site, by explicit instruction. The seam still
    # allows a split - each entry is independently overridable - but the shipped
    # default is uniform, which has a real operational virtue: one model to
    # reason about, one latency profile, one set of quirks.
    #
    # Two measurements stand behind keeping glm-5.2 rather than the cheaper model:
    #
    # * Routing. glm-4.5-air scored 2/8 on the orchestrator's real 8-field
    #   schema against 8/8 for glm-5.2, and the two "passes" were only the safe
    #   default firing. The cause was not reasoning - it chose the right route
    #   and then could not serialise `requested_rows: integer | null`, emitting
    #   0.0, 10000.0, 1.25e-08 and once a 1,000-digit integer. glm-5.2 was also
    #   faster (60s vs 82s over eight calls) because it needs no retries.
    #
    # * Sampling. glm-4.5-air is the cheaper fit on paper - it reports no
    #   reasoning tokens, so a small server-set ceiling is never eaten by
    #   thinking. glm-5.2 measured 92 reasoning tokens against a 400-token
    #   ceiling and still returned 701 characters of usable prose, so the
    #   uniform default is safe. `_MIN_TOKENS[SAMPLING]` is what keeps it safe;
    #   do not lower it without re-measuring.
    ZAI: {
        CallSite.ORCHESTRATOR:  "glm-5.2",
        CallSite.SAMPLING:      "glm-5.2",
        CallSite.MCP_AGENT:     "glm-5.2",
        CallSite.HOST_AGENT:    "glm-5.2",
        CallSite.DOMAIN_EXPERT: "glm-5.2",
    },
}

# Environment variable that overrides the model for each call site.
_MODEL_ENV: dict[CallSite, str] = {
    CallSite.ORCHESTRATOR:  "ORCHESTRATOR_MODEL",
    CallSite.SAMPLING:      "SAMPLING_MODEL",
    CallSite.MCP_AGENT:     "MCP_AGENT_MODEL",
    CallSite.HOST_AGENT:    "HOST_AGENT_MODEL",
    CallSite.DOMAIN_EXPERT: "DOMAIN_EXPERT_MODEL",
}

# A floor on `max_tokens`, applied per call site.
#
# Reasoning models bill their thinking against the same budget as the visible
# answer. Measured against Z.AI: glm-5.2 spent 13 of 16 tokens and 100 of 200
# on reasoning, so a tight ceiling returns an *empty* completion rather than a
# short one. glm-4.5-air reports no reasoning tokens at all and is unaffected.
#
# The floor is only ever raised toward these values, never lowered, so a caller
# that asks for more still gets it — and the MCP sampling contract, where the
# *server* sets the ceiling, is still honoured whenever the server asks for more
# than the floor.
_MIN_TOKENS: dict[CallSite, int] = {
    CallSite.ORCHESTRATOR:  1_200,
    # Sampling's floor is large for what it produces - a briefing under 120
    # words, perhaps 160 tokens. It has to be. The MCP data server sets the
    # ceiling at 400 and cannot know what the client's model costs to *think*,
    # and a reasoning model spends the budget before writing anything:
    #
    #   glm-5.2, ceiling raised to 1024 -> 755 reasoning, 278 visible
    #   glm-5.2, ceiling raised to 1024 -> 1022 reasoning, 0 visible  (empty!)
    #
    # An empty completion is not a short answer; it makes the tool fall back to
    # "[no briefing returned by the client's model]". 2048 leaves room for the
    # observed reasoning burn plus the prose. Re-measure before lowering it.
    CallSite.SAMPLING:      2_048,
    CallSite.MCP_AGENT:     3_000,
    CallSite.HOST_AGENT:    8_000,
    CallSite.DOMAIN_EXPERT: 6_000,
}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class ModelConfig:
    """Everything the model layer needs, resolved once."""

    backend: str
    api_key: str
    base_url: str
    models: dict[CallSite, str]
    #: Whole-request wall clock for a single model call, in seconds.
    timeout_seconds: float
    #: Bounded retries for *transient transport* failures only. A schema
    #: violation is deterministic and is never retried by the transport layer.
    max_transport_retries: int
    min_tokens: dict[CallSite, int] = field(default_factory=lambda: dict(_MIN_TOKENS))

    def model_for(self, call_site: CallSite) -> str:
        return self.models[call_site]

    def tokens_for(self, call_site: CallSite, requested: int | None) -> int:
        """Honour what the caller asked for, but never below the floor."""
        floor = self.min_tokens.get(call_site, 1_024)
        return max(int(requested or 0), floor)

    def redacted(self) -> dict[str, object]:
        """Safe to log. The key never appears — only whether one is present."""
        return {
            "backend": self.backend,
            "base_url": self.base_url or "(provider default)",
            "api_key_configured": bool(self.api_key),
            "timeout_seconds": self.timeout_seconds,
            "models": {site.value: name for site, name in self.models.items()},
        }


def load_config() -> ModelConfig:
    """Read the environment once and produce a config.

    `.env` is loaded first, because a service that starts healthy and dies on
    the first request is a confusing way to discover a missing key.
    """
    _load_dotenv()

    backend = _env("LLM_BACKEND", ANTHROPIC).lower()
    if backend not in (ANTHROPIC, ZAI):
        raise ValueError(
            f"LLM_BACKEND={backend!r} is not recognised; expected "
            f"{ANTHROPIC!r} or {ZAI!r}")

    if backend == ZAI:
        api_key = _env("ZAI_API_KEY")
        base_url = _env("ZAI_BASE_URL", ZAI_DEFAULT_BASE_URL)
    else:
        api_key = _env("ANTHROPIC_API_KEY")
        base_url = _env("ANTHROPIC_BASE_URL")

    defaults = _DEFAULT_MODELS[backend]
    models = {site: _env(_MODEL_ENV[site], defaults[site]) for site in CallSite}

    return ModelConfig(
        backend=backend,
        api_key=api_key,
        base_url=base_url,
        models=models,
        timeout_seconds=float(_env("LLM_TIMEOUT_SECONDS", "300")),
        max_transport_retries=int(_env("LLM_MAX_RETRIES", "2")),
    )


_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _repo_root() -> Path | None:
    """Walk up for a repository marker.

    Never `parents[N]`: five distributions sit at five depths, and a count is
    wrong the moment a file moves.
    """
    for candidate in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / ".git").exists():
            return candidate
    return None


def _load_dotenv() -> None:
    """Read `.env` without importing a layer above this one.

    Duplicated from `treasury_db.db.load_dotenv` on purpose, and it is about
    fifteen lines. `llm` is the lowest distribution in the repository - the MCP
    host must keep running standalone - so it may not import `treasury_db` to
    save them. Same semantics: values already in the real environment win, so an
    operator can override one setting for one command.
    """
    root = _repo_root()
    if root is None:
        return
    path = root / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:  # unreadable .env is not a reason to fail a request
        return
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _ENV_LINE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)
