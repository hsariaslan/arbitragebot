import os
import unittest
from collections import defaultdict, deque

os.environ.setdefault("DASHBOARD_PASSWORD", "test")

from optimizer import SymbolOptimizer, SymbolScore, SymbolTick


class OptimizerSamplingTests(unittest.TestCase):
    def _optimizer_stub(self, scoring_window: int = 1800) -> SymbolOptimizer:
        opt = object.__new__(SymbolOptimizer)
        opt._scoring_window = scoring_window
        opt._trade_amount = 100.0
        opt._ticks = {"ARBUSDT": deque()}
        opt._agg_total = defaultdict(int)
        opt._agg_sum_net = defaultdict(float)
        opt._agg_prof_count = defaultdict(int)
        opt._agg_prof_sum = defaultdict(float)
        opt._agg_prof_profit_sum = defaultdict(float)
        opt._best_net_dq = defaultdict(deque)
        opt._historical_stats = {}
        opt._historical_exchange_stats = {}
        return opt

    def test_samples_scale_with_scoring_window(self) -> None:
        opt = self._optimizer_stub(scoring_window=1800)

        self.assertEqual(opt._score_sample_interval_seconds(), 3.0)
        self.assertEqual(opt._samples_for_seconds(15), 5)
        self.assertEqual(opt._samples_per_hour(), 1200.0)

    def test_append_is_rate_limited_and_aggregates_use_retained_samples(self) -> None:
        opt = self._optimizer_stub(scoring_window=1800)

        first = SymbolTick(0.0, 0.10, "Binance", "OKX", 0.2, 0.1, 100.0)
        skipped = SymbolTick(1.0, 0.20, "Binance", "OKX", 0.3, 0.1, 100.0)
        second = SymbolTick(3.0, 0.30, "Binance", "OKX", 0.4, 0.1, 100.0)

        self.assertTrue(opt._append_score_tick("ARBUSDT", first))
        self.assertFalse(opt._append_score_tick("ARBUSDT", skipped))
        self.assertTrue(opt._append_score_tick("ARBUSDT", second))

        self.assertEqual(len(opt._ticks["ARBUSDT"]), 2)
        self.assertEqual(opt._agg_total["ARBUSDT"], 2)
        self.assertAlmostEqual(opt._agg_prof_sum["ARBUSDT"], 0.40)
        self.assertAlmostEqual(opt._best_net_dq["ARBUSDT"][0][1], 0.30)

    def test_eviction_does_not_subtract_default_trade_amount_for_zero_size_sample(self) -> None:
        opt = self._optimizer_stub(scoring_window=1)
        tick = SymbolTick(0.0, 0.25, "Binance", "OKX", 0.3, 0.05, 0.0)

        self.assertTrue(opt._append_score_tick("ARBUSDT", tick))
        self.assertEqual(opt._agg_prof_profit_sum["ARBUSDT"], 0.0)

        opt._prune_score_window("ARBUSDT", cutoff=2.0)

        self.assertEqual(len(opt._ticks["ARBUSDT"]), 0)
        self.assertEqual(opt._agg_total["ARBUSDT"], 0)
        self.assertEqual(opt._agg_prof_profit_sum["ARBUSDT"], 0.0)

    def test_execution_floor_blocks_candidates_below_monitor_min_net(self) -> None:
        class MonitorStub:
            def _effective_min_net_profit_pct(self) -> float:
                return 0.065

        opt = object.__new__(SymbolOptimizer)
        opt._monitor = MonitorStub()

        below_avg = SymbolScore(
            symbol="ZECUSDT",
            score=0.05,
            avg_net_pct=0.04,
            avg_profitable_net=0.059,
            profitable_ticks=10,
            total_ticks=10,
            frequency=1.0,
            best_net_pct=0.08,
            est_hourly_profit=1.0,
        )
        below_best = SymbolScore(
            symbol="ZECUSDT",
            score=0.05,
            avg_net_pct=0.04,
            avg_profitable_net=0.07,
            profitable_ticks=10,
            total_ticks=10,
            frequency=1.0,
            best_net_pct=0.064,
            est_hourly_profit=1.0,
        )
        tradable = SymbolScore(
            symbol="ZECUSDT",
            score=0.05,
            avg_net_pct=0.04,
            avg_profitable_net=0.07,
            profitable_ticks=10,
            total_ticks=10,
            frequency=1.0,
            best_net_pct=0.08,
            est_hourly_profit=1.0,
        )

        self.assertFalse(opt._passes_execution_net_floor(below_avg)[0])
        self.assertFalse(opt._passes_execution_net_floor(below_best)[0])
        self.assertTrue(opt._passes_execution_net_floor(tradable)[0])


if __name__ == "__main__":
    unittest.main()
