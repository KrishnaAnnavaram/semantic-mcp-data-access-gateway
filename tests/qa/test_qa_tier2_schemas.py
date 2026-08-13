"""Tier 2 — the advertised surface. What a client sees before it calls anything.

A tool the model cannot select correctly is worse than a missing one: it gets
called anyway, with plausible arguments, and returns something the model then
reasons from. So the schema, the description and the annotations are part of the
contract and are asserted here.
"""

from __future__ import annotations

import anyio
import pytest

from mcp_servers.data.server import server as data_server
from mcp_servers.risk.server import server as risk_server

BANNED_PARAMETER_NAMES = {"columns", "table", "schema", "order_by", "sql", "where"}

# Tools whose destination or wording is supplied by the client mid-call. Their
# resolved parameters must never appear in the schema the model fills in.
RESOLVED_PARAMETERS = {"choice", "roots", "drafted"}


def _tools(server):
    return anyio.run(server.list_tools)


@pytest.fixture(scope="module")
def data_tools():
    return _tools(data_server)


@pytest.fixture(scope="module")
def risk_tools():
    return _tools(risk_server)


# --- inventory --------------------------------------------------------------


def test_the_data_server_advertises_its_full_tool_set(data_tools):
    assert len(data_tools) >= 14


def test_the_risk_server_advertises_its_full_tool_set(risk_tools):
    assert len(risk_tools) >= 5


def test_tool_names_are_unique_within_each_server(data_tools, risk_tools):
    for tools in (data_tools, risk_tools):
        names = [t.name for t in tools]
        assert len(names) == len(set(names))


def test_tool_names_do_not_collide_across_servers(data_tools, risk_tools):
    """The host merges both into one namespace; a collision silently shadows."""
    assert not ({t.name for t in data_tools} & {t.name for t in risk_tools})


# --- every tool is selectable and parseable ---------------------------------


def test_every_tool_is_described(data_tools, risk_tools):
    """An undescribed tool cannot be selected correctly."""
    undescribed = [t.name for t in data_tools + risk_tools if not (t.description or "").strip()]
    assert undescribed == []


def test_every_tool_declares_an_output_schema(data_tools, risk_tools):
    """Structured results, not prose the model has to parse back."""
    missing = [t.name for t in data_tools + risk_tools if not t.output_schema]
    assert missing == []


def test_every_tool_declares_annotations(data_tools, risk_tools):
    missing = [t.name for t in data_tools + risk_tools if not t.annotations]
    assert missing == []


def test_no_tool_is_marked_destructive(data_tools, risk_tools):
    destructive = [t.name for t in data_tools + risk_tools
                   if t.annotations and t.annotations.destructive_hint]
    assert destructive == []


def test_tool_listing_is_deterministic():
    """A stable order lets a client cache tools/list and keeps the prompt cache warm."""
    assert [t.name for t in _tools(data_server)] == [t.name for t in _tools(data_server)]


# --- the SQL boundary -------------------------------------------------------


def test_no_tool_offers_a_sql_escape_hatch(data_tools, risk_tools):
    """A run_sql tool would move schema knowledge into the prompt."""
    suspicious = [t.name for t in data_tools + risk_tools
                  if any(word in t.name.lower()
                         for word in ("sql", "query", "execute", "raw", "eval"))]
    assert suspicious == []


def test_no_tool_accepts_a_parameter_that_shapes_sql(data_tools, risk_tools):
    """Callers supply values; the templates live in repository.py."""
    offenders = []
    for tool in data_tools + risk_tools:
        for name in (tool.input_schema or {}).get("properties", {}):
            if name.lower() in BANNED_PARAMETER_NAMES:
                offenders.append(f"{tool.name}.{name}")
    assert offenders == []


# --- client-directed tools --------------------------------------------------


def test_resolved_parameters_are_hidden_from_the_model(data_tools):
    """A resolver is filled by the framework, never by the LLM.

    If one leaked into the schema the model would invent a value for it and the
    elicitation, roots or sampling request would never be raised.
    """
    leaked = []
    for tool in data_tools:
        for name in (tool.input_schema or {}).get("properties", {}):
            if name in RESOLVED_PARAMETERS:
                leaked.append(f"{tool.name}.{name}")
    assert leaked == []


def test_the_only_writing_tool_is_the_declared_one(data_tools):
    """Read-only is not the invariant; "cannot write to the source of record" is."""
    writers = {t.name for t in data_tools
               if not (t.annotations and t.annotations.read_only_hint)}
    assert writers == {"export_curve_csv"}


@pytest.mark.parametrize("name", ["search_series", "export_curve_csv", "brief_dataset_caveat"])
def test_each_client_directed_tool_is_present(data_tools, name):
    assert name in {t.name for t in data_tools}


# --- resources and prompts --------------------------------------------------


def test_both_servers_expose_resources():
    for server in (data_server, risk_server):
        assert len(anyio.run(server.list_resources)) >= 2


def test_both_servers_expose_prompts():
    """Prompts are the server's own recommended tool ordering."""
    for server in (data_server, risk_server):
        assert len(anyio.run(server.list_prompts)) >= 3


def test_prompts_are_uniquely_named():
    for server in (data_server, risk_server):
        names = [p.name for p in anyio.run(server.list_prompts)]
        assert len(names) == len(set(names))
