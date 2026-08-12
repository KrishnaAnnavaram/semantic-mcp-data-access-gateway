"""Par curve -> discount curve.  `par_bootstrap_logdf_interp_v1`

Why this module has to exist
----------------------------
Treasury publishes par yields on a semiannual bond-equivalent basis. It does
not publish a zero-coupon curve. To discount a cash flow you need discount
factors, and getting them from par yields means solving for them.

At a semiannual par node n with annual par rate c (as a decimal), a bond priced
at par satisfies

    1 = (c/2) * sum_{i=1..n} D_i  +  D_n

which rearranges to the forward recurrence

    D_n = (1 - (c/2) * sum_{i=1..n-1} D_i) / (1 + c/2)

Bootstrapping needs a par rate at *every* semiannual node, but Treasury
publishes fourteen tenors, not sixty. So par yields are first interpolated onto
the semiannual grid. That interpolation is a modelling choice - linear in par
yield against tenor - and it is named in the manifest rather than buried here.

The short end (below six months) has no semiannual coupon to speak of; those
points are treated as simple money-market discounting, D = 1/(1 + y*t).

This is a transparent, reproducible construction. It is deliberately *not* a
reproduction of Treasury's own monotone-convex methodology, which Treasury does
not publish in full. Values derived from it are model-implied.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from typing import Sequence

SEMIANNUAL = 0.5
MAX_TENOR_YEARS = 30.0


class CurveError(ValueError):
    """The curve cannot be built from what was supplied."""


@dataclass(frozen=True)
class ParCurve:
    """Par yields in percent, indexed by tenor in years, ascending."""

    tenors_years: tuple[float, ...]
    rates_percent: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.tenors_years) != len(self.rates_percent):
            raise CurveError("tenor and rate arrays differ in length")
        if len(self.tenors_years) < 2:
            raise CurveError("a curve needs at least two nodes")
        if list(self.tenors_years) != sorted(self.tenors_years):
            raise CurveError("tenors must be ascending")
        if len(set(self.tenors_years)) != len(self.tenors_years):
            raise CurveError(
                "duplicate tenor nodes: a curve has exactly one rate per tenor")
        for r in self.rates_percent:
            if not math.isfinite(r):
                raise CurveError("non-finite par rate")
            if not -25.0 <= r <= 100.0:
                raise CurveError(f"par rate {r} outside the plausible band")

    @classmethod
    def from_months(
        cls, tenors_months: Sequence[float], rates_percent: Sequence[float]
    ) -> "ParCurve":
        pairs = sorted(zip((float(m) / 12.0 for m in tenors_months),
                           (float(r) for r in rates_percent)))
        return cls(tuple(t for t, _ in pairs), tuple(r for _, r in pairs))

    def shocked(self, shocks_bp_by_tenor_years: dict[float, float]) -> "ParCurve":
        """Apply an additive basis-point shock per tenor. Unlisted tenors move 0."""
        return ParCurve(
            self.tenors_years,
            tuple(r + shocks_bp_by_tenor_years.get(t, 0.0) / 100.0
                  for t, r in zip(self.tenors_years, self.rates_percent)),
        )

    def shifted(self, shock_bp: float) -> "ParCurve":
        """Parallel shift, in basis points."""
        return ParCurve(self.tenors_years,
                        tuple(r + shock_bp / 100.0 for r in self.rates_percent))

    def par_rate_at(self, tenor_years: float) -> float:
        """Linear interpolation in par yield; flat extrapolation past the ends.

        Flat rather than linear extrapolation because a linearly extrapolated
        long end can go negative or implausibly steep, and a curve that
        silently invents a 40-year point is worse than one that repeats the 30.
        """
        ts, rs = self.tenors_years, self.rates_percent
        if tenor_years <= ts[0]:
            return rs[0]
        if tenor_years >= ts[-1]:
            return rs[-1]
        i = bisect_left(ts, tenor_years)
        if ts[i] == tenor_years:
            return rs[i]
        t0, t1, r0, r1 = ts[i - 1], ts[i], rs[i - 1], rs[i]
        return r0 + (r1 - r0) * (tenor_years - t0) / (t1 - t0)


@dataclass(frozen=True)
class DiscountCurve:
    """Discount factors on a semiannual grid, with log-linear interpolation."""

    times_years: tuple[float, ...]
    discount_factors: tuple[float, ...]
    builder_version: str = "par_bootstrap_logdf_interp_v1"

    def discount_factor(self, t: float) -> float:
        if t < 0:
            raise CurveError(f"negative time to cash flow: {t}")
        if t == 0:
            return 1.0
        ts, ds = self.times_years, self.discount_factors
        if t <= ts[0]:
            # Log-linear between (0, 1.0) and the first node.
            return math.exp(math.log(ds[0]) * (t / ts[0]))
        if t >= ts[-1]:
            # Flat-forward extrapolation: continue the last observed forward
            # rate rather than inventing curvature beyond the data.
            f = -math.log(ds[-1] / ds[-2]) / (ts[-1] - ts[-2])
            return ds[-1] * math.exp(-f * (t - ts[-1]))
        i = bisect_left(ts, t)
        if ts[i] == t:
            return ds[i]
        t0, t1 = ts[i - 1], ts[i]
        w = (t - t0) / (t1 - t0)
        return math.exp((1 - w) * math.log(ds[i - 1]) + w * math.log(ds[i]))

    def zero_rate(self, t: float) -> float:
        """Continuously compounded zero rate in percent. For reporting only."""
        if t <= 0:
            raise CurveError("zero rate undefined at t=0")
        return -math.log(self.discount_factor(t)) / t * 100.0


def build_discount_curve(par: ParCurve, max_years: float = MAX_TENOR_YEARS) -> DiscountCurve:
    """Bootstrap discount factors from a par curve.

    Walks the semiannual grid forward, taking the par rate at each node from
    the interpolated par curve, and solving the par-bond identity for D_n.
    """
    horizon = min(max_years, max(par.tenors_years))
    n_periods = int(round(horizon / SEMIANNUAL))
    if n_periods < 1:
        raise CurveError("curve horizon is shorter than one semiannual period")

    times: list[float] = []
    dfs: list[float] = []
    running_sum = 0.0

    for k in range(1, n_periods + 1):
        t = k * SEMIANNUAL
        c = par.par_rate_at(t) / 100.0
        half_c = c / 2.0
        numerator = 1.0 - half_c * running_sum
        denominator = 1.0 + half_c
        if denominator <= 0:
            raise CurveError(f"degenerate par rate {c:.4%} at {t}y")
        d = numerator / denominator
        # A non-positive or increasing discount factor means the bootstrap has
        # left economic territory - almost always a bad input curve. Fail loudly
        # rather than returning prices built on it.
        if not math.isfinite(d) or d <= 0.0:
            raise CurveError(
                f"non-positive discount factor {d} at {t}y; the par curve is "
                "not arbitrage-consistent under this bootstrap")
        if dfs and d > dfs[-1] + 1e-12:
            raise CurveError(
                f"discount factor rose from {dfs[-1]:.8f} to {d:.8f} at {t}y, "
                "implying a negative forward rate")
        times.append(t)
        dfs.append(d)
        running_sum += d

    return DiscountCurve(tuple(times), tuple(dfs))


def simple_discount_factor(rate_percent: float, t: float) -> float:
    """Money-market discounting for the sub-six-month points."""
    return 1.0 / (1.0 + rate_percent / 100.0 * t)
