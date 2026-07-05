import os
import unittest

os.environ.setdefault("DASHBOARD_PASSWORD", "test")

from hedge_manager import HedgeManager
from monitor import ArbitrageMonitor


class RebalanceAndHedgeGuardTests(unittest.TestCase):
    def test_clear_rebalance_streak_removes_backoff_too(self) -> None:
        monitor = object.__new__(ArbitrageMonitor)
        monitor._miss_streak = {"ARBUSDT:Binance:OKX": 12}
        monitor._rebalance_empty_backoff = {"ARBUSDT:Binance:OKX": (123.0, 60.0)}

        monitor._clear_rebalance_streak("ARBUSDT:Binance:OKX")

        self.assertNotIn("ARBUSDT:Binance:OKX", monitor._miss_streak)
        self.assertNotIn("ARBUSDT:Binance:OKX", monitor._rebalance_empty_backoff)

    def test_hedge_adjustment_floor_suppresses_dust_delta(self) -> None:
        manager = object.__new__(HedgeManager)
        manager._adjust_threshold_pct = 0.01
        manager._dust_threshold_usd = 20.0
        manager._total_capital = 1000.0

        should_adjust, reason = manager._should_adjust_hedge(
            current_qty=100.0,
            target_qty=101.5,
            price=1.0,
        )

        self.assertFalse(should_adjust)
        self.assertIn("delta_dust", reason)

    def test_hedge_adjustment_floor_allows_meaningful_delta(self) -> None:
        manager = object.__new__(HedgeManager)
        manager._adjust_threshold_pct = 0.01
        manager._dust_threshold_usd = 20.0
        manager._total_capital = 1000.0

        should_adjust, reason = manager._should_adjust_hedge(
            current_qty=100.0,
            target_qty=130.0,
            price=1.0,
        )

        self.assertTrue(should_adjust)
        self.assertEqual(reason, "ok")

    def test_bnb_topup_skip_log_is_throttled(self) -> None:
        manager = object.__new__(HedgeManager)
        manager._last_bnb_topup_skip_log_ts = 0.0
        manager._last_bnb_topup_skip_signature = ""

        with self.assertLogs("hedge_manager", level="INFO") as first:
            manager._log_bnb_topup_skip(
                1000.0,
                futures_value=0.0,
                target_usd=10.0,
                spot_value=5.0,
                spot_floor_usd=5.0,
                transfer_min_usd=5.0,
                transferable_usd=0.0,
            )

        with self.assertLogs("hedge_manager", level="DEBUG") as second:
            manager._log_bnb_topup_skip(
                1010.0,
                futures_value=0.0,
                target_usd=10.0,
                spot_value=5.0,
                spot_floor_usd=5.0,
                transfer_min_usd=5.0,
                transferable_usd=0.0,
            )

        self.assertIn("FUTURES_BNB_TOPUP_SKIPPED", first.output[0])
        self.assertIn("throttled", second.output[0])

    def test_futures_bnb_discount_skip_log_is_throttled(self) -> None:
        manager = object.__new__(HedgeManager)
        manager._bnb_fee_reserve_status = {"futures_value_usd": 0.0}
        manager._last_futures_bnb_discount_skip_log_ts = 0.0
        manager._last_futures_bnb_discount_skip_signature = ""

        with self.assertLogs("hedge_manager", level="INFO") as first:
            manager._log_futures_bnb_discount_skip(1000.0, "ADAUSDT", 0.0123)

        with self.assertLogs("hedge_manager", level="DEBUG") as second:
            manager._log_futures_bnb_discount_skip(1010.0, "ADAUSDT", 0.0123)

        self.assertIn("Futures BNB fee discount skipped", first.output[0])
        self.assertIn("reserve=$0.00", second.output[0])


if __name__ == "__main__":
    unittest.main()
