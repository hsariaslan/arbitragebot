"""
Cross-exchange arbitrage monitor with trade simulation.

Reads live price state from all registered fetchers, compares prices
across exchanges, simulates trades when profitable after fees, and
tracks cumulative P&L. Prints a comprehensive discovery report on shutdown.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=3))  # UTC+3
from typing import TYPE_CHECKING

from balance import BalanceTracker
from config import (
    ACTIVE_EXCHANGES,
    ACTIVE_SYMBOLS,
    MAX_DATA_AGE_SECONDS,
    MONITOR_INTERVAL_SECONDS,
    TRADE_AMOUNT_USD,
)

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager
    from executor import DemoExecutor
    from fee_manager import FeeManager
    from fetchers.base import BaseFetcher
    from optimizer import SymbolOptimizer
    from state_manager import StateManager

logger = logging.getLogger(__name__)



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
    min_misses_before_rebalance: int = 5


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
    # Demo execution results (Phase 2: populated when execution_mode=demo)
    demo_buy_price: float = 0.0
    demo_sell_price: float = 0.0
    demo_buy_qty: float = 0.0
    demo_sell_qty: float = 0.0
    demo_profit_usd: float = 0.0
    demo_latency_ms: float = 0.0
    demo_slippage_pct: float = 0.0
    demo_status: str = ""  # "filled", "partial", "rejected", "one_legged"


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
        min_misses_before_rebalance: int = 5,
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

        self._optimizer: "SymbolOptimizer | None" = None
        self._trades: list[SimulatedTrade] = []
        self._low_profit_skips: int = 0
        self._start_time: float = 0.0
        self._tick_count: int = 0

        # Configuration history tracking
        self._config_history: list[ConfigSnapshot] = []

        # Consecutive miss tracking: only rebalance after N consecutive
        # profitable ticks that couldn't execute due to insufficient balance.
        # Key: "sym:buy_ex:sell_ex" → consecutive miss count
        self._miss_streak: dict[str, int] = {}
        self._min_misses_before_rebalance: int = min_misses_before_rebalance

        # Track all spread observations (even non-profitable) per symbol
        # Each entry: (spread_pct, fee_pct, net_pct, buy_ex, sell_ex)
        self._all_observations: list[tuple[str, float, float, float, str, str]] = []

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

        # Phase 2: Demo execution
        self._executor: "DemoExecutor | None" = None
        self._execution_mode: str = "simulation"
        self._state_mgr: "StateManager | None" = None
        self._demo_fetcher = None  # set via set_executor()

    def set_optimizer(self, optimizer: "SymbolOptimizer") -> None:
        """Store optimizer reference for score-based rebalance gating."""
        self._optimizer = optimizer

    def set_executor(
        self,
        executor: "DemoExecutor",
        state_mgr: "StateManager",
        demo_fetcher=None,
    ) -> None:
        """Enable demo execution mode with the given executor."""
        self._executor = executor
        self._execution_mode = "demo"
        self._state_mgr = state_mgr
        self._demo_fetcher = demo_fetcher
        logger.info(
            f"[Monitor] Demo execution enabled for: "
            f"{executor.supported_exchanges}"
        )

    def _output(self, text: str) -> None:
        """Print to console and append to log file."""
        print(text)
        if self._log_file:
            with open(self._log_file, "a") as f:
                f.write(text + "\n")

    def get_net_profit_stats(self) -> dict:
        """Compute rolling hourly net profit stats."""
        now = time.time()
        elapsed_hours = max((now - self._start_time) / 3600, 1 / 3600) if self._start_time else 1 / 3600

        trading_pnl = sum(t.profit_usd for t in self._trades)
        transfer_fees = self._balance.total_transfer_fees if self._balance else 0.0
        credited_cashback = (
            self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
        )
        pending_cashback = (
            self._fee_manager._total_pending_cashback if self._fee_manager else 0.0
        )
        net_profit = trading_pnl - transfer_fees + credited_cashback

        # Rolling 1-hour window
        one_hour_ago = now - 3600
        recent_profit = sum(t.profit_usd for t in self._trades if t.timestamp >= one_hour_ago)
        recent_fees = sum(
            tr.fee_usd for tr in (self._balance.transfers if self._balance else [])
            if tr.timestamp >= one_hour_ago
        )

        hourly_net = recent_profit - recent_fees
        session_hourly_rate = net_profit / elapsed_hours

        return {
            "net_profit": round(net_profit, 4),
            "hourly_net": round(hourly_net, 4),
            "session_hourly_rate": round(session_hourly_rate, 4),
            "trading_pnl": round(trading_pnl, 4),
            "transfer_fees": round(transfer_fees, 4),
            "credited_cashback": round(credited_cashback, 4),
            "pending_cashback": round(pending_cashback, 4),
            "is_profitable": net_profit > 0,
        }

    def _should_rebalance(self, buy_ex: str, sell_ex: str) -> tuple[bool, str]:
        """Check if rebalancing is worthwhile based on ROI and net P&L.

        Returns (allowed, reason). reason is non-empty only when blocked.
        """
        if not self._balance or not self._adaptive_mode:
            return True, ""

        # Block when net P&L is negative (after warm-up period)
        if len(self._trades) >= 10:
            trading_pnl = sum(t.profit_usd for t in self._trades)
            credited_cb = (
                self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
            )
            total_fees = self._balance.total_transfer_fees
            if trading_pnl + credited_cb < total_fees:
                return False, (
                    f"net_pnl_gate (pnl=${trading_pnl:.2f} + cb=${credited_cb:.2f} "
                    f"< fees=${total_fees:.2f})"
                )

        # ROI gate: profit margin vs amortized rebalance cost
        # Internal rebalance costs a single taker fee on one exchange;
        # external transfers have flat fees gated separately in try_rebalance().
        # Compare as percentages to avoid trade-amount sensitivity.
        if self._balance._estimated_profit_per_trade > 0 and self._trade_amount > 0:
            profit_pct = self._balance._estimated_profit_per_trade / self._trade_amount
            fee_rate = self._fee_manager.get_taker_fee(buy_ex) if self._fee_manager else 0.001
            threshold = fee_rate / 3
            # Rebalance enables ~3 trades; cost amortized = fee_rate / 3
            if profit_pct < threshold:
                return False, (
                    f"roi_gate (profit_pct={profit_pct * 100:.4f}% "
                    f"< threshold={threshold * 100:.4f}%)"
                )

        return True, ""

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

        # Max by available USDT on buy exchange (keep 20% buffer)
        usdt_available = self._balance.usdt.get(buy_ex, 0.0)
        max_by_usdt = usdt_available * 0.80

        # Max by available crypto value on sell exchange (keep 20% buffer)
        crypto_qty = self._balance.crypto.get(sell_ex, {}).get(symbol, 0.0)
        crypto_value = crypto_qty * sell_price
        max_by_crypto = crypto_value * 0.80

        # Tick quality factor (narrow range — symbol_mult does the heavy lifting)
        if net_pct >= 0.10:
            tick_factor = 1.0
        elif net_pct >= 0.05:
            tick_factor = 0.90
        else:
            tick_factor = 0.85

        # Capital-proportional floor
        min_trade = max(5.0, self._total_capital * 0.003)

        base = self._trade_amount * symbol_mult * tick_factor
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
        recent = self._trades[-100:] if self._trades else []
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
        Records discrepancies (D-08 through D-13) and saves state immediately.
        """
        if not self._executor:
            return

        try:
            result = await self._executor.execute_arbitrage(
                buy_ex, sell_ex, symbol, trade_size,
                buy_price, sell_price, buy_qty, sell_qty,
            )

            # Update the SimulatedTrade with demo results
            self._record_demo_comparison(sim_trade, result)

            # Immediate state save (crash safety for real trades)
            if self._state_mgr and self._balance and self._optimizer:
                self._state_mgr.save(
                    self._balance, self, self._optimizer, self._demo_fetcher,
                )

        except Exception as e:
            logger.error(f"[Monitor] Demo trade execution failed: {e}")

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

        # D-10: Rejection
        if not buy.success:
            logger.warning(
                f"[D-10] {sym} buy rejected on {buy.exchange}: {buy.error}"
            )
        if not sell.success:
            logger.warning(
                f"[D-10] {sym} sell rejected on {sell.exchange}: {sell.error}"
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

        # Profit comparison
        profit_diff = result.actual_profit_usd - sim_trade.profit_usd
        if abs(profit_diff) > 0.01:
            logger.info(
                f"[DemoCompare] {sym} profit: sim=${sim_trade.profit_usd:.4f} "
                f"actual=${result.actual_profit_usd:.4f} diff=${profit_diff:+.4f}"
            )

    def stop(self) -> None:
        """Signal the monitor to stop."""
        self._running = False

    def update_symbols(self, symbols: list[str]) -> None:
        """Update active symbols list (called by SymbolOptimizer)."""
        self._symbols = list(symbols)
        logger.info(f"[Monitor] Symbols updated: {symbols}")

    def reset(
        self,
        symbols: list[str] | None = None,
        exchanges: list[str] | None = None,
        trade_amount: float | None = None,
        balance: BalanceTracker | None = None,
        min_net_profit_pct: float | None = None,
        rebalance_roi_horizon: int | None = None,
    ) -> None:
        """Reset simulation state, optionally with new configuration."""
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

        self._trades.clear()
        self._all_observations.clear()
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
        self._tick_count = 0
        self._start_time = time.time()
        logger.info(
            f"[Monitor] Reset: {len(self._symbols)} symbols, "
            f"{len(self._active_exchanges)} exchanges, ${self._trade_amount}/trade"
        )

    async def run(self) -> None:
        """Main loop: periodically scan prices, simulate trades, print table."""
        self._running = True
        if not self._start_time:
            self._start_time = time.time()
        exchange_names = [f.exchange_name for f in self._fetchers]
        logger.info(
            f"[Monitor] Starting simulation: {', '.join(exchange_names)} "
            f"| {len(self._symbols)} symbols | ${self._trade_amount} per trade"
        )

        while self._running:
            if not self._paused:
                self._tick()
            await asyncio.sleep(MONITOR_INTERVAL_SECONDS)

        logger.info("[Monitor] Simulation stopped")

    def _tick(self) -> None:
        """One simulation tick: scan prices, simulate trades, print."""
        now = time.time()
        dt = datetime.fromtimestamp(now, tz=LOCAL_TZ)
        self._tick_count += 1

        # Initialize balance tracker as soon as prices are available
        if self._balance and not self._balance.initialized:
            self._balance.initialize_crypto(self._get_current_prices())

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

        for symbol in self._symbols:
            exchange_prices: list[tuple[str, float, float]] = []
            # Per-exchange data age for this symbol (for trade metadata)
            symbol_ex_age: dict[str, float] = {}

            for fetcher in self._fetchers:
                if fetcher.exchange_name not in self._active_exchanges:
                    continue
                state = fetcher.get_state()
                ps = state.get(symbol)
                if ps is None or not ps.bid or not ps.ask:
                    continue

                # Check data freshness
                if ps.received_at > 0:
                    age = now - ps.received_at
                    symbol_ex_age[fetcher.exchange_name] = age
                    tick_age_lists[fetcher.exchange_name].append(age)

                    # Track running stats for summary report
                    self._exchange_age_sum[fetcher.exchange_name] += age
                    self._exchange_age_count[fetcher.exchange_name] += 1
                    if age > self._exchange_age_max[fetcher.exchange_name]:
                        self._exchange_age_max[fetcher.exchange_name] = age

                    # Skip stale data
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

                # D-03: Round prices to tick size (corrects float imprecision)
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

                # Compute depth in USD at best bid/ask
                try:
                    bid_qty_f = float(ps.bid_qty) if ps.bid_qty else 0.0
                    ask_qty_f = float(ps.ask_qty) if ps.ask_qty else 0.0
                except (ValueError, TypeError):
                    bid_qty_f = 0.0
                    ask_qty_f = 0.0

                bid_depth = bid_f * bid_qty_f if bid_qty_f > 0 else float("inf")
                ask_depth = ask_f * ask_qty_f if ask_qty_f > 0 else float("inf")

                exchange_prices.append((fetcher.exchange_name, bid_f, ask_f, bid_depth, ask_depth))

            if len(exchange_prices) < 2:
                continue

            # Track per-exchange internal spread (bid-ask on same exchange)
            for ex_name, ex_bid, ex_ask, _, _ in exchange_prices:
                if ex_bid > 0:
                    internal_spread = (ex_ask - ex_bid) / ex_bid * 100
                    self._exchange_spread_sum[ex_name] += internal_spread
                    self._exchange_spread_count[ex_name] += 1
                    if internal_spread > self._exchange_spread_max[ex_name]:
                        self._exchange_spread_max[ex_name] = internal_spread

            best_scoring_net = float("-inf")
            best_row = None

            for i, (ex_buy, _, ask_i, _, ask_depth_i) in enumerate(exchange_prices):
                for j, (ex_sell, bid_j, _, bid_depth_j, _) in enumerate(exchange_prices):
                    if i == j:
                        continue

                    # Skip if insufficient depth (use min_trade as threshold)
                    min_depth = max(5.0, self._total_capital * 0.003) if self._adaptive_mode else self._trade_amount
                    if ask_depth_i < min_depth or bid_depth_j < min_depth:
                        self._depth_skips += 1
                        continue

                    spread_pct = (bid_j - ask_i) / ask_i * 100

                    # Scoring fees for pair selection (includes cashback weighting)
                    s_buy = self._fee_manager.get_scoring_fee(ex_buy, symbol) if self._fee_manager else 0.001
                    s_sell = self._fee_manager.get_scoring_fee(ex_sell, symbol) if self._fee_manager else 0.001
                    scoring_net = spread_pct - (s_buy + s_sell) * 100

                    # Taker fees for profit calculation (actual fee charged)
                    t_buy = self._fee_manager.get_taker_fee(ex_buy, symbol) if self._fee_manager else 0.001
                    t_sell = self._fee_manager.get_taker_fee(ex_sell, symbol) if self._fee_manager else 0.001
                    fee_pct = (t_buy + t_sell) * 100
                    net_pct = spread_pct - fee_pct
                    profit_usd = self._trade_amount * (net_pct / 100)

                    if scoring_net > best_scoring_net:
                        best_scoring_net = scoring_net
                        best_row = (symbol, ex_buy, ask_i, ex_sell, bid_j,
                                    spread_pct, fee_pct, net_pct, profit_usd)

            if best_row is not None:
                rows.append(best_row)
                sym, buy_ex, ask_p, sell_ex, bid_p, spread, fee, net, profit = best_row

                # Record observation (all, not just profitable)
                self._all_observations.append((sym, spread, fee, net, buy_ex, sell_ex))

                # Minimum net% threshold (scoring_net includes cashback weighting)
                pair_min_net = self._min_net_profit_pct

                # Simulate trade if profitable after cashback and above threshold
                if best_scoring_net > 0 and best_scoring_net >= pair_min_net:
                    self._interval_profitable += 1
                    can_trade = True

                    # Compute trade size (adaptive or static)
                    if self._adaptive_mode:
                        trade_size = self._compute_trade_size(
                            buy_ex, sell_ex, sym, best_scoring_net, bid_p,
                        )
                    else:
                        trade_size = self._trade_amount

                    if self._balance and self._balance.initialized:
                        # Track miss-streak for rebalancing (even when trade_size is 0)
                        if trade_size <= 0:
                            self._interval_size_skips += 1
                            miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                            streak = self._miss_streak[miss_key] = self._miss_streak.get(miss_key, 0) + 1
                            if streak <= 3 or streak % 30 == 0:
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
                                if streak <= 3 or streak % 30 == 0:
                                    logger.info(
                                        f"[Monitor] SKIP {sym} {buy_ex}->{sell_ex}: "
                                        f"insufficient balance (net={net:.4f}% size=${trade_size:.2f} "
                                        f"usdt={has_usdt} crypto={has_crypto} streak={streak})"
                                    )
                                can_trade = False

                        # Try rebalancing when miss-streak is high enough
                        miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                        if not can_trade and self._miss_streak.get(miss_key, 0) >= self._min_misses_before_rebalance:
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
                                self._balance.try_rebalance(
                                    buy_ex, sell_ex, sym, self._trade_amount, prices
                                )
                                self._miss_streak[miss_key] = 0
                            else:
                                streak = self._miss_streak.get(miss_key, 0)
                                self._rebalance_block_log_count[miss_key] += 1
                                rbl_count = self._rebalance_block_log_count[miss_key]
                                if rbl_count == 1 or rbl_count % 30 == 0:
                                    logger.info(
                                        f"[Rebalance] BLOCKED {sym} {buy_ex}->{sell_ex} "
                                        f"streak={streak}: {rebal_reason}"
                                    )

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
                        else:
                            trade_adj = None
                            self._balance.skipped_trades += 1
                    elif self._balance:
                        self._balance.skipped_trades += 1
                        can_trade = False
                        trade_adj = None

                    if can_trade:
                        self._interval_executed += 1
                        actual_profit = trade_size * (net / 100)
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
                            net_pct=net, profit_usd=actual_profit,
                            trade_amount=trade_size,
                            buy_qty_raw=adj.get("buy_qty_raw", 0.0),
                            buy_qty_rounded=adj.get("buy_qty_rounded", 0.0),
                            sell_qty_raw=adj.get("sell_qty_raw", 0.0),
                            sell_qty_rounded=adj.get("sell_qty_rounded", 0.0),
                            rounding_impact_usd=adj.get("rounding_impact_usd", 0.0),
                            data_age_ms=max_age_ms,
                        )
                        self._trades.append(trade)
                        qty = trade_size / ask_p if ask_p > 0 else 0.0
                        logger.info(
                            f"[Trade] #{len(self._trades)} {sym} {buy_ex}->{sell_ex}: "
                            f"buy@${ask_p:.4f} sell@${bid_p:.4f} qty={qty:.4f} "
                            f"size=${trade_size:.2f} profit=${actual_profit:.4f} "
                            f"(net={net:+.4f}%)"
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

                        # Phase 2: Fire demo orders in parallel (non-blocking)
                        if (self._execution_mode == "demo"
                                and self._executor
                                and self._executor.can_execute(buy_ex, sell_ex)):
                            asyncio.create_task(self._execute_demo_trade(
                                buy_ex, sell_ex, sym, trade_size,
                                ask_p, bid_p,
                                adj.get("buy_qty_rounded", trade_size / ask_p),
                                adj.get("sell_qty_rounded", trade_size / bid_p),
                                trade,
                            ))

                elif net > 0:
                    # Positive but below threshold — still track miss-streak
                    # so rebalancing can trigger for generally-profitable symbols
                    self._low_profit_skips += 1
                    if self._balance and self._balance.initialized:
                        miss_key = f"{sym}:{buy_ex}:{sell_ex}"
                        self._miss_streak[miss_key] = self._miss_streak.get(miss_key, 0) + 1

                        if self._miss_streak.get(miss_key, 0) >= self._min_misses_before_rebalance:
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
                                self._balance.try_rebalance(
                                    buy_ex, sell_ex, sym, self._trade_amount, prices
                                )
                                self._miss_streak[miss_key] = 0
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
                    recent_profits = [t.profit_usd for t in self._trades[-100:]]
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
            logger.info(f"[Balance] Snapshot: {' '.join(parts)} | total=${total:.0f}")

            # Session P&L summary
            elapsed = time.time() - self._start_time if self._start_time else 0
            hours = elapsed / 3600
            minutes = int(elapsed // 60)
            h, m = divmod(minutes, 60)
            trade_count = len(self._trades)
            trading_pnl = sum(t.profit_usd for t in self._trades)
            xfer_fees = self._balance.total_transfer_fees
            credited_cb = (
                self._fee_manager._total_credited_cashback if self._fee_manager else 0.0
            )
            pending_cb = (
                self._fee_manager._total_pending_cashback if self._fee_manager else 0.0
            )
            net = trading_pnl - xfer_fees + credited_cb
            hourly = net / hours if hours > 0 else 0.0
            logger.info(
                f"[Session] {h}h{m:02d}m: {trade_count} trades, "
                f"pnl=${trading_pnl:.2f}, xfer_fees=${xfer_fees:.2f}, "
                f"cashback=${credited_cb + pending_cb:.2f} "
                f"(credited=${credited_cb:.2f} pending=${pending_cb:.2f}), "
                f"net=${net:.2f}, $/hr=${hourly:.2f}"
            )

        # Compute average age per exchange for display
        tick_ages: dict[str, float] = {}
        for ex, ages in tick_age_lists.items():
            tick_ages[ex] = sum(ages) / len(ages)

        self._print_table(dt, rows, tick_ages)

    def _get_current_prices(self) -> dict[str, float]:
        """Get current mid prices for all active symbols from fetcher states."""
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

    def _print_table(self, dt: datetime,
                     rows: list[tuple[str, str, float, str, float, float, float, float, float]],
                     tick_ages: dict[str, float] | None = None) -> None:
        """Print the live arbitrage + simulation table."""
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
            "_tick_count": self._tick_count,
            "_start_time": self._start_time,
            "_miss_streak": dict(self._miss_streak),
            "_all_observations": self._all_observations[-100000:],
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
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore session state from a saved dict."""
        self._trades = [SimulatedTrade(**t) for t in data.get("trades", [])]
        self._config_history = [
            ConfigSnapshot(**c) for c in data.get("config_history", [])
        ]
        self._tick_count = data.get("_tick_count", 0)
        self._start_time = data.get("_start_time", 0.0)
        self._miss_streak = data.get("_miss_streak", {})
        self._all_observations = [
            tuple(obs) for obs in data.get("_all_observations", [])
        ]
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
