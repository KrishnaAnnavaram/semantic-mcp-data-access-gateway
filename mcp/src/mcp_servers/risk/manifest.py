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

RISK_ENGINE_VERSION = "0.1.0"

MODEL_MANIFEST: dict[str, Any] = {
    "risk_engine_version": RISK_ENGINE_VERSION,
    "curve_builder_version": "par_bootstrap_logdf_interp_v1",
    "pricing_version": "fixed_coupon_full_pv_v1",
    "sensitivity_version": "full_revaluation_bump_v1",
    "historical_risk_version": "absolute_par_shock_full_revaluation_v1",
    "stress_version": "tenor_vector_bp_v1",
    "quantile_method": "nearest_rank_v1",
    "expected_shortfall_method": "mean_of_losses_at_or_beyond_var_v1",
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
    },
    "supported_instruments": ["FIXED_RATE_BOND"],
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
