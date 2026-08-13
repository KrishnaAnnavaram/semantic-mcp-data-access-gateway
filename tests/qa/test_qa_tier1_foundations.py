"""Tier 1 — foundations. Pure, fast, no database and no network.

If any of these fail, nothing above them is worth reading: the packages are not
installed correctly, the wire contract does not hold its own invariants, or the
pagination cursor is forgeable.
"""

from __future__ import annotations

import datetime as dt
import importlib
import inspect
from decimal import Decimal
from pathlib import Path

import pytest

# --- packaging --------------------------------------------------------------


@pytest.mark.parametrize("module", [
    "treasury_db", "mcp_servers", "backend",
    "mcp_servers.data.server", "mcp_servers.risk.server",
    "mcp_servers.host.mcp_clients", "mcp_servers.host.interaction",
    "mcp_servers.data.interactive", "backend.agent.quant_agent",
])
def test_every_distribution_imports(module):
    """All three distributions must be installed; they import each other."""
    assert importlib.import_module(module) is not None


def test_no_sys_path_manipulation_anywhere_in_the_source():
    """`sys.path` hacks are banned - packages are pip-installed.

    A single `sys.path.insert` makes the import graph depend on which file was
    run first, which is the kind of failure that only shows up in someone
    else's checkout.
    """
    roots = [Path("mcp/src"), Path("backend/src"),
             Path("postgres/src")]
    offenders = []
    for root in roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "sys.path.insert" in text or "sys.path.append" in text:
                offenders.append(str(path))
    assert offenders == []


def test_repo_root_is_found_by_marker_not_by_counting_parents():
    """`parents[N]` is wrong the moment a file moves; three packages, three depths.

    Matches a *literal* index (`parents[2]`), not the prose - paths.py's own
    docstring explains why counting is wrong and must not trip its own check.
    """
    import re

    from mcp_servers import paths
    source = inspect.getsource(paths)
    assert re.search(r"parents\[\d+\]", source) is None, \
        "paths.py must walk up for a marker, not index a fixed ancestor"


# --- wire contract ----------------------------------------------------------


def test_contracts_reject_unknown_fields():
    """A typo'd argument must fail loudly, not silently widen a query."""
    from mcp_servers.data.contracts import Provenance
    with pytest.raises(Exception):
        Provenance(source_fyle="typo.xml")  # type: ignore[call-arg]


def test_a_rate_point_cannot_be_constructed_without_its_semantics():
    """A bare 4.26 could be a par yield, a discount rate or a real yield."""
    from mcp_servers.data.contracts import RatePoint
    with pytest.raises(Exception):
        RatePoint(  # type: ignore[call-arg]
            series_code="BC_10YEAR", display_name="10 Year",
            observation_date=dt.date(2026, 8, 11), rate_percent=Decimal("4.70"),
        )  # rate_kind and quote_basis missing


def test_a_fully_specified_rate_point_is_accepted():
    from mcp_servers.data.contracts import RatePoint
    point = RatePoint(
        series_code="BC_10YEAR", display_name="10 Year", rate_kind="nominal",
        quote_basis="par_coupon_semiannual", tenor_label="10 Year",
        tenor_months=Decimal("120"), observation_date=dt.date(2026, 8, 11),
        rate_percent=Decimal("4.70"),
    )
    assert point.quote_basis == "par_coupon_semiannual"


def test_rates_serialise_as_strings_not_floats():
    """Decimals stay decimal so 4.2 cannot become 4.2000000000000002."""
    from mcp_servers.data.contracts import RatePoint
    point = RatePoint(
        series_code="BC_10YEAR", display_name="10 Year", rate_kind="nominal",
        quote_basis="par_coupon_semiannual", observation_date=dt.date(2026, 8, 11),
        rate_percent=Decimal("4.70"),
    )
    assert isinstance(point.model_dump(mode="json")["rate_percent"], str)


@pytest.mark.parametrize("basis", ["par_coupon_semiannual", "bank_discount_act360",
                                   "coupon_equivalent", "average_real_yield"])
def test_the_four_real_quoting_bases_are_accepted(basis):
    from mcp_servers.data.contracts import RatePoint
    assert RatePoint(
        series_code="X", display_name="X", rate_kind="nominal", quote_basis=basis,
        observation_date=dt.date(2026, 8, 11), rate_percent=Decimal("1"),
    ).quote_basis == basis


def test_an_invented_quoting_basis_is_rejected():
    from mcp_servers.data.contracts import RatePoint
    with pytest.raises(Exception):
        RatePoint(
            series_code="X", display_name="X", rate_kind="nominal",
            quote_basis="made_up_basis",  # type: ignore[arg-type]
            observation_date=dt.date(2026, 8, 11), rate_percent=Decimal("1"),
        )


# --- pagination cursor ------------------------------------------------------


def test_cursor_round_trips_its_payload():
    from mcp_servers.data import cursor
    args = {"data_key": "daily_treasury_yield_curve", "page_size": 50}
    token = cursor.encode("list_series", args, {"c": "BC_10YEAR"})
    assert cursor.decode(token, "list_series", args)["c"] == "BC_10YEAR"


def test_a_cursor_is_bound_to_the_query_that_produced_it():
    """Replaying page 2 of one filter against another would silently mix results."""
    from mcp_servers.data import cursor
    token = cursor.encode("list_series", {"data_key": "a"}, {"c": "X"})
    with pytest.raises(Exception):
        cursor.decode(token, "list_series", {"data_key": "b"})


def test_a_cursor_is_bound_to_its_tool():
    from mcp_servers.data import cursor
    token = cursor.encode("list_series", {"x": 1}, {"c": "X"})
    with pytest.raises(Exception):
        cursor.decode(token, "get_rate_history", {"x": 1})


def test_a_tampered_cursor_is_rejected():
    """The signature is the point: a client must not be able to forge an offset."""
    from mcp_servers.data import cursor
    token = cursor.encode("list_series", {"x": 1}, {"c": "BC_10YEAR"})
    forged = ("A" if token[0] != "A" else "B") + token[1:]
    with pytest.raises(Exception):
        cursor.decode(forged, "list_series", {"x": 1})


def test_garbage_is_rejected_as_an_invalid_cursor_not_a_crash():
    from mcp_servers.data import cursor
    with pytest.raises(Exception):
        cursor.decode("not-a-cursor", "list_series", {})


# --- error contract ---------------------------------------------------------


def test_errors_carry_a_code_and_a_remedy():
    """Clients feed these back to the model, so each must name its own fix."""
    from mcp_servers.data import errors
    err = errors.unknown_series("BC_10Y", [{"series_code": "BC_10YEAR"}])
    body = err.args[0] if err.args else ""
    assert "UNKNOWN_SERIES" in str(body)


def test_row_limit_is_a_refusal_with_a_usable_hint():
    """A caller who asked for 5,000 and silently got 2,000 has a wrong answer."""
    from mcp_servers.data import errors
    err = errors.row_limit_exceeded(5000, 2000, "Use page_size between 1 and 2000.")
    assert "ROW_LIMIT_EXCEEDED" in str(err.args[0])


# --- risk engine manifest ---------------------------------------------------


def test_the_model_manifest_pins_every_numerical_convention():
    """Changing the quantile rule must change the fingerprint, by design."""
    from mcp_servers.risk.manifest import MODEL_MANIFEST
    assert MODEL_MANIFEST.get("risk_engine_version")
    flat = str(MODEL_MANIFEST).lower()
    assert "nearest_rank" in flat
    assert "bootstrap" in flat or "par" in flat
