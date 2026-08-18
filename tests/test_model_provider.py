"""The model-provider seam: selection, allocation, and what must be rejected.

Entirely offline. No API key, no network — every provider behaviour that can be
checked without a live model is checked here, because a suite that needs a paid
credential is a suite that stops being run.

The live counterpart is `tests/test_zai_live.py`, which is skipped unless
`ZAI_API_KEY` is present.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from llm import (
    ANTHROPIC,
    ZAI,
    CallSite,
    ProviderError,
    SchemaViolation,
    build_provider,
    load_config,
    strictened,
    validate_against_schema,
)
from llm.anthropic_provider import AnthropicProvider
from llm.zai_provider import ZaiProvider, sanitise_arguments

# The domain expert's shape, in miniature: a nullable integer, a boolean and a
# nullable string. Every interesting failure mode lives in those three types.
SCHEMA = strictened({
    "type": "object",
    "properties": {
        "rows": {"type": ["integer", "null"]},
        "grounded": {"type": "boolean"},
        "quote": {"type": ["string", "null"]},
    },
    "required": ["rows", "grounded", "quote"],
})

ROUTE_SCHEMA = strictened({
    "type": "object",
    "properties": {"route": {"type": "string",
                             "enum": ["direct", "clarify", "data_request"]}},
    "required": ["route"],
})


# --- provider selection ------------------------------------------------------

def test_llm_backend_selects_the_anthropic_provider(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-not-a-real-key")
    assert isinstance(build_provider(), AnthropicProvider)


def test_llm_backend_selects_the_zai_provider(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    assert isinstance(build_provider(), ZaiProvider)


def test_an_unknown_backend_is_refused_by_name(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "definitely-not-a-provider")
    with pytest.raises(ValueError, match="not recognised"):
        load_config()


def test_zai_without_a_key_fails_at_construction(monkeypatch):
    """Better to fail on startup than on the first user question.

    `.env` loading is stubbed out: on a developer machine a real key is sitting
    in `.env`, and `load_config()` would put it straight back after `delenv`.
    """
    monkeypatch.setattr("llm.config._load_dotenv", lambda: None)
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    with pytest.raises(ProviderError) as caught:
        build_provider()
    assert caught.value.kind == "auth"


def test_the_default_backend_is_anthropic_so_nothing_changes_silently(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert load_config().backend == ANTHROPIC


# --- per-call-site model allocation -----------------------------------------

@pytest.mark.parametrize("call_site", list(CallSite))
def test_zai_model_allocation(monkeypatch, call_site):
    """Every call site runs glm-5.2 by default. The split remains *possible*
    - each site is independently overridable - but is not the shipped default."""
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    for var in ("SAMPLING_MODEL", "MCP_AGENT_MODEL", "HOST_AGENT_MODEL",
                "DOMAIN_EXPERT_MODEL", "ORCHESTRATOR_MODEL"):
        monkeypatch.delenv(var, raising=False)
    assert load_config().model_for(call_site) == "glm-5.2"


def test_no_call_site_falls_back_to_the_weaker_model(monkeypatch):
    """Measured, not assumed: glm-4.5-air scored 2/8 on the real routing schema.

    It chose the right route and then could not serialise `requested_rows`
    (`0.0`, `10000.0`, `1.25e-08`, once a 1,000-digit integer), so every failure
    collapsed into the safe default and the cheap path stopped being cheap. No
    call site may silently regress to it.
    """
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    for var in ("SAMPLING_MODEL", "MCP_AGENT_MODEL", "HOST_AGENT_MODEL",
                "DOMAIN_EXPERT_MODEL", "ORCHESTRATOR_MODEL"):
        monkeypatch.delenv(var, raising=False)
    config = load_config()
    assert "glm-4.5-air" not in set(config.models.values())


def test_every_call_site_can_be_overridden_by_configuration(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("DOMAIN_EXPERT_MODEL", "some-other-model")
    assert load_config().model_for(CallSite.DOMAIN_EXPERT) == "some-other-model"


def test_anthropic_allocation_is_unchanged_from_before_the_seam(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    for var in ("ORCHESTRATOR_MODEL", "SAMPLING_MODEL", "MCP_AGENT_MODEL",
                "HOST_AGENT_MODEL", "DOMAIN_EXPERT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    config = load_config()
    assert config.model_for(CallSite.ORCHESTRATOR) == "claude-haiku-4-5"
    assert config.model_for(CallSite.DOMAIN_EXPERT) == "claude-opus-5"


# --- token budgets -----------------------------------------------------------

def test_a_server_set_ceiling_is_raised_to_the_floor_never_lowered(monkeypatch):
    """MCP sampling lets the *server* set max_tokens; a reasoning model can eat it.

    Measured: glm-5.2 spent 13 of 16 tokens and 100 of 200 on reasoning, so a
    tight ceiling returns an empty completion rather than a short one.
    """
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    config = load_config()
    assert config.tokens_for(CallSite.SAMPLING, 400) >= 1024   # raised
    assert config.tokens_for(CallSite.SAMPLING, 4000) == 4000  # honoured
    assert config.tokens_for(CallSite.SAMPLING, None) >= 1024  # defaulted


# --- forced tool calling, not response_format --------------------------------

class _FakeCompletions:
    """Records the request and replays a scripted response."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return self.script.pop(0)


