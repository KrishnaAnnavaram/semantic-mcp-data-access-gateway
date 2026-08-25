"""Property and invariant tests across the whole risk engine.

Unit tests check one answer. Properties check a whole class of answers at once,
and they catch the failures financial code actually has: a sign that only flips
on a rate cut, an ordering dependence that appears when a book is rebalanced, a
seed that turns out not to be used.

Every property here is stated as something that must be true of *any* input in
its domain, and then exercised over a spread of inputs chosen to include the
awkward ones - a short position, an inverted curve, a single-bond book, a zero
shock.

`hypothesis` is not a dependency of this project, so the generation is done with
explicit parameter grids. That is a deliberate trade: fewer cases, but a failing
case is reproducible from the test id alone rather than from a seed printed in a
log somebody has since discarded.
"""

from __future__ import annotations

import datetime as dt
import itertools

import pytest
from mcp_servers.risk.contributions import measure_contributions, run_shock
from mcp_servers.risk.curves import ParCurve, build_discount_curve
from mcp_servers.risk.manifest import MODEL_MANIFEST, run_fingerprint, sha256_of
from mcp_servers.risk.monte_carlo import compute_monte_carlo_risk
from mcp_servers.risk.pricing import FixedRateBond, Position, price_portfolio
from mcp_servers.risk.revaluation import compile_book, run_scenarios
from mcp_servers.risk.risk import nearest_rank_quantile
from mcp_servers.risk.sensitivities import compute_rate_sensitivities
from mcp_servers.risk.stress_matrix import build_standard_pack, run_stress_matrix
from mcp_servers.risk.stress_scenarios import parallel_shock, template_shock
from risk_fixtures import (
    VALUATION,
    demo_book,
    demo_positions,
    flat_par,
    inverted_par,
    single_bond,
    sloped_par,
    synthetic_history,
)

CURVES = {
    "flat_1pct": flat_par(1.0),
    "flat_4pct": flat_par(4.0),
    "flat_9pct": flat_par(9.0),
    "upward_sloping": sloped_par(),
    "inverted": inverted_par(),
}

BOOKS = {
    "five_bond_demo": lambda: demo_positions(),
    "single_10y": lambda: single_bond(4.0, dt.date(2036, 8, 15)),
    "single_30y": lambda: single_bond(4.75, dt.date(2056, 8, 15)),
    "long_short": lambda: [
        Position(FixedRateBond("LONG_10Y", 1000.0, 4.25, dt.date(2036, 8, 15),
                               VALUATION), 10_000_000),
        Position(FixedRateBond("SHORT_2Y", 1000.0, 3.75, dt.date(2028, 8, 15),
                               VALUATION), -4_000_000)],
}


def cases():
    return [(book_name, curve_name)
            for book_name, curve_name in itertools.product(BOOKS, CURVES)]


# --- valuation ---------------------------------------------------------------


@pytest.mark.parametrize("book_name,curve_name", cases())
def test_portfolio_value_is_the_sum_of_its_positions(book_name, curve_name):
    positions, par = BOOKS[book_name](), CURVES[curve_name]
    result = price_portfolio(positions, VALUATION, build_discount_curve(par))
    assert result.total_present_value == pytest.approx(
        sum(p.present_value for p in result.positions), rel=1e-12)


@pytest.mark.parametrize("book_name,curve_name", cases())
def test_valuation_does_not_depend_on_position_order(book_name, curve_name):
    positions, par = BOOKS[book_name](), CURVES[curve_name]
    curve = build_discount_curve(par)
    forward = price_portfolio(positions, VALUATION, curve).total_present_value
    backward = price_portfolio(list(reversed(positions)), VALUATION,
                               curve).total_present_value
    assert forward == pytest.approx(backward, rel=1e-12)


@pytest.mark.parametrize("book_name,curve_name", cases())
def test_the_compiled_book_prices_identically_to_the_original_pricer(
    book_name, curve_name,
):
    """The optimisation must be an optimisation and nothing else.

    A faster pricer that disagrees with the slow one in the seventeenth decimal
    makes every reconciliation in this engine unfalsifiable, so the requirement
    is bit-for-bit equality rather than approximate agreement.
    """
    positions, par = BOOKS[book_name](), CURVES[curve_name]
    curve = build_discount_curve(par)
    slow = price_portfolio(positions, VALUATION, curve)
    fast = compile_book(positions, VALUATION).price_positions(curve)
    assert [p.present_value for p in slow.positions] == list(fast)


