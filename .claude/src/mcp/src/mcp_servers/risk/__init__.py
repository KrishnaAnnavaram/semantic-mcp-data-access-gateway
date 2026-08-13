"""risk-engine-mcp — deterministic market-risk mathematics.

No database. No LLM. No network. Given the same typed inputs and the same model
manifest, this package returns the same numbers, and says so with a fingerprint.

The one thing to understand before reading further
--------------------------------------------------
**Treasury publishes a PAR yield curve, not zero-coupon rates.** A 10-year CMT
of 4.25% does not mean a ten-year cash flow discounts at 1/1.0425^10. The par
yield is the coupon a bond would need to trade at 100; the discount factors
implied by a whole par curve are something you have to solve for.

Treating par yields as spot rates is the single most common way to get bond
analytics wrong, and it fails quietly - the prices look plausible, the DV01 has
the right sign, and everything is off by an amount that grows with maturity and
curve slope. So curve construction is a mandatory, named, versioned step here:
`par_bootstrap_logdf_interp_v1`.

What the numbers are, and are not
---------------------------------
Values produced here are **model-implied from the published Treasury par
curve**. Treasury's own inputs are indicative bid-side quotations, not
transactions, and Treasury does not publish its full curve formulation. These
are not executable prices and should never be described as such.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
