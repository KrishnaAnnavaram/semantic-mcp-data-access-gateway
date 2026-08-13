"""Tier 5 — the boundaries. Adversarial input and separation of duties.

These are the guarantees the architecture is built around, so each is tested by
trying to break it rather than by reading the code that implements it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# --- injection --------------------------------------------------------------

INJECTIONS = [
    "BC_10YEAR'; DROP TABLE treasury.observation; --",
    "BC_10YEAR' OR '1'='1",
    "'; SELECT pg_sleep(10); --",
    "BC_10YEAR\"; DELETE FROM analytics.v_mcp_observation; --",
    "BC_10YEAR' UNION SELECT NULL,NULL,NULL --",
    "%' --",
]


@pytest.mark.parametrize("payload", INJECTIONS)
def test_sql_metacharacters_die_at_the_catalogue_boundary(payload, failing_tool, db):
    """Rejected as an unknown series, never interpolated into SQL."""
    err = failing_tool("get_rate_history", {
        "series_codes": [payload], "start_date": "2026-01-01", "end_date": "2026-02-01"})
    assert err.get("error_code") == "UNKNOWN_SERIES"


@pytest.mark.parametrize("payload", INJECTIONS)
def test_injection_through_search_leaves_the_database_intact(payload, db):
    """The search path is lexical; a payload must return rows or none, never execute."""
    from mcp_servers.data import repository as repo
    from mcp_servers.data._db import connect
    with connect() as conn:
        repo.search_series(conn, payload, None, 5)  # must not raise or execute
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM analytics.v_mcp_observation")
        assert cur.fetchone()[0] > 200_000, "observations disappeared after an injection attempt"


def test_an_injection_in_a_portfolio_id_is_refused(failing_tool, db):
    err = failing_tool("get_portfolio", {"portfolio_id": "x'; DROP TABLE demo.position; --"})
    assert err.get("error_code") == "UNKNOWN_PORTFOLIO"


# --- filesystem containment (roots) -----------------------------------------

TRAVERSALS = [
    "../escaped.csv", "../../etc/passwd", "..\\..\\windows\\system32\\config\\sam",
    "sub/nested.csv", "a\\b.csv", "..", ".", "",
    "/absolute.csv", "C:\\absolute.csv",
]


@pytest.mark.parametrize("name", TRAVERSALS)
def test_no_filename_can_escape_a_granted_root(name, tmp_path):
    from mcp.types import ListRootsResult, Root

    from mcp_servers.data import interactive
    root = tmp_path / "granted"
    root.mkdir()
    roots = ListRootsResult(roots=[Root(uri=root.resolve().as_uri(), name="granted")])
    target, _ = interactive.contained_target(roots, name)
    assert target is None, f"{name!r} resolved to {target}"


def test_a_legitimate_filename_still_works(tmp_path):
    """The mirror image: refusing everything would also pass a one-sided check."""
    from mcp.types import ListRootsResult, Root

    from mcp_servers.data import interactive
    root = tmp_path / "granted"
    root.mkdir()
    roots = ListRootsResult(roots=[Root(uri=root.resolve().as_uri(), name="granted")])
    target, _ = interactive.contained_target(roots, "curve.csv")
    assert target == (root / "curve.csv").resolve()


def test_writing_is_impossible_when_the_client_grants_nothing():
    """No grant is not permission to fall back to a default."""
    from mcp.types import ListRootsResult

    from mcp_servers.data import interactive
    target, offered = interactive.contained_target(ListRootsResult(roots=[]), "curve.csv")
    assert target is None and offered == []


# --- separation of duties ---------------------------------------------------


def test_the_risk_engine_holds_no_database_credential():
    """Its child environment is built by allow-list, so nothing can leak in."""
    from mcp_servers.host.mcp_clients import DATA_ENV_KEYS, RISK_SERVER, sanitised_env
    env = sanitised_env(RISK_SERVER.env_keys)
    leaked = [k for k in env
              if k in DATA_ENV_KEYS or "PASSWORD" in k.upper() or "DATABASE" in k.upper()]
    assert leaked == []


def test_the_data_server_does_get_its_credentials():
    """The mirror image - an allow-list that grants nothing is also broken."""
    from mcp_servers.host.mcp_clients import DATA_SERVER, sanitised_env
    env = sanitised_env(DATA_SERVER.env_keys)
    assert any(k.startswith("MCP_READER") or k.startswith("POSTGRES") for k in env)


def test_the_child_environment_is_an_allow_list_not_a_deny_list(monkeypatch):
    """A deny-list silently leaks the next credential someone adds to .env."""
    from mcp_servers.host import mcp_clients
    monkeypatch.setenv("SOME_BRAND_NEW_SECRET", "hunter2")
    env = mcp_clients.sanitised_env(mcp_clients.RISK_SERVER.env_keys)
    assert "SOME_BRAND_NEW_SECRET" not in env


def imported_modules(path: Path) -> set[str]:
    """Top-level module names actually imported by a file.

    Parsed, not grepped. These modules *document* the drivers they refuse to
    import, so a substring search finds `psycopg2` in the prose that promises
    it is absent and reports the guarantee as a violation of itself.
    """
    import ast

    names: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module", ["curves", "pricing", "risk", "server", "manifest"])
def test_the_risk_engine_never_imports_a_database_driver(module):
    imported = imported_modules(Path(f".claude/src/mcp/src/mcp_servers/risk/{module}.py"))
    forbidden = imported & {"psycopg2", "psycopg", "sqlalchemy", "treasury_db", "asyncpg"}
    assert forbidden == set(), f"risk/{module}.py imports {forbidden}"


@pytest.mark.parametrize("package", ["data", "risk"])
def test_neither_server_imports_an_llm_client(package):
    """Only the host reasons. A model inside a server moves reasoning across the boundary."""
    root = Path(f".claude/src/mcp/src/mcp_servers/{package}")
    offenders = [str(path) for path in root.rglob("*.py")
                 if imported_modules(path) & {"anthropic", "openai"}]
    assert offenders == []


def test_the_host_is_the_only_component_that_holds_a_model():
    """The mirror image: if nothing imports anthropic, sampling has no answerer."""
    host = Path(".claude/src/mcp/src/mcp_servers/host")
    sources = " ".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in host.rglob("*.py"))
    assert "import anthropic" in sources


def test_the_data_server_holds_no_pricing_code():
    """It retrieves facts; anything derived belongs to the risk engine."""
    root = Path(".claude/src/mcp/src/mcp_servers/data")
    offenders = [str(p) for p in root.rglob("*.py")
                 if "def price_" in p.read_text(encoding="utf-8", errors="replace")]
    assert offenders == []


# --- classification ---------------------------------------------------------


def test_synthetic_and_real_data_are_never_conflated(call_tool, db):
    real = call_tool("get_curve", {"curve_family": "nominal"}).structured_content
    demo = call_tool("list_portfolios", {}).structured_content
    assert real["envelope"]["data_classification"] == "REAL_MARKET_DATA"
    assert demo["envelope"]["data_classification"] == "SYNTHETIC_DEMO"


def test_every_demo_payload_carries_its_label(call_tool, db):
    """An unlabelled demo position is one of the suite's three original canaries."""
    body = call_tool("list_portfolios", {}).structured_content
    portfolio_id = body["portfolios"][0]["portfolio_id"]
    snapshot = call_tool("get_portfolio", {"portfolio_id": portfolio_id}).structured_content
    assert snapshot["envelope"]["data_classification"] == "SYNTHETIC_DEMO"
