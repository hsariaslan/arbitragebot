"""
Execution engine for CoirnaBot Phase 2 demo/live order placement.

Provides the core dataclasses (TradeResult, ArbitrageResult), a rate limiter,
the abstract ExecutionEngine base, and the DemoExecutor coordinator that
orchestrates parallel buy/sell order placement across exchanges.

When execution_mode=demo, the sim continues as baseline while DemoExecutor
places real orders on testnets. Actual fill data is compared with sim
expectations to detect discrepancies D-08 through D-14.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from exchange_info import ExchangeInfoManager

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────────────────


@dataclass
class TradeResult:
    """Result of a single order placed on an exchange."""

    success: bool
    order_id: str = ""                   # exchange order ID
    client_order_id: str = ""            # our idempotent ID
    exchange: str = ""
    symbol: str = ""
    side: str = ""                       # "buy" or "sell"
    requested_qty: float = 0.0
    filled_qty: float = 0.0              # D-09: may differ (partial fill)
    requested_price: float = 0.0         # what sim expected (ticker price)
    actual_avg_price: float = 0.0        # D-08: actual fill price
    actual_fee: float = 0.0              # actual fee amount charged
    fee_rate: float = 0.0                # actual fee rate (e.g. 0.001)
    fee_currency: str = ""               # D-05: "USDT", "BTC", "BNB", etc.
    is_maker: bool = False               # D-13: maker vs taker
    latency_ms: float = 0.0             # D-12: submit-to-fill time
    error: str = ""                      # D-10: rejection reason
    raw_response: dict = field(default_factory=dict)
    timestamp: float = 0.0              # fill timestamp

    @property
    def fill_ratio(self) -> float:
        """Fraction of requested qty that was filled (0.0 to 1.0)."""
        if self.requested_qty <= 0:
            return 0.0
        return min(self.filled_qty / self.requested_qty, 1.0)

    @property
    def is_partial(self) -> bool:
        return self.success and self.fill_ratio < 0.99

    @property
    def slippage_pct(self) -> float:
        """Price slippage as a percentage. Positive = worse than expected."""
        if self.requested_price <= 0 or self.actual_avg_price <= 0:
            return 0.0
        if self.side == "buy":
            # Slippage is positive when actual price is higher (paid more)
            return (self.actual_avg_price - self.requested_price) / self.requested_price * 100
        else:
            # Slippage is positive when actual price is lower (received less)
            return (self.requested_price - self.actual_avg_price) / self.requested_price * 100

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
            "requested_qty": self.requested_qty,
            "filled_qty": self.filled_qty,
            "requested_price": self.requested_price,
            "actual_avg_price": self.actual_avg_price,
            "actual_fee": self.actual_fee,
            "fee_rate": self.fee_rate,
            "fee_currency": self.fee_currency,
            "is_maker": self.is_maker,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class ArbitrageResult:
    """Result of a full arbitrage execution (buy + sell legs)."""

    buy_result: TradeResult
    sell_result: TradeResult
    one_legged: bool = False             # D-11: only one leg filled
    recovery_result: TradeResult | None = None  # D-11: unwind if one-legged
    total_latency_ms: float = 0.0        # D-12: detection-to-both-fills
    sim_profit_usd: float = 0.0          # what sim expected
    actual_profit_usd: float = 0.0       # what actually happened

    @property
    def both_filled(self) -> bool:
        return self.buy_result.success and self.sell_result.success

    @property
    def slippage_buy_pct(self) -> float:
        return self.buy_result.slippage_pct

    @property
    def slippage_sell_pct(self) -> float:
        return self.sell_result.slippage_pct

    @property
    def avg_slippage_pct(self) -> float:
        return (abs(self.slippage_buy_pct) + abs(self.slippage_sell_pct)) / 2

    def to_dict(self) -> dict:
        d = {
            "buy": self.buy_result.to_dict(),
            "sell": self.sell_result.to_dict(),
            "one_legged": self.one_legged,
            "total_latency_ms": self.total_latency_ms,
            "sim_profit_usd": self.sim_profit_usd,
            "actual_profit_usd": self.actual_profit_usd,
            "avg_slippage_pct": self.avg_slippage_pct,
        }
        if self.recovery_result:
            d["recovery"] = self.recovery_result.to_dict()
        return d


# ── Rate Limiter ─────────────────────────────────────────────────────────


class RateLimiter:
    """Per-exchange sliding window rate limiter (D-14).

    Prevents 429 responses by tracking request timestamps in a sliding
    window and blocking new requests when the limit is reached.
    """

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._blocked_count: int = 0

    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns False if rate limit would be exceeded."""
        now = time.time()
        cutoff = now - self._window

        # Evict expired entries
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

        if len(self._timestamps) >= self._max:
            self._blocked_count += 1
            return False

        self._timestamps.append(now)
        return True

    @property
    def remaining(self) -> int:
        now = time.time()
        cutoff = now - self._window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return max(0, self._max - len(self._timestamps))

    @property
    def blocked_count(self) -> int:
        return self._blocked_count


