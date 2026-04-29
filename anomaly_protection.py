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
        # Layer 2: Drawdown protection
        drawdown_threshold_pct: float = 5.0,
        drawdown_resume_pct: float = 3.0,
        drawdown_emergency_mult: float = 2.0,
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
        self._sls_threshold = symbol_loss_streak_threshold
        self._sls_cooldown = symbol_loss_streak_cooldown
        self._warning_pnl_pct = warning_pnl_pct

        # State: Circuit breaker
        self._rolling_pnl: deque[tuple[float, float]] = deque()
        self._rolling_pnl_sum: float = 0.0

        # State: Drawdown
        self._peak_portfolio_value: float = 0.0
        self._current_drawdown_pct: float = 0.0

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
    # tracking until a manual reset. Conservative 5%/tick allows real bull
    # rallies to compound peak smoothly while filtering single-tick spikes.
    PEAK_MAX_GROWTH_PER_TICK_PCT: float = 5.0

    def update_portfolio_value(
        self, value: float, context: dict | None = None,
    ) -> None:
        """Update peak portfolio and drawdown tracking.

        Peak growth is capped at PEAK_MAX_GROWTH_PER_TICK_PCT per call. Real
        sustained gains still compound (5% per ~1Hz update = 18,000% per
        hour theoretical ceiling — never reached in practice). Single-tick
        flash quotes can no longer corrupt peak.
        """
        if not self._enabled or value <= 0:
            return
        if context:
            self._portfolio_context = context
        if value > self._peak_portfolio_value:
            if self._peak_portfolio_value > 0:
                cap = self._peak_portfolio_value * (
                    1.0 + self.PEAK_MAX_GROWTH_PER_TICK_PCT / 100.0
                )
                self._peak_portfolio_value = min(value, cap)
            else:
                self._peak_portfolio_value = value
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

    def _check_drawdown(self, timestamp: float) -> None:
        """Evaluate drawdown protection and emergency sell."""
        if self._paused or self._peak_portfolio_value <= 0:
            return

        emergency_threshold = self._dd_threshold_pct * self._dd_emergency_mult
        ctx = self._portfolio_context

        if self._current_drawdown_pct >= emergency_threshold:
            drop = self._peak_portfolio_value * self._current_drawdown_pct / 100
            details = {
                "portfolio": f"${ctx.get('portfolio_value', 0):.2f}",
                "peak": f"${self._peak_portfolio_value:.2f}",
                "drop": f"${drop:.2f}",
                "usdt_total": f"${ctx.get('usdt_total', 0):.2f}",
                "crypto_total": f"${ctx.get('crypto_total', 0):.2f}",
                "action": "SELLING ALL CRYPTO POSITIONS",
            }
            reason = (
                f"Drawdown {self._current_drawdown_pct:.2f}% "
                f">= emergency threshold {emergency_threshold:.1f}%"
            )
            self._trigger_pause(
                timestamp, "drawdown", "emergency", reason,
                self._current_drawdown_pct, emergency_threshold, details,
            )
            self._emergency_triggered = True
            self._emergency_sell_pending = True
            self._total_emergency_sells += 1

        elif self._current_drawdown_pct >= self._dd_threshold_pct:
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
                details = {
                    "portfolio": f"${ctx.get('portfolio_value', 0):.2f}",
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

    def from_state_dict(self, data: dict) -> None:
        """Restore state from saved dict."""
        self._paused = data.get("_paused", False)
        self._pause_reason = data.get("_pause_reason", "")
        self._pause_layer = data.get("_pause_layer", "")
        self._pause_timestamp = data.get("_pause_timestamp", 0.0)
        self._rolling_pnl_at_pause = data.get("_rolling_pnl_at_pause", 0.0)
        self._peak_portfolio_value = data.get("_peak_portfolio_value", 0.0)
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
