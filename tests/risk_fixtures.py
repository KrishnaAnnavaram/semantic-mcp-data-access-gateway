"""Shared fixtures for the quantitative risk tests.

Deliberately not a conftest: these are plain constructors that each test file
imports, so a test's inputs are visible in the file that asserts on them. A
golden test whose portfolio is defined three directories away is a test nobody
can check by reading.

Everything here is deterministic. The synthetic histories are trigonometric
rather than random, so a failure reproduces exactly and a Monte Carlo test that
depends on an uncontrolled RNG cannot creep in.
"""

from __future__ import annotations

import datetime as dt
import math

from mcp_servers.risk.curves import ParCurve
from mcp_servers.risk.pricing import FixedRateBond, Position
from mcp_servers.risk.revaluation import CompiledBook, compile_book

VALUATION = dt.date(2026, 8, 15)

# An upward-sloping curve on Treasury's published tenors. Sloped on purpose:
# on a flat curve, treating par yields as spot rates happens to give roughly the
# right answer, so a flat curve cannot distinguish a correct engine from that
# particular mistake.
SLOPED_TENORS = (0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0)
SLOPED_RATES = (3.0, 3.2, 3.5, 3.7, 4.0, 4.3, 4.6, 5.0, 5.1)

# The four tenors the templates use as control points, so a template's shape can
# be asserted exactly rather than through an interpolation rule.
CONTROL_TENORS = (2.0, 5.0, 10.0, 30.0)


def sloped_par() -> ParCurve:
    return ParCurve(SLOPED_TENORS, SLOPED_RATES)


def flat_par(rate_percent: float = 4.0,
             tenors: tuple[float, ...] = SLOPED_TENORS) -> ParCurve:
    return ParCurve(tenors, tuple(rate_percent for _ in tenors))


def control_point_par() -> ParCurve:
    """A curve whose only nodes are the templates' control points."""
    return ParCurve(CONTROL_TENORS, (3.5, 4.0, 4.6, 5.1))


def inverted_par() -> ParCurve:
    return ParCurve(SLOPED_TENORS, (5.4, 5.3, 5.0, 4.8, 4.4, 4.3, 4.3, 4.5, 4.4))


DEMO_SPECS = (
    ("DEMO_NOTE_2Y", 3.75, dt.date(2028, 8, 15), 5_000_000),
    ("DEMO_NOTE_5Y", 4.00, dt.date(2031, 8, 15), 10_000_000),
    ("DEMO_NOTE_10Y", 4.25, dt.date(2036, 8, 15), 8_000_000),
    ("DEMO_BOND_20Y", 4.50, dt.date(2046, 8, 15), 4_000_000),
    ("DEMO_BOND_30Y", 4.75, dt.date(2056, 8, 15), 3_000_000),
)


def demo_positions(issue_date: dt.date = VALUATION) -> list[Position]:
    return [Position(FixedRateBond(i, 1000.0, c, m, issue_date), n)
            for i, c, m, n in DEMO_SPECS]


def demo_book(valuation_date: dt.date = VALUATION) -> CompiledBook:
    return compile_book(demo_positions(), valuation_date)


def single_bond(coupon: float = 4.0, maturity: dt.date = dt.date(2036, 8, 15),
                notional: float = 1_000_000.0,
                issue: dt.date = VALUATION) -> list[Position]:
    return [Position(FixedRateBond("SINGLE", 1000.0, coupon, maturity, issue), notional)]


def synthetic_history(
    observations: int = 300, tenors: tuple[float, ...] = (2.0, 5.0, 10.0, 30.0),
    amplitude: float = 0.30, base: float = 4.0,
) -> tuple[list[float], list[list[float]]]:
    """A deterministic, correlated, non-degenerate rate history in percent.

    Two superimposed sinusoids at different frequencies and per-tenor phase
    offsets. The result is correlated across tenors without being singular -
    which matters, because a covariance matrix estimated from perfectly
    collinear tenors is not positive definite and would exercise the repair
    path in every test rather than the one that is about it.
    """
    rows = [[base + amplitude * math.sin(i / 9.0 + j * 0.7)
             + 0.08 * math.cos(i / 3.0 + j)
             for j in range(len(tenors))]
            for i in range(observations)]
    return list(tenors), rows


def synthetic_dates(count: int, start: dt.date = dt.date(2025, 1, 1)) -> list[dt.date]:
    return [start + dt.timedelta(days=i) for i in range(count)]


def hand_built_history(rows_percent: list[list[float]],
                       tenors: tuple[float, ...] = (2.0, 10.0)) -> tuple:
    """A tiny history whose implied scenarios can be counted by hand."""
    return list(tenors), [list(r) for r in rows_percent]
