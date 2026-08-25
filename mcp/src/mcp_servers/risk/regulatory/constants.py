"""Basel FRTB parameters, in one place, with their source.  `bcbs_mar21_v1`

Every number in this file is prescribed by a supervisor. That makes it a
different kind of constant from the rest of the engine: it is not a modelling
choice, it cannot be tuned, and it changes only when the standard changes.

So it lives here rather than being spelled inline at the point of use. A risk
weight written into a formula is invisible at review, impossible to diff against
the standard, and unversioned - and the failure mode is a capital number that is
confidently wrong and passes every test, because the tests were written from the
same misremembered figure.

**Source.** Basel Committee on Banking Supervision, *Minimum capital
requirements for market risk*, chapter MAR21 "Standardised approach:
sensitivities-based method". The paragraph references below use the MAR21.x
numbering of the consolidated Basel Framework; national implementations
renumber the same text (the Saudi Central Bank rulebook, for example, carries it
as sections 7.x), and the parameters are identical.

**Scope.** GIRR only. This system holds interest-rate instruments and nothing
else, so credit spread, equity, FX, commodity, vega and default risk parameters
are deliberately absent. Adding a table here without the instruments and market
data to feed it would produce a capital number for a risk class that is not
being measured, which is worse than reporting no number at all.
"""

from __future__ import annotations

FRTB_SOURCE = (
    "BCBS, Minimum capital requirements for market risk, MAR21 "
    "(Standardised approach: sensitivities-based method)"
)
FRTB_CONSTANTS_VERSION = "bcbs_mar21_girr_v1"

# MAR21.8(1): the prescribed GIRR delta vertices, in years.
GIRR_VERTICES_YEARS: tuple[float, ...] = (
    0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 20.0, 30.0,
)

# MAR21.42, Table 1: GIRR delta risk weights per vertex, as decimals.
GIRR_DELTA_RISK_WEIGHTS: dict[float, float] = {
    0.25: 0.017,
    0.5: 0.017,
    1.0: 0.016,
    2.0: 0.013,
    3.0: 0.012,
    5.0: 0.011,
    10.0: 0.011,
    15.0: 0.011,
    20.0: 0.011,
    30.0: 0.011,
}

# MAR21.43: the inflation and cross-currency basis risk weights. Listed for
# completeness of the citation; neither risk factor exists in this system.
GIRR_INFLATION_RISK_WEIGHT = 0.016
GIRR_CROSS_CURRENCY_BASIS_RISK_WEIGHT = 0.016

# MAR21.46 footnote: rho(k,l) = max(40%, exp(-theta * |T_k - T_l| / min(T_k, T_l)))
GIRR_CORRELATION_THETA = 0.03
GIRR_CORRELATION_FLOOR = 0.40

# MAR21.47: between two different curves in the same currency bucket, the tenor
# correlation is multiplied by 99.90%. One curve here, so it never bites.
GIRR_DIFFERENT_CURVE_MULTIPLIER = 0.999

# MAR21.48 / MAR21.49: inflation to yield curve, and cross-currency basis to
# everything else. Present for citation completeness only.
GIRR_INFLATION_CORRELATION = 0.40
GIRR_CROSS_CURRENCY_BASIS_CORRELATION = 0.0

# MAR21.50: correlation between GIRR buckets, i.e. between currencies.
GIRR_INTER_BUCKET_CORRELATION = 0.50

# MAR21.6: the three prescribed correlation scenarios.
HIGH_CORRELATION_MULTIPLIER = 1.25
LOW_CORRELATION_ALTERNATIVE_MULTIPLIER = 2.0     # max(2*rho - 100%, 75%*rho)
LOW_CORRELATION_FLOOR_MULTIPLIER = 0.75

# MAR21.99: for GIRR the curvature shock is a parallel shift of every vertex of
# the curve, sized at the highest prescribed delta risk weight in the bucket -
# which is the 0.25-year weight, the most punitive one.
GIRR_CURVATURE_RISK_WEIGHT = max(GIRR_DELTA_RISK_WEIGHTS.values())

# MAR21.19: PV01 is the value change for a 1bp move, divided by 0.0001. The
# division is what turns a per-basis-point figure into a per-unit-rate
# sensitivity, and it is the difference between a capital number and one that is
# ten thousand times too small.
BASIS_POINT = 0.0001

# Risk classes the sensitivities-based method covers, and what this system can
# actually measure. Anything false here must never appear in a capital figure.
RISK_CLASS_SUPPORT: dict[str, bool] = {
    "GIRR_DELTA": True,
    "GIRR_CURVATURE": True,
    "GIRR_VEGA": False,          # no options in the book
    "CSR_NON_SEC": False,        # no credit-sensitive instruments, no spreads
    "CSR_SEC_CTP": False,
    "CSR_SEC_NON_CTP": False,
    "EQUITY": False,
    "COMMODITY": False,
    "FX": False,
    "DEFAULT_RISK_CHARGE": False,
    "RESIDUAL_RISK_ADD_ON": False,
}

UNSUPPORTED_REASON = (
    "This system holds US Treasury fixed-rate bonds and a Treasury par yield "
    "curve. The risk classes marked unsupported need instruments and market "
    "data it does not have - credit spreads, equity prices, FX rates, "
    "commodity curves, implied volatility surfaces, issuer default data. A "
    "capital figure that silently omits a risk class the bank actually runs is "
    "not conservative, it is understated, so those classes return "
    "UNSUPPORTED_REGULATORY_SCOPE rather than zero."
)
