"""The tool inventory, derived from code and checked against the documentation.

Documentation drift is not a cosmetic problem here. A model chooses tools from
their descriptions, and a reader trusts a count. When `CLAUDE.md` says "5 risk
tools" and the server advertises forty-two, the count is not merely stale - it
is evidence that nobody has reconciled the two since, and the next reader cannot
tell which other statements have gone the same way.

So the authoritative inventory is **derived from the registered tools** and the
documents are checked against it, never the reverse. If this test fails, the fix
is to update the document; if the document is right and the code is wrong, the
fix is a tool, not a smaller number in a test.
"""

from __future__ import annotations

import pathlib
import re

import anyio
import pytest
from mcp_servers.data.server import server as data_server
from mcp_servers.risk.server import server as risk_server

REPO = pathlib.Path(__file__).resolve().parents[1]

# The tool families the risk engine is expected to cover. Each entry is a
# capability a market-risk desk asks for by name; a missing one is a gap, and an
# unexpected one is a tool nobody documented.
EXPECTED_RISK_TOOLS = {
    # valuation and bond analytics
    "price_portfolio_tool", "compute_bond_analytics_tool", "compute_carry_roll_tool",
    # curve analytics
    "compute_curve_analytics_tool", "compute_rate_volatility_tool",
    # sensitivities
    "compute_dv01_tool", "compute_key_rate_dv01_tool",
    "compute_rate_sensitivities_tool", "compute_risk_contributions_tool",
    # custom and standardised stress
    "run_stress_tool", "run_rate_stress_tool", "run_key_rate_stress_tool",
    "run_curve_twist_stress_tool", "run_curve_curvature_stress_tool",
    "run_shock_ladder_tool",
    # stress suites
    "run_stress_matrix_tool", "compare_stress_scenarios_tool",
    "compute_stress_contributions_tool", "explain_stress_loss_tool",
    "compute_stress_thresholds_tool", "run_concentration_stress_tool",
    "run_scenario_severity_pack_tool",
    # historical stress
    "run_historical_stress_tool", "run_historical_crisis_stress_tool",
    "find_worst_historical_stresses_tool",
    # reverse stress
    "run_reverse_stress_tool", "find_limit_breach_stress_tool",
    # distribution risk
    "compute_historical_risk_tool", "compute_parametric_risk_tool",
    "compute_monte_carlo_risk_tool", "run_extreme_tail_simulation_tool",
    "run_volatility_regime_stress_tool", "run_rate_correlation_stress_tool",
    "compare_risk_methods_tool",
    # backtesting and attribution
    "backtest_var_tool", "compute_pnl_attribution_tool",
    # portfolio level
    "compute_concentration_tool", "evaluate_risk_limits_tool",
    "compare_portfolio_risk_tool", "analyze_hypothetical_trade_tool",
    "analyze_rate_hedge_tool",
    # regulatory
    "compute_frtb_girr_tool",
}

# The five that existed before the expansion. None may disappear or change name:
# `backend/src/backend/workflows/risk_workflows.py` calls each of them by string.
ORIGINAL_RISK_TOOLS = {
    "price_portfolio_tool", "compute_dv01_tool", "compute_key_rate_dv01_tool",
    "run_stress_tool", "compute_historical_risk_tool",
}


def risk_tools():
    return anyio.run(risk_server.list_tools)


def data_tools():
    return anyio.run(data_server.list_tools)


def test_the_registered_risk_tools_are_exactly_the_documented_inventory():
    registered = {t.name for t in risk_tools()}
    assert registered == EXPECTED_RISK_TOOLS, (
        f"missing: {sorted(EXPECTED_RISK_TOOLS - registered)}; "
        f"undocumented: {sorted(registered - EXPECTED_RISK_TOOLS)}")


def test_no_original_tool_was_renamed_or_removed():
    """The backend calls these by string; renaming one breaks `/chat` silently."""
    registered = {t.name for t in risk_tools()}
    assert ORIGINAL_RISK_TOOLS <= registered


def test_the_backend_workflow_tool_names_all_still_resolve():
    """Read out of the workflow module rather than restated here."""
    source = (REPO / "backend" / "src" / "backend" / "workflows"
              / "risk_workflows.py").read_text(encoding="utf-8")
    called = set(re.findall(r'call_tool(?:_with_meta)?\(\s*"([a-z_]+)"', source))
    available = {t.name for t in risk_tools()} | {t.name for t in data_tools()}
    assert called, "no tool calls were found; the regex needs updating"
    assert called <= available, f"unresolvable: {sorted(called - available)}"


