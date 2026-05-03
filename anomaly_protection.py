"""
Anomaly Protection for ArbitrageBot.

3-layer trading safety system:
  Layer 1: Circuit Breaker — global pause on rolling P&L decline
  Layer 2: Drawdown Protection — global pause on portfolio peak-to-trough decline
  Layer 3: Per-Symbol Loss Streak — targeted symbol blocking

Warning level reduces trade size before global pause triggers.
Emergency sell-all on extreme drawdown (requires manual resume).
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AnomalyEvent:
    """Record of an anomaly trigger for the event log."""

    timestamp: float
    layer: str  # "circuit_breaker", "drawdown", "loss_streak", "warning", "manual"
    level: str  # "warning", "pause", "emergency", "resume", "block", "unblock"
    reason: str
    value: float = 0.0
    threshold: float = 0.0
    details: dict = field(default_factory=dict)


class AnomalyProtection:
    """3-layer anomaly protection with comprehensive diagnostic logging."""

    def __init__(
        self,
        # Layer 1: Circuit breaker
        circuit_breaker_window: int = 900,
        circuit_breaker_threshold: float = -5.0,
        circuit_breaker_resume_pct: float = 0.5,
        circuit_breaker_cooldown: int = 300,
        # Layer 2: Drawdown protection (legacy MTM gate — kept as a soft
        # per-symbol throttle at `drawdown_threshold_pct`; the legacy
        # emergency multiplier is replaced by the two-layer gate below)
        drawdown_threshold_pct: float = 5.0,
        drawdown_resume_pct: float = 3.0,
        drawdown_emergency_mult: float = 2.0,
        # v0.31.0-beta+: Two-layer emergency gate
        # Layer A — realized capital drawdown (primary)
        #   Catches actually-locked-in losses (closed bad trades, fees, etc.).
        #   Doesn't fire on MTM noise because realized capital only moves
        #   when money is permanently in/out.
        realized_drawdown_emergency_pct: float = 15.0,
        # Layer B — combined spot+hedge unrealized drawdown (hedge-health)
        #   Fires only when the hedge fails to offset spot price moves AND
        #   the breach persists past `combined_drawdown_sustained_seconds`
        #   (so flash quotes / in-transit transients can't trip it).
        combined_drawdown_emergency_pct: float = 25.0,
        combined_drawdown_sustained_seconds: float = 300.0,
        # Action: default is halt + alert. Set True to keep legacy
        # auto-sell-all behavior on emergency trigger.
        emergency_auto_liquidate: bool = False,
        # Layer 3: Per-symbol loss streak
        symbol_loss_streak_threshold: int = 4,
        symbol_loss_streak_cooldown: int = 300,
        # Warning level
        warning_pnl_pct: float = 0.5,
        # Master toggle
        enabled: bool = True,
    ) -> None:
        # Config
        self._enabled = enabled
        self._cb_window = circuit_breaker_window
        self._cb_threshold = circuit_breaker_threshold
        self._cb_resume_pct = circuit_breaker_resume_pct
        self._cb_cooldown = circuit_breaker_cooldown
        self._dd_threshold_pct = drawdown_threshold_pct
        self._dd_resume_pct = drawdown_resume_pct
        self._dd_emergency_mult = drawdown_emergency_mult
        # v0.31.0-beta+: two-layer emergency gate config
        self._realized_dd_emergency_pct = realized_drawdown_emergency_pct
        self._combined_dd_emergency_pct = combined_drawdown_emergency_pct
        self._combined_dd_sustained_s = combined_drawdown_sustained_seconds
        self._emergency_auto_liquidate = emergency_auto_liquidate
        self._sls_threshold = symbol_loss_streak_threshold
        self._sls_cooldown = symbol_loss_streak_cooldown
        self._warning_pnl_pct = warning_pnl_pct

        # State: Circuit breaker
        self._rolling_pnl: deque[tuple[float, float]] = deque()
        self._rolling_pnl_sum: float = 0.0

        # State: Drawdown
        # _peak_portfolio_value tracks the realized-capital peak (USDT +
        # locked-in P&L). _current_drawdown_pct is the COMBINED gate metric:
        # (realized_peak − mtm_value) / realized_peak. Used by Layer B and
        # the legacy soft per-symbol-block path.
        self._peak_portfolio_value: float = 0.0
        self._current_drawdown_pct: float = 0.0
        # v0.31.0-beta+: realized-only peak/drawdown for Layer A.
        # _peak_realized only ratchets on realized capital growth — it has
        # zero MTM exposure, so phantom drawdowns can't fire Layer A.
        self._peak_realized_value: float = 0.0
        self._current_realized_drawdown_pct: float = 0.0
        # Layer B sustained-breach tracker. Set to the timestamp when the
        # combined drawdown first crossed the emergency threshold; cleared
        # when it dips back below. The gate fires only when
        # (now − _combined_breach_start) >= combined_drawdown_sustained_seconds.
        self._combined_breach_start: float | None = None

        # State: Per-symbol loss streak
        self._symbol_consecutive_losses: dict[str, int] = {}
        self._symbol_blocked_until: dict[str, float] = {}

        # State: Protection status
        self._paused: bool = False
        self._pause_reason: str = ""
        self._pause_layer: str = ""
        self._pause_timestamp: float = 0.0
        self._rolling_pnl_at_pause: float = 0.0
        self._warning_active: bool = False
        self._warning_reason: str = ""
        self._trade_size_multiplier: float = 1.0
        self._emergency_triggered: bool = False
        self._emergency_sell_pending: bool = False
        # Hourly emergency-email reminder (re-sent until operator manually resumes)
        self._emergency_email_last_sent: float = 0.0
        self._emergency_email_resend_interval: float = 3600.0  # 1h

        # Recent trades buffer for diagnostic snapshots
        self._recent_trades: deque[dict] = deque(maxlen=50)
        self._portfolio_context: dict = {}

        # Event log
        self._events: deque[AnomalyEvent] = deque(maxlen=100)

        # Counters
        self._total_pauses: int = 0
        self._total_warnings: int = 0
        self._total_emergency_sells: int = 0
        self._total_symbol_blocks: int = 0

    # ── Properties ──────────────────────────────────────────────

    @property
    def should_block_trading(self) -> bool:
        """Global pause — checked in monitor main loop."""
        return self._enabled and self._paused

    @property
    def trade_size_multiplier(self) -> float:
        """Warning multiplier (0.5 during warning, 1.0 normal)."""
        return self._trade_size_multiplier if self._enabled else 1.0

    @property
    def should_emergency_sell(self) -> bool:
        """One-shot flag: True when emergency sell needs to happen."""
        return self._emergency_sell_pending

    # ── Public Methods ──────────────────────────────────────────

    def clear_emergency_sell(self) -> None:
        """Called by monitor after executing the emergency sell."""
        self._emergency_sell_pending = False

    def should_resend_emergency_email(self, now: float) -> bool:
        """True when the hourly reminder is due.

        Conditions: emergency state is active, bot is still paused (operator
        has not manually resumed), and at least the resend interval has
        elapsed since the last email. Manual resume clears `_emergency_triggered`
        which permanently stops the reminder until the next emergency.
        """
        if not self._enabled:
            return False
        if not self._emergency_triggered or not self._paused:
            return False
        if self._emergency_email_last_sent <= 0:
            return False  # initial email hasn't been recorded yet
        return (now - self._emergency_email_last_sent) >= self._emergency_email_resend_interval

    def mark_emergency_email_sent(self, now: float) -> None:
        """Record timestamp of an emergency email (initial or reminder)."""
        self._emergency_email_last_sent = now

    def reset_peak_on_basis_change(self, portfolio_value: float, reason: str) -> None:
        """Reset peak when the portfolio_value accounting basis changes.

        Called when hedge transitions between zero-hedge and active-hedge
        states. The accounting basis changes (`portfolio = spot only` ↔
        `portfolio = spot + hedge_pnl`), so the historical peak is no
        longer an apples-to-apples comparison with current value. Pattern
        mirrors `reset_peak_if_no_crypto`.

        Without this reset, S24 showed: peak captured at $1,040 during
        pre-hedge spot fluctuation; after hedge engaged and offset price
        moves, current settled at $1,000 → 4% phantom drawdown.
        """
        if not self._enabled or portfolio_value <= 0:
            return
        old_peak = self._peak_portfolio_value
        old_dd = self._current_drawdown_pct
        old_realized_peak = self._peak_realized_value
        old_realized_dd = self._current_realized_drawdown_pct
        self._peak_portfolio_value = portfolio_value
        self._current_drawdown_pct = 0.0
        # CRITICAL: also reset the realized-only peak. Pre-fix, only the
        # combined peak was reset on basis change. After
        # `balance.reconfigure(allocations)` (e.g. discovery completes →
        # symbols activate), `_initial_investment` is recomputed from
        # the new allocation sum. If allocations only cover a subset of
        # capital, realized capital "drops" relative to peak (which was
        # locked in pre-reconfigure with the old initial_investment),
        # producing a phantom 75% Layer A drawdown emergency in the
        # 21:03 trace. Resetting realized peak here makes the reconfigure
        # the new reference point — same logic as the combined peak.
        self._peak_realized_value = 0.0  # re-seed on next update
        self._current_realized_drawdown_pct = 0.0
        logger.info(
            f"[Anomaly] PEAK_RESET ({reason}): basis change\n"
            f"  | old_peak=${old_peak:.2f} new_peak=${portfolio_value:.2f}\n"
            f"  | old_drawdown={old_dd:.2f}% new_drawdown=0.00%\n"
            f"  | old_realized_peak=${old_realized_peak:.2f} → reset (re-seeds on next update)\n"
            f"  | old_realized_drawdown={old_realized_dd:.2f}% new_realized_drawdown=0.00%"
        )
        self._events.append(AnomalyEvent(
            timestamp=time.time(), layer="drawdown", level="resume",
            reason=f"Peak reset: {reason}",
            value=portfolio_value, threshold=old_peak,
            details={
                "old_peak": f"${old_peak:.2f}",
                "old_drawdown": f"{old_dd:.2f}%",
                "old_realized_peak": f"${old_realized_peak:.2f}",
                "old_realized_drawdown": f"{old_realized_dd:.2f}%",
            },
        ))

    def reset_peak_if_no_crypto(self, portfolio_value: float) -> None:
        """Reset peak portfolio value when portfolio is 100% USDT.

        Called after emergency sell or demotion sell liquidates all crypto.
        Breaks the drawdown deadlock: once crypto exposure is zero, the old
        peak from when crypto was held is meaningless.
        """
        if not self._enabled or portfolio_value <= 0:
            return
        old_peak = self._peak_portfolio_value
        old_dd = self._current_drawdown_pct
        self._peak_portfolio_value = portfolio_value
        self._current_drawdown_pct = 0.0
        logger.info(
            f"[Anomaly] PEAK_RESET: Portfolio is 100% USDT after crypto liquidation\n"
            f"  | old_peak=${old_peak:.2f} new_peak=${portfolio_value:.2f}\n"
            f"  | old_drawdown={old_dd:.2f}% new_drawdown=0.00%"
        )
        self._events.append(AnomalyEvent(
            timestamp=time.time(), layer="drawdown", level="resume",
            reason="Peak reset after full crypto liquidation",
            value=portfolio_value, threshold=old_peak,
            details={"old_peak": f"${old_peak:.2f}", "old_drawdown": f"{old_dd:.2f}%"},
        ))
        # If paused due to drawdown, auto-resume now
        if self._paused and self._pause_layer == "drawdown":
            self._auto_resume(
                f"Peak reset after liquidation (drawdown 0% <= resume {self._dd_resume_pct}%)",
                {"old_peak": f"${old_peak:.2f}", "new_peak": f"${portfolio_value:.2f}"},
            )

    def is_symbol_blocked(self, symbol: str) -> bool:
        """Check if a symbol is in loss streak cooldown."""
        if not self._enabled:
            return False
        blocked_until = self._symbol_blocked_until.get(symbol, 0.0)
        if blocked_until <= 0:
            return False
        now = time.time()
        if now >= blocked_until:
            # Cooldown expired — unblock
            del self._symbol_blocked_until[symbol]
            self._symbol_consecutive_losses.pop(symbol, None)
            self._events.append(AnomalyEvent(
                timestamp=now, layer="loss_streak", level="unblock",
                reason=f"Cooldown expired for {symbol}",
            ))
            logger.info(
                f"[Anomaly] SYMBOL_UNBLOCKED {symbol}: cooldown expired"
            )
            return False
        return True

    def record_trade(
        self, timestamp: float, symbol: str, profit_usd: float,
        context: dict | None = None,
    ) -> None:
        """Update all anomaly trackers after a trade."""
        if not self._enabled:
            return

        # Store in recent trades buffer
        trade_record = {
            "timestamp": timestamp,
            "symbol": symbol,
            "profit": profit_usd,
            **(context or {}),
        }
        self._recent_trades.append(trade_record)

        # Layer 1: Update rolling P&L window
        self._rolling_pnl.append((timestamp, profit_usd))
        self._rolling_pnl_sum += profit_usd
        cutoff = timestamp - self._cb_window
        while self._rolling_pnl and self._rolling_pnl[0][0] < cutoff:
            _, old_profit = self._rolling_pnl.popleft()
            self._rolling_pnl_sum -= old_profit

        # Layer 3: Update per-symbol loss streak
        if profit_usd < 0:
            self._symbol_consecutive_losses[symbol] = (
                self._symbol_consecutive_losses.get(symbol, 0) + 1
            )
        else:
            self._symbol_consecutive_losses[symbol] = 0

        # Check all triggers
        self._check_triggers(timestamp)
        self._check_symbol_streak(timestamp, symbol)

    # Cap how fast peak can grow per tick. A flash quote / stale price feed
    # could otherwise inflate peak by 30%+ in a single tick (S23 observed
    # peak=$1297 with portfolio actually at $1000), poisoning drawdown
    # tracking until a manual reset. 1%/tick at ~1 Hz still compounds real
    # rallies smoothly (3,600%/hr theoretical ceiling — never reached) but
    # filters individual flash quotes effectively. Tightened from 5% to 1%
    # in v0.29.0-beta after S24 showed a 4% drawdown from sub-cap accumulation
    # of small spikes during the pre-hedge inventory-build window.
    PEAK_MAX_GROWTH_PER_TICK_PCT: float = 1.0

    def update_portfolio_value(
        self,
        value: float,
        context: dict | None = None,
        realized_value: float | None = None,
    ) -> None:
        """Update peak portfolio and drawdown tracking.

        v0.30.1+: peak ratchets only on **realized capital** (USDT + locked-in
        P&L), not on MTM portfolio value. Drawdown is computed against the
        realized peak with `value` (which includes MTM + hedge unrealized).

        Why: S25/S26 showed peaks getting inflated by MTM noise that the
        hedge was supposed to offset but didn't (spot/futures price source
        asymmetry, multi-exchange spot-price dispersion, symbol-rotation
        windows where spot inventory is unhedged). Tying peak to realized
        capital eliminates the entire class of phantom drawdowns: peak only
        moves when USDT is actually credited from a sell, so transient MTM
        swings on held inventory can't poison it.

        Params:
            value: full portfolio value with MTM (USDT + crypto×price + hedge_pnl).
                   This is what drawdown is measured against.
            realized_value: capital that's actually locked in
                   (initial + trading_pnl - external_fees + credited_cashback).
                   If None, falls back to `value` (legacy behavior — for callers
                   that don't yet plumb the realized number through).
            context: optional dict (active symbols, capital, etc.) for diagnostics.

        Peak still has the per-tick growth cap as a defense-in-depth, but
        with realized capital as input, the cap rarely kicks in (realized
        capital can't move fast in normal trading).
        """
        if not self._enabled or value <= 0:
            return
        if context:
            self._portfolio_context = context

        # Peak source: realized capital if provided, else fall back to MTM
        peak_source = realized_value if realized_value is not None and realized_value > 0 else value

        if peak_source > self._peak_portfolio_value:
            if self._peak_portfolio_value > 0:
                cap = self._peak_portfolio_value * (
                    1.0 + self.PEAK_MAX_GROWTH_PER_TICK_PCT / 100.0
                )
                old_peak = self._peak_portfolio_value
                self._peak_portfolio_value = min(peak_source, cap)
                # Diagnostic: log when realized peak grows substantially in
                # a single tick (rare; usually means a large trade just settled)
                if self._peak_portfolio_value - old_peak > old_peak * 0.005:
                    logger.info(
                        f"[Anomaly] Peak grew (realized): "
                        f"${old_peak:.2f} → ${self._peak_portfolio_value:.2f} "
                        f"(+{(self._peak_portfolio_value - old_peak):.2f}, "
                        f"realized_in=${peak_source:.2f}, mtm_value=${value:.2f})"
                    )
            else:
                self._peak_portfolio_value = peak_source

        # v0.31.0-beta+: track realized-only peak for Layer A. No growth
        # cap — realized capital can't move fast in normal trading, so
        # capping it would actually delay legitimate peak updates after
        # a large profitable trade settles.
        if realized_value is not None and realized_value > 0:
            if realized_value > self._peak_realized_value:
                self._peak_realized_value = realized_value
            if self._peak_realized_value > 0:
                self._current_realized_drawdown_pct = (
                    (self._peak_realized_value - realized_value)
                    / self._peak_realized_value * 100
                )

        # Combined drawdown: realized peak vs current MTM (includes hedge
        # PnL via the value param). Layer B uses this metric with a sustained
        # breach gate so transient MTM noise (in-transit, flash quotes,
        # hedge basis) can't trip emergency.
        if self._peak_portfolio_value > 0:
            self._current_drawdown_pct = (
                (self._peak_portfolio_value - value)
                / self._peak_portfolio_value * 100
            )
        self._check_drawdown(time.time())
        # Also check recovery if paused
        if self._paused:
            self._check_recovery(time.time())

    def manual_resume(self) -> None:
        """Manual resume from dashboard operator."""
        if not self._paused:
            return
        now = time.time()
        duration = now - self._pause_timestamp if self._pause_timestamp else 0
        details = {
            "paused_duration": f"{duration:.0f}s",
            "rolling_pnl_now": f"${self._rolling_pnl_sum:.2f}",
            "portfolio": f"${self._portfolio_context.get('portfolio_value', 0):.2f}",
        }
        logger.info(
            f"[Anomaly] MANUAL_RESUME (was: {self._pause_layer}, {self._pause_reason})\n"
            + "\n".join(f"  | {k}={v}" for k, v in details.items())
        )
        self._events.append(AnomalyEvent(
            timestamp=now, layer="manual", level="resume",
            reason=f"Manual resume (was: {self._pause_reason})",
            details=details,
        ))
        self._paused = False
        self._pause_reason = ""
        self._pause_layer = ""
        self._warning_active = False
        self._trade_size_multiplier = 1.0
        self._emergency_triggered = False
        self._emergency_sell_pending = False
        # Stop hourly reminder cycle
        self._emergency_email_last_sent = 0.0

    # ── Trigger Checks ──────────────────────────────────────────

    def _check_triggers(self, timestamp: float) -> None:
        """Evaluate circuit breaker and warning levels."""
        if self._paused:
            self._check_recovery(timestamp)
            return

        # Layer 1: Circuit breaker
        if self._cb_threshold < 0 and self._rolling_pnl_sum < self._cb_threshold:
            trades_in_window = len(self._rolling_pnl)
            losses = sum(1 for _, p in self._rolling_pnl if p < 0)
            wins = trades_in_window - losses
            loss_rate = (losses / trades_in_window * 100) if trades_in_window > 0 else 0

            # Build top losers/winners summary
            symbol_pnl: dict[str, tuple[float, int]] = {}
            for t in self._recent_trades:
                sym = t["symbol"]
                pnl, cnt = symbol_pnl.get(sym, (0.0, 0))
                symbol_pnl[sym] = (pnl + t["profit"], cnt + 1)
            sorted_syms = sorted(symbol_pnl.items(), key=lambda x: x[1][0])
            top_losers = ", ".join(
                f"{s}=${p:.2f} ({c} trades)"
                for s, (p, c) in sorted_syms[:3] if p < 0
            )
            top_winners = ", ".join(
                f"{s}=+${p:.2f} ({c} trades)"
                for s, (p, c) in reversed(sorted_syms) if p > 0
            )

            details = {
                "rolling_window": f"{self._cb_window // 60}min",
                "trades_in_window": f"{trades_in_window}",
                "losses": f"{losses}, wins={wins}",
                "loss_rate": f"{loss_rate:.1f}% (normal ~15-20%)",
                "top_losers": top_losers or "none",
                "top_winners": top_winners or "none",
                "portfolio": f"${self._portfolio_context.get('portfolio_value', 0):.2f}",
                "peak": f"${self._peak_portfolio_value:.2f}",
                "drawdown": f"{self._current_drawdown_pct:.2f}%",
                "active_symbols": str(self._portfolio_context.get("active_symbols", "?")),
                "connected_exchanges": (
                    f"{self._portfolio_context.get('connected_exchanges', '?')}"
                    f"/{self._portfolio_context.get('total_exchanges', '?')}"
                ),
            }
            reason = (
                f"Rolling P&L ${self._rolling_pnl_sum:.2f} "
                f"< threshold ${self._cb_threshold:.2f}"
            )
            self._trigger_pause(
                timestamp, "circuit_breaker", "pause", reason,
                self._rolling_pnl_sum, self._cb_threshold, details,
            )
            return

        # Warning check: rolling P&L approaching threshold
        warning_threshold = self._cb_threshold * self._warning_pnl_pct
        if self._cb_threshold < 0 and self._rolling_pnl_sum < warning_threshold:
            if not self._warning_active:
                self._warning_active = True
                self._warning_reason = reason
                self._trade_size_multiplier = 0.5
                self._total_warnings += 1
                pct_of_threshold = (
                    (self._rolling_pnl_sum / self._cb_threshold * 100)
                    if self._cb_threshold != 0 else 0
                )
                details = {
                    "trade_size_mult": "reduced to 0.5",
                }
                reason = (
                    f"Rolling P&L ${self._rolling_pnl_sum:.2f} "
                    f"approaching threshold ${self._cb_threshold:.2f} "
                    f"({pct_of_threshold:.0f}%)"
                )
                logger.warning(
                    f"[Anomaly] WARNING_ACTIVE: {reason}\n"
                    + "\n".join(f"  | {k}={v}" for k, v in details.items())
                )
                self._events.append(AnomalyEvent(
                    timestamp=timestamp, layer="warning", level="warning",
                    reason=reason, value=self._rolling_pnl_sum,
                    threshold=warning_threshold, details=details,
                ))
        elif self._warning_active:
            # Warning cleared
            self._warning_active = False
            self._warning_reason = ""
            self._trade_size_multiplier = 1.0
            pct_of_threshold = (
                (self._rolling_pnl_sum / self._cb_threshold * 100)
                if self._cb_threshold != 0 else 0
            )
            logger.info(
                f"[Anomaly] WARNING_CLEAR: Rolling P&L recovered to "
                f"${self._rolling_pnl_sum:.2f} ({pct_of_threshold:.0f}% of threshold)\n"
                f"  | trade_size_mult=restored to 1.0"
            )
            self._events.append(AnomalyEvent(
                timestamp=timestamp, layer="warning", level="resume",
                reason="Warning cleared — P&L recovered",
            ))

    def _fire_emergency(
        self,
        timestamp: float,
        layer_label: str,
        drawdown_pct: float,
        threshold_pct: float,
        ctx: dict,
        reason_extra: str,
    ) -> None:
        """Trigger emergency pause + alert. Auto-liquidate is opt-in only.

        v0.31.0-beta+: default action is HALT + ALERT, not sell-all. The
        operator gets paged via email and can use the existing Hard Stop
        button after investigating. Set `emergency_auto_liquidate=True` to
        restore the pre-v0.31 behavior.
        """
        realized = ctx.get("realized_value", 0.0)
        portfolio = ctx.get("portfolio_value", 0.0)
        details = {
            "layer": layer_label,
            "portfolio_mtm": f"${portfolio:.2f}",
            "realized_capital": f"${realized:.2f}",
            "realized_peak": f"${self._peak_realized_value:.2f}",
            "realized_drawdown": f"{self._current_realized_drawdown_pct:.2f}%",
            "combined_peak": f"${self._peak_portfolio_value:.2f}",
            "combined_drawdown": f"{self._current_drawdown_pct:.2f}%",
            "usdt_total": f"${ctx.get('usdt_total', 0):.2f}",
            "crypto_total": f"${ctx.get('crypto_total', 0):.2f}",
            "action": (
                "SELLING ALL CRYPTO POSITIONS"
                if self._emergency_auto_liquidate
                else "HALT + ALERT (no auto-sell — operator decides)"
            ),
        }
        reason = (
            f"EMERGENCY ({layer_label}): drawdown {drawdown_pct:.2f}% "
            f">= threshold {threshold_pct:.1f}% — {reason_extra}"
        )
        self._trigger_pause(
            timestamp, "drawdown", "emergency", reason,
            drawdown_pct, threshold_pct, details,
        )
        self._emergency_triggered = True
        if self._emergency_auto_liquidate:
            self._emergency_sell_pending = True
            self._total_emergency_sells += 1

    def _check_drawdown(self, timestamp: float) -> None:
        """Evaluate drawdown protection — two-layer emergency gate.

        Layer A (realized): fires immediately when realized-capital drawdown
        crosses `realized_drawdown_emergency_pct`. Realized capital can only
        move on locked-in events (closed trades, fees, cashback) so this
        gate has no MTM-noise exposure.

        Layer B (combined+sustained): fires when the combined spot+hedge
        unrealized drawdown crosses `combined_drawdown_emergency_pct` AND
        the breach persists past `combined_drawdown_sustained_seconds`. The
        combined metric is what matters for hedge health — if the hedge
        offsets spot moves correctly, this gate never fires regardless of
        spot price action. The sustained-breach requirement filters
        transient phantoms (in-transit, flash quotes, hedge basis change).

        Action: halt + alert by default. Sell-all is only triggered when
        `emergency_auto_liquidate=True` (off by default — operator should
        decide via the Hard Stop button after investigating).

        Below the emergency thresholds, the legacy MTM per-symbol blocking
        path stays as a soft throttle (kicks in at `drawdown_threshold_pct`).
        """
        if self._paused or self._peak_portfolio_value <= 0:
            return

        ctx = self._portfolio_context

        # Layer A — realized capital drawdown (primary trigger)
        if (
            self._peak_realized_value > 0
            and self._current_realized_drawdown_pct >= self._realized_dd_emergency_pct
        ):
            self._fire_emergency(
                timestamp, layer_label="layer_a_realized",
                drawdown_pct=self._current_realized_drawdown_pct,
                threshold_pct=self._realized_dd_emergency_pct,
                ctx=ctx,
                reason_extra="realized capital drop — actual locked-in loss",
            )
            return

        # Layer B — combined unrealized drawdown, sustained breach
        if self._current_drawdown_pct >= self._combined_dd_emergency_pct:
            if self._combined_breach_start is None:
                self._combined_breach_start = timestamp
                logger.info(
                    f"[Anomaly] Combined drawdown breach started: "
                    f"{self._current_drawdown_pct:.2f}% "
                    f">= {self._combined_dd_emergency_pct:.1f}% "
                    f"(must persist {self._combined_dd_sustained_s:.0f}s to fire emergency)"
                )
            else:
                breach_duration = timestamp - self._combined_breach_start
                if breach_duration >= self._combined_dd_sustained_s:
                    self._fire_emergency(
                        timestamp, layer_label="layer_b_combined",
                        drawdown_pct=self._current_drawdown_pct,
                        threshold_pct=self._combined_dd_emergency_pct,
                        ctx=ctx,
                        reason_extra=(
                            f"combined spot+hedge unrealized drop sustained "
                            f"{breach_duration:.0f}s — hedge not offsetting spot moves"
                        ),
                    )
                    self._combined_breach_start = None
                    return
        else:
            # Reverted below threshold — clear the breach timer
            if self._combined_breach_start is not None:
                duration = timestamp - self._combined_breach_start
                logger.info(
                    f"[Anomaly] Combined drawdown breach cleared after {duration:.0f}s "
                    f"(now {self._current_drawdown_pct:.2f}% < {self._combined_dd_emergency_pct:.1f}%)"
                )
                self._combined_breach_start = None

        # Soft per-symbol blocking — legacy path, unchanged
        if self._current_drawdown_pct >= self._dd_threshold_pct:
            drop = self._peak_portfolio_value * self._current_drawdown_pct / 100
            # Per-symbol blocking instead of global pause:
            # Block symbols with crypto exposure (they cause the drawdown)
            crypto_symbols = ctx.get("crypto_symbols", [])
            if crypto_symbols:
                blocked_count = 0
                for sym in crypto_symbols:
                    if sym not in self._symbol_blocked_until:
                        self._symbol_blocked_until[sym] = (
                            timestamp + self._sls_cooldown
                        )
                        self._total_symbol_blocks += 1
                        blocked_count += 1
                # v0.30.1+: include realized vs MTM breakdown so phantom
                # drawdowns are diagnosable. mtm_offset = portfolio - realized.
                # If mtm_offset is large negative, the MTM has dropped well
                # below realized capital — indicates either real loss OR
                # spot/hedge price-source asymmetry creating phantom drop.
                realized = ctx.get("realized_value", 0.0)
                mtm_offset = ctx.get("mtm_offset", 0.0)
                details = {
                    "portfolio_mtm": f"${ctx.get('portfolio_value', 0):.2f}",
                    "realized_capital": f"${realized:.2f}",
                    "mtm_offset": f"${mtm_offset:+.2f} (mtm vs realized)",
                    "peak": f"${self._peak_portfolio_value:.2f}",
                    "drop": f"${drop:.2f}",
                    "blocked_symbols": ", ".join(crypto_symbols),
                    "rolling_pnl": f"${self._rolling_pnl_sum:.2f} ({self._cb_window // 60}min)",
                    "active_symbols": str(ctx.get("active_symbols", "?")),
                }
                reason = (
                    f"Drawdown {self._current_drawdown_pct:.2f}% "
                    f">= threshold {self._dd_threshold_pct:.1f}% — "
                    f"blocked {len(crypto_symbols)} symbol(s) instead of global pause"
                )
                logger.warning(
                    f"[Anomaly] DRAWDOWN_BLOCK: {reason}\n"
                    + "\n".join(f"  | {k}={v}" for k, v in details.items())
                )
                self._events.append(AnomalyEvent(
                    timestamp=timestamp, layer="drawdown", level="block",
                    reason=reason, value=self._current_drawdown_pct,
                    threshold=self._dd_threshold_pct, details=details,
                ))
            else:
                # No crypto symbols info — fall back to global pause
                details = {
                    "portfolio": f"${ctx.get('portfolio_value', 0):.2f}",
                    "peak": f"${self._peak_portfolio_value:.2f}",
                    "drop": f"${drop:.2f}",
                    "rolling_pnl": f"${self._rolling_pnl_sum:.2f} ({self._cb_window // 60}min)",
                    "active_symbols": str(ctx.get("active_symbols", "?")),
                }
                reason = (
                    f"Drawdown {self._current_drawdown_pct:.2f}% "
                    f">= threshold {self._dd_threshold_pct:.1f}%"
                )
                self._trigger_pause(
                    timestamp, "drawdown", "pause", reason,
                    self._current_drawdown_pct, self._dd_threshold_pct, details,
                )

    def _check_symbol_streak(self, timestamp: float, symbol: str) -> None:
        """Check if a symbol should be blocked due to loss streak."""
        if symbol in self._symbol_blocked_until:
            return  # Already blocked

        losses = self._symbol_consecutive_losses.get(symbol, 0)
        if losses < self._sls_threshold:
            return

        # Block this symbol
        blocked_until = timestamp + self._sls_cooldown
        self._symbol_blocked_until[symbol] = blocked_until
        self._total_symbol_blocks += 1

        # Build diagnostic details
        symbol_trades = [
            t for t in self._recent_trades if t["symbol"] == symbol
        ]
        recent_str = ", ".join(
            f"${t['profit']:+.2f} ({t.get('buy_ex', '?')}→{t.get('sell_ex', '?')})"
            for t in symbol_trades[-losses:]
        )
        total_loss = sum(
            t["profit"] for t in symbol_trades[-losses:]
        )
        avg_loss = total_loss / losses if losses > 0 else 0

        # Count other blocked symbols
        now = time.time()
        other_blocked = sum(
            1 for s, t in self._symbol_blocked_until.items()
            if s != symbol and t > now
        )

        details = {
            "recent_trades": recent_str,
            "total_loss": f"${total_loss:.2f}",
            "avg_loss": f"${avg_loss:.3f}",
            "other_symbols_blocked": str(other_blocked),
        }
        reason = (
            f"{losses} consecutive losses on {symbol}, "
            f"blocked for {self._sls_cooldown}s"
        )
        logger.warning(
            f"[Anomaly] SYMBOL_BLOCKED {symbol}: {reason}\n"
            + "\n".join(f"  | {k}={v}" for k, v in details.items())
        )
        self._events.append(AnomalyEvent(
            timestamp=timestamp, layer="loss_streak", level="block",
            reason=reason, value=float(losses),
            threshold=float(self._sls_threshold), details=details,
        ))

    def _check_recovery(self, timestamp: float) -> None:
        """Check if paused state can be automatically recovered."""
        elapsed = timestamp - self._pause_timestamp

        if self._pause_layer == "circuit_breaker":
            resume_threshold = self._cb_threshold * self._cb_resume_pct
            if elapsed >= self._cb_cooldown and self._rolling_pnl_sum > resume_threshold:
                duration = timestamp - self._pause_timestamp
                details = {
                    "paused_duration": f"{duration:.0f}s",
                    "rolling_pnl_at_pause": f"${self._rolling_pnl_at_pause:.2f}",
                    "rolling_pnl_now": f"${self._rolling_pnl_sum:.2f}",
                }
                self._auto_resume(
                    f"Rolling P&L recovered to ${self._rolling_pnl_sum:.2f} "
                    f"(threshold ${resume_threshold:.2f})",
                    details,
                )

        elif self._pause_layer == "drawdown":
            if self._emergency_triggered:
                return  # Emergency requires manual resume
            if self._current_drawdown_pct <= self._dd_resume_pct:
                duration = timestamp - self._pause_timestamp
                details = {
                    "paused_duration": f"{duration:.0f}s",
                    "drawdown_now": f"{self._current_drawdown_pct:.2f}%",
                }
                self._auto_resume(
                    f"Drawdown recovered to {self._current_drawdown_pct:.2f}% "
                    f"(resume at {self._dd_resume_pct:.1f}%)",
                    details,
                )

    # ── Internal Helpers ────────────────────────────────────────

    def _trigger_pause(
        self, timestamp: float, layer: str, level: str,
        reason: str, value: float, threshold: float,
        details: dict,
    ) -> None:
        """Activate global pause with full diagnostic logging."""
        self._paused = True
        self._pause_reason = reason
        self._pause_layer = layer
        self._pause_timestamp = timestamp
        self._rolling_pnl_at_pause = self._rolling_pnl_sum
        self._total_pauses += 1

        # Clear warning state (we've escalated to pause)
        self._warning_active = False
        self._trade_size_multiplier = 1.0

        log_level = "EMERGENCY" if level == "emergency" else f"PAUSED ({layer})"
        logger.warning(
            f"[Anomaly] {log_level}: {reason}\n"
            + "\n".join(f"  | {k}={v}" for k, v in details.items())
        )
        self._events.append(AnomalyEvent(
            timestamp=timestamp, layer=layer, level=level,
            reason=reason, value=value, threshold=threshold,
            details=details,
        ))

    def _auto_resume(self, reason: str, details: dict) -> None:
        """Auto-resume with logging."""
        logger.info(
            f"[Anomaly] AUTO_RESUME ({self._pause_layer}): {reason}\n"
            + "\n".join(f"  | {k}={v}" for k, v in details.items())
        )
        self._events.append(AnomalyEvent(
            timestamp=time.time(), layer=self._pause_layer, level="resume",
            reason=f"Auto-resume: {reason}", details=details,
        ))
        self._paused = False
        self._pause_reason = ""
        self._pause_layer = ""
        self._warning_active = False
        self._trade_size_multiplier = 1.0

    # ── State Persistence ───────────────────────────────────────

    def to_state_dict(self) -> dict:
        """Serialize state for persistence."""
        return {
            "_paused": self._paused,
            "_pause_reason": self._pause_reason,
            "_pause_layer": self._pause_layer,
            "_pause_timestamp": self._pause_timestamp,
            "_rolling_pnl_at_pause": self._rolling_pnl_at_pause,
            "_peak_portfolio_value": self._peak_portfolio_value,
            "_symbol_consecutive_losses": dict(self._symbol_consecutive_losses),
            "_symbol_blocked_until": dict(self._symbol_blocked_until),
            "_total_pauses": self._total_pauses,
            "_total_warnings": self._total_warnings,
            "_total_emergency_sells": self._total_emergency_sells,
            "_total_symbol_blocks": self._total_symbol_blocks,
            "_emergency_triggered": self._emergency_triggered,
            "_emergency_email_last_sent": self._emergency_email_last_sent,
            "_warning_active": self._warning_active,
            "_trade_size_multiplier": self._trade_size_multiplier,
            # Snapshot the configured capital at save time so the next load
            # can detect operator-changed capital and reset stale peak.
            "_total_capital_at_save": self._portfolio_context.get("total_capital", 0.0),
            "_rolling_pnl": list(self._rolling_pnl),
            "_events": [
                {
                    "timestamp": e.timestamp, "layer": e.layer,
                    "level": e.level, "reason": e.reason,
                    "value": e.value, "threshold": e.threshold,
                    "details": e.details,
                }
                for e in self._events
            ],
        }

    def from_state_dict(self, data: dict, current_total_capital: float = 0.0) -> None:
        """Restore state from saved dict.

        If `current_total_capital` is provided AND the saved
        `_total_capital_at_save` differs (operator changed capital between
        sessions, or restoring from an old state file), the peak is reset.
        Otherwise the saved peak's drawdown comparisons are meaningless
        (e.g. a $1,800 peak from old capital vs $1,000 current → 44%
        permanent phantom drawdown).
        """
        self._paused = data.get("_paused", False)
        self._pause_reason = data.get("_pause_reason", "")
        self._pause_layer = data.get("_pause_layer", "")
        self._pause_timestamp = data.get("_pause_timestamp", 0.0)
        self._rolling_pnl_at_pause = data.get("_rolling_pnl_at_pause", 0.0)
        saved_peak = data.get("_peak_portfolio_value", 0.0)
        saved_capital = data.get("_total_capital_at_save", 0.0)
        if (
            current_total_capital > 0
            and saved_capital > 0
            and abs(saved_capital - current_total_capital) > 0.5  # > $0.50 differ
        ):
            logger.warning(
                f"[Anomaly] Capital changed across restart: "
                f"${saved_capital:.0f} → ${current_total_capital:.0f}. "
                f"Resetting peak (was ${saved_peak:.2f}) to avoid stale-peak "
                f"phantom drawdown."
            )
            self._peak_portfolio_value = 0.0  # will be set on first update_portfolio_value
        else:
            self._peak_portfolio_value = saved_peak
        self._symbol_consecutive_losses = data.get("_symbol_consecutive_losses", {})
        self._symbol_blocked_until = data.get("_symbol_blocked_until", {})
        self._total_pauses = data.get("_total_pauses", 0)
        self._total_warnings = data.get("_total_warnings", 0)
        self._total_emergency_sells = data.get("_total_emergency_sells", 0)
        self._total_symbol_blocks = data.get("_total_symbol_blocks", 0)
        self._emergency_triggered = data.get("_emergency_triggered", False)
        self._emergency_email_last_sent = data.get("_emergency_email_last_sent", 0.0)
        self._warning_active = data.get("_warning_active", False)
        self._trade_size_multiplier = data.get("_trade_size_multiplier", 1.0)

        # Restore rolling P&L deque, prune stale entries
        now = time.time()
        cutoff = now - self._cb_window
        self._rolling_pnl = deque(
            (ts, pnl) for ts, pnl in data.get("_rolling_pnl", [])
            if ts >= cutoff
        )
        self._rolling_pnl_sum = sum(p for _, p in self._rolling_pnl)

        # Restore events
        self._events = deque(
            (
                AnomalyEvent(
                    timestamp=e["timestamp"], layer=e["layer"],
                    level=e["level"], reason=e["reason"],
                    value=e.get("value", 0.0), threshold=e.get("threshold", 0.0),
                    details=e.get("details", {}),
                )
                for e in data.get("_events", [])
            ),
            maxlen=100,
        )

    # ── Dashboard Broadcast ─────────────────────────────────────

    def to_broadcast_dict(self) -> dict:
        """Build state dict for dashboard broadcast."""
        now = time.time()
        # Current blocked symbols
        blocked_symbols = {
            sym: until
            for sym, until in self._symbol_blocked_until.items()
            if until > now
        }
        return {
            "anomaly_protection": {
                "enabled": self._enabled,
                "paused": self._paused,
                "pause_reason": self._pause_reason,
                "pause_layer": self._pause_layer,
                "pause_timestamp": self._pause_timestamp,
                "warning_active": self._warning_active,
                "warning_reason": self._warning_reason,
                "trade_size_multiplier": self._trade_size_multiplier,
                "emergency_triggered": self._emergency_triggered,
                # Metrics
                "rolling_pnl": round(self._rolling_pnl_sum, 4),
                "rolling_pnl_window": self._cb_window,
                "trades_in_window": len(self._rolling_pnl),
                "loss_rate": round(
                    sum(1 for _, p in self._rolling_pnl if p < 0)
                    / max(len(self._rolling_pnl), 1) * 100, 1
                ),
                "peak_portfolio": round(self._peak_portfolio_value, 2),
                "current_drawdown_pct": round(self._current_drawdown_pct, 2),
                # Per-symbol
                "symbol_blocks": {
                    sym: round(until - now, 0)
                    for sym, until in blocked_symbols.items()
                },
                "symbol_losses": dict(self._symbol_consecutive_losses),
                # Counters
                "total_pauses": self._total_pauses,
                "total_warnings": self._total_warnings,
                "total_emergency_sells": self._total_emergency_sells,
                "total_symbol_blocks": self._total_symbol_blocks,
                # Thresholds (for display)
                "circuit_breaker_threshold": self._cb_threshold,
                "drawdown_threshold_pct": self._dd_threshold_pct,
                "symbol_loss_streak_threshold": self._sls_threshold,
                # Recent events (last 20)
                "events": [
                    {
                        "timestamp": e.timestamp, "layer": e.layer,
                        "level": e.level, "reason": e.reason,
                    }
                    for e in list(self._events)[-20:]
                ],
            },
        }