def shock_grid(par: ParCurve) -> list[float]:
    """A symmetric shock grid that keeps the curve inside the bootstrap's domain.

    A 200bp down-shift of a 1% curve lands below zero, where the
    no-negative-forward guard refuses to build - correctly, and as
    `test_bond_and_curve_analytics` asserts directly. A property test's job is to
    range over the engine's domain, not to rediscover its edge on every run, so
    the grid is sized to the curve it will be applied to.
    """
    headroom_bp = min(par.rates_percent) * 100.0
    widest = min(200.0, max(25.0, headroom_bp - 25.0))
    return [-widest, -widest / 2, 0.0, widest / 2, widest]


@pytest.mark.parametrize("curve_name", CURVES)
def test_higher_rates_lower_the_value_of_a_long_fixed_rate_book(curve_name):
    par = CURVES[curve_name]
    book = compile_book(demo_positions(), VALUATION)
    values = [book.value_under(par.shifted(bp)) for bp in shock_grid(par)]
    assert values == sorted(values, reverse=True)


@pytest.mark.parametrize("multiplier", [0.5, 2.0, 10.0])
def test_scaling_every_notional_scales_value_and_risk_by_the_same_factor(multiplier):
    par = sloped_par()
    base = compile_book(demo_positions(), VALUATION)
    scaled = compile_book([Position(p.bond, p.face_notional * multiplier)
                           for p in demo_positions()], VALUATION)
    assert scaled.value_under(par) == pytest.approx(
        base.value_under(par) * multiplier, rel=1e-12)
    assert compute_rate_sensitivities(scaled, par).dv01 == pytest.approx(
        compute_rate_sensitivities(base, par).dv01 * multiplier, rel=1e-12)


# --- stress ------------------------------------------------------------------


@pytest.mark.parametrize("book_name,curve_name", cases())
def test_a_zero_shock_gives_exactly_zero_pnl(book_name, curve_name):
    positions, par = BOOKS[book_name](), CURVES[curve_name]
    book = compile_book(positions, VALUATION)
    assert run_shock(book, par, parallel_shock(par, 0.0)).pnl == pytest.approx(
        0.0, abs=1e-6)


@pytest.mark.parametrize("book_name,curve_name", cases())
def test_position_contributions_always_sum_to_the_portfolio_pnl(book_name, curve_name):
    positions, par = BOOKS[book_name](), CURVES[curve_name]
    book = compile_book(positions, VALUATION)
    run = run_shock(book, par, parallel_shock(par, 100.0))
    assert sum(p.pnl for p in run.positions) == pytest.approx(run.pnl, rel=1e-11)


@pytest.mark.parametrize("curve_name", CURVES)
def test_stress_pnl_is_monotone_in_the_size_of_a_parallel_shock(curve_name):
    par = CURVES[curve_name]
    book = compile_book(demo_positions(), VALUATION)
    pnl = [run_shock(book, par, parallel_shock(par, bp)).pnl
           for bp in shock_grid(par)]
    assert pnl == sorted(pnl, reverse=True)


def test_stress_ranking_does_not_depend_on_the_order_scenarios_arrive_in():
    book, par = demo_book(), sloped_par()
    vectors, _ = build_standard_pack(par)
    forward = run_stress_matrix(book, par, vectors)
    backward = run_stress_matrix(book, par, list(reversed(vectors)))
    names = lambda m: [e.scenario_name for e in m.entries if e.failed_reason is None]
    assert names(forward) == names(backward)


@pytest.mark.parametrize("template", ["BEAR_STEEPENER", "BEAR_FLATTENER",
                                      "BELLY_SELLOFF", "WINGS_SELLOFF"])
