"""
Cross-exchange arbitrage monitor with trade simulation.

Reads live price state from all registered fetchers, compares prices
across exchanges, simulates trades when profitable after fees, and
tracks cumulative P&L. Prints a comprehensive discovery report on shutdown.
"""

import asyncio
import logging
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=3))  # UTC+3
from typing import TYPE_CHECKING

from balance import BalanceTracker
from slippage import compute_buy_slippage, compute_sell_slippage
from config import (
    ACTIVE_EXCHANGES,
    ACTIVE_SYMBOLS,
    MAX_DATA_AGE_SECONDS,
    MONITOR_INTERVAL_SECONDS,
    TRADE_AMOUNT_USD,
)

logger = logging.getLogger(__name__)


def _safe_task(coro, name: str = "task") -> asyncio.Task:
    """Create an asyncio task that logs exceptions instead of silently swallowing them."""
    task = asyncio.create_task(coro)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logger.error(f"[Monitor] Async {name} failed: {exc!r}", exc_info=exc)

    task.add_done_callback(_on_done)
    return task


if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager
    from executor import DemoExecutor
    from fee_manager import FeeManager
    from fetchers.base import BaseFetcher
    from hedge_manager import HedgeManager
    from optimizer import SymbolOptimizer
    from state_manager import StateManager



@dataclass
class ConfigSnapshot:
    """Record of configuration state at a point in time."""

    timestamp: float
    reason: str  # "initial", "settings_applied", "adaptive_update"
    trade_amount: float
    adaptive_mode: bool
    min_net_profit_pct: float
    rebalance_cooldown: float
    rebalance_roi_horizon: int
    total_capital: float
    num_active_symbols: int
    max_active_symbols: int
    avg_trade_size: float
    estimated_profit_per_trade: float
    min_misses_before_rebalance: int = 15


@dataclass
class SimulatedTrade:
    """Record of a single simulated trade."""

    timestamp: float
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float
    fee_pct: float
    net_pct: float
    profit_usd: float
    trade_amount: float = 0.0
    # Rounding metadata (D-01: lot size rounding)
    buy_qty_raw: float = 0.0
    buy_qty_rounded: float = 0.0
    sell_qty_raw: float = 0.0
    sell_qty_rounded: float = 0.0
    rounding_impact_usd: float = 0.0
    # Data freshness metadata (D-07: stale price detection)
    data_age_ms: float = 0.0
    # Simulated slippage (from order book depth)
    sim_slippage_pct: float = 0.0
    sim_buy_slippage_pct: float = 0.0
    sim_sell_slippage_pct: float = 0.0
    # Demo execution results (Phase 2: populated when execution_mode=demo)
    demo_buy_price: float = 0.0
    demo_sell_price: float = 0.0
    demo_buy_qty: float = 0.0
    demo_sell_qty: float = 0.0
    demo_profit_usd: float = 0.0
    demo_latency_ms: float = 0.0
    demo_slippage_pct: float = 0.0
    demo_status: str = ""  # "filled", "partial", "rejected", "one_legged"
    # Simulation realism: one-legged failure simulation
    one_leg_simulated: bool = False