def _zai_with(script, monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    provider = ZaiProvider(load_config())
    completions = _FakeCompletions(script)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return provider, completions


def _reply(arguments: str | None = None, *, content: str = "",
           name: str = "emit_result", finish: str = "tool_calls"):
    calls = None
    if arguments is not None:
        calls = [SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(name=name, arguments=arguments))]
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason=finish)],
        model="glm-5.2", usage=None)


def test_zai_structured_output_uses_a_forced_tool_call(monkeypatch):
    """The non-negotiable. `response_format` must not be the guarantee.

    Z.AI answers HTTP 200 to `response_format={"type":"json_schema"}` and then
    ignores the field names, which parses cleanly and is wrong.
    """
    provider, completions = _zai_with(
        [_reply(json.dumps({"rows": 250, "grounded": True, "quote": "q"}))],
        monkeypatch)

    result = provider.structured_call(
        call_site=CallSite.DOMAIN_EXPERT, system="s", prompt="p", schema=SCHEMA)

    request = completions.requests[0]
    assert "response_format" not in request
    assert request["tool_choice"] == {
        "type": "function", "function": {"name": "emit_result"}}
    assert request["tools"][0]["function"]["parameters"] == SCHEMA
    assert result == {"rows": 250, "grounded": True, "quote": "q"}


def test_the_schema_is_sent_with_additional_properties_closed(monkeypatch):
    provider, completions = _zai_with(
        [_reply(json.dumps({"route": "direct"}))], monkeypatch)
    provider.structured_call(call_site=CallSite.ORCHESTRATOR, system="s",
                             prompt="p", schema=ROUTE_SCHEMA)
    sent = completions.requests[0]["tools"][0]["function"]["parameters"]
    assert sent["additionalProperties"] is False


# --- what must be rejected ---------------------------------------------------

@pytest.mark.parametrize("payload,reason", [
    ({"rows": 250},                                        "missing required fields"),
    ({"rows_required": 250, "grounded": True, "quote": "q"}, "renamed field"),
    ({"rows": 250.0125, "grounded": True, "quote": "q"},   "float for integer"),
    ({"rows": 250.0, "grounded": True, "quote": "q"},      "whole float for integer"),
    ({"rows": "250", "grounded": True, "quote": "q"},      "string for integer"),
    ({"rows": True, "grounded": True, "quote": "q"},       "bool for integer"),
    ({"rows": 250, "grounded": "yes", "quote": "q"},       "string for boolean"),
    ({"rows": [250], "grounded": True, "quote": "q"},      "array for integer"),
    ({"rows": 250, "grounded": True, "quote": "q", "x": 1}, "unexpected field"),
])
def test_structurally_wrong_output_is_rejected(monkeypatch, payload, reason):
    """Each of these is valid JSON. None of them is a valid answer.

    Two rounds are scripted because the provider is allowed exactly one
    corrective retry; the violation must survive it.
    """
    provider, _ = _zai_with(
        [_reply(json.dumps(payload)), _reply(json.dumps(payload))], monkeypatch)
    with pytest.raises(SchemaViolation):
        provider.structured_call(call_site=CallSite.DOMAIN_EXPERT, system="s",
                                 prompt="p", schema=SCHEMA)


