"""Model manifest and run fingerprints.

Every number this engine produces carries the identity of the code and
conventions that produced it. Six months later, "VaR was 128,450" is worthless;
"VaR was 128,450 under historical-var 1.0.0, nearest-rank quantile, curve
builder par_bootstrap_logdf_interp_v1, inputs hashing to 0648..." can be
re-run and checked.

The numerical conventions below are part of the model definition, not
implementation detail. Two engines can both honestly claim "99% historical VaR"
and disagree because one interpolates the percentile and the other takes an
order statistic. Naming the convention is what makes the disagreement visible.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

RISK_ENGINE_VERSION = "0.2.0"

MODEL_MANIFEST: dict[str, Any] = {
    "risk_engine_version": RISK_ENGINE_VERSION,
    "curve_builder_version": "par_bootstrap_logdf_interp_v1",
    "pricing_version": "fixed_coupon_full_pv_v1",
    "sensitivity_version": "full_revaluation_bump_v1",
    "historical_risk_version": "absolute_par_shock_full_revaluation_v1",
    "stress_version": "tenor_vector_bp_v1",
    "quantile_method": "nearest_rank_v1",
    "expected_shortfall_method": "mean_of_losses_at_or_beyond_var_v1",

    # --- added in 0.2.0 -----------------------------------------------------
    # Each entry below names a methodology, not a module. A change to any of
    # them changes every fingerprint produced under it, which is the point:
    # "VaR was 128,450" is only checkable if the conventions that produced it
    # travel with the number.
    "revaluation_version": "compiled_full_reval_v1",
    "bond_analytics_version": "icma_quasi_period_analytics_v1",
    "ytm_solver_version": "brent_bisection_secant_v1",
    "accrued_interest_method": "act_act_icma_quasi_coupon_period_v1",
    "duration_method": "macaulay_from_ytm_periods_v1",
    "convexity_method": "second_derivative_from_ytm_periods_years_squared_v1",
    "effective_sensitivity_method": "central_difference_parallel_par_shift_v1",
    "curve_analytics_version": "bootstrapped_zero_forward_v1",
    "forward_rate_method": "continuous_from_log_discount_ratio_v1",
    "butterfly_method": "two_belly_minus_wings_v1",
    "curve_spread_method": "long_tenor_minus_short_tenor_v1",
    "stress_scenario_version": "control_point_templates_linear_in_years_v1",
    "stress_matrix_version": "standard_pack_2026_08_v1",
    "tenor_attribution_method": "first_order_key_rate_with_stated_residual_v1",
    "historical_stress_version": "observed_curve_difference_full_reval_v1",
    "historical_crisis_catalogue_version": "documented_windows_v1",
    "reverse_stress_version": "bracketed_bisection_secant_v1",
    "volatility_method": "sample_stdev_of_absolute_bp_changes_v1",
    "covariance_method": "sample_covariance_bp_changes_ddof1_v1",
    "psd_repair_method": "jacobi_eigenvalue_clipping_v1",
    "parametric_var_version": "delta_normal_key_rate_exposure_v1",
    "parametric_horizon_scaling": "sqrt_time_on_the_parametric_path_only_v1",
    "monte_carlo_version": "cholesky_box_muller_full_reval_v1",
    "monte_carlo_rng": "python_mersenne_twister_explicit_box_muller_v1",
    "extreme_tail_version": "labelled_tail_methodologies_v1",
    "backtesting_version": "exception_counting_strict_exceedance_v1",
    "kupiec_test_version": "unconditional_coverage_lr_chi2_1df_v1",
    "christoffersen_test_version": "markov_independence_lr_chi2_1df_v1",
    "conditional_coverage_test_version": "kupiec_plus_christoffersen_chi2_2df_v1",
    "pnl_attribution_version": "carry_roll_rate_residual_v1",
    "carry_roll_version": "forward_value_carry_static_curve_roll_v1",
    "risk_contribution_version": "euler_scenario_decomposition_v1",
    "concentration_version": "share_and_herfindahl_v1",
    "risk_limits_version": "explicit_threshold_utilisation_v1",
    "portfolio_comparison_version": "paired_measure_difference_v1",
    "frtb_girr_version": "bcbs_mar21_girr_delta_curvature_v1",
    "numeric_policy": {
        "interchange": "decimal strings; rates in percent, money with currency",
        "internal_arithmetic": "IEEE-754 binary64",
        "time_basis": (
            "ACT/ACT ICMA quasi-coupon periods: t = (i + 1 - w) / frequency. "
            "Deliberately the same basis the bootstrap uses, so a par bond "
            "prices to exactly 100 rather than 99.96"
        ),
        "coupon_frequency": "semiannual only",
        "par_node_interpolation": "linear in par yield against tenor in years",
        "discount_interpolation": "linear in log discount factor against time",
        "short_end": "tenors below 0.5y discounted simply: D = 1/(1 + y*t)",
        "intermediate_rounding": "none",
        "quantile": "nearest rank, k = ceil(alpha * N), no interpolation",
        "horizon": "observed h-day changes; never sqrt(h) scaling of 1-day",
        "missing_data": "reject; never interpolated across dates",
        "rate_shock_unit": "basis points, additive on the par yield",
        "pnl_sign": "stressed PV minus base PV; negative is a loss",
        "dv01_sign": "base PV minus PV after +1bp; positive for a long book",
        "curve_spread_sign": "long-tenor yield minus short-tenor yield",
        "butterfly": "2 x belly - short wing - long wing, in basis points",
        "var_sign": "reported as a positive loss threshold",
        "es_sign": "reported as a positive expected tail loss",
        "duration_unit": "years",
        "convexity_unit": (
            "years squared; price approximation dP/P = -D_mod*dy + 0.5*C*dy^2 "
            "with dy in decimal"
        ),
        "backtest_exception": (
            "strict exceedance: a loss exactly equal to the VaR forecast is not "
            "an exception"
        ),
        "template_interpolation": (
            "control points linear in tenor-years, flat beyond the outermost "
            "control point"
        ),
        "attribution_residual": (
            "reported, never forced to zero - the residual is the model control"
        ),
    },
    "supported_instruments": ["FIXED_RATE_BOND"],
    "regulatory_scope": {
        "implemented": ["FRTB_SA_GIRR_DELTA", "FRTB_SA_GIRR_CURVATURE"],
        "not_implemented": [
            "CSR_NON_SEC", "CSR_SEC", "DRC", "FX", "EQUITY", "COMMODITY",
            "VEGA", "RRAO", "NMRF", "PLA", "IMA_ES",
        ],
        "why": (
            "Those risk classes need instruments and market data this system "
            "does not hold. A capital number computed over an absent risk class "
            "is not conservative, it is wrong. See docs/capability-gaps.md."
        ),
    },
    "currency": "USD",
    "limitations": (
        "Model-implied values from the published Treasury par curve, not "
        "executable prices. No floating-rate notes, inflation-linked "
        "instruments, options, credit, repo/funding or FX."
    ),
}


def canonical_json(payload: Any) -> str:
    """Stable serialisation: sorted keys, no whitespace, decimals as strings.

    A fingerprint is only meaningful if the same logical input always produces
    the same bytes, so key order and float formatting cannot be left to chance.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def run_fingerprint(inputs: Any) -> str:
    """Identify a calculation by its inputs *and* the model that consumed them.

    Both halves are needed. Same inputs under a changed quantile convention is
    a different calculation and must not collide with the original.
    """
    combined = canonical_json(inputs) + "\x00" + canonical_json(MODEL_MANIFEST)
    return hashlib.sha256(combined.encode()).hexdigest()


def reproducibility_block(inputs: Any, extra: dict[str, str] | None = None) -> dict[str, Any]:
    block = {
        "input_sha256": sha256_of(inputs),
        "model_manifest_sha256": sha256_of(MODEL_MANIFEST),
        "run_fingerprint": run_fingerprint(inputs),
    }
    block.update(extra or {})
    return block
