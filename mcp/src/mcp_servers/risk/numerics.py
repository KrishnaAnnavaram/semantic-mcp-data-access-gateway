"""One root finder, one convergence report.  `brent_bisection_secant_v1`

Three separate questions in this engine reduce to "find the scalar that makes
this function hit a target": the yield that reprices a bond, the parallel shock
that loses a given amount, and the stress severity that breaches a limit. They
are the same problem and they get the same solver, so a convergence failure
means the same thing everywhere and is reported the same way.

Brent's method: bisection's guaranteed convergence with secant/inverse-quadratic
speed where the function is well behaved. It cannot diverge, which matters more
than iteration count when the function being solved is a full portfolio
revaluation and the caller is a risk report.

**A solver that stops is not a solver that succeeded.** Every result carries
`converged` and the iteration count, and callers are expected to propagate them
rather than quietly returning the last iterate.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SolveResult:
    root: float
    value_at_root: float
    iterations: int
    converged: bool
    bracket_low: float
    bracket_high: float
    method: str = "brent_bisection_secant_v1"


class BracketError(ValueError):
    """The target is not enclosed by the search bounds."""


def bracket_target(
    f: Callable[[float], float], low: float, high: float, target: float = 0.0,
    expansions: int = 0, growth: float = 2.0,
) -> tuple[float, float, float, float]:
    """Find (lo, hi, f(lo), f(hi)) with the target strictly enclosed.

    `expansions` > 0 widens outward from the supplied bounds. Widening is opt-in
    rather than automatic: a reverse-stress caller who asks for a solution
    within +-300bp wants "no solution inside +-300bp", not a silent answer at
    +900bp that no scenario library would ever contain.
    """
    lo, hi = float(low), float(high)
    if hi <= lo:
        raise BracketError(f"search bounds are empty: [{lo}, {hi}]")
    flo, fhi = f(lo) - target, f(hi) - target
    tries = 0
    while flo * fhi > 0 and tries < expansions:
        span = hi - lo
        lo, hi = lo - span * (growth - 1) / 2, hi + span * (growth - 1) / 2
        flo, fhi = f(lo) - target, f(hi) - target
        tries += 1
    if flo * fhi > 0:
        raise BracketError(
            f"target {target:.10g} is not reached anywhere in [{lo:.6g}, {hi:.6g}]: "
            f"the function spans {min(flo, fhi) + target:.10g} to "
            f"{max(flo, fhi) + target:.10g} there")
    return lo, hi, flo, fhi


def solve_scalar(
    f: Callable[[float], float], low: float, high: float, target: float = 0.0,
    tolerance: float = 1e-10, max_iterations: int = 200, expansions: int = 0,
) -> SolveResult:
    """Brent's method on f(x) = target over [low, high]."""
    a, b, fa, fb = bracket_target(f, low, high, target, expansions)
    bracket_lo, bracket_hi = a, b
    if abs(fa) < abs(fb):
        a, b, fa, fb = b, a, fb, fa

    c, fc, d = a, fa, b - a
    used_bisection = True
    for i in range(1, max_iterations + 1):
        if fb == 0.0 or abs(b - a) < tolerance:
            return SolveResult(b, fb + target, i, True, bracket_lo, bracket_hi)
        if fa != fc and fb != fc:
            # Inverse quadratic interpolation through three points.
            s = (a * fb * fc / ((fa - fb) * (fa - fc))
                 + b * fa * fc / ((fb - fa) * (fb - fc))
                 + c * fa * fb / ((fc - fa) * (fc - fb)))
        else:
            s = b - fb * (b - a) / (fb - fa)          # secant

        span = (3 * a + b) / 4
        conditions = (
            not (min(span, b) < s < max(span, b)),
            used_bisection and abs(s - b) >= abs(b - c) / 2,
            not used_bisection and abs(s - b) >= abs(c - d) / 2,
            used_bisection and abs(b - c) < tolerance,
            not used_bisection and abs(c - d) < tolerance,
        )
        if any(conditions):
            s = (a + b) / 2
            used_bisection = True
        else:
            used_bisection = False

        fs = f(s) - target
        d, c, fc = c, b, fb
        if fa * fs < 0:
            b, fb = s, fs
        else:
            a, fa = s, fs
        if abs(fa) < abs(fb):
            a, b, fa, fb = b, a, fb, fa

    return SolveResult(b, fb + target, max_iterations, False, bracket_lo, bracket_hi)


def is_monotone(values: list[float], tolerance: float = 0.0) -> bool:
    """Weakly monotone in either direction, within a tolerance."""
    ups = all(b >= a - tolerance for a, b in zip(values, values[1:]))
    downs = all(b <= a + tolerance for a, b in zip(values, values[1:]))
    return ups or downs


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sample_stdev(values: list[float]) -> float:
    """Bessel-corrected sample standard deviation; 0.0 for fewer than two points."""
    n = len(values)
    if n < 2:
        return 0.0
    mu = sum(values) / n
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (n - 1))