def test_a_nullable_answer_is_accepted(monkeypatch):
    """The honesty contract: "the corpus does not say" must be expressible."""
    provider, _ = _zai_with(
        [_reply(json.dumps({"rows": None, "grounded": False, "quote": None}))],
        monkeypatch)
    result = provider.structured_call(call_site=CallSite.DOMAIN_EXPERT,
                                      system="s", prompt="p", schema=SCHEMA)
    assert result == {"rows": None, "grounded": False, "quote": None}


def test_an_invalid_enum_value_is_rejected(monkeypatch):
    provider, _ = _zai_with(
        [_reply(json.dumps({"route": "quant"})),
         _reply(json.dumps({"route": "quant"}))], monkeypatch)
    with pytest.raises(SchemaViolation):
        provider.structured_call(call_site=CallSite.ORCHESTRATOR, system="s",
                                 prompt="p", schema=ROUTE_SCHEMA)


def test_prose_instead_of_the_forced_call_is_not_treated_as_success(monkeypatch):
    """A model that ignores the forced call must not be quietly scraped."""
    prose = _reply(None, content="I'd be happy to help, but I need more context.")
    provider, _ = _zai_with([prose, prose], monkeypatch)   # survives the retry
    with pytest.raises(ProviderError) as caught:
        provider.structured_call(call_site=CallSite.DOMAIN_EXPERT, system="s",
                                 prompt="p", schema=SCHEMA)
    assert caught.value.kind == "no_tool_call"


def test_one_corrective_retry_is_attempted_and_only_one(monkeypatch):
    """Bounded. A deterministic violation must not become a retry storm."""
    good = json.dumps({"rows": 250, "grounded": True, "quote": "q"})
    provider, completions = _zai_with(
        [_reply(json.dumps({"rows": 250.5, "grounded": True, "quote": "q"})),
         _reply(good)], monkeypatch)

    result = provider.structured_call(call_site=CallSite.DOMAIN_EXPERT,
                                      system="s", prompt="p", schema=SCHEMA)
    assert result["rows"] == 250
    assert len(completions.requests) == 2
    # The retry must tell the model what was actually wrong.
    correction = completions.requests[1]["messages"][-1]["content"]
    assert "output contract" in correction and "250.5" in correction


def test_a_persistent_violation_is_not_retried_forever(monkeypatch):
    bad = json.dumps({"rows": 250.5, "grounded": True, "quote": "q"})
    provider, completions = _zai_with([_reply(bad), _reply(bad)], monkeypatch)
    with pytest.raises(SchemaViolation, match="unchanged after one corrective retry"):
        provider.structured_call(call_site=CallSite.DOMAIN_EXPERT, system="s",
                                 prompt="p", schema=SCHEMA)
    assert len(completions.requests) == 2


# --- the observed serialisation defect ---------------------------------------

@pytest.mark.parametrize("raw,expected", [
    # Observed verbatim on glm-4.5-air: stop token leaked into the arguments and
    # the closing brace lost.
    ('{"route":"direct","requested_rows":-1.0\n</tool_call>',
     {"route": "direct", "requested_rows": -1.0}),
    ('{"a":1}', {"a": 1}),
    ('{"a":{"b":[1,2', {"a": {"b": [1, 2]}}),
    ('{"a":1,', {"a": 1}),
    ('{"a":"unterminated', {"a": "unterminated"}),
    # A brace inside a string must not be mistaken for a closer.
    ('{"a":"} not a closer"', {"a": "} not a closer"}),
])
def test_leaked_stop_tokens_and_truncation_are_repaired(raw, expected):
    assert json.loads(sanitise_arguments(raw)) == expected


