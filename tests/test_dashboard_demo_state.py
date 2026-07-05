import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("DASHBOARD_PASSWORD_HASH", "test-hash")

from dashboard_server import DashboardServer


class DummyBalance:
    def __init__(self, total: float) -> None:
        self._exchanges = ["Binance"]
        self._symbols = ["ABCUSDT"]
        self.crypto = {"Binance": {"ABCUSDT": 1.0}}
        self.usdt = {"Binance": 10.0}
        self.initialized = True
        self._initial_investment = total
        self._total = total

    def get_portfolio_value(self, prices: dict[str, float]) -> float:
        return self._total


class DummyFetcher:
    latest_balances = {}
    baselines = {}
    recent_discrepancies = []
    total_discrepancy_count = 0
    last_fetch_time = 0.0
    _configured = {"Binance": True}

    def get_total_delta(self, prices: dict[str, float]) -> float:
        return 0.0


class DashboardDemoStateTests(unittest.TestCase):
    def test_demo_state_uses_super_primary_bundle_not_selected_monitor(self) -> None:
        server = DashboardServer.__new__(DashboardServer)
        server._demo_fetcher = DummyFetcher()
        server._settings = {"execution_mode": "simulation"}
        server._monitor = SimpleNamespace(_execution_mode="simulation")
        server._balance = DummyBalance(111.0)
        server._registry = SimpleNamespace(super_primary_id="sp")

        super_primary_bundle = SimpleNamespace(
            config_id="sp",
            execution_mode="demo",
            demo_executor=object(),
            monitor=SimpleNamespace(_execution_mode="demo"),
            balance=DummyBalance(222.0),
            fee_manager=object(),
        )
        server._orchestrator = SimpleNamespace(
            get_bundle=lambda cid: super_primary_bundle if cid == "sp" else None
        )
        server._get_prices = lambda exchanges, symbols: {sym: 1.0 for sym in symbols}

        state = DashboardServer._build_demo_state(server)

        self.assertTrue(state["enabled"])
        self.assertEqual(state["demo_portfolio_total"], 222.0)


if __name__ == "__main__":
    unittest.main()
