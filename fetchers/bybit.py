"""
Bybit Spot WebSocket fetcher.

Connects to Bybit v5 public WebSocket API for spot and streams real-time
data using two channels per symbol:
    - orderbook.50 for 50-level bid/ask depth
    - tickers for lastPrice and 24h volume

Bybit v5 Spot valid orderbook depths: 1, 50, 200, 1000.
Note: orderbook.5 does NOT exist — causes silent subscription failure
and zero data (discovered Session #2, 2026-03-03).

Bybit orderbook.50 fields:
    b = [[price, qty], ...] bids (up to 50 levels, descending)
    a = [[price, qty], ...] asks (up to 50 levels, ascending)
    s = symbol

Bybit tickers fields:
    lastPrice = last traded price
    volume24h = 24h volume (base asset)

Connection notes:
    - Subscription is done post-connect via JSON message
    - Symbol format: BTCUSDT (matches our config)
    - Application-level ping: send {"op": "ping"}, receive JSON pong
    - Must ping every 20s
"""

import asyncio
import json
import logging
from typing import Any

from config import BYBIT_EXCHANGE_NAME, BYBIT_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class BybitFetcher(BaseFetcher):
    """Bybit Spot WebSocket fetcher using orderbook.50 + tickers channels."""

    def __init__(self, symbols: list[str] | None = None) -> None:
        super().__init__(symbols)
        # Bybit v5 sends an initial order-book snapshot and then delta
        # messages. Keep a local book per symbol so deltas do not replace the
        # whole visible depth with only the changed levels.
        self._book_bids: dict[str, dict[float, float]] = {}
        self._book_asks: dict[str, dict[float, float]] = {}
        self._book_ready: set[str] = set()

    @property
    def exchange_name(self) -> str:
        return BYBIT_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return BYBIT_WS_URL

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to orderbook.50 and tickers for all symbols (batched, max 10 args per message)."""
        args = []
        for s in self.symbols:
            args.append(f"orderbook.50.{s}")
            args.append(f"tickers.{s}")
        # Bybit limits 10 args per subscribe message
        batch_size = 10
        for i in range(0, len(args), batch_size):
            batch = args[i:i + batch_size]
            await ws.send(json.dumps({"op": "subscribe", "args": batch}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} symbols (orderbook + tickers)")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Bybit uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send {"op": "ping"} every 18 seconds (Bybit expects within 20s)."""
        while self._running and self._ws_connected:
            try:
                await ws.send(json.dumps({"op": "ping"}))
            except Exception:
                break
            await asyncio.sleep(18)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse Bybit orderbook.50 or tickers messages.

        orderbook.50: {"topic": "orderbook.50.BTCUSDT",
                       "data": {"s": "BTCUSDT", "b": [["price","qty"], ...], "a": [["price","qty"], ...]}}
        tickers:     {"topic": "tickers.BTCUSDT",
                      "data": {"symbol": "BTCUSDT", "lastPrice": "...", "volume24h": "..."}}

        Both are merged into the existing PriceState for each symbol.
        """
        topic = raw_message.get("topic", "")
        data = raw_message.get("data")
        if data is None:
            return None

        ts_raw = raw_message.get("ts", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        if topic.startswith("orderbook."):
            symbol = data.get("s", "")
            bids_raw = data.get("b", [])
            asks_raw = data.get("a", [])
            update_type = str(raw_message.get("type", "snapshot") or "snapshot").lower()

            existing = self._state.get(symbol, PriceState())

            if update_type == "snapshot":
                self._book_bids[symbol] = {}
                self._book_asks[symbol] = {}
                self._book_ready.add(symbol)
                self._apply_book_levels(self._book_bids[symbol], bids_raw)
                self._apply_book_levels(self._book_asks[symbol], asks_raw)
            elif update_type == "delta":
                if symbol not in self._book_ready:
                    return None
                self._apply_book_levels(self._book_bids.setdefault(symbol, {}), bids_raw)
                self._apply_book_levels(self._book_asks.setdefault(symbol, {}), asks_raw)
            else:
                # Unknown orderbook push type: treat non-empty payload as a
                # partial refresh without clearing known levels.
                self._apply_book_levels(self._book_bids.setdefault(symbol, {}), bids_raw)
                self._apply_book_levels(self._book_asks.setdefault(symbol, {}), asks_raw)

            depth_bids, depth_asks = self._top_book_levels(symbol)
            best_bid = depth_bids[0] if depth_bids else None
            best_ask = depth_asks[0] if depth_asks else None

            price_state = PriceState(
                bid=best_bid[0] if best_bid else existing.bid,
                ask=best_ask[0] if best_ask else existing.ask,
                bid_qty=best_bid[1] if best_bid else existing.bid_qty,
                ask_qty=best_ask[1] if best_ask else existing.ask_qty,
                last_price=existing.last_price,
                volume=existing.volume,
                updated_at=updated_at,
                book_received_at=-1.0,
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        elif topic.startswith("tickers."):
            symbol = data.get("symbol", "")
            existing = self._state.get(symbol, PriceState())
            price_state = PriceState(
                bid=existing.bid,
                ask=existing.ask,
                bid_qty=existing.bid_qty,
                ask_qty=existing.ask_qty,
                last_price=data.get("lastPrice") or existing.last_price,
                volume=data.get("volume24h") or existing.volume,
                updated_at=updated_at,
                bids=existing.bids,
                asks=existing.asks,
            )
            return symbol, price_state

        return None

    @staticmethod
    def _apply_book_levels(
        book: dict[float, float],
        levels: list,
    ) -> None:
        """Apply Bybit snapshot/delta levels to a local price→qty book."""
        for level in levels or []:
            if len(level) < 2:
                continue
            try:
                price = float(level[0])
                qty = float(level[1])
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            if qty <= 0:
                book.pop(price, None)
            else:
                book[price] = qty

    def _top_book_levels(
        self,
        symbol: str,
        depth: int = 50,
    ) -> tuple[list[tuple[str, str]] | None, list[tuple[str, str]] | None]:
        bids = sorted(
            self._book_bids.get(symbol, {}).items(),
            key=lambda kv: -kv[0],
        )[:depth]
        asks = sorted(
            self._book_asks.get(symbol, {}).items(),
            key=lambda kv: kv[0],
        )[:depth]
        depth_bids = [(str(price), str(qty)) for price, qty in bids] or None
        depth_asks = [(str(price), str(qty)) for price, qty in asks] or None
        return depth_bids, depth_asks
