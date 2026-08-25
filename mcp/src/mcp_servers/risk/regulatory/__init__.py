"""Regulatory capital calculations, and the constants supervisors prescribe.

Kept apart from the rest of the engine because the numbers here are not
modelling choices. They come from a standard, they change when the standard
changes, and they must be diffable against it - which they are not if they are
spelled inline at the point of use.

Only what the data genuinely supports is implemented. See
`constants.RISK_CLASS_SUPPORT` for the complete list of what is and is not, and
`docs/capability-gaps.md` for what each absent risk class would require.
"""

from .constants import FRTB_CONSTANTS_VERSION, FRTB_SOURCE, RISK_CLASS_SUPPORT
from .girr import GirrCapital, compute_girr_capital, girr_correlation

__all__ = [
    "FRTB_CONSTANTS_VERSION", "FRTB_SOURCE", "RISK_CLASS_SUPPORT",
    "GirrCapital", "compute_girr_capital", "girr_correlation",
]