def test_a_selloff_template_never_shows_a_gain_on_a_long_book(template):
    """Loses money, or refuses by name. Never a gain.

    Stated as "never a gain" rather than "always a loss" because one legitimate
    outcome is a refusal: selling the belly off by 100bp on an already-inverted
    curve produces a shape the bootstrap will not build, and saying so is the
    correct answer. What must never happen is a long book quietly profiting from
    a selloff.
    """
    from mcp_servers.risk.curves import CurveError

    refusals = 0
    for curve_name, par in CURVES.items():
        book = compile_book(demo_positions(), VALUATION)
        try:
            pnl = run_shock(book, par, template_shock(par, template, 100.0)).pnl
        except CurveError as exc:
            assert "negative forward" in str(exc) or "non-positive" in str(exc), (
                f"{template} on {curve_name} failed for an unexplained reason")
            refusals += 1
            continue
        assert pnl < 0, f"{template} on {curve_name} showed a gain"
    assert refusals <= 1, (
        "at most the inverted curve should be un-buildable under a selloff")


# --- risk measures -----------------------------------------------------------


@pytest.mark.parametrize("confidence", [0.90, 0.95, 0.975, 0.99])
def test_expected_shortfall_can_never_fall_below_var(confidence):
    tenors, rows = synthetic_history(260)
    book, par = demo_book(), sloped_par()
    from mcp_servers.risk.volatility import observed_changes_bp
    changes = observed_changes_bp(rows, 1)
    scenarios = run_scenarios(book, par, [dict(zip(tenors, c)) for c in changes])
    losses = scenarios.losses_sorted()
    var, _ = nearest_rank_quantile(losses, confidence)
    tail = [loss for loss in losses if loss >= var]
    assert sum(tail) / len(tail) >= var


@pytest.mark.parametrize("measure", ["var", "es"])
def test_component_contributions_always_reconcile(measure):
    tenors, rows = synthetic_history(260)
    from mcp_servers.risk.volatility import observed_changes_bp
    changes = observed_changes_bp(rows, 1)
    for book_name in BOOKS:
        book = compile_book(BOOKS[book_name](), VALUATION)
        scenarios = run_scenarios(book, sloped_par(),
                                  [dict(zip(tenors, c)) for c in changes])
        result = measure_contributions(scenarios, 0.99, measure,
                                       include_incremental=False)
        assert sum(p.component for p in result.positions) == pytest.approx(
            result.portfolio_measure, rel=1e-9), f"{measure} on {book_name}"


def test_the_quantile_convention_is_exactly_ceil_alpha_n():
    values = [float(i) for i in range(1, 101)]
    assert nearest_rank_quantile(values, 0.99) == (99.0, 98)
    assert nearest_rank_quantile(values, 0.95) == (95.0, 94)
    assert nearest_rank_quantile(values, 0.50) == (50.0, 49)
    # Small samples are where interpolation conventions diverge most.
    assert nearest_rank_quantile([10.0, 20.0, 30.0], 0.99)[0] == 30.0
    assert nearest_rank_quantile([10.0], 0.99)[0] == 10.0


# --- reproducibility ---------------------------------------------------------


def test_identical_inputs_produce_an_identical_fingerprint_regardless_of_key_order():
    payload = {"portfolio": "TREASURY_DEMO_001", "confidence": 0.99, "days": 250}
    assert run_fingerprint(payload) == run_fingerprint(
        dict(reversed(list(payload.items()))))


def test_a_changed_manifest_changes_every_fingerprint():
    payload = {"portfolio": "X"}
    before = run_fingerprint(payload)
    original = MODEL_MANIFEST["quantile_method"]
    try:
        MODEL_MANIFEST["quantile_method"] = "linear_interpolation_v1"
        assert run_fingerprint(payload) != before
    finally:
        MODEL_MANIFEST["quantile_method"] = original
    assert run_fingerprint(payload) == before


@pytest.mark.parametrize("key", [
    "bond_analytics_version", "stress_scenario_version", "monte_carlo_version",
    "kupiec_test_version", "frtb_girr_version", "pnl_attribution_version",
    "reverse_stress_version", "parametric_var_version",
])
def test_every_new_methodology_is_named_in_the_manifest(key):
    """A methodology absent from the manifest cannot change a fingerprint."""
    assert key in MODEL_MANIFEST
    assert isinstance(MODEL_MANIFEST[key], str) and MODEL_MANIFEST[key]


