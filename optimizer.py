"""
Automatic symbol rotation optimizer for CoirnaBot.

Scores all 60 symbols continuously across exchanges by computing
cross-exchange spreads every second. Maintains a rolling window of scores
and periodically evaluates whether to rotate the active trading set.

Discovery stage (first 5 minutes):
  - Scores ALL symbols on ALL exchanges (unlimited money simulation)
  - Picks the best N symbols based on profitability
  - All active exchanges always participate in trading
  - Configures balance tracker and monitor, then starts trading

Rotation only fires when the expected hourly improvement exceeds the
switching cost (sell old crypto + buy new crypto fees) by a safety margin.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from config import (
    MAX_DATA_AGE_SECONDS,
    SYMBOLS,
)

if TYPE_CHECKING:
    from balance import BalanceTracker, Transfer
    from dashboard_server import DashboardServer
    from fee_manager import FeeManager
    from fetchers.base import BaseFetcher
    from monitor import ArbitrageMonitor

logger = logging.getLogger(__name__)

# Score thresholds for tiered behavior (module-level defaults)
TRADING_SCORE_THRESHOLD = 0.01     # trading + rebalance gate (minimum to trade/transfer)
STRONG_SCORE_THRESHOLD = 0.1       # strong tier (higher multiplier, more exchanges)
VERY_STRONG_SCORE_THRESHOLD = 0.3  # very strong tier (highest multiplier, most exchanges)


@dataclass
class SymbolTick:
    """Single observation of best cross-exchange opportunity for a symbol."""

    timestamp: float
    best_net_pct: float
    buy_exchange: str
    sell_exchange: str
    spread_pct: float
    fee_pct: float


@dataclass
class SymbolScore:
    """Computed score for a symbol over the rolling window."""

    symbol: str
    score: float
    avg_net_pct: float
    avg_profitable_net: float
    profitable_ticks: int
    total_ticks: int
    frequency: float
    best_net_pct: float
    est_hourly_profit: float
    rank: int = 0
    trade_multiplier: float = 1.0
    focus_tier: str = "normal"


@dataclass
class RotationEvent:
    """Record of a symbol rotation."""

    timestamp: float
    old_symbol: str
    new_symbol: str
    old_score: float
    new_score: float
    switching_cost_usd: float
    est_hourly_improvement_usd: float


@dataclass
class HistoricalSymbolStats:
    """Cumulative session-level stats for a symbol (never pruned)."""

    symbol: str
    total_profitable_ticks: int = 0
    total_ticks: int = 0
    total_net_pct_sum: float = 0.0
    total_profitable_net_sum: float = 0.0
    best_net_pct: float = 0.0
    worst_net_pct: float = 0.0
    est_total_profit: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    current_profitable_streak: int = 0
    longest_profitable_streak: int = 0
    current_unprofitable_streak: int = 0
    longest_unprofitable_streak: int = 0
    # Candidate/watchlist/activation tracking
    times_became_candidate: int = 0
    times_entered_watchlist: int = 0
    times_confirmed: int = 0
    times_activated: int = 0
    times_demoted: int = 0
    total_active_duration: float = 0.0
    last_activated_at: float = 0.0
    # Strong/very strong tier tracking
    times_became_strong: int = 0       # score crossed >= 0.1
    times_became_very_strong: int = 0  # score crossed >= 0.3
    total_strong_duration: float = 0.0
    total_very_strong_duration: float = 0.0
    last_strong_at: float = 0.0        # 0 = not currently strong
    last_very_strong_at: float = 0.0   # 0 = not currently very strong
    # Per-exchange direction tracking
    buy_exchange_counts: dict = field(default_factory=dict)
    sell_exchange_counts: dict = field(default_factory=dict)

    @property
    def overall_frequency(self) -> float:
        return self.total_profitable_ticks / self.total_ticks if self.total_ticks > 0 else 0.0

    @property
    def avg_net_pct(self) -> float:
        return self.total_net_pct_sum / self.total_ticks if self.total_ticks > 0 else 0.0

    @property
    def avg_profitable_net(self) -> float:
        return (
            self.total_profitable_net_sum / self.total_profitable_ticks
            if self.total_profitable_ticks > 0
            else 0.0
        )

    @property
    def all_time_score(self) -> float:
        return self.avg_profitable_net * self.overall_frequency


@dataclass
class HistoricalExchangeStats:
    """Cumulative session-level stats for an exchange."""

    exchange: str
    total_buy_ticks: int = 0
    total_sell_ticks: int = 0
    total_profit_sum: float = 0.0
    total_involvement: int = 0


@dataclass
class WatchlistEntry:
    """Tracks a strong candidate symbol being observed for confirmation."""

    symbol: str
    entered_at: float
    confirmation_start: float
    score_samples: list[float] = field(default_factory=list)
    confirmed: bool = False


class SymbolOptimizer:
    """
    Scores all symbols and auto-rotates the active trading set.

    On startup (if auto_rotate): runs a discovery stage that scores all symbols
    on all exchanges for discovery_duration seconds, then picks the best
    symbols and exchanges to trade.

    After discovery: continues scoring, evaluates rotation periodically.
    """

    def __init__(
        self,
        fetchers: list["BaseFetcher"],
        monitor: "ArbitrageMonitor",
        balance: "BalanceTracker",
        active_exchanges: list[str],
        active_symbols: list[str],
        all_symbols: list[str] | None = None,
        trade_amount: float = 100.0,
        total_capital: float = 1800.0,
        fee_manager: "FeeManager | None" = None,
        num_active_symbols: int = 3,
        max_active_symbols: int = 8,
        scoring_window: int = 1800,
        evaluation_interval: int = 300,
        min_warmup_ticks: int = 60,
        safety_multiplier: float = 2.0,
        auto_rotate: bool = True,
        discovery_duration: int = 300,
        min_rebalance_score: float = 0.0001,
        confirmation_period: int = 300,
        promotion_threshold: float = 0.0001,
        demotion_threshold: float = 0.0,
        demotion_period: int = 600,
        demotion_cooldown_multiplier: float = 5.0,
        reallocation_cost_horizon: float = 2.0,
    ) -> None:
        self._fetchers = fetchers
        self._monitor = monitor
        self._balance = balance
        self._active_exchanges = set(active_exchanges)
        self._active_symbols: list[str] = list(active_symbols)
        self._all_symbols: list[str] = all_symbols or SYMBOLS
        self._trade_amount = trade_amount
        self._total_capital = total_capital
        self._fee_manager = fee_manager
        self._min_active_symbols = num_active_symbols
        self._max_active_symbols = max(max_active_symbols, num_active_symbols)
        self._scoring_window = scoring_window
        self._evaluation_interval = evaluation_interval
        self._min_warmup_ticks = min_warmup_ticks
        self._safety_multiplier = safety_multiplier
        self._auto_rotate = auto_rotate
        self._discovery_duration = discovery_duration
        self._initial_discovery_duration = discovery_duration
        self._running = False

        # Score threshold for transfers (Phase 2)
        self._min_rebalance_score = min_rebalance_score

        # Watchlist / strong candidate tracking (Phase 3)
        self._watchlist: dict[str, WatchlistEntry] = {}
        self._confirmation_period = confirmation_period
        self._promotion_threshold = promotion_threshold

        # Demotion tracking (Phase 4)
        self._demotion_threshold = demotion_threshold
        self._demotion_period = demotion_period
        self._demotion_tracking: dict[str, float] = {}
        # Anti-churning: cooldown after demotion prevents immediate re-activation
        self._recently_demoted: dict[str, float] = {}  # symbol -> demotion timestamp
        self._demotion_cooldown_multiplier = demotion_cooldown_multiplier
        self._demotion_cooldown = demotion_period * demotion_cooldown_multiplier

        # Reallocation cost gate
        self._reallocation_cost_horizon = reallocation_cost_horizon

        # Configurable score thresholds (settable from dashboard)
        self._trading_threshold: float = TRADING_SCORE_THRESHOLD
        self._strong_threshold: float = STRONG_SCORE_THRESHOLD
        self._very_strong_threshold: float = VERY_STRONG_SCORE_THRESHOLD

        # Net profit awareness: block rotations when in deficit
        self._rotation_budget_ok: bool = True
        self._session_hourly_rate: float = 0.0

        # Discovery debug logging
        self._discovery_debug_last_summary: float = 0.0
        self._discovery_debug_last_detail: float = 0.0

        # Per-symbol dominant exchange pair mapping
        self._dominant_pairs: dict[str, dict] = {}
        self._last_reallocation: dict[str, float] = {}

        # Dashboard reference (set by DashboardServer.__init__)
        self._dashboard: "DashboardServer | None" = None

        # Rolling window per symbol
        self._ticks: dict[str, deque[SymbolTick]] = {
            sym: deque() for sym in self._all_symbols
        }

        # Latest computed scores
        self._scores: dict[str, SymbolScore] = {}
        self._prev_candidate_set: set[str] = set()  # for tracking candidate transitions
        self._prev_strong_set: set[str] = set()     # score >= 0.1 last tick
        self._prev_very_strong_set: set[str] = set()  # score >= 0.3 last tick

        # Rotation history
        self._rotations: list[RotationEvent] = []

        # Timing
        self._last_evaluation: float = 0.0
        self._tick_count: int = 0
        self._session_start: float = time.time()

        # Historical stats (never pruned, survive reset)
        self._historical_stats: dict[str, HistoricalSymbolStats] = {
            sym: HistoricalSymbolStats(symbol=sym) for sym in self._all_symbols
        }
        self._historical_exchange_stats: dict[str, HistoricalExchangeStats] = {}

        # Discovery state
        self._discovery_mode: bool = auto_rotate
        self._discovery_complete: bool = False
        self._discovery_start: float = 0.0

        # Discovery: track exchange profitability
        self._exchange_profit_ticks: dict[str, int] = defaultdict(int)
        self._exchange_profit_sum: dict[str, float] = defaultdict(float)

        # Discovery: track buy vs sell direction per exchange (for asymmetric allocation)
        self._exchange_buy_ticks: dict[str, int] = defaultdict(int)
        self._exchange_sell_ticks: dict[str, int] = defaultdict(int)

    def stop(self) -> None:
        self._running = False

    def set_dashboard(self, dashboard: "DashboardServer") -> None:
        """Store dashboard reference for post-discovery updates."""
        self._dashboard = dashboard

    def update_profit_state(self, net_profit: float, session_hourly_rate: float, grace_active: bool = False) -> None:
        """Called by dashboard to update net profit awareness for rotation gating."""
        was_ok = self._rotation_budget_ok
        if grace_active:
            self._rotation_budget_ok = True
        else:
            self._rotation_budget_ok = net_profit >= 0
        self._session_hourly_rate = session_hourly_rate
        # Log transitions
        if was_ok and not self._rotation_budget_ok:
            logger.info(
                f"[Optimizer] Rotation gate CLOSED: net_profit=${net_profit:.2f} "
                f"(using ext-only fees)"
            )
        elif not was_ok and self._rotation_budget_ok and not grace_active:
            logger.info(
                f"[Optimizer] Rotation gate OPENED: net_profit=${net_profit:.2f}"
            )

    async def run(self) -> None:
        """Score all symbols every second, evaluate rotation periodically."""
        self._running = True
        if not self._discovery_start:
            self._discovery_start = time.time()
        if not self._last_evaluation:
            self._last_evaluation = time.time()

        if self._discovery_mode:
            self._monitor._paused = True
            # Enable DEBUG logging during discovery
            logger.setLevel(logging.DEBUG)
            logger.info(
                f"[Optimizer] Discovery stage: scoring all "
                f"{len(self._all_symbols)} symbols on all exchanges "
                f"for {self._discovery_duration}s"
            )
        else:
            logger.info(
                f"[Optimizer] Starting: top {self._min_active_symbols} symbols from "
                f"{len(self._all_symbols)}, window={self._scoring_window}s, "
                f"eval_interval={self._evaluation_interval}s, "
                f"auto_rotate={self._auto_rotate}"
            )

        while self._running:
            self._score_tick()
            self._tick_count += 1

            now = time.time()

            # Discovery stage: check for tradeable candidates every tick, complete when duration elapses
            if self._discovery_mode and not self._discovery_complete:
                elapsed = now - self._discovery_start

                if self._tick_count >= self._min_warmup_ticks:
                    # Check every tick for tradeable candidates (>= 0.01)
                    tradeable_found = sorted(
                        [
                            s for s in self._scores.values()
                            if s.score >= self._trading_threshold and s.total_ticks > 0
                        ],
                        key=lambda s: s.score,
                        reverse=True,
                    )
                    # Early exit: at least 1 tradeable + 60s for stable scores
                    min_early_exit_time = 60.0
                    if (
                        tradeable_found
                        and elapsed >= min_early_exit_time
                    ):
                        names = ", ".join(
                            f"{s.symbol.replace('USDT', '')}({s.score:.4f})"
                            for s in tradeable_found[:5]
                        )
                        logger.info(
                            f"[Optimizer] {len(tradeable_found)} tradeable candidates "
                            f"found at {elapsed:.0f}s: {names} — exiting discovery"
                        )
                        self._complete_discovery()
                    elif elapsed >= self._discovery_duration:
                        # Duration elapsed, none found — extend discovery
                        self._complete_discovery()
            elif (
                self._auto_rotate
                and not self._discovery_mode
                and self._tick_count >= self._min_warmup_ticks
                and now - self._last_evaluation >= self._evaluation_interval
            ):
                # Post-discovery stabilization: allow rotations after 1 evaluation interval
                time_since_discovery = now - (self._discovery_start + self._discovery_duration)
                if time_since_discovery >= self._evaluation_interval:
                    self._evaluate_rotation()
                else:
                    # Still evaluate demotions only (protect against truly dead symbols)
                    self._evaluate_demotions()
                self._last_evaluation = now

            await asyncio.sleep(1.0)

    # ── Scoring ──────────────────────────────────────────────────────────

    def _score_tick(self) -> None:
        """Compute best net spread for each symbol, append to rolling window."""
        now = time.time()

        for symbol in self._all_symbols:
            exchange_prices: list[tuple[str, float, float]] = []

            for fetcher in self._fetchers:
                if fetcher.exchange_name not in self._active_exchanges:
                    continue
                state = fetcher.get_state()
                ps = state.get(symbol)
                if ps is None or not ps.bid or not ps.ask:
                    continue
                if ps.received_at > 0 and (now - ps.received_at) > MAX_DATA_AGE_SECONDS:
                    continue

                try:
                    bid_f = float(ps.bid)
                    ask_f = float(ps.ask)
                    if bid_f <= 0 or ask_f <= 0:
                        continue
                    exchange_prices.append((fetcher.exchange_name, bid_f, ask_f))
                except (ValueError, TypeError):
                    continue

            if len(exchange_prices) < 2:
                continue

            # Find best cross-exchange spread
            best_net = float("-inf")
            best_buy = ""
            best_sell = ""
            best_spread = 0.0
            best_fee = 0.0

            for i, (ex_buy, _, ask_i) in enumerate(exchange_prices):
                for j, (ex_sell, bid_j, _) in enumerate(exchange_prices):
                    if i == j:
                        continue
                    spread_pct = (bid_j - ask_i) / ask_i * 100
                    buy_fee = self._fee_manager.get_scoring_fee(ex_buy, symbol) if self._fee_manager else 0.001
                    sell_fee = self._fee_manager.get_scoring_fee(ex_sell, symbol) if self._fee_manager else 0.001
                    fee_pct = (buy_fee + sell_fee) * 100
                    net_pct = spread_pct - fee_pct

                    if net_pct > best_net:
                        best_net = net_pct
                        best_buy = ex_buy
                        best_sell = ex_sell
                        best_spread = spread_pct
                        best_fee = fee_pct

            if best_net > float("-inf"):
                tick = SymbolTick(
                    timestamp=now,
                    best_net_pct=best_net,
                    buy_exchange=best_buy,
                    sell_exchange=best_sell,
                    spread_pct=best_spread,
                    fee_pct=best_fee,
                )
                self._ticks[symbol].append(tick)
                self._update_historical_stats(symbol, tick)

                # During discovery: track exchange profitability + direction
                if self._discovery_mode and best_net > 0:
                    self._exchange_profit_ticks[best_buy] += 1
                    self._exchange_profit_ticks[best_sell] += 1
                    self._exchange_profit_sum[best_buy] += best_net
                    self._exchange_profit_sum[best_sell] += best_net
                    self._exchange_buy_ticks[best_buy] += 1
                    self._exchange_sell_ticks[best_sell] += 1

        # Discovery debug logging
        if self._discovery_mode:
            self._discovery_debug_log(now)

        # Prune old ticks
        cutoff = now - self._scoring_window
        for dq in self._ticks.values():
            while dq and dq[0].timestamp < cutoff:
                dq.popleft()

        self._compute_scores()

    def _discovery_debug_log(self, now: float) -> None:
        """Emit debug logs during discovery to diagnose low scores."""
        elapsed = now - self._discovery_start

        # Every 30s: exchange data availability + tick-level spread summary
        if now - self._discovery_debug_last_summary >= 30.0:
            self._discovery_debug_last_summary = now

            # Count how many exchanges have fresh data per symbol
            ex_data_counts: dict[str, int] = {}
            symbols_with_data = 0
            for symbol in self._all_symbols:
                count = 0
                for fetcher in self._fetchers:
                    if fetcher.exchange_name not in self._active_exchanges:
                        continue
                    state = fetcher.get_state()
                    ps = state.get(symbol)
                    if ps and ps.bid and ps.ask:
                        if ps.received_at > 0 and (now - ps.received_at) <= MAX_DATA_AGE_SECONDS:
                            count += 1
                ex_data_counts[symbol] = count
                if count >= 2:
                    symbols_with_data += 1

            # Exchange connectivity
            ex_names = []
            for fetcher in self._fetchers:
                if fetcher.exchange_name in self._active_exchanges:
                    state = fetcher.get_state()
                    fresh = sum(1 for ps in state.values()
                                if ps and ps.bid and ps.received_at > 0
                                and (now - ps.received_at) <= MAX_DATA_AGE_SECONDS)
                    ex_names.append(f"{fetcher.exchange_name}({fresh})")

            # Best spread this tick across all symbols
            best_ticks: list[tuple[str, float, float, float, str, str]] = []
            for symbol in self._all_symbols:
                ticks = self._ticks.get(symbol)
                if ticks:
                    last = ticks[-1]
                    if last.timestamp >= now - 2.0:  # Recent tick
                        best_ticks.append((
                            symbol, last.best_net_pct, last.spread_pct,
                            last.fee_pct, last.buy_exchange, last.sell_exchange,
                        ))
            best_ticks.sort(key=lambda x: x[1], reverse=True)

            logger.debug(
                f"[Discovery] {elapsed:.0f}s | tick={self._tick_count} | "
                f"exchanges: {', '.join(ex_names)} | "
                f"symbols_with_2+_exchanges: {symbols_with_data}/{len(self._all_symbols)}"
            )

            # Top 5 spreads this tick
            if best_ticks:
                for sym, net, spread, fee, buy_ex, sell_ex in best_ticks[:5]:
                    logger.debug(
                        f"[Discovery]   {sym.replace('USDT', ''):>8s}: "
                        f"net={net:+.4f}% spread={spread:+.4f}% fee={fee:.4f}% "
                        f"({buy_ex}->{sell_ex})"
                    )
                # Count positive vs negative net spreads
                pos = sum(1 for _, n, *_ in best_ticks if n > 0)
                neg = len(best_ticks) - pos
                logger.debug(
                    f"[Discovery]   Spread summary: {pos} positive, {neg} negative "
                    f"out of {len(best_ticks)} symbols with data"
                )

        # Every 60s: score ranking summary
        if now - self._discovery_debug_last_detail >= 60.0:
            self._discovery_debug_last_detail = now

            if self._scores:
                ranked = sorted(
                    self._scores.values(),
                    key=lambda s: s.score,
                    reverse=True,
                )
                # Top 10 with full breakdown
                logger.debug(
                    f"[Discovery] Score ranking at {elapsed:.0f}s "
                    f"(threshold={self._trading_threshold}):"
                )
                for s in ranked[:10]:
                    logger.debug(
                        f"[Discovery]   #{s.rank:2d} {s.symbol.replace('USDT', ''):>8s}: "
                        f"score={s.score:.6f} "
                        f"(avg_prof_net={s.avg_profitable_net:.4f}% × freq={s.frequency:.2%}) "
                        f"ticks={s.profitable_ticks}/{s.total_ticks} "
                        f"best_net={s.best_net_pct:+.4f}%"
                    )
                above = sum(1 for s in ranked if s.score >= self._trading_threshold)
                logger.debug(
                    f"[Discovery]   {above} symbols above threshold "
                    f"({self._trading_threshold}), "
                    f"{sum(1 for s in ranked if s.score >= self._strong_threshold)} strong "
                    f"({self._strong_threshold})"
                )

                # Fee floor analysis: show min combined fee for each exchange pair
                if elapsed <= 120:  # Only in first 2 minutes
                    ex_list = sorted(self._active_exchanges)
                    logger.debug("[Discovery]   Fee pairs:")
                    for i, ex1 in enumerate(ex_list):
                        for ex2 in ex_list[i + 1:]:
                            fee1 = self._fee_manager.get_taker_fee(ex1) if self._fee_manager else 0.001
                            fee2 = self._fee_manager.get_taker_fee(ex2) if self._fee_manager else 0.001
                            combined = (fee1 + fee2) * 100
                            logger.debug(
                                f"[Discovery]     {ex1}+{ex2}: {combined:.3f}%"
                            )

    def _compute_scores(self) -> None:
        """Recompute SymbolScore for all symbols from rolling windows."""
        all_scores: list[SymbolScore] = []

        for sym in self._all_symbols:
            ticks = self._ticks[sym]
            total = len(ticks)
            if total == 0:
                all_scores.append(
                    SymbolScore(
                        symbol=sym,
                        score=0.0,
                        avg_net_pct=0.0,
                        avg_profitable_net=0.0,
                        profitable_ticks=0,
                        total_ticks=0,
                        frequency=0.0,
                        best_net_pct=0.0,
                        est_hourly_profit=0.0,
                    )
                )
                continue

            profitable = [t for t in ticks if t.best_net_pct > 0]
            profitable_count = len(profitable)
            frequency = profitable_count / total

            avg_net = sum(t.best_net_pct for t in ticks) / total
            avg_profitable_net = (
                sum(t.best_net_pct for t in profitable) / profitable_count
                if profitable_count > 0
                else 0.0
            )
            best_net = max(t.best_net_pct for t in ticks)

            # score = avg profitable spread × frequency
            score = avg_profitable_net * frequency

            # est hourly profit = profitable ticks/hour × profit per tick
            ticks_per_hour = frequency * 3600
            profit_per_tick = self._trade_amount * (avg_profitable_net / 100)
            est_hourly = ticks_per_hour * profit_per_tick

            all_scores.append(
                SymbolScore(
                    symbol=sym,
                    score=score,
                    avg_net_pct=avg_net,
                    avg_profitable_net=avg_profitable_net,
                    profitable_ticks=profitable_count,
                    total_ticks=total,
                    frequency=frequency,
                    best_net_pct=best_net,
                    est_hourly_profit=est_hourly,
                )
            )

        all_scores.sort(key=lambda s: s.score, reverse=True)
        for i, s in enumerate(all_scores):
            s.rank = i + 1

        self._scores = {s.symbol: s for s in all_scores}

        # Compute per-symbol trade multipliers with focus tiers for active symbols
        # Tiered system: very_strong (>=0.3), strong (>=0.1), normal (>=0.01), weak (<0.01)
        # Symbols >= self._trading_threshold (0.01) can trade; below that get multiplier=0
        active_set = set(self._active_symbols)
        active_with_score = [s for s in all_scores if s.symbol in active_set and s.score > 0]
        if active_with_score:
            mean_score = sum(s.score for s in active_with_score) / len(active_with_score)
            if mean_score > 0:
                for s in active_with_score:
                    raw = s.score / mean_score
                    if s.score >= self._very_strong_threshold:
                        s.trade_multiplier = max(3.0, min(4.0, raw * 2.0))
                        s.focus_tier = "very_strong"
                    elif s.score >= self._strong_threshold:
                        s.trade_multiplier = max(2.0, min(3.0, raw * 1.5))
                        s.focus_tier = "strong"
                    elif s.score >= self._trading_threshold:
                        s.trade_multiplier = max(0.5, min(1.5, raw))
                        s.focus_tier = "normal"
                    else:
                        # Below trading threshold: no trading allowed
                        s.trade_multiplier = 0.0
                        s.focus_tier = "weak"
                    # Recompute est_hourly_profit with multiplied trade amount
                    ticks_per_hour = s.frequency * 3600
                    profit_per_tick = (self._trade_amount * s.trade_multiplier) * (s.avg_profitable_net / 100)
                    s.est_hourly_profit = ticks_per_hour * profit_per_tick

        self._track_candidate_transitions()

    # ── Historical Tracking ─────────────────────────────────────────────

    def _update_historical_stats(self, symbol: str, tick: SymbolTick) -> None:
        """Append one tick's data to cumulative session-level stats."""
        stats = self._historical_stats.get(symbol)
        if not stats:
            stats = HistoricalSymbolStats(symbol=symbol)
            self._historical_stats[symbol] = stats

        stats.total_ticks += 1
        stats.total_net_pct_sum += tick.best_net_pct
        stats.last_seen = tick.timestamp
        if stats.first_seen == 0.0:
            stats.first_seen = tick.timestamp

        if tick.best_net_pct > stats.best_net_pct:
            stats.best_net_pct = tick.best_net_pct
        if tick.best_net_pct < stats.worst_net_pct:
            stats.worst_net_pct = tick.best_net_pct

        if tick.best_net_pct > 0:
            stats.total_profitable_ticks += 1
            stats.total_profitable_net_sum += tick.best_net_pct
            stats.est_total_profit += self._trade_amount * (tick.best_net_pct / 100)
            stats.current_profitable_streak += 1
            stats.current_unprofitable_streak = 0
            if stats.current_profitable_streak > stats.longest_profitable_streak:
                stats.longest_profitable_streak = stats.current_profitable_streak
        else:
            stats.current_unprofitable_streak += 1
            stats.current_profitable_streak = 0
            if stats.current_unprofitable_streak > stats.longest_unprofitable_streak:
                stats.longest_unprofitable_streak = stats.current_unprofitable_streak

        # Per-exchange direction tracking
        if tick.best_net_pct > 0:
            stats.buy_exchange_counts[tick.buy_exchange] = (
                stats.buy_exchange_counts.get(tick.buy_exchange, 0) + 1
            )
            stats.sell_exchange_counts[tick.sell_exchange] = (
                stats.sell_exchange_counts.get(tick.sell_exchange, 0) + 1
            )

        # Historical exchange stats
        if tick.best_net_pct > 0:
            for ex_name in (tick.buy_exchange, tick.sell_exchange):
                if ex_name not in self._historical_exchange_stats:
                    self._historical_exchange_stats[ex_name] = HistoricalExchangeStats(
                        exchange=ex_name
                    )
                ex_stats = self._historical_exchange_stats[ex_name]
                ex_stats.total_profit_sum += tick.best_net_pct
                ex_stats.total_involvement += 1
            self._historical_exchange_stats[tick.buy_exchange].total_buy_ticks += 1
            self._historical_exchange_stats[tick.sell_exchange].total_sell_ticks += 1

    def _track_candidate_transitions(self) -> None:
        """Track when symbols transition to/from candidate, strong, very_strong status."""
        now = time.time()

        current_candidates = {
            s.symbol for s in self._scores.values() if s.score > 0
        }
        current_strong = {
            s.symbol for s in self._scores.values() if s.score >= self._strong_threshold
        }
        current_very_strong = {
            s.symbol for s in self._scores.values() if s.score >= self._very_strong_threshold
        }

        # Newly became candidate
        for sym in current_candidates - self._prev_candidate_set:
            if sym in self._historical_stats:
                self._historical_stats[sym].times_became_candidate += 1

        # Strong transitions (score >= 0.1)
        for sym in current_strong - self._prev_strong_set:
            stats = self._historical_stats.get(sym)
            if stats:
                stats.times_became_strong += 1
                stats.last_strong_at = now
        for sym in self._prev_strong_set - current_strong:
            stats = self._historical_stats.get(sym)
            if stats and stats.last_strong_at > 0:
                stats.total_strong_duration += now - stats.last_strong_at
                stats.last_strong_at = 0.0

        # Very strong transitions (score >= 0.3)
        for sym in current_very_strong - self._prev_very_strong_set:
            stats = self._historical_stats.get(sym)
            if stats:
                stats.times_became_very_strong += 1
                stats.last_very_strong_at = now
        for sym in self._prev_very_strong_set - current_very_strong:
            stats = self._historical_stats.get(sym)
            if stats and stats.last_very_strong_at > 0:
                stats.total_very_strong_duration += now - stats.last_very_strong_at
                stats.last_very_strong_at = 0.0

        self._prev_candidate_set = current_candidates
        self._prev_strong_set = current_strong
        self._prev_very_strong_set = current_very_strong

    # ── Discovery ─────────────────────────────────────────────────────────

    def _complete_discovery(self) -> None:
        """Pick best symbols after discovery period. All active exchanges stay active."""
        if not self._scores:
            logger.warning("[Optimizer] Discovery complete but no scores available")
            logger.setLevel(logging.INFO)
            self._discovery_mode = False
            self._discovery_complete = True
            self._monitor._paused = False
            return

        # Pick symbols that meet the trading threshold (score >= 0.01)
        ranked_symbols = sorted(
            [s for s in self._scores.values() if s.total_ticks > 0],
            key=lambda s: s.score,
            reverse=True,
        )
        tradeable_symbols = [
            s.symbol for s in ranked_symbols
            if s.score >= self._trading_threshold
        ]

        if tradeable_symbols:
            # Activate tradeable symbols (cap at max_active)
            best_symbols = tradeable_symbols[: self._max_active_symbols]
            strong_count = sum(1 for s in ranked_symbols
                             if s.symbol in best_symbols and s.score >= self._strong_threshold)
            logger.info(
                f"[Optimizer] Discovery: {len(tradeable_symbols)} tradeable symbols found "
                f"(score >= {self._trading_threshold}), {strong_count} strong (>= {self._strong_threshold}), "
                f"activating {len(best_symbols)}"
            )
        else:
            # No tradeable symbols found — extend discovery and keep scanning
            self._discovery_duration = min(
                self._discovery_duration * 2, 3600
            )
            self._discovery_start = time.time()
            top_10 = ", ".join(
                f"{s.symbol.replace('USDT', '')}({s.score:.6f} "
                f"prof={s.profitable_ticks}/{s.total_ticks} "
                f"best={s.best_net_pct:+.4f}%)"
                for s in ranked_symbols[:10]
            ) if ranked_symbols else "no data"
            logger.warning(
                f"[Optimizer] Discovery: NO tradeable symbols (>= {self._trading_threshold}). "
                f"Extending to {self._discovery_duration}s. Top 10: {top_10}"
            )
            return  # Stay in discovery mode, don't proceed

        if not best_symbols:
            logger.warning("[Optimizer] Discovery: no symbols with data")
            logger.setLevel(logging.INFO)
            self._discovery_mode = False
            self._discovery_complete = True
            self._monitor._paused = False
            return

        # All active exchanges stay active (no exchange filtering)
        all_exchanges = list(self._active_exchanges)

        # Log exchange profitability from discovery
        sorted_exchanges = sorted(
            self._exchange_profit_sum.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for ex, score in sorted_exchanges[:7]:
            ticks = self._exchange_profit_ticks.get(ex, 0)
            logger.info(
                f"[Optimizer]   {ex}: profit_sum={score:.2f}, "
                f"profitable_ticks={ticks}"
            )

        # Compute per-symbol dominant exchange pairs and concentrated allocation
        total_capital = self._total_capital

        # Compute dominant pairs per symbol (1 buyer + 1 seller by default,
        # strong=2 per dir, very_strong=3 per dir)
        for sym in best_symbols:
            sym_score = self._scores.get(sym)
            score_val = sym_score.score if sym_score else 0.0
            if score_val >= self._very_strong_threshold:
                max_dir = 3
            elif score_val >= self._strong_threshold:
                max_dir = 2
            else:
                max_dir = 2  # min 2 to avoid over-concentration on 1 pair
            pairs = self._compute_dominant_pairs(sym, max_per_direction=max_dir)
            self._dominant_pairs[sym] = pairs
            buyers_str = ",".join(f"{ex}({w:.0%})" for ex, w in pairs["buyers"])
            sellers_str = ",".join(f"{ex}({w:.0%})" for ex, w in pairs["sellers"])
            logger.info(
                f"[Optimizer]   {sym.replace('USDT', '')}: "
                f"buyers=[{buyers_str}] sellers=[{sellers_str}] "
                f"({pairs['num_exchanges']} exchanges)"
            )

        # Carve out Bitfinex reserve before allocating to symbols
        reserve_pct = self._balance._bitfinex_reserve_pct if self._balance else 0.15
        reserve_amount = 0.0
        if reserve_pct > 0 and "Bitfinex" in all_exchanges:
            reserve_amount = total_capital * reserve_pct
            logger.info(
                f"[Optimizer] Bitfinex reserve: ${reserve_amount:.0f} "
                f"({reserve_pct:.0%} of ${total_capital:.0f} capital)"
            )
        allocatable_capital = total_capital - reserve_amount

        # Score-weighted capital distribution across symbols
        best_scores = {sym: self._scores[sym].score for sym in best_symbols if sym in self._scores}
        total_score = sum(best_scores.values())
        min_weight = 0.1 / len(best_symbols)  # minimum 10% / num_symbols

        # Build allocations: USDT to buyer exchanges, crypto to seller exchanges
        allocations: dict[str, dict] = {}
        for ex in all_exchanges:
            allocations[ex] = {"usdt": 0.0, "crypto": {}}

        # Assign Bitfinex reserve as USDT
        if reserve_amount > 0:
            allocations["Bitfinex"]["usdt"] += reserve_amount

        for sym in best_symbols:
            # Score-weighted capital per symbol
            if total_score > 0:
                sym_weight = max(min_weight, best_scores.get(sym, 0) / total_score)
            else:
                sym_weight = 1.0 / len(best_symbols)
            sym_capital = allocatable_capital * sym_weight

            pairs = self._dominant_pairs[sym]

            # USDT → buyer exchanges (proportional to buyer weight)
            total_buy_w = sum(w for _, w in pairs["buyers"])
            for ex, w in pairs["buyers"]:
                usdt_share = sym_capital * 0.5 * (w / total_buy_w) if total_buy_w > 0 else 0
                allocations[ex]["usdt"] += usdt_share

            # Crypto → seller exchanges (proportional to seller weight)
            total_sell_w = sum(w for _, w in pairs["sellers"])
            for ex, w in pairs["sellers"]:
                crypto_share = sym_capital * 0.5 * (w / total_sell_w) if total_sell_w > 0 else 0
                if sym not in allocations[ex]["crypto"]:
                    allocations[ex]["crypto"][sym] = 0.0
                allocations[ex]["crypto"][sym] += crypto_share

        # Round allocations
        for ex in all_exchanges:
            allocations[ex]["usdt"] = round(allocations[ex]["usdt"], 2)
            for sym in list(allocations[ex]["crypto"].keys()):
                allocations[ex]["crypto"][sym] = round(allocations[ex]["crypto"][sym], 2)

        # Log per-exchange totals
        for ex in all_exchanges:
            usdt = allocations[ex]["usdt"]
            crypto_total = sum(allocations[ex]["crypto"].values())
            if usdt > 0 or crypto_total > 0:
                syms = [s.replace("USDT", "") for s, v in allocations[ex]["crypto"].items() if v > 0]
                logger.info(
                    f"[Optimizer]   {ex}: USDT=${usdt:.0f}, "
                    f"crypto=${crypto_total:.0f} ({', '.join(syms) if syms else 'none'})"
                )

        logger.info(
            f"[Optimizer] Discovery complete! "
            f"Best symbols: {', '.join(s.replace('USDT', '') for s in best_symbols)} | "
            f"Concentrated allocation, ${total_capital:.0f} total"
        )

        # Update optimizer state (only symbols change, exchanges stay the same)
        self._active_symbols = best_symbols

        # Track activation in historical stats
        now_ts = time.time()
        for sym in best_symbols:
            stats = self._historical_stats.get(sym)
            if stats:
                stats.times_activated += 1
                stats.last_activated_at = now_ts

        # Reset balance tracker in-place with new config
        self._balance._exchanges = list(all_exchanges)
        self._balance._symbols = list(best_symbols)
        self._balance.reset(allocations=allocations)

        # Reset monitor with new config (all exchanges stay active)
        self._monitor.reset(
            symbols=best_symbols,
            exchanges=all_exchanges,
            trade_amount=self._trade_amount,
            balance=self._balance,
        )
        self._monitor._paused = False

        # Update dashboard references and in-memory settings
        if self._dashboard:
            self._dashboard._balance = self._balance
            self._dashboard._settings["active_symbols"] = list(best_symbols)
            self._dashboard._settings["allocations"] = allocations

        # Transition to normal operation — disable discovery debug logging
        logger.setLevel(logging.INFO)
        self._discovery_mode = False
        self._discovery_complete = True
        self._last_evaluation = time.time()

        # Keep rolling tick data — scoring logic is identical before/after discovery.
        # Only reset tick count for warmup timing.
        self._tick_count = 0

        logger.info(
            f"[Optimizer] Trading started: {best_symbols} on {all_exchanges}"
        )

    # ── Watchlist ──────────────────────────────────────────────────────────

    def _update_watchlist(self) -> None:
        """Track strong candidates and confirm after sustained performance."""
        now = time.time()
        active_set = set(self._active_symbols)

        # Determine threshold: max of promotion_threshold and worst active score
        active_scores = [
            self._scores[s].score
            for s in self._active_symbols
            if s in self._scores
        ]
        threshold = max(
            self._promotion_threshold,
            min(active_scores) if active_scores else 0.0,
        )

        # Update existing entries and add new ones
        cooldown_set = set(self._recently_demoted.keys())
        for sym, score_obj in self._scores.items():
            if sym in active_set or sym in cooldown_set:
                continue

            if score_obj.score >= threshold and score_obj.score > 0:
                if sym not in self._watchlist:
                    self._watchlist[sym] = WatchlistEntry(
                        symbol=sym,
                        entered_at=now,
                        confirmation_start=now,
                    )
                    # Track in historical stats
                    stats = self._historical_stats.get(sym)
                    if stats:
                        stats.times_entered_watchlist += 1

                entry = self._watchlist[sym]
                entry.score_samples.append(score_obj.score)

                # Check confirmation (faster for strong/very_strong candidates)
                score_val = score_obj.score if score_obj else 0.0
                if score_val >= self._very_strong_threshold:
                    confirm_time = self._confirmation_period * 0.1
                elif score_val >= self._strong_threshold:
                    confirm_time = self._confirmation_period * 0.4
                else:
                    confirm_time = self._confirmation_period
                if not entry.confirmed and now - entry.entered_at >= confirm_time:
                    entry.confirmed = True
                    stats = self._historical_stats.get(sym)
                    if stats:
                        stats.times_confirmed += 1
                    logger.info(
                        f"[Optimizer] Watchlist CONFIRMED: {sym} "
                        f"(avg score={sum(entry.score_samples)/len(entry.score_samples):.6f}, "
                        f"confirm={confirm_time:.0f}s)"
                    )
            else:
                # Score dropped below threshold — remove from watchlist
                self._watchlist.pop(sym, None)

    # ── Demotion ─────────────────────────────────────────────────────────

    def _evaluate_demotions(self) -> None:
        """Demote active symbols that drop below trading threshold."""
        now = time.time()
        to_demote: list[str] = []

        for sym in self._active_symbols:
            score_obj = self._scores.get(sym)
            score_val = score_obj.score if score_obj else 0.0
            multiplier = score_obj.trade_multiplier if score_obj else 0.0

            # Instant demotion: if trade_multiplier is 0, symbol is dead weight
            if multiplier <= 0 and score_val < self._trading_threshold and sym in self._demotion_tracking:
                elapsed = now - self._demotion_tracking[sym]
                if elapsed >= 30:  # 30s grace period to stabilize after discovery
                    to_demote.append(sym)
                    continue

            # Demote if below trading threshold (score < 0.01)
            if score_val < self._trading_threshold:
                if sym not in self._demotion_tracking:
                    self._demotion_tracking[sym] = now
                else:
                    # Fast-track: symbols at zero or negative demote faster
                    if score_val <= self._demotion_threshold:
                        required_period = self._demotion_period / 4  # very fast
                    elif score_val < self._trading_threshold / 2:
                        required_period = self._demotion_period / 2  # fast
                    else:
                        required_period = self._demotion_period  # normal
                    if now - self._demotion_tracking[sym] >= required_period:
                        to_demote.append(sym)
            else:
                # Score recovered above trading threshold, reset tracking
                self._demotion_tracking.pop(sym, None)

        for sym in to_demote:
            self._execute_demotion(sym)

    def _execute_demotion(self, symbol: str) -> None:
        """Remove an underperforming symbol from the active set.

        Sells all held crypto to avoid market exposure risk from price drops.
        """
        from balance import Transfer

        now = time.time()

        # Sell all crypto of the demoted symbol on every exchange
        prices = self._get_all_prices()
        price = prices.get(symbol, 0.0)
        freed_capital = 0.0
        total_sell_fee = 0.0
        if price > 0:
            for ex in self._balance._exchanges:
                qty = self._balance.crypto[ex].get(symbol, 0.0)
                if qty > 0:
                    fee_rate = (
                        self._fee_manager.get_taker_fee(ex)
                        if self._fee_manager
                        else 0.001
                    )
                    gross = qty * price
                    fee = gross * fee_rate
                    self._balance.crypto[ex][symbol] = 0.0
                    self._balance.usdt[ex] += gross - fee
                    total_sell_fee += fee
                    freed_capital += gross - fee
                    self._balance.transfers.append(
                        Transfer(
                            timestamp=now,
                            transfer_type="demotion_sell",
                            from_exchange=ex,
                            to_exchange=ex,
                            symbol=symbol,
                            amount_usd=gross,
                            fee_usd=fee,
                        )
                    )
            self._balance.total_transfer_fees += total_sell_fee

        logger.info(
            f"[Optimizer] DEMOTING: {symbol} (score below threshold for "
            f"{self._demotion_period}s) — selling crypto "
            f"(freed ${freed_capital:.2f}, fees ${total_sell_fee:.4f})"
        )

        # Update historical stats
        stats = self._historical_stats.get(symbol)
        if stats:
            stats.times_demoted += 1
            if stats.last_activated_at > 0:
                stats.total_active_duration += now - stats.last_activated_at
                stats.last_activated_at = 0.0

        # Remove from active
        self._active_symbols = [s for s in self._active_symbols if s != symbol]
        self._demotion_tracking.pop(symbol, None)
        # Anti-churning: record demotion time to prevent immediate re-activation
        self._recently_demoted[symbol] = now

        self._monitor.update_symbols(list(self._active_symbols))
        self._balance.update_symbols(list(self._active_symbols))

        logger.info(
            f"[Optimizer] Demotion complete: {symbol} removed, "
            f"cooldown={self._demotion_cooldown}s, active: {self._active_symbols}"
        )

        # Re-enter discovery if no active symbols remain
        if not self._active_symbols:
            logger.warning(
                "[Optimizer] All symbols demoted — re-entering discovery mode"
            )
            self._discovery_mode = True
            self._discovery_complete = False
            self._discovery_start = time.time()
            # Reset to initial discovery duration
            self._discovery_duration = self._initial_discovery_duration
            self._monitor._paused = True

    # ── Activation threshold ─────────────────────────────────────────────

    def _get_activation_threshold(self, symbol: str) -> float:
        """Minimum score for activation, elevated for frequently-demoted symbols."""
        base = self._trading_threshold  # 0.01
        stats = self._historical_stats.get(symbol)
        if not stats or stats.times_demoted <= 0:
            return base
        # Each demotion adds 50% of base, cap at strong threshold
        elevated = base * (1.0 + stats.times_demoted * 0.5)
        result = min(elevated, self._strong_threshold)
        if result > base:
            logger.info(
                f"[Optimizer] Activation threshold elevated for {symbol}: "
                f"{result:.3f} (demoted {stats.times_demoted} times)"
            )
        return result

    # ── Expansion ────────────────────────────────────────────────────────

    def _expand_active(self, symbol: str, score: SymbolScore) -> None:
        """Add a new confirmed symbol to the active set."""
        from balance import Transfer

        now = time.time()
        prices = self._get_all_prices()
        new_price = prices.get(symbol, 0.0)

        if new_price <= 0:
            return

        logger.info(
            f"[Optimizer] EXPANDING: adding {symbol} (score={score.score:.4f})"
        )

        # Compute dominant pairs (tier-based exchange count)
        if score.score >= self._very_strong_threshold:
            max_dir = 3
        elif score.score >= self._strong_threshold:
            max_dir = 2
        else:
            max_dir = 2  # min 2 to avoid over-concentration on 1 pair
        pairs = self._compute_dominant_pairs(symbol, max_per_direction=max_dir)
        self._dominant_pairs[symbol] = pairs

        total_fee = 0.0
        # Only buy crypto on dominant seller exchanges
        total_sell_w = sum(w for _, w in pairs["sellers"])
        total_alloc = self._trade_amount * len(self._balance._exchanges)
        for ex, w in pairs["sellers"]:
            alloc = total_alloc * (w / total_sell_w) if total_sell_w > 0 else self._trade_amount
            if ex not in self._balance.usdt or self._balance.usdt[ex] < alloc:
                continue
            fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
            fee_usd = alloc * fee_rate
            new_qty = (alloc - fee_usd) / new_price
            self._balance.usdt[ex] -= alloc
            if symbol not in self._balance.crypto[ex]:
                self._balance.crypto[ex][symbol] = 0.0
            self._balance.crypto[ex][symbol] += new_qty
            total_fee += fee_usd
            self._balance.transfers.append(
                Transfer(
                    timestamp=now,
                    transfer_type="expansion_buy",
                    from_exchange=ex,
                    to_exchange=ex,
                    symbol=symbol,
                    amount_usd=alloc,
                    fee_usd=fee_usd,
                )
            )

        sellers_str = ",".join(ex for ex, _ in pairs["sellers"])
        logger.info(
            f"[Optimizer] Expansion concentrated on sellers: [{sellers_str}]"
        )

        self._balance.total_transfer_fees += total_fee

        self._active_symbols.append(symbol)

        # Historical stats
        stats = self._historical_stats.get(symbol)
        if stats:
            stats.times_activated += 1
            stats.last_activated_at = now

        self._monitor.update_symbols(list(self._active_symbols))
        self._balance.update_symbols(list(self._active_symbols))

        logger.info(
            f"[Optimizer] Expansion complete: {symbol} added, "
            f"fees: ${total_fee:.4f}, active: {self._active_symbols}"
        )

    # ── Rotation ─────────────────────────────────────────────────────────

    def _evaluate_rotation(self) -> None:
        """Check watchlist for confirmed candidates, evaluate demotions and expansion."""
        if not self._scores:
            return

        now = time.time()

        # Net profit gate: block rotations/expansions when in deficit
        if not self._rotation_budget_ok:
            logger.info(
                "[Optimizer] Rotation suppressed: net profit is negative "
                "(transfer fees exceed trading profit)"
            )
            # Still run demotions to remove truly dead symbols
            self._update_watchlist()
            self._evaluate_demotions()
            return

        # Clean up expired demotion cooldowns
        expired = [
            sym for sym, ts in self._recently_demoted.items()
            if now - ts >= self._demotion_cooldown
        ]
        for sym in expired:
            del self._recently_demoted[sym]
            logger.info(f"[Optimizer] Cooldown expired for {sym}, eligible for re-activation")

        # Phase 3: Update watchlist
        self._update_watchlist()

        # Phase 3.5: Re-evaluate dominant exchange pairs for active symbols
        self._reevaluate_dominant_pairs()

        # Phase 3.6: Replenish Bitfinex reserve if depleted and profitable
        if self._rotation_budget_ok and self._balance:
            self._balance.replenish_reserve()

        # Phase 4: Evaluate demotions first
        self._evaluate_demotions()

        active_scores = [
            self._scores[s]
            for s in self._active_symbols
            if s in self._scores
        ]
        if not active_scores:
            return

        # Sort active symbols worst-first
        active_scores.sort(key=lambda s: s.score)

        # Switching cost: uses actual exchange counts per symbol (concentrated)
        avg_fee_rate = (
            sum(
                (self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001)
                for ex in self._active_exchanges
            )
            / max(len(self._active_exchanges), 1)
        )

        # Symbols on demotion cooldown cannot be candidates
        cooldown_set = set(self._recently_demoted.keys())

        # Get confirmed watchlist candidates sorted best-first
        active_set = set(self._active_symbols)
        confirmed_candidates = sorted(
            [
                self._scores[e.symbol]
                for e in self._watchlist.values()
                if e.confirmed and e.symbol not in active_set
                and e.symbol not in cooldown_set and e.symbol in self._scores
            ],
            key=lambda s: s.score,
            reverse=True,
        )

        # No fallback: only confirmed watchlist candidates are eligible for rotation.
        # This prevents premature rotations with unconfirmed symbols.

        # Rotation: replace worst active with best confirmed candidate
        # Only strong/very_strong candidates can be activated
        for worst in active_scores:
            if not confirmed_candidates:
                break

            best_candidate = confirmed_candidates[0]
            # Gate: candidate must meet activation threshold (elevated for frequently-demoted)
            if best_candidate.score < self._get_activation_threshold(best_candidate.symbol):
                break
            # Require candidate score to be at least 3x the worst active score
            if best_candidate.score <= worst.score * 3:
                break

            # Per-pair switching cost using actual exchange counts
            old_ex_count = len(self._get_symbol_exchanges(worst.symbol))
            new_ex_count = len(self._get_symbol_exchanges(best_candidate.symbol))
            switching_cost = self._trade_amount * (old_ex_count + new_ex_count) * avg_fee_rate * 1.5

            hourly_improvement = (
                best_candidate.est_hourly_profit - worst.est_hourly_profit
            )
            threshold = switching_cost * self._safety_multiplier

            if hourly_improvement > threshold:
                self._execute_rotation(
                    old_symbol=worst.symbol,
                    new_symbol=best_candidate.symbol,
                    old_score=worst,
                    new_score=best_candidate,
                    switching_cost=switching_cost,
                    hourly_improvement=hourly_improvement,
                )
                # Remove from watchlist after activation
                self._watchlist.pop(best_candidate.symbol, None)
                confirmed_candidates.pop(0)
            else:
                break

        # Phase 4: Expansion — add high-scoring symbols if under max
        # Don't require watchlist confirmation for expansion (low risk, just adding)
        if len(self._active_symbols) < self._max_active_symbols:
            active_set = set(self._active_symbols)
            cooldown_set_now = set(self._recently_demoted.keys())
            expansion_cost = self._trade_amount * 2 * avg_fee_rate * 1.5

            # Consider ALL scored symbols (not just confirmed watchlist)
            expansion_candidates = sorted(
                [
                    s for s in self._scores.values()
                    if s.symbol not in active_set
                    and s.symbol not in cooldown_set_now
                    and s.score >= self._get_activation_threshold(s.symbol)
                    and s.total_ticks >= 30  # minimum data points
                    and s.est_hourly_profit > expansion_cost * self._safety_multiplier
                ],
                key=lambda s: s.score,
                reverse=True,
            )
            for candidate in expansion_candidates:
                if len(self._active_symbols) >= self._max_active_symbols:
                    break
                self._expand_active(candidate.symbol, candidate)
                self._watchlist.pop(candidate.symbol, None)

    def _execute_rotation(
        self,
        old_symbol: str,
        new_symbol: str,
        old_score: SymbolScore,
        new_score: SymbolScore,
        switching_cost: float,
        hourly_improvement: float,
    ) -> None:
        """Execute symbol rotation: sell old crypto, buy new, update trackers."""
        from balance import Transfer

        now = time.time()
        prices = self._get_all_prices()
        old_price = prices.get(old_symbol, 0.0)
        new_price = prices.get(new_symbol, 0.0)

        if old_price <= 0 or new_price <= 0:
            logger.warning(
                f"[Optimizer] Cannot rotate {old_symbol}→{new_symbol}: "
                f"missing price (old={old_price}, new={new_price})"
            )
            return

        logger.info(
            f"[Optimizer] ROTATING: {old_symbol} (score={old_score.score:.4f}) "
            f"→ {new_symbol} (score={new_score.score:.4f}), "
            f"est improvement: ${hourly_improvement:.4f}/hr, "
            f"switching cost: ${switching_cost:.4f}"
        )

        total_fee = 0.0

        # 1. Sell all old symbol crypto on each exchange
        for ex in self._balance._exchanges:
            old_qty = self._balance.crypto[ex].get(old_symbol, 0.0)
            if old_qty > 0:
                fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
                gross_usd = old_qty * old_price
                fee_usd = gross_usd * fee_rate
                self._balance.crypto[ex][old_symbol] = 0.0
                self._balance.usdt[ex] += gross_usd - fee_usd
                total_fee += fee_usd

                self._balance.transfers.append(
                    Transfer(
                        timestamp=now,
                        transfer_type="rotation_sell",
                        from_exchange=ex,
                        to_exchange=ex,
                        symbol=old_symbol,
                        amount_usd=gross_usd,
                        fee_usd=fee_usd,
                    )
                )

        # 2. Buy new symbol crypto only on dominant seller exchanges
        if new_score.score >= self._very_strong_threshold:
            max_dir = 3
        elif new_score.score >= self._strong_threshold:
            max_dir = 2
        else:
            max_dir = 2  # min 2 to avoid over-concentration on 1 pair
        pairs = self._compute_dominant_pairs(new_symbol, max_per_direction=max_dir)
        self._dominant_pairs[new_symbol] = pairs
        # Clean up old symbol's dominant pair data
        self._dominant_pairs.pop(old_symbol, None)

        total_sell_w = sum(w for _, w in pairs["sellers"])
        total_alloc = self._trade_amount * len(self._balance._exchanges)
        for ex, w in pairs["sellers"]:
            alloc = total_alloc * (w / total_sell_w) if total_sell_w > 0 else self._trade_amount
            if ex not in self._balance.usdt or self._balance.usdt[ex] < alloc:
                continue
            fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
            fee_usd = alloc * fee_rate
            new_qty = (alloc - fee_usd) / new_price
            self._balance.usdt[ex] -= alloc
            if new_symbol not in self._balance.crypto[ex]:
                self._balance.crypto[ex][new_symbol] = 0.0
            self._balance.crypto[ex][new_symbol] += new_qty
            total_fee += fee_usd

            self._balance.transfers.append(
                Transfer(
                    timestamp=now,
                    transfer_type="rotation_buy",
                    from_exchange=ex,
                    to_exchange=ex,
                    symbol=new_symbol,
                    amount_usd=alloc,
                    fee_usd=fee_usd,
                )
            )

        self._balance.total_transfer_fees += total_fee

        # 3. Update active symbols
        try:
            idx = self._active_symbols.index(old_symbol)
            self._active_symbols[idx] = new_symbol
        except ValueError:
            self._active_symbols.append(new_symbol)

        # 4. Propagate to monitor and balance tracker
        self._monitor.update_symbols(list(self._active_symbols))
        self._balance.update_symbols(list(self._active_symbols))

        # 5. Anti-churning: cooldown for rotated-out symbol
        self._recently_demoted[old_symbol] = now

        # 6. Update historical lifecycle counters
        old_stats = self._historical_stats.get(old_symbol)
        if old_stats:
            old_stats.times_demoted += 1
            if old_stats.last_activated_at > 0:
                old_stats.total_active_duration += now - old_stats.last_activated_at
                old_stats.last_activated_at = 0.0

        new_stats = self._historical_stats.get(new_symbol)
        if new_stats:
            new_stats.times_activated += 1
            new_stats.last_activated_at = now

        # 7. Record event
        self._rotations.append(
            RotationEvent(
                timestamp=now,
                old_symbol=old_symbol,
                new_symbol=new_symbol,
                old_score=old_score.score,
                new_score=new_score.score,
                switching_cost_usd=total_fee,
                est_hourly_improvement_usd=hourly_improvement,
            )
        )

        logger.info(
            f"[Optimizer] Rotation complete: {old_symbol} → {new_symbol}, "
            f"fees: ${total_fee:.4f}, active: {self._active_symbols}"
        )

    # ── Exchange Concentration ────────────────────────────────────────────

    def _compute_dominant_pairs(
        self, symbol: str, min_ticks: int = 30, max_per_direction: int = 1
    ) -> dict:
        """Analyze rolling tick data to find dominant buyer/seller exchanges for a symbol.

        Args:
            max_per_direction: max exchanges per buy/sell direction.
                Default 1 (= 1 buyer + 1 seller = 2 exchanges total).
                Strong symbols may pass 2, very_strong may pass 3.

        Returns dict with:
            buyers: list of (exchange, weight) tuples, sorted by weight desc
            sellers: list of (exchange, weight) tuples, sorted by weight desc
            num_exchanges: total unique exchanges needed
        """
        buy_scores: dict[str, float] = defaultdict(float)
        sell_scores: dict[str, float] = defaultdict(float)

        ticks = self._ticks.get(symbol, deque())
        profitable = [t for t in ticks if t.best_net_pct > 0]

        if len(profitable) >= min_ticks:
            for t in profitable:
                buy_scores[t.buy_exchange] += t.best_net_pct
                sell_scores[t.sell_exchange] += t.best_net_pct
        else:
            stats = self._historical_stats.get(symbol)
            if stats:
                for ex, count in stats.buy_exchange_counts.items():
                    buy_scores[ex] += count
                for ex, count in stats.sell_exchange_counts.items():
                    sell_scores[ex] += count

        if not buy_scores or not sell_scores:
            equal_w = 1.0 / max(len(self._active_exchanges), 1)
            all_ex = list(self._active_exchanges)
            return {
                "buyers": [(ex, equal_w) for ex in all_ex[:max_per_direction]],
                "sellers": [(ex, equal_w) for ex in all_ex[:max_per_direction]],
                "num_exchanges": min(len(all_ex), max_per_direction * 2),
            }

        def _select_top(
            scores: dict[str, float], max_n: int, direction: str = "buy"
        ) -> list[tuple[str, float]]:
            total = sum(scores.values())
            if total <= 0:
                equal_w = 1.0 / max(len(scores), 1)
                return [(ex, equal_w) for ex in list(scores)[:max_n]]
            weighted = [(ex, s / total) for ex, s in scores.items()]

            # Fee-weighted tie-breaking: prefer lower-fee exchanges
            if self._fee_manager:
                fees = {ex: self._fee_manager.get_scoring_fee(ex) for ex, _ in weighted}
                max_fee = max(fees.values(), default=0.001) or 0.001
                weighted = [
                    (ex, w * (1 + (max_fee - fees.get(ex, max_fee)) / max_fee))
                    for ex, w in weighted
                ]

            # Seller penalty: USDT accumulates on sell exchanges, so penalize
            # those with high withdrawal fees (capital gets trapped there).
            # Exchanges with fee > $0.20 get weight reduced by up to 50%.
            if direction == "sell" and self._balance:
                for i, (ex, w) in enumerate(weighted):
                    wfee = self._balance._get_withdrawal_fee(ex, 100.0)
                    if wfee > 0.20:
                        penalty = min(0.5, wfee)  # up to 50% penalty
                        weighted[i] = (ex, w * (1 - penalty))

            weighted.sort(key=lambda x: x[1], reverse=True)
            # Take top N, ignoring < 2% weight exchanges
            selected = []
            for ex, w in weighted:
                if len(selected) >= max_n:
                    break
                if w < 0.02 and selected:
                    break
                selected.append((ex, w))
            return selected if selected else weighted[:1]

        buyers = _select_top(buy_scores, max_per_direction, "buy")
        sellers = _select_top(sell_scores, max_per_direction, "sell")
        all_exchanges = {ex for ex, _ in buyers} | {ex for ex, _ in sellers}

        return {
            "buyers": buyers,
            "sellers": sellers,
            "num_exchanges": len(all_exchanges),
        }

    def _get_symbol_exchanges(self, symbol: str) -> set[str]:
        """Return the set of exchanges relevant for this symbol."""
        pairs = self._dominant_pairs.get(symbol)
        if not pairs:
            return set(self._active_exchanges)
        buyers = {ex for ex, _ in pairs["buyers"]}
        sellers = {ex for ex, _ in pairs["sellers"]}
        return buyers | sellers

    def _reevaluate_dominant_pairs(self) -> None:
        """Re-check dominant exchange pairs for active symbols, reallocate if shifted."""
        if not self._rotation_budget_ok:
            return

        now = time.time()
        realloc_cooldown = self._evaluation_interval * 3

        for sym in list(self._active_symbols):
            old_pairs = self._dominant_pairs.get(sym)
            if not old_pairs:
                # Determine max exchanges based on score tier
                score_obj = self._scores.get(sym)
                score_val = score_obj.score if score_obj else 0.0
                if score_val >= self._very_strong_threshold:
                    max_dir = 3
                elif score_val >= self._strong_threshold:
                    max_dir = 2
                else:
                    max_dir = 2  # min 2 to avoid over-concentration on 1 pair
                self._dominant_pairs[sym] = self._compute_dominant_pairs(sym, max_per_direction=max_dir)
                continue

            # Check cooldown
            last = self._last_reallocation.get(sym, 0.0)
            if now - last < realloc_cooldown:
                continue

            score_obj = self._scores.get(sym)
            score_val = score_obj.score if score_obj else 0.0
            if score_val >= self._very_strong_threshold:
                max_dir = 3
            elif score_val >= self._strong_threshold:
                max_dir = 2
            else:
                max_dir = 2  # min 2 to avoid over-concentration on 1 pair
            new_pairs = self._compute_dominant_pairs(sym, max_per_direction=max_dir)
            old_sellers = {ex for ex, _ in old_pairs["sellers"]}
            new_sellers = {ex for ex, _ in new_pairs["sellers"]}
            old_buyers = {ex for ex, _ in old_pairs["buyers"]}
            new_buyers = {ex for ex, _ in new_pairs["buyers"]}

            if old_sellers != new_sellers or old_buyers != new_buyers:
                self._reallocate_symbol(sym, old_pairs, new_pairs)
                self._dominant_pairs[sym] = new_pairs
                self._last_reallocation[sym] = now

    def _reallocate_symbol(
        self, symbol: str, old_pairs: dict, new_pairs: dict
    ) -> None:
        """Move capital for a symbol from old dominant exchanges to new ones."""
        from balance import Transfer

        prices = self._get_all_prices()
        price = prices.get(symbol, 0.0)
        if price <= 0:
            return

        now = time.time()
        old_sellers = {ex for ex, _ in old_pairs["sellers"]}
        new_sellers = {ex for ex, _ in new_pairs["sellers"]}
        removed_sellers = old_sellers - new_sellers
        added_sellers = new_sellers - old_sellers

        if not removed_sellers and not added_sellers:
            return

        # --- Cost estimation gate ---
        est_sell_cost = 0.0
        for ex in removed_sellers:
            qty = self._balance.crypto[ex].get(symbol, 0.0)
            if qty > 0:
                fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
                est_sell_cost += qty * price * fee_rate

        est_buy_cost = 0.0
        freed_est = sum(
            self._balance.crypto[ex].get(symbol, 0.0) * price
            for ex in removed_sellers
        )
        if freed_est > 0 and added_sellers:
            per_new = freed_est / len(added_sellers)
            for ex in added_sellers:
                fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
                est_buy_cost += per_new * fee_rate

        total_est_cost = est_sell_cost + est_buy_cost
        score_obj = self._scores.get(symbol)
        est_hourly = score_obj.est_hourly_profit if score_obj else 0.0
        benefit = est_hourly * self._reallocation_cost_horizon

        if total_est_cost > benefit and total_est_cost > 0.001:
            logger.info(
                f"[Optimizer] Reallocation SKIPPED for {symbol}: "
                f"est_cost=${total_est_cost:.4f} > benefit=${benefit:.4f} "
                f"(hourly=${est_hourly:.4f} x {self._reallocation_cost_horizon}h)"
            )
            return

        # Sell crypto on exchanges no longer dominant
        freed_capital = 0.0
        total_fee = 0.0
        for ex in removed_sellers:
            qty = self._balance.crypto[ex].get(symbol, 0.0)
            if qty > 0:
                fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
                gross = qty * price
                fee = gross * fee_rate
                self._balance.crypto[ex][symbol] = 0.0
                self._balance.usdt[ex] += gross - fee
                total_fee += fee
                freed_capital += gross - fee
                self._balance.transfers.append(
                    Transfer(
                        timestamp=now,
                        transfer_type="realloc_sell",
                        from_exchange=ex,
                        to_exchange=ex,
                        symbol=symbol,
                        amount_usd=gross,
                        fee_usd=fee,
                    )
                )

        # Buy crypto on newly dominant exchanges (use USDT already on those exchanges)
        if freed_capital > 0 and added_sellers:
            per_new = freed_capital / len(added_sellers)
            for ex in added_sellers:
                avail = self._balance.usdt.get(ex, 0.0)
                alloc = min(per_new, avail)
                if alloc < 1.0:
                    continue
                fee_rate = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
                fee = alloc * fee_rate
                qty = (alloc - fee) / price
                self._balance.usdt[ex] -= alloc
                if symbol not in self._balance.crypto[ex]:
                    self._balance.crypto[ex][symbol] = 0.0
                self._balance.crypto[ex][symbol] += qty
                total_fee += fee
                self._balance.transfers.append(
                    Transfer(
                        timestamp=now,
                        transfer_type="realloc_buy",
                        from_exchange=ex,
                        to_exchange=ex,
                        symbol=symbol,
                        amount_usd=alloc,
                        fee_usd=fee,
                    )
                )

        self._balance.total_transfer_fees += total_fee
        old_str = ",".join(old_sellers)
        new_str = ",".join(new_sellers)
        logger.info(
            f"[Optimizer] Reallocated {symbol}: sellers [{old_str}]→[{new_str}], "
            f"fees: ${total_fee:.4f}"
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_all_prices(self) -> dict[str, float]:
        """Get mid prices for all symbols from active exchange fetchers."""
        prices: dict[str, float] = {}
        for sym in self._all_symbols:
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

    # ── Dashboard Interface ──────────────────────────────────────────────

    def get_rankings(self) -> list[dict]:
        """Return symbol scores sorted by score, active symbols pinned to top."""
        if not self._scores:
            return []
        active_set = set(self._active_symbols)
        all_scores = list(self._scores.values())

        # Split into active and non-active, sort each by score
        active = sorted(
            [s for s in all_scores if s.symbol in active_set],
            key=lambda s: s.score,
            reverse=True,
        )
        non_active = sorted(
            [s for s in all_scores if s.symbol not in active_set],
            key=lambda s: s.score,
            reverse=True,
        )
        ranked = active + non_active

        now = time.time()
        return [
            {
                "rank": i + 1,
                "symbol": s.symbol,
                "score": round(s.score, 6),
                "avg_net_pct": round(s.avg_net_pct, 4),
                "avg_profitable_net": round(s.avg_profitable_net, 4),
                "profitable_ticks": s.profitable_ticks,
                "total_ticks": s.total_ticks,
                "frequency": round(s.frequency, 4),
                "best_net_pct": round(s.best_net_pct, 4),
                "est_hourly_profit": round(s.est_hourly_profit, 6),
                "is_active": s.symbol in active_set,
                "trade_multiplier": round(s.trade_multiplier, 2),
                "allocated_trade_size": round(self._trade_amount * s.trade_multiplier, 2),
                "cooldown_remaining": round(max(0.0, self._demotion_cooldown - (now - self._recently_demoted[s.symbol]))) if s.symbol in self._recently_demoted else 0,
                "focus_tier": s.focus_tier,
                "dominant_buyers": [ex for ex, _ in self._dominant_pairs[s.symbol]["buyers"]] if s.symbol in self._dominant_pairs else [],
                "dominant_sellers": [ex for ex, _ in self._dominant_pairs[s.symbol]["sellers"]] if s.symbol in self._dominant_pairs else [],
                "current_net_pct": round(self._ticks[s.symbol][-1].best_net_pct, 4) if s.symbol in self._ticks and self._ticks[s.symbol] else 0.0,
            }
            for i, s in enumerate(ranked)
        ]

    def get_rotations(self) -> list[dict]:
        """Return rotation history for the dashboard."""
        return [
            {
                "timestamp": r.timestamp,
                "old_symbol": r.old_symbol,
                "new_symbol": r.new_symbol,
                "old_score": round(r.old_score, 6),
                "new_score": round(r.new_score, 6),
                "switching_cost_usd": round(r.switching_cost_usd, 4),
                "est_hourly_improvement_usd": round(
                    r.est_hourly_improvement_usd, 6
                ),
            }
            for r in reversed(self._rotations[-50:])
        ]

    def get_exchange_rankings(self) -> list[dict]:
        """Return per-exchange profitability rankings from rolling window data."""
        # Aggregate from all symbol ticks
        ex_buy_count: dict[str, int] = defaultdict(int)
        ex_sell_count: dict[str, int] = defaultdict(int)
        ex_profit_sum: dict[str, float] = defaultdict(float)
        ex_total_ticks: dict[str, int] = defaultdict(int)

        for sym_ticks in self._ticks.values():
            for tick in sym_ticks:
                if tick.best_net_pct > 0:
                    ex_buy_count[tick.buy_exchange] += 1
                    ex_sell_count[tick.sell_exchange] += 1
                    ex_profit_sum[tick.buy_exchange] += tick.best_net_pct
                    ex_profit_sum[tick.sell_exchange] += tick.best_net_pct
                ex_total_ticks[tick.buy_exchange] += 1
                ex_total_ticks[tick.sell_exchange] += 1

        # Also track exchange pair rankings
        pair_count: dict[tuple[str, str], int] = defaultdict(int)
        pair_profit: dict[tuple[str, str], float] = defaultdict(float)
        for sym_ticks in self._ticks.values():
            for tick in sym_ticks:
                if tick.best_net_pct > 0:
                    pair = (tick.buy_exchange, tick.sell_exchange)
                    pair_count[pair] += 1
                    pair_profit[pair] += tick.best_net_pct

        all_exchanges = set(ex_total_ticks.keys())
        exchange_list = []
        for ex in sorted(all_exchanges):
            buys = ex_buy_count.get(ex, 0)
            sells = ex_sell_count.get(ex, 0)
            total = buys + sells
            profit = ex_profit_sum.get(ex, 0)
            fee = self._fee_manager.get_taker_fee(ex) if self._fee_manager else 0.001
            exchange_list.append({
                "exchange": ex,
                "as_buyer": buys,
                "as_seller": sells,
                "total_involvement": total,
                "profit_sum": round(profit, 4),
                "fee_pct": round(fee * 100, 3),
            })
        exchange_list.sort(key=lambda x: x["profit_sum"], reverse=True)

        pair_list = []
        for (buy_ex, sell_ex), count in sorted(
            pair_count.items(), key=lambda x: pair_profit[x[0]], reverse=True
        )[:10]:
            pair_list.append({
                "buy_exchange": buy_ex,
                "sell_exchange": sell_ex,
                "trades": count,
                "profit_sum": round(pair_profit[(buy_ex, sell_ex)], 4),
            })

        return {
            "exchanges": exchange_list,
            "pairs": pair_list,
        }

    def get_historical_rankings(self) -> list[dict]:
        """Return all-time symbol stats for the dashboard."""
        now = time.time()
        session_duration = now - self._session_start if self._session_start else 1.0
        active_set = set(self._active_symbols)
        result = []

        for sym, stats in self._historical_stats.items():
            if stats.total_ticks == 0:
                continue

            duration = stats.last_seen - stats.first_seen if stats.first_seen > 0 else 1.0
            hours = max(duration / 3600, 1 / 3600)  # avoid division by zero
            est_hourly = stats.est_total_profit / hours

            # Get rolling score for trend comparison
            rolling = self._scores.get(sym)
            rolling_score = rolling.score if rolling else 0.0
            trend = rolling_score - stats.all_time_score

            # Active duration: include current stint if active
            active_dur = stats.total_active_duration
            if sym in active_set and stats.last_activated_at > 0:
                active_dur += now - stats.last_activated_at

            # Strong/very_strong duration: include current stint
            strong_dur = stats.total_strong_duration
            if sym in self._prev_strong_set and stats.last_strong_at > 0:
                strong_dur += now - stats.last_strong_at

            very_strong_dur = stats.total_very_strong_duration
            if sym in self._prev_very_strong_set and stats.last_very_strong_at > 0:
                very_strong_dur += now - stats.last_very_strong_at

            result.append({
                "symbol": sym,
                "all_time_score": round(stats.all_time_score, 6),
                "rolling_score": round(rolling_score, 6),
                "trend": round(trend, 6),
                "total_profitable_ticks": stats.total_profitable_ticks,
                "total_ticks": stats.total_ticks,
                "overall_frequency": round(stats.overall_frequency, 4),
                "avg_net_pct": round(stats.avg_net_pct, 4),
                "avg_profitable_net": round(stats.avg_profitable_net, 4),
                "best_net_pct": round(stats.best_net_pct, 4),
                "worst_net_pct": round(stats.worst_net_pct, 4),
                "est_total_profit": round(stats.est_total_profit, 6),
                "est_hourly_rate": round(est_hourly, 6),
                "longest_profitable_streak": stats.longest_profitable_streak,
                "longest_unprofitable_streak": stats.longest_unprofitable_streak,
                "times_became_candidate": stats.times_became_candidate,
                "times_entered_watchlist": stats.times_entered_watchlist,
                "times_confirmed": stats.times_confirmed,
                "times_activated": stats.times_activated,
                "times_demoted": stats.times_demoted,
                "total_active_duration": round(active_dur, 1),
                "times_became_strong": stats.times_became_strong,
                "times_became_very_strong": stats.times_became_very_strong,
                "total_strong_duration": round(strong_dur, 1),
                "total_very_strong_duration": round(very_strong_dur, 1),
                "is_active": sym in active_set,
                "buy_exchange_counts": dict(stats.buy_exchange_counts),
                "sell_exchange_counts": dict(stats.sell_exchange_counts),
            })

        result.sort(key=lambda x: x["all_time_score"], reverse=True)
        return result

    def get_historical_exchange_rankings(self) -> list[dict]:
        """Return cumulative exchange stats for the dashboard."""
        result = []
        for ex_name, stats in self._historical_exchange_stats.items():
            result.append({
                "exchange": stats.exchange,
                "total_buy_ticks": stats.total_buy_ticks,
                "total_sell_ticks": stats.total_sell_ticks,
                "total_profit_sum": round(stats.total_profit_sum, 4),
                "total_involvement": stats.total_involvement,
            })
        result.sort(key=lambda x: x["total_profit_sum"], reverse=True)
        return result

    def get_watchlist(self) -> list[dict]:
        """Return current watchlist entries for the dashboard."""
        now = time.time()
        result = []
        for sym, entry in self._watchlist.items():
            elapsed = now - entry.entered_at
            progress = min(100.0, elapsed / self._confirmation_period * 100) if self._confirmation_period > 0 else 100.0
            avg_score = sum(entry.score_samples) / len(entry.score_samples) if entry.score_samples else 0.0
            result.append({
                "symbol": sym,
                "watching_since": entry.entered_at,
                "elapsed": round(elapsed, 1),
                "progress": round(progress, 1),
                "confirmed": entry.confirmed,
                "avg_score": round(avg_score, 6),
            })
        result.sort(key=lambda x: x["avg_score"], reverse=True)
        return result

    def should_allow_rebalance(self, symbol: str) -> bool:
        """Check if a symbol's score is high enough to justify transfer fees.

        Any tradeable symbol (score >= 0.01) is allowed to rebalance.
        The ROI gate, net P&L gate, and transfer worthiness checks in
        monitor/balance already protect against unprofitable transfers.
        """
        score = self._scores.get(symbol)
        if not score:
            return False
        return score.score >= self._trading_threshold

    def get_symbol_score(self, symbol: str) -> SymbolScore | None:
        """Return the current rolling score for a symbol."""
        return self._scores.get(symbol)

    @property
    def active_symbols(self) -> list[str]:
        return list(self._active_symbols)

    def reset(
        self,
        active_symbols: list[str] | None = None,
        active_exchanges: list[str] | None = None,
        trade_amount: float | None = None,
        num_active_symbols: int | None = None,
        scoring_window: int | None = None,
        evaluation_interval: int | None = None,
        safety_multiplier: float | None = None,
        auto_rotate: bool | None = None,
    ) -> None:
        """Reset optimizer state (called when settings change).

        Historical stats are NOT cleared — they persist for the entire session.
        """
        # Accumulate active duration for currently active symbols before reset
        now = time.time()
        active_set = set(self._active_symbols)
        for sym in active_set:
            stats = self._historical_stats.get(sym)
            if stats and stats.last_activated_at > 0:
                stats.total_active_duration += now - stats.last_activated_at
                stats.last_activated_at = 0.0

        if active_symbols is not None:
            self._active_symbols = list(active_symbols)
        if active_exchanges is not None:
            self._active_exchanges = set(active_exchanges)
        if trade_amount is not None:
            self._trade_amount = trade_amount
        if num_active_symbols is not None:
            self._min_active_symbols = num_active_symbols
        if scoring_window is not None:
            self._scoring_window = scoring_window
        if evaluation_interval is not None:
            self._evaluation_interval = evaluation_interval
        if safety_multiplier is not None:
            self._safety_multiplier = safety_multiplier
        if auto_rotate is not None:
            self._auto_rotate = auto_rotate

        # Clear rolling windows (NOT historical stats)
        for dq in self._ticks.values():
            dq.clear()
        self._scores.clear()
        self._rotations.clear()
        self._watchlist.clear()
        self._demotion_tracking.clear()
        self._prev_candidate_set.clear()
        self._tick_count = 0
        self._last_evaluation = time.time()

        # Restart discovery if auto_rotate is on
        self._discovery_mode = self._auto_rotate
        self._discovery_complete = not self._auto_rotate
        self._discovery_start = time.time()
        self._exchange_profit_ticks.clear()
        self._exchange_profit_sum.clear()
        self._exchange_buy_ticks.clear()
        self._exchange_sell_ticks.clear()
        if self._discovery_mode:
            self._monitor._paused = True
            logger.info(
                f"[Optimizer] Reset + Discovery restart: "
                f"{self._discovery_duration}s, top {self._min_active_symbols} symbols"
            )
        else:
            logger.info(
                f"[Optimizer] Reset: top {self._min_active_symbols} symbols, "
                f"window={self._scoring_window}s, auto_rotate={self._auto_rotate}"
            )

    # ── State persistence ────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize all mutable session state."""
        from dataclasses import asdict

        return {
            "_active_symbols": list(self._active_symbols),
            "_rotations": [asdict(r) for r in self._rotations],
            "_historical_stats": {
                sym: asdict(stats)
                for sym, stats in self._historical_stats.items()
                if stats.total_ticks > 0
            },
            "_historical_exchange_stats": {
                ex: asdict(stats)
                for ex, stats in self._historical_exchange_stats.items()
            },
            "_watchlist": {
                sym: {
                    "symbol": e.symbol,
                    "entered_at": e.entered_at,
                    "confirmation_start": e.confirmation_start,
                    "score_samples": e.score_samples,
                    "confirmed": e.confirmed,
                }
                for sym, e in self._watchlist.items()
            },
            "_demotion_tracking": dict(self._demotion_tracking),
            "_recently_demoted": dict(self._recently_demoted),
            "_dominant_pairs": dict(self._dominant_pairs),
            "_last_reallocation": dict(self._last_reallocation),
            "_tick_count": self._tick_count,
            "_session_start": self._session_start,
            "_discovery_mode": self._discovery_mode,
            "_discovery_complete": self._discovery_complete,
            "_discovery_start": self._discovery_start,
            "_discovery_duration": self._discovery_duration,
            "_exchange_profit_ticks": dict(self._exchange_profit_ticks),
            "_exchange_profit_sum": dict(self._exchange_profit_sum),
            "_exchange_buy_ticks": dict(self._exchange_buy_ticks),
            "_exchange_sell_ticks": dict(self._exchange_sell_ticks),
            "_prev_strong_set": list(self._prev_strong_set),
            "_prev_very_strong_set": list(self._prev_very_strong_set),
            "_prev_candidate_set": list(self._prev_candidate_set),
        }

    def from_state_dict(self, data: dict) -> None:
        """Restore session state from a saved dict."""
        self._active_symbols = data.get("_active_symbols", self._active_symbols)
        self._rotations = [
            RotationEvent(**r) for r in data.get("_rotations", [])
        ]
        for sym, stats_dict in data.get("_historical_stats", {}).items():
            self._historical_stats[sym] = HistoricalSymbolStats(**stats_dict)
        for ex, stats_dict in data.get("_historical_exchange_stats", {}).items():
            self._historical_exchange_stats[ex] = HistoricalExchangeStats(**stats_dict)
        self._watchlist = {
            sym: WatchlistEntry(**entry)
            for sym, entry in data.get("_watchlist", {}).items()
        }
        self._demotion_tracking = data.get("_demotion_tracking", {})
        self._recently_demoted = data.get("_recently_demoted", {})
        self._dominant_pairs = data.get("_dominant_pairs", {})
        self._last_reallocation = data.get("_last_reallocation", {})
        self._tick_count = data.get("_tick_count", 0)
        self._session_start = data.get("_session_start", self._session_start)
        self._discovery_mode = data.get("_discovery_mode", self._discovery_mode)
        self._discovery_complete = data.get(
            "_discovery_complete", self._discovery_complete
        )
        self._discovery_start = data.get("_discovery_start", self._discovery_start)
        self._discovery_duration = data.get(
            "_discovery_duration", self._discovery_duration
        )
        self._exchange_profit_ticks = defaultdict(
            int, data.get("_exchange_profit_ticks", {})
        )
        self._exchange_profit_sum = defaultdict(
            float, data.get("_exchange_profit_sum", {})
        )
        self._exchange_buy_ticks = defaultdict(
            int, data.get("_exchange_buy_ticks", {})
        )
        self._exchange_sell_ticks = defaultdict(
            int, data.get("_exchange_sell_ticks", {})
        )
        self._prev_strong_set = set(data.get("_prev_strong_set", []))
        self._prev_very_strong_set = set(data.get("_prev_very_strong_set", []))
        self._prev_candidate_set = set(data.get("_prev_candidate_set", []))

        # If discovery was in progress when saved, reset for fresh restart.
        # Rolling scores (_scores dict) are NOT persisted, so resuming discovery
        # with stale timestamps and tick counts produces incorrect results.
        if self._discovery_mode and not self._discovery_complete:
            self._discovery_start = 0.0  # run() will set to time.time()
            self._discovery_duration = self._initial_discovery_duration
            self._tick_count = 0
            # Clear stale exchange profitability data (matches empty scores)
            self._exchange_profit_ticks = defaultdict(int)
            self._exchange_profit_sum = defaultdict(float)
            self._exchange_buy_ticks = defaultdict(int)
            self._exchange_sell_ticks = defaultdict(int)
            logger.info(
                "[Optimizer] Discovery was in progress — resetting timer for fresh restart"
            )
