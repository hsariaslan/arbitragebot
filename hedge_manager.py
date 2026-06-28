"""
Hedge state + sizing logic (Phase C — shadow mode).

The HedgeManager computes "what hedge SHOULD I have" for each active symbol
and tracks the shadow position state. In Phase C it does NOT place real
orders — it logs decisions and accumulates would-be funding costs against
live funding rates. This lets us validate the sizing math against real bot
inventory before committing real money in Phase D.

Design:
  - For each active symbol available on Binance Futures:
      target_hedge_qty = sum(balance.crypto[ex][symbol]) across all exchanges
      target_hedge_usd = target_hedge_qty × current_price
  - If target_hedge_usd >= dust_threshold AND funding rate is OK:
      → "WOULD_OPEN" or "WOULD_ADJUST" depending on existing shadow state
  - If target drops below dust threshold:
      → "WOULD_CLOSE"
  - If funding rate falls below skip threshold:
      → "WOULD_SKIP" + close any open shadow position
  - Symbols not on Binance Futures: silently skipped

Shadow state is persisted via to_state_dict/from_state_dict so we can
observe accumulated funding costs across restarts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from funding_monitor import FUTURES_SYMBOL_OVERRIDE, get_futures_symbol

if TYPE_CHECKING:
    from balance import BalanceTracker
    from executors.binance_futures_exec import BinanceFuturesExecutor
    from funding_monitor import FundingMonitor
    from optimizer import SymbolOptimizer

logger = logging.getLogger(__name__)


def _log_task_exception(name: str):
    """Build a done-callback that logs exceptions from fire-and-forget tasks.

    Used at sites that can't return a Task to a caller (e.g. sync→async
    bridges via loop.create_task). Without this wrapper Python emits a
    bare 'Task exception was never retrieved' warning at GC time with
    no context — observed in S21 during OKX reconnect / Pionex cycling.
    """
    def _cb(task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(f"[Hedge] task '{name}' failed: {exc!r}", exc_info=exc)
    return _cb


def _futures_to_spot(futures_symbol: str) -> str | None:
    """Reverse-lookup spot symbol for a 1000X futures contract.

    Non-1000X contracts pass through unchanged. For 1000PEPEUSDT etc.,
    returns the spot equivalent (PEPEUSDT).
    """
    for spot, (f_sym, _) in FUTURES_SYMBOL_OVERRIDE.items():
        if f_sym == futures_symbol:
            return spot
    return futures_symbol


@dataclass
class ShadowHedge:
    """Per-symbol shadow hedge state.

    `qty` is the spot-side quantity we would hedge (positive = we'd be short
    that many units on futures; the futures contract qty may differ for
    1000X symbols and is computed at execution time).
    """
    spot_symbol: str
    qty: float = 0.0                              # Current shadow position size (units of base asset)
    entry_price: float = 0.0                      # Mark price at hedge open
    opened_at: float = 0.0                        # Unix ts of open
    last_adjusted_at: float = 0.0                 # Unix ts of last size adjustment
    accumulated_funding_usd: float = 0.0          # Cumulative would-be funding paid/received (negative = paid)
    funding_periods_observed: int = 0             # Count of settlements that landed while open
    last_funding_check_ts: float = 0.0            # For estimating partial-period accruals
    open_count: int = 0                           # How many times we've opened (Phase C: lifetime stats)
    close_count: int = 0
    adjust_count: int = 0


class HedgeManager:
    """Computes target hedge per symbol and tracks shadow positions.

    Phase C: shadow mode only. Phase D will wire the executor.
    """

    def __init__(
        self,
        balance: "BalanceTracker",
        funding_monitor: "FundingMonitor",
        optimizer: "SymbolOptimizer | None" = None,
        executor: "BinanceFuturesExecutor | None" = None,
        # Hot-applied settings
        enabled: bool = True,
        execution_mode: str = "simulation",       # simulation | testnet | live
        dust_threshold_usd: float = 20.0,
        evaluation_interval_seconds: float = 60.0,
        margin_buffer_pct: float = 0.20,
        adjust_threshold_pct: float = 0.01,       # only adjust if drift > 1% of current size
        leverage: int = 1,                        # set on each symbol before first open
    ) -> None:
        self._balance = balance
        self._funding_monitor = funding_monitor
        self._optimizer = optimizer
        self._executor = executor
        self._enabled = bool(enabled)
        self._execution_mode = execution_mode
        self._dust_threshold_usd = float(dust_threshold_usd)
        self._evaluation_interval = float(evaluation_interval_seconds)
        self._margin_buffer_pct = float(margin_buffer_pct)
        self._adjust_threshold_pct = float(adjust_threshold_pct)
        self._leverage = int(leverage)

        # Per-symbol shadow state
        self._shadows: dict[str, ShadowHedge] = {}

        # Per-symbol asyncio.Lock to serialize concurrent operations.
        # Created lazily — only when a symbol is first touched.
        self._symbol_locks: dict[str, asyncio.Lock] = {}

        # Last evaluation timestamp
        self._last_evaluation_ts: float = 0.0

        # Reconciliation has run at least once after startup
        self._reconciled: bool = False

        # Cumulative would-be statistics (lifetime, persisted)
        self._cumulative_funding_usd: float = 0.0
        self._total_opens: int = 0
        self._total_closes: int = 0
        self._total_adjusts: int = 0
        self._total_executor_errors: int = 0

        # One-line startup log so [Hedge] appears in Bot Logs immediately,
        # before the first eval cycle (which only fires after symbols activate).
        logger.info(
            f"[Hedge] HedgeManager initialized: enabled={self._enabled} "
            f"mode={self._execution_mode} dust=${self._dust_threshold_usd:.0f} "
            f"eval_interval={self._evaluation_interval:.0f}s "
            f"margin_buffer={self._margin_buffer_pct*100:.0f}% "
            f"leverage={self._leverage}x"
        )

    # ── Public lifecycle hooks ────────────────────────────────────────

    def set_optimizer(self, optimizer: "SymbolOptimizer") -> None:
        self._optimizer = optimizer

    def set_executor(self, executor: "BinanceFuturesExecutor") -> None:
        """Wire the Binance Futures executor (Phase D)."""
        self._executor = executor

    def _is_real_mode(self) -> bool:
        return self._execution_mode in ("testnet", "live") and self._executor is not None

    # ── Phase E: anomaly / emergency / demotion integration ────────────

    # When True, evaluate() will not OPEN new hedges (existing hedges keep
    # tracking inventory and can still close on demotion/inventory-drop).
    # Set by monitor when anomaly trading-pause is active or operator stop.
    _safety_paused: bool = False

    def on_safety_pause(self, reason: str = "") -> None:
        """Called when trading is paused by anomaly protection or operator.

        Existing hedges keep working (so demotions still close them); only
        new opens are blocked.
        """
        if not self._safety_paused:
            self._safety_paused = True
            logger.info(f"[Hedge] SAFETY_PAUSE engaged ({reason}) — no new opens, existing hedges continue")

    def on_safety_resume(self) -> None:
        """Called when trading resumes. Triggers immediate reconcile to make
        sure shadow state matches reality after the pause window.
        """
        if self._safety_paused:
            self._safety_paused = False
            logger.info("[Hedge] SAFETY_RESUME — reconciling and resuming opens")
            # Force a reconcile next eval cycle in real mode
            self._reconciled = False
            # Force evaluate to run on next tick (drop the throttle)
            self._last_evaluation_ts = 0.0

    def request_close(self, spot_symbol: str, reason: str) -> None:
        """Synchronously schedule an async close for a single symbol.

        Called from sync paths (e.g. optimizer._execute_demotion). Fires a
        fire-and-forget asyncio task using the running event loop.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(f"[Hedge] request_close({spot_symbol}, {reason}) — no event loop")
            return
        task = loop.create_task(self._close_for_request(spot_symbol, reason))
        task.add_done_callback(_log_task_exception(f"hedge_request_close_{spot_symbol}"))

    async def _close_for_request(self, spot_symbol: str, reason: str) -> None:
        async with self._lock_for(spot_symbol):
            now = time.time()
            price = self._lookup_price(spot_symbol)
            await self._close(spot_symbol, price, now, reason)

    async def close_all_for_emergency(self, reason: str = "emergency") -> dict:
        """Close every open hedge as fast as possible.

        Used by monitor._emergency_sell_all() — in shadow mode this just
        clears shadow state with WOULD_CLOSE logs; in real mode it closes
        every futures position. Returns a summary suitable for emails:

            {
                "closed": [{"symbol": "BTC", "qty": 0.001, "funding_pnl_usd": 0.12, "held_h": 5.4}, ...],
                "failed": [{"symbol": "...", "error": "..."}],
                "total_funding_pnl_usd": 1.34,
                "n_closed": 3,
                "n_failed": 0,
            }
        """
        closed: list[dict] = []
        failed: list[dict] = []
        now = time.time()
        for sym in list(self._shadows.keys()):
            sh = self._shadows[sym]
            if sh.qty <= 0:
                continue
            old_qty = sh.qty
            old_funding = sh.accumulated_funding_usd
            held_h = (now - sh.opened_at) / 3600 if sh.opened_at > 0 else 0.0
            async with self._lock_for(sym):
                ok = await self._close(sym, self._lookup_price(sym), now, reason)
            if ok:
                closed.append({
                    "symbol": sym,
                    "qty": old_qty,
                    "funding_pnl_usd": old_funding,
                    "held_h": held_h,
                })
            else:
                failed.append({"symbol": sym, "error": "close_failed"})
        total_funding = sum(c["funding_pnl_usd"] for c in closed)
        if closed or failed:
            logger.warning(
                f"[Hedge] CLOSE_ALL_FOR_EMERGENCY reason={reason}: "
                f"closed={len(closed)} failed={len(failed)} "
                f"funding_pnl=${total_funding:+.4f}"
            )
        return {
            "closed": closed,
            "failed": failed,
            "total_funding_pnl_usd": total_funding,
            "n_closed": len(closed),
            "n_failed": len(failed),
        }

    async def close_all_real_positions(self, reason: str = "restart") -> dict:
        """Close every real futures position, including orphans not in shadow.

        Used by Restart Bot to wipe the slate clean — orphan positions
        carried over from previous sessions can produce phantom drawdowns
        (S30: PENDLE -273 contracts inherited at $1.3357 entry produced a
        $215 unrealized loss when Fix B switched to futures markPrice
        post-restart).

        Differs from `close_all_for_emergency`:
        - Queries the executor for ALL real positions (not just shadow)
        - Closes orphans that have no shadow entry
        - Wipes shadow state regardless of close success

        Safe in shadow/simulation mode — just clears shadow state.
        """
        closed: list[dict] = []
        failed: list[dict] = []
        if self._execution_mode in ("simulation",) or self._executor is None:
            # No real positions to close; just wipe shadow
            n_shadows = len(self._shadows)
            self._shadows.clear()
            logger.info(
                f"[Hedge] CLOSE_ALL_REAL_POSITIONS reason={reason}: "
                f"shadow_only mode — cleared {n_shadows} shadow entries"
            )
            return {"closed": [], "failed": [], "n_closed": 0, "n_failed": 0,
                    "shadow_cleared": n_shadows}
        try:
            real_positions = await self._executor.get_all_positions()
        except Exception as e:
            logger.error(f"[Hedge] CLOSE_ALL_REAL_POSITIONS get_all_positions failed: {e}")
            real_positions = []
        symbols_to_close: set[str] = set()
        for pos in real_positions or []:
            futures_sym = pos.get("symbol")
            if not futures_sym:
                continue
            try:
                size = float(pos.get("positionAmt", 0.0) or 0.0)
            except (TypeError, ValueError):
                size = 0.0
            if abs(size) > 0:
                symbols_to_close.add(futures_sym)
        # Also close any shadow-tracked symbols whose futures may have desynced
        for spot_sym in list(self._shadows.keys()):
            futures_sym, _ = get_futures_symbol(spot_sym)
            symbols_to_close.add(futures_sym)
        for futures_sym in symbols_to_close:
            try:
                ok = await self._executor.close_position(futures_sym)
                if ok:
                    closed.append({"symbol": futures_sym})
                    logger.info(f"[Hedge] CLOSE_ALL_REAL_POSITIONS: closed {futures_sym}")
                else:
                    failed.append({"symbol": futures_sym, "error": "close returned False"})
                    logger.warning(f"[Hedge] CLOSE_ALL_REAL_POSITIONS: {futures_sym} returned False")
            except Exception as e:
                failed.append({"symbol": futures_sym, "error": str(e)})
                logger.error(f"[Hedge] CLOSE_ALL_REAL_POSITIONS {futures_sym} failed: {e}")
        # Wipe shadow state regardless
        self._shadows.clear()
        logger.info(
            f"[Hedge] CLOSE_ALL_REAL_POSITIONS reason={reason}: "
            f"closed={len(closed)} failed={len(failed)} (shadow wiped)"
        )
        return {"closed": closed, "failed": failed,
                "n_closed": len(closed), "n_failed": len(failed)}

    def _lock_for(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._symbol_locks:
            self._symbol_locks[symbol] = asyncio.Lock()
        return self._symbol_locks[symbol]

    def update_settings(
        self,
        enabled: bool | None = None,
        execution_mode: str | None = None,
        dust_threshold_usd: float | None = None,
        evaluation_interval_seconds: float | None = None,
        margin_buffer_pct: float | None = None,
        adjust_threshold_pct: float | None = None,
    ) -> None:
        if enabled is not None:
            self._enabled = bool(enabled)
        if execution_mode is not None:
            self._execution_mode = str(execution_mode)
        if dust_threshold_usd is not None:
            self._dust_threshold_usd = float(dust_threshold_usd)
        if evaluation_interval_seconds is not None:
            self._evaluation_interval = float(evaluation_interval_seconds)
        if margin_buffer_pct is not None:
            self._margin_buffer_pct = float(margin_buffer_pct)
        if adjust_threshold_pct is not None:
            self._adjust_threshold_pct = float(adjust_threshold_pct)

    def mark_inventory_changed(self, reason: str = "") -> None:
        """Wake the next evaluate() call after spot inventory changes.

        The monitor calls evaluate() every tick, but evaluate() is normally
        throttled. A trade, rebalance, expansion, or demotion changes the
        target hedge immediately, so the next tick should reconcile instead
        of waiting for the periodic interval.
        """
        self._last_evaluation_ts = 0.0
        if reason and logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Hedge] inventory changed: {reason} — next eval unthrottled")

    # ── Sizing primitives ─────────────────────────────────────────────

    def compute_target_hedge_qty(self, spot_symbol: str) -> float:
        """Total spot quantity held across all exchanges for a symbol."""
        total = 0.0
        for ex in self._balance._exchanges:
            qty = self._balance.crypto.get(ex, {}).get(spot_symbol, 0.0)
            if qty > 0:
                total += qty
        return total

    def compute_target_hedge_usd(self, spot_symbol: str, price: float) -> float:
        return self.compute_target_hedge_qty(spot_symbol) * price

    def _held_symbols(self) -> set[str]:
        """Symbols with any positive spot inventory, including demoted residuals."""
        held: set[str] = set()
        for ex in self._balance._exchanges:
            for sym, qty in self._balance.crypto.get(ex, {}).items():
                if qty > 0:
                    held.add(sym)
        return held

    def _target_symbols(self) -> list[str]:
        """Symbols that need a hedge decision: active symbols plus held inventory."""
        active_symbols = list(self._optimizer._active_symbols) if self._optimizer else []
        active_set = set(active_symbols)
        residual_symbols = sorted(self._held_symbols() - active_set)
        return active_symbols + residual_symbols

    def is_available_on_futures(self, spot_symbol: str) -> bool:
        """True if Binance Futures has a perpetual for this symbol.

        Detected by: funding_monitor has a live rate for the futures symbol.
        Falls back to True before the first poll — we'll discover failures
        at order-placement time in Phase D.
        """
        rate = self._funding_monitor.get_funding_rate(spot_symbol)
        # Before first poll, we don't know — assume available (1000X mapping handled elsewhere)
        return rate is not None or self._funding_monitor._poll_count == 0

    def should_hedge(self, spot_symbol: str, target_usd: float) -> tuple[bool, str]:
        """Decide whether to hedge this symbol right now.

        Returns (decision, reason). Reason is a short tag suitable for log.
        Order of checks: cheapest gates first.
        """
        if not self._enabled:
            return (False, "hedging_disabled")
        if target_usd < self._dust_threshold_usd:
            return (False, f"dust(${target_usd:.2f}<${self._dust_threshold_usd:.0f})")
        if not self.is_available_on_futures(spot_symbol):
            return (False, "no_futures_contract")
        if self._funding_monitor.should_skip_hedge(spot_symbol):
            rate = (self._funding_monitor.get_funding_rate(spot_symbol) or 0.0) * 100
            interval_h = self._funding_monitor.get_funding_interval_hours(spot_symbol)
            return (False, f"funding_skip({rate:+.4f}%/{interval_h}h)")
        return (True, "ok")

    # ── Shadow position lifecycle ─────────────────────────────────────

    def _get_shadow(self, spot_symbol: str) -> ShadowHedge:
        if spot_symbol not in self._shadows:
            self._shadows[spot_symbol] = ShadowHedge(spot_symbol=spot_symbol)
        return self._shadows[spot_symbol]

    async def _open(self, spot_symbol: str, target_qty: float, price: float, now: float) -> bool:
        """Open a hedge for the given spot quantity.

        In simulation mode: shadow-only (logs WOULD_OPEN).
        In real mode: place futures market SHORT, update shadow on success.

        Returns True if the open landed (shadow updated), False on failure.
        """
        f_sym, mult = get_futures_symbol(spot_symbol)
        notional = target_qty * price
        ann_short = self._funding_monitor.get_annualized_short_pct(spot_symbol)
        ann_str = f"{ann_short:+.2f}%/yr" if ann_short is not None else "n/a"

        if not self._is_real_mode():
            # Shadow-only path
            sh = self._get_shadow(spot_symbol)
            sh.qty = target_qty
            sh.entry_price = price
            sh.opened_at = now
            sh.last_adjusted_at = now
            sh.last_funding_check_ts = now
            sh.open_count += 1
            self._total_opens += 1
            logger.info(
                f"[Hedge] WOULD_OPEN {spot_symbol} → {f_sym} "
                f"(mult={mult}) qty={target_qty:.6f} notional=${notional:.2f} "
                f"price=${price:.4f} funding={ann_str}"
            )
            return True

        # Real mode: prepare margin/leverage + check buffer
        if not await self._ensure_symbol_configured(f_sym):
            return False
        if not await self._has_margin_for(notional):
            self._total_executor_errors += 1
            logger.warning(
                f"[Hedge] OPEN_BLOCKED {spot_symbol}: insufficient margin for "
                f"${notional:.2f} (buffer={self._margin_buffer_pct*100:.0f}%)"
            )
            return False

        futures_qty = target_qty / mult  # 1000X scaling
        cid = f"hopen{int(now * 1000) % 1_000_000_000}"
        result = await self._executor.place_market_order(
            symbol=f_sym, side="SELL", qty=futures_qty,
            client_order_id=cid, reduce_only=False,
            expected_price=price * mult,  # 1000X-quoted price
        )
        if not result.success:
            self._total_executor_errors += 1
            logger.error(
                f"[Hedge] OPEN_FAILED {spot_symbol} → {f_sym} qty={futures_qty:.6f} "
                f"err={result.error}"
            )
            return False

        # Real fill landed — update shadow
        sh = self._get_shadow(spot_symbol)
        sh.qty = target_qty
        # Prefer real fill price (×mult to convert futures-quoted back to spot)
        fill_px = result.actual_avg_price / mult if result.actual_avg_price > 0 else price
        sh.entry_price = fill_px
        sh.opened_at = now
        sh.last_adjusted_at = now
        sh.last_funding_check_ts = now
        sh.open_count += 1
        self._total_opens += 1
        logger.info(
            f"[Hedge] OPEN {spot_symbol} → {f_sym} qty={futures_qty:.6f} "
            f"(spot_qty={target_qty:.6f}) fill_px=${fill_px:.4f} notional=${notional:.2f} "
            f"funding={ann_str} latency={result.latency_ms:.0f}ms"
        )
        return True

    async def _adjust(self, spot_symbol: str, new_qty: float, price: float, now: float) -> bool:
        """Adjust hedge size to match new target.

        Real mode: places a delta order (BUY to shrink short, SELL to grow short).
        Entry-price math (S31 fix):
          - Growing the position (|new_qty| > |old_qty|): the new fills happen
            at the executor's actual fill price, not the original entry. Compute
            a size-weighted average so unrealized PnL math is correct going
            forward. Without this, the entry stays frozen at the original value
            and produces a phantom unrealized PnL the more the position grows.
          - Shrinking (|new_qty| < |old_qty|): FIFO realization — the entry of
            the remaining position is unchanged; the closed slice's PnL is
            realized at fill price (handled in funding/PnL accounting).
        """
        sh = self._get_shadow(spot_symbol)
        old_qty = sh.qty
        old_entry = sh.entry_price
        delta = new_qty - old_qty
        if abs(delta) < 1e-12:
            return True
        # First accumulate funding for the period that just ended at the old size
        self._accumulate_funding(spot_symbol, now)

        f_sym, mult = get_futures_symbol(spot_symbol)
        notional = new_qty * price

        # Helper: size-weighted average entry for "growing" adjusts.
        def _weighted_entry(fill_price: float) -> float:
            """When growing the position (|new| > |old|), fill_qty = |new| - |old|
            new fills happen at fill_price. New entry = size-weighted average."""
            if old_entry <= 0 or abs(old_qty) < 1e-12:
                return fill_price  # no prior entry to blend
            fill_qty = abs(new_qty) - abs(old_qty)
            if fill_qty <= 0:
                return old_entry  # not growing — entry unchanged
            return (abs(old_qty) * old_entry + fill_qty * fill_price) / abs(new_qty)

        if not self._is_real_mode():
            # Shadow mode: use the input price as the synthetic fill price
            sh.qty = new_qty
            if abs(new_qty) > abs(old_qty):
                sh.entry_price = _weighted_entry(price)
            sh.last_adjusted_at = now
            sh.adjust_count += 1
            self._total_adjusts += 1
            sign = "+" if delta > 0 else "-"
            logger.info(
                f"[Hedge] WOULD_ADJUST {spot_symbol} {sign}{abs(delta):.6f} "
                f"(was {old_qty:.6f} → now {new_qty:.6f}) notional=${notional:.2f} "
                f"entry=${sh.entry_price:.4f}"
            )
            return True

        # Real mode: place a delta order
        if delta > 0:
            # Need MORE short. Sell more on futures.
            if not await self._has_margin_for(abs(delta) * price):
                self._total_executor_errors += 1
                logger.warning(
                    f"[Hedge] ADJUST_BLOCKED {spot_symbol}: insufficient margin for "
                    f"+${abs(delta)*price:.2f}"
                )
                return False
            side, futures_delta_qty = "SELL", abs(delta) / mult
        else:
            # Reduce short. Buy back, reduceOnly.
            side, futures_delta_qty = "BUY", abs(delta) / mult

        cid = f"hadj{int(now * 1000) % 1_000_000_000}"
        result = await self._executor.place_market_order(
            symbol=f_sym, side=side, qty=futures_delta_qty,
            client_order_id=cid, reduce_only=(side == "BUY"),
            expected_price=price * mult,
        )
        if not result.success:
            self._total_executor_errors += 1
            logger.error(
                f"[Hedge] ADJUST_FAILED {spot_symbol} {side} qty={futures_delta_qty:.6f} "
                f"err={result.error}"
            )
            return False

        # Recompute entry on grow using the actual fill price (or expected
        # if the executor doesn't report a real avg). On shrink, entry is
        # unchanged — FIFO realizes PnL on the closed slice.
        sh.qty = new_qty
        if abs(new_qty) > abs(old_qty):
            fill_px = (
                result.actual_avg_price
                if result.actual_avg_price > 0
                else price
            )
            new_entry = _weighted_entry(fill_px)
            entry_log = f" entry={old_entry:.4f}→{new_entry:.4f} (fill ${fill_px:.4f})"
            sh.entry_price = new_entry
        else:
            entry_log = f" entry=${old_entry:.4f} (unchanged on shrink)"
        sh.last_adjusted_at = now
        sh.adjust_count += 1
        self._total_adjusts += 1
        sign = "+" if delta > 0 else "-"
        logger.info(
            f"[Hedge] ADJUST {spot_symbol} {sign}{abs(delta):.6f} "
            f"(was {old_qty:.6f} → now {new_qty:.6f}) notional=${notional:.2f} "
            f"latency={result.latency_ms:.0f}ms{entry_log}"
        )
        return True

    async def _close(self, spot_symbol: str, price: float, now: float, reason: str) -> bool:
        """Close a hedge position.

        Real mode: calls executor.close_position() which auto-detects current side.
        """
        sh = self._shadows.get(spot_symbol)
        if sh is None or sh.qty == 0.0:
            return True
        # Final funding accrual against the OLD size
        self._accumulate_funding(spot_symbol, now)
        old_qty = sh.qty
        held_seconds = now - sh.opened_at if sh.opened_at > 0 else 0.0
        held_h = held_seconds / 3600

        if not self._is_real_mode():
            sh.qty = 0.0
            sh.entry_price = 0.0
            sh.opened_at = 0.0
            sh.close_count += 1
            self._total_closes += 1
            logger.info(
                f"[Hedge] WOULD_CLOSE {spot_symbol} qty={old_qty:.6f} held={held_h:.1f}h "
                f"reason={reason} cumulative_funding=${sh.accumulated_funding_usd:+.4f}"
            )
            return True

        # Real mode: query then close
        f_sym, mult = get_futures_symbol(spot_symbol)
        result = await self._executor.close_position(f_sym)
        if result is None:
            # No real position — sync shadow to zero
            sh.qty = 0.0
            sh.entry_price = 0.0
            sh.opened_at = 0.0
            sh.close_count += 1
            self._total_closes += 1
            logger.info(
                f"[Hedge] CLOSE {spot_symbol}: no real position to close "
                f"(shadow had {old_qty:.6f}); shadow synced to flat. reason={reason}"
            )
            return True
        if not result.success:
            self._total_executor_errors += 1
            logger.error(
                f"[Hedge] CLOSE_FAILED {spot_symbol} err={result.error} reason={reason}"
            )
            return False

        sh.qty = 0.0
        sh.entry_price = 0.0
        sh.opened_at = 0.0
        sh.close_count += 1
        self._total_closes += 1
        logger.info(
            f"[Hedge] CLOSE {spot_symbol} → {f_sym} closed_qty={result.filled_qty:.6f} "
            f"held={held_h:.1f}h reason={reason} "
            f"cumulative_funding=${sh.accumulated_funding_usd:+.4f} "
            f"latency={result.latency_ms:.0f}ms"
        )
        return True

    # ── Real-mode helpers ────────────────────────────────────────────

    async def _ensure_symbol_configured(self, futures_symbol: str) -> bool:
        """Set leverage + isolated margin for a futures symbol (cached, idempotent)."""
        if self._executor is None:
            return False
        if not await self._executor.set_leverage(futures_symbol, self._leverage):
            return False
        if not await self._executor.set_margin_type(futures_symbol, isolated=True):
            return False
        return True

    async def _has_margin_for(self, notional_usd: float) -> bool:
        """Check that available futures margin meets the buffered requirement."""
        if self._executor is None:
            return False
        info = await self._executor.get_account_info()
        if not info:
            return False
        available = float(info.get("available_balance", 0.0))
        required = notional_usd * (1.0 + self._margin_buffer_pct)
        return available >= required

    def _accumulate_funding(self, spot_symbol: str, now: float) -> None:
        """Add funding accrued since last check to the shadow state.

        For Phase C (shadow), we estimate: rate × notional × periods_elapsed.
        Periods are counted between settlements. If only a partial period has
        elapsed, we accrue proportionally — not exactly how real Binance
        funding works (paid in discrete events), but adequate for tracking.
        """
        sh = self._shadows.get(spot_symbol)
        if sh is None or sh.qty == 0.0 or sh.last_funding_check_ts == 0.0:
            return
        rate = self._funding_monitor.get_funding_rate(spot_symbol)
        if rate is None:
            return
        interval_h = self._funding_monitor.get_funding_interval_hours(spot_symbol)
        elapsed_s = now - sh.last_funding_check_ts
        if elapsed_s <= 0:
            return
        period_s = interval_h * 3600
        periods_fraction = elapsed_s / period_s
        # Notional at entry × accrued rate × fraction. Sign for SHORT:
        # positive funding = short receives (gain); negative = short pays (loss)
        notional = sh.qty * sh.entry_price
        delta = rate * periods_fraction * notional
        sh.accumulated_funding_usd += delta
        sh.funding_periods_observed += int(periods_fraction)
        sh.last_funding_check_ts = now
        self._cumulative_funding_usd += delta

    # ── Main evaluation loop ──────────────────────────────────────────

    async def evaluate(self, now: float | None = None, force: bool = False) -> None:
        """Run one decision cycle. Throttled by evaluation_interval unless force=True.

        In real mode, executor calls happen here — each per-symbol op is
        guarded by a per-symbol lock so concurrent calls (e.g. demote-during-
        eval) serialize correctly.
        """
        if not self._enabled:
            return
        if now is None:
            now = time.time()
        if not force and (now - self._last_evaluation_ts) < self._evaluation_interval:
            return
        self._last_evaluation_ts = now

        if self._optimizer is None:
            return  # No symbol set yet — nothing to evaluate

        # Lazy reconciliation on first eval after startup, in real mode only
        if self._is_real_mode() and not self._reconciled:
            await self.reconcile_with_executor()

        target_symbols = self._target_symbols()
        if not target_symbols:
            # No active/held symbols → close all open hedges.
            for sym in list(self._shadows.keys()):
                if self._shadows[sym].qty > 0:
                    async with self._lock_for(sym):
                        price = self._lookup_price(sym)
                        await self._close(sym, price, now, "no_spot_inventory")
            return

        prices = self._get_prices_for(target_symbols)

        # 1) For each active or held symbol: decide hedge. Residual crypto from
        # demoted symbols remains real spot exposure until sold, so it must stay
        # hedged instead of being closed only because the symbol left active set.
        seen: set[str] = set()
        for sym in target_symbols:
            seen.add(sym)
            price = prices.get(sym, 0.0)
            if price <= 0:
                continue
            target_qty = self.compute_target_hedge_qty(sym)
            target_usd = target_qty * price
            decision, reason = self.should_hedge(sym, target_usd)
            sh = self._shadows.get(sym)
            current_qty = sh.qty if sh else 0.0

            async with self._lock_for(sym):
                if not decision:
                    # We do NOT want a hedge. Close any open hedge.
                    if current_qty > 0:
                        await self._close(sym, price, now, reason)
                    else:
                        # Throttle to debug-level (silence per-symbol noise)
                        logger.debug(
                            f"[Hedge] SKIP {sym} target=${target_usd:.2f} reason={reason}"
                        )
                    continue

                # We DO want a hedge.
                if current_qty == 0.0:
                    if self._safety_paused:
                        logger.debug(
                            f"[Hedge] OPEN_SUPPRESSED {sym}: safety_pause active "
                            f"target=${target_usd:.2f}"
                        )
                        continue
                    await self._open(sym, target_qty, price, now)
                else:
                    # Already hedged. Adjust if drift exceeds threshold.
                    drift_pct = abs(target_qty - current_qty) / max(current_qty, 1e-12)
                    if drift_pct >= self._adjust_threshold_pct:
                        await self._adjust(sym, target_qty, price, now)
                    else:
                        # No adjustment needed — just accumulate funding
                        self._accumulate_funding(sym, now)

        # 2) For shadows of symbols with no active role and no held inventory:
        # close them. Dust-sized held positions close via should_hedge().
        for sym in list(self._shadows.keys()):
            if sym not in seen and self._shadows[sym].qty > 0:
                async with self._lock_for(sym):
                    price = self._lookup_price(sym)
                    await self._close(sym, price, now, "no_spot_inventory")

        # 3) Periodic summary log (every evaluation)
        n_open = sum(1 for s in self._shadows.values() if s.qty > 0)
        if n_open > 0:
            total_notional = sum(
                s.qty * s.entry_price for s in self._shadows.values() if s.qty > 0
            )
            logger.info(
                f"[Hedge] Eval cycle: {n_open} hedges open ({self._execution_mode}), "
                f"total_notional=${total_notional:.2f}, "
                f"cumulative_funding=${self._cumulative_funding_usd:+.4f}, "
                f"opens={self._total_opens} adjusts={self._total_adjusts} "
                f"closes={self._total_closes} errors={self._total_executor_errors}"
            )

    # ── Reconciliation ───────────────────────────────────────────────

    async def reconcile_with_executor(self) -> None:
        """Sync shadow state with actual exchange positions (real mode only).

        Strategy: real positions are source of truth. Any divergence is logged
        and the shadow is corrected to match. Run once at startup (lazy on
        first evaluate) and any time the operator suspects drift.
        """
        if self._executor is None:
            return
        positions = await self._executor.get_all_positions()
        actual_by_spot: dict[str, dict] = {}
        for pos in positions:
            f_sym = pos.get("symbol", "")
            spot_sym = _futures_to_spot(f_sym)
            if spot_sym is None:
                continue
            actual_by_spot[spot_sym] = pos

        n_drift = 0
        n_orphan = 0
        n_missing = 0

        # 1) Sync existing shadows against real
        for spot_sym, sh in list(self._shadows.items()):
            f_sym, mult = get_futures_symbol(spot_sym)
            real = actual_by_spot.get(spot_sym)
            real_size = real["size"] if real else 0.0
            # Expected real size if shadow is correct: short on real = -shadow_qty/mult
            expected_real = -(sh.qty / mult) if sh.qty > 0 else 0.0
            diff = abs(real_size - expected_real)
            if diff < 1e-9:
                continue
            n_drift += 1
            # Sync shadow to real
            new_shadow_qty = -real_size * mult
            logger.warning(
                f"[Hedge] RECONCILE {spot_sym}: shadow_qty={sh.qty:.6f} "
                f"(expected_real={expected_real:.6f}) actual_real={real_size:.6f} "
                f"diff={diff:.6f} → syncing shadow to {new_shadow_qty:.6f}"
            )
            sh.qty = new_shadow_qty
            if new_shadow_qty == 0.0:
                sh.entry_price = 0.0
                sh.opened_at = 0.0
            elif sh.entry_price == 0.0 and real:
                # Same anti-phantom-PnL logic as the orphan branch below:
                # prefer current markPrice over the exchange's stale entry.
                current_mark = float(real.get("mark_price", 0.0))
                if current_mark > 0:
                    sh.entry_price = current_mark
                else:
                    sh.entry_price = float(real.get("entry_price", 0.0))
                sh.opened_at = time.time()
                sh.last_funding_check_ts = time.time()

        # 2) Orphan real positions (no shadow entry)
        for spot_sym, real in actual_by_spot.items():
            if spot_sym in self._shadows:
                continue
            f_sym, mult = get_futures_symbol(spot_sym)
            real_size = real["size"]
            new_shadow_qty = -real_size * mult
            if new_shadow_qty == 0.0:
                continue
            n_orphan += 1
            historical_entry = float(real.get("entry_price", 0.0))
            current_mark = float(real.get("mark_price", 0.0))
            # Adopt at current markPrice — the historical entry on the
            # exchange's own position record can be days/sessions stale, and
            # on testnet the markPrice oracle drifts independently from real
            # markets. Marking against a stale entry produces a phantom
            # unrealized PnL the moment the bot starts MTM-ing the position
            # (S30 PENDLE -$215 case; S31 ARUSDT ~15% phantom drawdown).
            # Resetting the entry to current mark makes unrealized_pnl = 0
            # at adoption — the operator can then close or grow the position
            # via normal hedge ops without phantom losses.
            if current_mark > 0:
                adopted_entry = current_mark
                entry_log = (
                    f"entry=${adopted_entry:.4f} (was ${historical_entry:.4f} "
                    f"on exchange — reset to current markPrice to avoid phantom PnL)"
                )
            else:
                adopted_entry = historical_entry
                entry_log = f"entry=${adopted_entry:.4f} (markPrice unavailable — using historical)"
            logger.warning(
                f"[Hedge] RECONCILE {spot_sym}: orphan real position "
                f"size={real_size:.6f} {entry_log} "
                f"→ creating shadow entry"
            )
            self._shadows[spot_sym] = ShadowHedge(
                spot_symbol=spot_sym,
                qty=new_shadow_qty,
                entry_price=adopted_entry,
                opened_at=time.time(),
                last_funding_check_ts=time.time(),
            )

        # 3) Shadows expecting a real position but none exists
        for spot_sym, sh in self._shadows.items():
            if sh.qty > 0 and spot_sym not in actual_by_spot:
                n_missing += 1

        self._reconciled = True
        if n_drift or n_orphan or n_missing:
            logger.warning(
                f"[Hedge] RECONCILE_DONE: {n_drift} drift-corrected, "
                f"{n_orphan} orphans adopted, {n_missing} missing real positions"
            )
        else:
            logger.info("[Hedge] RECONCILE_DONE: shadow state matches exchange")

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_prices_for(self, symbols: list[str]) -> dict[str, float]:
        """Compute mid-price per symbol from the optimizer's fetcher view."""
        prices: dict[str, float] = {}
        if self._optimizer is None:
            return prices
        for fetcher in self._optimizer._fetchers:
            state = fetcher.get_state()
            for sym in symbols:
                ps = state.get(sym)
                if ps is None or not ps.bid or not ps.ask:
                    continue
                try:
                    bid = float(ps.bid); ask = float(ps.ask)
                    if bid > 0 and ask > 0 and sym not in prices:
                        prices[sym] = (bid + ask) / 2
                except (TypeError, ValueError):
                    continue
        return prices

    def _lookup_price(self, sym: str) -> float:
        """Best-effort single-symbol price lookup (for close decisions)."""
        return self._get_prices_for([sym]).get(sym, 0.0)

    # ── State persistence ────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        return {
            "_shadows": {
                sym: {
                    "spot_symbol": sh.spot_symbol,
                    "qty": sh.qty,
                    "entry_price": sh.entry_price,
                    "opened_at": sh.opened_at,
                    "last_adjusted_at": sh.last_adjusted_at,
                    "accumulated_funding_usd": sh.accumulated_funding_usd,
                    "funding_periods_observed": sh.funding_periods_observed,
                    "last_funding_check_ts": sh.last_funding_check_ts,
                    "open_count": sh.open_count,
                    "close_count": sh.close_count,
                    "adjust_count": sh.adjust_count,
                }
                for sym, sh in self._shadows.items()
            },
            "_cumulative_funding_usd": self._cumulative_funding_usd,
            "_total_opens": self._total_opens,
            "_total_closes": self._total_closes,
            "_total_adjusts": self._total_adjusts,
            "_total_executor_errors": self._total_executor_errors,
            "_last_evaluation_ts": self._last_evaluation_ts,
        }

    def from_state_dict(self, data: dict) -> None:
        self._cumulative_funding_usd = float(data.get("_cumulative_funding_usd", 0.0))
        self._total_opens = int(data.get("_total_opens", 0))
        self._total_closes = int(data.get("_total_closes", 0))
        self._total_adjusts = int(data.get("_total_adjusts", 0))
        self._total_executor_errors = int(data.get("_total_executor_errors", 0))
        self._last_evaluation_ts = float(data.get("_last_evaluation_ts", 0.0))
        self._shadows = {}
        for sym, sd in data.get("_shadows", {}).items():
            self._shadows[sym] = ShadowHedge(
                spot_symbol=sd.get("spot_symbol", sym),
                qty=float(sd.get("qty", 0.0)),
                entry_price=float(sd.get("entry_price", 0.0)),
                opened_at=float(sd.get("opened_at", 0.0)),
                last_adjusted_at=float(sd.get("last_adjusted_at", 0.0)),
                accumulated_funding_usd=float(sd.get("accumulated_funding_usd", 0.0)),
                funding_periods_observed=int(sd.get("funding_periods_observed", 0)),
                last_funding_check_ts=float(sd.get("last_funding_check_ts", 0.0)),
                open_count=int(sd.get("open_count", 0)),
                close_count=int(sd.get("close_count", 0)),
                adjust_count=int(sd.get("adjust_count", 0)),
            )

    # ── Debug snapshot for dashboard ─────────────────────────────────

    def get_debug_state(self) -> dict:
        now = time.time()
        # v0.30.1+: Mark-price source priority for hedge unrealized PnL:
        #   1. Binance Futures markPrice (from FundingMonitor poll, 1000X-scaled)
        #      — this is the actual close-out price on the hedge venue
        #   2. Spot mid from optimizer fetchers — fallback only
        # Using spot mid as proxy created phantom drawdowns (S25/S26): when
        # spot/futures basis spread, the offset between spot crypto MTM and
        # hedge unrealized was wrong by the basis. Now they truly net out.
        target_symbols = self._target_symbols()
        price_symbols = set(self._shadows.keys()) | set(target_symbols)
        if price_symbols and self._optimizer is not None:
            spot_prices = self._get_prices_for(list(price_symbols))
        else:
            spot_prices = {}

        open_hedges: list[dict] = []
        unhedged_targets: list[dict] = []
        total_notional = 0.0
        total_unrealized_pnl = 0.0
        total_target_notional = 0.0
        total_gap_notional = 0.0
        futures_mark_used = 0
        spot_fallback_used = 0
        open_symbols: set[str] = set()
        for s in self._shadows.values():
            if s.qty <= 0:
                continue
            open_symbols.add(s.spot_symbol)
            entry = s.entry_price
            # Prefer Binance Futures mark — actual hedge venue
            futures_mark = self._funding_monitor.get_mark_price(s.spot_symbol)
            if futures_mark is not None and futures_mark > 0:
                mark = futures_mark
                mark_source = "futures"
                futures_mark_used += 1
            else:
                # Fall back to spot mid until first funding poll arrives
                mark = spot_prices.get(s.spot_symbol, entry)
                mark_source = "spot"
                spot_fallback_used += 1
            # Short PnL: (entry - mark) × qty (positive when price drops)
            unrealized_pnl = (entry - mark) * s.qty
            notional = s.qty * (mark if mark > 0 else entry)
            target_qty = self.compute_target_hedge_qty(s.spot_symbol)
            target_notional = target_qty * (mark if mark > 0 else entry)
            gap_qty = target_qty - s.qty
            gap_notional = gap_qty * (mark if mark > 0 else entry)
            gap_pct = abs(gap_qty) / max(s.qty, 1e-12) if s.qty > 0 else 0.0
            funding_rate = self._funding_monitor.get_funding_rate(s.spot_symbol)
            ann_short = self._funding_monitor.get_annualized_short_pct(s.spot_symbol)
            open_hedges.append({
                "symbol": s.spot_symbol,
                "side": "SHORT",
                "qty": s.qty,
                "entry_price": entry,
                "mark_price": mark,
                "mark_source": mark_source,  # "futures" or "spot" (fallback)
                "notional_usd": notional,
                "target_qty": target_qty,
                "target_notional_usd": target_notional,
                "quantity_gap": gap_qty,
                "quantity_gap_pct": gap_pct,
                "notional_gap_usd": gap_notional,
                "unrealized_pnl_usd": unrealized_pnl,
                "opened_at": s.opened_at,
                "held_seconds": (now - s.opened_at) if s.opened_at > 0 else 0.0,
                "accumulated_funding_usd": s.accumulated_funding_usd,
                "funding_rate": funding_rate,
                "annualized_short_pct": ann_short,
                "open_count": s.open_count,
                "adjust_count": s.adjust_count,
            })
            total_notional += notional
            total_unrealized_pnl += unrealized_pnl
            total_target_notional += target_notional
            total_gap_notional += gap_notional

        for sym in target_symbols:
            if sym in open_symbols:
                continue
            target_qty = self.compute_target_hedge_qty(sym)
            if target_qty <= 0:
                continue
            futures_mark = self._funding_monitor.get_mark_price(sym)
            if futures_mark is not None and futures_mark > 0:
                mark = futures_mark
                mark_source = "futures"
            else:
                mark = spot_prices.get(sym, 0.0)
                mark_source = "spot"
            if mark <= 0:
                continue
            target_notional = target_qty * mark
            total_target_notional += target_notional
            total_gap_notional += target_notional
            unhedged_targets.append({
                "symbol": sym,
                "target_qty": target_qty,
                "target_notional_usd": target_notional,
                "mark_price": mark,
                "mark_source": mark_source,
                "reason": (
                    "dust"
                    if target_notional < self._dust_threshold_usd
                    else "no_open_hedge"
                ),
            })

        # v0.30.1+: log when first futures-mark snapshot is taken (one-time
        # transition from spot fallback to futures mark) — confirms Fix B
        # is active in the diagnostic logs.
        if futures_mark_used > 0 and not getattr(self, "_logged_futures_mark", False):
            logger.info(
                f"[Hedge] Mark price source: Binance Futures markPrice for "
                f"{futures_mark_used} hedge(s). Hedge unrealized PnL now "
                f"matches actual close-out price (was: spot mid proxy)."
            )
            self._logged_futures_mark = True

        return {
            "enabled": self._enabled,
            "execution_mode": self._execution_mode,
            "safety_paused": self._safety_paused,
            "dust_threshold_usd": self._dust_threshold_usd,
            "evaluation_interval_seconds": self._evaluation_interval,
            "margin_buffer_pct": self._margin_buffer_pct,
            "adjust_threshold_pct": self._adjust_threshold_pct,
            "open_count": len(open_hedges),
            "open_hedges": open_hedges,
            "unhedged_targets": unhedged_targets,
            # Backward-compat alias for shadow-only callers
            "open_shadows": open_hedges,
            "total_notional_usd": total_notional,
            "total_target_notional_usd": total_target_notional,
            "total_hedge_gap_usd": total_gap_notional,
            "total_unrealized_pnl_usd": total_unrealized_pnl,
            "cumulative_funding_usd": self._cumulative_funding_usd,
            "total_opens": self._total_opens,
            "total_closes": self._total_closes,
            "total_adjusts": self._total_adjusts,
            "total_executor_errors": self._total_executor_errors,
            "reconciled": self._reconciled,
            "last_evaluation_ts": self._last_evaluation_ts,
        }

    def get_recent_events(self, limit: int = 200) -> list[dict]:
        """Recent open/close/adjust events for the dashboard timeline.

        Phase F: returns lifetime aggregates per symbol (not a true event log).
        Replace with a deque[Event] in a follow-up if per-event detail is
        needed for analysis.
        """
        events: list[dict] = []
        for s in self._shadows.values():
            if s.open_count == 0 and s.close_count == 0:
                continue
            events.append({
                "symbol": s.spot_symbol,
                "open_count": s.open_count,
                "close_count": s.close_count,
                "adjust_count": s.adjust_count,
                "accumulated_funding_usd": s.accumulated_funding_usd,
                "current_qty": s.qty,
                "current_entry_price": s.entry_price,
                "opened_at": s.opened_at,
                "last_adjusted_at": s.last_adjusted_at,
            })
        events.sort(key=lambda e: e["accumulated_funding_usd"], reverse=True)
        return events[:limit]
