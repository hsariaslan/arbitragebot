"""
WebSocket server for the CoirnaBot live dashboard.

Pushes a full state snapshot (balances, trades, transfers, prices, system status)
to all connected browser clients every second via WebSocket on port 8765.

Also handles incoming messages from the dashboard for settings updates.
"""

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import websockets

from config import ALL_EXCHANGES, DASHBOARD_WS_PORT, SYMBOLS, USDT_WITHDRAWAL_FEES
from settings import save_settings

if TYPE_CHECKING:
    from balance import BalanceTracker
    from fetchers.base import BaseFetcher
    from monitor import ArbitrageMonitor
    from optimizer import SymbolOptimizer

logger = logging.getLogger(__name__)


class DashboardServer:
    """WebSocket server that broadcasts live state to dashboard clients."""

    def __init__(
        self,
        monitor: "ArbitrageMonitor",
        balance: "BalanceTracker",
        fetchers: list["BaseFetcher"],
        settings: dict | None = None,
        optimizer: "SymbolOptimizer | None" = None,
    ) -> None:
        self._monitor = monitor
        self._balance = balance
        self._fetchers = fetchers
        self._settings = settings or {}
        self._optimizer = optimizer
        if optimizer:
            optimizer.set_dashboard(self)
        self._running = False
        self._clients: set[Any] = set()
        self._start_time = 0.0

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Start WebSocket server and broadcast state every second."""
        self._running = True
        self._start_time = time.time()

        async with websockets.serve(
            self._handle_client,
            "0.0.0.0",
            DASHBOARD_WS_PORT,
            ping_interval=20,
            ping_timeout=60,
        ):
            logger.info(
                f"[Dashboard] WebSocket server started on ws://localhost:{DASHBOARD_WS_PORT}"
            )
            while self._running:
                if self._clients:
                    state = self._build_state()
                    payload = json.dumps(state)
                    dead: set[Any] = set()
                    for ws in self._clients:
                        try:
                            await ws.send(payload)
                        except Exception:
                            dead.add(ws)
                    self._clients -= dead
                await asyncio.sleep(1.0)

        logger.info("[Dashboard] WebSocket server stopped")

    async def _handle_client(self, ws: Any) -> None:
        """Handle a new WebSocket client connection."""
        self._clients.add(ws)
        logger.info(f"[Dashboard] Client connected ({len(self._clients)} total)")
        try:
            # Send initial state immediately
            state = self._build_state()
            await ws.send(json.dumps(state))
            # Listen for incoming messages
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    await self._handle_message(msg, ws)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.debug(f"[Dashboard] Invalid message: {e}")
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            logger.info(f"[Dashboard] Client disconnected ({len(self._clients)} total)")

    async def _handle_message(self, msg: dict, ws: Any) -> None:
        """Process an incoming message from the dashboard."""
        msg_type = msg.get("type", "")

        if msg_type == "get_settings":
            await ws.send(json.dumps({"type": "settings", "settings": self._settings}))

        elif msg_type == "save_settings":
            new_settings = msg.get("settings", {})
            self._settings = new_settings
            save_settings(new_settings)
            await ws.send(json.dumps({"type": "settings_saved", "ok": True}))
            logger.info("[Dashboard] Settings saved to file")

        elif msg_type == "apply_settings":
            new_settings = msg.get("settings", {})
            self._settings = new_settings
            save_settings(new_settings)
            self._apply_settings(new_settings)
            await ws.send(json.dumps({"type": "settings_applied", "ok": True}))
            logger.info("[Dashboard] Settings applied and simulation reset")

    def _apply_settings(self, settings: dict) -> None:
        """Apply new settings: restart discovery with updated parameters."""
        trade_amount = settings.get("trade_amount_usd", self._monitor._trade_amount)
        total_capital = settings.get("total_capital", 1800.0)

        # Reset optimizer if present — triggers new discovery
        if self._optimizer:
            opt = self._optimizer
            opt._total_capital = total_capital
            # Update Phase 2-4 parameters directly (not in reset())
            if "max_active_symbols" in settings:
                opt._max_active_symbols = max(settings["max_active_symbols"], settings.get("num_active_symbols", opt._min_active_symbols))
            if "min_rebalance_score" in settings:
                opt._min_rebalance_score = settings["min_rebalance_score"]
            if "confirmation_period" in settings:
                opt._confirmation_period = settings["confirmation_period"]
            if "promotion_threshold" in settings:
                opt._promotion_threshold = settings["promotion_threshold"]
            if "demotion_threshold" in settings:
                opt._demotion_threshold = settings["demotion_threshold"]
            if "demotion_period" in settings:
                opt._demotion_period = settings["demotion_period"]
            opt.reset(
                trade_amount=trade_amount,
                num_active_symbols=settings.get("num_active_symbols"),
                scoring_window=settings.get("scoring_window"),
                evaluation_interval=settings.get("evaluation_interval"),
                safety_multiplier=settings.get("safety_multiplier"),
                auto_rotate=settings.get("auto_rotate"),
            )

        # Update monitor thresholds
        if "min_net_profit_pct" in settings:
            self._monitor._min_net_profit_pct = settings["min_net_profit_pct"]
        if "rebalance_roi_horizon" in settings:
            self._monitor._rebalance_roi_horizon = settings["rebalance_roi_horizon"]
        self._monitor._total_capital = total_capital

        # Adaptive mode
        if "adaptive_mode" in settings:
            self._monitor._adaptive_mode = settings["adaptive_mode"]
            self._balance._adaptive_mode = settings["adaptive_mode"]

        # Update balance cooldown and trade amount
        if "rebalance_cooldown" in settings:
            self._balance._rebalance_cooldown = settings["rebalance_cooldown"]
        self._balance._trade_amount = trade_amount
        self._balance._max_rebalance = trade_amount * 4

        # Record config snapshot
        self._monitor.record_config_snapshot("settings_applied")

    def _build_optimizer_state(self) -> dict[str, Any]:
        """Collect optimizer state for dashboard broadcast."""
        if not self._optimizer:
            return {}
        opt = self._optimizer
        is_discovering = opt._discovery_mode and not opt._discovery_complete
        now = time.time()
        exchange_rankings = opt.get_exchange_rankings()
        return {
            "rankings": opt.get_rankings(),
            "exchange_rankings": exchange_rankings.get("exchanges", []),
            "pair_rankings": exchange_rankings.get("pairs", []),
            "rotations": opt.get_rotations(),
            "historical_rankings": opt.get_historical_rankings(),
            "historical_exchange_rankings": opt.get_historical_exchange_rankings(),
            "watchlist": opt.get_watchlist(),
            "auto_rotate": opt._auto_rotate,
            "active_symbols": opt.active_symbols,
            "min_active_symbols": opt._min_active_symbols,
            "max_active_symbols": opt._max_active_symbols,
            "scoring_window": opt._scoring_window,
            "evaluation_interval": opt._evaluation_interval,
            "tick_count": opt._tick_count,
            "warmup_remaining": max(
                0, opt._min_warmup_ticks - opt._tick_count
            ),
            "discovery_mode": is_discovering,
            "discovery_remaining": max(
                0,
                opt._discovery_duration - (now - opt._discovery_start),
            )
            if is_discovering
            else 0,
            "session_start": opt._session_start,
        }

    def _build_state(self) -> dict[str, Any]:
        """Collect all system state into a JSON-serializable dict."""
        now = time.time()
        active_exchanges = self._balance._exchanges
        active_symbols = self._balance._symbols
        prices = self._get_prices(active_exchanges, active_symbols)

        # Connection status
        active_set = set(active_exchanges)
        connected = sum(
            1
            for f in self._fetchers
            if f._ws_connected and f.exchange_name in active_set
        )

        # Portfolio
        portfolio_value = self._balance.get_portfolio_value(prices) if self._balance.initialized else 0.0
        initial = self._balance._initial_investment
        trading_pnl = sum(t.profit_usd for t in self._monitor._trades)
        transfer_fees = self._balance.total_transfer_fees

        # Net profit awareness: update optimizer to gate rotations when in deficit
        net_profit = trading_pnl - transfer_fees
        elapsed_hours = max((now - self._start_time) / 3600, 1 / 3600)
        session_hourly_rate = net_profit / elapsed_hours
        if self._optimizer:
            self._optimizer.update_profit_state(net_profit, session_hourly_rate)

        # Balances per exchange
        balances: dict[str, Any] = {}
        for ex in active_exchanges:
            usdt = self._balance.usdt[ex]
            crypto_data: dict[str, Any] = {}
            ex_total = usdt
            for sym in active_symbols:
                qty = self._balance.crypto[ex].get(sym, 0.0)
                p = prices.get(sym, 0.0)
                val = qty * p
                ex_total += val
                crypto_data[sym] = {"qty": round(qty, 6), "value": round(val, 2), "price": round(p, 6)}
            balances[ex] = {
                "usdt": round(usdt, 2),
                "crypto": crypto_data,
                "total": round(ex_total, 2),
            }

        # Prices per symbol per exchange
        price_grid: dict[str, dict[str, Any]] = {}
        for sym in active_symbols:
            price_grid[sym] = {}
            for fetcher in self._fetchers:
                if fetcher.exchange_name not in active_set:
                    continue
                state = fetcher.get_state()
                ps = state.get(sym)
                if ps and ps.bid and ps.ask:
                    try:
                        age = now - ps.received_at if ps.received_at > 0 else 999.0
                        price_grid[sym][fetcher.exchange_name] = {
                            "bid": round(float(ps.bid), 6),
                            "ask": round(float(ps.ask), 6),
                            "age": round(age, 1),
                        }
                    except (ValueError, TypeError):
                        pass

        # Simulation stats
        total_trades = len(self._monitor._trades)
        elapsed = now - self._monitor._start_time if self._monitor._start_time else 0
        trades_per_min = total_trades / (elapsed / 60) if elapsed > 60 else 0.0

        # Recent trades (last 100, newest first)
        recent_trades = []
        for t in reversed(self._monitor._trades[-100:]):
            recent_trades.append({
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "buy_exchange": t.buy_exchange,
                "sell_exchange": t.sell_exchange,
                "buy_price": round(t.buy_price, 6),
                "sell_price": round(t.sell_price, 6),
                "spread_pct": round(t.spread_pct, 4),
                "fee_pct": round(t.fee_pct, 4),
                "net_pct": round(t.net_pct, 4),
                "profit_usd": round(t.profit_usd, 6),
                "trade_amount": round(t.trade_amount, 2),
            })

        # Recent transfers (last 50, newest first)
        recent_transfers = []
        for tr in reversed(self._balance.transfers[-50:]):
            recent_transfers.append({
                "timestamp": tr.timestamp,
                "type": tr.transfer_type,
                "from_exchange": tr.from_exchange,
                "to_exchange": tr.to_exchange,
                "symbol": tr.symbol,
                "amount_usd": round(tr.amount_usd, 2),
                "fee_usd": round(tr.fee_usd, 4),
            })

        price_pnl = portfolio_value - initial - trading_pnl + transfer_fees if self._balance.initialized else 0.0

        # Adaptive trade size stats
        recent_trades_list = self._monitor._trades[-100:] if self._monitor._trades else []
        trade_sizes = [t.trade_amount for t in recent_trades_list if t.trade_amount > 0]
        avg_trade_size = sum(trade_sizes) / len(trade_sizes) if trade_sizes else self._monitor._trade_amount
        min_trade_size = min(trade_sizes) if trade_sizes else 0
        max_trade_size = max(trade_sizes) if trade_sizes else 0

        return {
            "timestamp": now,
            "uptime_seconds": round(now - self._start_time, 0),
            "connected_exchanges": connected,
            "total_exchanges": len(active_exchanges),
            "portfolio": {
                "total_value": round(portfolio_value, 2),
                "initial_investment": round(initial, 2),
                "net_pnl": round(portfolio_value - initial, 2) if self._balance.initialized else 0.0,
                "trading_pnl": round(trading_pnl, 4),
                "transfer_fees": round(transfer_fees, 4),
                "price_pnl": round(price_pnl, 2) if self._balance.initialized else 0.0,
            },
            "balances": balances,
            "prices": price_grid,
            "simulation": {
                "total_trades": total_trades,
                "skipped_trades": self._balance.skipped_trades,
                "total_transfers": len(self._balance.transfers),
                "trades_per_minute": round(trades_per_min, 1),
                "low_profit_skips": self._monitor._low_profit_skips,
                "avg_trade_size": round(avg_trade_size, 2),
                "min_trade_size": round(min_trade_size, 2),
                "max_trade_size": round(max_trade_size, 2),
                "configured_trade_amount": self._monitor._trade_amount,
            },
            "recent_trades": recent_trades,
            "recent_transfers": recent_transfers,
            "all_trades": [
                {
                    "timestamp": t.timestamp,
                    "symbol": t.symbol,
                    "buy_exchange": t.buy_exchange,
                    "sell_exchange": t.sell_exchange,
                    "buy_price": round(t.buy_price, 6),
                    "sell_price": round(t.sell_price, 6),
                    "spread_pct": round(t.spread_pct, 4),
                    "fee_pct": round(t.fee_pct, 4),
                    "net_pct": round(t.net_pct, 4),
                    "profit_usd": round(t.profit_usd, 6),
                    "trade_amount": round(t.trade_amount, 2),
                }
                for t in self._monitor._trades
            ],
            "all_transfers": [
                {
                    "timestamp": tr.timestamp,
                    "type": tr.transfer_type,
                    "from_exchange": tr.from_exchange,
                    "to_exchange": tr.to_exchange,
                    "symbol": tr.symbol,
                    "amount_usd": round(tr.amount_usd, 2),
                    "fee_usd": round(tr.fee_usd, 4),
                }
                for tr in self._balance.transfers
            ],
            "settings": self._settings,
            "all_exchanges": ALL_EXCHANGES,
            "all_symbols": SYMBOLS,
            "optimizer": self._build_optimizer_state(),
            "adaptive_config": self._build_adaptive_config(),
            "all_config_history": [
                {
                    "timestamp": c.timestamp,
                    "reason": c.reason,
                    "trade_amount": c.trade_amount,
                    "adaptive_mode": c.adaptive_mode,
                    "min_net_profit_pct": c.min_net_profit_pct,
                    "rebalance_cooldown": c.rebalance_cooldown,
                    "rebalance_roi_horizon": c.rebalance_roi_horizon,
                    "total_capital": c.total_capital,
                    "num_active_symbols": c.num_active_symbols,
                    "max_active_symbols": c.max_active_symbols,
                    "avg_trade_size": round(c.avg_trade_size, 2),
                    "estimated_profit_per_trade": round(c.estimated_profit_per_trade, 6),
                }
                for c in self._monitor._config_history
            ],
            "profit_stats": self._monitor.get_net_profit_stats(),
        }

    def _build_adaptive_config(self) -> dict[str, Any]:
        """Current adaptive configuration decisions."""
        monitor = self._monitor
        balance = self._balance

        # Per-exchange transfer worthiness
        exchange_transfer_status: dict[str, Any] = {}
        for ex in balance._exchanges:
            fee = USDT_WITHDRAWAL_FEES.get(ex, 1.0)
            est_profit = balance._estimated_profit_per_trade
            trades_to_recoup = fee / est_profit if est_profit > 0 else 999
            exchange_transfer_status[ex] = {
                "withdrawal_fee": fee,
                "trades_to_recoup": round(trades_to_recoup, 1),
                "transfer_allowed": trades_to_recoup <= 50,
            }

        recent = monitor._trades[-100:] if monitor._trades else []
        sizes = [t.trade_amount for t in recent if t.trade_amount > 0]

        return {
            "adaptive_mode": monitor._adaptive_mode,
            "configured_trade_amount": monitor._trade_amount,
            "avg_trade_size": round(sum(sizes) / len(sizes), 2) if sizes else 0,
            "min_trade_size": round(min(sizes), 2) if sizes else 0,
            "max_trade_size": round(max(sizes), 2) if sizes else 0,
            "min_net_profit_pct": monitor._min_net_profit_pct,
            "estimated_profit_per_trade": round(balance._estimated_profit_per_trade, 6),
            "total_capital": monitor._total_capital,
            "exchange_transfer_status": exchange_transfer_status,
        }

    def _get_prices(
        self, exchanges: list[str], symbols: list[str]
    ) -> dict[str, float]:
        """Get current mid prices for active symbols."""
        prices: dict[str, float] = {}
        active = set(exchanges)
        for sym in symbols:
            for fetcher in self._fetchers:
                if fetcher.exchange_name not in active:
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
