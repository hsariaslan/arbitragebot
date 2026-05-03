"""
Automatic symbol rotation optimizer for ArbitrageBot.

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
from typing import TYPE_CHECKING, ClassVar

from config import (
    AUTO_EXPAND_ON_UNDERSTAFF,
    BITFINEX_OVER_TARGET_ENABLED,
    BITFINEX_OVER_TARGET_MULTIPLIER,
    INVENTORY_DRIFT_THRESHOLD,
    INVENTORY_REBALANCE_ENABLED,
    INVENTORY_REBALANCE_INTERVAL_HOURS,
    MAX_DATA_AGE_SECONDS,
    MOMENTUM_FILTER_ENABLED,
    MOMENTUM_LOOKBACK_HOURS,
    MOMENTUM_MAX_FACTOR,
    MOMENTUM_MIN_FACTOR,
    MOMENTUM_SAMPLE_INTERVAL_MINUTES,
    SYMBOLS,
)
from slippage import compute_buy_slippage, compute_sell_slippage

if TYPE_CHECKING:
    from balance import BalanceTracker, Transfer
    from dashboard_server import DashboardServer
    from fee_manager import FeeManager
    from funding_monitor import FundingMonitor
    from fetchers.base import BaseFetcher
    from monitor import ArbitrageMonitor

logger = logging.getLogger(__name__)

# Score thresholds for tiered behavior (module-level defaults)
TRADING_SCORE_THRESHOLD = 0.01     # trading + rebalance gate (minimum to trade/transfer)
STRONG_SCORE_THRESHOLD = 0.1       # strong tier (higher multiplier, more exchanges)
VERY_STRONG_SCORE_THRESHOLD = 0.3  # very strong tier (highest multiplier, most exchanges)
FEE_THRESHOLD_MULTIPLIER = 0.5     # activation threshold scales with pair fee excess over cheapest


@dataclass(slots=True)
class SymbolTick:
    """Single observation of best cross-exchange opportunity for a symbol.

    `slots=True` is critical here: at 48 configs × 60 symbols ×
    `scoring_window` (1800) ticks, the bot accumulates ~5 million live
    instances at steady state. Without slots, each instance carries a
    full `__dict__` (~224B overhead just for the dict header) —
    that's ~1.1 GB of dict overhead alone. With slots: ~80B/instance
    total. ~75% memory reduction. The Python GC also tracks fewer
    container objects, cutting gen2 collection time proportionally.
    Observed in the 19:45-20:01 trace: per_cfg time grew 25× as the
    deques filled, dominated by gen2 GC pauses during tick_once.
    """

    timestamp: float
    best_net_pct: float
    buy_exchange: str
    sell_exchange: str
    spread_pct: float
    fee_pct: float


@dataclass(slots=True)
class SymbolScore:
    """Computed score for a symbol over the rolling window.

    `slots=True`: 60 SymbolScore instances are allocated per config per
    tick in `_compute_scores`. At 48 configs that's 2,880 allocations
    per second. Without slots, each instance carries a ~224B __dict__
    overhead. Slots cut per-instance memory ~75% AND reduce GC load
    (fewer attribute dicts to track). Pairs with the SymbolTick slots
    fix to control the heap growth rate the diagnostic exposed.
    """

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
    """Tracks a strong candidate symbol being observed for confirmation.

    `score_samples` is kept as a `list` (multiple call sites use
    `samples[-N:]` slice notation, which deque doesn't support). It's
    bounded by trimming-on-append at the writer sites: the trajectory
    classifier reads the last 30, stability checks read the last 3-5,
    so capping at 60 is plenty. Pre-cap this was unbounded: at 48
    configs × ~5 watchlist candidates × 1 sample/sec, after 30 min the
    cumulative size hit ~432K floats, with linear scans on every read
    — observed as the slow ~13ms/min creep in sweep time even after
    the optimizer aggregates fix.
    """

    SAMPLES_MAX: ClassVar[int] = 60

    symbol: str
    entered_at: float
    confirmation_start: float
    score_samples: list[float] = field(default_factory=list)
    peak_score: float = 0.0
    confirmed: bool = False

    def add_sample(self, score: float) -> None:
        """Append + trim. Use this instead of `score_samples.append()`."""
        s = self.score_samples
        s.append(score)
        if len(s) > self.SAMPLES_MAX:
            # Slice-assign keeps the same list object so any external
            # references (e.g. `samples = entry.score_samples`) stay valid.
            del s[:-self.SAMPLES_MAX]


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
        score_stability_seconds: int = 120,
        score_stability_factor: float = 0.5,
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
        # v0.31: tick_once() can be called from either run() or the
        # multi-config orchestrator. Track first-tick startup separately
        # so we log the startup line exactly once per component lifetime.
        self._startup_logged = False

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
        self._score_stability_seconds = score_stability_seconds
        self._score_stability_factor = score_stability_factor

        # Per-symbol demotion history for frequency-aware cooldown scaling.
        # The same symbol cycling through activate→demote→re-activate is
        # the worst churn pattern: each cycle pays setup+teardown fees
        # (~$0.30-1.00) without proportional trade volume. Track 24h
        # rolling demotion count per symbol; scale cooldown geometrically
        # so problem symbols self-lockout for the day. Operator can
        # disable via `demotion_freq_scaling_enabled` setting.
        self._demotion_history: dict[str, list[float]] = {}
        self._demotion_freq_scaling_enabled: bool = True

        # Reallocation cost gate
        self._reallocation_cost_horizon = reallocation_cost_horizon
        # Activation profitability bar — multiplier applied on top of
        # `reallocation_cost_horizon` for SETUP costs (vs reallocation
        # costs which keep using the base horizon). Tighter setting means
        # marginal symbols don't activate. Default 2.0 = same behavior
        # as before; higher = stricter. Per-config tunable.
        self._activation_profit_horizon_multiplier: float = 2.0

        # Configurable score thresholds (settable from dashboard)
        self._trading_threshold: float = TRADING_SCORE_THRESHOLD
        self._strong_threshold: float = STRONG_SCORE_THRESHOLD
        self._very_strong_threshold: float = VERY_STRONG_SCORE_THRESHOLD
        self._fee_threshold_multiplier: float = FEE_THRESHOLD_MULTIPLIER

        # Event-driven seller penalty for scoring (mirrors monitor's execution penalty)
        self._event_driven_exchanges: set[str] = {
            f.exchange_name for f in fetchers if getattr(f, "IS_EVENT_DRIVEN", False)
        }
        self._event_driven_seller_penalty: float = 0.05  # synced from settings via dashboard

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

        # Incremental aggregates over the rolling window — maintained at
        # the two `_ticks` mutation sites (append in `_score_tick`,
        # popleft in the prune loop). This keeps `_compute_scores` O(1)
        # per symbol instead of O(window). At full window (1800 entries)
        # × 60 symbols × 48 configs the previous single-pass cost ~5M
        # element scans/sweep — visible as progressive sweep-time growth
        # over the first 30 minutes as deques filled (1500ms → 2140ms
        # observed in the 16:22 log). With incremental aggregates the
        # cost is constant regardless of window size.
        #
        # `best_net` is the only aggregate that can't be incrementally
        # decreased on popleft, so it's tracked with a stale flag: on
        # popleft of a tick equal to the current max, we mark the symbol
        # stale and recompute lazily inside `_compute_scores`. Most
        # popleft events don't touch the max so the recompute is rare.
        self._agg_total: dict[str, int] = defaultdict(int)
        self._agg_sum_net: dict[str, float] = defaultdict(float)
        self._agg_prof_count: dict[str, int] = defaultdict(int)
        self._agg_prof_sum: dict[str, float] = defaultdict(float)
        # Monotonic max-deque: (timestamp, best_net_pct) pairs in
        # monotonically decreasing order by value. Front is always the
        # current max in the time window. Replaces the previous
        # `_best_net + _best_net_stale` lazy-recompute pattern, which
        # produced a sweep-time peak at deque saturation (~T+30-90min)
        # because many symbols simultaneously triggered O(window)
        # full-deque scans when the front-of-deque max evicted. With
        # the monotonic structure, max retrieval is O(1) and append +
        # popleft are O(1) amortized — no recompute path exists.
        self._best_net_dq: dict[str, deque[tuple[float, float]]] = defaultdict(deque)

        # Latest computed scores
        self._scores: dict[str, SymbolScore] = {}

        # Per-symbol score history — updated every tick for ALL symbols (not
        # tied to watchlist). Used by `_classify_trajectory` so trajectory
        # stays current for active symbols too. (Bug fixed v0.30.5: watchlist
        # samples were frozen post-activation, making active symbols always
        # show their last-discovery trend even after they'd been declining
        # for tens of minutes.)
        self._score_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=120))

        # Last-known Bitfinex bid per symbol, updated each tick when a
        # Bitfinex quote is observed in `_score_tick`. Used by
        # `_execute_demotion` to route through Bitfinex 0% even when the
        # current Bitfinex feed has a brief gap (event-driven update can
        # be 10-20s stale; without this cache, demotion sells fall back
        # to local-exchange taker fees — observed in S27: PENDLE demoted
        # locally on MEXC at 0.04% taker = $0.18 fee, vs $0.00 if routed
        # via Bitfinex). v0.30.7-beta.
        self._bitfinex_last_bid: dict[str, float] = {}
        self._prev_candidate_set: set[str] = set()  # for tracking candidate transitions
        self._prev_strong_set: set[str] = set()     # score >= 0.1 last tick
        self._prev_very_strong_set: set[str] = set()  # score >= 0.3 last tick

        # Rotation history
        self._rotations: list[RotationEvent] = []

        # Timing
        self._last_evaluation: float = 0.0
        # Throttle for fast-track-related INFO logs (fire once per 30s
        # per config when the candidate is at the threshold-but-unstable
        # boundary; without this the tight loop fires both logs every tick).
        self._last_fast_track_log: float = 0.0
        # Throttle for the "trading float overflow blocked" log — when
        # the custody hub is unreachable (e.g. disabled in a Lean config),
        # this condition holds indefinitely and the log otherwise fires
        # every tick.
        self._last_overflow_blocked_log: float = 0.0
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

        # Price momentum filter (Feature 3)
        self._momentum_filter_enabled: bool = MOMENTUM_FILTER_ENABLED
        self._momentum_lookback_seconds: float = MOMENTUM_LOOKBACK_HOURS * 3600
        self._momentum_sample_interval: float = MOMENTUM_SAMPLE_INTERVAL_MINUTES * 60
        self._momentum_min_factor: float = MOMENTUM_MIN_FACTOR
        self._momentum_max_factor: float = MOMENTUM_MAX_FACTOR
        self._price_history: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
        self._last_momentum_log: dict[str, float] = {}

        # Periodic inventory rebalance (Feature 4)
        self._inventory_rebalance_enabled: bool = INVENTORY_REBALANCE_ENABLED
        self._inventory_rebalance_interval: float = INVENTORY_REBALANCE_INTERVAL_HOURS * 3600
        self._inventory_drift_threshold: float = INVENTORY_DRIFT_THRESHOLD
        self._last_inventory_rebalance: float = 0.0

        # Bitfinex over-target redistribution (Feature 5)
        self._bitfinex_over_target_enabled: bool = BITFINEX_OVER_TARGET_ENABLED
        self._bitfinex_over_target_multiplier: float = BITFINEX_OVER_TARGET_MULTIPLIER

        # Auto-expand on understaff (Feature 6)
        self._auto_expand_on_understaff: bool = AUTO_EXPAND_ON_UNDERSTAFF
        self._last_auto_expand_attempt: float = 0.0

        # Time-based regime gating (mirrors monitor settings). When weak
        # hours are active, demotion + auto-expand are suppressed to
        # avoid the activate→demote→reactivate fee churn observed in
        # the 04:00 UTC funding-settlement event of 2026-05-03 (216
        # transfers in one minute, $1+/config in fees during a 2-trade
        # session). Each per-config bundle has its own regime config so
        # aggressive configs can stay active while conservative ones
        # idle through thin windows.
        self._regime_gating_enabled: bool = False
        self._regime_strong_hours: set[int] = {7, 15, 20, 21, 22}
        self._regime_neutral_hours: set[int] = {0, 1, 5, 6, 8, 9, 11}
        self._regime_weak_disable_demote: bool = True
        self._regime_weak_disable_expand: bool = True

        # Diversification floor (S21 follow-up). When understaffed, multiply
        # activation threshold by `_diversification_floor_multiplier` so
        # marginal candidates can clear the gate. Hot-applied via dashboard.
        from config import DIVERSIFICATION_FLOOR_ENABLED, DIVERSIFICATION_FLOOR_MULTIPLIER
        self._diversification_floor_enabled: bool = DIVERSIFICATION_FLOOR_ENABLED
        self._diversification_floor_multiplier: float = DIVERSIFICATION_FLOOR_MULTIPLIER

        # Fast-track discovery exit (S29 follow-up). Trajectory-aware exit:
        # rising/stable candidates activate sooner than declining ones, with
        # tier-based time requirements scaled by aggressiveness multiplier.
        # See config.py FAST_TRACK_* docs for the timing matrix.
        from config import FAST_TRACK_DISCOVERY_ENABLED, FAST_TRACK_AGGRESSIVENESS
        self._fast_track_discovery_enabled: bool = FAST_TRACK_DISCOVERY_ENABLED
        self._fast_track_aggressiveness: float = FAST_TRACK_AGGRESSIVENESS

        # Funding-aware scoring (Phase A — set externally via set_funding_monitor)
        self._funding_monitor: "FundingMonitor | None" = None
        # Per-symbol throttle for [Optimizer] funding-applied summary log
        self._last_funding_log: dict[str, float] = {}

    def stop(self) -> None:
        self._running = False

    def set_dashboard(self, dashboard: "DashboardServer") -> None:
        """Store dashboard reference for post-discovery updates."""
        self._dashboard = dashboard

    def set_funding_monitor(self, monitor: "FundingMonitor") -> None:
        """Wire the live funding-rate monitor (Phase A scoring multiplier)."""
        self._funding_monitor = monitor

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

    def _ensure_started(self) -> None:
        """Initialize discovery_start / last_evaluation timestamps + log
        the first-tick startup line. Idempotent — safe to call from
        either `run()` or the multi-config orchestrator."""
        if not self._discovery_start:
            self._discovery_start = time.time()
        if not self._last_evaluation:
            self._last_evaluation = time.time()
        if not self._startup_logged:
            self._startup_logged = True
            if self._discovery_mode:
                self._monitor._paused = True
                # NOTE: DEBUG-level not enabled here — at 48 configs the
                # `[Candidate] WATCH` and `[Discovery]` debug lines flood
                # the log file (~15K lines / 15 min observed in 16:22
                # log) and grow sweep time. The discovery summary log
                # below is INFO and stays visible regardless.
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

    def tick_once(self) -> None:
        """Single optimizer tick (score + discovery + rotation + inventory + auto-expand).

        Extracted from `run()` so the multi-config Orchestrator can drive
        the tick rate directly.
        """
        self._ensure_started()
        self._score_tick()
        self._tick_count += 1

        now = time.time()

        # Discovery stage: check for tradeable candidates every tick, complete when duration elapses
        if self._discovery_mode and not self._discovery_complete:
            elapsed = now - self._discovery_start

            if self._tick_count >= self._min_warmup_ticks:
                # Standard early-exit: half a scoring window of observation.
                # Prevents inflated scores from thin windows (e.g., 100% freq
                # from 60 ticks vs real 55% from 1800 ticks).
                min_ticks_std = self._scoring_window // 2
                min_time_std = float(self._scoring_window // 2)

                # Fast-track (S29 follow-up): trajectory-aware exit. Per-tier
                # base times multiplied by aggressiveness; declining
                # candidates fall back to the standard wait.
                ft_enabled = self._fast_track_discovery_enabled
                ft_aggr = self._fast_track_aggressiveness

                def _qualifies(s) -> tuple[bool, str, float]:
                    """Return (qualifies_for_exit, path_kind, required_elapsed_seconds)."""
                    if s.score < self._get_activation_threshold(s.symbol):
                        return False, "", min_time_std
                    # Standard path always wins if eligible
                    if s.total_ticks >= min_ticks_std:
                        return True, "standard", min_time_std
                    if not ft_enabled:
                        return False, "", min_time_std

                    # Trajectory classification needs 30+ samples — use
                    # live per-symbol score history (works for active +
                    # candidates).
                    history = self._score_history.get(s.symbol)
                    wl = self._watchlist.get(s.symbol)
                    if not history or len(history) < 30:
                        return False, "", min_time_std

                    peak_for_traj = wl.peak_score if wl else max(history)
                    trajectory = self._classify_trajectory(history, peak_score=peak_for_traj)
                    if trajectory == "declining":
                        return False, "", min_time_std  # full wait

                    # Tier from current score (matches focus-tier classification)
                    if s.score >= self._strong_threshold:
                        # very_strong AND strong both use the same fast wait
                        tier_kind = "strong+"
                        base = 30.0 if trajectory == "rising" else 60.0
                    else:
                        tier_kind = "normal"
                        base = 240.0 if trajectory == "rising" else 300.0

                    required = base * ft_aggr

                    # Tier-confirmation gate: prevents activating on a brief
                    # single-tick spike into the tier. Last `required`
                    # samples (= seconds at 1Hz) must all be at the tier
                    # threshold. A symbol that was strong throughout
                    # discovery passes immediately; one that just
                    # transitioned waits until enough strong samples
                    # accumulate.
                    if tier_kind == "strong+":
                        n_check = int(required)
                        if len(history) < n_check:
                            return False, "", required
                        recent = list(history)[-n_check:]
                        if not all(x >= self._strong_threshold for x in recent):
                            return False, "", required

                    # Total ticks gate: at least as many ticks as seconds
                    if s.total_ticks < required:
                        return False, "", required
                    return True, f"fast_track_{tier_kind}_{trajectory}", required

                tradeable_found: list = []
                qualified_kind: str = ""
                qualified_required: float = min_time_std
                for s in self._scores.values():
                    ok, kind, required = _qualifies(s)
                    if ok:
                        tradeable_found.append(s)
                        # Prefer the standard kind in logs if any candidate
                        # qualifies via that path; otherwise show fast-track
                        # kind of the best (highest-score) candidate.
                        if not qualified_kind or "standard" in kind:
                            qualified_kind = kind
                            qualified_required = required
                tradeable_found.sort(key=lambda s: s.score, reverse=True)

                if tradeable_found and elapsed >= qualified_required:
                    names = ", ".join(
                        f"{s.symbol.replace('USDT', '')}({s.score:.4f})"
                        for s in tradeable_found[:5]
                    )
                    # When the stability gate keeps rejecting, this branch
                    # fires every tick. Throttle to once per 30s per config
                    # so we don't spam ~30 log lines/min × 48 configs at
                    # 40+ scale.
                    if now - self._last_fast_track_log >= 30.0:
                        self._last_fast_track_log = now
                        logger.info(
                            f"[Optimizer] {len(tradeable_found)} tradeable candidates "
                            f"found at {elapsed:.0f}s ({qualified_kind}): {names} — exiting discovery"
                        )
                    self._complete_discovery(from_fast_track=True)
                elif elapsed >= self._discovery_duration:
                    # Duration elapsed, none found — extend discovery
                    self._complete_discovery(from_fast_track=False)

                # During discovery, only consolidate from cheap sources
                # (skip KuCoin $0.40, Gate.io $0.50, OKX $0.10 — too expensive
                # when we don't know if next symbol will use Bitfinex)
                if (
                    now - self._last_evaluation >= self._evaluation_interval
                    and self._balance
                    and "Bitfinex" in self._balance._exchanges
                ):
                    transfers = self._balance.consolidate_to_custody_hub(
                        None, max_fee_per_source=0.02,
                    )
                    if transfers:
                        hub_fee = sum(t.fee_usd for t in transfers)
                        hub_amt = sum(t.amount_usd for t in transfers)
                        logger.info(
                            f"[Optimizer] Discovery consolidation (cheap only): "
                            f"{len(transfers)} transfers, ${hub_amt:.2f} to Bitfinex "
                            f"(fees: ${hub_fee:.4f}, max_fee=$0.02)"
                        )
                    self._balance.replenish_trading_float(max_fee_per_source=0.02)
                    self._last_evaluation = now

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

        # Quiet-period detection (consulted via monitor — single source).
        # When True, suppress rebalance-class transfers that aren't
        # producing matching trade volume. Disabled by default; when
        # enabled (`quiet_period_pause_minutes > 0`), the gate below
        # short-circuits inventory rebalance + overflow + replenish.
        in_quiet = self._monitor.in_quiet_period() if self._monitor else False

        # Periodic inventory drift rebalance (Feature 4)
        # `balance.initialized` gate prevents firing between reconfigure()
        # and initialize_crypto() — running there would see crypto=0
        # against the just-set target and DRIFT_BUY phantom crypto,
        # uncompensated when initialize_crypto() later overwrites the qty.
        if (
            self._inventory_rebalance_enabled
            and not self._discovery_mode
            and self._active_symbols
            and self._balance
            and self._balance.initialized
            and not in_quiet  # quiet-period: skip drift rebalance
            and now - self._last_inventory_rebalance >= self._inventory_rebalance_interval
        ):
            self._run_inventory_rebalance(now)
            self._last_inventory_rebalance = now

        # Trading float overflow → custody hub (v0.30+, was Feature 5)
        # Same initialized-gate as above: pre-init Bitfinex USDT
        # transiently includes the about-to-be-crypto allocation, so a
        # premature sweep would drain the planned crypto pool.
        if (
            self._bitfinex_over_target_enabled
            and not self._discovery_mode
            and self._active_symbols
            and self._balance
            and self._balance.initialized
            and not in_quiet  # quiet-period: skip float overflow sweep
            and "Bitfinex" in self._balance._exchanges
        ):
            self._consolidate_trading_float_overflow()

        # Auto-expand on understaff (Feature 6) — fire ASAP when active count < min
        if (
            self._auto_expand_on_understaff
            and self._auto_rotate
            and not self._discovery_mode
            and self._discovery_complete
            and self._tick_count >= self._min_warmup_ticks
            and len(self._active_symbols) < self._min_active_symbols
            and now - self._last_auto_expand_attempt >= 60.0  # max 1/minute
        ):
            self._auto_expand_on_understaff_tick(now)
            self._last_auto_expand_attempt = now

    async def run(self) -> None:
        """Legacy single-component loop. The multi-config Orchestrator drives
        `tick_once()` directly and skips this wrapper."""
        self._running = True
        self._ensure_started()
        while self._running:
            self.tick_once()
            await asyncio.sleep(1.0)

    # ── Scoring ──────────────────────────────────────────────────────────

    def _score_tick(self) -> None:
        """Compute best net spread for each symbol, append to rolling window."""
        now = time.time()

        # v0.31.0-beta+: read from the orchestrator's per-sweep prices cache
        # if one is set. Cuts 60 symbols × 9 fetchers × N configs of redundant
        # `fetcher.get_state()` work down to a single build per sweep, plus
        # gives us pre-parsed `bids_f` / `asks_f` for the slippage walker.
        from tick_cache import get_sweep_prices, filter_for_config
        sweep_prices = get_sweep_prices()

        for symbol in self._all_symbols:
            if sweep_prices is not None:
                # Shared-cache fast path: read pre-built tuples + filter
                # by this config's active exchanges.
                exchange_prices = filter_for_config(
                    sweep_prices, symbol, self._active_exchanges
                )
                # Bitfinex last-bid cache is per-config but the value is
                # identical across configs — replicate the legacy write
                # so demotion routing still works.
                for ex, bid_f, _, _, _ in exchange_prices:
                    if ex == "Bitfinex":
                        self._bitfinex_last_bid[symbol] = bid_f
                        break
            else:
                # Legacy single-config path: build per-tick from fetchers.
                exchange_prices = []
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
                        exchange_prices.append((fetcher.exchange_name, bid_f, ask_f, ps.bids, ps.asks))
                        if fetcher.exchange_name == "Bitfinex":
                            self._bitfinex_last_bid[symbol] = bid_f
                    except (ValueError, TypeError):
                        continue

            if len(exchange_prices) < 2:
                continue

            # v0.31 perf: pre-filter to exchanges that can either buy or
            # sell this symbol. With 80 configs running in parallel on a
            # 1 vCPU VPS, the inner pair-combinatorics loop is the hot
            # path; filtering early avoids ~30-50% of slippage compute
            # for symbols heavily auto-disabled (low <$10k/24h volume).
            buyers: set[str] = set()
            sellers: set[str] = set()
            if self._fee_manager:
                buyers = {
                    ex for (ex, _, _, _, _) in exchange_prices
                    if self._fee_manager.can_buy(ex, symbol)
                }
                sellers = {
                    ex for (ex, _, _, _, _) in exchange_prices
                    if self._fee_manager.can_sell(ex, symbol)
                }
                if not buyers or not sellers:
                    continue
                # Drop the entry if it can't act as either side
                exchange_prices = [
                    e for e in exchange_prices
                    if e[0] in buyers or e[0] in sellers
                ]
                if len(exchange_prices) < 2:
                    continue

            # Per-symbol scoring-fee memo. `get_scoring_fee(ex, symbol)`
            # is deterministic for the duration of this scoring tick;
            # the inner pair loop hits the same (ex, symbol) up to
            # 2*(N-1) times. One dict lookup vs full fee computation
            # is a meaningful win at 48 configs × 60 symbols × 72 pairs.
            fee_cache: dict[str, float] = {}

            # Track mid-price for momentum filter (Feature 3)
            mid_prices = [(b + a) / 2.0 for _, b, a, _, _ in exchange_prices]
            current_mid = sum(mid_prices) / len(mid_prices)
            self._record_price_sample(symbol, current_mid, now)

            # Find best cross-exchange spread
            best_net = float("-inf")
            best_buy = ""
            best_sell = ""
            best_spread = 0.0
            best_fee = 0.0

            for i, (ex_buy, _, ask_i, _bids_i, asks_i) in enumerate(exchange_prices):
                # Outer-leg block check: cheap set lookup using the
                # buyers set already computed above. Was a fee_manager
                # call per (i,j) pair — now once per i.
                if self._fee_manager and ex_buy not in buyers:
                    continue
                for j, (ex_sell, bid_j, _, bids_j, _asks_j) in enumerate(exchange_prices):
                    if i == j:
                        continue
                    # Inner-leg block check: same — set lookup vs call.
                    if self._fee_manager and ex_sell not in sellers:
                        continue
                    spread_pct = (bid_j - ask_i) / ask_i * 100
                    if self._fee_manager:
                        buy_fee = fee_cache.get(ex_buy)
                        if buy_fee is None:
                            buy_fee = self._fee_manager.get_scoring_fee(ex_buy, symbol)
                            fee_cache[ex_buy] = buy_fee
                        sell_fee = fee_cache.get(ex_sell)
                        if sell_fee is None:
                            sell_fee = self._fee_manager.get_scoring_fee(ex_sell, symbol)
                            fee_cache[ex_sell] = sell_fee
                    else:
                        buy_fee = 0.001
                        sell_fee = 0.001
                    fee_pct = (buy_fee + sell_fee) * 100

                    # Deduct estimated slippage from depth data
                    buy_slip = compute_buy_slippage(asks_i, self._trade_amount)
                    sell_slip = compute_sell_slippage(bids_j, self._trade_amount)
                    slippage_pct = buy_slip.slippage_pct + sell_slip.slippage_pct

                    net_pct = spread_pct - fee_pct - slippage_pct

                    # Penalize event-driven sellers during scoring (stale bid risk)
                    if self._event_driven_seller_penalty > 0 and ex_sell in self._event_driven_exchanges:
                        net_pct -= self._event_driven_seller_penalty

                    if net_pct > best_net:
                        best_net = net_pct
                        best_buy = ex_buy
                        best_sell = ex_sell
                        best_spread = spread_pct
                        best_fee = fee_pct

            # Apply momentum factor: penalize symbols with declining 24h price
            if self._momentum_filter_enabled and best_net > float("-inf"):
                momentum_factor = self._compute_momentum_factor(symbol, current_mid, now)
                if momentum_factor != 1.0:
                    best_net = best_net * momentum_factor

            # Apply funding-rate multiplier (Phase A): boost positive-funding
            # symbols, penalize negative-funding symbols. Floored at min_factor
            # when funding is below skip threshold (effectively disqualifies).
            if self._funding_monitor is not None and best_net > float("-inf"):
                funding_factor = self._funding_monitor.get_funding_factor(symbol)
                if funding_factor != 1.0:
                    best_net = best_net * funding_factor

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
                # Incremental aggregate maintenance — see __init__ note
                self._agg_total[symbol] += 1
                self._agg_sum_net[symbol] += best_net
                if best_net > 0:
                    self._agg_prof_count[symbol] += 1
                    self._agg_prof_sum[symbol] += best_net
                # Monotonic max-deque maintenance: pop trailing entries
                # whose value is <= new value (they're dominated and can
                # never be the max while the new value is in the window).
                # Then append new (timestamp, value). Amortized O(1).
                mq = self._best_net_dq[symbol]
                while mq and mq[-1][1] <= best_net:
                    mq.pop()
                mq.append((now, best_net))
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

        # Prune old ticks + maintain incremental aggregates + max-deque.
        cutoff = now - self._scoring_window
        for sym, dq in self._ticks.items():
            while dq and dq[0].timestamp < cutoff:
                evicted = dq.popleft()
                v = evicted.best_net_pct
                self._agg_total[sym] -= 1
                self._agg_sum_net[sym] -= v
                if v > 0:
                    self._agg_prof_count[sym] -= 1
                    self._agg_prof_sum[sym] -= v
            # Prune monotonic max-deque to the same time cutoff. O(1)
            # amortized — each entry is popleft'd at most once. The
            # front of the deque is the current max in the window.
            mq = self._best_net_dq.get(sym)
            if mq is not None:
                while mq and mq[0][0] < cutoff:
                    mq.popleft()

        self._compute_scores()

        # Per-tick candidate tracking during discovery (after scores are fresh)
        if self._discovery_mode and self._scores:
            self._track_discovery_candidates()

    def _record_price_sample(self, symbol: str, mid_price: float, now: float) -> None:
        """Append mid-price sample to history if sample interval elapsed (Feature 3)."""
        if mid_price <= 0:
            return
        history = self._price_history[symbol]
        if not history or (now - history[-1][0]) >= self._momentum_sample_interval:
            history.append((now, mid_price))
            # Prune samples older than lookback window (keep one buffer beyond)
            cutoff = now - self._momentum_lookback_seconds - self._momentum_sample_interval
            while history and history[0][0] < cutoff:
                history.popleft()

    def _compute_momentum_factor(self, symbol: str, current_mid: float, now: float) -> float:
        """Compute score multiplier from 24h price change (Feature 3).

        Returns clamp(1.0 + price_change_decimal, min, max).
        Falling prices reduce score (down to min_factor); rising prices boost (up to max_factor).
        Returns 1.0 if insufficient history or feature disabled.
        """
        history = self._price_history.get(symbol)
        if not history or len(history) < 2 or current_mid <= 0:
            return 1.0

        # Find oldest sample within lookback window
        target_time = now - self._momentum_lookback_seconds
        oldest_in_window = None
        for ts, price in history:
            if ts >= target_time:
                oldest_in_window = (ts, price)
                break
        if oldest_in_window is None or oldest_in_window[1] <= 0:
            return 1.0

        ref_price = oldest_in_window[1]
        ref_age_hours = (now - oldest_in_window[0]) / 3600.0
        change_decimal = (current_mid - ref_price) / ref_price
        factor = max(self._momentum_min_factor, min(self._momentum_max_factor, 1.0 + change_decimal))

        # Throttled logging: log significant adjustments every 10 min per symbol
        if abs(factor - 1.0) > 0.1:
            last = self._last_momentum_log.get(symbol, 0.0)
            if now - last >= 600:
                self._last_momentum_log[symbol] = now
                logger.info(
                    f"[Momentum] {symbol}: ref_age={ref_age_hours:.1f}h, "
                    f"price {ref_price:.6f}→{current_mid:.6f} "
                    f"({change_decimal*100:+.2f}%), factor={factor:.3f}"
                )
        return factor

    def _track_discovery_candidates(self) -> None:
        """Log candidate status every tick during discovery for trend visibility."""
        now = time.time()
        ranked = sorted(
            self._scores.values(),
            key=lambda s: s.score,
            reverse=True,
        )

        active_candidates: set[str] = set()
        for s in ranked:
            if s.score < self._trading_threshold or s.score <= 0:
                break  # sorted desc, no more candidates
            active_candidates.add(s.symbol)

            # Tier classification
            if s.score >= self._very_strong_threshold:
                tier = "very_strong"
            elif s.score >= self._strong_threshold:
                tier = "strong"
            else:
                tier = "normal"

            # Create or update watchlist entry
            is_new = s.symbol not in self._watchlist
            if is_new:
                self._watchlist[s.symbol] = WatchlistEntry(
                    symbol=s.symbol,
                    entered_at=now,
                    confirmation_start=now,
                )
            wl = self._watchlist[s.symbol]
            wl.add_sample(s.score)
            # Only track peak after 10 samples — early scores are inflated
            # by tiny sample sizes (100% frequency on 1-2 ticks)
            if len(wl.score_samples) >= 10:
                wl.peak_score = max(wl.peak_score, s.score)

            # Trend from score samples
            samples = wl.score_samples
            if len(samples) >= 3:
                if samples[-1] > samples[-2] > samples[-3]:
                    trend = "rising"
                elif samples[-1] < samples[-2] < samples[-3]:
                    trend = "declining"
                elif samples[-1] > samples[-2]:
                    trend = "up"
                elif samples[-1] < samples[-2]:
                    trend = "down"
                else:
                    trend = "flat"
            elif len(samples) >= 2:
                trend = "up" if samples[-1] > samples[-2] else "down" if samples[-1] < samples[-2] else "flat"
            else:
                trend = "new"

            # Score change from peak
            drop_from_peak = ((wl.peak_score - s.score) / wl.peak_score * 100) if wl.peak_score > 0 else 0.0

            status = "NEW" if is_new else "WATCH"
            act_thresh = self._get_activation_threshold(s.symbol)
            fee_adj = self._compute_fee_threshold_adjustment(s.symbol)
            # Per-tick WATCH logs at 48 configs × ~5 candidates each = ~240
            # log lines/sec going through file I/O + dashboard buffer +
            # WebSocket broadcast — directly contributes to capacity warnings.
            # NEW (first sighting) stays at INFO since it's a discrete event.
            # Steady-state WATCH drops to DEBUG so it only fires when the
            # operator explicitly wants verbose output.
            log_level = logging.INFO if is_new else logging.DEBUG
            logger.log(
                log_level,
                f"[Candidate] {status} {s.symbol}: "
                f"score={s.score:.6f} peak={wl.peak_score:.6f} "
                f"drop={drop_from_peak:.0f}% tier={tier} "
                f"avg_net={s.avg_profitable_net:.4f}% freq={s.frequency:.1%} "
                f"ticks={s.profitable_ticks}/{s.total_ticks} "
                f"trend={trend} phase=discovery "
                f"threshold={act_thresh:.4f}(fee_adj={fee_adj:+.4f})"
            )

        # Drop watchlist entries that fell below threshold
        dropped = []
        for sym in list(self._watchlist.keys()):
            if sym not in active_candidates:
                score_obj = self._scores.get(sym)
                dropped.append(
                    f"{sym}({score_obj.score:.6f})" if score_obj else sym
                )
                del self._watchlist[sym]
        if dropped:
            logger.info(
                f"[Candidate] DROPPED {len(dropped)}: "
                + ", ".join(dropped[:5])
                + (f" +{len(dropped)-5} more" if len(dropped) > 5 else "")
            )

    def _discovery_debug_log(self, now: float) -> None:
        """Emit debug logs during discovery to diagnose low scores."""
        # All output here is `logger.debug(...)`, which is filtered out
        # at the default INFO threshold. But the f-strings + list comps +
        # dict iteration still execute — at 48 configs × 2 cycles/min ×
        # 14 min = ~1,344 wasted invocations per session. Skip the work
        # entirely when DEBUG isn't enabled.
        if not logger.isEnabledFor(logging.DEBUG):
            return
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
                strong_count = sum(1 for s in ranked if s.score >= self._strong_threshold)
                logger.debug(
                    f"[Discovery]   {above} symbols above threshold "
                    f"({self._trading_threshold}), "
                    f"{strong_count} strong "
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
            total = self._agg_total.get(sym, 0)
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

            # O(1) read from incremental aggregates (maintained at the
            # append/popleft sites in `_score_tick`). Pre-v0.31 this was
            # 4 linear scans of a deque growing toward `scoring_window`
            # — the dominant cause of progressive sweep-time growth.
            sum_net = self._agg_sum_net.get(sym, 0.0)
            profitable_count = self._agg_prof_count.get(sym, 0)
            sum_profitable_net = self._agg_prof_sum.get(sym, 0.0)

            # O(1) read from monotonic max-deque (front is always the
            # current max in the time window). Replaces the previous
            # lazy-recompute pattern that produced the sweep peak at
            # deque saturation.
            mq = self._best_net_dq.get(sym)
            best_net = mq[0][1] if mq else float("-inf")

            frequency = profitable_count / total
            avg_net = sum_net / total
            avg_profitable_net = (
                sum_profitable_net / profitable_count if profitable_count > 0 else 0.0
            )

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

        # Maintain per-symbol score history for trajectory classification.
        # Independent of watchlist so it stays current for active symbols.
        for s in all_scores:
            self._score_history[s.symbol].append(s.score)

        # Compute per-symbol trade multipliers with focus tiers for active symbols
        # Tiered system: very_strong (>=0.3), strong (>=0.1), normal (>=0.01), weak (<0.01)
        # Symbols >= self._trading_threshold can trade; below that get multiplier=0 (unless active: 1.0x floor)
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
                        # Below trading threshold: active symbols still trade at 1.0x
                        s.trade_multiplier = 1.0 if s.symbol in active_set else 0.0
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

    def _complete_discovery(self, from_fast_track: bool = False) -> None:
        """Pick best symbols after discovery period. All active exchanges stay active.

        `from_fast_track`: True when the call came from the early-exit
        path (a candidate cleared the fast-track timer + threshold) rather
        than from the duration-elapsed path. When True and the activation
        threshold + stability gate then rejects every candidate, we DON'T
        double `_discovery_duration` or reset `_discovery_start` — the
        ticks/watchlist/score history all keep accumulating, but the
        duration timer stays put so the next fast-track re-evaluation
        fires on the natural cadence instead of being pushed out
        exponentially.

        Without this differentiation, every fast-track rejection (e.g.
        cliff-drop on a candidate that bloomed and then cooled) compounds
        `_discovery_duration` 300→600→1200→…→3600. The candidate's tick
        data was preserved but the time-based gates kept growing, making
        activation effectively impossible — observed in S31 with AR on
        Group 2/Config 4 ticking 191/274 → 274/405 across an extension,
        the user reasonably perceiving it as "ticks reset" when really
        the *eligible-to-fire window* was the thing pushed further away.
        """
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
        tradeable_symbols_raw = [
            s.symbol for s in ranked_symbols
            if s.score >= self._get_activation_threshold(s.symbol)
        ]

        # Filter out symbols with declining scores or fading profitable frequency
        tradeable_symbols: list[str] = []
        rejected_declining: list[str] = []
        now = time.time()
        evd_exchanges = self._event_driven_exchanges
        for sym in tradeable_symbols_raw:
            # Check 1: Recent profitable frequency — are ticks STILL profitable?
            # Look at recent tick data. If frequency dropped to near-zero,
            # the opportunity was transient and has already closed.
            # Use a longer window (60s) for symbols involving event-driven exchanges
            # (e.g., Bitfinex updates every 10-20s, so a 15s window misses updates).
            ticks = self._ticks.get(sym, [])
            if len(ticks) >= 15:
                # Determine if this symbol's profitable ticks involve event-driven exchanges
                involves_evd = False
                if evd_exchanges:
                    recent_sample = list(ticks)[-30:]
                    profitable_ticks_sample = [
                        t for t in recent_sample if t.best_net_pct > 0
                    ]
                    if profitable_ticks_sample:
                        involves_evd = any(
                            t.buy_exchange in evd_exchanges or t.sell_exchange in evd_exchanges
                            for t in profitable_ticks_sample
                        )
                recent_window = 60.0 if involves_evd else 15.0
                min_recent_ticks = 5 if involves_evd else 10
                recent_cutoff = now - recent_window
                recent_ticks = [t for t in ticks if t.timestamp >= recent_cutoff]
                if len(recent_ticks) >= min_recent_ticks:
                    recent_profitable = sum(1 for t in recent_ticks if t.best_net_pct > 0)
                    recent_freq = recent_profitable / len(recent_ticks)
                    if recent_freq < 0.05:
                        score_obj = self._scores.get(sym)
                        overall_freq = score_obj.frequency if score_obj else 0.0
                        rejected_declining.append(
                            f"{sym.replace('USDT', '')}("
                            f"recent_freq={recent_freq:.1%} "
                            f"overall_freq={overall_freq:.1%} "
                            f"window={recent_window:.0f}s "
                            f"reason=fading)"
                        )
                        continue

            # Check 2: Declining score trajectory
            wl = self._watchlist.get(sym)
            if wl and len(wl.score_samples) >= 5:
                samples = wl.score_samples
                # Check if meaningfully declining: last 5 all decreasing AND
                # total drop > 10% (filters out rolling window dilution noise)
                last5 = samples[-5:]
                all_declining = all(
                    last5[i] > last5[i + 1] for i in range(len(last5) - 1)
                )
                current = samples[-1]
                decline_pct = (last5[0] - current) / last5[0] * 100 if last5[0] > 0 else 0
                meaningful_decline = all_declining and decline_pct > 10
                # Also check cliff drop: current < peak × stability_factor
                cliff = (
                    wl.peak_score > 0
                    and current < wl.peak_score * self._score_stability_factor
                )
                if meaningful_decline or cliff:
                    reason = f"declining ({decline_pct:.1f}%)" if meaningful_decline else "cliff_drop"
                    rejected_declining.append(
                        f"{sym.replace('USDT', '')}("
                        f"cur={current:.4f} peak={wl.peak_score:.4f} "
                        f"reason={reason})"
                    )
                    continue

            # Note: pair_fee_exceeds_net gate is NOT applied in discovery.
            # Discovery has zero switching cost — being idle is always worse
            # than trading on a marginal pair. The demotion system handles
            # bad symbols within 15-30 min. The gate remains active for
            # expansion/rotation where there IS a cost to switch.

            tradeable_symbols.append(sym)

        if rejected_declining:
            logger.info(
                f"[Candidate] REJECTED at activation (unstable): "
                + ", ".join(rejected_declining)
            )

        if tradeable_symbols:
            # Activate tradeable symbols (cap at max_active)
            best_symbols = tradeable_symbols[: self._max_active_symbols]
            strong_count = sum(1 for s in ranked_symbols
                             if s.symbol in best_symbols and s.score >= self._strong_threshold)
            logger.info(
                f"[Optimizer] Discovery: {len(tradeable_symbols)} tradeable symbols found "
                f"(fee-aware threshold, base={self._trading_threshold}, mult={self._fee_threshold_multiplier}), "
                f"{strong_count} strong (>= {self._strong_threshold}), activating {len(best_symbols)}"
            )
        else:
            # No tradeable symbols found — keep scanning. Two paths:
            #   * from_fast_track=True: a candidate cleared the threshold
            #     but stability gate rejected it (cliff drop / declining /
            #     etc.). The ticks + score history are still accumulating
            #     and the candidate may stabilize on the next eval. DON'T
            #     compound `_discovery_duration` — that just pushes future
            #     activation gates exponentially further out.
            #   * from_fast_track=False: actual duration timeout with no
            #     candidates anywhere. Double duration (capped at 3600s)
            #     so we keep collecting data but don't churn evaluation
            #     work.
            top_10 = ", ".join(
                f"{s.symbol.replace('USDT', '')}({s.score:.6f} "
                f"prof={s.profitable_ticks}/{s.total_ticks} "
                f"best={s.best_net_pct:+.4f}%)"
                for s in ranked_symbols[:10]
            ) if ranked_symbols else "no data"
            if from_fast_track:
                # Same per-config 30s throttle — when a candidate keeps
                # cycling through fast-track + stability rejection, both
                # this log and the "found at Xs" log fire on every tick.
                # Logging once per 30s gives the operator visibility
                # without flooding the file.
                now_ts = time.time()
                if now_ts - self._last_fast_track_log >= 30.0:
                    self._last_fast_track_log = now_ts
                    logger.info(
                        f"[Optimizer] Discovery: candidates cleared threshold "
                        f"but stability gate rejected — keeping current duration "
                        f"({self._discovery_duration}s), ticks preserved. "
                        f"Top 10: {top_10}"
                    )
            else:
                self._discovery_duration = min(
                    self._discovery_duration * 2, 3600
                )
                self._discovery_start = time.time()
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

        # v0.30: capital architecture
        #   - Trading float (Bitfinex): bounded by trade_amount × multiplier
        #   - Custody hub (Bybit by default): receives the rest
        #   - Symbol allocations come out of "allocatable_capital" = remainder
        # The reserve_amount variable name is preserved for downstream compat
        # but its value now reflects trading float, not capital%.
        trade_amount = self._balance._trade_amount if self._balance else 40.0
        float_mult = (
            self._balance._trading_float_multiplier if self._balance else 8.0
        )
        custody_hub = (
            self._balance._custody_hub_exchange if self._balance else "Bybit"
        )
        reserve_amount = 0.0
        if "Bitfinex" in all_exchanges and float_mult > 0:
            reserve_amount = trade_amount * float_mult
            logger.info(
                f"[Capital] Trading float: ${reserve_amount:.0f} on Bitfinex "
                f"(trade_amount ${trade_amount:.0f} × {float_mult:.1f}x), "
                f"custody hub = {custody_hub}"
            )
        allocatable_capital = total_capital - reserve_amount

        # Score-weighted capital distribution across symbols
        best_scores = {sym: self._scores[sym].score for sym in best_symbols if sym in self._scores}
        total_score = sum(best_scores.values())
        min_weight = 0.1 / len(best_symbols)  # minimum 10% / num_symbols

        # Build allocations: symmetric 50/50 USDT+crypto on ALL dominant exchanges
        # (bidirectional trading — any exchange can be buyer or seller)
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

            # Symmetric allocation: combine buyer+seller weights into unified
            # per-exchange weights. Each exchange gets both USDT and crypto,
            # enabling bidirectional trading (natural rebalancing through trades).
            exchange_weights: dict[str, float] = {}
            for ex, w in pairs["buyers"]:
                exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
            for ex, w in pairs["sellers"]:
                exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
            total_w = sum(exchange_weights.values())

            for ex, w in exchange_weights.items():
                share = sym_capital * (w / total_w) if total_w > 0 else sym_capital / max(1, len(exchange_weights))
                usdt_share = share * 0.5
                crypto_share = share * 0.5
                allocations[ex]["usdt"] += usdt_share
                if sym not in allocations[ex]["crypto"]:
                    allocations[ex]["crypto"][sym] = 0.0
                allocations[ex]["crypto"][sym] += crypto_share

            exchanges_str = "+".join(
                f"{ex}({w / total_w:.0%})" if total_w > 0 else ex
                for ex, w in exchange_weights.items()
            )
            logger.info(
                f"[Optimizer]   {sym.replace('USDT', '')}: "
                f"symmetric 50/50 on [{exchanges_str}], "
                f"capital=${sym_capital:.0f}"
            )

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
            f"Symmetric 50/50 allocation, ${total_capital:.0f} total"
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

        # Reconfigure balance tracker with new allocations (preserves cumulative fees/transfers)
        self._balance._exchanges = list(all_exchanges)
        self._balance._symbols = list(best_symbols)
        self._balance.reconfigure(allocations=allocations)

        # CRITICAL: reset anomaly peaks on basis change. balance.reconfigure
        # recomputes _initial_investment from the new allocation sum; without
        # this reset, _peak_realized_value stays anchored to the old basis
        # and Layer A misreads the basis change as a massive realized
        # drawdown (e.g. 75% phantom emergency in the 21:03 trace).
        try:
            new_realized = self._balance.get_realized_capital(
                trading_pnl=0.0,  # post-reconfigure trading_pnl is what monitor will track going forward
                credited_cashback=0.0,
            )
            self._monitor._anomaly.reset_peak_on_basis_change(
                portfolio_value=new_realized,
                reason="discovery_complete_reconfigure",
            )
        except Exception:
            logger.exception("[Optimizer] Failed to reset anomaly peak post-reconfigure")

        # Reconfigure monitor with new symbols/exchanges (preserves cumulative trades/P&L)
        self._monitor.reconfigure(
            symbols=best_symbols,
            exchanges=all_exchanges,
            trade_amount=self._trade_amount,
            balance=self._balance,
        )
        self._monitor._paused = False

        # Reset periodic-rebalance timer so the first inventory rebalance
        # fires a full interval after activation (not immediately on next
        # tick when _last_inventory_rebalance==0). Belt-and-suspenders with
        # the balance.initialized gate.
        now_init = time.time()
        self._last_inventory_rebalance = now_init

        # Mark every newly-allocated exchange as "just started trading" so
        # _consolidate_idle_exchange_crypto doesn't see them as infinitely
        # idle (last_trade_time==0 → idle_seconds==inf → instant consolidation
        # of the freshly-allocated crypto, observed in S21 30s post-activation).
        for ex in all_exchanges:
            if allocations.get(ex, {}).get("usdt", 0) > 0 or any(
                v > 0 for v in allocations.get(ex, {}).get("crypto", {}).values()
            ):
                self._balance.last_trade_time[ex] = now_init

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

    def _classify_trajectory(self, samples_or_entry, peak_score: float | None = None) -> str:
        """Classify a symbol's recent score trajectory as rising/stable/declining.

        Accepts either a list/deque of scores or a WatchlistEntry (back-compat).
        Compares the average of the recent half of the sample window against
        the earlier half, with a peak-resilience clause to tolerate brief
        dips. Robust to single-tick noise (averages instead of endpoints).

        Returns one of: "rising", "stable", "declining".
            rising:    recent_avg > earlier_avg × 1.02 (clear up bias)
            stable:    within ±2% OR current ≥ peak × 0.85 (peak resilience)
            declining: recent_avg < earlier_avg × 0.95 (sustained drop)
        """
        if isinstance(samples_or_entry, WatchlistEntry):
            samples = list(samples_or_entry.score_samples)
            peak = samples_or_entry.peak_score if peak_score is None else peak_score
        else:
            samples = list(samples_or_entry)
            peak = peak_score if peak_score is not None else (max(samples) if samples else 0.0)

        n = len(samples)
        if n < 30:
            return "stable"

        # Use the last 30 samples; split into two halves of 15
        recent = samples[-30:]
        earlier_half = recent[:15]
        recent_half = recent[15:]
        earlier_avg = sum(earlier_half) / 15
        recent_avg = sum(recent_half) / 15

        if earlier_avg <= 0:
            return "rising" if recent_avg > 0 else "stable"

        ratio = recent_avg / earlier_avg
        if ratio >= 1.02:
            return "rising"
        if ratio < 0.95:
            current = samples[-1]
            if peak > 0 and current >= peak * 0.85:
                return "stable"
            return "declining"
        return "stable"

    def _is_score_stable(
        self, entry: WatchlistEntry, current_score: float
    ) -> tuple[bool, str]:
        """Check if a watchlist candidate's score trend is stable enough for activation.

        Returns (is_stable, reason_string).
        """
        now = time.time()
        # 1. Minimum observation period
        if now - entry.entered_at < self._score_stability_seconds:
            return False, "min_observation"
        # 2. Cliff drop: current score fell below peak × stability_factor
        if (
            entry.peak_score > 0
            and current_score < entry.peak_score * self._score_stability_factor
        ):
            return (
                False,
                f"cliff_drop (cur={current_score:.6f} < peak={entry.peak_score:.6f}"
                f" × {self._score_stability_factor})",
            )
        # 3. Declining trend: 3+ consecutive drops
        samples = entry.score_samples
        if len(samples) >= 3:
            last3 = samples[-3:]
            if last3[0] > last3[1] > last3[2]:
                return (
                    False,
                    f"declining_trend (last3="
                    f"[{last3[0]:.6f}, {last3[1]:.6f}, {last3[2]:.6f}])",
                )
        return True, "stable"

    def _update_watchlist(self) -> None:
        """Track strong candidates and confirm after sustained performance."""
        now = time.time()
        active_set = set(self._active_symbols)

        # Update existing entries and add new ones.
        # Pre-fix: threshold was `max(promotion_threshold, min(active_scores))`
        # — meaning if any active symbol scored anomalously high (e.g., JUP at
        # ~1.32 during its structural inefficiency window), no other candidate
        # could ever stay watchlisted because nothing else hits 1.32. Observed
        # in 20:21 trace: ALGO at score=0.018 entered EXPAND_TRACK, was dropped
        # 28s later as `0.018<1.328104`, then immediately re-added as "first
        # seen" by _evaluate_expansion. The 30s observation reset broke
        # confirmation entirely. Now we use the per-symbol activation threshold
        # which matches the threshold _evaluate_expansion uses to consider the
        # candidate, so they don't fight each other. The rotation gate (beating
        # worst active to trigger replacement) lives in _evaluate_rotation
        # where it belongs — not in watchlist retention.
        cooldown_set = set(self._recently_demoted.keys())
        removed_candidates: list[str] = []
        for sym, score_obj in self._scores.items():
            if sym in active_set or sym in cooldown_set:
                continue

            threshold = self._get_activation_threshold(sym)
            if score_obj.score >= threshold and score_obj.score > 0:
                is_new = sym not in self._watchlist
                if is_new:
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
                entry.add_sample(score_obj.score)
                if len(entry.score_samples) >= 10:
                    entry.peak_score = max(entry.peak_score, score_obj.score)

                # Check confirmation (faster for strong/very_strong candidates)
                score_val = score_obj.score if score_obj else 0.0
                if score_val >= self._very_strong_threshold:
                    confirm_time = self._confirmation_period * 0.1
                elif score_val >= self._strong_threshold:
                    confirm_time = self._confirmation_period * 0.4
                else:
                    confirm_time = self._confirmation_period

                # Stability gate: must pass trend checks before confirmation
                stable, stability_reason = self._is_score_stable(
                    entry, score_obj.score
                )
                if not entry.confirmed and stable and now - entry.entered_at >= confirm_time:
                    entry.confirmed = True
                    stats = self._historical_stats.get(sym)
                    if stats:
                        stats.times_confirmed += 1
                    logger.info(
                        f"[Candidate] CONFIRMED {sym}: "
                        f"score={score_val:.6f} avg={sum(entry.score_samples)/len(entry.score_samples):.6f} "
                        f"peak={entry.peak_score:.6f} confirm={confirm_time:.0f}s "
                        f"avg_net={score_obj.avg_profitable_net:.4f}% freq={score_obj.frequency:.1%} "
                        f"ticks={score_obj.profitable_ticks}/{score_obj.total_ticks} "
                        f"best_net={score_obj.best_net_pct:+.4f}%"
                    )
                elif not entry.confirmed:
                    # Log candidate status: trend, time remaining, why not confirmed yet
                    elapsed = now - entry.entered_at
                    samples = entry.score_samples
                    if len(samples) >= 2:
                        trend = "rising" if samples[-1] > samples[-2] else "falling" if samples[-1] < samples[-2] else "flat"
                    else:
                        trend = "new"
                    # Determine blocking reason
                    if not stable:
                        block = stability_reason
                    elif elapsed < confirm_time:
                        block = f"time ({elapsed:.0f}/{confirm_time:.0f}s)"
                    else:
                        block = "unknown"
                    status = "NEW" if is_new else "WATCH"
                    act_thresh = self._get_activation_threshold(sym)
                    fee_adj = self._compute_fee_threshold_adjustment(sym)
                    # Same throttling as the discovery-phase WATCH — NEW
                    # stays INFO (discrete event), per-tick WATCH drops to
                    # DEBUG to keep file I/O and dashboard buffer usage
                    # under control at 40+ configs scale.
                    log_level = logging.INFO if is_new else logging.DEBUG
                    logger.log(
                        log_level,
                        f"[Candidate] {status} {sym}: "
                        f"score={score_val:.6f} peak={entry.peak_score:.6f} "
                        f"avg_net={score_obj.avg_profitable_net:.4f}% freq={score_obj.frequency:.1%} "
                        f"ticks={score_obj.profitable_ticks}/{score_obj.total_ticks} "
                        f"trend={trend} block={block} "
                        f"threshold={act_thresh:.4f}(fee_adj={fee_adj:+.4f})"
                    )
            else:
                # Score dropped below threshold — remove from watchlist
                if sym in self._watchlist:
                    entry = self._watchlist[sym]
                    removed_candidates.append(
                        f"{sym}({score_obj.score:.6f}<{threshold:.6f})"
                    )
                self._watchlist.pop(sym, None)

        if removed_candidates:
            logger.info(
                f"[Candidate] DROPPED {len(removed_candidates)}: "
                + ", ".join(removed_candidates[:5])
                + (f" +{len(removed_candidates)-5} more" if len(removed_candidates) > 5 else "")
            )

    # ── Regime helpers ──────────────────────────────────────────────────

    def _current_regime(self) -> str:
        """Return 'strong', 'neutral', or 'weak' for the current UTC hour.

        Mirrors the monitor's helper. When regime_gating_enabled is False,
        always returns 'strong' so all gates remain open. Hours not in
        strong_hours or neutral_hours fall to weak.
        """
        if not self._regime_gating_enabled:
            return "strong"
        h = time.gmtime().tm_hour
        if h in self._regime_strong_hours:
            return "strong"
        if h in self._regime_neutral_hours:
            return "neutral"
        return "weak"

    def _compute_demotion_cooldown(self, symbol: str) -> float:
        """Frequency-scaled cooldown.

        A symbol cycling through demotions wastes setup+teardown fees
        on each cycle without matching trade volume. Geometric scaling:

            1 demotion in last 24h →  1× base cooldown
            2 demotions             →  2×
            3 demotions             →  4×
            4+ demotions            →  8× (capped, ~3.3h at default 25min base)

        The 24h window auto-resets at midnight UTC roll, so a symbol
        that had a bad run yesterday gets a fresh chance today.
        Disabled per-config via `demotion_freq_scaling_enabled = False`.
        """
        base = self._demotion_cooldown
        if not self._demotion_freq_scaling_enabled:
            return base
        hist = self._demotion_history.get(symbol)
        if not hist:
            return base
        # Prune to 24h rolling window (cheap on small list)
        now = time.time()
        cutoff = now - 86400.0
        recent = [t for t in hist if t >= cutoff]
        n = len(recent)
        if n <= 1:
            return base
        # 2^(n-1) capped at 8× — n=2→2×, n=3→4×, n=4+→8×
        multiplier = min(2 ** (n - 1), 8)
        return base * multiplier

    # ── Demotion ─────────────────────────────────────────────────────────

    def _evaluate_demotions(self) -> None:
        """Demote active symbols that drop below trading threshold."""
        # Regime gate: skip demotions during weak UTC hours. The activation
        # cost was already paid; demoting now means paying teardown fees
        # to free capital that probably won't get redeployed during this
        # thin window anyway. Better to let symbols sit until conditions
        # improve.
        if (
            self._regime_gating_enabled
            and self._regime_weak_disable_demote
            and self._current_regime() == "weak"
        ):
            return
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

        # After all demotions: if portfolio is 100% USDT, reset drawdown peak
        if to_demote and self._balance:
            has_crypto = any(
                qty > 0
                for ex in self._balance._exchanges
                for qty in self._balance.crypto.get(ex, {}).values()
            )
            if not has_crypto:
                prices = self._get_all_prices()
                portfolio = self._balance.get_portfolio_value(prices)
                self._monitor._anomaly.reset_peak_if_no_crypto(portfolio)

    def _execute_demotion(self, symbol: str) -> None:
        """Remove an underperforming symbol from the active set.

        Sells all held crypto to avoid market exposure risk from price drops.
        When Bitfinex has the symbol, transfers crypto there first and sells
        at 0% taker fee instead of selling locally (saves source taker fee).
        """
        from balance import Transfer

        now = time.time()

        # Decide whether to route the demotion sell through Bitfinex 0%
        # taker. Uses a cached last-known bid so event-driven feed gaps
        # don't force a fall-back to local-exchange selling at 0.04-0.10%
        # taker. v0.30.7-beta — fixes S27's $0.28 demotion-sell fee leak.
        bitfinex_available, bitfinex_bid = self._bitfinex_sell_route(symbol)

        # Sell all crypto of the demoted symbol on every exchange
        prices = self._get_all_prices()
        price = prices.get(symbol, 0.0)
        freed_capital = 0.0
        total_sell_fee = 0.0
        via_bitfinex_count = 0
        via_bitfinex_saved = 0.0
        if price > 0:
            for ex in self._balance._exchanges:
                qty = self._balance.crypto[ex].get(symbol, 0.0)
                if qty <= 0:
                    continue

                if bitfinex_available and ex != "Bitfinex":
                    # Transfer crypto to Bitfinex, sell at 0% taker fee
                    withdrawal_fee = self._balance._get_withdrawal_fee(ex)
                    gross = qty * bitfinex_bid
                    # 0% taker fee on Bitfinex — no fee deduction
                    self._balance.crypto[ex][symbol] = 0.0
                    self._balance.usdt["Bitfinex"] += gross
                    self._balance.total_transfer_fees += withdrawal_fee
                    self._balance.total_external_transfer_fees += withdrawal_fee
                    if withdrawal_fee > 0:
                        self._balance._record_external_fee(withdrawal_fee)
                    total_sell_fee += withdrawal_fee
                    freed_capital += gross
                    via_bitfinex_count += 1
                    # Compute savings vs local sell
                    local_fee_rate = (
                        self._fee_manager.get_taker_fee(ex)
                        if self._fee_manager
                        else 0.001
                    )
                    via_bitfinex_saved += gross * local_fee_rate
                    self._balance.transfers.append(
                        Transfer(
                            timestamp=now,
                            transfer_type="demotion_sell_via_bitfinex",
                            from_exchange=ex,
                            to_exchange="Bitfinex",
                            symbol=symbol,
                            amount_usd=gross,
                            fee_usd=withdrawal_fee,
                        )
                    )
                    logger.info(
                        f"[Optimizer] Demotion sell via Bitfinex: "
                        f"{symbol} {ex}→Bitfinex, ${gross:.2f} "
                        f"(saved {local_fee_rate*100:.3f}% taker, "
                        f"withdrawal ${withdrawal_fee:.4f})"
                    )
                else:
                    # Sell locally (Bitfinex doesn't have symbol, or crypto on Bitfinex)
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
                    self._balance.total_transfer_fees += fee

        saved_msg = ""
        if via_bitfinex_count > 0:
            saved_msg = f", {via_bitfinex_count} via Bitfinex (saved ${via_bitfinex_saved:.4f} taker)"
        logger.info(
            f"[Optimizer] DEMOTING: {symbol} (score below threshold for "
            f"{self._demotion_period}s) — selling crypto "
            f"(freed ${freed_capital:.2f}, fees ${total_sell_fee:.4f}{saved_msg})"
        )

        # Phase E: close any futures hedge for this symbol (async, fire-and-forget).
        # The hedge manager handles real vs shadow mode internally.
        hm = getattr(self._monitor, "_hedge_manager", None)
        if hm is not None:
            hm.request_close(symbol, reason=f"demoted({symbol})")

        # v0.30: post-demotion sweep — freed USDT flows to custody hub (Bybit),
        # not Bitfinex. This includes:
        #   (1) Local-sell proceeds on the original buyer exchange → custody hub
        #   (2) Via-Bitfinex sell proceeds (now sitting on Bitfinex) → custody hub
        #       only if the float is above its overflow threshold
        if self._balance:
            # Symmetric: all dominant exchanges are active for both buy and sell
            active_exchanges = set()
            for sym in self._active_symbols:
                pairs = self._dominant_pairs.get(sym, {})
                for ex_name, _ in pairs.get("buyers", []):
                    active_exchanges.add(ex_name)
                for ex_name, _ in pairs.get("sellers", []):
                    active_exchanges.add(ex_name)
            # When net-negative, only consolidate from free/near-free sources
            fee_cap = 0.02 if not self._rotation_budget_ok else None
            transfers = self._balance.consolidate_to_custody_hub(
                active_exchanges, idle_threshold=1800.0,
                active_seller_exchanges=active_exchanges,
                max_fee_per_source=fee_cap,
            )
            if transfers:
                hub = self._balance._custody_hub_exchange
                hub_fee = sum(t.fee_usd for t in transfers)
                hub_amt = sum(t.amount_usd for t in transfers)
                logger.info(
                    f"[Capital] Post-demotion sweep: "
                    f"{len(transfers)} transfers, ${hub_amt:.2f} → {hub} "
                    f"(fees: ${hub_fee:.4f})"
                )
            # Also sweep Bitfinex trading float overflow if any
            self._consolidate_trading_float_overflow()

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
        # Track demotion in 24h rolling history for frequency-aware cooldown scaling
        hist = self._demotion_history.setdefault(symbol, [])
        cutoff_24h = now - 86400.0
        hist[:] = [t for t in hist if t >= cutoff_24h]
        hist.append(now)
        # Compute escalating cooldown: 1× / 2× / 4× / 8× for 1/2/3/4+ demotions
        effective_cooldown = self._compute_demotion_cooldown(symbol)

        self._monitor.update_symbols(list(self._active_symbols))
        self._balance.update_symbols(list(self._active_symbols))

        logger.info(
            f"[Optimizer] Demotion complete: {symbol} removed, "
            f"cooldown={effective_cooldown:.0f}s "
            f"(base={self._demotion_cooldown:.0f}s, "
            f"24h_demotions={len(hist)}), active: {self._active_symbols}"
        )

        # Redistribute freed capital to starved buyer exchanges
        if self._active_symbols:
            self._redistribute_post_demotion()

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

    # ── Post-demotion redistribution ────────────────────────────────────

    def _redistribute_post_demotion(self) -> None:
        """Push freed capital from Bitfinex to starved active exchanges.

        After a demotion, capital consolidates on Bitfinex via demotion sells.
        Instead of waiting for miss-streaks, proactively redistribute to
        all active exchanges that need USDT. Bitfinex $0-fee transfers pass the
        hourly cap (Fix 1). Symmetric: all dominant exchanges need USDT.
        """
        from balance import Transfer

        if not self._balance:
            return
        # v0.30: source is the custody hub (Bybit), not Bitfinex.
        # Bitfinex is the trading float, not the redistribution source.
        hub = self._balance._custody_hub_exchange
        if hub not in self._balance._exchanges:
            return
        available = self._balance._available_usdt_for_rebalance(hub)
        if available < self._trade_amount * 2:
            return  # Nothing meaningful to redistribute

        # Collect ALL active exchanges from remaining symbols' dominant pairs
        exchange_needs: dict[str, float] = {}
        for sym in self._active_symbols:
            pairs = self._dominant_pairs.get(sym)
            if not pairs:
                continue
            all_sym_exchanges = {ex for ex, _ in pairs.get("buyers", [])} | {ex for ex, _ in pairs.get("sellers", [])}
            for ex in all_sym_exchanges:
                if ex == hub:
                    continue
                bal = self._balance.usdt.get(ex, 0.0)
                if bal < self._trade_amount * 2:
                    shortfall = self._trade_amount * 3 - bal
                    exchange_needs[ex] = max(exchange_needs.get(ex, 0), shortfall)

        if not exchange_needs:
            return

        # Sort by largest shortfall first
        sorted_needs = sorted(exchange_needs.items(), key=lambda x: x[1], reverse=True)
        total_sent = 0.0
        now = time.time()
        for ex, need in sorted_needs:
            amount = min(need, available - total_sent)
            if amount < self._trade_amount:
                continue
            fee = self._balance._get_withdrawal_fee(hub, amount)
            if not self._balance._check_hourly_transfer_budget(fee):
                continue
            self._balance._record_external_fee(fee)
            self._balance.usdt[hub] -= amount
            self._balance.usdt[ex] = self._balance.usdt.get(ex, 0.0) + (amount - fee)
            self._balance.total_transfer_fees += fee
            self._balance.total_external_transfer_fees += fee
            total_sent += amount
            self._balance.transfers.append(
                Transfer(
                    timestamp=now,
                    transfer_type="post_demotion_redistribute",
                    from_exchange=hub,
                    to_exchange=ex,
                    symbol="USDT",
                    amount_usd=amount,
                    fee_usd=fee,
                )
            )
            logger.info(
                f"[Capital] Post-demotion redistribute: {hub}→{ex} "
                f"${amount:.2f} via {self._balance._custody_hub_network} "
                f"(fee=${fee:.4f}, shortfall=${need:.2f})"
            )
            if total_sent >= available * 0.8:
                break  # Keep 20% buffer on custody hub

    def _consolidate_trading_float_overflow(self) -> None:
        """Move excess Bitfinex trading-float USDT back to the custody hub.

        v0.30+: previously redistributed excess to active buyer exchanges
        (legacy `_redistribute_bitfinex_over_target`). Now flows back to
        the custody hub (default Bybit) via Aptos $0 — the custody hub
        handles further redistribution to active exchanges on demand.
        Single destination, single network.

        Triggers when Bitfinex USDT > target × overflow_multiplier
        (default 1.5×). Excess = bitfinex - target.
        """
        if not self._balance:
            return
        bfx_usdt = self._balance.usdt.get("Bitfinex", 0.0)
        target = self._balance._bitfinex_reserve_target  # = trade_amount × multiplier
        if target <= 0:
            return  # Trading float disabled

        threshold = target * self._balance._trading_float_overflow_multiplier
        if bfx_usdt <= threshold:
            return  # Within target band

        excess = bfx_usdt - target
        if excess < self._trade_amount:
            return  # Too small to bother

        # Single destination: the configured custody hub (default Bybit)
        transfer = self._balance.transfer_excess_to_custody(excess)
        if transfer is None:
            # When the custody hub is disabled (e.g. Lean BFX+MEX config),
            # this condition persists indefinitely and the log fires on
            # EVERY tick. Throttle to once per 5 min per config so we
            # still surface the issue without flooding the file.
            now_ts = time.time()
            if now_ts - self._last_overflow_blocked_log >= 300.0:
                self._last_overflow_blocked_log = now_ts
                logger.info(
                    f"[Capital] Trading float overflow blocked: "
                    f"bfx=${bfx_usdt:.2f} target=${target:.2f} excess=${excess:.2f} "
                    f"(custody hub={self._balance._custody_hub_exchange} unreachable)"
                )
            return
        logger.info(
            f"[Capital] Trading float overflow: Bitfinex ${bfx_usdt:.2f} > "
            f"threshold ${threshold:.2f}, swept ${transfer.amount_usd:.2f} to "
            f"{transfer.to_exchange}, Bitfinex now ${self._balance.usdt.get('Bitfinex', 0.0):.2f}"
        )

    # Backward-compat alias
    _redistribute_bitfinex_over_target = _consolidate_trading_float_overflow

    def _auto_expand_on_understaff_tick(self, now: float) -> None:
        """Fire expansion immediately when active symbol count is below minimum (Feature 6).

        After demotions, the bot can sit idle for up to evaluation_interval (5 min)
        before _evaluate_rotation() runs again. When active count < min_active_symbols
        this delay creates dead capital. This method bypasses the eval cooldown.
        """
        # Regime gate: skip auto-expand during weak UTC hours. Activating
        # new symbols means paying setup transfer fees — wasteful if the
        # market window won't generate enough trades to amortize them.
        if (
            self._regime_gating_enabled
            and self._regime_weak_disable_expand
            and self._current_regime() == "weak"
        ):
            return
        active_count = len(self._active_symbols)
        deficit = self._min_active_symbols - active_count
        logger.info(
            f"[Optimizer] AUTO_EXPAND triggered: active={active_count}/{self._min_active_symbols} "
            f"(deficit={deficit})"
        )
        # Reuse the standard rotation path — it includes expansion if there's room
        try:
            self._evaluate_rotation()
        except Exception as e:
            logger.error(f"[Optimizer] AUTO_EXPAND _evaluate_rotation failed: {e}")

    # ── Activation threshold ─────────────────────────────────────────────

    def _get_activation_threshold(self, symbol: str) -> float:
        """Minimum score for activation, fee-aware and demotion-aware.

        The threshold scales with the dominant pair's combined taker fees.
        Cheap pairs (Bitfinex involved, ~0.04%) get the base threshold.
        Expensive pairs (no Bitfinex, ~0.14%+) need proportionally higher
        scores to justify the setup/transfer overhead.

        Formula: threshold = base + (pair_fee_pct - cheapest_possible_fee) * fee_threshold_mult

        Diversification floor (S21 follow-up): when active symbol count is
        below `num_active_symbols`, multiply the final threshold by
        `_diversification_floor_multiplier` (default 0.7 → 30% easier to
        clear). Encourages reaching minimum diversity even at marginal symbol
        quality. Momentum filter still penalizes bleeders, so this won't
        activate clearly bad symbols.
        """
        base = self._trading_threshold

        # Fee-aware component: compute cheapest pair fee from recent tick data
        fee_adj = self._compute_fee_threshold_adjustment(symbol)
        threshold = base + fee_adj

        # Demotion penalty: each demotion adds 50% of base
        stats = self._historical_stats.get(symbol)
        if stats and stats.times_demoted > 0:
            threshold += base * stats.times_demoted * 0.5

        # Cap at strong threshold
        threshold = min(threshold, self._strong_threshold)

        # Diversification floor — relax when understaffed.
        # Applies whenever the bot is below min_active_symbols, including
        # discovery re-extensions after total demotion (the gate previously
        # required _discovery_complete=True, which silently disabled the
        # floor during the most-needed scenario: 0 active symbols + fresh
        # discovery — observed in S22 with WIFUSDT score=0.022 vs threshold
        # 0.032 sitting in extended discovery for 30+ min).
        if (
            self._diversification_floor_enabled
            and len(self._active_symbols) < self._min_active_symbols
        ):
            threshold *= self._diversification_floor_multiplier

        return threshold

    def _get_dominant_buyer_seller(self, symbol: str) -> tuple[str, str]:
        """Return (top_buyer, top_seller) for a symbol.

        Prefers the cached dominant pair (set by `_compute_dominant_pairs`
        for active symbols); falls back to last 100 profitable ticks for
        candidates that haven't been activated yet.
        """
        # Active symbols: use cached dominant pair (top entry per direction)
        dom = self._dominant_pairs.get(symbol)
        if dom:
            buyers = dom.get("buyers", [])
            sellers = dom.get("sellers", [])
            top_buyer = buyers[0][0] if buyers else ""
            top_seller = sellers[0][0] if sellers else ""
            if top_buyer and top_seller:
                return top_buyer, top_seller

        # Candidate path: derive from recent profitable ticks
        ticks = self._ticks.get(symbol, deque())
        profitable = [t for t in ticks if t.best_net_pct > 0]
        if not profitable:
            return "", ""

        buy_counts: dict[str, int] = defaultdict(int)
        sell_counts: dict[str, int] = defaultdict(int)
        for t in profitable[-100:]:
            buy_counts[t.buy_exchange] += 1
            sell_counts[t.sell_exchange] += 1
        top_buyer = max(buy_counts, key=buy_counts.get) if buy_counts else ""
        top_seller = max(sell_counts, key=sell_counts.get) if sell_counts else ""
        return top_buyer, top_seller

    def _compute_fee_threshold_adjustment(self, symbol: str) -> float:
        """Compute threshold adjustment based on dominant pair's combined fees.

        Returns 0 for Bitfinex-involved pairs (cheapest possible).
        Returns positive value for expensive pairs, scaling with fee level.

        The cheapest possible pair fee is used as baseline (typically Bitfinex
        0% + MEXC 0.04% = 0.04%). Any pair above that gets a proportional
        threshold increase via fee_threshold_multiplier.
        """
        if not self._fee_manager:
            return 0.0

        # Get cheapest possible combined fee across all enabled exchanges
        cheapest_fee = self._get_cheapest_pair_fee(symbol)

        # Get this symbol's dominant pair fee from tick data
        pair_fee = self._get_symbol_pair_fee(symbol)

        if pair_fee <= cheapest_fee:
            return 0.0  # Already using cheapest pair

        # Scale adjustment: how much more expensive is this pair?
        fee_excess = pair_fee - cheapest_fee  # e.g., 0.14% - 0.04% = 0.10%
        adjustment = fee_excess * self._fee_threshold_multiplier
        return adjustment

    def _get_cheapest_pair_fee(self, symbol: str) -> float:
        """Get the cheapest possible combined taker fee for any exchange pair."""
        if not self._fee_manager:
            return 0.0

        fees = []
        for ex in self._active_exchanges:
            fee = self._fee_manager.get_scoring_fee(ex, symbol)
            fees.append(fee)

        if len(fees) < 2:
            return 0.0

        fees.sort()
        return (fees[0] + fees[1]) * 100  # Two cheapest as percentage

    def _get_symbol_pair_fee(self, symbol: str) -> float:
        """Get the dominant pair's combined fee from recent tick data."""
        ticks = self._ticks.get(symbol, deque())
        profitable = [t for t in ticks if t.best_net_pct > 0]

        if not profitable:
            # No tick data — estimate from all exchanges
            return self._get_cheapest_pair_fee(symbol)

        # Find most common buyer and seller from profitable ticks
        buy_counts: dict[str, int] = defaultdict(int)
        sell_counts: dict[str, int] = defaultdict(int)
        for t in profitable[-100:]:  # Last 100 profitable ticks
            buy_counts[t.buy_exchange] += 1
            sell_counts[t.sell_exchange] += 1

        top_buyer = max(buy_counts, key=buy_counts.get) if buy_counts else ""
        top_seller = max(sell_counts, key=sell_counts.get) if sell_counts else ""

        if not top_buyer or not top_seller or not self._fee_manager:
            return self._get_cheapest_pair_fee(symbol)

        buy_fee = self._fee_manager.get_scoring_fee(top_buyer, symbol)
        sell_fee = self._fee_manager.get_scoring_fee(top_seller, symbol)
        return (buy_fee + sell_fee) * 100  # As percentage

    def _is_symbol_on_bitfinex(self, symbol: str) -> bool:
        """Check if symbol has a live Bitfinex price."""
        if "Bitfinex" not in self._balance._exchanges:
            return False
        for fetcher in self._fetchers:
            if fetcher.exchange_name == "Bitfinex":
                ps = fetcher.get_state().get(symbol)
                return bool(ps and ps.bid and float(ps.bid) > 0)
        return False

    def _bitfinex_sell_route(self, symbol: str) -> tuple[bool, float]:
        """Decide if demotion sells should route through Bitfinex 0% taker.

        Returns (route_via_bitfinex, bid_for_valuation).

        Tolerates the event-driven feed gap by using a cached last-known
        Bitfinex bid (`_bitfinex_last_bid`), so brief 10-20s windows where
        Bitfinex hasn't pushed an update don't force a fallback to local-
        exchange selling at 0.04-0.10% taker. v0.30.7-beta — fixes S27's
        $0.28 demotion-sell fee leak.

        Conditions for routing via Bitfinex:
        - Bitfinex is in the active exchanges set
        - Symbol is not blocked on Bitfinex (manual or auto blocklist)
        - Either: (a) Bitfinex has a live bid right now, OR
                 (b) Bitfinex has previously quoted this symbol (cached bid)
        """
        if "Bitfinex" not in self._balance._exchanges:
            return False, 0.0
        if self._fee_manager is not None:
            if not self._fee_manager.is_symbol_enabled("Bitfinex", symbol):
                return False, 0.0
            # Both buy/sell roles must be allowed for the route to make sense
            # (we transfer crypto to Bitfinex and sell — the sell side must
            # be permitted).
            if not self._fee_manager.can_sell("Bitfinex", symbol):
                return False, 0.0

        # Try live bid first
        for fetcher in self._fetchers:
            if fetcher.exchange_name == "Bitfinex":
                ps = fetcher.get_state().get(symbol)
                if ps and ps.bid:
                    try:
                        live_bid = float(ps.bid)
                        if live_bid > 0:
                            self._bitfinex_last_bid[symbol] = live_bid
                            return True, live_bid
                    except (ValueError, TypeError):
                        pass
                break  # Found Bitfinex fetcher, no live bid — fall through

        # Fall back to cached last-known bid (event-driven feed gap)
        cached = self._bitfinex_last_bid.get(symbol, 0.0)
        if cached > 0:
            return True, cached

        return False, 0.0

    def _any_active_on_bitfinex(self) -> bool:
        """Check if any active symbol is tradeable on Bitfinex."""
        if not self._active_symbols:
            return False
        for sym in self._active_symbols:
            if self._is_symbol_on_bitfinex(sym):
                return True
        return False

    def _run_inventory_rebalance(self, now: float) -> None:
        """Trigger periodic inventory drift correction (Feature 4).

        Builds (exchange, symbol) pairs from current dominant pairs of all
        active symbols, then calls balance.rebalance_inventory_drift().
        """
        pairs: list[tuple[str, str]] = []
        for sym in self._active_symbols:
            dom = self._dominant_pairs.get(sym, {})
            seen: set[str] = set()
            for ex, _ in dom.get("buyers", []):
                if ex not in seen:
                    pairs.append((ex, sym))
                    seen.add(ex)
            for ex, _ in dom.get("sellers", []):
                if ex not in seen:
                    pairs.append((ex, sym))
                    seen.add(ex)

        if not pairs:
            logger.info("[Inventory] Periodic rebalance SKIPPED: no dominant pairs")
            return

        prices = self._get_all_prices()
        logger.info(
            f"[Inventory] Periodic rebalance START: {len(pairs)} (exchange, symbol) pairs, "
            f"drift_threshold={self._inventory_drift_threshold*100:.0f}%, "
            f"interval={self._inventory_rebalance_interval/3600:.1f}h"
        )
        transfers = self._balance.rebalance_inventory_drift(
            pairs, prices, drift_threshold=self._inventory_drift_threshold,
        )
        if transfers:
            total_value = sum(t.amount_usd for t in transfers)
            total_fee = sum(t.fee_usd for t in transfers)
            n_sells = sum(1 for t in transfers if t.transfer_type == "inventory_drift_sell")
            n_buys = sum(1 for t in transfers if t.transfer_type == "inventory_drift_buy")
            logger.info(
                f"[Inventory] Periodic rebalance DONE: {n_sells} sells + {n_buys} buys, "
                f"total=${total_value:.2f}, fees=${total_fee:.4f}"
            )
        else:
            logger.info("[Inventory] Periodic rebalance DONE: no drift exceeded threshold")

    def _consolidate_idle_exchange_crypto(self, idle_threshold: float = 900.0) -> None:
        """Transfer crypto from idle exchanges to Bitfinex and sell at 0%.

        With symmetric allocation, all dominant exchanges hold crypto.
        If an exchange hasn't had a trade in idle_threshold seconds, its
        crypto is unproductive. Transfer to Bitfinex (0% taker) frees it
        as USDT for redistribution.

        Uses a longer threshold than USDT consolidation (15 min vs 10 min)
        since restoring crypto costs a taker fee on the destination exchange.
        """
        if not self._balance or "Bitfinex" not in self._balance._exchanges:
            return

        now = time.time()
        prices = self._get_all_prices()

        # Build Bitfinex bid prices for available symbols
        bitfinex_bids: dict[str, float] = {}
        for fetcher in self._fetchers:
            if fetcher.exchange_name == "Bitfinex":
                state = fetcher.get_state()
                for symbol in self._active_symbols:
                    ps = state.get(symbol)
                    if ps and ps.bid and float(ps.bid) > 0:
                        bitfinex_bids[symbol] = float(ps.bid)
                break

        if not bitfinex_bids:
            return

        # Collect all active exchanges per symbol (symmetric — any exchange holds crypto)
        for symbol in list(self._active_symbols):
            if symbol not in bitfinex_bids:
                continue  # Bitfinex doesn't have this symbol

            pairs = self._dominant_pairs.get(symbol, {})
            all_sym_exchanges = {ex for ex, _ in pairs.get("buyers", [])} | {ex for ex, _ in pairs.get("sellers", [])}
            for ex in all_sym_exchanges:
                if ex == "Bitfinex":
                    continue

                # Check if this seller exchange is idle
                last_trade = self._balance.last_trade_time.get(ex, 0.0)
                idle_seconds = now - last_trade if last_trade > 0 else float("inf")
                if idle_seconds < idle_threshold:
                    continue  # Recently active, keep crypto

                # Check if exchange has meaningful crypto of this symbol
                qty = self._balance.crypto[ex].get(symbol, 0.0)
                if qty <= 0:
                    continue

                transfer = self._balance.sell_crypto_via_bitfinex(
                    source_exchange=ex,
                    symbol=symbol,
                    qty=qty,
                    bitfinex_bid=bitfinex_bids[symbol],
                )
                if transfer:
                    proceeds = transfer.amount_usd
                    logger.info(
                        f"[Capital] Idle crypto sold via Bitfinex 0%: "
                        f"{symbol} on {ex} idle {idle_seconds:.0f}s, "
                        f"${proceeds:.2f} USDT credited to Bitfinex"
                    )
                    # v0.30: sweep proceeds to custody hub instead of leaving on Bitfinex
                    sweep = self._balance.transfer_to_custody_hub("Bitfinex", proceeds)
                    if sweep:
                        logger.info(
                            f"[Capital] Idle-sell sweep: ${sweep.amount_usd:.2f} "
                            f"Bitfinex→{sweep.to_exchange}"
                        )

    # ── Expansion ────────────────────────────────────────────────────────

    def _estimate_expansion_cost(self, symbol: str, score: SymbolScore) -> float:
        """Estimate the total fee of setting up capital for a new symbol.

        Considers current balance state: if buyer/seller exchanges have no
        capital, includes the cheapest rebalance cost (internal sell taker fee
        or external transfer withdrawal fee) for each exchange that needs funding.
        Also includes eventual demotion sell cost (taker fee on seller capital).
        """
        if not self._balance or not self._fee_manager:
            return 0.0

        # Compute what dominant pairs would look like
        if score.score >= self._very_strong_threshold:
            max_dir = 3
        elif score.score >= self._strong_threshold:
            max_dir = 2
        else:
            max_dir = 2
        pairs = self._compute_dominant_pairs(symbol, max_per_direction=max_dir)

        total_cost = 0.0
        needed_per_exchange = self._trade_amount * 3  # 3× trade amount needed

        # Cost to get USDT on buyer exchanges (for buying)
        # Use raw USDT balance (not reserve-adjusted) for Bitfinex because the
        # reserve IS the trading capital when Bitfinex is the buyer.  The reserve
        # protects per-trade execution via available_usdt_for_trading(), but for
        # expansion cost estimation we only care whether USDT physically exists
        # on the exchange — no external transfer is needed if it does.
        for ex, _ in pairs["buyers"]:
            usdt_avail = (
                self._balance.usdt.get(ex, 0.0)
                if ex == "Bitfinex"
                else self._balance.available_usdt_for_trading(ex)
            )
            if usdt_avail >= needed_per_exchange:
                continue  # already funded
            # Estimate cheapest way to get USDT here
            internal_fee = needed_per_exchange * self._fee_manager.get_taker_fee(ex)
            external_fee = self._balance._get_withdrawal_fee(ex)  # cheapest source fee
            # Find actual cheapest source
            cheapest_ext = float("inf")
            for src in self._balance._exchanges:
                if src == ex:
                    continue
                src_avail = self._balance._available_usdt_for_rebalance(src)
                if src_avail >= needed_per_exchange:
                    cheapest_ext = min(cheapest_ext, self._balance._get_withdrawal_fee(src))
            if cheapest_ext < float("inf"):
                total_cost += min(internal_fee, cheapest_ext)
            else:
                total_cost += internal_fee  # internal sell is the only option

        # Cost to get crypto on seller exchanges (for selling)
        for ex, _ in pairs["sellers"]:
            usdt_avail = self._balance.usdt.get(ex, 0.0)
            if usdt_avail >= needed_per_exchange:
                # Can buy crypto directly — taker fee
                total_cost += needed_per_exchange * self._fee_manager.get_taker_fee(ex)
            else:
                # Need USDT transferred + buy fee
                internal_fee = needed_per_exchange * self._fee_manager.get_taker_fee(ex)
                cheapest_ext = float("inf")
                for src in self._balance._exchanges:
                    if src == ex:
                        continue
                    src_avail = self._balance._available_usdt_for_rebalance(src)
                    if src_avail >= needed_per_exchange:
                        cheapest_ext = min(cheapest_ext, self._balance._get_withdrawal_fee(src))
                if cheapest_ext < float("inf"):
                    total_cost += cheapest_ext + internal_fee  # transfer + buy
                else:
                    total_cost += internal_fee * 2  # sell existing + buy new

        # Eventual demotion sell cost (taker fee on all seller positions)
        for ex, _ in pairs["sellers"]:
            total_cost += needed_per_exchange * self._fee_manager.get_taker_fee(ex)

        return total_cost

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
        # Symmetric: buy crypto (50% of allocation) on ALL dominant exchanges
        exchange_weights: dict[str, float] = {}
        for ex, w in pairs["buyers"]:
            exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
        for ex, w in pairs["sellers"]:
            exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
        total_w = sum(exchange_weights.values())
        total_alloc = self._trade_amount * len(self._balance._exchanges)
        for ex, w in exchange_weights.items():
            # Only 50% of allocation as crypto (symmetric — keep 50% as USDT)
            alloc = total_alloc * (w / total_w) * 0.5 if total_w > 0 else self._trade_amount * 0.5
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

        exchanges_str = ",".join(exchange_weights.keys())
        logger.info(
            f"[Optimizer] Expansion symmetric on: [{exchanges_str}]"
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
            # Consolidate to Bitfinex hub even when in deficit (not gated by PnL)
            # Skip if no active symbol is tradeable on Bitfinex (avoids circular waste)
            if (
                self._balance
                and "Bitfinex" in self._balance._exchanges
                and self._any_active_on_bitfinex()
            ):
                # Symmetric: all dominant exchanges are both buyers and sellers
                active_exchanges = set()
                for sym in self._active_symbols:
                    pairs = self._dominant_pairs.get(sym, {})
                    for ex_name, _ in pairs.get("buyers", []):
                        active_exchanges.add(ex_name)
                    for ex_name, _ in pairs.get("sellers", []):
                        active_exchanges.add(ex_name)
                exchange_set = active_exchanges if self._active_symbols else None
                fee_cap = 0.02 if not self._rotation_budget_ok else None
                self._balance.consolidate_to_custody_hub(
                    exchange_set, idle_threshold=1800.0,
                    active_seller_exchanges=exchange_set,
                    max_fee_per_source=fee_cap,
                )
                self._consolidate_idle_exchange_crypto(idle_threshold=1800.0)
                fee_cap_r = 0.02 if not self._rotation_budget_ok else None
                self._balance.replenish_trading_float(max_fee_per_source=fee_cap_r)
            elif self._balance and "Bitfinex" in self._balance._exchanges:
                logger.info(
                    "[Optimizer] Consolidation SKIPPED (deficit path): "
                    "no active symbol tradeable on Bitfinex"
                )
            return

        # Clean up expired demotion cooldowns. Cooldown is scaled by
        # 24h demotion count when frequency scaling is enabled — a
        # symbol that keeps churning gets locked out longer each time.
        expired = [
            sym for sym, ts in self._recently_demoted.items()
            if now - ts >= self._compute_demotion_cooldown(sym)
        ]
        for sym in expired:
            del self._recently_demoted[sym]
            logger.info(f"[Optimizer] Cooldown expired for {sym}, eligible for re-activation")

        # Phase 3: Update watchlist
        self._update_watchlist()

        # Phase 3.5: Re-evaluate dominant exchange pairs for active symbols
        self._reevaluate_dominant_pairs()

        # Phase 3.6: Replenish Bitfinex reserve
        # When net-negative, only replenish from free/near-free sources
        if self._balance:
            fee_cap = 0.02 if not self._rotation_budget_ok else None
            self._balance.replenish_trading_float(max_fee_per_source=fee_cap)

        # Phase 4: Evaluate demotions first
        self._evaluate_demotions()

        # Phase 4.5: Consolidate idle capital to Bitfinex hub
        # Skip if no active symbol is tradeable on Bitfinex (avoids circular waste)
        if (
            self._balance
            and "Bitfinex" in self._balance._exchanges
            and self._any_active_on_bitfinex()
        ):
            # Symmetric: all dominant exchanges are both buyers and sellers
            active_exchanges = set()
            for sym in self._active_symbols:
                pairs = self._dominant_pairs.get(sym, {})
                for ex_name, _ in pairs.get("buyers", []):
                    active_exchanges.add(ex_name)
                for ex_name, _ in pairs.get("sellers", []):
                    active_exchanges.add(ex_name)
            # Full consolidation if no active symbols, partial otherwise
            # When net-negative, only consolidate from free/near-free sources
            exchange_set = active_exchanges if self._active_symbols else None
            fee_cap = 0.02 if not self._rotation_budget_ok else None
            transfers = self._balance.consolidate_to_custody_hub(
                exchange_set, idle_threshold=1800.0,
                active_seller_exchanges=exchange_set,
                max_fee_per_source=fee_cap,
            )
            if transfers:
                hub_fee = sum(t.fee_usd for t in transfers)
                hub_amt = sum(t.amount_usd for t in transfers)
                logger.info(
                    f"[Optimizer] Idle consolidation: "
                    f"{len(transfers)} transfers, ${hub_amt:.2f} to Bitfinex "
                    f"(fees: ${hub_fee:.4f})"
                )
            # Also consolidate crypto from idle exchanges (30 min threshold)
            self._consolidate_idle_exchange_crypto(idle_threshold=1800.0)
        elif (
            self._balance
            and "Bitfinex" in self._balance._exchanges
            and self._active_symbols
        ):
            # Throttle: log every 5 min
            if not hasattr(self, "_last_consol_skip_log"):
                self._last_consol_skip_log = 0.0
            if now - self._last_consol_skip_log >= 300:
                logger.info(
                    "[Optimizer] Idle consolidation SKIPPED: "
                    "no active symbol tradeable on Bitfinex "
                    f"(active={list(self._active_symbols)})"
                )
                self._last_consol_skip_log = now

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
                # Pair fee viability: block if dominant pair's combined fees exceed avg net%
                # Same gate as expansion — prevents rotating into symbols that lose on every trade
                pair_fee_blocked = False
                if self._fee_manager:
                    cand_pairs = self._compute_dominant_pairs(best_candidate.symbol, max_per_direction=2)
                    buyers = cand_pairs.get("buyers", [])
                    sellers = cand_pairs.get("sellers", [])
                    if buyers and sellers:
                        buy_fee = self._fee_manager.get_taker_fee(buyers[0][0])
                        sell_fee = self._fee_manager.get_taker_fee(sellers[0][0])
                        combined_fee_pct = (buy_fee + sell_fee) * 100
                        avg_net = best_candidate.avg_profitable_net
                        if combined_fee_pct > avg_net * 0.8 and avg_net > 0:
                            logger.info(
                                f"[Candidate] ROTATE_BLOCKED {best_candidate.symbol}: "
                                f"pair_fee={combined_fee_pct:.3f}% > "
                                f"avg_net={avg_net:.3f}%x0.8={avg_net*0.8:.3f}% "
                                f"({buyers[0][0]}->{sellers[0][0]}) — pair_fee_exceeds_net"
                            )
                            pair_fee_blocked = True
                if pair_fee_blocked:
                    confirmed_candidates.pop(0)
                    continue

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
                key=lambda s: s.score * (1.0 if self._is_symbol_on_bitfinex(s.symbol) else 0.7),
                reverse=True,
            )
            now = time.time()
            for candidate in expansion_candidates:
                if len(self._active_symbols) >= self._max_active_symbols:
                    break
                # Stability gate for expansion
                wl_entry = self._watchlist.get(candidate.symbol)
                if wl_entry is None:
                    # First seen — create watchlist entry to start tracking
                    self._watchlist[candidate.symbol] = WatchlistEntry(
                        symbol=candidate.symbol,
                        entered_at=now,
                        confirmation_start=now,
                        score_samples=[candidate.score],
                        peak_score=candidate.score,
                    )
                    logger.info(
                        f"[Candidate] EXPAND_TRACK {candidate.symbol}: "
                        f"score={candidate.score:.6f} "
                        f"avg_net={candidate.avg_profitable_net:.4f}% "
                        f"freq={candidate.frequency:.1%} "
                        f"ticks={candidate.profitable_ticks}/{candidate.total_ticks} "
                        f"est_hourly=${candidate.est_hourly_profit:.4f} — "
                        f"first seen, observing stability"
                    )
                    continue
                wl_entry.add_sample(candidate.score)
                if len(wl_entry.score_samples) >= 10:
                    wl_entry.peak_score = max(wl_entry.peak_score, candidate.score)
                stable, reason = self._is_score_stable(wl_entry, candidate.score)
                if not stable:
                    logger.info(
                        f"[Candidate] EXPAND_WAIT {candidate.symbol}: "
                        f"score={candidate.score:.6f} peak={wl_entry.peak_score:.6f} "
                        f"avg_net={candidate.avg_profitable_net:.4f}% "
                        f"freq={candidate.frequency:.1%} — "
                        f"unstable: {reason}"
                    )
                    continue
                # Expansion cost gate: estimate setup cost vs expected profit.
                # Setup cost requires a stricter horizon than reallocation —
                # `activation_profit_horizon_multiplier` raises the bar for
                # NEW activations (which pay full setup). Reallocations
                # between already-active exchanges keep using the base
                # horizon since the inventory is already in place.
                est_cost = self._estimate_expansion_cost(candidate.symbol, candidate)
                effective_horizon = (
                    self._reallocation_cost_horizon * self._activation_profit_horizon_multiplier
                )
                est_benefit = candidate.est_hourly_profit * effective_horizon
                if est_cost > 0 and est_benefit > 0 and est_cost > est_benefit:
                    logger.info(
                        f"[Candidate] EXPAND_BLOCKED {candidate.symbol}: "
                        f"setup_cost=${est_cost:.4f} > "
                        f"est_benefit=${est_benefit:.4f} "
                        f"(hourly=${candidate.est_hourly_profit:.4f} × "
                        f"{effective_horizon:.1f}h, "
                        f"base={self._reallocation_cost_horizon}h × "
                        f"activation_mult={self._activation_profit_horizon_multiplier:.1f})"
                    )
                    continue
                # Pair fee viability: block if dominant pair's combined fees exceed avg net%
                if self._fee_manager:
                    cand_pairs = self._compute_dominant_pairs(candidate.symbol, max_per_direction=2)
                    buyers = cand_pairs.get("buyers", [])
                    sellers = cand_pairs.get("sellers", [])
                    if buyers and sellers:
                        buy_fee = self._fee_manager.get_taker_fee(buyers[0][0])
                        sell_fee = self._fee_manager.get_taker_fee(sellers[0][0])
                        combined_fee_pct = (buy_fee + sell_fee) * 100  # convert to %
                        avg_net = candidate.avg_profitable_net
                        if combined_fee_pct > avg_net * 0.8 and avg_net > 0:
                            logger.info(
                                f"[Candidate] EXPAND_BLOCKED {candidate.symbol}: "
                                f"pair_fee={combined_fee_pct:.3f}% > "
                                f"avg_net={avg_net:.3f}%×0.8={avg_net*0.8:.3f}% "
                                f"({buyers[0][0]}→{sellers[0][0]}) — pair_fee_exceeds_net"
                            )
                            continue
                logger.info(
                    f"[Candidate] EXPAND_READY {candidate.symbol}: "
                    f"score={candidate.score:.6f} peak={wl_entry.peak_score:.6f} "
                    f"avg_net={candidate.avg_profitable_net:.4f}% "
                    f"freq={candidate.frequency:.1%} "
                    f"ticks={candidate.profitable_ticks}/{candidate.total_ticks} "
                    f"est_hourly=${candidate.est_hourly_profit:.4f} "
                    f"setup_cost=${est_cost:.2f} "
                    f"bfx={'yes' if self._is_symbol_on_bitfinex(candidate.symbol) else 'no'} "
                    f"— activating"
                )
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

        # 2. Buy new symbol crypto on ALL dominant exchanges (symmetric 50%)
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

        exchange_weights: dict[str, float] = {}
        for ex, w in pairs["buyers"]:
            exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
        for ex, w in pairs["sellers"]:
            exchange_weights[ex] = exchange_weights.get(ex, 0.0) + w
        total_w = sum(exchange_weights.values())
        total_alloc = self._trade_amount * len(self._balance._exchanges)
        for ex, w in exchange_weights.items():
            alloc = total_alloc * (w / total_w) * 0.5 if total_w > 0 else self._trade_amount * 0.5
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

        # Per-role filtering: drop buyer/seller scores for exchanges the
        # operator has disabled in that role (Fee Management → Buyer/Seller
        # checkboxes). Lets operator pin trades to specific routes, e.g.
        # Bitfinex(buyer)+MEXC(seller) only.
        if self._fee_manager:
            buy_scores = {
                ex: s for ex, s in buy_scores.items()
                if self._fee_manager.can_buy(ex, symbol)
            }
            sell_scores = {
                ex: s for ex, s in sell_scores.items()
                if self._fee_manager.can_sell(ex, symbol)
            }

        if not buy_scores or not sell_scores:
            # Fall back to active exchanges respecting role flags
            allowed_buyers = [
                ex for ex in self._active_exchanges
                if not self._fee_manager or self._fee_manager.can_buy(ex, symbol)
            ]
            allowed_sellers = [
                ex for ex in self._active_exchanges
                if not self._fee_manager or self._fee_manager.can_sell(ex, symbol)
            ]
            equal_w = 1.0 / max(len(self._active_exchanges), 1)
            return {
                "buyers": [(ex, equal_w) for ex in allowed_buyers[:max_per_direction]],
                "sellers": [(ex, equal_w) for ex in allowed_sellers[:max_per_direction]],
                "num_exchanges": min(
                    len(set(allowed_buyers) | set(allowed_sellers)),
                    max_per_direction * 2,
                ),
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

                # Per-exchange role boost: operator-set preference multiplier
                # (default 1.0 = neutral, Bitfinex.buyer_boost=5.0 / MEXC.seller_boost=5.0
                # bias the bot toward the cheapest sustainable route).
                if direction == "buy":
                    weighted = [
                        (ex, w * self._fee_manager.get_buyer_boost(ex))
                        for ex, w in weighted
                    ]
                else:  # "sell"
                    weighted = [
                        (ex, w * self._fee_manager.get_seller_boost(ex))
                        for ex, w in weighted
                    ]

            # Seller penalty: USDT accumulates on sell exchanges, so penalize
            # those with high withdrawal fees (capital gets trapped there).
            # Exchanges with fee > $0.05 get weight reduced proportionally
            # (up to 50% for $0.50+ fees). This prevents expensive-withdrawal
            # exchanges like OKX ($0.10) from being selected as sellers
            # when micro-profit trades can't recover the rebalance cost.
            if direction == "sell" and self._balance:
                for i, (ex, w) in enumerate(weighted):
                    wfee = self._balance._get_withdrawal_fee(ex, 100.0)
                    if wfee > 0.05:
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

    def get_symbol_exchange_view(self, symbol: str) -> dict:
        """Return ranked exchange weights for a symbol (dashboard display).

        Unlike `_compute_dominant_pairs`, this:
        - Returns ALL active exchanges (not top-N), so the dashboard can show
          a full ranked list per direction.
        - Includes blocked exchanges marked with `blocked=True` so the operator
          can see WHY a particular exchange isn't being used.
        - Computes weights via the same fee/role-boost/withdrawal-penalty math
          as dominant pair detection — so the order matches what allocation
          would actually pick.

        Output shape:
            {
                "buyers":  [{"exchange": ex, "weight": w, "blocked": bool}, ...],
                "sellers": [{"exchange": ex, "weight": w, "blocked": bool}, ...],
            }
        Both lists sorted by weight desc within each subset (allowed first,
        then blocked at the end ordered by what their weight WOULD be).
        """
        buy_scores: dict[str, float] = defaultdict(float)
        sell_scores: dict[str, float] = defaultdict(float)

        ticks = self._ticks.get(symbol, deque())
        profitable = [t for t in ticks if t.best_net_pct > 0]

        # Note: post option-1, profitable ticks already exclude blocked pairs,
        # so we DON'T have ranking weight for blocked exchanges from live data.
        # Fall back to historical counts (which include pre-block data) so the
        # operator can still see the rough ordering of blocked exchanges.
        for t in profitable:
            buy_scores[t.buy_exchange] += t.best_net_pct
            sell_scores[t.sell_exchange] += t.best_net_pct

        stats = self._historical_stats.get(symbol)
        if stats:
            for ex, count in stats.buy_exchange_counts.items():
                if ex not in buy_scores:
                    buy_scores[ex] += count * 0.001  # tiny weight, just for ordering
            for ex, count in stats.sell_exchange_counts.items():
                if ex not in sell_scores:
                    sell_scores[ex] += count * 0.001

        def _build_ranked(
            scores: dict[str, float], direction: str
        ) -> list[dict]:
            # Apply same weighting math as _select_top, but no trim.
            allowed_scores = {ex: s for ex, s in scores.items() if (
                self._fee_manager is None or
                (self._fee_manager.can_buy(ex, symbol) if direction == "buy"
                 else self._fee_manager.can_sell(ex, symbol))
            )}

            # Normalize allowed
            ranked: list[dict] = []
            total = sum(allowed_scores.values())
            if total > 0 and self._fee_manager:
                weighted = [(ex, s / total) for ex, s in allowed_scores.items()]
                fees = {ex: self._fee_manager.get_scoring_fee(ex) for ex, _ in weighted}
                max_fee = max(fees.values(), default=0.001) or 0.001
                weighted = [
                    (ex, w * (1 + (max_fee - fees.get(ex, max_fee)) / max_fee))
                    for ex, w in weighted
                ]
                if direction == "buy":
                    weighted = [(ex, w * self._fee_manager.get_buyer_boost(ex)) for ex, w in weighted]
                else:
                    weighted = [(ex, w * self._fee_manager.get_seller_boost(ex)) for ex, w in weighted]
                if direction == "sell" and self._balance:
                    out = []
                    for ex, w in weighted:
                        wfee = self._balance._get_withdrawal_fee(ex, 100.0)
                        if wfee > 0.05:
                            w = w * (1 - min(0.5, wfee))
                        out.append((ex, w))
                    weighted = out
                weighted.sort(key=lambda x: x[1], reverse=True)
                ranked.extend({"exchange": ex, "weight": round(w, 4), "blocked": False}
                              for ex, w in weighted)
            elif allowed_scores:
                # No fee_manager — just sort by raw scores
                eq = sorted(allowed_scores.items(), key=lambda x: x[1], reverse=True)
                ranked.extend({"exchange": ex, "weight": 0.0, "blocked": False}
                              for ex, _ in eq)

            # Append blocked exchanges (with their raw historical weight as "would-be")
            blocked_scores = {ex: s for ex, s in scores.items() if ex not in allowed_scores}
            if blocked_scores:
                blocked_total = sum(blocked_scores.values()) or 1.0
                blocked_sorted = sorted(blocked_scores.items(), key=lambda x: x[1], reverse=True)
                ranked.extend({
                    "exchange": ex,
                    "weight": round(s / blocked_total, 4),
                    "blocked": True,
                } for ex, s in blocked_sorted)

            return ranked

        return {
            "buyers": _build_ranked(buy_scores, "buy"),
            "sellers": _build_ranked(sell_scores, "sell"),
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
                # No-trades-since-last-alloc gate: dominant-pair detection
                # keeps shifting based on tick-level scoring, but moving
                # capital across exchanges costs taker fees on BOTH sides
                # of the swap. If we haven't actually traded the symbol
                # since the previous allocation, the previous allocation
                # didn't generate value — chasing a new "winner" is
                # speculative and the cost often exceeds any benefit.
                # Observed in S31: Group 2/Config 3 paid $0.38 in
                # internal-taker fees from a single
                # [Bybit,MEXC,OKX]→[Bitget,MEXC,OKX] reallocation despite
                # zero AR trades since activation.
                last_realloc = self._last_reallocation.get(sym, 0.0)
                trades_since = 0
                if self._monitor is not None:
                    trades_since = sum(
                        1 for t in self._monitor._trades
                        if t.symbol == sym and t.timestamp > last_realloc
                    )
                if trades_since == 0:
                    logger.info(
                        f"[Optimizer] Reallocation SKIPPED for {sym}: "
                        f"0 trades since last allocation — no realized "
                        f"value to justify reallocation churn"
                    )
                    continue
                if self._reallocate_symbol(sym, old_pairs, new_pairs):
                    self._dominant_pairs[sym] = new_pairs
                    self._last_reallocation[sym] = now

    def _reallocate_symbol(
        self, symbol: str, old_pairs: dict, new_pairs: dict
    ) -> bool:
        """Move capital for a symbol from old dominant exchanges to new ones.
        Returns True if capital was actually moved, False if skipped."""
        from balance import Transfer

        prices = self._get_all_prices()
        price = prices.get(symbol, 0.0)
        if price <= 0:
            return False

        now = time.time()
        # Symmetric: track ALL exchanges (buyers + sellers combined)
        old_exchanges = {ex for ex, _ in old_pairs.get("buyers", [])} | {ex for ex, _ in old_pairs.get("sellers", [])}
        new_exchanges = {ex for ex, _ in new_pairs.get("buyers", [])} | {ex for ex, _ in new_pairs.get("sellers", [])}
        removed_sellers = old_exchanges - new_exchanges
        added_sellers = new_exchanges - old_exchanges

        if not removed_sellers and not added_sellers:
            return False

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
            return False

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
        old_str = ",".join(old_exchanges)
        new_str = ",".join(new_exchanges)
        logger.info(
            f"[Optimizer] Reallocated {symbol}: exchanges [{old_str}]→[{new_str}], "
            f"fees: ${total_fee:.4f}"
        )
        return True

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
                "exchange_view": self.get_symbol_exchange_view(s.symbol),
                "current_net_pct": round(self._ticks[s.symbol][-1].best_net_pct, 4) if s.symbol in self._ticks and self._ticks[s.symbol] else 0.0,
                "diagnostic": self._build_symbol_diagnostic(s, s.symbol in active_set, now),
            }
            for i, s in enumerate(ranked)
        ]

    def _build_symbol_diagnostic(self, s, is_active: bool, now: float) -> dict:
        """Build a structured diagnostic explaining a symbol's current state.

        Used by the dashboard hover tooltip to show WHY a symbol is active /
        candidate / blocked. All values are pre-computed strings so the UI
        can just render them.
        """
        symbol = s.symbol
        threshold = self._get_activation_threshold(symbol)
        fee_adj = self._compute_fee_threshold_adjustment(symbol)
        score = s.score

        # Tier (matches focus tier classification)
        if score >= self._very_strong_threshold:
            tier = "very_strong"
        elif score >= self._strong_threshold:
            tier = "strong"
        elif score >= self._trading_threshold:
            tier = "normal"
        else:
            tier = "weak"

        # Trajectory (from per-symbol score history — live for both
        # active and candidate symbols, updated each tick in _compute_scores)
        history = self._score_history.get(symbol)
        wl = self._watchlist.get(symbol)
        if history and len(history) >= 30:
            peak_for_traj = wl.peak_score if wl else max(history)
            trajectory = self._classify_trajectory(history, peak_score=peak_for_traj)
            samples_count = len(history)
        elif history:
            trajectory = "insufficient_data"
            samples_count = len(history)
        else:
            trajectory = "insufficient_data"
            samples_count = 0

        # Status reason
        reasons: list[str] = []
        if is_active:
            status = "active"
            mult = round(s.trade_multiplier, 2)
            sized = round(self._trade_amount * s.trade_multiplier, 2)
            reasons.append(f"Active in dominant pair (multiplier {mult}×, trade size ${sized})")
        elif symbol in self._recently_demoted:
            status = "cooldown"
            cd = max(0.0, self._demotion_cooldown - (now - self._recently_demoted[symbol]))
            reasons.append(f"In demotion cooldown ({cd:.0f}s remaining)")
        elif score < threshold:
            status = "below_threshold"
            reasons.append(
                f"Score {score:.4f} < activation threshold {threshold:.4f}"
            )
            reasons.append(
                f"Need score ≥ {threshold:.4f} (= base {self._trading_threshold} + fee_adj {fee_adj:+.4f})"
            )
        elif trajectory == "declining":
            status = "candidate_declining"
            reasons.append(
                f"Score is declining — falls back to standard {self._scoring_window // 2}s wait"
            )
        elif trajectory == "insufficient_data":
            status = "candidate_warming_up"
            reasons.append(f"Need 30+ samples for trajectory check (have {samples_count})")
        else:
            status = "candidate"
            # Determine fast-track requirement
            if score >= self._strong_threshold:
                base = 30.0 if trajectory == "rising" else 60.0
                tier_label = "strong+"
            else:
                base = 240.0 if trajectory == "rising" else 300.0
                tier_label = "normal"
            required = base * self._fast_track_aggressiveness
            reasons.append(
                f"Fast-track {tier_label}+{trajectory}: needs {required:.0f}s observation"
            )
            if score >= self._strong_threshold:
                # Tier-confirmation gate (uses live score_history)
                n_check = int(required)
                if history and len(history) >= n_check:
                    recent = list(history)[-n_check:]
                    strong_count = sum(1 for x in recent if x >= self._strong_threshold)
                    if strong_count < n_check:
                        reasons.append(
                            f"Tier-confirmation: {strong_count}/{n_check} recent samples at strong tier"
                        )
            if s.total_ticks < required:
                reasons.append(
                    f"Observation: {s.total_ticks}/{int(required)} ticks accumulated"
                )

        # Score breakdown
        score_formula = (
            f"avg_profitable_net {s.avg_profitable_net:.4f}% × frequency "
            f"{s.frequency:.1%} = score {score:.4f}"
        )

        # Watchlist details
        wl_info = {}
        if wl:
            elapsed = now - wl.entered_at
            wl_info = {
                "entered_seconds_ago": round(elapsed, 0),
                "samples": samples_count,
                "peak_score": round(wl.peak_score, 4),
                "confirmed": bool(wl.confirmed),
            }

        return {
            "status": status,
            "tier": tier,
            "trajectory": trajectory,
            "reasons": reasons,
            "score_formula": score_formula,
            "threshold_breakdown": (
                f"base {self._trading_threshold:.4f} + fee_adj {fee_adj:+.4f} "
                f"= {threshold:.4f}"
            ),
            "watchlist": wl_info,
        }

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
            current_score = entry.score_samples[-1] if entry.score_samples else 0.0
            stable, stability_reason = self._is_score_stable(entry, current_score)
            result.append({
                "symbol": sym,
                "watching_since": entry.entered_at,
                "elapsed": round(elapsed, 1),
                "progress": round(progress, 1),
                "confirmed": entry.confirmed,
                "avg_score": round(avg_score, 6),
                "peak_score": round(entry.peak_score, 6),
                "stable": stable,
                "stability_reason": stability_reason,
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
        # Aggregates mirror the deques — reset alongside
        self._agg_total.clear()
        self._agg_sum_net.clear()
        self._agg_prof_count.clear()
        self._agg_prof_sum.clear()
        self._best_net_dq.clear()
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
                    # Serialize deque as list for JSON; from_state_dict
                    # coerces back to deque(maxlen=60).
                    "score_samples": list(e.score_samples),
                    "peak_score": e.peak_score,
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
        # Trim score_samples to SAMPLES_MAX in case a pre-cap state file
        # is being loaded with a long list.
        self._watchlist = {}
        for sym, entry in data.get("_watchlist", {}).items():
            entry = dict(entry)
            saved = entry.get("score_samples", []) or []
            if len(saved) > WatchlistEntry.SAMPLES_MAX:
                saved = saved[-WatchlistEntry.SAMPLES_MAX:]
            entry["score_samples"] = list(saved)
            self._watchlist[sym] = WatchlistEntry(**entry)
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
