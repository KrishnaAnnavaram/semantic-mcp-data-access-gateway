"""LangSmith observability — status, configuration and the fail-open contract.

These are unit tests over `agents.observability`. They never require LangSmith to
be installed or reachable: the whole point of this layer is that tracing degrades
to a no-op rather than failing a request, and that is exactly what is asserted
here.

`_load_env` is neutralised in the status tests so a developer's real `.env`
cannot make them flap — the environment under test is only what each test sets.
"""

from __future__ import annotations

import pytest

import agents.observability as obs

TRACE_ENV = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGSMITH_API_KEY",
             "LANGCHAIN_API_KEY", "LANGSMITH_PROJECT", "LANGCHAIN_PROJECT",
             "LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT", "LANGSMITH_WORKSPACE_ID",
             "LANGCHAIN_WORKSPACE_ID")


@pytest.fixture
def clean_env(monkeypatch):
    """A blank LangSmith environment, with `.env` loading disabled."""
    monkeypatch.setattr(obs, "_load_env", lambda: None)
    for name in TRACE_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# --- status matrix ----------------------------------------------------------


def test_disabled_when_neither_flag_nor_key(clean_env):
    status = obs.langsmith_status()
    assert status["enabled"] is False
    assert status["api_key_configured"] is False
    assert "set LANGSMITH_TRACING=true" in status["reason"]


def test_flag_only_explains_the_missing_key(clean_env):
    clean_env.setenv("LANGSMITH_TRACING", "true")
    status = obs.langsmith_status()
    assert status["enabled"] is False
    assert "no API key" in status["reason"]
    assert status["tracing_flag"] is True
    assert status["api_key_configured"] is False


def test_key_only_explains_the_missing_flag(clean_env):
    clean_env.setenv("LANGSMITH_API_KEY", "lsv2_secret")
    status = obs.langsmith_status()
    assert status["enabled"] is False
    assert "not 'true'" in status["reason"]
    assert status["api_key_configured"] is True


def test_flag_and_key_enable_tracing(clean_env):
    clean_env.setenv("LANGSMITH_TRACING", "true")
    clean_env.setenv("LANGSMITH_API_KEY", "lsv2_secret")
    status = obs.langsmith_status()
    assert status["enabled"] is True
    assert status["configured"] is True
    assert status["api_key_configured"] is True
    assert "sent to LangSmith" in status["reason"]


def test_status_never_contains_the_api_key(clean_env):
    clean_env.setenv("LANGSMITH_TRACING", "true")
    clean_env.setenv("LANGSMITH_API_KEY", "lsv2_super_secret_value")
    status = obs.langsmith_status()
    assert "lsv2_super_secret_value" not in repr(status)


def test_project_resolves_default_and_override(clean_env):
    assert obs.project_name() == obs.DEFAULT_PROJECT
    clean_env.setenv("LANGSMITH_PROJECT", "my-project")
    assert obs.project_name() == "my-project"


def test_endpoint_default_and_override(clean_env):
    assert obs.endpoint() == obs.DEFAULT_ENDPOINT
    clean_env.setenv("LANGSMITH_ENDPOINT", "https://eu.smith.langchain.com")
    assert obs.endpoint() == "https://eu.smith.langchain.com"


def test_workspace_recognised_when_set(clean_env):
    assert obs.workspace_id() is None
    assert obs.langsmith_status()["workspace_configured"] is False
    clean_env.setenv("LANGSMITH_WORKSPACE_ID", "ws-123")
    assert obs.workspace_id() == "ws-123"
    assert obs.langsmith_status()["workspace_configured"] is True


# --- Redis rate limiting is visible in the trace ----------------------------


def test_rate_limited_call_is_tagged_for_langsmith(monkeypatch):
    """A call the native rate limiter rejects still marks the open span.

    Without this, a call the limiter blocked returns `None` exactly like a
    schema violation or a provider outage — nothing in the trace could tell a
    reader which of the three actually happened.
    """
    metadata_calls: list[dict] = []
    tag_calls: list[tuple] = []
    monkeypatch.setattr(obs, "set_run_metadata", lambda **kw: metadata_calls.append(kw))
    monkeypatch.setattr(obs, "set_run_tags", lambda *tags: tag_calls.append(tags))

    class _Blocked:
        def allow_llm(self, agent):
            del agent
            return False

    import agents.cache as cache_module

    monkeypatch.setattr(cache_module, "get_intelligence", lambda: _Blocked())

    from llm import CallSite

    result = obs.structured_call(
        call_site=CallSite.DOMAIN_EXPERT, system="s", prompt="p", schema={}
    )

    assert result is None
    assert obs.last_failure_kind() == "rate_limit"
    assert any(call.get("failure_kind") == "rate_limit" for call in metadata_calls)
    assert ("call_site:domain_expert", "rate_limited") in tag_calls


def test_legacy_langchain_variables_still_work(clean_env):
    clean_env.setenv("LANGCHAIN_TRACING_V2", "true")
    clean_env.setenv("LANGCHAIN_API_KEY", "lsv2_legacy")
    clean_env.setenv("LANGCHAIN_PROJECT", "legacy-project")
    status = obs.langsmith_status()
    assert status["enabled"] is True
    assert status["project"] == "legacy-project"


# --- fail-open contract (no LangSmith installed / tracing off) --------------


def test_helpers_are_no_ops_when_tracing_disabled(clean_env):
    # With no flag/key, tracing_enabled() is False and every helper degrades to
    # doing nothing — and, crucially, none of them raises.
    assert obs.tracing_enabled() is False
    assert obs.current_trace_headers() is None
    assert obs.run_url() is None
    assert obs.run_id() is None
    # These must be safe to call unconditionally from hot paths.
    obs.set_run_metadata(route="data_request", model="glm-5.2")
    obs.set_run_tags("route:data_request")


def test_continue_trace_is_a_transparent_no_op(clean_env):
    entered = False
    with obs.continue_trace({"langsmith-trace": "x", "baggage": "y"}):
        entered = True
    assert entered is True


def test_continue_trace_with_none_is_a_no_op(clean_env):
    with obs.continue_trace(None):
        pass  # must not raise


def test_span_runs_the_block_untraced(clean_env):
    ran = False
    with obs.span("mcp.call:get_curve", "tool", tool_name="get_curve"):
        ran = True
    assert ran is True


def test_span_does_not_swallow_the_blocks_own_error(clean_env):
    with pytest.raises(ValueError):
        with obs.span("postgres.query", "tool"):
            raise ValueError("the block's own failure must propagate")


def test_app_metadata_is_present_and_safe(clean_env):
    meta = obs.app_metadata()
    assert meta["application"] == "smcp-gateway"
    assert "environment" in meta
    # No secret should ever be stamped as trace metadata.
    assert not any("key" in k.lower() for k in meta)


def test_trace_header_key_constant_is_stable():
    # The envelope and the observability layer must agree on this key, or
    # propagation silently stops working.
    assert obs.TRACE_HEADER_KEY == "langsmith_trace"
