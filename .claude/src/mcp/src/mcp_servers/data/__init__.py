"""market-risk-data-mcp — semantic, read-only access to trusted market-risk facts.

This server owns one job: turning a bounded business request into trusted data.
It does not reason, and it does not calculate.

What it must never contain
--------------------------
* An LLM. Reasoning lives in the host; an LLM here would smuggle it back across
  the boundary and make the server's output non-deterministic.
* A `run_sql` tool, or any parameter carrying a table, column, ordering or SQL
  fragment. SQL templates live in `repository.py`; caller input supplies values
  only. Exposing SQL would move schema knowledge into the model's prompt and
  make row/column control impossible - the opposite of a semantic gateway.
* Any risk arithmetic: no VaR, DV01, pricing, spreads, slopes or curve
  interpolation across maturity. Interpolating *between tenors* is a documented
  modelling step and belongs to the risk engine. Interpolating *across dates* is
  never acceptable anywhere, because it invents market data.

What every response carries
---------------------------
`rate_kind`, `quote_basis`, `unit` and `data_classification` on every rate, plus
source provenance. A bare number is not an answer: 4.26 is meaningless until you
know it is a nominal par yield in percent rather than a bank-discount rate.

Database identity
-----------------
Connects as `mcp_reader`, which holds SELECT on `analytics` and `demo` only and
cannot reach `treasury.*` at all. That privilege boundary - not the tool
annotations - is what actually constrains this server.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