# ── Client Order ID Generation ───────────────────────────────────────────


def generate_client_order_id(symbol: str, side: str) -> str:
    """Generate an idempotent client order ID for crash recovery.

    Format: coirna-{base}-{side}-{ts_ms}-{uuid8}
    Example: coirna-BTC-buy-1740000000000-a1b2c3d4
    Max 36 chars (Binance limit).
    """
    base = symbol.replace("USDT", "")[:5]
    ts = str(int(time.time() * 1000))[-10:]  # last 10 digits
    uid = uuid.uuid4().hex[:6]
    s = side[0]  # "b" or "s"
    return f"coirna-{base}-{s}-{ts}-{uid}"


# ── Abstract Execution Engine ────────────────────────────────────────────


class ExecutionEngine(ABC):
    """Base class for per-exchange order execution."""

    def __init__(self, exchange_name: str, exchange_info: ExchangeInfoManager | None = None) -> None:
        self.exchange_name = exchange_name
        self._exchange_info = exchange_info

    @abstractmethod
    async def place_market_order(
        self, symbol: str, side: str, qty: float, client_order_id: str,
        expected_price: float = 0.0,
    ) -> TradeResult:
        """Place a market order. Returns TradeResult with fill details."""
        ...

    @abstractmethod
    async def get_order_status(self, symbol: str, order_id: str) -> TradeResult:
        """Query the status of an existing order."""
        ...

    @abstractmethod
    async def get_balance(self, asset: str) -> float:
        """Get available balance for an asset (e.g. 'USDT', 'BTC')."""
        ...

    @abstractmethod
    def format_symbol(self, symbol: str) -> str:
        """Convert our symbol format (BTCUSDT) to exchange format."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (aiohttp session, etc.)."""
        ...

    def _failed_result(self, symbol: str, side: str, qty: float,
                       expected_price: float, error: str,
                       client_order_id: str = "") -> TradeResult:
        """Create a TradeResult for a failed order."""
        return TradeResult(
            success=False,
            exchange=self.exchange_name,
            symbol=symbol,
            side=side,
            requested_qty=qty,
            requested_price=expected_price,
            error=error,
            client_order_id=client_order_id,
            timestamp=time.time(),
        )


# ── Demo Executor Coordinator ────────────────────────────────────────────


