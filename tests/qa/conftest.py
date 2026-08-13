"""Shared fixtures for the tiered QA suite.

Tiers 1-2 are pure and always run. Tiers 3-5 need PostgreSQL. Tier 6 needs the
HTTP service. Each dependency is probed once per session and the dependent tests
*skip* rather than fail, so a red result always means a real defect and never
"the developer forgot to start Docker".
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

API_BASE = "http://localhost:8000"


@pytest.fixture(scope="session")
def db():
    """A live connection factory, or skip the whole tier."""
    try:
        from mcp_servers.data._db import connect
        with connect() as conn:
            conn.cursor().execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}: {exc}")
    return connect


@pytest.fixture(scope="session")
def api():
    """Base URL of the running /chat service, or skip the tier."""
    try:
        with urllib.request.urlopen(f"{API_BASE}/health", timeout=5) as response:
            payload = json.loads(response.read())
        if payload.get("status") != "ok":
            pytest.skip(f"/health reported {payload}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        pytest.skip(f"backend service unavailable: {exc}")
    return API_BASE


def post_chat(base: str, query: str, session_id: str, timeout: float = 300.0) -> dict:
    """One /chat turn. Kept here so tier 6 reads as behaviour, not plumbing."""
    body = json.dumps({"query": query, "session_id": session_id}).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


@pytest.fixture(scope="session")
def call_tool():
    """Call an MCP data tool in-process (see `call_tool_sync`)."""
    return call_tool_sync


@pytest.fixture(scope="session")
def failing_tool():
    """Provoke a domain error and return its structured body (see `tool_error`)."""
    return tool_error


@pytest.fixture(scope="session")
def chat(api):
    """One /chat turn against the live service."""
    def _chat(query: str, session_id: str, timeout: float = 300.0) -> dict:
        return post_chat(api, query, session_id, timeout)
    return _chat


def call_tool_sync(name: str, arguments: dict):
    """Call an MCP data tool in-process and return the result object.

    Only valid for tools without `Resolve(...)` parameters — a resolver needs a
    request context that this path does not create. The three client-directed
    tools are covered end-to-end by `tools/verify_mcp.py` instead.
    """
    import anyio

    from mcp_servers.data.server import server

    return anyio.run(lambda: server.call_tool(name, arguments))


def tool_error(name: str, arguments: dict) -> dict:
    """Provoke a domain error and return its structured body.

    Returns `{}` when the call unexpectedly succeeds, so a test that expects a
    refusal fails loudly rather than passing on an empty dict.
    """
    try:
        call_tool_sync(name, arguments)
    except Exception as exc:  # noqa: BLE001 - the error IS the assertion target
        text = str(exc)
        start = text.find("{")
        if start >= 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                return {"_unparsed": text}
        return {"_unparsed": text}
    return {}
