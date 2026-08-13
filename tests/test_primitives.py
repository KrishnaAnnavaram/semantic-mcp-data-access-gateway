"""The parts of the three client-directed primitives that must hold on their own.

The end-to-end behaviour is covered by `tools/verify_mcp.py`, which drives real
child processes with a real client. What is tested here is the logic that must
be correct even when nothing is connected — above all the root containment
check, which is a permission boundary and therefore has to be provably closed
rather than observed working.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp.types import ListRootsResult, Root

from mcp_servers.data import interactive


@pytest.fixture
def granted(tmp_path: Path) -> ListRootsResult:
    """One granted root, as a client would declare it."""
    root = tmp_path / "exports"
    root.mkdir()
    return ListRootsResult(roots=[Root(uri=root.resolve().as_uri(), name="exports")])


# --- roots ------------------------------------------------------------------


def test_bare_filename_inside_a_granted_root_is_allowed(granted, tmp_path):
    target, offered = interactive.contained_target(granted, "curve.csv")
    assert target == (tmp_path / "exports" / "curve.csv").resolve()
    assert offered and "exports" in offered[0]


@pytest.mark.parametrize("name", [
    "../escaped.csv",       # parent traversal
    "../../etc/passwd",     # deeper traversal
    "sub/nested.csv",       # forward-slash separator
    "a\\b.csv",             # backslash separator, which Windows would honour
    "..",                   # bare parent reference
    "",                     # empty name
])
def test_names_that_would_leave_the_root_are_refused(granted, name):
    """Refused, never sanitised.

    Stripping the offending part would silently write somewhere the caller did
    not ask for, which is worse than failing: the caller believes the file is
    where they named it.
    """
    target, _ = interactive.contained_target(granted, name)
    assert target is None


def test_no_declared_roots_means_nothing_is_writable():
    """A client that grants nothing gets nothing written.

    The absence of a grant is not permission to fall back to a default; that
    fallback is how a roots implementation quietly becomes an arbitrary write.
    """
    target, offered = interactive.contained_target(ListRootsResult(roots=[]), "curve.csv")
    assert target is None
    assert offered == []


def test_a_non_file_root_cannot_even_be_constructed():
    """The wire type rejects a non-file scheme before this server sees it.

    Worth pinning: it is the reason `root_paths` can treat every well-formed
    root as a local path. If `Root.uri` ever widens beyond `FileUrl`, this test
    fails and the scheme filter below stops being belt-and-braces.
    """
    with pytest.raises(ValueError):
        Root(uri="https://example.invalid/somewhere", name="remote")  # type: ignore[arg-type]


def test_a_malformed_root_is_skipped_rather_than_guessed_at(tmp_path):
    """A root that cannot be resolved is dropped, never approximated.

    Built with `model_construct` to bypass validation, standing in for a peer
    that sent something the type would have rejected. This list is a permission
    boundary, so anything not positively understood is excluded.
    """
    usable = tmp_path / "ok"
    usable.mkdir()
    roots = ListRootsResult(roots=[
        Root.model_construct(uri="https://example.invalid/somewhere", name="remote"),
        Root(uri=usable.resolve().as_uri(), name="ok"),
    ])
    paths = [p for p, _ in interactive.root_paths(roots)]
    assert paths == [usable.resolve()]


def test_a_symlink_pointing_out_of_the_root_is_refused(granted, tmp_path):
    """Containment is re-checked after resolution, not only before it.

    The bare-name check alone would pass here: 'escape.csv' contains no
    separator. Only re-checking the resolved path catches a link that leaves
    the granted directory.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "exports" / "escape.csv"
    try:
        link.symlink_to(outside / "target.csv")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted in this environment")
    target, _ = interactive.contained_target(granted, "escape.csv")
    assert target is None


# --- elicitation ------------------------------------------------------------


def test_the_elicitation_schema_admits_only_the_two_real_curve_families():
    """'nominal' and 'real' are the whole domain; anything else is a bug upstream."""
    assert interactive.RateKindChoice(rate_kind="nominal").rate_kind == "nominal"
    assert interactive.RateKindChoice(rate_kind="real").rate_kind == "real"
    with pytest.raises(ValueError):
        interactive.RateKindChoice(rate_kind="notional")


def test_the_elicitation_schema_stays_a_single_question():
    """One field, deliberately.

    An elicitation is a form a human fills in mid-task; every extra field is
    another chance to answer a question they were not asked.
    """
    assert list(interactive.RateKindChoice.model_fields) == ["rate_kind"]