class DemoExecutor:
    """Coordinates parallel order execution across exchanges for arbitrage.

    When the monitor detects an opportunity, DemoExecutor places real orders
    on both exchanges simultaneously. Results are compared with sim expectations.
    Handles one-legged trade recovery (D-11) and balance reconciliation.
    """

    def __init__(
        self,
        exchange_info: ExchangeInfoManager | None,
        executors: dict[str, ExecutionEngine],
    ) -> None:
        self._exchange_info = exchange_info
        self._executors = executors
        self._total_trades: int = 0
        self._one_legged_count: int = 0
        self._rejection_count: int = 0
        self._partial_fill_count: int = 0

        # Pending order IDs for crash recovery
        self._pending_orders: list[dict] = []

    @property
    def supported_exchanges(self) -> list[str]:
        return list(self._executors.keys())

    def has_executor(self, exchange: str) -> bool:
        return exchange in self._executors

    def can_execute(self, buy_ex: str, sell_ex: str) -> bool:
        """Check if both exchanges have executors available."""
        return buy_ex in self._executors and sell_ex in self._executors

    async def execute_arbitrage(
        self,
        buy_ex: str,
        sell_ex: str,
        symbol: str,
        trade_size: float,
        buy_price: float,
        sell_price: float,
        buy_qty: float,
        sell_qty: float,
    ) -> ArbitrageResult:
        """Execute a full arbitrage trade (buy + sell) in parallel.

        Places market orders on both exchanges simultaneously.
        If one leg fails, attempts to unwind the other (D-11).
        Returns ArbitrageResult with actual fill data for comparison.
        """
        t0 = time.time()
        self._total_trades += 1

        buy_executor = self._executors[buy_ex]
        sell_executor = self._executors[sell_ex]

        buy_client_id = generate_client_order_id(symbol, "buy")
        sell_client_id = generate_client_order_id(symbol, "sell")

        # Track pending orders for crash recovery
        pending = [
            {"exchange": buy_ex, "symbol": symbol, "side": "buy",
             "client_id": buy_client_id, "qty": buy_qty, "price": buy_price},
            {"exchange": sell_ex, "symbol": symbol, "side": "sell",
             "client_id": sell_client_id, "qty": sell_qty, "price": sell_price},
        ]
        self._pending_orders.extend(pending)

        # Fire both legs in parallel
        buy_task = buy_executor.place_market_order(
            symbol, "buy", buy_qty, buy_client_id, expected_price=buy_price,
        )
        sell_task = sell_executor.place_market_order(
            symbol, "sell", sell_qty, sell_client_id, expected_price=sell_price,
        )

        results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)

        # Unpack results (handle exceptions)
        if isinstance(results[0], Exception):
            buy_result = buy_executor._failed_result(
                symbol, "buy", buy_qty, buy_price, str(results[0]), buy_client_id,
            )
        else:
            buy_result = results[0]

        if isinstance(results[1], Exception):
            sell_result = sell_executor._failed_result(
                symbol, "sell", sell_qty, sell_price, str(results[1]), sell_client_id,
            )
        else:
            sell_result = results[1]

        total_latency = (time.time() - t0) * 1000.0

        # Clear pending orders (completed or failed)
        self._pending_orders = [
            p for p in self._pending_orders
            if p["client_id"] not in (buy_client_id, sell_client_id)
        ]

        # Check for one-legged trade (D-11)
        one_legged = buy_result.success != sell_result.success
        recovery_result = None

        if one_legged:
            self._one_legged_count += 1
            logger.warning(
                f"[Executor] ONE-LEGGED TRADE {symbol}: "
                f"buy={'OK' if buy_result.success else 'FAIL'} on {buy_ex}, "
                f"sell={'OK' if sell_result.success else 'FAIL'} on {sell_ex}"
            )
            recovery_result = await self._handle_one_legged(
                buy_result, sell_result, buy_executor, sell_executor,
            )

        # Track rejections and partial fills
        if not buy_result.success:
            self._rejection_count += 1
        if not sell_result.success:
            self._rejection_count += 1
        if buy_result.is_partial:
            self._partial_fill_count += 1
        if sell_result.is_partial:
            self._partial_fill_count += 1

        # Compute actual profit
        actual_profit = 0.0
        if buy_result.success and sell_result.success:
            buy_cost = buy_result.filled_qty * buy_result.actual_avg_price
            buy_fee_cost = buy_result.actual_fee if buy_result.fee_currency == "USDT" else 0.0
            sell_revenue = sell_result.filled_qty * sell_result.actual_avg_price
            sell_fee_cost = sell_result.actual_fee if sell_result.fee_currency == "USDT" else 0.0
            actual_profit = sell_revenue - buy_cost - buy_fee_cost - sell_fee_cost

        sim_profit = trade_size * (
            (sell_price - buy_price) / buy_price * 100
        ) / 100 if buy_price > 0 else 0.0

        arb_result = ArbitrageResult(
            buy_result=buy_result,
            sell_result=sell_result,
            one_legged=one_legged,
            recovery_result=recovery_result,
            total_latency_ms=total_latency,
            sim_profit_usd=sim_profit,
            actual_profit_usd=actual_profit,
        )

        # Log trade result
        status = "FILLED" if arb_result.both_filled else (
            "ONE-LEGGED" if one_legged else "REJECTED"
        )
        logger.info(
            f"[Executor] {symbol} {buy_ex}→{sell_ex} {status}: "
            f"buy@{buy_result.actual_avg_price:.4f} "
            f"sell@{sell_result.actual_avg_price:.4f} "
            f"slippage={arb_result.avg_slippage_pct:.4f}% "
            f"latency={total_latency:.0f}ms "
            f"sim_profit=${sim_profit:.4f} actual=${actual_profit:.4f}"
        )

        return arb_result

    async def _handle_one_legged(
        self,
        buy_result: TradeResult,
        sell_result: TradeResult,
        buy_executor: ExecutionEngine,
        sell_executor: ExecutionEngine,
    ) -> TradeResult:
        """Recover from a one-legged trade by unwinding the successful leg.

        If buy filled but sell failed: sell the bought crypto on the same
        exchange where we bought it.
        If sell filled but buy failed: buy back crypto on the same exchange
        where we sold it.
        """
        if buy_result.success and not sell_result.success:
            # Buy filled, sell failed → sell the bought crypto on buy exchange
            recovery_symbol = buy_result.symbol
            recovery_qty = buy_result.filled_qty
            recovery_side = "sell"
            executor = buy_executor
            logger.warning(
                f"[Executor] Unwinding buy leg: selling {recovery_qty:.8f} "
                f"{recovery_symbol} on {buy_result.exchange}"
            )
        elif sell_result.success and not buy_result.success:
            # Sell filled, buy failed → buy back crypto on sell exchange
            recovery_symbol = sell_result.symbol
            recovery_qty = sell_result.filled_qty
            recovery_side = "buy"
            executor = sell_executor
            logger.warning(
                f"[Executor] Unwinding sell leg: buying {recovery_qty:.8f} "
                f"{recovery_symbol} on {sell_result.exchange}"
            )
        else:
            # Both failed — nothing to unwind
            return TradeResult(success=False, error="nothing_to_unwind")

        recovery_id = generate_client_order_id(recovery_symbol, f"rcv-{recovery_side}")

        try:
            result = await executor.place_market_order(
                recovery_symbol, recovery_side, recovery_qty, recovery_id,
            )
            if result.success:
                logger.info(
                    f"[Executor] Recovery {recovery_side} filled: "
                    f"qty={result.filled_qty:.8f} @ {result.actual_avg_price:.4f}"
                )
            else:
                logger.error(
                    f"[Executor] RECOVERY FAILED: {result.error} — "
                    f"MANUAL INTERVENTION NEEDED for {recovery_qty:.8f} "
                    f"{recovery_symbol} on {executor.exchange_name}"
                )
            return result
        except Exception as e:
            logger.error(
                f"[Executor] RECOVERY EXCEPTION: {e} — "
                f"MANUAL INTERVENTION NEEDED for {recovery_qty:.8f} "
                f"{recovery_symbol} on {executor.exchange_name}"
            )
            return TradeResult(
                success=False,
                exchange=executor.exchange_name,
                symbol=recovery_symbol,
                side=recovery_side,
                error=f"recovery_exception: {e}",
                timestamp=time.time(),
            )

    async def reconcile_balances(
        self, balance_tracker: "BalanceTracker",
    ) -> dict[str, dict]:
        """Query actual exchange balances and compare with BalanceTracker.

        Called on startup when execution_mode=demo. Detects D-19 (missing
        positions) and D-20 (extra positions).

        Returns dict of exchange → {asset: {sim: x, actual: y, diff: z}}.
        """
        from balance import BalanceTracker  # avoid circular

        discrepancies: dict[str, dict] = {}

        for ex_name, executor in self._executors.items():
            ex_discs: dict[str, dict] = {}

            # Check USDT
            try:
                actual_usdt = await executor.get_balance("USDT")
                sim_usdt = balance_tracker.usdt.get(ex_name, 0.0)
                diff = actual_usdt - sim_usdt
                if abs(diff) > 1.0:
                    ex_discs["USDT"] = {
                        "sim": sim_usdt, "actual": actual_usdt, "diff": diff,
                    }
                    logger.warning(
                        f"[Reconcile] {ex_name} USDT: sim=${sim_usdt:.2f} "
                        f"actual=${actual_usdt:.2f} diff=${diff:+.2f}"
                    )
            except Exception as e:
                logger.warning(f"[Reconcile] {ex_name} USDT balance query failed: {e}")

            # Check crypto positions
            sim_crypto = balance_tracker.crypto.get(ex_name, {})
            for symbol, sim_qty in sim_crypto.items():
                if sim_qty <= 0:
                    continue
                asset = symbol.replace("USDT", "")
                try:
                    actual_qty = await executor.get_balance(asset)
                    diff = actual_qty - sim_qty
                    if abs(diff) / max(sim_qty, 1e-10) > 0.01:  # >1% difference
                        ex_discs[symbol] = {
                            "sim": sim_qty, "actual": actual_qty, "diff": diff,
                        }
                        logger.warning(
                            f"[Reconcile] {ex_name} {symbol}: sim={sim_qty:.8f} "
                            f"actual={actual_qty:.8f} diff={diff:+.8f}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[Reconcile] {ex_name} {asset} balance query failed: {e}"
                    )

            if ex_discs:
                discrepancies[ex_name] = ex_discs

        if discrepancies:
            total = sum(len(d) for d in discrepancies.values())
            logger.warning(
                f"[Reconcile] Found {total} balance discrepancies across "
                f"{len(discrepancies)} exchanges"
            )
        else:
            logger.info("[Reconcile] All exchange balances match BalanceTracker")

        return discrepancies

    async def recover_pending_orders(self) -> list[TradeResult]:
        """On startup, check status of any pending orders from before crash.

        Uses client order IDs to query exchanges. Updates state accordingly.
        """
        if not self._pending_orders:
            return []

        logger.info(
            f"[Executor] Recovering {len(self._pending_orders)} pending orders..."
        )
        recovered: list[TradeResult] = []

        for pending in list(self._pending_orders):
            ex = pending["exchange"]
            if ex not in self._executors:
                continue
            executor = self._executors[ex]
            try:
                result = await executor.get_order_status(
                    pending["symbol"], pending["client_id"],
                )
                recovered.append(result)
                logger.info(
                    f"[Executor] Recovered {pending['symbol']} {pending['side']} "
                    f"on {ex}: {'FILLED' if result.success else 'NOT_FILLED'} "
                    f"qty={result.filled_qty:.8f}"
                )
            except Exception as e:
                logger.warning(
                    f"[Executor] Failed to recover {pending['symbol']} "
                    f"{pending['side']} on {ex}: {e}"
                )

        self._pending_orders.clear()
        return recovered

    async def execute_setup_orders(
        self,
        allocations: dict[str, dict[str, float]],
        prices: dict[str, float],
        crypto_init_time: float,
        exchange_info: "ExchangeInfoManager | None" = None,
    ) -> list[TradeResult]:
        """Place initial buy orders on demo/testnet to establish positions.

        Called once after initialize_crypto() to mirror sim's virtual positions
        with real demo orders. Each allocation becomes a market buy order.

        Args:
            allocations: {exchange: {symbol: usd_amount}} from balance._crypto_usd
            prices: Current prices for all symbols
            crypto_init_time: Timestamp when initialize_crypto() completed
            exchange_info: For lot_size rounding

        Returns list of TradeResult for every order attempted.
        """
        from decimal import Decimal

        info = exchange_info or self._exchange_info
        results: list[TradeResult] = []
        total_sim_alloc = 0.0
        total_demo_cost = 0.0
        filled_count = 0
        partial_count = 0
        rejected_count = 0

        for exchange, symbols in sorted(allocations.items()):
            if not self.has_executor(exchange):
                continue

            executor = self._executors[exchange]

            for symbol, usd_amount in sorted(symbols.items()):
                if usd_amount <= 0 or symbol not in prices or prices[symbol] <= 0:
                    continue

                price = prices[symbol]
                qty = usd_amount / price

                # Round quantity via exchange_info if available
                if info:
                    qty_dec = info.round_quantity(exchange, symbol, Decimal(str(qty)))
                    qty = float(qty_dec)

                if qty <= 0:
                    continue

                # Check min notional
                if info:
                    rules = info.get_rules(exchange, symbol)
                    if rules and qty * price < float(rules.min_notional):
                        logger.info(
                            f"[DemoSetup] {exchange} {symbol} SKIP: "
                            f"${usd_amount:.2f} below min notional ${float(rules.min_notional):.2f}"
                        )
                        continue

                client_id = generate_client_order_id(symbol, "setup")

                # Wait for rate limit
                if hasattr(executor, '_rate_limiter'):
                    while not await executor._rate_limiter.acquire():
                        await asyncio.sleep(0.1)

                t0 = time.time()
                try:
                    result = await executor.place_market_order(
                        symbol, "buy", qty, client_id, expected_price=price,
                    )
                except Exception as e:
                    result = TradeResult(
                        success=False,
                        exchange=exchange,
                        symbol=symbol,
                        side="buy",
                        requested_qty=qty,
                        requested_price=price,
                        error=str(e),
                        timestamp=time.time(),
                    )

                order_time = time.time()
                setup_delay_ms = (order_time - crypto_init_time) * 1000
                latency_ms = (order_time - t0) * 1000

                # Compute actual demo cost
                demo_cost = 0.0
                if result.success:
                    demo_cost = result.filled_qty * result.actual_avg_price
                    if result.fee_currency == "USDT":
                        demo_cost += result.actual_fee
                    filled_count += 1
                    if result.is_partial:
                        partial_count += 1
                else:
                    rejected_count += 1

                total_sim_alloc += usd_amount
                total_demo_cost += demo_cost
                diff = usd_amount - demo_cost

                # Per-order log with timing
                status = "FILLED" if result.success and not result.is_partial else (
                    "PARTIAL" if result.success else "REJECTED"
                )
                fee_info = (
                    f"fee=${result.actual_fee:.4f} ({result.fee_rate*100:.3f}% {result.fee_currency})"
                    if result.success else f"error={result.error}"
                )
                logger.info(
                    f"[DemoSetup] {exchange} {symbol} BUY: "
                    f"qty={qty:.8f} price=${price:.2f} | "
                    f"status={status} filled={result.filled_qty:.8f} "
                    f"avg=${result.actual_avg_price:.2f} | "
                    f"latency={latency_ms:.0f}ms setup_delay={setup_delay_ms:.0f}ms | "
                    f"{fee_info} | "
                    f"sim_alloc=${usd_amount:.2f} demo_cost=${demo_cost:.2f} diff=${diff:+.2f}"
                )

                results.append(result)

        # Summary log
        total_orders = filled_count + partial_count + rejected_count
        total_latency = sum(
            r.latency_ms for r in results if hasattr(r, 'latency_ms') and r.latency_ms > 0
        )
        # Compute total latency from timestamps
        if results:
            first_t = min(r.timestamp for r in results if r.timestamp > 0)
            last_t = max(r.timestamp for r in results if r.timestamp > 0)
            total_span = (last_t - first_t) * 1000 if last_t > first_t else 0
        else:
            total_span = 0

        diff_total = total_sim_alloc - total_demo_cost
        diff_pct = (diff_total / total_sim_alloc * 100) if total_sim_alloc > 0 else 0

        logger.info(
            f"[DemoSetup] Complete: {filled_count}/{total_orders} filled, "
            f"{partial_count} partial, {rejected_count} rejected | "
            f"total_span={total_span:.0f}ms | "
            f"sim_alloc=${total_sim_alloc:.2f} demo_cost=${total_demo_cost:.2f} "
            f"diff=${diff_total:+.2f} ({diff_pct:+.2f}%)"
        )

        return results

    def to_state_dict(self) -> dict:
        return {
            "pending_orders": self._pending_orders,
            "total_trades": self._total_trades,
            "one_legged_count": self._one_legged_count,
            "rejection_count": self._rejection_count,
            "partial_fill_count": self._partial_fill_count,
        }

    def from_state_dict(self, data: dict) -> None:
        self._pending_orders = data.get("pending_orders", [])
        self._total_trades = data.get("total_trades", 0)
        self._one_legged_count = data.get("one_legged_count", 0)
        self._rejection_count = data.get("rejection_count", 0)
        self._partial_fill_count = data.get("partial_fill_count", 0)

    async def close(self) -> None:
        """Clean up all executor sessions."""
        for executor in self._executors.values():
            try:
                await executor.close()
            except Exception as e:
                logger.warning(f"[Executor] Error closing {executor.exchange_name}: {e}")
