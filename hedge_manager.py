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


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if value == "":
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _reserve_numbers(info: dict) -> tuple[float, float, float, float]:
    wallet = _to_float(info.get("total_wallet_balance"))
    margin = _to_float(info.get("total_margin_balance"), wallet)
    available = _to_float(info.get("available_balance"))
    max_withdraw = _to_float(info.get("max_withdraw_amount"))
    return wallet, margin, available, max_withdraw


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
    accumulated_execution_fees_usd: float = 0.0
    accumulated_fee_bnb_discount_usd: float = 0.0
    accumulated_fee_referral_cashback_usd: float = 0.0


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
        leverage: int = 2,                        # set on each symbol before first open
        futures_taker_fee_rate: float = 0.0005,
        futures_bnb_discount_enabled: bool = True,
        futures_bnb_discount_pct: float = 0.10,
        futures_referral_cashback_enabled: bool = False,
        futures_referral_cashback_pct: float = 0.10,
        futures_bnb_auto_topup_enabled: bool = True,
        futures_bnb_min_usd: float = 5.0,
        futures_bnb_target_pct: float = 0.01,
        futures_bnb_transfer_min_usd: float = 5.0,
        spot_bnb_min_usd: float = 5.0,
        spot_bnb_auto_buy_enabled: bool = True,
        spot_bnb_target_pct: float = 0.01,
        spot_bnb_buy_min_usd: float = 10.0,
        total_capital: float = 0.0,
        futures_capital_target_pct: float = 0.40,
        futures_capital_topup_pct: float = 0.35,
        futures_capital_emergency_pct: float = 0.30,
        futures_capital_overflow_pct: float = 0.45,
        futures_capital_transfer_min_usd: float = 10.0,
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
        self._leverage = max(1, int(leverage))
        self._futures_taker_fee_rate = max(0.0, float(futures_taker_fee_rate))
        self._futures_bnb_discount_enabled = bool(futures_bnb_discount_enabled)
        self._futures_bnb_discount_pct = max(0.0, min(1.0, float(futures_bnb_discount_pct)))
        self._futures_referral_cashback_enabled = bool(futures_referral_cashback_enabled)
        self._futures_referral_cashback_pct = max(
            0.0,
            min(1.0, float(futures_referral_cashback_pct)),
        )
        self._futures_bnb_auto_topup_enabled = bool(futures_bnb_auto_topup_enabled)
        self._futures_bnb_min_usd = max(0.0, float(futures_bnb_min_usd))
        self._futures_bnb_target_pct = max(0.0, float(futures_bnb_target_pct))
        self._futures_bnb_transfer_min_usd = max(0.0, float(futures_bnb_transfer_min_usd))
        self._spot_bnb_min_usd = max(0.0, float(spot_bnb_min_usd))
        self._spot_bnb_auto_buy_enabled = bool(spot_bnb_auto_buy_enabled)
        self._spot_bnb_target_pct = max(0.0, float(spot_bnb_target_pct))
        self._spot_bnb_buy_min_usd = max(0.0, float(spot_bnb_buy_min_usd))
        self._total_capital = max(0.0, float(total_capital))
        self._futures_capital_target_pct = max(0.0, float(futures_capital_target_pct))
        self._futures_capital_topup_pct = max(0.0, float(futures_capital_topup_pct))
        self._futures_capital_emergency_pct = max(0.0, float(futures_capital_emergency_pct))
        self._futures_capital_overflow_pct = max(0.0, float(futures_capital_overflow_pct))
        self._futures_capital_transfer_min_usd = max(0.0, float(futures_capital_transfer_min_usd))
        self._last_reserve_check_ts: float = 0.0
        self._last_reserve_transfer_ts: float = 0.0
        self._last_reserve_error: str = ""
        self._last_bnb_reserve_check_ts: float = 0.0
        self._last_bnb_reserve_transfer_ts: float = 0.0
        self._last_spot_bnb_buy_ts: float = 0.0
        self._last_bnb_reserve_error: str = ""
        self._last_spot_bnb_buy_error: str = ""
        self._last_bnb_price_usd: float = 0.0
        self._bnb_fee_reserve_status: dict = self._make_bnb_fee_reserve_status("unknown")
        self._reserve_status: dict = self._make_reserve_status("unknown")
        self._last_bnb_reserve_status_log_ts: float = 0.0
        self._last_bnb_reserve_status_signature: str = ""
        self._last_spot_bnb_skip_log_ts: float = 0.0
        self._last_spot_bnb_skip_signature: str = ""
        self._last_bnb_topup_skip_log_ts: float = 0.0
        self._last_bnb_topup_skip_signature: str = ""
        self._last_futures_bnb_discount_skip_log_ts: float = 0.0
        self._last_futures_bnb_discount_skip_signature: str = ""
        self._sync_balance_bnb_reserve_floor()

        # Per-symbol shadow state
        self._shadows: dict[str, ShadowHedge] = {}

        # Per-symbol asyncio.Lock to serialize concurrent operations.
        # Created lazily — only when a symbol is first touched.
        self._symbol_locks: dict[str, asyncio.Lock] = {}
        self._close_failure_backoff: dict[str, tuple[float, float, int]] = {}

        # Last evaluation timestamp
        self._last_evaluation_ts: float = 0.0

        # Reconciliation has run at least once after startup
        self._reconciled: bool = False

        # Cumulative would-be statistics (lifetime, persisted)
        self._cumulative_funding_usd: float = 0.0
        self._cumulative_execution_fees_usd: float = 0.0
        self._cumulative_fee_bnb_discount_usd: float = 0.0
        self._cumulative_fee_referral_cashback_usd: float = 0.0
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
            f"adjust_floor=${self._hedge_adjust_floor_usd():.2f} "
            f"margin_buffer={self._margin_buffer_pct*100:.0f}% "
            f"leverage={self._leverage}x "
            f"futures_taker_fee={self._effective_futures_fee_rate()*100:.4f}% "
            f"futures_bnb_target={self._futures_bnb_target_pct*100:.0f}% "
            f"spot_bnb_floor=${self._spot_bnb_min_usd:.0f} "
            f"spot_bnb_buy={'on' if self._spot_bnb_auto_buy_enabled else 'off'} "
            f"spot_bnb_target={self._spot_bnb_target_pct*100:.0f}% "
            f"futures_reserve_target={self._futures_capital_target_pct*100:.0f}% "
            f"topup={self._futures_capital_topup_pct*100:.0f}% "
            f"emergency={self._futures_capital_emergency_pct*100:.0f}%"
        )

    # ── Public lifecycle hooks ────────────────────────────────────────

    def set_optimizer(self, optimizer: "SymbolOptimizer") -> None:
        self._optimizer = optimizer

    def set_executor(self, executor: "BinanceFuturesExecutor") -> None:
        """Wire the Binance Futures executor (Phase D)."""
        self._executor = executor

    def _is_real_mode(self) -> bool:
        return self._execution_mode in ("testnet", "live") and self._executor is not None

    def _futures_fee_components(
        self,
        notional_usd: float,
        *,
        bnb_discount_available: bool | None = None,
    ) -> dict[str, float]:
        """Estimate Binance USD-M futures taker fee components for one order."""
        notional = max(0.0, float(notional_usd))
        base_fee = notional * self._futures_taker_fee_rate
        apply_bnb_discount = self._futures_bnb_discount_enabled and (
            True if bnb_discount_available is None else bool(bnb_discount_available)
        )
        bnb_discount = (
            base_fee * self._futures_bnb_discount_pct
            if apply_bnb_discount
            else 0.0
        )
        fee_after_bnb = max(0.0, base_fee - bnb_discount)
        referral_cashback = (
            fee_after_bnb * self._futures_referral_cashback_pct
            if self._futures_referral_cashback_enabled
            else 0.0
        )
        net_fee = max(0.0, fee_after_bnb - referral_cashback)
        effective_rate = net_fee / notional if notional > 0 else 0.0
        return {
            "notional_usd": notional,
            "base_fee_usd": base_fee,
            "bnb_discount_usd": bnb_discount,
            "bnb_fee_payment_usd": fee_after_bnb if apply_bnb_discount else 0.0,
            "bnb_discount_applied": apply_bnb_discount,
            "referral_cashback_usd": referral_cashback,
            "net_fee_usd": net_fee,
            "effective_rate": effective_rate,
        }

    def _effective_futures_fee_rate(self) -> float:
        return self._futures_fee_components(1.0)["effective_rate"]

    def _record_execution_fee(
        self,
        shadow: ShadowHedge,
        notional_usd: float,
        *,
        actual_fee: float = 0.0,
        fee_currency: str = "",
    ) -> dict[str, float]:
        fee = self._actual_futures_fee_components(
            notional_usd,
            actual_fee,
            fee_currency,
        )
        if fee is None:
            fee = self._futures_fee_components(notional_usd, bnb_discount_available=True)
            bnb_fee_usd = fee.get("bnb_fee_payment_usd", 0.0)
            if bnb_fee_usd > 0 and not self._can_pay_futures_bnb_fee(bnb_fee_usd):
                self._log_futures_bnb_discount_skip(
                    time.time(),
                    shadow.spot_symbol,
                    bnb_fee_usd,
                )
                fee = self._futures_fee_components(
                    notional_usd,
                    bnb_discount_available=False,
                )
        elif fee.get("fee_source") == "actual":
            logger.debug(
                f"[Hedge] Actual futures fee {shadow.spot_symbol}: "
                f"${fee['net_fee_usd']:.4f} {fee.get('fee_currency', '')}"
            )
        shadow.accumulated_execution_fees_usd += fee["net_fee_usd"]
        shadow.accumulated_fee_bnb_discount_usd += fee["bnb_discount_usd"]
        shadow.accumulated_fee_referral_cashback_usd += fee["referral_cashback_usd"]
        self._cumulative_execution_fees_usd += fee["net_fee_usd"]
        self._cumulative_fee_bnb_discount_usd += fee["bnb_discount_usd"]
        self._cumulative_fee_referral_cashback_usd += fee["referral_cashback_usd"]
        bnb_fee_usd = fee.get("bnb_fee_payment_usd", 0.0)
        if self._execution_mode != "live" and bnb_fee_usd > 0:
            price = _to_float(self._funding_monitor.get_mark_price("BNBUSDT"))
            if price <= 0:
                price = self._last_bnb_price_usd or self._lookup_price("BNBUSDT")
            deducted = self._balance.deduct_futures_bnb_fee(
                bnb_fee_usd,
                price,
                context=f"hedge {shadow.spot_symbol}",
            )
            if deducted > 0:
                self._last_bnb_price_usd = price
        return fee

    def _actual_futures_fee_components(
        self,
        notional_usd: float,
        actual_fee: float,
        fee_currency: str,
    ) -> dict[str, float] | None:
        """Convert an exchange-reported futures commission into USD accounting."""
        raw_fee = max(0.0, float(actual_fee or 0.0))
        currency = str(fee_currency or "").upper()
        if raw_fee <= 0 or not currency or currency == "MIXED":
            return None

        if currency in ("USDT", "BUSD", "USDC", "USD"):
            fee_usd = raw_fee
        elif currency == "BNB":
            price = _to_float(self._funding_monitor.get_mark_price("BNBUSDT"))
            if price <= 0:
                price = self._last_bnb_price_usd or self._lookup_price("BNBUSDT")
            if price <= 0:
                return None
            self._last_bnb_price_usd = price
            fee_usd = raw_fee * price
        else:
            return None

        notional = max(0.0, float(notional_usd))
        base_fee = notional * self._futures_taker_fee_rate
        bnb_discount = (
            max(0.0, base_fee - fee_usd)
            if currency == "BNB" and self._futures_bnb_discount_enabled
            else 0.0
        )
        referral_cashback = (
            fee_usd * self._futures_referral_cashback_pct
            if self._futures_referral_cashback_enabled
            else 0.0
        )
        net_fee = max(0.0, fee_usd - referral_cashback)
        return {
            "notional_usd": notional,
            "base_fee_usd": base_fee,
            "bnb_discount_usd": bnb_discount,
            "bnb_fee_payment_usd": fee_usd if currency == "BNB" else 0.0,
            "bnb_discount_applied": currency == "BNB",
            "referral_cashback_usd": referral_cashback,
            "net_fee_usd": net_fee,
            "effective_rate": net_fee / notional if notional > 0 else 0.0,
            "fee_source": "actual",
            "fee_currency": currency,
            "raw_fee": raw_fee,
        }

    def _can_pay_futures_bnb_fee(self, fee_usd: float) -> bool:
        """Return whether the modeled Futures BNB wallet can fund this fee."""
        if not self._futures_bnb_discount_enabled:
            return False
        fee_value = max(0.0, float(fee_usd))
        if fee_value <= 0:
            return True

        price = _to_float(self._funding_monitor.get_mark_price("BNBUSDT"))
        if price <= 0:
            price = self._last_bnb_price_usd or self._lookup_price("BNBUSDT")
        if price <= 0:
            return False

        if self._execution_mode != "live":
            qty = float(getattr(self._balance, "binance_futures_bnb", 0.0) or 0.0)
            available_usd = qty * price
        else:
            status = self._bnb_fee_reserve_status if isinstance(self._bnb_fee_reserve_status, dict) else {}
            available_usd = float(status.get("futures_value_usd", 0.0) or 0.0)
        return available_usd + 1e-9 >= fee_value

    def _reserve_amounts(self) -> dict[str, float]:
        capital = float(self._total_capital or 0.0)
        return {
            "total_capital_usd": capital,
            "target_usd": capital * self._futures_capital_target_pct,
            "topup_usd": capital * self._futures_capital_topup_pct,
            "emergency_usd": capital * self._futures_capital_emergency_pct,
            "overflow_usd": capital * self._futures_capital_overflow_pct,
        }

    def _bnb_fee_reserve_amounts(self) -> dict[str, float]:
        capital = float(self._total_capital or 0.0)
        return {
            "target_usd": capital * self._futures_bnb_target_pct,
            "min_usd": self._futures_bnb_min_usd,
            "transfer_min_usd": self._futures_bnb_transfer_min_usd,
            "spot_min_usd": self._spot_bnb_min_usd,
            "spot_target_usd": max(
                self._spot_bnb_min_usd,
                capital * self._spot_bnb_target_pct,
            ),
            "spot_buy_min_usd": self._spot_bnb_buy_min_usd,
        }

    def _make_bnb_fee_reserve_status(
        self,
        status: str,
        *,
        price_usd: float = 0.0,
        futures_qty: float = 0.0,
        spot_qty: float = 0.0,
        last_error: str = "",
    ) -> dict:
        amounts = self._bnb_fee_reserve_amounts()
        futures_value = max(0.0, futures_qty * price_usd)
        spot_value = max(0.0, spot_qty * price_usd)
        spot_status = "healthy" if spot_value >= amounts["spot_min_usd"] else "low"
        reserve_mode = "live" if self._execution_mode == "live" else "simulated"
        return {
            "status": status,
            "mode": reserve_mode,
            "enabled": self._futures_bnb_auto_topup_enabled or self._spot_bnb_auto_buy_enabled,
            "discount_enabled": self._futures_bnb_discount_enabled,
            "target_pct": self._futures_bnb_target_pct,
            "target_usd": amounts["target_usd"],
            "min_usd": amounts["min_usd"],
            "transfer_min_usd": amounts["transfer_min_usd"],
            "spot_min_usd": amounts["spot_min_usd"],
            "spot_status": spot_status,
            "spot_auto_buy_enabled": self._spot_bnb_auto_buy_enabled,
            "spot_target_pct": self._spot_bnb_target_pct,
            "spot_target_usd": amounts["spot_target_usd"],
            "spot_buy_min_usd": amounts["spot_buy_min_usd"],
            "price_usd": price_usd,
            "futures_qty": futures_qty,
            "futures_value_usd": futures_value,
            "spot_qty": spot_qty,
            "spot_value_usd": spot_value,
            "last_check_ts": self._last_bnb_reserve_check_ts,
            "last_transfer_ts": self._last_bnb_reserve_transfer_ts,
            "last_spot_buy_ts": self._last_spot_bnb_buy_ts,
            "last_error": last_error or self._last_bnb_reserve_error,
            "last_spot_buy_error": self._last_spot_bnb_buy_error,
        }

    def _make_reserve_status(
        self,
        status: str,
        *,
        wallet_balance_usd: float = 0.0,
        margin_balance_usd: float = 0.0,
        available_usd: float = 0.0,
        max_withdraw_usd: float = 0.0,
        last_error: str = "",
    ) -> dict:
        amounts = self._reserve_amounts()
        notional = self._current_target_notional_usd()
        required_initial = notional / max(1, self._leverage)
        required_buffered = required_initial * (1.0 + self._margin_buffer_pct)
        can_open = status not in ("emergency", "unavailable", "unknown")
        status_payload = {
            "status": status,
            "execution_mode": self._execution_mode,
            "leverage": self._leverage,
            "margin_buffer_pct": self._margin_buffer_pct,
            "target_pct": self._futures_capital_target_pct,
            "topup_pct": self._futures_capital_topup_pct,
            "emergency_pct": self._futures_capital_emergency_pct,
            "overflow_pct": self._futures_capital_overflow_pct,
            "transfer_min_usd": self._futures_capital_transfer_min_usd,
            "wallet_balance_usd": wallet_balance_usd,
            "margin_balance_usd": margin_balance_usd,
            "available_usd": available_usd,
            "max_withdraw_usd": max_withdraw_usd,
            "required_initial_margin_usd": required_initial,
            "required_buffered_margin_usd": required_buffered,
            "can_open_new_hedges": can_open,
            "last_check_ts": self._last_reserve_check_ts,
            "last_transfer_ts": self._last_reserve_transfer_ts,
            "last_error": last_error or self._last_reserve_error,
            **amounts,
        }
        if hasattr(self, "_bnb_fee_reserve_status"):
            status_payload["bnb_fee_reserve"] = dict(self._bnb_fee_reserve_status)
        return status_payload

    def _classify_reserve(self, available_usd: float) -> str:
        amounts = self._reserve_amounts()
        if amounts["target_usd"] <= 0:
            return "disabled"
        if available_usd < amounts["emergency_usd"]:
            return "emergency"
        if available_usd < amounts["topup_usd"]:
            return "topup_needed"
        return "healthy"

    def _current_target_notional_usd(self) -> float:
        total = 0.0
        if self._optimizer is None:
            return 0.0
        for sym in self._target_symbols():
            price = self._lookup_price(sym)
            if price > 0:
                total += self.compute_target_hedge_usd(sym, price)
        return total

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
                size = _to_float(pos.get("size", pos.get("positionAmt")))
            except AttributeError:
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
        leverage: int | None = None,
        futures_taker_fee_rate: float | None = None,
        futures_bnb_discount_enabled: bool | None = None,
        futures_bnb_discount_pct: float | None = None,
        futures_referral_cashback_enabled: bool | None = None,
        futures_referral_cashback_pct: float | None = None,
        futures_bnb_auto_topup_enabled: bool | None = None,
        futures_bnb_min_usd: float | None = None,
        futures_bnb_target_pct: float | None = None,
        futures_bnb_transfer_min_usd: float | None = None,
        spot_bnb_min_usd: float | None = None,
        spot_bnb_auto_buy_enabled: bool | None = None,
        spot_bnb_target_pct: float | None = None,
        spot_bnb_buy_min_usd: float | None = None,
        total_capital: float | None = None,
        futures_capital_target_pct: float | None = None,
        futures_capital_topup_pct: float | None = None,
        futures_capital_emergency_pct: float | None = None,
        futures_capital_overflow_pct: float | None = None,
        futures_capital_transfer_min_usd: float | None = None,
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
        if leverage is not None:
            self._leverage = max(1, int(leverage))
        if futures_taker_fee_rate is not None:
            self._futures_taker_fee_rate = max(0.0, float(futures_taker_fee_rate))
        if futures_bnb_discount_enabled is not None:
            self._futures_bnb_discount_enabled = bool(futures_bnb_discount_enabled)
        if futures_bnb_discount_pct is not None:
            self._futures_bnb_discount_pct = max(
                0.0, min(1.0, float(futures_bnb_discount_pct))
            )
        if futures_referral_cashback_enabled is not None:
            self._futures_referral_cashback_enabled = bool(futures_referral_cashback_enabled)
        if futures_referral_cashback_pct is not None:
            self._futures_referral_cashback_pct = max(
                0.0, min(1.0, float(futures_referral_cashback_pct))
            )
        if futures_bnb_auto_topup_enabled is not None:
            self._futures_bnb_auto_topup_enabled = bool(futures_bnb_auto_topup_enabled)
        if futures_bnb_min_usd is not None:
            self._futures_bnb_min_usd = max(0.0, float(futures_bnb_min_usd))
        if futures_bnb_target_pct is not None:
            self._futures_bnb_target_pct = max(0.0, float(futures_bnb_target_pct))
        if futures_bnb_transfer_min_usd is not None:
            self._futures_bnb_transfer_min_usd = max(0.0, float(futures_bnb_transfer_min_usd))
        if spot_bnb_min_usd is not None:
            self._spot_bnb_min_usd = max(0.0, float(spot_bnb_min_usd))
        if spot_bnb_auto_buy_enabled is not None:
            self._spot_bnb_auto_buy_enabled = bool(spot_bnb_auto_buy_enabled)
        if spot_bnb_target_pct is not None:
            self._spot_bnb_target_pct = max(0.0, float(spot_bnb_target_pct))
        if spot_bnb_buy_min_usd is not None:
            self._spot_bnb_buy_min_usd = max(0.0, float(spot_bnb_buy_min_usd))
        if total_capital is not None:
            self._total_capital = max(0.0, float(total_capital))
        if futures_capital_target_pct is not None:
            self._futures_capital_target_pct = max(0.0, float(futures_capital_target_pct))
        if futures_capital_topup_pct is not None:
            self._futures_capital_topup_pct = max(0.0, float(futures_capital_topup_pct))
        if futures_capital_emergency_pct is not None:
            self._futures_capital_emergency_pct = max(0.0, float(futures_capital_emergency_pct))
        if futures_capital_overflow_pct is not None:
            self._futures_capital_overflow_pct = max(0.0, float(futures_capital_overflow_pct))
        if futures_capital_transfer_min_usd is not None:
            self._futures_capital_transfer_min_usd = max(0.0, float(futures_capital_transfer_min_usd))
        self._reserve_status = self._make_reserve_status(self._reserve_status.get("status", "unknown"))
        self._sync_balance_bnb_reserve_floor()

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

    def _sync_balance_bnb_reserve_floor(self) -> None:
        setter = getattr(self._balance, "set_binance_spot_bnb_reserved_usd", None)
        if callable(setter):
            setter(self._spot_bnb_min_usd)

    def _maybe_log_bnb_fee_reserve_status(self, now: float, status_payload: dict) -> None:
        """Log BNB reserve health on changes and then periodically."""
        signature = "|".join(
            str(status_payload.get(k, ""))
            for k in ("status", "spot_status", "last_error", "last_spot_buy_error")
        )
        if (
            signature == self._last_bnb_reserve_status_signature
            and now - self._last_bnb_reserve_status_log_ts < 300.0
        ):
            return
        self._last_bnb_reserve_status_signature = signature
        self._last_bnb_reserve_status_log_ts = now
        logger.info(
            f"[Hedge] BNB_RESERVE_STATUS status={status_payload.get('status', 'unknown')} "
            f"mode={status_payload.get('mode', 'unknown')} "
            f"spot=${status_payload.get('spot_value_usd', 0.0):.2f}/"
            f"${status_payload.get('spot_target_usd', 0.0):.2f} "
            f"floor=${status_payload.get('spot_min_usd', 0.0):.2f} "
            f"futures=${status_payload.get('futures_value_usd', 0.0):.2f}/"
            f"${status_payload.get('target_usd', 0.0):.2f} "
            f"fut_min=${status_payload.get('min_usd', 0.0):.2f} "
            f"price=${status_payload.get('price_usd', 0.0):.4f} "
            f"err={status_payload.get('last_error', '') or '-'} "
            f"spot_buy_err={status_payload.get('last_spot_buy_error', '') or '-'}"
        )

    def _log_spot_bnb_buy_skip(
        self,
        now: float,
        label: str,
        buy_attempt: int,
        reason: str,
        *,
        warning: bool = False,
    ) -> None:
        """Log repeated spot-BNB buy skips on change or every five minutes."""
        signature = f"{label}|{reason}"
        if (
            signature == self._last_spot_bnb_skip_signature
            and now - self._last_spot_bnb_skip_log_ts < 300.0
        ):
            return
        self._last_spot_bnb_skip_signature = signature
        self._last_spot_bnb_skip_log_ts = now
        message = f"[Hedge] {label} attempt={buy_attempt}: {reason}"
        if warning:
            logger.warning(message)
        else:
            logger.info(message)

    def _log_bnb_topup_skip(
        self,
        now: float,
        *,
        futures_value: float,
        target_usd: float,
        spot_value: float,
        spot_floor_usd: float,
        transfer_min_usd: float,
        transferable_usd: float,
    ) -> None:
        """Keep BNB top-up diagnostics without flooding logs every sweep."""
        reason = f"transferable_below_min:${transferable_usd:.2f}<${transfer_min_usd:.2f}"
        signature = (
            f"{reason}|fut={futures_value:.2f}|target={target_usd:.2f}|"
            f"spot={spot_value:.2f}|floor={spot_floor_usd:.2f}"
        )
        if (
            signature == self._last_bnb_topup_skip_signature
            and now - self._last_bnb_topup_skip_log_ts < 300.0
        ):
            logger.debug(f"[Hedge] FUTURES_BNB_TOPUP_SKIPPED throttled: {reason}")
            return
        self._last_bnb_topup_skip_signature = signature
        self._last_bnb_topup_skip_log_ts = now
        logger.info(
            f"[Hedge] FUTURES_BNB_TOPUP_SKIPPED futures=${futures_value:.2f} "
            f"target=${target_usd:.2f} spot=${spot_value:.2f} "
            f"spot_floor=${spot_floor_usd:.2f} transferable=${transferable_usd:.2f} "
            f"transfer_min=${transfer_min_usd:.2f}"
        )

    def _log_futures_bnb_discount_skip(
        self,
        now: float,
        spot_symbol: str,
        bnb_fee_usd: float,
    ) -> None:
        """Throttle repeated estimated-fee discount skip notices."""
        status = (
            self._bnb_fee_reserve_status
            if isinstance(self._bnb_fee_reserve_status, dict)
            else {}
        )
        reserve = float(status.get("futures_value_usd", 0.0) or 0.0)
        signature = f"{spot_symbol}|reserve=${reserve:.2f}|fee=${bnb_fee_usd:.4f}"
        if (
            signature == self._last_futures_bnb_discount_skip_signature
            and now - self._last_futures_bnb_discount_skip_log_ts < 300.0
        ):
            logger.debug(
                f"[Hedge] Futures BNB fee discount skipped for {spot_symbol}: "
                f"reserve=${reserve:.2f} estimated_fee=${bnb_fee_usd:.4f}"
            )
            return
        self._last_futures_bnb_discount_skip_signature = signature
        self._last_futures_bnb_discount_skip_log_ts = now
        logger.info(
            f"[Hedge] Futures BNB fee discount skipped for {spot_symbol}: "
            f"reserve=${reserve:.2f} below estimated fee ${bnb_fee_usd:.4f}"
        )

    # ── Sizing primitives ─────────────────────────────────────────────

    def compute_target_hedge_qty(self, spot_symbol: str) -> float:
        """Total spot quantity held across all exchanges for a symbol.

        Includes crypto in transit: it has left the source wallet but still
        belongs to the portfolio, so price movement remains spot exposure
        until delivery.
        """
        total = 0.0
        for ex in self._balance._exchanges:
            qty = self._balance.crypto.get(ex, {}).get(spot_symbol, 0.0)
            if qty > 0:
                total += qty
        for fund in getattr(self._balance, "_in_transit", []):
            if getattr(fund, "asset", None) == spot_symbol:
                qty = float(getattr(fund, "amount", 0.0) or 0.0)
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
        for fund in getattr(self._balance, "_in_transit", []):
            asset = getattr(fund, "asset", None)
            qty = float(getattr(fund, "amount", 0.0) or 0.0)
            if asset and asset != "USDT" and qty > 0:
                held.add(asset)
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

    def _hedge_adjust_floor_usd(self) -> float:
        """Minimum delta notional worth paying a futures adjustment fee for."""
        return max(self._dust_threshold_usd, self._total_capital * 0.001)

    def _should_adjust_hedge(
        self,
        current_qty: float,
        target_qty: float,
        price: float,
    ) -> tuple[bool, str]:
        if current_qty <= 0 or price <= 0:
            return (False, "no_current_hedge")
        drift_pct = abs(target_qty - current_qty) / max(current_qty, 1e-12)
        if drift_pct < self._adjust_threshold_pct:
            return (False, f"drift({drift_pct:.2%}<{self._adjust_threshold_pct:.2%})")
        delta_notional = abs(target_qty - current_qty) * price
        floor = self._hedge_adjust_floor_usd()
        if delta_notional < floor:
            return (False, f"delta_dust(${delta_notional:.2f}<${floor:.2f})")
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
            fee = self._record_execution_fee(sh, notional)
            logger.info(
                f"[Hedge] WOULD_OPEN {spot_symbol} → {f_sym} "
                f"(mult={mult}) qty={target_qty:.6f} notional=${notional:.2f} "
                f"price=${price:.4f} funding={ann_str} "
                f"fee=${fee['net_fee_usd']:.4f}@{fee['effective_rate']*100:.4f}%"
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
        fill_notional = result.filled_qty * result.actual_avg_price
        fee = self._record_execution_fee(
            sh,
            fill_notional if fill_notional > 0 else notional,
            actual_fee=result.actual_fee,
            fee_currency=result.fee_currency,
        )
        logger.info(
            f"[Hedge] OPEN {spot_symbol} → {f_sym} qty={futures_qty:.6f} "
            f"(spot_qty={target_qty:.6f}) fill_px=${fill_px:.4f} notional=${notional:.2f} "
            f"funding={ann_str} fee=${fee['net_fee_usd']:.4f}@{fee['effective_rate']*100:.4f}% "
            f"latency={result.latency_ms:.0f}ms"
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
            fee = self._record_execution_fee(sh, abs(delta) * price)
            sign = "+" if delta > 0 else "-"
            logger.info(
                f"[Hedge] WOULD_ADJUST {spot_symbol} {sign}{abs(delta):.6f} "
                f"(was {old_qty:.6f} → now {new_qty:.6f}) notional=${notional:.2f} "
                f"entry=${sh.entry_price:.4f} fee=${fee['net_fee_usd']:.4f}"
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
                result.actual_avg_price / mult
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
        fill_notional = result.filled_qty * result.actual_avg_price
        fee = self._record_execution_fee(
            sh,
            fill_notional if fill_notional > 0 else abs(delta) * price,
            actual_fee=result.actual_fee,
            fee_currency=result.fee_currency,
        )
        sign = "+" if delta > 0 else "-"
        logger.info(
            f"[Hedge] ADJUST {spot_symbol} {sign}{abs(delta):.6f} "
            f"(was {old_qty:.6f} → now {new_qty:.6f}) notional=${notional:.2f} "
            f"fee=${fee['net_fee_usd']:.4f} latency={result.latency_ms:.0f}ms{entry_log}"
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
            fee = self._record_execution_fee(sh, old_qty * price)
            sh.qty = 0.0
            sh.entry_price = 0.0
            sh.opened_at = 0.0
            sh.close_count += 1
            self._total_closes += 1
            logger.info(
                f"[Hedge] WOULD_CLOSE {spot_symbol} qty={old_qty:.6f} held={held_h:.1f}h "
                f"reason={reason} cumulative_funding=${sh.accumulated_funding_usd:+.4f} "
                f"fee=${fee['net_fee_usd']:.4f}"
            )
            return True

        # Real mode: query then close
        f_sym, mult = get_futures_symbol(spot_symbol)
        backoff = self._close_failure_backoff.get(spot_symbol)
        if backoff:
            retry_at, delay, attempts = backoff
            if now < retry_at:
                logger.debug(
                    f"[Hedge] CLOSE_BACKOFF {spot_symbol}: retry in "
                    f"{retry_at - now:.0f}s after {attempts} failed close attempts"
                )
                return False

        result = await self._executor.close_position(f_sym)
        if result is None:
            # No real position — sync shadow to zero
            self._close_failure_backoff.pop(spot_symbol, None)
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
            previous = self._close_failure_backoff.get(spot_symbol)
            prev_delay = previous[1] if previous else 30.0
            attempts = (previous[2] if previous else 0) + 1
            next_delay = min(max(prev_delay * 2.0, 60.0), 600.0)
            self._close_failure_backoff[spot_symbol] = (
                time.time() + next_delay,
                next_delay,
                attempts,
            )
            logger.error(
                f"[Hedge] CLOSE_FAILED {spot_symbol} err={result.error} reason={reason} "
                f"next_retry={next_delay:.0f}s attempts={attempts}"
            )
            return False

        self._close_failure_backoff.pop(spot_symbol, None)
        sh.qty = 0.0
        sh.entry_price = 0.0
        sh.opened_at = 0.0
        sh.close_count += 1
        self._total_closes += 1
        fill_notional = result.filled_qty * result.actual_avg_price
        fee = self._record_execution_fee(
            sh,
            fill_notional if fill_notional > 0 else old_qty * price,
            actual_fee=result.actual_fee,
            fee_currency=result.fee_currency,
        )
        logger.info(
            f"[Hedge] CLOSE {spot_symbol} → {f_sym} closed_qty={result.filled_qty:.6f} "
            f"held={held_h:.1f}h reason={reason} "
            f"cumulative_funding=${sh.accumulated_funding_usd:+.4f} "
            f"fee=${fee['net_fee_usd']:.4f} latency={result.latency_ms:.0f}ms"
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

    async def _refresh_bnb_fee_reserve(self, now: float, allow_transfer: bool) -> dict:
        """Maintain BNB reserves for Binance Spot and USD-M Futures fees.

        Live mode buys Spot BNB with a market order, then transfers excess
        Spot BNB to USD-M Futures when the Futures fee reserve is low.
        Non-live modes run the same policy against BalanceTracker's synthetic
        BNB wallets so the capital impact is visible before going live.
        """
        futures_policy_enabled = (
            self._futures_bnb_discount_enabled
            and self._futures_bnb_auto_topup_enabled
            and self._futures_bnb_target_pct > 0
        )
        spot_buy_enabled = (
            self._spot_bnb_auto_buy_enabled
            and (self._spot_bnb_min_usd > 0 or self._spot_bnb_target_pct > 0)
        )
        if not futures_policy_enabled and not spot_buy_enabled:
            self._last_bnb_reserve_check_ts = now
            self._bnb_fee_reserve_status = self._make_bnb_fee_reserve_status("disabled")
            self._maybe_log_bnb_fee_reserve_status(now, self._bnb_fee_reserve_status)
            return self._bnb_fee_reserve_status

        if now - self._last_bnb_reserve_check_ts < 60.0:
            return self._bnb_fee_reserve_status

        self._last_bnb_reserve_check_ts = now
        amounts = self._bnb_fee_reserve_amounts()
        simulated = self._execution_mode != "live"
        price = 0.0
        if not simulated and self._executor is not None:
            price = await self._executor.get_spot_ticker_price("BNBUSDT")
            if price <= 0:
                price = await self._executor.get_ticker_price("BNBUSDT")
        else:
            price = _to_float(self._funding_monitor.get_mark_price("BNBUSDT"))
            if price <= 0:
                price = self._lookup_price("BNBUSDT")
        if price <= 0:
            self._last_bnb_reserve_error = "bnb_price_unavailable"
            self._bnb_fee_reserve_status = self._make_bnb_fee_reserve_status(
                "unavailable",
                last_error=self._last_bnb_reserve_error,
            )
            self._maybe_log_bnb_fee_reserve_status(now, self._bnb_fee_reserve_status)
            return self._bnb_fee_reserve_status
        self._last_bnb_price_usd = price

        if simulated:
            futures_qty = float(getattr(self._balance, "binance_futures_bnb", 0.0) or 0.0)
            spot_qty = float(getattr(self._balance, "binance_spot_bnb", 0.0) or 0.0)
        elif self._executor is not None:
            futures_qty = await self._executor.get_balance("BNB")
            spot_qty = await self._executor.get_spot_balance("BNB")
        else:
            self._last_bnb_reserve_error = "futures_executor_missing"
            self._bnb_fee_reserve_status = self._make_bnb_fee_reserve_status(
                "unavailable",
                price_usd=price,
                last_error=self._last_bnb_reserve_error,
            )
            self._maybe_log_bnb_fee_reserve_status(now, self._bnb_fee_reserve_status)
            return self._bnb_fee_reserve_status

        futures_value = futures_qty * price
        spot_value = spot_qty * price
        futures_low = futures_policy_enabled and futures_value < amounts["min_usd"]
        spot_low = spot_buy_enabled and spot_value < amounts["spot_min_usd"]
        status = "low" if futures_low or spot_low else "healthy"
        self._last_bnb_reserve_error = ""
        self._last_spot_bnb_buy_error = ""

        futures_topup_needed_usd = (
            max(0.0, amounts["target_usd"] - futures_value)
            if futures_low
            else 0.0
        )
        required_spot_usd = amounts["spot_target_usd"]
        if futures_topup_needed_usd > 0:
            required_spot_usd = max(
                required_spot_usd,
                amounts["spot_min_usd"] + futures_topup_needed_usd,
            )

        buy_gap_ok = (now - self._last_spot_bnb_buy_ts) >= 60.0
        should_buy_spot = (
            allow_transfer
            and spot_buy_enabled
            and buy_gap_ok
            and (spot_low or (futures_topup_needed_usd > 0 and spot_value < required_spot_usd))
            and required_spot_usd > spot_value
        )
        if should_buy_spot:
            max_buy_attempts = 3
            buy_attempt = 0

            if simulated:
                while spot_value < required_spot_usd and buy_attempt < max_buy_attempts:
                    buy_attempt += 1
                    remaining_usd = max(0.0, required_spot_usd - spot_value)
                    available_usdt = max(0.0, float(self._balance.usdt.get("Binance", 0.0)))
                    if available_usdt <= 0:
                        self._last_spot_bnb_buy_error = (
                            f"sim_binance_spot_usdt=${available_usdt:.2f} "
                            f"remaining=${remaining_usd:.2f}"
                        )
                        self._last_spot_bnb_buy_ts = now
                        self._log_spot_bnb_buy_skip(
                            now,
                            "SIM_SPOT_BNB_BUY_SKIPPED",
                            buy_attempt,
                            self._last_spot_bnb_buy_error,
                        )
                        break
                    buy_usd = remaining_usd * 1.001
                    if 0 < buy_usd < amounts["spot_buy_min_usd"]:
                        buy_usd = amounts["spot_buy_min_usd"]
                    buy_usd = min(buy_usd, available_usdt)
                    if buy_usd < amounts["spot_buy_min_usd"]:
                        self._last_spot_bnb_buy_error = (
                            f"sim_binance_spot_usdt=${available_usdt:.2f} "
                            f"below_buy_min=${amounts['spot_buy_min_usd']:.2f}"
                        )
                        self._last_spot_bnb_buy_ts = now
                        self._log_spot_bnb_buy_skip(
                            now,
                            "SIM_SPOT_BNB_BUY_SKIPPED",
                            buy_attempt,
                            self._last_spot_bnb_buy_error,
                        )
                        break
                    result = self._balance.buy_spot_bnb_with_usdt(buy_usd, price)
                    if result.get("success"):
                        bought_qty = float(result.get("net_qty", 0.0) or 0.0)
                        spent = float(result.get("spent_usd", 0.0) or 0.0)
                        spot_qty += bought_qty
                        spot_value = spot_qty * price
                        self._last_spot_bnb_buy_ts = now
                        logger.info(
                            f"[Hedge] SIM_SPOT_BNB_BUY attempt={buy_attempt} "
                            f"amount=${spent:.2f} qty={bought_qty:.8f} BNB "
                            f"price=${price:.4f} "
                            f"spot=${spot_value:.2f} target=${required_spot_usd:.2f}"
                        )
                        if spot_value >= required_spot_usd:
                            break
                    else:
                        self._last_spot_bnb_buy_error = str(result.get("error") or result)
                        logger.warning(
                            f"[Hedge] SIM_SPOT_BNB_BUY_FAILED attempt={buy_attempt} "
                            f"amount=${buy_usd:.2f}: {self._last_spot_bnb_buy_error}"
                        )
                        break
            elif self._executor is not None:
                while spot_value < required_spot_usd and buy_attempt < max_buy_attempts:
                    buy_attempt += 1
                    latest_price = await self._executor.get_spot_ticker_price("BNBUSDT")
                    if latest_price <= 0:
                        latest_price = await self._executor.get_ticker_price("BNBUSDT")
                    if latest_price > 0:
                        price = latest_price
                        spot_value = spot_qty * price
                    remaining_usd = max(0.0, required_spot_usd - spot_value)
                    if remaining_usd <= 0:
                        break

                    buy_usd = remaining_usd * 1.001
                    if 0 < buy_usd < amounts["spot_buy_min_usd"]:
                        buy_usd = amounts["spot_buy_min_usd"]
                    available_usdt = await self._executor.get_spot_balance("USDT")
                    buy_usd = min(buy_usd, max(0.0, available_usdt))
                    if buy_usd < amounts["spot_buy_min_usd"]:
                        self._last_spot_bnb_buy_error = (
                            f"binance_spot_usdt=${available_usdt:.2f} "
                            f"below_buy_min=${amounts['spot_buy_min_usd']:.2f}"
                        )
                        self._last_spot_bnb_buy_ts = now
                        self._log_spot_bnb_buy_skip(
                            now,
                            "SPOT_BNB_BUY_SKIPPED",
                            buy_attempt,
                            self._last_spot_bnb_buy_error,
                            warning=True,
                        )
                        break

                    cid = f"bnbbuy{int(now * 1000) % 1_000_000_000}{buy_attempt}"
                    result = await self._executor.place_spot_market_buy_bnb(
                        buy_usd,
                        client_order_id=cid,
                    )
                    if result.get("success"):
                        bought_qty = float(result.get("net_qty", 0.0) or 0.0)
                        spent = float(result.get("spent_usdt", 0.0) or 0.0)
                        spot_qty += bought_qty
                        spot_value = spot_qty * price
                        self._last_spot_bnb_buy_ts = now
                        logger.info(
                            f"[Hedge] SPOT_BNB_BUY attempt={buy_attempt} "
                            f"amount=${spent:.2f} qty={bought_qty:.8f} BNB "
                            f"market_avg=${result.get('avg_price', 0.0):.4f} "
                            f"spot=${spot_value:.2f} target=${required_spot_usd:.2f}"
                        )
                        if spot_value >= required_spot_usd:
                            break
                    else:
                        error = str(result.get("error") or result)
                        self._last_spot_bnb_buy_error = error
                        logger.warning(
                            f"[Hedge] SPOT_BNB_BUY_FAILED attempt={buy_attempt} "
                            f"amount=${buy_usd:.2f}: {error}"
                        )
                        break

                if spot_value < required_spot_usd and not self._last_spot_bnb_buy_error:
                    self._last_spot_bnb_buy_error = (
                        f"spot_bnb_buy_incomplete spot=${spot_value:.2f} "
                        f"target=${required_spot_usd:.2f} attempts={buy_attempt}"
                    )
                    logger.warning(f"[Hedge] SPOT_BNB_BUY_INCOMPLETE: {self._last_spot_bnb_buy_error}")

            futures_value = futures_qty * price
            futures_low = futures_policy_enabled and futures_value < amounts["min_usd"]
            spot_low = spot_buy_enabled and spot_value < amounts["spot_min_usd"]
            status = "low" if futures_low or spot_low else "healthy"

        transfer_gap_ok = (now - self._last_bnb_reserve_transfer_ts) >= 30.0
        if (
            allow_transfer
            and futures_policy_enabled
            and futures_low
            and transfer_gap_ok
            and amounts["target_usd"] > futures_value
        ):
            desired_usd = amounts["target_usd"] - futures_value
            transferable_usd = max(0.0, spot_value - amounts["spot_min_usd"])
            transfer_usd = min(desired_usd, transferable_usd)
            if transfer_usd >= amounts["transfer_min_usd"]:
                transfer_qty = transfer_usd / price
                if simulated:
                    result = self._balance.transfer_spot_bnb_to_futures(transfer_qty)
                else:
                    result = await self._executor.transfer_spot_to_futures(
                        transfer_qty,
                        asset="BNB",
                    )
                if result.get("success"):
                    self._last_bnb_reserve_transfer_ts = now
                    moved_qty = float(result.get("amount", transfer_qty) or transfer_qty)
                    moved_usd = moved_qty * price
                    logger.info(
                        f"[Hedge] {'SIM_' if simulated else ''}FUTURES_BNB_TOPUP "
                        f"amount={moved_qty:.8f} BNB "
                        f"value=${moved_usd:.2f} target=${amounts['target_usd']:.2f} "
                        f"futures=${futures_value:.2f} spot_floor=${amounts['spot_min_usd']:.2f}"
                    )
                    futures_qty += moved_qty
                    spot_qty = max(0.0, spot_qty - moved_qty)
                    futures_value = futures_qty * price
                    spot_value = spot_qty * price
                    futures_low = futures_policy_enabled and futures_value < amounts["min_usd"]
                    spot_low = spot_buy_enabled and spot_value < amounts["spot_min_usd"]
                    status = "low" if futures_low or spot_low else "healthy"
                else:
                    self._last_bnb_reserve_error = str(result.get("error") or result)
                    logger.warning(
                        f"[Hedge] FUTURES_BNB_TOPUP_FAILED value=${transfer_usd:.2f}: "
                        f"{self._last_bnb_reserve_error}"
                    )
            else:
                self._last_bnb_reserve_error = (
                    f"spot_bnb_transferable=${transferable_usd:.2f} "
                    f"below_min=${amounts['transfer_min_usd']:.2f}"
                )
                self._log_bnb_topup_skip(
                    now,
                    futures_value=futures_value,
                    target_usd=amounts["target_usd"],
                    spot_value=spot_value,
                    spot_floor_usd=amounts["spot_min_usd"],
                    transfer_min_usd=amounts["transfer_min_usd"],
                    transferable_usd=transferable_usd,
                )

        self._bnb_fee_reserve_status = self._make_bnb_fee_reserve_status(
            status,
            price_usd=price,
            futures_qty=futures_qty,
            spot_qty=spot_qty,
            last_error=self._last_bnb_reserve_error,
        )
        self._maybe_log_bnb_fee_reserve_status(now, self._bnb_fee_reserve_status)
        return self._bnb_fee_reserve_status

    async def refresh_reserve_status(self, allow_transfer: bool = True) -> dict:
        """Refresh Binance Futures reserve health and optionally rebalance it.

        Reserve health is based on futures margin balance (wallet + unrealized
        PnL), not free available balance. Initial-margin capacity is checked
        separately before each grow/open order.
        """
        now = time.time()
        previous_status = dict(self._reserve_status)
        previous_check_ts = float(previous_status.get("last_check_ts", 0.0) or 0.0)
        previous_label = str(previous_status.get("status", "unknown"))
        if (
            self._is_real_mode()
            and previous_check_ts > 0
            and now - previous_check_ts < 5.0
            and not (allow_transfer and previous_label in ("emergency", "topup_needed"))
        ):
            return self._reserve_status

        self._last_reserve_check_ts = now

        if self._futures_capital_target_pct <= 0 or self._total_capital <= 0:
            wallet = margin = available = max_withdraw = 0.0
            if self._is_real_mode() and self._executor is not None:
                info = await self._executor.get_account_info()
                if info:
                    wallet, margin, available, max_withdraw = _reserve_numbers(info)
            else:
                available = float(getattr(self._balance, "binance_futures_usdt", 0.0) or 0.0)
                wallet = margin = max_withdraw = available
            self._reserve_status = self._make_reserve_status(
                "disabled",
                wallet_balance_usd=wallet,
                margin_balance_usd=margin,
                available_usd=available,
                max_withdraw_usd=max_withdraw,
            )
            return self._reserve_status

        if not self._is_real_mode():
            await self._refresh_bnb_fee_reserve(now, allow_transfer=allow_transfer)
            reserve = float(getattr(self._balance, "binance_futures_usdt", 0.0) or 0.0)
            status = self._classify_reserve(reserve)
            self._reserve_status = self._make_reserve_status(
                status,
                wallet_balance_usd=reserve,
                margin_balance_usd=reserve,
                available_usd=reserve,
                max_withdraw_usd=reserve,
            )
            return self._reserve_status

        if self._executor is None:
            self._reserve_status = self._make_reserve_status(
                "unavailable",
                last_error="futures_executor_missing",
            )
            return self._reserve_status

        info = await self._executor.get_account_info()
        if not info:
            self._last_reserve_error = "futures_account_info_unavailable"
            if (
                previous_check_ts > 0
                and previous_label not in ("unknown", "unavailable")
                and now - previous_check_ts <= 300.0
            ):
                cached = dict(previous_status)
                cached["last_error"] = (
                    "futures_account_info_unavailable_using_cached_reserve"
                )
                self._reserve_status = cached
                return self._reserve_status
            self._reserve_status = self._make_reserve_status(
                "unavailable",
                last_error=self._last_reserve_error,
            )
            return self._reserve_status

        wallet, margin, available, max_withdraw = _reserve_numbers(info)
        equity = margin if margin > 0 else wallet
        status = self._classify_reserve(equity)

        amounts = self._reserve_amounts()
        transfer_min = self._futures_capital_transfer_min_usd
        transfer_gap_ok = (now - self._last_reserve_transfer_ts) >= 30.0
        self._last_reserve_error = ""

        if (
            allow_transfer
            and self._execution_mode == "live"
            and status in ("emergency", "topup_needed")
            and transfer_gap_ok
        ):
            amount = max(0.0, amounts["target_usd"] - equity)
            if amount >= transfer_min:
                result = await self._executor.transfer_spot_to_futures(amount)
                if result.get("success"):
                    self._last_reserve_transfer_ts = now
                    logger.info(
                        f"[Hedge] FUTURES_RESERVE_TOPUP amount=${amount:.2f} "
                        f"target=${amounts['target_usd']:.2f} equity=${equity:.2f}"
                    )
                    info = await self._executor.get_account_info()
                    if info:
                        wallet, margin, available, max_withdraw = _reserve_numbers(info)
                        equity = margin if margin > 0 else wallet
                        status = self._classify_reserve(equity)
                else:
                    self._last_reserve_error = str(result.get("error") or result)
                    logger.warning(
                        f"[Hedge] FUTURES_RESERVE_TOPUP_FAILED amount=${amount:.2f}: "
                        f"{self._last_reserve_error}"
                    )

        if (
            allow_transfer
            and self._execution_mode == "live"
            and equity > amounts["overflow_usd"]
            and transfer_gap_ok
        ):
            amount = min(max(0.0, equity - amounts["target_usd"]), max_withdraw)
            if amount >= transfer_min:
                result = await self._executor.transfer_futures_to_spot(amount)
                if result.get("success"):
                    self._last_reserve_transfer_ts = now
                    logger.info(
                        f"[Hedge] FUTURES_RESERVE_OVERFLOW amount=${amount:.2f} "
                        f"target=${amounts['target_usd']:.2f} equity=${equity:.2f}"
                    )
                    info = await self._executor.get_account_info()
                    if info:
                        wallet, margin, available, max_withdraw = _reserve_numbers(info)
                        equity = margin if margin > 0 else wallet
                        status = self._classify_reserve(equity)
                else:
                    self._last_reserve_error = str(result.get("error") or result)
                    logger.warning(
                        f"[Hedge] FUTURES_RESERVE_OVERFLOW_FAILED amount=${amount:.2f}: "
                        f"{self._last_reserve_error}"
                    )

        await self._refresh_bnb_fee_reserve(now, allow_transfer=allow_transfer)
        self._reserve_status = self._make_reserve_status(
            status,
            wallet_balance_usd=wallet,
            margin_balance_usd=margin,
            available_usd=available,
            max_withdraw_usd=max_withdraw,
            last_error=self._last_reserve_error,
        )
        return self._reserve_status

    def can_open_spot_position(self) -> tuple[bool, str]:
        """Whether monitor may add spot exposure without leaving it unhedgeable."""
        if not self._enabled or self._futures_capital_target_pct <= 0:
            return (True, "ok")
        status = str(self._reserve_status.get("status", "unknown"))
        if self._execution_mode in ("testnet", "live") and status in (
            "unknown",
            "unavailable",
            "topup_needed",
            "emergency",
        ):
            return (False, f"futures_reserve_{status}")
        return (True, "ok")

    async def _has_margin_for(self, notional_usd: float) -> bool:
        """Check that available futures margin meets the buffered requirement."""
        if self._executor is None:
            return False
        status = await self.refresh_reserve_status(allow_transfer=True)
        reserve_status = str(status.get("status", "unknown"))
        if reserve_status in ("emergency", "unavailable", "unknown"):
            return False
        available = float(status.get("available_usd", 0.0) or 0.0)
        required = (notional_usd / max(1, self._leverage)) * (1.0 + self._margin_buffer_pct)
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

        await self.refresh_reserve_status(allow_transfer=True)

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
                    # Already hedged. Adjust only when drift is meaningful
                    # enough to justify another futures taker fee.
                    adjust_ok, adjust_reason = self._should_adjust_hedge(
                        current_qty,
                        target_qty,
                        price,
                    )
                    if adjust_ok:
                        await self._adjust(sym, target_qty, price, now)
                    else:
                        self._accumulate_funding(sym, now)
                        if adjust_reason.startswith("delta_dust"):
                            logger.debug(
                                f"[Hedge] ADJUST_SUPPRESSED {sym}: {adjust_reason} "
                                f"current={current_qty:.6f} target={target_qty:.6f}"
                            )

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
                f"reserve={self._reserve_status.get('status', 'unknown')} "
                f"equity=${self._reserve_status.get('margin_balance_usd', 0.0):.2f}/"
                f"${self._reserve_status.get('target_usd', 0.0):.2f}, "
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
            real_size = _to_float(real.get("size")) if real else 0.0
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
                current_mark = _to_float(real.get("mark_price"))
                if current_mark > 0:
                    sh.entry_price = current_mark
                else:
                    sh.entry_price = _to_float(real.get("entry_price"))
                sh.opened_at = time.time()
                sh.last_funding_check_ts = time.time()

        # 2) Orphan real positions (no shadow entry)
        for spot_sym, real in actual_by_spot.items():
            if spot_sym in self._shadows:
                continue
            f_sym, mult = get_futures_symbol(spot_sym)
            real_size = _to_float(real.get("size"))
            new_shadow_qty = -real_size * mult
            if new_shadow_qty == 0.0:
                continue
            n_orphan += 1
            historical_entry = _to_float(real.get("entry_price"))
            current_mark = _to_float(real.get("mark_price"))
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
                    "accumulated_execution_fees_usd": sh.accumulated_execution_fees_usd,
                    "accumulated_fee_bnb_discount_usd": sh.accumulated_fee_bnb_discount_usd,
                    "accumulated_fee_referral_cashback_usd": sh.accumulated_fee_referral_cashback_usd,
                }
                for sym, sh in self._shadows.items()
            },
            "_cumulative_funding_usd": self._cumulative_funding_usd,
            "_cumulative_execution_fees_usd": self._cumulative_execution_fees_usd,
            "_cumulative_fee_bnb_discount_usd": self._cumulative_fee_bnb_discount_usd,
            "_cumulative_fee_referral_cashback_usd": self._cumulative_fee_referral_cashback_usd,
            "_last_bnb_reserve_check_ts": self._last_bnb_reserve_check_ts,
            "_last_bnb_reserve_transfer_ts": self._last_bnb_reserve_transfer_ts,
            "_last_spot_bnb_buy_ts": self._last_spot_bnb_buy_ts,
            "_last_bnb_reserve_error": self._last_bnb_reserve_error,
            "_last_spot_bnb_buy_error": self._last_spot_bnb_buy_error,
            "_bnb_fee_reserve_status": dict(self._bnb_fee_reserve_status),
            "_last_bnb_reserve_status_log_ts": self._last_bnb_reserve_status_log_ts,
            "_last_bnb_reserve_status_signature": self._last_bnb_reserve_status_signature,
            "_last_spot_bnb_skip_log_ts": self._last_spot_bnb_skip_log_ts,
            "_last_spot_bnb_skip_signature": self._last_spot_bnb_skip_signature,
            "_last_bnb_topup_skip_log_ts": self._last_bnb_topup_skip_log_ts,
            "_last_bnb_topup_skip_signature": self._last_bnb_topup_skip_signature,
            "_last_futures_bnb_discount_skip_log_ts": self._last_futures_bnb_discount_skip_log_ts,
            "_last_futures_bnb_discount_skip_signature": self._last_futures_bnb_discount_skip_signature,
            "_close_failure_backoff": {
                sym: {
                    "retry_at": retry_at,
                    "delay": delay,
                    "attempts": attempts,
                }
                for sym, (retry_at, delay, attempts) in self._close_failure_backoff.items()
            },
            "_total_opens": self._total_opens,
            "_total_closes": self._total_closes,
            "_total_adjusts": self._total_adjusts,
            "_total_executor_errors": self._total_executor_errors,
            "_last_evaluation_ts": self._last_evaluation_ts,
        }

    def from_state_dict(self, data: dict) -> None:
        self._cumulative_funding_usd = float(data.get("_cumulative_funding_usd", 0.0))
        self._cumulative_execution_fees_usd = float(
            data.get("_cumulative_execution_fees_usd", 0.0)
        )
        self._cumulative_fee_bnb_discount_usd = float(
            data.get("_cumulative_fee_bnb_discount_usd", 0.0)
        )
        self._cumulative_fee_referral_cashback_usd = float(
            data.get("_cumulative_fee_referral_cashback_usd", 0.0)
        )
        self._last_bnb_reserve_check_ts = float(data.get("_last_bnb_reserve_check_ts", 0.0))
        self._last_bnb_reserve_transfer_ts = float(data.get("_last_bnb_reserve_transfer_ts", 0.0))
        self._last_spot_bnb_buy_ts = float(data.get("_last_spot_bnb_buy_ts", 0.0))
        self._last_bnb_reserve_error = str(data.get("_last_bnb_reserve_error", ""))
        self._last_spot_bnb_buy_error = str(data.get("_last_spot_bnb_buy_error", ""))
        if isinstance(data.get("_bnb_fee_reserve_status"), dict):
            self._bnb_fee_reserve_status = dict(data["_bnb_fee_reserve_status"])
        self._last_bnb_reserve_status_log_ts = float(
            data.get("_last_bnb_reserve_status_log_ts", 0.0)
        )
        self._last_bnb_reserve_status_signature = str(
            data.get("_last_bnb_reserve_status_signature", "")
        )
        self._last_spot_bnb_skip_log_ts = float(
            data.get("_last_spot_bnb_skip_log_ts", 0.0)
        )
        self._last_spot_bnb_skip_signature = str(
            data.get("_last_spot_bnb_skip_signature", "")
        )
        self._last_bnb_topup_skip_log_ts = float(
            data.get("_last_bnb_topup_skip_log_ts", 0.0)
        )
        self._last_bnb_topup_skip_signature = str(
            data.get("_last_bnb_topup_skip_signature", "")
        )
        self._last_futures_bnb_discount_skip_log_ts = float(
            data.get("_last_futures_bnb_discount_skip_log_ts", 0.0)
        )
        self._last_futures_bnb_discount_skip_signature = str(
            data.get("_last_futures_bnb_discount_skip_signature", "")
        )
        self._close_failure_backoff = {}
        now = time.time()
        raw_backoff = data.get("_close_failure_backoff", {})
        if isinstance(raw_backoff, dict):
            for sym, item in raw_backoff.items():
                if not isinstance(item, dict):
                    continue
                retry_at = float(item.get("retry_at", 0.0) or 0.0)
                if retry_at <= now:
                    continue
                delay = float(item.get("delay", 60.0) or 60.0)
                attempts = int(item.get("attempts", 1) or 1)
                self._close_failure_backoff[str(sym)] = (retry_at, delay, attempts)
        self._sync_balance_bnb_reserve_floor()
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
                accumulated_execution_fees_usd=float(
                    sd.get("accumulated_execution_fees_usd", 0.0)
                ),
                accumulated_fee_bnb_discount_usd=float(
                    sd.get("accumulated_fee_bnb_discount_usd", 0.0)
                ),
                accumulated_fee_referral_cashback_usd=float(
                    sd.get("accumulated_fee_referral_cashback_usd", 0.0)
                ),
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
                "total_pnl_usd": (
                    unrealized_pnl
                    + s.accumulated_funding_usd
                    - s.accumulated_execution_fees_usd
                ),
                "opened_at": s.opened_at,
                "held_seconds": (now - s.opened_at) if s.opened_at > 0 else 0.0,
                "accumulated_funding_usd": s.accumulated_funding_usd,
                "accumulated_execution_fees_usd": s.accumulated_execution_fees_usd,
                "accumulated_fee_bnb_discount_usd": s.accumulated_fee_bnb_discount_usd,
                "accumulated_fee_referral_cashback_usd": s.accumulated_fee_referral_cashback_usd,
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

        total_pnl = (
            total_unrealized_pnl
            + self._cumulative_funding_usd
            - self._cumulative_execution_fees_usd
        )

        return {
            "enabled": self._enabled,
            "execution_mode": self._execution_mode,
            "safety_paused": self._safety_paused,
            "dust_threshold_usd": self._dust_threshold_usd,
            "evaluation_interval_seconds": self._evaluation_interval,
            "leverage": self._leverage,
            "margin_buffer_pct": self._margin_buffer_pct,
            "adjust_threshold_pct": self._adjust_threshold_pct,
            "futures_reserve": dict(self._reserve_status),
            "open_count": len(open_hedges),
            "open_hedges": open_hedges,
            "unhedged_targets": unhedged_targets,
            # Backward-compat alias for shadow-only callers
            "open_shadows": open_hedges,
            "total_notional_usd": total_notional,
            "total_target_notional_usd": total_target_notional,
            "total_hedge_gap_usd": total_gap_notional,
            "total_unrealized_pnl_usd": total_unrealized_pnl,
            "total_pnl_usd": total_pnl,
            "cumulative_funding_usd": self._cumulative_funding_usd,
            "cumulative_execution_fees_usd": self._cumulative_execution_fees_usd,
            "cumulative_fee_bnb_discount_usd": self._cumulative_fee_bnb_discount_usd,
            "cumulative_fee_referral_cashback_usd": self._cumulative_fee_referral_cashback_usd,
            "futures_fee_rate": self._futures_taker_fee_rate,
            "futures_effective_fee_rate": self._effective_futures_fee_rate(),
            "futures_bnb_discount_enabled": self._futures_bnb_discount_enabled,
            "futures_bnb_discount_pct": self._futures_bnb_discount_pct,
            "futures_referral_cashback_enabled": self._futures_referral_cashback_enabled,
            "futures_referral_cashback_pct": self._futures_referral_cashback_pct,
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
                "accumulated_execution_fees_usd": s.accumulated_execution_fees_usd,
                "current_qty": s.qty,
                "current_entry_price": s.entry_price,
                "opened_at": s.opened_at,
                "last_adjusted_at": s.last_adjusted_at,
            })
        events.sort(key=lambda e: e["accumulated_funding_usd"], reverse=True)
        return events[:limit]
