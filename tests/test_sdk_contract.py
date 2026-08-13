"""Pin the MCP SDK facts the whole design rests on.

These are not tests of our code. They are tests of an assumption: that the
installed SDK actually implements protocol 2026-07-28 and the three features
the architecture depends on. If a dependency bump quietly drops one of them,
this fails here rather than three layers deeper.
"""

from __future__ import annotations

import importlib.metadata

import mcp.types as types


def test_protocol_revision_is_2026_07_28() -> None:
    """1.x tops out at 2025-11-25 and has no MRTR. 2.0.0 is the floor."""
    assert types.LATEST_PROTOCOL_VERSION == "2026-07-28"
    major = int(importlib.metadata.version("mcp").split(".", 1)[0])
    assert major >= 2, "mcp 1.x uses camelCase fields and lacks InputRequiredResult"


def test_mrtr_is_available() -> None:
    """Elicitation is delivered by returning InputRequiredResult from a tool."""
    assert hasattr(types, "InputRequiredResult")
    assert "input_requests" in types.InputRequiredResult.model_fields


def test_tool_results_carry_structured_content_and_meta() -> None:
    """The bulk-routing design needs both channels on one result.

    `structured_content` is what the model reads; `meta` is the application
    channel the host reads. A 250-day x 11-tenor matrix is ~2,750 numbers that
    must reach the risk engine without ever entering model context.
    """
    fields = types.CallToolResult.model_fields
    assert "structured_content" in fields
    assert "meta" in fields
    assert "result_type" in fields


def test_list_results_carry_cache_hints() -> None:
    """Catalogue listings are stable for long periods; the protocol lets us say so."""
    for model in (types.ListToolsResult, types.ListResourcesResult):
        assert "ttl_ms" in model.model_fields
        assert "cache_scope" in model.model_fields


def test_servers_declare_no_deprecated_capabilities() -> None:
    """Sampling and Roots are deprecated as of this revision (SEP-2577).

    Both are *client* features a server may request. Neither server here asks
    for them: the data server needs no model, and the risk engine must not have
    one. Asserted against the real capability declaration rather than a comment,
    so adding a sampling call later fails this test.
    """
    import inspect  # noqa: PLC0415

    from mcp_servers.data import server as data_module  # noqa: PLC0415

    source = inspect.getsource(data_module)
    for deprecated in ("sampling/createMessage", "create_message", "roots/list"):
        assert deprecated not in source, (
            f"{deprecated!r} is deprecated in protocol 2026-07-28 (SEP-2577) "
            "and must not be introduced"
        )