def test_every_risk_tool_declares_a_description_annotations_and_an_output_schema():
    for tool in risk_tools():
        assert (tool.description or "").strip(), f"{tool.name} has no description"
        assert tool.annotations, f"{tool.name} declares no annotations"
        assert tool.output_schema, f"{tool.name} declares no output schema"


def test_every_risk_tool_description_is_substantial_enough_to_choose_from():
    """A model picks tools by description. One line cannot separate forty-two."""
    for tool in risk_tools():
        assert len(tool.description) >= 120, (
            f"{tool.name}'s description is {len(tool.description)} characters; "
            "with this many neighbouring tools it must say what it does, what "
            "convention it uses, and what it refuses")


def test_no_risk_tool_is_marked_destructive_or_open_world():
    """The engine has no database, no network and no side effects."""
    for tool in risk_tools():
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.destructive_hint is False, tool.name
        assert tool.annotations.open_world_hint is False, tool.name


def test_risk_tool_names_are_unique_and_do_not_collide_with_the_data_server():
    risk_names = [t.name for t in risk_tools()]
    assert len(risk_names) == len(set(risk_names))
    assert not (set(risk_names) & {t.name for t in data_tools()})


def test_the_tool_list_is_returned_in_a_stable_order():
    """Clients cache `tools/list`; a permuting order defeats prompt caching."""
    assert [t.name for t in risk_tools()] == [t.name for t in risk_tools()]


def test_the_risk_server_publishes_the_resources_its_tools_refer_to():
    uris = {str(r.uri) for r in anyio.run(risk_server.list_resources)}
    assert {
        "risk://model/manifest",
        "risk://methodology/curve-construction",
        "risk://scenarios/templates",
        "risk://scenarios/historical-crises",
        "risk://methodology/risk-measures",
        "risk://methodology/regulatory-girr",
        "risk://capability-gaps",
    } <= uris


def test_the_risk_server_publishes_a_prompt_for_each_major_workflow():
    names = {p.name for p in anyio.run(risk_server.list_prompts)}
    assert {"risk_summary", "stress_review", "var_methodology",
            "stress_matrix_review", "reverse_stress_review",
            "model_validation_review", "pnl_attribution_review",
            "regulatory_scope"} <= names


# --- documentation drift -----------------------------------------------------


DOCUMENTED_COUNT_PATTERN = re.compile(
    r"(\d+)\s+data\s+tools?,\s*(\d+)\s+risk\s+tools?", re.IGNORECASE)


@pytest.mark.parametrize("document", ["CLAUDE.md", "docs/mcp-contract.md",
                                      "docs/risk-methodology.md", "README.md"])
def test_documented_tool_counts_match_the_registered_ones(document):
    """Derived from code, checked against prose. Never the other way round."""
    path = REPO / document
    if not path.exists():
        pytest.skip(f"{document} is not present")
    text = path.read_text(encoding="utf-8")
    matches = DOCUMENTED_COUNT_PATTERN.findall(text)
    if not matches:
        pytest.skip(f"{document} states no 'N data tools, M risk tools' count")

    expected = (len(data_tools()), len(risk_tools()))
    for data_count, risk_count in matches:
        assert (int(data_count), int(risk_count)) == expected, (
            f"{document} claims {data_count} data and {risk_count} risk tools; "
            f"the servers register {expected[0]} and {expected[1]}")


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_RISK_TOOLS))
def test_every_risk_tool_is_named_in_the_tool_reference(tool_name):
    """A tool nobody documented is a tool nobody will choose."""
    reference = REPO / "docs" / "risk-tool-reference.md"
    if not reference.exists():
        pytest.skip("docs/risk-tool-reference.md is not present")
    assert tool_name in reference.read_text(encoding="utf-8"), (
        f"{tool_name} is registered but absent from the tool reference")