class ArbitrageMonitor:
    """
    Centralized cross-exchange price comparison and trade simulator.

    Every second:
    1. Scans all fetcher states for cross-exchange spread opportunities
    2. If spread > total fees, simulates a $10 trade and records profit
    3. Prints a live table sorted by net profit (after fees)

    On shutdown: prints a comprehensive discovery report.
    """

    def __init__(
        self,
        fetchers: list["BaseFetcher"],
        balance: BalanceTracker | None = None,
        symbols: list[str] | None = None,
        exchanges: list[str] | None = None,
        trade_amount: float | None = None,
        min_net_profit_pct: float = 0.02,
        rebalance_roi_horizon: int = 1800,
        total_capital: float = 1800.0,
        adaptive_mode: bool = True,
        log_file: "Path | None" = None,
        exchange_info: "ExchangeInfoManager | None" = None,
        fee_manager: "FeeManager | None" = None,
        min_misses_before_rebalance: int = 15,
        net_pct_sizing_enabled: bool = True,
        net_pct_multiplier_cap: float = 2.5,
    ) -> None:
        self._fetchers = fetchers
        self._balance = balance
        self._log_file = log_file
        self._exchange_info = exchange_info
        self._fee_manager = fee_manager
        self._running: bool = False
        self._paused: bool = False
        self._symbols: list[str] = symbols or ACTIVE_SYMBOLS
        self._trade_amount: float = trade_amount or TRADE_AMOUNT_USD
        self._active_exchanges: set[str] = set(exchanges or ACTIVE_EXCHANGES)
        self._min_net_profit_pct: float = min_net_profit_pct
        self._rebalance_roi_horizon: int = rebalance_roi_horizon
        self._total_capital: float = total_capital
        self._adaptive_mode: bool = adaptive_mode
        self._net_pct_sizing_enabled: bool = net_pct_sizing_enabled
        self._net_pct_multiplier_cap: float = net_pct_multiplier_cap

        # Quiet-period pause: when no trade has fired for N minutes, the
        # bot's replenish/overflow/reallocation logic still runs, paying
        # transfer fees that aren't matched by trade revenue. This setting
        # gates those costs: 0 = disabled (current behavior), > 0 = pause
        # all rebalance-class transfers after that many minutes without
        # a trade. Auto-resumes the moment a trade fires. Per-config so
        # aggressive configs (low quiet_period_minutes) keep trying while
        # conservative configs (high) stop wasting on dead windows.
        self._quiet_period_pause_minutes: float = 0.0  # 0 = disabled
        self._last_trade_ts: float = 0.0  # set on every successful trade

        # Time-based regime gating (v0.31). Each UTC hour 0-23 maps to one
        # of three regimes: STRONG, NEUTRAL, or WEAK (any hour not in
        # strong or neutral defaults to weak).
        # - STRONG / NEUTRAL: full activity, base thresholds
        # - WEAK: tightened — `min_net_profit_pct *= weak_min_net_multiplier`
        #   plus optional gates blocking rebalances/demotions/expansions.
        # Operator-configurable per config so different configs can have
        # different active windows (e.g., aggressive configs trade more
        # hours, conservative configs idle through thin windows).
        # Default off (regime_gating_enabled=False) — backward-compatible.
        # When off, behavior matches the pre-regime path exactly.
        self._regime_gating_enabled: bool = False
        self._regime_strong_hours: set[int] = {7, 15, 20, 21, 22}
        self._regime_neutral_hours: set[int] = {0, 1, 5, 6, 8, 9, 11}
        self._regime_weak_min_net_multiplier: float = 2.0
        self._regime_weak_disable_rebalance: bool = True
        self._regime_last_logged_regime: str = ""  # track transitions for logging

        self._optimizer: "SymbolOptimizer | None" = None
        # Bounded deque (maxlen=5000) — pre-fix this was an unbounded list
        # despite CLAUDE.md claiming the cap. At 48 configs the per-tick
        # `sum(t.profit_usd for t in self._trades)` in get_net_profit_stats()
        # AND in _should_rebalance() became the dominant slow-growth source
        # after the optimizer aggregates fix. Now bounded; we ALSO track
        # `_cumulative_pnl` incrementally so totals don't reset when older
        # trades evict from the deque.
        self._trades: deque[SimulatedTrade] = deque(maxlen=5000)
        self._cumulative_pnl: float = 0.0
        self._cumulative_trade_count: int = 0
        self._low_profit_skips: int = 0
        self._start_time: float = 0.0
        self._tick_count: int = 0

        # Net P&L gate configurable params
        self._net_pnl_gate_warmup_trades: int = 10
        self._net_pnl_gate_grace_seconds: int = 1800
        self._rebalance_roi_divisor: int = 3

        # Configuration history tracking — bounded deque(maxlen=500).
        # `record_config_snapshot("adaptive_update")` fires every 300
        # ticks (5 min) regardless of trade activity, so this grows
        # over time even when nothing else does. 500 entries = ~41
        # hours of snapshots, more than the broadcast's UI needs.
        self._config_history: deque[ConfigSnapshot] = deque(maxlen=500)

        # Hourly/daily P&L tracking (persisted across restarts)
        # Key: "YYYY-MM-DD_HH" -> {"pnl": float, "trades": int}
        self._hourly_pnl: dict[str, dict] = {}
        # Key: "YYYY-MM-DD" -> {"pnl": float, "trades": int}
        self._daily_pnl: dict[str, dict] = {}

        # Consecutive miss tracking: only rebalance after N consecutive
        # profitable ticks that couldn't execute due to insufficient balance.
        # Key: "sym:buy_ex:sell_ex" → consecutive miss count
        self._miss_streak: dict[str, int] = {}
        self._min_misses_before_rebalance: int = min_misses_before_rebalance
        # Backoff after try_rebalance returns empty (no viable transfers).
        # Key: miss_key → (next_retry_time, current_backoff_seconds)
        self._rebalance_empty_backoff: dict[str, tuple[float, float]] = {}

        # Data freshness tracking
        self._stale_skips: dict[str, int] = defaultdict(int)
        self._fresh_samples: dict[str, int] = defaultdict(int)
        self._exchange_age_sum: dict[str, float] = defaultdict(float)
        self._exchange_age_max: dict[str, float] = defaultdict(float)
        self._exchange_age_count: dict[str, int] = defaultdict(int)

        # Depth filtering tracking
        self._depth_skips: int = 0

        # Min notional / min qty rejection tracking (D-02)
        self._notional_skips: int = 0
        self._interval_notional_skips: int = 0

        # Throttle counters for diagnostic logging
        self._size_zero_log_count: dict[str, int] = defaultdict(int)
        self._rebalance_block_log_count: dict[str, int] = defaultdict(int)

        # Post-discovery periodic summary counters (reset every summary)
        self._summary_interval: int = 30  # Log summary every N ticks
        self._interval_profitable: int = 0  # Profitable spreads seen
        self._interval_size_skips: int = 0  # Skipped: trade_size = 0
        self._interval_balance_skips: int = 0  # Skipped: insufficient balance
        self._interval_executed: int = 0  # Trades executed

        # Per-exchange internal spread tracking (bid-ask on same exchange)
        self._exchange_spread_sum: dict[str, float] = defaultdict(float)
        self._exchange_spread_max: dict[str, float] = defaultdict(float)
        self._exchange_spread_count: dict[str, int] = defaultdict(int)

        # Simulation realism features
        self._spread_persistence_ticks: int = 1
        self._pending_opportunities: dict[str, dict] = {}
        self._phantom_spread_count: int = 0
        self._event_driven_seller_penalty: float = 0.05
        self._event_driven_seller_penalties: int = 0
        self._event_driven_seller_demoted: int = 0
        self._evd_demoted_last_log: dict[str, float] = {}  # symbol -> last log timestamp
        self._event_driven_exchanges: set[str] = {
            f.exchange_name for f in fetchers if f.IS_EVENT_DRIVEN
        }
        self._one_leg_failure_rate: float = 0.02
        self._one_leg_unwind_slippage_mult: float = 1.5
        self._one_leg_sim_count: int = 0
        self._one_leg_sim_cost: float = 0.0
        self._max_position_multiplier: float = 5.0
        self._position_cap_skips: int = 0

        # Anomaly protection
        from anomaly_protection import AnomalyProtection

        self._anomaly = AnomalyProtection()
        self._anomaly_paused: bool = False
        self._manual_stopped: bool = False
        self._manual_stop_timestamp: float = 0.0

        # Phase 2: Demo execution
        self._executor: "DemoExecutor | None" = None
        self._execution_mode: str = "simulation"
        self._state_mgr: "StateManager | None" = None
        self._demo_fetcher = None  # set via set_executor()

        # Demo setup (initial position establishment)
        self._demo_setup_complete: bool = False
        self._demo_setup_running: bool = False
        self._crypto_init_time: float = 0.0
        # Throttle "no demo position" logs (first per key, then silent)
        self._demo_sell_skip_log: dict[str, int] = {}
        # Throttle D-10 rejection logs (first per exchange:symbol, then silent)
        self._demo_reject_log: dict[str, int] = {}
        # Permanently skip demo orders for exchange:symbol:side combos that
        # fail with "instrument not found" type errors (symbol doesn't exist
        # on that exchange's demo/testnet environment)
        self._demo_skip_pairs: set[str] = set()
        self._demo_skip_count: int = 0  # total skipped demo trades due to skip pairs

        # Demo accuracy stats (for [Session] summary)
        self._demo_trade_count: int = 0
        self._demo_fill_count: int = 0
        self._demo_reject_count: int = 0
        self._demo_partial_count: int = 0
        self._demo_one_legged_count: int = 0
        self._demo_total_sim_profit: float = 0.0
        self._demo_total_actual_profit: float = 0.0
        self._demo_total_sim_slippage: float = 0.0
        self._demo_total_actual_slippage: float = 0.0
        self._demo_total_latency_ms: float = 0.0
        self._demo_fee_mismatches: int = 0

        # Hedge manager (Phase C — set externally via set_hedge_manager).
        # Evaluated periodically from the main loop. Shadow mode in C, live in D.
        self._hedge_manager: "HedgeManager | None" = None
        # Tracks whether any hedge was open last tick. When this transitions
        # 0→N or N→0, the anomaly tracker's peak basis changes (spot-only ↔
        # spot+hedge_pnl) and we reset peak so drawdown is apples-to-apples.
        self._prev_hedge_count: int = 0

    def set_optimizer(self, optimizer: "SymbolOptimizer") -> None:
        """Store optimizer reference for score-based rebalance gating."""
        self._optimizer = optimizer

    def set_hedge_manager(self, hedge_manager: "HedgeManager") -> None:
        """Store hedge manager reference for periodic evaluation."""
        self._hedge_manager = hedge_manager

    def set_executor(
        self,
        executor: "DemoExecutor",
        state_mgr: "StateManager",
        demo_fetcher=None,
        execution_mode: str = "demo",
    ) -> None:
        """Enable demo execution mode with the given executor."""
        self._executor = executor
        self._execution_mode = execution_mode
        self._state_mgr = state_mgr
        self._demo_fetcher = demo_fetcher
        logger.info(
            f"[Monitor] Demo execution enabled for: "
            f"{executor.supported_exchanges}"
        )

    def _record_trade_pnl(self, timestamp: float, profit_usd: float) -> None:
        """Record trade profit in hourly and daily P&L buckets."""
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        hour_key = dt.strftime("%Y-%m-%d_%H")
        day_key = dt.strftime("%Y-%m-%d")

        if hour_key not in self._hourly_pnl:
            self._hourly_pnl[hour_key] = {"pnl": 0.0, "trades": 0}
        self._hourly_pnl[hour_key]["pnl"] += profit_usd
        self._hourly_pnl[hour_key]["trades"] += 1

        if day_key not in self._daily_pnl:
            self._daily_pnl[day_key] = {"pnl": 0.0, "trades": 0}
        self._daily_pnl[day_key]["pnl"] += profit_usd
        self._daily_pnl[day_key]["trades"] += 1

    def _output(self, text: str) -> None:
        """Print to console and append to log file.

        v0.31.0-beta+: when `_log_file` isn't configured (the multi-config
        default — orchestrator passes `log_file=None`), skip both the
        print() and the file write. The dashboard is the primary view,
        and stdout flooding at 48 configs × per-tick prints was both
        making the terminal unreadable and adding I/O contention. The
        per-config `[Session]` and `[Balance] Snapshot` log lines via
        the standard logger already capture equivalent info.
        """
        if not self._log_file:
            return
        print(text)
        with open(self._log_file, "a") as f:
            f.write(text + "\n")

    def _emergency_sell_all(self) -> None:
        """Emergency: sell all crypto positions to USDT."""
        if not self._balance:
            return
        prices = self._get_current_prices()
        total_sold = 0.0
        positions_sold = 0
        liquidated: list[dict] = []
        for ex in list(self._balance._exchanges):
            for sym in list(self._balance.crypto.get(ex, {}).keys()):
                qty = self._balance.crypto[ex].get(sym, 0.0)
                if qty <= 0:
                    continue
                price = prices.get(sym, 0.0)
                if price <= 0:
                    continue
                fee_rate = (
                    self._fee_manager.get_taker_fee(ex, sym)
                    if self._fee_manager else 0.001
                )
                gross = qty * price
                net = gross * (1 - fee_rate)
                self._balance.usdt[ex] += net
                self._balance.crypto[ex][sym] = 0.0
                total_sold += gross
                positions_sold += 1
                liquidated.append({
                    "exchange": ex, "symbol": sym, "qty": qty,
                    "price": price, "gross": gross, "net": net,
                    "fee_pct": fee_rate * 100,
                })
                logger.warning(
                    f"[Anomaly] EMERGENCY_SELL {sym} on {ex}: "
                    f"qty={qty:.6f} price=${price:.4f} gross=${gross:.2f} "
                    f"fee={fee_rate * 100:.3f}% net=${net:.2f}"
                )
        logger.warning(
            f"[Anomaly] EMERGENCY_SELL_COMPLETE: {positions_sold} positions sold, "
            f"total=${total_sold:.2f}"
        )

        # Emergency consolidation: move all USDT to the custody hub (Bybit by
        # default) for safety. Cheapest withdrawal route per exchange (function
        # sorts by fee).
        consolidation_transfers = self._balance.emergency_consolidate_to_custody_hub()
        consolidation_summary = {
            "transfers": [
                {
                    "from_exchange": t.from_exchange,
                    "amount_usd": t.amount_usd,
                    "fee_usd": t.fee_usd,
                }
                for t in consolidation_transfers
            ],
            "total_moved": sum(t.amount_usd for t in consolidation_transfers),
            "total_fees": sum(t.fee_usd for t in consolidation_transfers),
        }
        if consolidation_transfers:
            logger.warning(
                f"[Anomaly] EMERGENCY_CONSOLIDATE_COMPLETE: "
                f"{len(consolidation_transfers)} transfers, "
                f"${consolidation_summary['total_moved']:.2f} moved to Bitfinex, "
                f"${consolidation_summary['total_fees']:.4f} fees"
            )

        # Phase E: close all open futures hedges. Async because the executor
        # makes REST calls. Wrapped together with the email so the email can
        # include the hedge-close summary.
        usdt_breakdown = {
            ex: self._balance.usdt.get(ex, 0.0)
            for ex in self._balance._exchanges
            if self._balance.usdt.get(ex, 0.0) > 0
        }
        _safe_task(
            self._emergency_close_hedges_and_notify(
                positions_sold=positions_sold,
                total_sold=total_sold,
                liquidated=liquidated,
                usdt_breakdown=usdt_breakdown,
                consolidation_summary=consolidation_summary,
            ),
            name="emergency_email",
        )
        self._anomaly.mark_emergency_email_sent(time.time())

    async def _emergency_close_hedges_and_notify(
        self,
        positions_sold: int,
        total_sold: float,
        liquidated: list,
        usdt_breakdown: dict,
        consolidation_summary: dict,
    ) -> None:
        """Phase E: emergency tail — close all hedges then send email.

        Closing happens BEFORE the email so the email reflects post-close
        state and includes the hedge close summary (per-symbol funding P&L).
        """
        from email_notifier import notify_emergency

        hedge_summary = None
        if self._hedge_manager is not None:
            try:
                hedge_summary = await self._hedge_manager.close_all_for_emergency(
                    reason=self._anomaly._pause_reason or "emergency"
                )
            except Exception as e:
                logger.error(f"[Hedge] close_all_for_emergency failed: {e}")
                hedge_summary = {"error": str(e), "closed": [], "failed": [],
                                 "total_funding_pnl_usd": 0.0, "n_closed": 0, "n_failed": 0}

        await notify_emergency(
            reason=self._anomaly._pause_reason,
            drawdown_pct=self._anomaly._current_drawdown_pct,
            peak_value=self._anomaly._peak_portfolio_value,
            current_value=sum(usdt_breakdown.values()),
            positions_sold=positions_sold,
            total_sold=total_sold,
            portfolio_breakdown=usdt_breakdown,
            liquidated_positions=liquidated,
            consolidation_summary=consolidation_summary,
            hedge_summary=hedge_summary,
        )

    def get_net_profit_stats(self) -> dict:
        """Compute rolling hourly net profit stats."""
        now = time.time()
        elapsed_seconds = (now - self._start_time) if self._start_time else 0.0

        # O(1) read from incremental aggregate (was a full scan of an
        # unbounded list — at 48 configs called per-tick from broadcast,
        # this was the largest remaining slow-growth source after the
        # optimizer aggregates + score_samples fixes).
        trading_pnl = self._cumulative_pnl
        transfer_fees = self._balance.total_transfer_fees if self._balance else 0.0
        credited_cashback = (
            self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
        )
        pending_cashback = (
            self._fee_manager._total_pending_cashback if self._fee_manager else 0.0
        )
        net_profit = trading_pnl - transfer_fees + credited_cashback

        # Rolling 1-hour window — `self._trades` is now bounded at 5000,
        # so the scan is O(min(5000, N)) instead of O(N) growing forever.
        # The transfers scan was similarly unbounded; we use the running
        # `total_transfer_fees` as an approximation (loses time-window
        # precision but matches the displayed "Net Total" semantics).
        one_hour_ago = now - 3600
        recent_profit = sum(t.profit_usd for t in self._trades if t.timestamp >= one_hour_ago)
        recent_fees = sum(
            tr.fee_usd for tr in (self._balance.transfers if self._balance else [])
            if tr.timestamp >= one_hour_ago
        )

        hourly_net = recent_profit - recent_fees
        # Suppress only the most extreme early-session noise:
        #   - No trades yet → setup-time transfer fees extrapolate to
        #     misleading rates over near-zero elapsed time.
        #   - Less than 60 seconds elapsed → just give it a minute.
        # Operator wants $/hr visible quickly, so keep the floor short.
        WARMUP_SECONDS = 60.0
        if len(self._trades) == 0 or elapsed_seconds < WARMUP_SECONDS:
            session_hourly_rate = 0.0
        else:
            session_hourly_rate = net_profit / (elapsed_seconds / 3600)

        referrer_earnings = (
            self._fee_manager._total_referrer_earnings
            if self._fee_manager
            else 0.0
        )

        return {
            "net_profit": round(net_profit, 4),
            "hourly_net": round(hourly_net, 4),
            "session_hourly_rate": round(session_hourly_rate, 4),
            "trading_pnl": round(trading_pnl, 4),
            "transfer_fees": round(transfer_fees, 4),
            "credited_cashback": round(credited_cashback, 4),
            "pending_cashback": round(pending_cashback, 4),
            "is_profitable": net_profit > 0,
            "referrer_earnings_total": round(referrer_earnings, 4),
        }

    def in_quiet_period(self) -> bool:
        """True when no trade has fired for `quiet_period_pause_minutes`.

        Used to gate rebalance/reallocation/replenish/overflow logic so
        the bot doesn't pay transfer fees during dead windows that won't
        produce trades. The first trade after a quiet period resets the
        timer immediately. Setting `quiet_period_pause_minutes=0` (default)
        disables the gate entirely.
        """
        if self._quiet_period_pause_minutes <= 0:
            return False
        # No trades yet AND start_time elapsed > pause threshold → quiet
        ref = self._last_trade_ts if self._last_trade_ts > 0 else self._start_time
        if ref <= 0:
            return False
        elapsed = time.time() - ref
        return elapsed > (self._quiet_period_pause_minutes * 60.0)

    def _current_regime(self) -> str:
        """Return 'strong', 'neutral', or 'weak' for the current UTC hour.

        When regime_gating_enabled is False, always returns 'strong' so
        all gates remain open (backward-compatible). Strong and neutral
        behave identically for execution; only WEAK applies restrictions.
        Hours not listed in strong_hours or neutral_hours fall to weak.
        """
        if not self._regime_gating_enabled:
            return "strong"
        h = time.gmtime().tm_hour
        if h in self._regime_strong_hours:
            return "strong"
        if h in self._regime_neutral_hours:
            return "neutral"
        return "weak"

    def _effective_min_net_profit_pct(self) -> float:
        """Apply regime multiplier to the base threshold. Weak hours get
        a higher floor so marginal opportunities are skipped during thin
        market windows."""
        if not self._regime_gating_enabled:
            return self._min_net_profit_pct
        if self._current_regime() == "weak":
            return self._min_net_profit_pct * self._regime_weak_min_net_multiplier
        return self._min_net_profit_pct

    def _should_rebalance(self, buy_ex: str, sell_ex: str) -> tuple[bool, str]:
        """Check if rebalancing is worthwhile based on ROI and net P&L.

        Returns (allowed, reason). reason is non-empty only when blocked.
        """
        if not self._balance or not self._adaptive_mode:
            return True, ""

        # Regime gate: block rebalances during weak hours (saves transfer
        # fees during thin spread windows). The bot can still trade
        # existing positions but won't pay setup costs to chase new ones.
        if (
            self._regime_gating_enabled
            and self._regime_weak_disable_rebalance
            and self._current_regime() == "weak"
        ):
            return False, "regime_weak (no rebalance during thin hours)"

        # Quiet-period gate: when no trade has fired for the configured
        # pause window, suppress rebalance attempts. Transfer fees during
        # quiet windows aren't matched by trade volume — pure cost.
        if self.in_quiet_period():
            return False, (
                f"quiet_period (no trades for "
                f"{self._quiet_period_pause_minutes:.0f}m)"
            )

        # Block when net P&L is negative (after warm-up: trades + grace period)
        warmup_trades = getattr(self, "_net_pnl_gate_warmup_trades", 10)
        grace_seconds = getattr(self, "_net_pnl_gate_grace_seconds", 1800)
        elapsed = time.time() - self._start_time if self._start_time else 0
        if self._cumulative_trade_count >= warmup_trades and elapsed >= grace_seconds:
            trading_pnl = self._cumulative_pnl
            credited_cb = (
                self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
            )
            total_fees = self._balance.total_external_transfer_fees
            if trading_pnl + credited_cb < total_fees:
                return False, (
                    f"net_pnl_gate (pnl=${trading_pnl:.2f} + cb=${credited_cb:.2f} "
                    f"< ext_fees=${total_fees:.2f})"
                )

        # ROI gate: profit margin vs amortized rebalance cost
        # Internal rebalance costs a single taker fee on one exchange;
        # external transfers have flat fees gated separately in try_rebalance().
        # Compare as percentages to avoid trade-amount sensitivity.
        if self._balance._estimated_profit_per_trade > 0 and self._trade_amount > 0:
            profit_pct = self._balance._estimated_profit_per_trade / self._trade_amount
            fee_rate = self._fee_manager.get_taker_fee(buy_ex) if self._fee_manager else 0.001
            threshold = fee_rate / self._rebalance_roi_divisor
            # Rebalance enables ~3 trades; cost amortized = fee_rate / 3
            if profit_pct < threshold:
                return False, (
                    f"roi_gate (profit_pct={profit_pct * 100:.4f}% "
                    f"< threshold={threshold * 100:.4f}%)"
                )

        return True, ""

    def _get_miss_threshold(self, buy_ex: str, sell_ex: str) -> int:
        """Lower miss threshold for exchanges with free/cheap transfers."""
        base = self._min_misses_before_rebalance
        if not self._balance or not self._balance._transfer_fee_mgr:
            return base
        tfm = self._balance._transfer_fee_mgr
        buy_fee = tfm.get_withdrawal_fee(buy_ex)
        sell_fee = tfm.get_withdrawal_fee(sell_ex)
        # Free transfers: trigger after base // 3 (min 3)
        if buy_fee <= 0.01 and sell_fee <= 0.01:
            return max(3, base // 3)
        # Cheap transfers (< $0.20): after base // 2 (min 5)
        if buy_fee < 0.20 or sell_fee < 0.20:
            return max(5, base // 2)
        return base

    def _compute_trade_size(
        self, buy_ex: str, sell_ex: str, symbol: str,
        net_pct: float, sell_price: float,
    ) -> float:
        """Compute optimal trade size based on available balance, symbol score, and spread quality."""
        if not self._balance or not self._balance.initialized:
            return self._trade_amount

        # Per-symbol multiplier from optimizer (better symbols get more capital)
        symbol_mult = 1.0
        if self._optimizer:
            sym_score = self._optimizer.get_symbol_score(symbol)
            if sym_score:
                symbol_mult = sym_score.trade_multiplier

        # Capital-proportional floor (computed first for dynamic buffer)
        min_trade = max(5.0, self._total_capital * 0.003)

        # Max by available USDT on buy exchange (dynamic buffer)
        # Protects Bitfinex reserve from being spent by trades
        usdt_available = self._balance.available_usdt_for_trading(buy_ex)
        usdt_buffer = 0.95 if usdt_available < min_trade * 2 else 0.80
        max_by_usdt = usdt_available * usdt_buffer

        # Max by available crypto value on sell exchange (dynamic buffer)
        crypto_qty = self._balance.crypto.get(sell_ex, {}).get(symbol, 0.0)
        crypto_value = crypto_qty * sell_price
        crypto_buffer = 0.95 if crypto_value < min_trade * 2 else 0.80
        max_by_crypto = crypto_value * crypto_buffer

        # Net%-based trade sizing: scale trade size by current tick profitability
        if self._net_pct_sizing_enabled:
            if net_pct >= 0.25:
                net_mult = 2.5
            elif net_pct >= 0.15:
                net_mult = 2.0
            elif net_pct >= 0.08:
                net_mult = 1.5
            elif net_pct >= 0.03:
                net_mult = 1.0
            else:
                net_mult = 0.5
            net_mult = min(net_mult, self._net_pct_multiplier_cap)
        else:
            net_mult = 1.0

        anomaly_mult = self._anomaly.trade_size_multiplier
        base = self._trade_amount * symbol_mult * net_mult * anomaly_mult
        trade_size = min(max_by_usdt, max_by_crypto, base)

        if trade_size < min_trade:
            self._size_zero_log_count[symbol] += 1
            sz_count = self._size_zero_log_count[symbol]
            if sz_count == 1 or sz_count % 30 == 0:
                if max_by_usdt <= max_by_crypto and max_by_usdt <= base:
                    reason = f"usdt_avail=${usdt_available:.2f} < min=${min_trade:.2f}"
                elif max_by_crypto <= max_by_usdt and max_by_crypto <= base:
                    reason = f"crypto_val=${crypto_value:.2f} < min=${min_trade:.2f}"
                else:
                    reason = f"base=${base:.2f} < min=${min_trade:.2f}"
                logger.info(
                    f"[Monitor] SIZE_ZERO {symbol} {buy_ex}->{sell_ex}: "
                    f"{reason} (usdt=${usdt_available:.2f} crypto=${crypto_value:.2f} "
                    f"base=${base:.2f} #{sz_count})"
                )
            return 0.0

        trade_size = round(trade_size, 2)

        # D-02: Min notional & min qty validation via exchange rules
        if self._exchange_info:
            from decimal import Decimal

            buy_price_d = Decimal(str(sell_price))  # approximate; actual ask is close
            sell_price_d = Decimal(str(sell_price))
            buy_qty_d = Decimal(str(trade_size)) / buy_price_d if sell_price > 0 else Decimal(0)
            sell_qty_d = Decimal(str(trade_size)) / sell_price_d if sell_price > 0 else Decimal(0)

            buy_rules = self._exchange_info.get_rules(buy_ex, symbol)
            sell_rules = self._exchange_info.get_rules(sell_ex, symbol)

            rejected = False
            reason = ""

            # Check min notional on both sides
            if buy_rules and not self._exchange_info.check_min_notional(
                buy_ex, symbol, buy_qty_d, buy_price_d
            ):
                rejected = True
                reason = f"buy min_notional ${float(buy_rules.min_notional):.2f}"
            if sell_rules and not self._exchange_info.check_min_notional(
                sell_ex, symbol, sell_qty_d, sell_price_d
            ):
                rejected = True
                reason = f"sell min_notional ${float(sell_rules.min_notional):.2f}"

            # Check min qty on both sides
            if not rejected and buy_rules and not self._exchange_info.check_min_qty(
                buy_ex, symbol, buy_qty_d
            ):
                rejected = True
                reason = f"buy min_qty {float(buy_rules.min_qty)}"
            if not rejected and sell_rules and not self._exchange_info.check_min_qty(
                sell_ex, symbol, sell_qty_d
            ):
                rejected = True
                reason = f"sell min_qty {float(sell_rules.min_qty)}"

            if rejected:
                self._notional_skips += 1
                self._interval_notional_skips += 1
                if self._notional_skips <= 5 or self._notional_skips % 100 == 0:
                    logger.info(
                        f"[Monitor] REJECT {symbol} {buy_ex}->{sell_ex}: "
                        f"${trade_size:.2f} below {reason} "
                        f"(total_rejects={self._notional_skips})"
                    )
                return 0.0

        return trade_size

    def record_config_snapshot(self, reason: str) -> None:
        """Record current configuration state for history tracking."""
        # deque doesn't support [-100:] slicing — use itertools.islice or
        # convert via list. Since this is rare (settings save / periodic),
        # the list copy cost is negligible.
        n = len(self._trades)
        recent = list(self._trades)[-100:] if n else []
        sizes = [t.trade_amount for t in recent if t.trade_amount > 0]
        self._config_history.append(ConfigSnapshot(
            timestamp=time.time(),
            reason=reason,
            trade_amount=self._trade_amount,
            adaptive_mode=self._adaptive_mode,
            min_net_profit_pct=self._min_net_profit_pct,
            rebalance_cooldown=self._balance._rebalance_cooldown if self._balance else 0,
            min_misses_before_rebalance=self._min_misses_before_rebalance,
            rebalance_roi_horizon=self._rebalance_roi_horizon,
            total_capital=self._total_capital,
            num_active_symbols=len(self._optimizer.active_symbols) if self._optimizer else 0,
            max_active_symbols=self._optimizer._max_active_symbols if self._optimizer else 0,
            avg_trade_size=sum(sizes) / len(sizes) if sizes else 0,
            estimated_profit_per_trade=(
                self._balance._estimated_profit_per_trade if self._balance else 0
            ),
        ))

    # ── Phase 2: Demo Execution ────────────────────────────────────────

    async def _execute_demo_trade(
        self,
        buy_ex: str, sell_ex: str, symbol: str,
        trade_size: float, buy_price: float, sell_price: float,
        buy_qty: float, sell_qty: float,
        sim_trade: SimulatedTrade,
    ) -> None:
        """Fire real demo orders and compare with sim result.

        Called as an asyncio task — does not block the tick loop.
        Supports single-leg execution: if only one exchange has an executor,
        only that leg is placed on demo. This maximizes demo coverage.
        Records discrepancies (D-08 through D-13) and saves state immediately.
        """
        if not self._executor:
            return

        try:
            has_buy = self._executor.has_executor(buy_ex)
            has_sell = self._executor.has_executor(sell_ex)

            # Skip exchange:symbol:side combos permanently rejected (instrument not found)
            buy_skip_key = f"{buy_ex}:{symbol}:buy"
            sell_skip_key = f"{sell_ex}:{symbol}:sell"
            if has_buy and buy_skip_key in self._demo_skip_pairs:
                has_buy = False
                self._demo_skip_count += 1
            if has_sell and sell_skip_key in self._demo_skip_pairs:
                has_sell = False
                self._demo_skip_count += 1

            # Cap sell qty to available demo position to avoid "insufficient balance"
            actual_sell_qty = sell_qty
            if has_sell:
                actual_sell_qty = self._executor.cap_sell_qty(sell_ex, symbol, sell_qty)
                if actual_sell_qty <= 0:
                    if self._demo_sell_skip_log.get(f"{sell_ex}:{symbol}", 0) == 0:
                        logger.info(
                            f"[DemoTrade] {symbol} SKIP sell on {sell_ex}: "
                            f"no demo position (requested={sell_qty:.8f})"
                        )
                    self._demo_sell_skip_log[f"{sell_ex}:{symbol}"] = (
                        self._demo_sell_skip_log.get(f"{sell_ex}:{symbol}", 0) + 1
                    )
                    has_sell = False  # Treat as no executor for this trade
                elif actual_sell_qty < sell_qty:
                    logger.info(
                        f"[DemoTrade] {symbol} sell on {sell_ex} capped: "
                        f"{sell_qty:.8f}->{actual_sell_qty:.8f} (demo position limit)"
                    )
                # Round qty to exchange lot_size_step after capping
                if has_sell and self._exchange_info:
                    from decimal import Decimal
                    rounded = self._exchange_info.round_quantity(
                        sell_ex, symbol, Decimal(str(actual_sell_qty))
                    )
                    actual_sell_qty = float(rounded)

            if has_buy and has_sell:
                # Both legs available — use full arbitrage execution
                result = await self._executor.execute_arbitrage(
                    buy_ex, sell_ex, symbol, trade_size,
                    buy_price, sell_price, buy_qty, actual_sell_qty,
                )
                self._record_demo_comparison(sim_trade, result)
            elif has_buy or has_sell:
                # Single-leg execution
                from executor import generate_client_order_id

                buy_result = None
                sell_result = None
                t0 = time.time()

                if has_buy:
                    client_id = generate_client_order_id(symbol, "buy")
                    executor = self._executor._executors[buy_ex]
                    try:
                        buy_result = await executor.place_market_order(
                            symbol, "buy", buy_qty, client_id,
                            expected_price=buy_price,
                        )
                    except Exception as e:
                        from executor import TradeResult
                        buy_result = TradeResult(
                            success=False, exchange=buy_ex, symbol=symbol,
                            side="buy", requested_qty=buy_qty,
                            requested_price=buy_price, error=str(e),
                            timestamp=time.time(),
                        )
                    # Track buy position
                    if buy_result and buy_result.success:
                        self._executor.update_demo_position(
                            buy_ex, symbol, "buy", buy_result.filled_qty
                        )

                if has_sell:
                    client_id = generate_client_order_id(symbol, "sell")
                    executor = self._executor._executors[sell_ex]
                    try:
                        sell_result = await executor.place_market_order(
                            symbol, "sell", actual_sell_qty, client_id,
                            expected_price=sell_price,
                        )
                    except Exception as e:
                        from executor import TradeResult
                        sell_result = TradeResult(
                            success=False, exchange=sell_ex, symbol=symbol,
                            side="sell", requested_qty=actual_sell_qty,
                            requested_price=sell_price, error=str(e),
                            timestamp=time.time(),
                        )
                    # Track sell position
                    if sell_result and sell_result.success:
                        self._executor.update_demo_position(
                            sell_ex, symbol, "sell", sell_result.filled_qty
                        )

                total_latency = (time.time() - t0) * 1000.0
                self._record_single_leg_comparison(
                    sim_trade, buy_result, sell_result,
                    buy_ex, sell_ex, total_latency,
                )

            # Immediate state save (crash safety for real trades)
            if self._state_mgr and self._balance and self._optimizer:
                self._state_mgr.save(
                    self._balance, self, self._optimizer, self._demo_fetcher,
                )

        except Exception as e:
            logger.error(f"[Monitor] Demo trade execution failed: {e}")

    async def _run_demo_setup(self) -> None:
        """Place initial buy orders on demo/testnet to establish positions.

        Called once after initialize_crypto() to mirror sim's virtual crypto
        allocations with real demo market buy orders. Runs as asyncio.create_task
        so it doesn't block the tick loop.
        """
        if self._demo_setup_complete or self._demo_setup_running:
            return
        if not self._executor or self._execution_mode == "simulation":
            return
        if not self._balance:
            return

        self._demo_setup_running = True
        logger.info("[DemoSetup] Starting position establishment...")

        try:
            # Build allocations from balance._crypto_usd (per-exchange-per-symbol USD)
            allocations: dict[str, dict[str, float]] = {}
            for ex in self._balance._exchanges:
                if not self._executor.has_executor(ex):
                    continue
                ex_allocs: dict[str, float] = {}
                for sym in self._balance._symbols:
                    usd = self._balance._crypto_usd.get(ex, {}).get(sym, 0.0)
                    if usd > 0:
                        ex_allocs[sym] = usd
                if ex_allocs:
                    allocations[ex] = ex_allocs

            if not allocations:
                logger.info("[DemoSetup] No crypto allocations to establish — skipping")
                self._demo_setup_complete = True
                self._demo_setup_running = False
                return

            total_orders = sum(len(syms) for syms in allocations.values())
            exchanges = list(allocations.keys())
            logger.info(
                f"[DemoSetup] Placing {total_orders} buy orders on {exchanges}"
            )

            prices = self._get_current_prices()
            exchange_info = self._balance._exchange_info if self._balance else None

            # Build fetcher states for depth-aware sizing
            fetcher_states: dict[str, dict] = {}
            for fetcher in self._fetchers:
                ex_name = fetcher.exchange_name
                if ex_name in allocations:
                    fetcher_states[ex_name] = fetcher.get_state()

            results = await self._executor.execute_setup_orders(
                allocations, prices, self._crypto_init_time, exchange_info,
                fetcher_states=fetcher_states,
            )

            self._demo_setup_complete = True
            self._demo_setup_running = False

            # Save state immediately
            if self._state_mgr and self._balance and self._optimizer:
                self._state_mgr.save(
                    self._balance, self, self._optimizer, self._demo_fetcher,
                )

        except Exception as e:
            logger.error(f"[DemoSetup] Position establishment failed: {e}")
            self._demo_setup_running = False

    def _record_demo_comparison(
        self,
        sim_trade: SimulatedTrade,
        result: "ArbitrageResult",
    ) -> None:
        """Compare sim expectations with actual demo results.

        Updates the SimulatedTrade's demo_* fields and logs discrepancies
        for D-08 (slippage), D-09 (partial fill), D-10 (rejection),
        D-11 (one-legged), D-12 (latency), D-13 (maker/taker).
        """
        from executor import ArbitrageResult

        buy = result.buy_result
        sell = result.sell_result

        # Update SimulatedTrade with demo data
        sim_trade.demo_buy_price = buy.actual_avg_price
        sim_trade.demo_sell_price = sell.actual_avg_price
        sim_trade.demo_buy_qty = buy.filled_qty
        sim_trade.demo_sell_qty = sell.filled_qty
        sim_trade.demo_profit_usd = result.actual_profit_usd
        sim_trade.demo_latency_ms = result.total_latency_ms
        sim_trade.demo_slippage_pct = result.avg_slippage_pct

        # Determine status
        if result.one_legged:
            sim_trade.demo_status = "one_legged"
        elif not buy.success and not sell.success:
            sim_trade.demo_status = "rejected"
        elif buy.is_partial or sell.is_partial:
            sim_trade.demo_status = "partial"
        elif buy.success and sell.success:
            sim_trade.demo_status = "filled"
        else:
            sim_trade.demo_status = "unknown"

        # Log significant discrepancies
        sym = sim_trade.symbol

        # D-08: Slippage
        if result.avg_slippage_pct > 0.01:
            logger.info(
                f"[D-08] {sym} slippage: buy={buy.slippage_pct:+.4f}% "
                f"sell={sell.slippage_pct:+.4f}% avg={result.avg_slippage_pct:.4f}%"
            )

        # D-09: Partial fill
        if buy.is_partial:
            logger.warning(
                f"[D-09] {sym} partial fill on {buy.exchange}: "
                f"requested={buy.requested_qty:.8f} filled={buy.filled_qty:.8f} "
                f"ratio={buy.fill_ratio:.2%}"
            )
        if sell.is_partial:
            logger.warning(
                f"[D-09] {sym} partial fill on {sell.exchange}: "
                f"requested={sell.requested_qty:.8f} filled={sell.filled_qty:.8f} "
                f"ratio={sell.fill_ratio:.2%}"
            )

        # D-10: Rejection (throttled — log first per exchange:symbol, then suppress)
        for leg, side in [(buy, "buy"), (sell, "sell")]:
            if not leg.success:
                rkey = f"{leg.exchange}:{sym}:{side}"
                count = self._demo_reject_log.get(rkey, 0) + 1
                self._demo_reject_log[rkey] = count
                if count == 1:
                    logger.warning(
                        f"[D-10] {sym} {side} rejected on {leg.exchange}: {leg.error}"
                    )
                elif count == 2:
                    logger.info(
                        f"[D-10] {sym} {side} on {leg.exchange} rejection repeated — "
                        f"suppressing further logs"
                    )
                # Permanently skip if instrument doesn't exist on this exchange
                err = (leg.error or "").lower()
                if "instrument" in err or "doesn't exist" in err or "not exist" in err:
                    skip_key = f"{leg.exchange}:{sym}:{side}"
                    if skip_key not in self._demo_skip_pairs:
                        self._demo_skip_pairs.add(skip_key)
                        logger.warning(
                            f"[DemoTrade] Permanently skipping {side} {sym} on "
                            f"{leg.exchange}: instrument not available on demo"
                        )

        # D-11: One-legged trade
        if result.one_legged:
            logger.error(
                f"[D-11] {sym} ONE-LEGGED: "
                f"buy={'OK' if buy.success else 'FAIL'} "
                f"sell={'OK' if sell.success else 'FAIL'} "
                f"recovery={'OK' if result.recovery_result and result.recovery_result.success else 'FAIL'}"
            )

        # D-12: High latency
        if result.total_latency_ms > 500:
            logger.warning(
                f"[D-12] {sym} high latency: {result.total_latency_ms:.0f}ms "
                f"(buy={buy.latency_ms:.0f}ms sell={sell.latency_ms:.0f}ms)"
            )

        # D-13: Maker fill (unexpected for market orders)
        if buy.is_maker:
            logger.info(f"[D-13] {sym} buy filled as MAKER on {buy.exchange}")
        if sell.is_maker:
            logger.info(f"[D-13] {sym} sell filled as MAKER on {sell.exchange}")

        # D-05: Fee currency mismatch
        for leg, expected_side in [(buy, "buy"), (sell, "sell")]:
            if leg.success and leg.fee_currency:
                expected_ccy = "USDT" if expected_side == "sell" else sym.replace("USDT", "")
                if leg.fee_currency not in (expected_ccy, "USDT", "BNB", "BGB", "KCS"):
                    logger.warning(
                        f"[D-05] {sym} {expected_side} fee in unexpected currency: "
                        f"{leg.fee_currency} on {leg.exchange}"
                    )

        # D-04b: Fee rate validation per trade
        for leg, side in [(buy, "buy"), (sell, "sell")]:
            if leg.success and leg.fee_rate > 0 and self._fee_manager:
                configured_rate = self._fee_manager.get_taker_fee(leg.exchange)
                if abs(leg.fee_rate - configured_rate) > 0.00005:  # 0.005% tolerance
                    self._demo_fee_mismatches += 1
                    logger.warning(
                        f"[DemoTrade] {sym} {side} fee rate mismatch on {leg.exchange}: "
                        f"configured={configured_rate*100:.3f}% actual={leg.fee_rate*100:.3f}%"
                    )

        # Slippage model accuracy
        if buy.success and sell.success:
            slip_model_err = abs(sim_trade.sim_slippage_pct - result.avg_slippage_pct)
            if slip_model_err > 0.02:  # >0.02% model error
                logger.info(
                    f"[DemoTrade] {sym} slippage model off by {slip_model_err:.4f}%: "
                    f"sim={sim_trade.sim_slippage_pct:.4f}% actual={result.avg_slippage_pct:.4f}%"
                )

        # Profit comparison
        profit_diff = result.actual_profit_usd - sim_trade.profit_usd
        if abs(profit_diff) > 0.01:
            logger.info(
                f"[DemoCompare] {sym} profit: sim=${sim_trade.profit_usd:.4f} "
                f"actual=${result.actual_profit_usd:.4f} diff=${profit_diff:+.4f}"
            )

        # Update demo accuracy counters
        self._demo_trade_count += 1
        self._demo_total_sim_profit += sim_trade.profit_usd
        self._demo_total_actual_profit += result.actual_profit_usd
        self._demo_total_sim_slippage += sim_trade.sim_slippage_pct
        self._demo_total_actual_slippage += result.avg_slippage_pct
        self._demo_total_latency_ms += result.total_latency_ms
        if sim_trade.demo_status == "filled":
            self._demo_fill_count += 1
        elif sim_trade.demo_status == "rejected":
            self._demo_reject_count += 1
        elif sim_trade.demo_status == "partial":
            self._demo_partial_count += 1
        elif sim_trade.demo_status == "one_legged":
            self._demo_one_legged_count += 1

        # Comprehensive per-trade summary log
        logger.info(
            f"[DemoTrade] {sym} {buy.exchange}\u2192{sell.exchange} "
            f"status={sim_trade.demo_status} "
            f"sim_profit=${sim_trade.profit_usd:+.4f} "
            f"demo_profit=${result.actual_profit_usd:+.4f} "
            f"diff=${profit_diff:+.4f} "
            f"sim_slip={sim_trade.sim_slippage_pct:.4f}% "
            f"demo_slip={result.avg_slippage_pct:.4f}% "
            f"buy_price={sim_trade.buy_price:.6f}\u2192{buy.actual_avg_price:.6f} "
            f"sell_price={sim_trade.sell_price:.6f}\u2192{sell.actual_avg_price:.6f} "
            f"buy_fill={buy.fill_ratio:.2%} sell_fill={sell.fill_ratio:.2%} "
            f"buy_fee={buy.actual_fee:.6f}({buy.fee_currency}) "
            f"sell_fee={sell.actual_fee:.6f}({sell.fee_currency}) "
            f"latency={result.total_latency_ms:.0f}ms "
            f"data_age={sim_trade.data_age_ms:.0f}ms"
        )

    def _record_single_leg_comparison(
        self,
        sim_trade: SimulatedTrade,
        buy_result: "TradeResult | None",
        sell_result: "TradeResult | None",
        buy_ex: str,
        sell_ex: str,
        total_latency_ms: float,
    ) -> None:
        """Record demo comparison when only one leg was executed on demo.

        Logs per-leg discrepancies and updates SimulatedTrade demo fields
        for whichever leg(s) were executed.
        """
        sym = sim_trade.symbol
        demo_legs: list[str] = []

        # Update SimulatedTrade fields for executed legs
        if buy_result:
            sim_trade.demo_buy_price = buy_result.actual_avg_price
            sim_trade.demo_buy_qty = buy_result.filled_qty
            demo_legs.append(f"buy@{buy_ex}")
        if sell_result:
            sim_trade.demo_sell_price = sell_result.actual_avg_price
            sim_trade.demo_sell_qty = sell_result.filled_qty
            demo_legs.append(f"sell@{sell_ex}")

        sim_trade.demo_latency_ms = total_latency_ms

        # Determine status based on executed legs
        executed = [r for r in (buy_result, sell_result) if r is not None]
        if all(r.success for r in executed):
            if any(r.is_partial for r in executed):
                sim_trade.demo_status = "partial"
            else:
                sim_trade.demo_status = "filled"
        elif any(r.success for r in executed):
            sim_trade.demo_status = "partial"
        else:
            sim_trade.demo_status = "rejected"

        # Per-leg discrepancy checks
        for leg in executed:
            side = leg.side

            # D-08: Slippage
            if leg.success and leg.slippage_pct > 0.01:
                logger.info(
                    f"[D-08] {sym} {side} slippage on {leg.exchange}: "
                    f"{leg.slippage_pct:+.4f}%"
                )

            # D-09: Partial fill
            if leg.is_partial:
                logger.warning(
                    f"[D-09] {sym} partial fill on {leg.exchange}: "
                    f"requested={leg.requested_qty:.8f} filled={leg.filled_qty:.8f} "
                    f"ratio={leg.fill_ratio:.2%}"
                )

            # D-10: Rejection (throttled — first per exchange:symbol, then suppress)
            if not leg.success:
                rkey = f"{leg.exchange}:{sym}:{side}"
                count = self._demo_reject_log.get(rkey, 0) + 1
                self._demo_reject_log[rkey] = count
                if count == 1:
                    logger.warning(
                        f"[D-10] {sym} {side} rejected on {leg.exchange}: {leg.error}"
                    )
                elif count == 2:
                    logger.info(
                        f"[D-10] {sym} {side} on {leg.exchange} rejection repeated — "
                        f"suppressing further logs"
                    )
                # Permanently skip if instrument doesn't exist on this exchange
                err = (leg.error or "").lower()
                if "instrument" in err or "doesn't exist" in err or "not exist" in err:
                    skip_key = f"{leg.exchange}:{sym}:{side}"
                    if skip_key not in self._demo_skip_pairs:
                        self._demo_skip_pairs.add(skip_key)
                        logger.warning(
                            f"[DemoTrade] Permanently skipping {side} {sym} on "
                            f"{leg.exchange}: instrument not available on demo"
                        )

            # D-12: High latency
            if leg.latency_ms > 500:
                logger.warning(
                    f"[D-12] {sym} {side} high latency on {leg.exchange}: "
                    f"{leg.latency_ms:.0f}ms"
                )

            # D-13: Maker fill
            if leg.is_maker:
                logger.info(f"[D-13] {sym} {side} filled as MAKER on {leg.exchange}")

            # D-05: Fee currency mismatch
            if leg.success and leg.fee_currency:
                expected_ccy = "USDT" if side == "sell" else sym.replace("USDT", "")
                if leg.fee_currency not in (expected_ccy, "USDT", "BNB", "BGB", "KCS"):
                    logger.warning(
                        f"[D-05] {sym} {side} fee in unexpected currency: "
                        f"{leg.fee_currency} on {leg.exchange}"
                    )

            # D-04b: Fee rate validation
            if leg.success and leg.fee_rate > 0 and self._fee_manager:
                configured_rate = self._fee_manager.get_taker_fee(leg.exchange)
                if abs(leg.fee_rate - configured_rate) > 0.00005:
                    self._demo_fee_mismatches += 1
                    logger.warning(
                        f"[DemoTrade] {sym} {side} fee rate mismatch on {leg.exchange}: "
                        f"configured={configured_rate*100:.3f}% "
                        f"actual={leg.fee_rate*100:.3f}%"
                    )

        # Update counters
        self._demo_trade_count += 1
        self._demo_total_latency_ms += total_latency_ms
        if sim_trade.demo_status == "filled":
            self._demo_fill_count += 1
        elif sim_trade.demo_status == "rejected":
            self._demo_reject_count += 1
        elif sim_trade.demo_status == "partial":
            self._demo_partial_count += 1

        # Build per-leg summary parts
        parts = []
        for leg in executed:
            side = leg.side
            status = "OK" if leg.success else "FAIL"
            if leg.success:
                parts.append(
                    f"{side}@{leg.exchange}={status} "
                    f"price={leg.actual_avg_price:.6f} "
                    f"fill={leg.fill_ratio:.2%} "
                    f"fee={leg.actual_fee:.6f}({leg.fee_currency}) "
                    f"latency={leg.latency_ms:.0f}ms"
                )
            else:
                parts.append(f"{side}@{leg.exchange}={status} err={leg.error}")

        sim_only_legs = []
        if buy_result is None:
            sim_only_legs.append(f"buy@{buy_ex}")
        if sell_result is None:
            sim_only_legs.append(f"sell@{sell_ex}")

        sim_note = f" sim_only=[{','.join(sim_only_legs)}]" if sim_only_legs else ""

        logger.info(
            f"[DemoTrade] {sym} {buy_ex}→{sell_ex} "
            f"single_leg status={sim_trade.demo_status} "
            f"{' | '.join(parts)}{sim_note} "
            f"total_latency={total_latency_ms:.0f}ms "
            f"data_age={sim_trade.data_age_ms:.0f}ms"
        )

    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._running = False

    def update_symbols(self, symbols: list[str]) -> None:
        """Update active symbols list (called by SymbolOptimizer)."""
        self._symbols = list(symbols)
        logger.info(f"[Monitor] Symbols updated: {symbols}")

    def reconfigure(
        self,
        symbols: list[str] | None = None,
        exchanges: list[str] | None = None,
        trade_amount: float | None = None,
        balance: BalanceTracker | None = None,
        min_net_profit_pct: float | None = None,
        rebalance_roi_horizon: int | None = None,
    ) -> None:
        """Reconfigure for new symbols/exchanges while preserving cumulative state.

        Resets per-cycle operational state (observations, miss streaks, stale
        tracking) but keeps cumulative session data (trades, tick count, start
        time, P&L buckets, simulation realism counters, demo stats, anomaly
        protection) intact across demotion→discovery→activation cycles.
        """
        if symbols is not None:
            self._symbols = symbols
        if exchanges is not None:
            self._active_exchanges = set(exchanges)
        if trade_amount is not None:
            self._trade_amount = trade_amount
        if balance is not None:
            self._balance = balance
        if min_net_profit_pct is not None:
            self._min_net_profit_pct = min_net_profit_pct
        if rebalance_roi_horizon is not None:
            self._rebalance_roi_horizon = rebalance_roi_horizon

        # Reset per-cycle operational state only
        self._low_profit_skips = 0
        self._stale_skips.clear()
        self._fresh_samples.clear()
        self._exchange_age_sum.clear()
        self._exchange_age_max.clear()
        self._exchange_age_count.clear()
        self._depth_skips = 0
        self._exchange_spread_sum.clear()
        self._exchange_spread_max.clear()
        self._exchange_spread_count.clear()
        self._miss_streak.clear()
        self._rebalance_empty_backoff.clear()
        self._pending_opportunities.clear()

        # Reset demo setup so new symbols get positions established
        self._demo_setup_complete = False
        self._demo_setup_running = False

        # Preserve: _trades, _tick_count, _start_time, _hourly_pnl, _daily_pnl,
        # _config_history, simulation realism counters, demo accuracy stats,
        # _anomaly, _manual_stopped, _demo_skip_pairs

        logger.info(
            f"[Monitor] Reconfigured: {len(self._symbols)} symbols, "
            f"{len(self._active_exchanges)} exchanges, ${self._trade_amount}/trade "
            f"(cumulative: {len(self._trades)} trades, tick #{self._tick_count})"
        )

    def tick_once(self) -> None:
        """Single monitor tick (anomaly sync + trade scan).

        Extracted from `run()` so the multi-config Orchestrator can drive
        the tick rate directly. Calling this in a single-config setup is
        equivalent to one iteration of the legacy while-loop body.
        """
        # First-tick init: `run()` used to seed `_start_time` on its first
        # iteration, but the v0.31 Orchestrator drives `tick_once()` directly
        # and skips `run()`. Without this guard, `_start_time` stays at 0
        # forever for fresh-state bundles, which makes `elapsed_seconds=0`
        # in `get_net_profit_stats()` (so Net $/hr is always $0.00 via the
        # 5-min warmup gate) and `trades_per_minute=0.0` in the dashboard
        # payload (because `start_t > 0` is False). Restored bundles get
        # `_start_time` from state — leave that path untouched.
        if not self._start_time:
            self._start_time = time.time()

        # Anomaly protection: sync pause state
        if self._anomaly.should_block_trading:
            if not self._anomaly_paused:
                self._anomaly_paused = True
                logger.warning("[Monitor] Anomaly protection activated, trading paused")
                # Phase E: tell hedge manager to stop opening new hedges.
                # Existing hedges keep tracking inventory and can still close.
                if self._hedge_manager is not None:
                    self._hedge_manager.on_safety_pause(reason=self._anomaly._pause_reason or "anomaly")
        elif self._anomaly_paused:
            self._anomaly_paused = False
            logger.info("[Monitor] Anomaly protection cleared, resuming trading")
            # Phase E: hedge manager should re-evaluate / reconcile after resume
            if self._hedge_manager is not None:
                self._hedge_manager.on_safety_resume()

        # Phase E: also propagate manual-stop state to hedge manager
        if self._hedge_manager is not None:
            if self._manual_stopped and not self._hedge_manager._safety_paused:
                self._hedge_manager.on_safety_pause(reason="manual_stop")
            elif not self._manual_stopped and not self._anomaly_paused and self._hedge_manager._safety_paused:
                # Both anomaly and manual-stop are clear → resume
                self._hedge_manager.on_safety_resume()

        if not self._paused and not self._anomaly_paused and not self._manual_stopped:
            self._tick()

    async def run(self) -> None:
        """Main loop: periodically scan prices, simulate trades, print table.

        Used by the legacy single-component setup. The multi-config
        Orchestrator drives `tick_once()` directly and skips this wrapper.
        """
        self._running = True
        if not self._start_time:
            self._start_time = time.time()
        exchange_names = [f.exchange_name for f in self._fetchers]
        logger.info(
            f"[Monitor] Starting simulation: {', '.join(exchange_names)} "
            f"| {len(self._symbols)} symbols | ${self._trade_amount} per trade"
        )

        while self._running:
            self.tick_once()
            await asyncio.sleep(MONITOR_INTERVAL_SECONDS)

        logger.info("[Monitor] Simulation stopped")

    def _tick(self) -> None:
        """One simulation tick: scan prices, simulate trades, print."""
        now = time.time()
        dt = datetime.fromtimestamp(now, tz=LOCAL_TZ)
        self._tick_count += 1

        # Emergency sell-all triggered by anomaly protection
        if self._anomaly.should_emergency_sell and self._balance:
            self._emergency_sell_all()
            self._anomaly.clear_emergency_sell()
            # Reset peak: portfolio is now 100% USDT, old peak is meaningless
            prices = self._get_current_prices()
            portfolio = self._balance.get_portfolio_value(prices)
            self._anomaly.reset_peak_if_no_crypto(portfolio)

        # Hourly emergency-email reminder while operator hasn't manually resumed.
        # `should_resend_emergency_email()` returns False once `_emergency_triggered`
        # is cleared by manual_resume(), naturally stopping the cycle.
        if self._anomaly.should_resend_emergency_email(now) and self._balance:
            from email_notifier import notify_emergency_reminder
            usdt_breakdown = {
                ex: self._balance.usdt.get(ex, 0.0)
                for ex in self._balance._exchanges
                if self._balance.usdt.get(ex, 0.0) > 0
            }
            paused_for = now - self._anomaly._pause_timestamp if self._anomaly._pause_timestamp else 0.0
            _safe_task(
                notify_emergency_reminder(
                    reason=self._anomaly._pause_reason,
                    drawdown_pct=self._anomaly._current_drawdown_pct,
                    peak_value=self._anomaly._peak_portfolio_value,
                    current_value=sum(usdt_breakdown.values()),
                    paused_for_seconds=paused_for,
                    portfolio_breakdown=usdt_breakdown,
                ),
                name="emergency_email_reminder",
            )
            self._anomaly.mark_emergency_email_sent(now)
            logger.warning(
                f"[Anomaly] EMERGENCY_EMAIL_REMINDER sent "
                f"(paused {paused_for/3600:.1f}h, drawdown {self._anomaly._current_drawdown_pct:.1f}%)"
            )

        # Initialize balance tracker as soon as prices are available
        if self._balance and not self._balance.initialized:
            self._balance.initialize_crypto(self._get_current_prices())
            if self._balance.initialized:
                self._crypto_init_time = time.time()

        # Hedge manager evaluation (Phase C: shadow; Phase D: real on testnet;
        # Phase E: respects safety-pause but still runs so demotion-driven
        # closes can fire). Internally throttled by evaluation_interval.
        # Gated on balance.initialized to mirror the inventory-rebalance fix.
        # Fire as a task so the executor's REST calls don't block the main loop.
        if (self._hedge_manager is not None
                and self._balance and self._balance.initialized):
            _safe_task(self._hedge_manager.evaluate(now), "hedge_evaluate")

            # Detect hedge-state transition (0↔N) and reset anomaly peak
            # so drawdown is apples-to-apples after the basis change.
            try:
                hedge_state = self._hedge_manager.get_debug_state()
                cur_count = int(hedge_state.get("open_count", 0))
                if (self._prev_hedge_count == 0) != (cur_count == 0):
                    # Transition between zero-hedge and active-hedge state
                    prices = self._get_current_prices()
                    portfolio = self._balance.get_portfolio_value(
                        prices,
                        hedge_pnl_usd=float(hedge_state.get("total_unrealized_pnl_usd", 0.0)),
                    )
                    direction = "hedge_opened" if cur_count > 0 else "hedge_closed"
                    self._anomaly.reset_peak_on_basis_change(portfolio, direction)
                self._prev_hedge_count = cur_count
            except Exception as e:
                logger.debug(f"[Hedge] state transition check failed: {e}")

        # After initialize_crypto, place demo setup orders (one-shot)
        if (self._balance and self._balance.initialized
                and not self._demo_setup_complete
                and not self._demo_setup_running
                and self._execution_mode in ("demo", "demo_only")
                and self._executor):
            _safe_task(self._run_demo_setup(), "demo_setup")

        # D-17: Deliver in-transit funds that have arrived
        if self._balance and self._balance._in_transit:
            self._balance.deliver_in_transit()

        # Credit referral cashbacks whose settlement time has passed
        if self._fee_manager and self._balance:
            credited = self._fee_manager.credit_due_cashbacks()
            for cb in credited:
                if cb.exchange in self._balance.usdt:
                    self._balance.usdt[cb.exchange] += cb.cashback_usd
                    logger.info(
                        f"[Fee] Cashback credited: {cb.exchange} +${cb.cashback_usd:.4f}"
                    )

        rows: list[tuple[str, str, float, str, float, float, float, float, float]] = []

        # Track per-exchange data age for this tick's display
        tick_age_lists: dict[str, list[float]] = defaultdict(list)

        # v0.31.0-beta+: read from the orchestrator's per-sweep prices cache
        # if one is set. Same primitives as `optimizer._score_tick` — sharing
        # the cache avoids 60-symbol × 9-fetcher state lookups per config.
        from tick_cache import get_sweep_prices, filter_for_config_full
        sweep_prices = get_sweep_prices()

        for symbol in self._symbols:
            exchange_prices: list[tuple[str, float, float]] = []
            # Per-exchange data age for this symbol (for trade metadata)
            symbol_ex_age: dict[str, float] = {}

            if sweep_prices is not None:
                # Shared-cache fast path: read pre-built (ex, bid, ask, bid_qty,
                # ask_qty, bids_f, asks_f, received_at) tuples and assemble
                # the legacy 7-tuple format the rest of `_tick` consumes.
                for ex, bid_f, ask_f, bid_qty_f, ask_qty_f, bids_f, asks_f, recv_at in (
                    filter_for_config_full(sweep_prices, symbol, self._active_exchanges)
                ):
                    # Per-config age stats — same numbers, just sourced
                    # from the shared cache's received_at column.
                    if recv_at > 0:
                        age = now - recv_at
                        symbol_ex_age[ex] = age
                        tick_age_lists[ex].append(age)
                        self._exchange_age_sum[ex] += age
                        self._exchange_age_count[ex] += 1
                        if age > self._exchange_age_max[ex]:
                            self._exchange_age_max[ex] = age
                        if age > MAX_DATA_AGE_SECONDS:
                            self._stale_skips[ex] += 1
                            continue
                        self._fresh_samples[ex] += 1
                    # D-03: Round prices to tick size (corrects float imprecision)
                    if self._exchange_info:
                        from decimal import Decimal
                        bid_f = float(self._exchange_info.round_price(
                            ex, symbol, Decimal(str(bid_f))
                        ))
                        ask_f = float(self._exchange_info.round_price(
                            ex, symbol, Decimal(str(ask_f))
                        ))
                    bid_depth = bid_f * bid_qty_f if bid_qty_f > 0 else float("inf")
                    ask_depth = ask_f * ask_qty_f if ask_qty_f > 0 else float("inf")
                    exchange_prices.append((ex, bid_f, ask_f, bid_depth, ask_depth, bids_f, asks_f))
            else:
                # Legacy single-config path: build per-tick from fetchers.
                for fetcher in self._fetchers:
                    if fetcher.exchange_name not in self._active_exchanges:
                        continue
                    state = fetcher.get_state()
                    ps = state.get(symbol)
                    if ps is None or not ps.bid or not ps.ask:
                        continue
                    if ps.received_at > 0:
                        age = now - ps.received_at
                        symbol_ex_age[fetcher.exchange_name] = age
                        tick_age_lists[fetcher.exchange_name].append(age)
                        self._exchange_age_sum[fetcher.exchange_name] += age
                        self._exchange_age_count[fetcher.exchange_name] += 1
                        if age > self._exchange_age_max[fetcher.exchange_name]:
                            self._exchange_age_max[fetcher.exchange_name] = age
                        if age > MAX_DATA_AGE_SECONDS:
                            self._stale_skips[fetcher.exchange_name] += 1
                            continue
                        self._fresh_samples[fetcher.exchange_name] += 1
                    try:
                        bid_f = float(ps.bid)
                        ask_f = float(ps.ask)
                    except (ValueError, TypeError):
                        continue
                    if bid_f <= 0 or ask_f <= 0:
                        continue
                    if self._exchange_info:
                        from decimal import Decimal
                        bid_rounded = self._exchange_info.round_price(
                            fetcher.exchange_name, symbol, Decimal(str(bid_f))
                        )
                        ask_rounded = self._exchange_info.round_price(
                            fetcher.exchange_name, symbol, Decimal(str(ask_f))
                        )
                        bid_f = float(bid_rounded)
                        ask_f = float(ask_rounded)
                    try:
                        bid_qty_f = float(ps.bid_qty) if ps.bid_qty else 0.0
                        ask_qty_f = float(ps.ask_qty) if ps.ask_qty else 0.0
                    except (ValueError, TypeError):
                        bid_qty_f = 0.0
                        ask_qty_f = 0.0
                    bid_depth = bid_f * bid_qty_f if bid_qty_f > 0 else float("inf")
                    ask_depth = ask_f * ask_qty_f if ask_qty_f > 0 else float("inf")
                    exchange_prices.append((fetcher.exchange_name, bid_f, ask_f, bid_depth, ask_depth, ps.bids, ps.asks))

            if len(exchange_prices) < 2:
                continue

            # Track per-exchange internal spread (bid-ask on same exchange)
            for ex_name, ex_bid, ex_ask, _, _, _, _ in exchange_prices:
                if ex_bid > 0:
                    internal_spread = (ex_ask - ex_bid) / ex_bid * 100
                    self._exchange_spread_sum[ex_name] += internal_spread
                    self._exchange_spread_count[ex_name] += 1
                    if internal_spread > self._exchange_spread_max[ex_name]:
                        self._exchange_spread_max[ex_name] = internal_spread

            best_scoring_net = float("-inf")
            best_row = None
            best_buy_asks = None
            best_sell_bids = None
            # Track best without EVD penalty for demotion detection
            best_raw_net = float("-inf")
            best_raw_sell_ex: str = ""

            for i, (ex_buy, _, ask_i, _, ask_depth_i, _bids_i, asks_i) in enumerate(exchange_prices):
                for j, (ex_sell, bid_j, _, bid_depth_j, _, bids_j, _asks_j) in enumerate(exchange_prices):
                    if i == j:
                        continue

                    # Per-role gate: skip pairs where the operator has disabled
                    # buyer or seller role (Fee Management → Buyer/Seller checkboxes)
                    # or where the symbol is in the exchange's disabled_symbols list.
                    if self._fee_manager and (
                        not self._fee_manager.can_buy(ex_buy, symbol)
                        or not self._fee_manager.can_sell(ex_sell, symbol)
                    ):
                        continue

                    # Skip if insufficient depth (use min_trade as threshold)
                    min_depth = max(5.0, self._total_capital * 0.003) if self._adaptive_mode else self._trade_amount
                    if ask_depth_i < min_depth or bid_depth_j < min_depth:
                        self._depth_skips += 1
                        continue

                    spread_pct = (bid_j - ask_i) / ask_i * 100

                    # Compute slippage estimate using trade_amount
                    buy_slip = compute_buy_slippage(asks_i, self._trade_amount)
                    sell_slip = compute_sell_slippage(bids_j, self._trade_amount)
                    slippage_pct = buy_slip.slippage_pct + sell_slip.slippage_pct

                    # Scoring fees for pair selection (includes cashback weighting)
                    s_buy = self._fee_manager.get_scoring_fee(ex_buy, symbol) if self._fee_manager else 0.001
                    s_sell = self._fee_manager.get_scoring_fee(ex_sell, symbol) if self._fee_manager else 0.001
                    raw_scoring_net = spread_pct - (s_buy + s_sell) * 100 - slippage_pct
                    scoring_net = raw_scoring_net

                    # Per-role boost: multiply scoring_net by the buyer/seller
                    # preference multipliers. Default 1.0 (neutral) — operator can
                    # set Bitfinex.buyer_boost=5.0 + MEXC.seller_boost=5.0 to bias
                    # selection toward the cheapest sustainable route. A non-preferred
                    # pair must beat the preferred pair's net% by at least the boost
                    # ratio to win — a 12% spike on OKX→MEXC easily overrides 5×.
                    if self._fee_manager:
                        buy_boost = self._fee_manager.get_buyer_boost(ex_buy)
                        sell_boost = self._fee_manager.get_seller_boost(ex_sell)
                        scoring_net *= buy_boost * sell_boost

                    # Penalize event-driven sellers (stale bid risk)
                    if self._event_driven_seller_penalty > 0 and ex_sell in self._event_driven_exchanges:
                        scoring_net -= self._event_driven_seller_penalty
                        self._event_driven_seller_penalties += 1

                    # Track raw best for demotion detection
                    if raw_scoring_net > best_raw_net:
                        best_raw_net = raw_scoring_net
                        best_raw_sell_ex = ex_sell

                    # Taker fees for profit calculation (actual fee charged)
                    t_buy = self._fee_manager.get_taker_fee(ex_buy, symbol) if self._fee_manager else 0.001
                    t_sell = self._fee_manager.get_taker_fee(ex_sell, symbol) if self._fee_manager else 0.001
                    fee_pct = (t_buy + t_sell) * 100
                    net_pct = spread_pct - fee_pct - slippage_pct
                    profit_usd = self._trade_amount * (net_pct / 100)

                    if scoring_net > best_scoring_net:
                        best_scoring_net = scoring_net
                        best_row = (symbol, ex_buy, ask_i, ex_sell, bid_j,
                                    spread_pct, fee_pct, net_pct, profit_usd)
                        best_buy_asks = asks_i
                        best_sell_bids = bids_j

            # EVD demotion detection: raw winner was event-driven but penalized winner differs
            if (
                self._event_driven_seller_penalty > 0
                and best_raw_sell_ex in self._event_driven_exchanges
                and best_row is not None
                and best_row[3] != best_raw_sell_ex  # winner sell_ex differs from raw winner
            ):
                self._event_driven_seller_demoted += 1
                _evd_last = self._evd_demoted_last_log.get(symbol, 0.0)
                if now - _evd_last >= 300:
                    self._evd_demoted_last_log[symbol] = now
                    logger.info(
                        f"[Monitor] EVD_DEMOTED {symbol}: {best_raw_sell_ex} demoted to "
                        f"{best_row[3]} (penalty={self._event_driven_seller_penalty:.3f}%)"
                    )

            if best_row is not None:
                rows.append(best_row)
                sym, buy_ex, ask_p, sell_ex, bid_p, spread, fee, net, profit = best_row

                # Log when event-driven exchange IS selected as seller (despite penalty)
                if (
                    self._event_driven_seller_penalty > 0
                    and sell_ex in self._event_driven_exchanges
                ):
                    evd_key = f"evd_seller:{sym}"
                    self._size_zero_log_count.setdefault(evd_key, 0)
                    self._size_zero_log_count[evd_key] += 1
                    evd_count = self._size_zero_log_count[evd_key]
                    if evd_count <= 3 or evd_count % 30 == 0:
                        logger.info(
                            f"[Monitor] EVD_SELLER {sym} {buy_ex}->{sell_ex}: "
                            f"net={net:.4f}% (penalty={self._event_driven_seller_penalty:.3f}% "
                            f"applied, still best)"
                        )

                # Minimum net% threshold (scoring_net includes cashback weighting).
                # Apply regime multiplier — during WEAK UTC hours the threshold
                # is raised so marginal opportunities are skipped to avoid
                # transfer-fee overhead in thin market windows.
                pair_min_net = self._effective_min_net_profit_pct()

                # Simulate trade if profitable after cashback AND raw P&L is
                # positive. The raw-net check (v0.30.5) prevents executing
                # trades that depend on delayed cashback to break even —
                # observed in S30 where Bitget→Binance PENDLE trades printed
                # net=-0.0055% (raw loss $0.001/trade) because scoring_net
                # included pre-applied cashback. Cashback is real but
                # delayed; we shouldn't trade at an immediate raw deficit
                # for the *promise* of cashback.
                raw_net_pct = best_row[7] if best_row else 0.0
                if (
                    best_scoring_net > 0
                    and best_scoring_net >= pair_min_net
                    and raw_net_pct > 0
                ):
                    self._interval_profitable += 1

                    # Spread persistence gate: require spread across consecutive ticks
                    if self._spread_persistence_ticks > 0:
                        opp_key = f"{sym}:{buy_ex}:{sell_ex}"
                        pending = self._pending_opportunities.get(opp_key)
                        if pending is None or pending["tick"] < self._tick_count - 1:
                            # New or non-consecutive — start tracking
                            self._pending_opportunities[opp_key] = {
                                "tick": self._tick_count, "count": 1,
                            }
                            self._phantom_spread_count += 1
                            continue  # Don't execute yet — wait for persistence
                        else:
                            pending["tick"] = self._tick_count
                            pending["count"] += 1
                            if pending["count"] <= self._spread_persistence_ticks:
                                continue  # Not enough consecutive ticks yet
                            # Passed persistence check — proceed to execute

                    # Per-symbol anomaly block: skip symbols in loss streak cooldown
                    if self._anomaly.is_symbol_blocked(sym):
                        continue

                    can_trade = True

                    # Compute trade size (adaptive or static)
                    if self._adaptive_mode:
                        trade_size = self._compute_trade_size(
                            buy_ex, sell_ex, sym, best_scoring_net, bid_p,
                        )
                    else:
                        trade_size = self._trade_amount

                    # Position accumulation cap: limit crypto value per symbol per buyer exchange
                    if self._max_position_multiplier > 0 and self._balance and trade_size > 0:
                        cap = self._trade_amount * self._max_position_multiplier
                        crypto_qty = self._balance.crypto.get(buy_ex, {}).get(sym, 0.0)
                        crypto_val = crypto_qty * ask_p if crypto_qty > 0 else 0.0
                        min_trade = max(5.0, self._total_capital * 0.003)
                        if crypto_val >= cap:
                            self._position_cap_skips += 1
                            trade_size = 0  # will be caught by trade_size <= 0 check below
                        elif crypto_val + trade_size > cap:
                            trade_size = max(0, cap - crypto_val)
                            if trade_size < min_trade:
                                self._position_cap_skips += 1
                                trade_size = 0

                    if self._balance and self._balance.initialized:
                        # Track miss-streak for rebalancing (even when trade_size is 0)
                        if trade_size <= 0:
                            self._interval_size_skips += 1
                            miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                            streak = self._miss_streak[miss_key] = self._miss_streak.get(miss_key, 0) + 1
                            if streak == 1 or streak % 120 == 0:
                                sym_score = self._optimizer.get_symbol_score(sym) if self._optimizer else None
                                mult = sym_score.trade_multiplier if sym_score else 1.0
                                score_val = sym_score.score if sym_score else 0.0
                                logger.info(
                                    f"[Monitor] SKIP {sym} {buy_ex}->{sell_ex}: "
                                    f"trade_size=0 (net={net:.4f}% mult={mult:.1f} "
                                    f"score={score_val:.4f} streak={streak})"
                                )
                            can_trade = False
                        else:
                            has_usdt, has_crypto = self._balance.can_execute(
                                buy_ex, sell_ex, sym, trade_size, bid_p
                            )
                            if not has_usdt or not has_crypto:
                                self._interval_balance_skips += 1
                                miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                                streak = self._miss_streak[miss_key] = self._miss_streak.get(miss_key, 0) + 1
                                if streak == 1 or streak % 120 == 0:
                                    logger.info(
                                        f"[Monitor] SKIP {sym} {buy_ex}->{sell_ex}: "
                                        f"insufficient balance (net={net:.4f}% size=${trade_size:.2f} "
                                        f"usdt={has_usdt} crypto={has_crypto} streak={streak})"
                                    )
                                can_trade = False

                        # Try rebalancing when miss-streak is high enough
                        miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                        if not can_trade and self._miss_streak.get(miss_key, 0) >= self._get_miss_threshold(buy_ex, sell_ex):
                            # Check backoff from previous EMPTY results
                            backoff_entry = self._rebalance_empty_backoff.get(miss_key)
                            if backoff_entry and time.time() < backoff_entry[0]:
                                pass  # Skip — still in backoff cooldown
                            else:
                                # Gates: optimizer score + ROI + net P&L
                                score_ok = self._optimizer and self._optimizer.should_allow_rebalance(sym)
                                if score_ok:
                                    rebal_ok, rebal_reason = self._should_rebalance(buy_ex, sell_ex)
                                else:
                                    rebal_ok = False
                                    sym_score_obj = self._optimizer.get_symbol_score(sym) if self._optimizer else None
                                    score_val = sym_score_obj.score if sym_score_obj else 0.0
                                    rebal_reason = f"score_gate (score={score_val:.4f} < 0.01)"

                                if score_ok and rebal_ok:
                                    prices = self._get_current_prices()
                                    rebal_transfers = self._balance.try_rebalance(
                                        buy_ex, sell_ex, sym, self._trade_amount, prices
                                    )
                                    if rebal_transfers:
                                        self._miss_streak[miss_key] = 0
                                        self._rebalance_empty_backoff.pop(miss_key, None)
                                    else:
                                        # Exponential backoff: 30s → 60s → 120s → 240s, cap 300s
                                        prev_backoff = backoff_entry[1] if backoff_entry else 15.0
                                        next_backoff = min(prev_backoff * 2, 300.0)
                                        self._rebalance_empty_backoff[miss_key] = (
                                            time.time() + next_backoff, next_backoff
                                        )
                                        logger.info(
                                            f"[Rebalance] EMPTY {sym} {buy_ex}->{sell_ex} "
                                            f"streak={streak}: no transfers, backoff={next_backoff:.0f}s"
                                        )
                                else:
                                    streak = self._miss_streak.get(miss_key, 0)
                                    self._rebalance_block_log_count[miss_key] += 1
                                    rbl_count = self._rebalance_block_log_count[miss_key]
                                    if rbl_count == 1 or rbl_count % 30 == 0:
                                        logger.info(
                                            f"[Rebalance] BLOCKED {sym} {buy_ex}->{sell_ex} "
                                            f"streak={streak}: {rebal_reason}"
                                        )

                                    # Emergency draw from custody hub when net_pnl_gate blocks
                                    # (v0.30+: was Bitfinex reserve, now Bybit custody)
                                    miss_thresh = self._get_miss_threshold(buy_ex, sell_ex)
                                    if (
                                        rebal_reason.startswith("net_pnl_gate")
                                        and streak >= miss_thresh * 2
                                        and self._balance
                                    ):
                                        reserve_transfers = self._balance.emergency_draw_from_custody(
                                            buy_ex, self._trade_amount * 3
                                        )
                                        if reserve_transfers:
                                            self._miss_streak[miss_key] = 0
                                            self._rebalance_empty_backoff.pop(miss_key, None)
                                            # Mark as allowed so retry path runs
                                            score_ok = True
                                            rebal_ok = True

                                if score_ok and rebal_ok:
                                    # Retry trade after rebalancing
                                    trade_size = self._compute_trade_size(
                                        buy_ex, sell_ex, sym, net, bid_p,
                                    ) if self._adaptive_mode else self._trade_amount
                                    if trade_size > 0:
                                        has_usdt, has_crypto = self._balance.can_execute(
                                            buy_ex, sell_ex, sym, trade_size, bid_p
                                        )
                                        can_trade = has_usdt and has_crypto

                        # Execute the trade or count the skip
                        if can_trade:
                            miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                            # Only fully reset streak if trade is substantial (≥50% of base amount).
                            # Tiny residual trades shouldn't prevent rebalance from triggering.
                            if trade_size >= self._trade_amount * 0.5:
                                self._miss_streak[miss_key] = 0
                                self._rebalance_empty_backoff.pop(miss_key, None)
                            else:
                                self._miss_streak[miss_key] = max(0, self._miss_streak.get(miss_key, 0) - 1)
                            buy_fee_rate = self._fee_manager.get_taker_fee(buy_ex, sym) if self._fee_manager else 0.001
                            sell_fee_rate = self._fee_manager.get_taker_fee(sell_ex, sym) if self._fee_manager else 0.001
                            buy_fee_model = self._fee_manager.get_fee_model(buy_ex) if self._fee_manager else "received"
                            sell_fee_model = self._fee_manager.get_fee_model(sell_ex) if self._fee_manager else "received"
                            trade_adj = self._balance.execute_trade(
                                buy_ex, sell_ex, sym, trade_size,
                                ask_p, bid_p, buy_fee_rate, sell_fee_rate,
                                buy_fee_model=buy_fee_model,
                                sell_fee_model=sell_fee_model,
                            )
                            logger.info(
                                f"[Fee] {sym} {buy_ex}->{sell_ex}: "
                                f"buy={buy_fee_rate*100:.4f}% sell={sell_fee_rate*100:.4f}% "
                                f"model={buy_fee_model}/{sell_fee_model}"
                            )
                            # Record referral cashback if enabled
                            if self._fee_manager:
                                buy_cb = self._fee_manager.record_referral_cashback(
                                    buy_ex, sym, trade_size, buy_fee_rate
                                )
                                sell_cb = self._fee_manager.record_referral_cashback(
                                    sell_ex, sym, trade_size, sell_fee_rate
                                )
                                if buy_cb > 0 or sell_cb > 0:
                                    logger.info(
                                        f"[Fee] Referral pending: "
                                        f"{buy_ex}=${buy_cb:.4f} {sell_ex}=${sell_cb:.4f}"
                                    )
                                # Record referrer commission (display-only)
                                buy_rc = self._fee_manager.record_referrer_commission(
                                    buy_ex, sym, trade_size, buy_fee_rate
                                )
                                sell_rc = self._fee_manager.record_referrer_commission(
                                    sell_ex, sym, trade_size, sell_fee_rate
                                )
                                if buy_rc > 0 or sell_rc > 0:
                                    logger.info(
                                        f"[Fee] Referrer commission: "
                                        f"{buy_ex}=${buy_rc:.4f} {sell_ex}=${sell_rc:.4f}"
                                    )
                        else:
                            trade_adj = None
                            self._balance.skipped_trades += 1
                    elif self._balance:
                        self._balance.skipped_trades += 1
                        can_trade = False
                        trade_adj = None

                    if can_trade:
                        self._interval_executed += 1
                        # Recompute slippage with actual trade size
                        buy_slip_actual = compute_buy_slippage(best_buy_asks, trade_size)
                        sell_slip_actual = compute_sell_slippage(best_sell_bids, trade_size)
                        actual_slippage = buy_slip_actual.slippage_pct + sell_slip_actual.slippage_pct
                        net_adjusted = spread - fee - actual_slippage
                        actual_profit = trade_size * (net_adjusted / 100)

                        # One-legged failure simulation
                        one_leg_flag = False
                        if self._one_leg_failure_rate > 0 and random.random() < self._one_leg_failure_rate:
                            failed_leg = random.choice(["buy", "sell"])
                            unwind_fee = buy_fee_rate if failed_leg == "buy" else sell_fee_rate
                            unwind_slip = actual_slippage * self._one_leg_unwind_slippage_mult
                            unwind_cost = trade_size * (unwind_fee + unwind_slip / 100)
                            actual_profit -= unwind_cost
                            self._one_leg_sim_count += 1
                            self._one_leg_sim_cost += unwind_cost
                            one_leg_flag = True
                            logger.info(
                                f"[Trade] ONE_LEG_SIM #{self._cumulative_trade_count + 1} {sym} "
                                f"{buy_ex}->{sell_ex}: failed_leg={failed_leg} "
                                f"unwind_cost=${unwind_cost:.4f} "
                                f"adjusted_profit=${actual_profit:.4f}"
                            )

                        # Data age: max of buy and sell exchange ages (ms)
                        buy_age = symbol_ex_age.get(buy_ex, 0.0)
                        sell_age = symbol_ex_age.get(sell_ex, 0.0)
                        max_age_ms = max(buy_age, sell_age) * 1000.0
                        # Rounding metadata from execute_trade adjustment
                        adj = trade_adj or {}
                        trade = SimulatedTrade(
                            timestamp=now, symbol=sym,
                            buy_exchange=buy_ex, sell_exchange=sell_ex,
                            buy_price=ask_p, sell_price=bid_p,
                            spread_pct=spread, fee_pct=fee,
                            net_pct=net_adjusted, profit_usd=actual_profit,
                            trade_amount=trade_size,
                            buy_qty_raw=adj.get("buy_qty_raw", 0.0),
                            buy_qty_rounded=adj.get("buy_qty_rounded", 0.0),
                            sell_qty_raw=adj.get("sell_qty_raw", 0.0),
                            sell_qty_rounded=adj.get("sell_qty_rounded", 0.0),
                            rounding_impact_usd=adj.get("rounding_impact_usd", 0.0),
                            data_age_ms=max_age_ms,
                            sim_slippage_pct=actual_slippage,
                            sim_buy_slippage_pct=buy_slip_actual.slippage_pct,
                            sim_sell_slippage_pct=sell_slip_actual.slippage_pct,
                            one_leg_simulated=one_leg_flag,
                        )
                        self._trades.append(trade)
                        # Incremental aggregates — survives deque eviction
                        # so totals stay accurate after >5000 trades.
                        self._cumulative_pnl += actual_profit
                        self._last_trade_ts = time.time()  # quiet-period reset
                        self._cumulative_trade_count += 1
                        self._record_trade_pnl(now, actual_profit)
                        self._anomaly.record_trade(now, sym, actual_profit, context={
                            "buy_ex": buy_ex, "sell_ex": sell_ex,
                            "net_pct": net_adjusted, "trade_size": trade_size,
                        })
                        qty = trade_size / ask_p if ask_p > 0 else 0.0
                        slip_str = f" slip={actual_slippage:.4f}%" if actual_slippage > 0 else ""
                        logger.info(
                            f"[Trade] #{self._cumulative_trade_count} {sym} {buy_ex}->{sell_ex}: "
                            f"buy@${ask_p:.4f} sell@${bid_p:.4f} qty={qty:.4f} "
                            f"size=${trade_size:.2f} profit=${actual_profit:.4f} "
                            f"(net={net_adjusted:+.4f}%{slip_str})"
                        )
                        if trade_adj:
                            rnd = trade_adj["rounding_impact_usd"]
                            if abs(rnd) > 0.001:
                                logger.debug(
                                    f"[Monitor] {sym} rounding: buy {trade_adj['buy_qty_raw']:.8f}"
                                    f"→{trade_adj['buy_qty_rounded']:.8f}, "
                                    f"sell {trade_adj['sell_qty_raw']:.8f}"
                                    f"→{trade_adj['sell_qty_rounded']:.8f}, "
                                    f"impact=${rnd:+.4f}"
                                )

                        # Phase 2: Fire demo orders (non-blocking)
                        # Execute on ANY leg that has a demo executor (not just both)
                        if (self._execution_mode in ("demo", "demo_only")
                                and self._executor
                                and (self._executor.has_executor(buy_ex)
                                     or self._executor.has_executor(sell_ex))):
                            _safe_task(self._execute_demo_trade(
                                buy_ex, sell_ex, sym, trade_size,
                                ask_p, bid_p,
                                adj.get("buy_qty_rounded", trade_size / ask_p),
                                adj.get("sell_qty_rounded", trade_size / bid_p),
                                trade,
                            ), f"demo_trade_{sym}")

                elif net > 0:
                    # Positive but below threshold — still track miss-streak
                    # so rebalancing can trigger for generally-profitable symbols
                    self._low_profit_skips += 1
                    if self._balance and self._balance.initialized:
                        miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                        self._miss_streak[miss_key] = self._miss_streak.get(miss_key, 0) + 1

                        if self._miss_streak.get(miss_key, 0) >= self._get_miss_threshold(buy_ex, sell_ex):
                            # Check backoff from previous EMPTY results
                            backoff_entry = self._rebalance_empty_backoff.get(miss_key)
                            if backoff_entry and time.time() < backoff_entry[0]:
                                pass  # Skip — still in backoff cooldown
                            else:
                                score_ok = self._optimizer and self._optimizer.should_allow_rebalance(sym)
                                if score_ok:
                                    rebal_ok, rebal_reason = self._should_rebalance(buy_ex, sell_ex)
                                else:
                                    rebal_ok = False
                                    sym_score_obj = self._optimizer.get_symbol_score(sym) if self._optimizer else None
                                    score_val = sym_score_obj.score if sym_score_obj else 0.0
                                    rebal_reason = f"score_gate (score={score_val:.4f} < 0.01)"

                                if score_ok and rebal_ok:
                                    prices = self._get_current_prices()
                                    rebal_transfers = self._balance.try_rebalance(
                                        buy_ex, sell_ex, sym, self._trade_amount, prices
                                    )
                                    if rebal_transfers:
                                        self._miss_streak[miss_key] = 0
                                        self._rebalance_empty_backoff.pop(miss_key, None)
                                    else:
                                        # Exponential backoff: 30s → 60s → 120s → 240s, cap 300s
                                        prev_backoff = backoff_entry[1] if backoff_entry else 15.0
                                        next_backoff = min(prev_backoff * 2, 300.0)
                                        self._rebalance_empty_backoff[miss_key] = (
                                            time.time() + next_backoff, next_backoff
                                        )
                                        streak = self._miss_streak.get(miss_key, 0)
                                        logger.info(
                                            f"[Rebalance] EMPTY {sym} {buy_ex}->{sell_ex} "
                                            f"streak={streak}: no transfers, backoff={next_backoff:.0f}s"
                                        )
                                else:
                                    streak = self._miss_streak.get(miss_key, 0)
                                    self._rebalance_block_log_count[miss_key] += 1
                                    rbl_count = self._rebalance_block_log_count[miss_key]
                                    if rbl_count == 1 or rbl_count % 30 == 0:
                                        logger.info(
                                            f"[Rebalance] BLOCKED {sym} {buy_ex}->{sell_ex} "
                                            f"streak={streak}: {rebal_reason}"
                                        )

                # Periodically update estimated profit on balance + record config
                if self._tick_count % 60 == 0 and self._balance and self._trades:
                    recent_profits = [t.profit_usd for t in list(self._trades)[-100:]]
                    avg_profit = sum(recent_profits) / len(recent_profits)
                    self._balance._estimated_profit_per_trade = max(0.005, avg_profit)
                if self._adaptive_mode and self._tick_count % 300 == 0 and self._tick_count > 0:
                    self.record_config_snapshot("adaptive_update")

        rows.sort(key=lambda r: r[7], reverse=True)

        # Periodic monitor status summary (every N ticks)
        if self._tick_count % self._summary_interval == 0 and self._tick_count > 0:
            syms = ", ".join(self._symbols) if self._symbols else "none"
            # Per-symbol score/multiplier breakdown
            sym_details = []
            if self._optimizer:
                for s in self._symbols:
                    sc = self._optimizer.get_symbol_score(s)
                    if sc:
                        sym_details.append(
                            f"{s}(score={sc.score:.4f} mult={sc.trade_multiplier:.1f} "
                            f"tier={sc.focus_tier})"
                        )
            sym_info = " | ".join(sym_details) if sym_details else syms
            notional_part = f" notional_reject={self._interval_notional_skips}" if self._interval_notional_skips else ""
            logger.info(
                f"[Monitor] Status @{self._tick_count}s: "
                f"profitable={self._interval_profitable} "
                f"executed={self._interval_executed} "
                f"skip_size={self._interval_size_skips} "
                f"skip_balance={self._interval_balance_skips} "
                f"low_profit={self._low_profit_skips}"
                f"{notional_part} | {sym_info}"
            )
            # Reset interval counters
            self._interval_profitable = 0
            self._interval_size_skips = 0
            self._interval_balance_skips = 0
            self._interval_executed = 0
            self._interval_notional_skips = 0

        # 5-minute periodic snapshots: balance + session P&L
        if self._tick_count % 300 == 0 and self._tick_count > 0 and self._balance and self._balance.initialized:
            prices = self._get_current_prices()
            parts = []
            total = 0.0
            for ex in sorted(self._balance._exchanges):
                ex_usdt = self._balance.usdt.get(ex, 0.0)
                ex_crypto = sum(
                    qty * prices.get(sym, 0.0)
                    for sym, qty in self._balance.crypto.get(ex, {}).items()
                    if qty > 0
                )
                ex_total = ex_usdt + ex_crypto
                total += ex_total
                parts.append(f"{ex}=${ex_total:.0f}")
            ext_fees_snap = self._balance.total_external_transfer_fees
            total_fees_snap = self._balance.total_transfer_fees
            logger.info(
                f"[Balance] Snapshot: {' '.join(parts)} | total=${total:.0f} "
                f"| fees: ${total_fees_snap:.2f} (ext=${ext_fees_snap:.2f})"
            )

            # Session P&L summary
            elapsed = time.time() - self._start_time if self._start_time else 0
            hours = elapsed / 3600
            minutes = int(elapsed // 60)
            h, m = divmod(minutes, 60)
            trade_count = len(self._trades)
            trading_pnl = sum(t.profit_usd for t in self._trades)
            xfer_fees = self._balance.total_transfer_fees
            ext_fees = self._balance.total_external_transfer_fees
            credited_cb = (
                self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
            )
            pending_cb = (
                self._fee_manager._total_pending_cashback if self._fee_manager else 0.0
            )
            net = trading_pnl - xfer_fees + credited_cb
            hourly = net / hours if hours > 0 else 0.0
            ref_earn = (
                self._fee_manager._total_referrer_earnings
                if self._fee_manager
                else 0.0
            )
            size_zero_total = sum(self._size_zero_log_count.values())
            rebal_blocked_total = sum(self._rebalance_block_log_count.values())
            logger.info(
                f"[Session] {h}h{m:02d}m: {trade_count} trades, "
                f"pnl=${trading_pnl:.2f}, xfer_fees=${xfer_fees:.2f}, "
                f"cashback=${credited_cb + pending_cb:.2f} "
                f"(credited=${credited_cb:.2f} pending=${pending_cb:.2f}), "
                f"net=${net:.2f}, $/hr=${hourly:.2f}, "
                f"ref_earn=${ref_earn:.2f}, "
                f"sz0={size_zero_total}, rebal_blocked={rebal_blocked_total}, "
                f"phantom={self._phantom_spread_count}, "
                f"evd_sell={self._event_driven_seller_penalties}/demoted={self._event_driven_seller_demoted}, "
                f"one_leg={self._one_leg_sim_count}/${self._one_leg_sim_cost:.2f}, "
                f"pos_cap={self._position_cap_skips}, "
                f"anomaly={self._anomaly._total_pauses}p/{self._anomaly._total_warnings}w/{self._anomaly._total_symbol_blocks}sb"
            )
            # Demo accuracy stats (only when demo trades have been placed)
            if self._demo_trade_count > 0:
                avg_lat = self._demo_total_latency_ms / self._demo_trade_count
                avg_sim_slip = self._demo_total_sim_slippage / self._demo_trade_count
                avg_demo_slip = self._demo_total_actual_slippage / self._demo_trade_count
                drift = self._demo_total_actual_profit - self._demo_total_sim_profit
                logger.info(
                    f"[Session] demo={self._demo_fill_count}/{self._demo_trade_count}filled "
                    f"reject={self._demo_reject_count} partial={self._demo_partial_count} "
                    f"one_leg={self._demo_one_legged_count} "
                    f"profit_sim=${self._demo_total_sim_profit:.2f} "
                    f"profit_demo=${self._demo_total_actual_profit:.2f} "
                    f"drift=${drift:+.2f} "
                    f"avg_slip_sim={avg_sim_slip:.4f}% avg_slip_demo={avg_demo_slip:.4f}% "
                    f"fee_mismatch={self._demo_fee_mismatches} "
                    f"latency_avg={avg_lat:.0f}ms "
                    f"reject_suppressed={sum(max(0, v - 1) for v in self._demo_reject_log.values())} "
                    f"demo_skipped={self._demo_skip_count}"
                )
            if self._demo_skip_pairs:
                logger.info(
                    f"[Session] demo_skip_pairs={sorted(self._demo_skip_pairs)}"
                )

        # Cleanup stale pending opportunities (spread didn't persist)
        if self._pending_opportunities:
            stale_keys = [
                k for k, v in self._pending_opportunities.items()
                if v["tick"] < self._tick_count - 1
            ]
            for k in stale_keys:
                del self._pending_opportunities[k]

        # Compute average age per exchange for display
        tick_ages: dict[str, float] = {}
        for ex, ages in tick_age_lists.items():
            tick_ages[ex] = sum(ages) / len(ages)

        self._print_table(dt, rows, tick_ages)

    def _get_current_prices(self) -> dict[str, float]:
        """Get current mid prices for all active symbols from fetcher states.

        Returns ONE price per symbol — the mid from the first active exchange
        that has live data. Used as a fallback when per-exchange prices are
        unavailable. For accurate per-position MTM, prefer
        `_get_per_exchange_prices()` (v0.30.1+).
        """
        prices: dict[str, float] = {}
        for sym in self._symbols:
            for fetcher in self._fetchers:
                if fetcher.exchange_name not in self._active_exchanges:
                    continue
                state = fetcher.get_state()
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        mid = (float(ps.bid) + float(ps.ask)) / 2.0
                        if mid > 0:
                            prices[sym] = mid
                            break
                    except (ValueError, TypeError):
                        continue
        return prices

    def _get_per_exchange_prices(self) -> dict[str, dict[str, float]]:
        """Get current mid prices per (exchange, symbol).

        Returns `{exchange: {symbol: mid_price}}`. Used by
        `BalanceTracker.get_portfolio_value()` to MTM crypto held on each
        exchange against THAT exchange's actual price — not against the
        first-fetcher's price as a global proxy.

        Eliminates cross-exchange spot-price dispersion error from MTM
        (Fix A). Per-exchange spreads are typically 0.05–0.5% — small per
        position but adds up across multiple holdings.
        """
        per_ex: dict[str, dict[str, float]] = {}
        for fetcher in self._fetchers:
            ex_name = fetcher.exchange_name
            if ex_name not in self._active_exchanges:
                continue
            state = fetcher.get_state()
            ex_prices: dict[str, float] = {}
            for sym in self._symbols:
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        mid = (float(ps.bid) + float(ps.ask)) / 2.0
                        if mid > 0:
                            ex_prices[sym] = mid
                    except (ValueError, TypeError):
                        continue
            if ex_prices:
                per_ex[ex_name] = ex_prices
        return per_ex

    def _print_table(self, dt: datetime,
                     rows: list[tuple[str, str, float, str, float, float, float, float, float]],
                     tick_ages: dict[str, float] | None = None) -> None:
        """Print the live arbitrage + simulation table.

        v0.31.0-beta+: legacy single-config console-table display from
        the pre-dashboard era. In multi-config mode (`_log_file` is None)
        the orchestrator runs 48+ configs and all that output would flood
        stdout every tick. Short-circuit early to avoid both the print
        AND the string-building work.
        """
        if not self._log_file:
            return
        total_profit = sum(t.profit_usd for t in self._trades)
        total_trades = len(self._trades)

        lines: list[str] = []
        connected = sum(
            1 for f in self._fetchers
            if f._ws_connected and f.exchange_name in self._active_exchanges
        )
        active_count = len(self._active_exchanges)
        skipped = self._balance.skipped_trades if self._balance else 0
        lines.append(
            f"\n[{dt.strftime('%H:%M:%S')}] "
            f"{connected}/{active_count} ex | "
            f"{total_trades} trades | "
            f"{skipped} skip | "
            f"P&L ${total_profit:+.4f}"
        )

        # Only show stale exchanges
        if tick_ages:
            stale = [
                f"{ex} {tick_ages[ex]:.0f}s"
                for f in self._fetchers
                if (ex := f.exchange_name) in tick_ages and tick_ages[ex] > MAX_DATA_AGE_SECONDS
            ]
            if stale:
                lines.append(f"  STALE: {', '.join(stale)}")

        # Balance summary line
        if self._balance and self._balance.initialized:
            prices = self._get_current_prices()
            for bl in self._balance.get_balance_lines(prices):
                lines.append(bl)

        if not rows:
            lines.append("  (waiting for data...)")
        else:
            for sym, buy_ex, _, sell_ex, _, spread, fee, net, profit in rows:
                marker = " <--" if net > 0 else ""
                lines.append(
                    f"  {sym:<10} {buy_ex:>7}>{sell_ex:<7} "
                    f"{spread:>+.4f}% -{fee:.3f}% ={net:>+.4f}% ${profit:+.4f}{marker}"
                )

        self._output("\n".join(lines))

    # ── Summary Report ──────────────────────────────────────────────────

    def print_summary(self) -> None:
        """Print discovery report. Called on shutdown."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        minutes = elapsed / 60
        total_trades = len(self._trades)
        trading_pnl = sum(t.profit_usd for t in self._trades)
        transfer_fees = self._balance.total_transfer_fees if self._balance else 0.0

        lines: list[str] = []
        lines.append(f"\n=== REPORT ({minutes:.1f}min, {self._tick_count} ticks) ===")
        lines.append(
            f"  {len(self._symbols)} symbols, {len(self._fetchers)} exchanges, "
            f"{total_trades} trades ({total_trades / minutes:.1f}/min)"
            if minutes > 0 else
            f"  {len(self._symbols)} symbols, {len(self._fetchers)} exchanges, {total_trades} trades"
        )
        lines.append(
            f"  P&L: ${trading_pnl:+.4f} trading, "
            f"${-transfer_fees:+.4f} fees, "
            f"${trading_pnl - transfer_fees:+.4f} net"
        )
        if self._low_profit_skips > 0:
            lines.append(f"  Low-profit skips: {self._low_profit_skips}")

        self._section_symbol_ranking_net(lines)
        self._section_exchange_pair_ranking(lines)
        self._section_top_trades(lines)
        if self._balance:
            self._section_balance_overview(lines)
        if self._balance:
            self._section_transfer_log(lines)

        self._output("\n".join(lines))

    # Removed sections: exchange spreads, data freshness, trade projections
    # (redundant with net rankings and XLSX export)

    def _section_symbol_ranking_net(self, lines: list[str]) -> None:
        """Symbol ranking sorted by net profit (fees included)."""
        lines.append(f"\n--- Symbols (net profit) ---")

        # Aggregate per symbol from trades
        sym_data: dict[str, list[SimulatedTrade]] = defaultdict(list)
        for t in self._trades:
            sym_data[t.symbol].append(t)

        if not sym_data:
            lines.append("  (no profitable trades detected)")
            return

        # Sort by total net_pct sum (= total profit potential)
        ranked = sorted(
            sym_data.items(),
            key=lambda x: sum(t.net_pct for t in x[1]),
            reverse=True,
        )

        for rank, (sym, trades) in enumerate(ranked, 1):
            n = len(trades)
            total_net = sum(t.net_pct for t in trades)
            avg_net = total_net / n
            best_net = max(t.net_pct for t in trades)
            p100 = total_net / 100 * self._trade_amount
            lines.append(
                f"  {rank}. {sym:<10} {n} trades, avg {avg_net:+.4f}%, "
                f"best {best_net:+.4f}%, P&L ${p100:+.4f}"
            )

        # Show symbols with 0 trades
        zero = [s for s in self._symbols if s not in sym_data]
        if zero:
            lines.append(f"  No trades: {', '.join(zero[:15])}")

    def _section_exchange_pair_ranking(self, lines: list[str]) -> None:
        """Rank buy@X -> sell@Y exchange pair combinations."""
        lines.append(f"\n--- Exchange pairs ---")

        # Aggregate from trades
        pair_data: dict[tuple[str, str], list[float]] = defaultdict(list)
        for t in self._trades:
            pair_data[(t.buy_exchange, t.sell_exchange)].append(t.net_pct)

        if not pair_data:
            lines.append("  (no profitable trades detected)")
            return

        ranked = sorted(
            pair_data.items(),
            key=lambda x: sum(x[1]),
            reverse=True,
        )

        for rank, ((buy_ex, sell_ex), nets) in enumerate(ranked, 1):
            n = len(nets)
            total_net = sum(nets)
            avg_net = total_net / n
            p = total_net / 100 * self._trade_amount
            lines.append(
                f"  {rank}. {buy_ex}>{sell_ex} {n} trades, avg {avg_net:+.4f}%, P&L ${p:+.4f}"
            )

    def _section_top_trades(self, lines: list[str]) -> None:
        """Top 10 most profitable individual trades."""
        if not self._trades:
            return

        lines.append(f"\n--- Top 10 trades ---")
        top = sorted(self._trades, key=lambda t: t.net_pct, reverse=True)[:10]
        for t in top:
            trade_dt = datetime.fromtimestamp(t.timestamp, tz=LOCAL_TZ)
            p = t.net_pct / 100 * t.trade_amount
            lines.append(
                f"  {trade_dt.strftime('%H:%M:%S')} {t.symbol:<10} "
                f"{t.buy_exchange}>{t.sell_exchange} "
                f"net {t.net_pct:+.4f}% ${p:+.4f}"
            )

    def _section_balance_overview(self, lines: list[str]) -> None:
        """Show final balance state across all exchanges."""
        if not self._balance:
            return

        prices = self._get_current_prices()
        lines.append(f"\n--- Balances ---")

        grand_total = 0.0
        for ex in self._balance._exchanges:
            usdt = self._balance.usdt[ex]
            ex_total = usdt
            crypto_parts = []
            for sym in self._balance._symbols:
                qty = self._balance.crypto[ex].get(sym, 0.0)
                val = qty * prices.get(sym, 0.0)
                ex_total += val
                if val >= 0.01:
                    crypto_parts.append(f"{sym.replace('USDT', '')} ${val:.2f}")
            grand_total += ex_total
            crypto_str = f" + {', '.join(crypto_parts)}" if crypto_parts else ""
            lines.append(f"  {ex:<8} ${usdt:.2f} USDT{crypto_str} = ${ex_total:.2f}")

        initial = self._balance._initial_investment
        trading_pnl = sum(t.profit_usd for t in self._trades)
        transfer_fees = self._balance.total_transfer_fees
        lines.append(
            f"  Total: ${grand_total:.2f} (init ${initial:.0f}, "
            f"trade ${trading_pnl:+.4f}, fees ${-transfer_fees:+.4f}, "
            f"net ${grand_total - initial:+.4f})"
        )
        if self._balance.skipped_trades > 0:
            lines.append(f"  Skipped: {self._balance.skipped_trades} (insufficient balance)")

    def _section_transfer_log(self, lines: list[str]) -> None:
        """Show transfer/rebalancing summary."""
        if not self._balance:
            return

        lines.append(f"\n--- Transfers ---")

        transfers = self._balance.transfers
        if not transfers:
            lines.append("  None")
            return

        # Aggregate by type
        by_type: dict[str, list] = defaultdict(list)
        for t in transfers:
            by_type[t.transfer_type].append(t)

        type_labels = {
            "internal_sell": "Int sell",
            "internal_buy": "Int buy",
            "external_usdt": "Ext USDT",
            "external_crypto": "Ext crypto",
        }
        for ttype, label in type_labels.items():
            group = by_type.get(ttype, [])
            if group:
                total_fee = sum(t.fee_usd for t in group)
                lines.append(f"  {label}: {len(group)}, fees ${total_fee:.4f}")
        lines.append(
            f"  Total: {len(transfers)} transfers, ${self._balance.total_transfer_fees:.4f} fees"
        )

    # ── State persistence ────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize all mutable session state."""
        from dataclasses import asdict

        return {
            "trades": [asdict(t) for t in self._trades],
            "config_history": [asdict(c) for c in self._config_history],
            "_cumulative_pnl": self._cumulative_pnl,
            "_cumulative_trade_count": self._cumulative_trade_count,
            "_tick_count": self._tick_count,
            "_start_time": self._start_time,
            "_miss_streak": dict(self._miss_streak),
            "_low_profit_skips": self._low_profit_skips,
            "_stale_skips": dict(self._stale_skips),
            "_fresh_samples": dict(self._fresh_samples),
            "_depth_skips": self._depth_skips,
            "_notional_skips": self._notional_skips,
            "_exchange_age_sum": dict(self._exchange_age_sum),
            "_exchange_age_max": dict(self._exchange_age_max),
            "_exchange_age_count": dict(self._exchange_age_count),
            "_exchange_spread_sum": dict(self._exchange_spread_sum),
            "_exchange_spread_max": dict(self._exchange_spread_max),
            "_exchange_spread_count": dict(self._exchange_spread_count),
            "_execution_mode": self._execution_mode,
            "demo_executor": self._executor.to_state_dict() if self._executor else None,
            "_hourly_pnl": self._hourly_pnl,
            "_daily_pnl": self._daily_pnl,
            # Simulation realism counters
            "_phantom_spread_count": self._phantom_spread_count,
            "_event_driven_seller_penalties": self._event_driven_seller_penalties,
            "_event_driven_seller_demoted": self._event_driven_seller_demoted,
            "_one_leg_sim_count": self._one_leg_sim_count,
            "_one_leg_sim_cost": self._one_leg_sim_cost,
            "_position_cap_skips": self._position_cap_skips,
            # Anomaly protection
            "_anomaly": self._anomaly.to_state_dict(),
            "_manual_stopped": self._manual_stopped,
            "_manual_stop_timestamp": self._manual_stop_timestamp,
            # Demo accuracy stats
            "_demo_trade_count": self._demo_trade_count,
            "_demo_fill_count": self._demo_fill_count,
            "_demo_reject_count": self._demo_reject_count,
            "_demo_partial_count": self._demo_partial_count,
            "_demo_one_legged_count": self._demo_one_legged_count,
            "_demo_total_sim_profit": self._demo_total_sim_profit,
            "_demo_total_actual_profit": self._demo_total_actual_profit,
            "_demo_total_sim_slippage": self._demo_total_sim_slippage,
            "_demo_total_actual_slippage": self._demo_total_actual_slippage,
            "_demo_total_latency_ms": self._demo_total_latency_ms,
            "_demo_fee_mismatches": self._demo_fee_mismatches,
            # Demo setup
            "_demo_setup_complete": self._demo_setup_complete,
            "_demo_skip_pairs": list(self._demo_skip_pairs),
            "_demo_skip_count": self._demo_skip_count,
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore session state from a saved dict."""
        # Bounded deque(maxlen=5000) — old state files may have lists
        # longer than this; the deque drops the oldest automatically.
        loaded_trades = [SimulatedTrade(**t) for t in data.get("trades", [])]
        self._trades = deque(loaded_trades, maxlen=5000)
        # Restore aggregates if present (post-v0.31 state files); fall
        # back to recomputing from the loaded trades for older files
        # (the count is exact for trades currently in the deque, but
        # the cumulative pnl is approximate when older trades were
        # already evicted before the upgrade).
        if "_cumulative_pnl" in data:
            self._cumulative_pnl = float(data["_cumulative_pnl"])
            self._cumulative_trade_count = int(data.get("_cumulative_trade_count", len(self._trades)))
        else:
            self._cumulative_pnl = sum(t.profit_usd for t in self._trades)
            self._cumulative_trade_count = len(self._trades)
        self._config_history = deque(
            (ConfigSnapshot(**c) for c in data.get("config_history", [])),
            maxlen=500,
        )
        self._tick_count = data.get("_tick_count", 0)
        self._start_time = data.get("_start_time", 0.0)
        self._miss_streak = data.get("_miss_streak", {})
        self._low_profit_skips = data.get("_low_profit_skips", 0)
        self._stale_skips = defaultdict(int, data.get("_stale_skips", {}))
        self._fresh_samples = defaultdict(int, data.get("_fresh_samples", {}))
        self._depth_skips = data.get("_depth_skips", 0)
        self._notional_skips = data.get("_notional_skips", 0)
        self._exchange_age_sum = defaultdict(float, data.get("_exchange_age_sum", {}))
        self._exchange_age_max = defaultdict(float, data.get("_exchange_age_max", {}))
        self._exchange_age_count = defaultdict(int, data.get("_exchange_age_count", {}))
        self._exchange_spread_sum = defaultdict(
            float, data.get("_exchange_spread_sum", {})
        )
        self._exchange_spread_max = defaultdict(
            float, data.get("_exchange_spread_max", {})
        )
        self._exchange_spread_count = defaultdict(
            int, data.get("_exchange_spread_count", {})
        )
        self._hourly_pnl = data.get("_hourly_pnl", {})
        self._daily_pnl = data.get("_daily_pnl", {})
        # Simulation realism counters
        self._phantom_spread_count = data.get("_phantom_spread_count", 0)
        self._event_driven_seller_penalties = data.get("_event_driven_seller_penalties", 0)
        self._event_driven_seller_demoted = data.get("_event_driven_seller_demoted", 0)
        self._one_leg_sim_count = data.get("_one_leg_sim_count", 0)
        self._one_leg_sim_cost = data.get("_one_leg_sim_cost", 0.0)
        self._position_cap_skips = data.get("_position_cap_skips", 0)
        # Anomaly protection — pass current configured capital so the load
        # can detect operator-changed capital and reset stale peak.
        if "_anomaly" in data:
            self._anomaly.from_state_dict(
                data["_anomaly"],
                current_total_capital=float(self._total_capital or 0.0),
            )
            if self._anomaly._paused:
                # Reset pause timestamp to now so cooldown re-starts from this
                # boot — gives the system time to collect fresh data before
                # auto-resume rather than resuming instantly on stale state.
                self._anomaly._pause_timestamp = time.time()
                logger.warning(
                    f"[Anomaly] Restored paused state on startup "
                    f"(layer={self._anomaly._pause_layer}, "
                    f"reason={self._anomaly._pause_reason}) — "
                    f"cooldown restarted, will auto-resume when conditions clear"
                )
        self._manual_stopped = data.get("_manual_stopped", False)
        self._manual_stop_timestamp = data.get("_manual_stop_timestamp", 0.0)
        # Demo accuracy stats
        self._demo_trade_count = data.get("_demo_trade_count", 0)
        self._demo_fill_count = data.get("_demo_fill_count", 0)
        self._demo_reject_count = data.get("_demo_reject_count", 0)
        self._demo_partial_count = data.get("_demo_partial_count", 0)
        self._demo_one_legged_count = data.get("_demo_one_legged_count", 0)
        self._demo_total_sim_profit = data.get("_demo_total_sim_profit", 0.0)
        self._demo_total_actual_profit = data.get("_demo_total_actual_profit", 0.0)
        self._demo_total_sim_slippage = data.get("_demo_total_sim_slippage", 0.0)
        self._demo_total_actual_slippage = data.get("_demo_total_actual_slippage", 0.0)
        self._demo_total_latency_ms = data.get("_demo_total_latency_ms", 0.0)
        self._demo_fee_mismatches = data.get("_demo_fee_mismatches", 0)
        # Demo setup
        self._demo_setup_complete = data.get("_demo_setup_complete", False)
        self._demo_skip_pairs = set(data.get("_demo_skip_pairs", []))
        self._demo_skip_count = data.get("_demo_skip_count", 0)
