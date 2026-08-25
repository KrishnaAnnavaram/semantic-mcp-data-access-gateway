"""Delta-normal VaR and ES.  `delta_normal_key_rate_exposure_v1`

A closed-form alternative to historical simulation, kept deliberately separate
from it and never blended. The two disagree, and the disagreement is the point:
where parametric VaR sits well below the historical figure, the loss
distribution has a fatter tail than a normal, and that is a finding.

## The model, stated in full

1. The risk factors are the par yields at the curve's key tenors.
2. The portfolio's exposure to each is its key-rate DV01, so the P&L of a
   change vector `dy` (in basis points) is approximated as
   `P&L = -sum_t KRD_t * dy_t`. **This is a linear approximation** - it has no
   convexity in it at all, which is exactly why it is cheap and exactly why it
   understates the loss on a 30-year bond in a large move.
3. `dy` is multivariate normal with the sample covariance of the observed
   changes, and with zero mean unless the caller asks otherwise.
4. Then `sigma_P = sqrt(e' Sigma e)` and
   `VaR = z_alpha * sigma_P`, `ES = phi(z_alpha)/(1-alpha) * sigma_P`.

The ES formula is the closed form for a normal distribution and only for a
normal distribution. It is not the historical ES estimator with a different
input, and it is labelled with its own method name so a comparison table cannot
present the two as the same measure computed twice.

## Horizon

Two paths, and the caller picks:

* `observed` (default) - the covariance is estimated from actual h-day changes.
  Consistent with the historical method in this engine.
* `sqrt_time` - the covariance is estimated from 1-day changes and the result
  scaled by `sqrt(h)`. Legitimate *here*, because the model already assumes
  independent normal increments and the scaling follows from that assumption
  rather than contradicting it. The same shortcut is forbidden on the historical
  path, where nothing licenses it.

Whichever ran is named in the output. A 10-day VaR whose derivation is not
stated is not comparable with anything.

## Contributions are exact

Component VaR here is the Euler decomposition of a homogeneous risk measure:
`marginal_t = z * (Sigma e)_t / sigma_P` and `component_t = e_t * marginal_t`,
and the components sum to the VaR identically. That is a theorem about
positively homogeneous functions, not a normalisation applied afterwards, and
the reconciliation figure in the result should always be at machine precision.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

from .curves import ParCurve
from .errors import EngineError
from .linalg import Matrix, matrix_vector, min_eigenvalue, quadratic_form
from .revaluation import CompiledBook, key_rate_exposures
from .volatility import covariance_matrix, observed_changes_bp

HorizonMethod = Literal["observed", "sqrt_time"]

STANDARD_NORMAL = NormalDist(0.0, 1.0)


@dataclass(frozen=True)
class FactorExposure:
    tenor_years: float
    key_rate_dv01: float
    exposure_per_bp: float
    volatility_bp: float
    marginal_var: float
    component_var: float
    component_percent: float


@dataclass(frozen=True)
class ParametricRisk:
    base_value: float
    confidence_level: float
    horizon_days: int
    horizon_method: HorizonMethod
    z_score: float
    portfolio_volatility: float
    mean_pnl: float
    var: float
    expected_shortfall: float
    observations_used: int
    include_mean: bool
    factors: tuple[FactorExposure, ...]
    covariance_is_psd: bool
    smallest_eigenvalue: float
    var_reconciliation_difference: float = 0.0
    reconciliation_note: str = (
        "Component VaR sums to z * portfolio_volatility exactly. When "
        "include_mean is true the reported VaR also subtracts the drift, which "
        "is not decomposed, so the components then sum to VaR + mean_pnl."
    )
    distribution: str = "multivariate normal on absolute basis-point changes"
    method: str = "delta_normal_key_rate_exposure_v1"


def normal_expected_shortfall_multiplier(confidence_level: float) -> float:
    """phi(z_alpha) / (1 - alpha): the ES-to-sigma ratio under a normal."""
    z = STANDARD_NORMAL.inv_cdf(confidence_level)
    return STANDARD_NORMAL.pdf(z) / (1.0 - confidence_level)


def compute_parametric_risk(
    book: CompiledBook, par: ParCurve,
    history_tenors_years: Sequence[float],
    history_rates_percent: Sequence[Sequence[float]],
    confidence_level: float = 0.99, horizon_days: int = 1,
    horizon_method: HorizonMethod = "observed", include_mean: bool = False,
    bump_bp: float = 1.0,
) -> ParametricRisk:
    if not 0.5 <= confidence_level < 1.0:
        raise EngineError(
            "INVALID_CONFIDENCE_LEVEL",
            f"confidence_level {confidence_level} is outside [0.5, 1.0)",
            category="USER_INPUT",
            suggested_action="Use 0.95, 0.975 or 0.99.")
    if horizon_days < 1:
        raise EngineError(
            "INVALID_HORIZON", f"horizon_days must be at least 1; got {horizon_days}",
            category="USER_INPUT")

    live = set(par.tenors_years)
    columns = [j for j, t in enumerate(history_tenors_years) if float(t) in live]
    tenors = [float(history_tenors_years[j]) for j in columns]
    if len(tenors) < 1:
        raise EngineError(
            "MISSING_REQUIRED_MARKET_DATA",
            "none of the history's tenors are nodes on the valuation curve, so "
            "no exposure vector can be formed.",
            category="DATA_AVAILABILITY",
            suggested_action=(
                "Fetch the history on the same tenor set as the valuation curve."),
            details={"history_tenors_years": [float(t) for t in history_tenors_years],
                     "curve_nodes_years": list(par.tenors_years)})

    sample_horizon = 1 if horizon_method == "sqrt_time" else horizon_days
    changes = observed_changes_bp(history_rates_percent, sample_horizon)
    trimmed = [[row[j] for j in columns] for row in changes]
    cov = covariance_matrix(trimmed)
    means = [sum(row[i] for row in trimmed) / len(trimmed) for i in range(len(tenors))]

    base_value, krd_totals, _ = key_rate_exposures(book, par, bump_bp)
    krd = dict(krd_totals)
    # Exposure sign: P&L = -KRD * dy, so the exposure vector is -KRD.
    exposure = [-krd[t] for t in tenors]

    variance = quadratic_form(exposure, cov)
    if variance < 0:
        raise EngineError(
            "INVALID_COVARIANCE_MATRIX",
            f"the estimated covariance gives a negative portfolio variance "
            f"({variance:.6g}); it is not positive semidefinite and the result "
            "would be an imaginary volatility reported as a number.",
            category="NUMERICAL",
            suggested_action=(
                "Widen the estimation window, or drop tenors that moved "
                "identically over it."))
    sigma = math.sqrt(variance)
    scaling = math.sqrt(horizon_days) if horizon_method == "sqrt_time" else 1.0
    sigma *= scaling
    mean_pnl = (sum(e * m for e, m in zip(exposure, means)) * scaling
                if include_mean else 0.0)

    z = STANDARD_NORMAL.inv_cdf(confidence_level)
    var = max(0.0, z * sigma - mean_pnl)
    es = max(0.0, normal_expected_shortfall_multiplier(confidence_level) * sigma - mean_pnl)

    # Euler decomposition. With sigma_h = scaling * sqrt(e' Sigma e),
    #
    #     d(sigma_h)/de_t = scaling^2 * (Sigma e)_t / sigma_h
    #     marginal_t      = z * d(sigma_h)/de_t
    #     component_t     = e_t * marginal_t
    #
    # and sum_t component_t = z * sigma_h = VaR exactly, because VaR is
    # positively homogeneous of degree one in the exposure vector. The scaling
    # appears squared because it is inside sigma_h in the denominator as well.
    sigma_e = matrix_vector(cov, exposure)
    marginals = [(z * scaling * scaling * v / sigma) if sigma > 0 else 0.0
                 for v in sigma_e]
    components = [e * m for e, m in zip(exposure, marginals)]
    total_component = sum(components)

    factors = tuple(
        FactorExposure(
            tenor_years=t, key_rate_dv01=krd[t], exposure_per_bp=e,
            volatility_bp=math.sqrt(cov[i][i]) * scaling if cov[i][i] > 0 else 0.0,
            marginal_var=m, component_var=c,
            component_percent=(c / total_component * 100.0) if total_component else 0.0)
        for i, (t, e, m, c) in enumerate(zip(tenors, exposure, marginals, components)))

    return ParametricRisk(
        base_value=base_value, confidence_level=confidence_level,
        horizon_days=horizon_days, horizon_method=horizon_method, z_score=z,
        portfolio_volatility=sigma, mean_pnl=mean_pnl, var=var,
        expected_shortfall=es, observations_used=len(trimmed),
        include_mean=include_mean, factors=factors,
        covariance_is_psd=min_eigenvalue(cov) >= -1e-10,
        smallest_eigenvalue=min_eigenvalue(cov),
        var_reconciliation_difference=total_component - (z * sigma),
    )


def parametric_from_covariance(
    exposure_per_bp: Sequence[float], covariance_bp2: Matrix,
    confidence_level: float = 0.99, horizon_days: int = 1,
    horizon_method: HorizonMethod = "observed",
) -> tuple[float, float, float]:
    """(sigma, VaR, ES) for a supplied exposure vector and covariance.

    The entry point a correlation-stress scenario uses: same closed form, but
    on a covariance that was constructed rather than estimated.
    """
    variance = quadratic_form(list(exposure_per_bp), covariance_bp2)
    if variance < 0:
        raise EngineError(
            "INVALID_COVARIANCE_MATRIX",
            f"the supplied covariance gives a negative portfolio variance "
            f"({variance:.6g}) and cannot be used.",
            category="NUMERICAL",
            suggested_action="Repair the matrix to the nearest PSD one first.")
    sigma = math.sqrt(variance)
    if horizon_method == "sqrt_time":
        sigma *= math.sqrt(horizon_days)
    z = STANDARD_NORMAL.inv_cdf(confidence_level)
    return (sigma, z * sigma,
            normal_expected_shortfall_multiplier(confidence_level) * sigma)