def test_the_repair_cannot_invent_a_value(monkeypatch):
    """Structure only. A repaired object that is wrong is still rejected."""
    provider, _ = _zai_with(
        [_reply('{"rows":250,"grounded":true\n</tool_call>'),
         _reply('{"rows":250,"grounded":true\n</tool_call>')], monkeypatch)
    with pytest.raises(SchemaViolation, match="quote"):
        provider.structured_call(call_site=CallSite.DOMAIN_EXPERT, system="s",
                                 prompt="p", schema=SCHEMA)


# --- no domain value is baked in anywhere ------------------------------------

@pytest.mark.parametrize("window", [30, 60, 90, 125, 250, 365, 500, 750])
def test_any_window_the_corpus_states_is_carried_through(monkeypatch, window):
    """250 was a smoke-test value, not an architectural assumption."""
    provider, _ = _zai_with(
        [_reply(json.dumps({"rows": window, "grounded": True, "quote": "q"}))],
        monkeypatch)
    result = provider.structured_call(call_site=CallSite.DOMAIN_EXPERT,
                                      system="s", prompt="p", schema=SCHEMA)
    assert result["rows"] == window


def test_no_domain_constant_is_hardcoded_in_the_model_layer():
    """The one number that must never appear as a value anywhere.

    Parsed rather than grepped: the string "250" legitimately appears in prose
    describing the observed defect, and a text search cannot tell a docstring
    from a default. This looks for the integer literal itself.
    """
    import ast  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    offenders = []
    for path in Path("llm/src/llm").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, int)
                    and not isinstance(node.value, bool) and node.value == 250):
                offenders.append(f"{path}:{node.lineno}")
    assert offenders == [], f"domain values must come from the corpus: {offenders}"


# --- provider neutrality of message shapes -----------------------------------

def test_each_provider_shapes_tool_results_its_own_way(monkeypatch):
    """The host loop stays neutral because this difference is hidden here."""
    monkeypatch.setenv("LLM_BACKEND", "zai")
    monkeypatch.setenv("ZAI_API_KEY", "placeholder-not-a-real-key")
    zai = ZaiProvider(load_config())

    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "placeholder-not-a-real-key")
    anthropic = AnthropicProvider(load_config())

    results = [("call_1", "ok", False), ("call_2", "boom", True)]

    # OpenAI-compatible: one message per result.
    shaped = zai.tool_result_message(results)
    assert isinstance(shaped, list) and len(shaped) == 2
    assert shaped[0]["role"] == "tool" and shaped[0]["tool_call_id"] == "call_1"

    # Anthropic: all results in a single user turn.
    shaped = anthropic.tool_result_message(results)
    assert isinstance(shaped, dict) and shaped["role"] == "user"
    assert len(shaped["content"]) == 2
    assert shaped["content"][1]["is_error"] is True


def test_validation_reports_every_problem_not_just_the_first():
    with pytest.raises(SchemaViolation) as caught:
        validate_against_schema({"rows": "x", "grounded": 3}, SCHEMA)
    message = str(caught.value)
    assert "rows" in message and "grounded" in message and "quote" in message


def test_prose_instead_of_the_forced_call_gets_one_corrective_retry(monkeypatch):
    """Observed on glm-5.2 composing the final reply: a prose task resists the
    forced-tool wrapper. One correction is allowed; a transport failure is not."""
    good = json.dumps({"rows": 250, "grounded": True, "quote": "q"})
    provider, completions = _zai_with(
        [_reply(None, content="Here is the answer in prose."), _reply(good)],
        monkeypatch)
    result = provider.structured_call(call_site=CallSite.ORCHESTRATOR, system="s",
                                      prompt="p", schema=SCHEMA)
    assert result["rows"] == 250
    assert len(completions.requests) == 2
    assert "no prose outside the call" in completions.requests[1]["messages"][-1]["content"]


def test_a_transport_failure_is_never_retried_by_the_provider(monkeypatch):
    """The SDK already retries those. Retrying an expensive reasoning request on
    a timeout is how a retry storm starts."""
    provider, completions = _zai_with([], monkeypatch)

    def boom(**_request):
        raise TimeoutError("read timed out")

    completions.create = boom
    with pytest.raises(ProviderError) as caught:
        provider.structured_call(call_site=CallSite.DOMAIN_EXPERT, system="s",
                                 prompt="p", schema=SCHEMA)
    assert caught.value.kind == "timeout"
