"""Risk-data layer — interface + mock stub (Phase 4 seam).

The smart agent decides *what* data it needs and calls this provider to get it.
Today the concrete implementation is MockDataProvider, which returns hardcoded
sample risk data. Tomorrow we swap in an MCP-backed provider that reads the real
PostgreSQL/SQLite tables (assets, historical_prices, portfolio_positions,
counterparty_exposure) — the agent code does not change, because it only ever
talks to the DataProvider interface.
"""

from __future__ import annotations

import math
from typing import Protocol


class DataProvider(Protocol):
    def get_assets(self) -> list[dict]: ...
    def get_historical_prices(self, asset_id: str, days: int = 250) -> list[dict]: ...
    def get_portfolio_positions(self) -> list[dict]: ...
    def get_counterparty_exposure(self, counterparty: str | None = None) -> list[dict]: ...


class MockDataProvider:
    """Hardcoded sample risk data. Replace with an MCP/DB-backed provider later."""

    _ASSETS = [
        {"asset_id": "AAPL", "name": "Apple Inc.", "asset_class": "equity", "currency": "USD"},
        {"asset_id": "GOVT10Y", "name": "US 10Y Treasury", "asset_class": "rates", "currency": "USD"},
        {"asset_id": "EURUSD", "name": "EUR/USD FX", "asset_class": "fx", "currency": "USD"},
    ]

    _POSITIONS = [
        {"asset_id": "AAPL", "quantity": 10_000, "market_value": 1_900_000.0},
        {"asset_id": "GOVT10Y", "quantity": 5_000, "market_value": 4_850_000.0},
        {"asset_id": "EURUSD", "quantity": 2_000_000, "market_value": 2_160_000.0},
    ]

    _COUNTERPARTIES = [
        {
            "counterparty": "ACME_BANK",
            "rating": "BBB",
            "expected_exposure": 3_200_000.0,
            "expected_positive_exposure": 1_800_000.0,
            "credit_spread_bps": 180,
            "recovery_rate": 0.40,
        },
        {
            "counterparty": "GLOBEX",
            "rating": "BB",
            "expected_exposure": 1_100_000.0,
            "expected_positive_exposure": 700_000.0,
            "credit_spread_bps": 420,
            "recovery_rate": 0.35,
        },
    ]

    def get_assets(self) -> list[dict]:
        return list(self._ASSETS)

    def get_historical_prices(self, asset_id: str, days: int = 250) -> list[dict]:
        """Deterministic synthetic price series so demos are reproducible."""
        base = {"AAPL": 190.0, "GOVT10Y": 97.0, "EURUSD": 1.08}.get(asset_id, 100.0)
        vol = {"AAPL": 0.018, "GOVT10Y": 0.004, "EURUSD": 0.006}.get(asset_id, 0.01)
        prices = []
        price = base
        for t in range(days):
            # smooth pseudo-random walk (seeded by asset+t, no external deps)
            shock = math.sin(t * 1.7 + hash(asset_id) % 7) * vol
            price = round(price * (1 + shock), 4)
            prices.append({"day": t, "price": price})
        return prices

    def get_portfolio_positions(self) -> list[dict]:
        return list(self._POSITIONS)

    def get_counterparty_exposure(self, counterparty: str | None = None) -> list[dict]:
        if counterparty is None:
            return list(self._COUNTERPARTIES)
        cp = counterparty.strip().upper()
        return [c for c in self._COUNTERPARTIES if c["counterparty"] == cp]