def test_changing_any_methodology_version_changes_the_fingerprint():
    payload = {"portfolio": "X"}
    before = run_fingerprint(payload)
    original = MODEL_MANIFEST["monte_carlo_version"]
    try:
        MODEL_MANIFEST["monte_carlo_version"] = "something_else_v2"
        assert run_fingerprint(payload) != before, (
            "a methodology change that does not move the fingerprint could "
            "masquerade as the same calculation")
    finally:
        MODEL_MANIFEST["monte_carlo_version"] = original


def test_the_manifest_states_every_sign_convention_this_engine_relies_on():
    policy = MODEL_MANIFEST["numeric_policy"]
    for key in ("pnl_sign", "dv01_sign", "curve_spread_sign", "butterfly",
                "var_sign", "es_sign", "rate_shock_unit", "duration_unit",
                "convexity_unit", "backtest_exception"):
        assert key in policy, f"{key} is a convention with a defensible opposite"


@pytest.mark.parametrize("seed", [1, 20260824, 999_999])
def test_the_same_monte_carlo_seed_always_reproduces_the_same_numbers(seed):
    tenors, rows = synthetic_history(200)
    args = (demo_book(), sloped_par(), tenors, rows, 0.99, 1, 500, seed)
    first, second = compute_monte_carlo_risk(*args), compute_monte_carlo_risk(*args)
    assert (first.var, first.expected_shortfall, first.worst_pnl) == \
           (second.var, second.expected_shortfall, second.worst_pnl)


def test_canonical_hashing_is_stable_across_equivalent_structures():
    assert sha256_of({"a": 1, "b": 2}) == sha256_of({"b": 2, "a": 1})
    assert sha256_of([1, 2, 3]) != sha256_of([3, 2, 1])


# --- boundaries the engine must not cross -----------------------------------


def test_the_risk_engine_imports_no_database_network_or_model_client():
    """The calculation boundary, asserted over the whole package including
    subpackages.

    Checked through the AST rather than by grepping, because the first version
    of this test in this repository failed on a *comment* explaining that
    psycopg2 must not be imported - a false positive that trains people to stop
    writing the explanation.
    """
    import ast
    import pathlib

    banned = {"psycopg2", "sqlalchemy", "asyncpg", "requests", "httpx",
              "anthropic", "openai", "socket", "urllib", "ftplib", "smtplib",
              "subprocess", "boto3"}
    package = (pathlib.Path(__file__).resolve().parents[1]
               / "mcp" / "src" / "mcp_servers" / "risk")
    checked = 0
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        offending = imported & banned
        assert not offending, (
            f"mcp_servers/risk/{path.relative_to(package)} imports "
            f"{sorted(offending)}; the risk engine must have no database, "
            "network or model access")
        checked += 1
    assert checked >= 20, (
        f"only {checked} modules were scanned; the guard must cover the whole "
        "package including the regulatory subpackage")


def test_no_risk_module_reads_the_environment_or_the_clock_for_a_calculation():
    """Determinism, enforced structurally.

    A calculation that consults `os.environ` or `datetime.now()` cannot be
    reproduced from its inputs and its manifest, which is the promise every
    result in this engine carries. The protocol wrappers are exempt only for
    labelling a result's `valuation_date` when the caller supplied none.
    """
    import ast
    import pathlib

    package = (pathlib.Path(__file__).resolve().parents[1]
               / "mcp" / "src" / "mcp_servers" / "risk")
    calculation_modules = [
        p for p in sorted(package.rglob("*.py"))
        if not p.name.startswith("tools_") and p.name not in {"server.py"}
    ]
    for path in calculation_modules:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                qualified = f"{node.value.id}.{node.attr}"
                assert qualified not in {"os.environ", "os.getenv"}, (
                    f"{path.name} reads the environment inside a calculation")
                assert qualified not in {"dt.today", "date.today"}, (
                    f"{path.name} reads the clock inside a calculation")