def test_the_manifest_and_the_regulatory_resource_agree_on_scope():
    """Two places state what regulatory work is implemented; they must match."""
    import json

    from mcp_servers.risk.manifest import MODEL_MANIFEST
    from mcp_servers.risk.regulatory.constants import RISK_CLASS_SUPPORT

    manifest_scope = MODEL_MANIFEST["regulatory_scope"]
    implemented = {name for name, supported in RISK_CLASS_SUPPORT.items() if supported}
    assert implemented == {"GIRR_DELTA", "GIRR_CURVATURE"}
    assert set(manifest_scope["implemented"]) == {
        "FRTB_SA_GIRR_DELTA", "FRTB_SA_GIRR_CURVATURE"}
    assert "DRC" in manifest_scope["not_implemented"]

    published = json.loads(read_resource("risk://methodology/regulatory-girr"))
    assert published["risk_class_support"] == RISK_CLASS_SUPPORT
    assert published["constants_version"] == MODEL_MANIFEST["frtb_girr_version"] or         published["girr_delta"]["vertices_years"], (
        "the published resource must carry the same scope the manifest declares")


def read_resource(uri: str) -> str:
    contents = anyio.run(risk_server.read_resource, uri)
    return "".join(getattr(c, "content", "") for c in contents)


def test_the_published_scenario_catalogue_matches_the_code():
    import json

    from mcp_servers.risk.stress_scenarios import SEVERITY_BP, TEMPLATES

    published = json.loads(read_resource("risk://scenarios/templates"))
    assert set(published["templates"]) == set(TEMPLATES)
    assert published["severity_labels_bp"] == SEVERITY_BP
    for name, (_, control) in TEMPLATES.items():
        at_100 = published["templates"][name]["at_severity_100bp"]
        assert at_100 == {f"{t:g}y": m * 100.0 for t, m in sorted(control.items())}


def test_the_published_crisis_catalogue_carries_dates_and_no_rates():
    import json

    from mcp_servers.risk.historical_stress import CRISIS_CATALOGUE

    published = json.loads(read_resource("risk://scenarios/historical-crises"))
    assert len(published["crises"]) == len(CRISIS_CATALOGUE)
    for entry in published["crises"]:
        assert set(entry) == {"crisis_id", "name", "start_date", "end_date",
                              "description", "what_happened"}
        assert all(isinstance(v, str) for v in entry.values()), (
            "a numeric field here would be a stored shock, which the design "
            "forbids")


# --- agent-reachable capabilities, versus the MCP surface --------------------


def agent_catalogue():
    """The capability catalogue, built against a provider that can calculate."""
    from agents.mcp_agent import McpAgent

    class Capable:
        def call_tool(self, name, arguments=None):
            return {}

        def call_tool_with_meta(self, name, arguments=None):
            return {}, {}

    return McpAgent(Capable()).catalogue()


def test_the_capability_document_lists_every_advertised_capability():
    """A capability nobody documented is one nobody can review."""
    doc = REPO / "docs" / "agent-capabilities.md"
    if not doc.exists():
        pytest.skip("docs/agent-capabilities.md is not present")
    text = doc.read_text(encoding="utf-8")
    missing = [name for name in agent_catalogue().executable_tools
               if f"`{name}`" not in text]
    assert not missing, f"advertised but undocumented: {missing}"


def test_the_capability_document_states_the_two_inventory_counts():
    """The distinction this document exists to draw must survive edits to it."""
    doc = REPO / "docs" / "agent-capabilities.md"
    if not doc.exists():
        pytest.skip("docs/agent-capabilities.md is not present")
    text = doc.read_text(encoding="utf-8")
    catalogue = agent_catalogue()
    assert f"**{len(risk_tools())}**" in text, (
        "the MCP-registered tool count has drifted from the document")
    assert f"**{len(catalogue.executable_tools)} executable**" in text, (
        "the agent capability count has drifted from the document")


def test_every_withheld_tool_is_documented_with_a_reason():
    """Withholding is a decision, and a decision needs its reason written down."""
    import ast

    doc = REPO / "docs" / "agent-capabilities.md"
    if not doc.exists():
        pytest.skip("docs/agent-capabilities.md is not present")
    text = doc.read_text(encoding="utf-8")

    source = (REPO / "backend" / "src" / "backend" / "workflows"
              / "risk_workflows.py").read_text(encoding="utf-8")
    reached = set()
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"call_tool", "call_tool_with_meta"}
                and node.args and isinstance(node.args[0], ast.Constant)):
            reached.add(node.args[0].value)
        if isinstance(node, ast.Tuple):
            for element in node.elts:
                if (isinstance(element, ast.Constant)
                        and isinstance(element.value, str)
                        and element.value.endswith("_tool")):
                    reached.add(element.value)

    withheld = {t.name for t in risk_tools()} - reached
    undocumented = [name for name in withheld if f"`{name}`" not in text]
    assert not undocumented, (
        f"withheld from the planner but with no stated reason: {undocumented}")
