"""Scenario generation.  `control_point_templates_linear_in_years_v1`

`run_stress` already revalues a book under an explicit tenor-to-basis-point
vector, and that stays the engine underneath everything here. What was missing
is the layer above it: the vocabulary a risk manager actually uses. Nobody asks
for `{2.0: 25, 5.0: 50, 10.0: 100, 30.0: 150}`. They ask for a bear steepener.

So this module turns names into vectors, and **the vector always travels with
the result**. A scenario library whose shapes cannot be inspected is a set of
numbers nobody can check; the moment "bear steepener" means something slightly
different in two reports, the only way to find out is to read the shocks.

## The templates

Each named shape is a handful of **control points** expressed as multipliers of
a single `severity_bp`. At severity 100 they reproduce the canonical desk
shapes exactly:

| template        |  2Y  |  5Y  | 10Y  | 30Y  |
|-----------------|------|------|------|------|
| BEAR_STEEPENER  | +25  | +50  | +100 | +150 |
| BULL_STEEPENER  | -150 | -100 | -50  | -25  |
| BEAR_FLATTENER  | +150 | +100 | +50  | +25  |
| BULL_FLATTENER  | -25  | -50  | -100 | -150 |
| BELLY_SELLOFF   | +25  | +100 | +100 | +25  |
| WINGS_SELLOFF   | +100 | +25  | +25  | +100 |

Steepener and flattener are named for what happens to the *curve*, not to the
direction of rates: a bear steepener sells off with the long end leading, a bull
steepener rallies with the front end leading. Both steepen. Getting this pair
the wrong way round is the most common naming error in scenario libraries and it
is invisible in the output unless the vector is printed.

## Between the control points

Curves have nodes the templates do not mention - 1Y, 3Y, 7Y, 20Y. Two documented
rules fill them in:

* `linear_years` (default) - linear in tenor measured in years, held flat
  beyond the outermost control point. Uniform in economic time, so a 20Y sits
  where its maturity puts it.
* `node_rank` - linear in the *position* of the tenor within the curve's node
  list. Spreads a shape evenly across the published points regardless of how
  they are spaced, and is what reproduces the textbook twist table
  (2Y -100, 5Y -50, 10Y 0, 20Y +50, 30Y +100) exactly.

Neither is more correct. They are different scenarios, and which one ran is
recorded in the result.

## Severity labels

`MILD` / `MODERATE` / `SEVERE` / `EXTREME` are **project-defined** magnitudes,
not a regulatory classification. Nothing in the Basel framework, and no
supervisor, prescribes them. They are here so a request for "a severe
steepener" resolves to one reproducible number instead of the model's mood.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from .curves import ParCurve
from .errors import EngineError

Interpolation = Literal["linear_years", "node_rank"]

ScenarioType = Literal[
    "PARALLEL", "STEEPENER", "FLATTENER", "TWIST", "CURVATURE", "KEY_RATE",
    "CUSTOM", "HISTORICAL_REPLAY", "SEVERITY_PACK", "CONCENTRATION",
]

# Control points as multipliers of severity_bp, keyed by tenor in years.
TEMPLATES: dict[str, tuple[ScenarioType, dict[float, float]]] = {
    "BEAR_STEEPENER": ("STEEPENER", {2.0: 0.25, 5.0: 0.50, 10.0: 1.00, 30.0: 1.50}),
    "BULL_STEEPENER": ("STEEPENER", {2.0: -1.50, 5.0: -1.00, 10.0: -0.50, 30.0: -0.25}),
    "BEAR_FLATTENER": ("FLATTENER", {2.0: 1.50, 5.0: 1.00, 10.0: 0.50, 30.0: 0.25}),
    "BULL_FLATTENER": ("FLATTENER", {2.0: -0.25, 5.0: -0.50, 10.0: -1.00, 30.0: -1.50}),
    "BELLY_SELLOFF": ("CURVATURE", {2.0: 0.25, 5.0: 1.00, 10.0: 1.00, 30.0: 0.25}),
    "BELLY_RALLY": ("CURVATURE", {2.0: -0.25, 5.0: -1.00, 10.0: -1.00, 30.0: -0.25}),
    "WINGS_SELLOFF": ("CURVATURE", {2.0: 1.00, 5.0: 0.25, 10.0: 0.25, 30.0: 1.00}),
    "WINGS_RALLY": ("CURVATURE", {2.0: -1.00, 5.0: -0.25, 10.0: -0.25, 30.0: -1.00}),
}

# Project-defined, and labelled as such wherever they surface.
SEVERITY_BP: dict[str, float] = {
    "MILD": 25.0,
    "MODERATE": 100.0,
    "SEVERE": 200.0,
    "EXTREME": 300.0,
}

SEVERITY_NOTE = (
    "MILD/MODERATE/SEVERE/EXTREME are project-defined magnitudes (25/100/200/"
    "300bp), not a regulatory classification. No supervisor prescribes them."
)


@dataclass(frozen=True)
class ShockVector:
    """A scenario reduced to what the revaluation engine actually consumes."""

    scenario_name: str
    scenario_type: ScenarioType
    shocks_bp_by_tenor_years: dict[float, float]
    interpolation: Interpolation | None = None
    severity_bp: float | None = None
    template: str | None = None
    parameters: dict[str, object] = field(default_factory=dict)

    def as_months(self) -> dict[str, float]:
        """The wire form: tenor in months as a string key, shock in basis points."""
        return {str(t * 12.0): v for t, v in sorted(self.shocks_bp_by_tenor_years.items())}

    def max_absolute_bp(self) -> float:
        return max((abs(v) for v in self.shocks_bp_by_tenor_years.values()), default=0.0)

    def scaled(self, multiplier: float) -> ShockVector:
        """The same shape at a different magnitude - the reverse-stress lever."""
        return ShockVector(
            scenario_name=f"{self.scenario_name} x{multiplier:.4g}",
            scenario_type=self.scenario_type,
            shocks_bp_by_tenor_years={t: v * multiplier
                                      for t, v in self.shocks_bp_by_tenor_years.items()},
            interpolation=self.interpolation,
            severity_bp=(self.severity_bp * multiplier
                         if self.severity_bp is not None else None),
            template=self.template,
            parameters={**self.parameters, "multiplier": multiplier},
        )


def _interpolate_control_points(
    par: ParCurve, control: dict[float, float], interpolation: Interpolation,
) -> dict[float, float]:
    """Evaluate a control-point shape at every node of the curve."""
    points = sorted(control.items())
    if interpolation == "linear_years":
        axis = [t for t, _ in points]
        node_axis = list(par.tenors_years)
    elif interpolation == "node_rank":
        axis = [_node_position(par, t) for t, _ in points]
        node_axis = [float(i) for i in range(len(par.tenors_years))]
    else:  # pragma: no cover - guarded by the Literal at the boundary
        raise EngineError("INVALID_STRESS_VECTOR",
                          f"unknown interpolation {interpolation!r}")
    values = [v for _, v in points]

    out: dict[float, float] = {}
    for tenor, x in zip(par.tenors_years, node_axis):
        if x <= axis[0]:
            out[tenor] = values[0]
        elif x >= axis[-1]:
            out[tenor] = values[-1]
        else:
            for (x0, v0), (x1, v1) in zip(list(zip(axis, values)),
                                          list(zip(axis, values))[1:]):
                if x0 <= x <= x1:
                    w = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
                    out[tenor] = v0 + (v1 - v0) * w
                    break
    return out


def _node_position(par: ParCurve, tenor_years: float) -> float:
    """A tenor's (possibly fractional) index in the curve's node list."""
    tenors = par.tenors_years
    if tenor_years <= tenors[0]:
        return 0.0
    if tenor_years >= tenors[-1]:
        return float(len(tenors) - 1)
    for i, (a, b) in enumerate(zip(tenors, tenors[1:])):
        if a <= tenor_years <= b:
            return i + (tenor_years - a) / (b - a)
    return float(len(tenors) - 1)  # pragma: no cover


def parallel_shock(par: ParCurve, shock_bp: float, name: str | None = None) -> ShockVector:
    return ShockVector(
        scenario_name=name or f"Parallel {shock_bp:+.0f}bp",
        scenario_type="PARALLEL",
        shocks_bp_by_tenor_years={t: shock_bp for t in par.tenors_years},
        severity_bp=abs(shock_bp),
        parameters={"shock_bp": shock_bp},
    )


def template_shock(
    par: ParCurve, template: str, severity_bp: float = 100.0,
    interpolation: Interpolation = "linear_years", name: str | None = None,
) -> ShockVector:
    key = template.upper()
    if key not in TEMPLATES:
        raise EngineError(
            "UNKNOWN_SCENARIO_TEMPLATE",
            f"{template!r} is not a scenario template this engine defines.",
            category="USER_INPUT",
            suggested_action=f"Choose one of {sorted(TEMPLATES)}.",
            details={"available_templates": sorted(TEMPLATES)})
    if severity_bp <= 0:
        raise EngineError(
            "INVALID_STRESS_VECTOR",
            f"severity_bp must be positive; got {severity_bp}. The direction of "
            "a template is part of its definition, so a negative severity would "
            "silently invert a bear scenario into a bull one.",
            category="USER_INPUT",
            suggested_action="Use the matching BULL_/BEAR_ template instead.")
    scenario_type, control = TEMPLATES[key]
    scaled = {t: m * severity_bp for t, m in control.items()}
    return ShockVector(
        scenario_name=name or f"{key.replace('_', ' ').title()} {severity_bp:.0f}bp",
        scenario_type=scenario_type,
        shocks_bp_by_tenor_years=_interpolate_control_points(par, scaled, interpolation),
        interpolation=interpolation,
        severity_bp=severity_bp,
        template=key,
        parameters={"control_points_bp": {str(t): v for t, v in sorted(scaled.items())}},
    )


def twist_shock(
    par: ParCurve, pivot_tenor_years: float, magnitude_bp: float,
    interpolation: Interpolation = "linear_years", name: str | None = None,
) -> ShockVector:
    """Rotate the curve about a pivot: -magnitude at the short end, +magnitude at the long.

    A negative magnitude inverts the rotation (short end sells off, long end
    rallies), which is the meaningful opposite of a twist and so is allowed here
    where a negative template severity is not.

    The pivot itself moves exactly zero, by construction rather than by
    interpolation, and a test asserts it.
    """
    lo, hi = par.tenors_years[0], par.tenors_years[-1]
    if not lo <= pivot_tenor_years <= hi:
        raise EngineError(
            "INVALID_STRESS_VECTOR",
            f"pivot {pivot_tenor_years:g}y is outside the curve ({lo:g}y-{hi:g}y); "
            "there is nothing to rotate about.",
            category="USER_INPUT",
            suggested_action=f"Choose a pivot between {lo:g}y and {hi:g}y.")

    if interpolation == "node_rank":
        pos = {t: float(i) for i, t in enumerate(par.tenors_years)}
        pivot_x, lo_x, hi_x = _node_position(par, pivot_tenor_years), 0.0, float(len(par.tenors_years) - 1)
    else:
        pos = {t: t for t in par.tenors_years}
        pivot_x, lo_x, hi_x = pivot_tenor_years, lo, hi

    shocks: dict[float, float] = {}
    for t in par.tenors_years:
        x = pos[t]
        if x < pivot_x:
            span = pivot_x - lo_x
            shocks[t] = -magnitude_bp * ((pivot_x - x) / span if span > 0 else 0.0)
        elif x > pivot_x:
            span = hi_x - pivot_x
            shocks[t] = magnitude_bp * ((x - pivot_x) / span if span > 0 else 0.0)
        else:
            shocks[t] = 0.0
    return ShockVector(
        scenario_name=name or (f"Twist about {pivot_tenor_years:g}y "
                               f"{magnitude_bp:+.0f}bp at the long end"),
        scenario_type="TWIST",
        shocks_bp_by_tenor_years=shocks,
        interpolation=interpolation,
        severity_bp=abs(magnitude_bp),
        parameters={"pivot_tenor_years": pivot_tenor_years,
                    "magnitude_bp": magnitude_bp},
    )


def key_rate_shock(
    par: ParCurve, tenors_years: Sequence[float], shock_bp: float,
    name: str | None = None,
) -> ShockVector:
    """Move named curve nodes and nothing else. No tent, no smoothing.

    Every other node stays exactly where it was, so the result is directly
    comparable with `compute_key_rate_dv01`, which perturbs the same way. A
    non-node tenor is refused rather than snapped to a neighbour: bumping an
    interpolated point perturbs its neighbours too, and the answer would not be
    the sensitivity to the tenor that was named.
    """
    nodes = set(par.tenors_years)
    unknown = [t for t in tenors_years if t not in nodes]
    if unknown:
        raise EngineError(
            "MISSING_CURVE_TENOR",
            f"key tenors {unknown} are not nodes on this curve. Shocking an "
            "interpolated point moves its neighbours as well, so the result "
            "would not be the sensitivity to the tenor named.",
            category="USER_INPUT",
            suggested_action=f"Choose from the curve's nodes: {list(par.tenors_years)}.",
            details={"curve_nodes_years": list(par.tenors_years)})
    if not list(tenors_years):
        raise EngineError(
            "INVALID_STRESS_VECTOR", "no key tenors were given to shock",
            category="USER_INPUT")
    targets = set(tenors_years)
    label = ", ".join(f"{t:g}y" for t in sorted(targets))
    return ShockVector(
        scenario_name=name or f"Key rate {label} {shock_bp:+.0f}bp",
        scenario_type="KEY_RATE",
        shocks_bp_by_tenor_years={t: (shock_bp if t in targets else 0.0)
                                  for t in par.tenors_years},
        severity_bp=abs(shock_bp),
        parameters={"key_tenors_years": sorted(targets), "shock_bp": shock_bp},
    )


def custom_shock(
    par: ParCurve, shocks_bp_by_tenor_years: dict[float, float],
    name: str = "Custom shock vector", scenario_type: ScenarioType = "CUSTOM",
    allow_unknown_tenors: bool = False,
) -> ShockVector:
    """Validate a caller-supplied vector against the curve it will be applied to.

    `ParCurve.shocked` ignores a tenor that is not a node, so a vector with a
    typo'd key applies a *smaller* shock than the caller asked for and reports
    success. That silent partial application is refused here.
    """
    nodes = set(par.tenors_years)
    unknown = sorted(t for t in shocks_bp_by_tenor_years if t not in nodes)
    if unknown and not allow_unknown_tenors:
        raise EngineError(
            "INVALID_STRESS_VECTOR",
            f"the shock vector names tenors {unknown} that are not on this "
            "curve. They would be silently dropped, applying a smaller shock "
            "than requested.",
            category="USER_INPUT",
            suggested_action=(
                "Use the curve's own nodes, or pass allow_unknown_tenors=true "
                "to accept that the extra tenors do nothing."),
            details={"curve_nodes_years": list(par.tenors_years),
                     "unknown_tenors_years": unknown})
    for tenor, value in shocks_bp_by_tenor_years.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise EngineError(
                "INVALID_STRESS_VECTOR",
                f"the shock at {tenor}y is {value!r}, which is not a finite "
                "number. A NaN shock propagates silently through the bootstrap "
                "and reaches a report as a blank rather than as an error.",
                category="USER_INPUT",
                suggested_action="Supply a finite basis-point shock per tenor.")
    filled = {t: float(shocks_bp_by_tenor_years.get(t, 0.0)) for t in par.tenors_years}
    return ShockVector(
        scenario_name=name, scenario_type=scenario_type,
        shocks_bp_by_tenor_years=filled,
        severity_bp=max((abs(v) for v in filled.values()), default=0.0),
        parameters={"unknown_tenors_ignored": unknown} if unknown else {},
    )


def severity_pack(
    par: ParCurve, template: str, interpolation: Interpolation = "linear_years",
    severities: Sequence[str] | None = None,
) -> list[ShockVector]:
    """The same shape at MILD, MODERATE, SEVERE and EXTREME magnitudes."""
    names = list(severities) if severities else list(SEVERITY_BP)
    unknown = [n for n in names if n.upper() not in SEVERITY_BP]
    if unknown:
        raise EngineError(
            "UNKNOWN_SCENARIO_TEMPLATE",
            f"unknown severity label(s) {unknown}",
            category="USER_INPUT",
            suggested_action=f"Choose from {list(SEVERITY_BP)}.")
    out = []
    for label in names:
        bp = SEVERITY_BP[label.upper()]
        if template.upper() == "PARALLEL_UP":
            vector = parallel_shock(par, bp, name=f"Parallel +{bp:.0f}bp ({label.upper()})")
        elif template.upper() == "PARALLEL_DOWN":
            vector = parallel_shock(par, -bp, name=f"Parallel -{bp:.0f}bp ({label.upper()})")
        else:
            vector = template_shock(
                par, template, bp, interpolation,
                name=f"{template.upper().replace('_', ' ').title()} {bp:.0f}bp ({label.upper()})")
        out.append(ShockVector(
            scenario_name=vector.scenario_name, scenario_type="SEVERITY_PACK",
            shocks_bp_by_tenor_years=vector.shocks_bp_by_tenor_years,
            interpolation=vector.interpolation, severity_bp=bp,
            template=vector.template or template.upper(),
            parameters={**vector.parameters, "severity_label": label.upper(),
                        "severity_note": SEVERITY_NOTE}))
    return out
