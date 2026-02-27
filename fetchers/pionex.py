"""
Pionex Spot WebSocket fetcher.

Connects to Pionex WebSocket API and streams real-time order book data
for all configured symbols using the DEPTH topic for bid/ask prices
and the TRADE topic for last traded price.

Pionex DEPTH fields:
    bids = [[price, size], ...] sorted by price descending
    asks = [[price, size], ...] sorted by price ascending
    We use bids[0] / asks[0] for best bid/ask.

Pionex TRADE fields:
    price = last trade price
    size  = trade size
    side  = BUY or SELL

Connection notes:
    - Subscription is done post-connect via JSON messages
    - Symbol format: BTC_USDT (underscore-separated, uppercase)
    - Server sends {"op": "PING"} every 15s, client must reply {"op": "PONG"}
    - Max 10 WebSocket connections per IP
    - Public endpoint: wss://ws.pionex.com/wsPub
"""

import asyncio
import json
import logging
import time
from typing import Any

from config import PIONEX_EXCHANGE_NAME, PIONEX_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class PionexFetcher(BaseFetcher):
    """Pionex Spot WebSocket fetcher using DEPTH + TRADE topics."""

    def __init__(self, symbols: list[str] | None = None) -> None:
        super().__init__(symbols)
        # Track last trade prices per symbol (TRADE topic updates these)
        self._last_prices: dict[str, str] = {}

    @property
    def exchange_name(self) -> str:
        return PIONEX_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return PIONEX_WS_URL

    @staticmethod
    def _to_pionex_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> BTC_USDT."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}_USDT"
        return symbol

    @staticmethod
    def _from_pionex_symbol(pionex_symbol: str) -> str:
        """Convert BTC_USDT -> BTCUSDT."""
        return pionex_symbol.replace("_", "")

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to DEPTH and TRADE for all symbols."""
        for s in self.symbols:
            pionex_sym = self._to_pionex_symbol(s)
            # Subscribe to DEPTH for bid/ask
            await ws.send(json.dumps({
                "op": "SUBSCRIBE",
                "topic": "DEPTH",
                "symbol": pionex_sym,
            }))
            # Subscribe to TRADE for last_price
            await ws.send(json.dumps({
                "op": "SUBSCRIBE",
                "topic": "TRADE",
                "symbol": pionex_sym,
            }))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} symbols (DEPTH+TRADE)")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Pionex uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Reply to server PINGs. Also send periodic PONGs as fallback."""
        while self._running and self._ws_connected:
            try:
                await ws.send(json.dumps({
                    "op": "PONG",
                    "timestamp": int(time.time() * 1000),
                }))
            except Exception:
                break
            await asyncio.sleep(14)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse Pionex DEPTH or TRADE push messages.

        DEPTH format:
            {"topic": "DEPTH", "symbol": "BTC_USDT", "timestamp": ...,
             "data": {"bids": [["price", "size"], ...],
                      "asks": [["price", "size"], ...]}}

        TRADE format:
            {"topic": "TRADE", "symbol": "BTC_USDT", "timestamp": ...,
             "data": [{"price": "...", "size": "...", "side": "BUY", "timestamp": ...}]}
        """
        # Handle server PING
        op = raw_message.get("op", "")
        if op == "PING":
            # Will be handled by _keep_alive, but also track as activity
            return None

        # Ignore subscription confirmations and errors
        msg_type = raw_message.get("type", "")
        if msg_type in ("SUBSCRIBED", "UNSUBSCRIBED", "ERROR"):
            return None

        topic = raw_message.get("topic", "")
        pionex_symbol = raw_message.get("symbol", "")
        if not pionex_symbol:
            return None

        symbol = self._from_pionex_symbol(pionex_symbol)

        ts_raw = raw_message.get("timestamp", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        if topic == "TRADE":
            # Extract last trade price; store for DEPTH messages
            data_list = raw_message.get("data")
            if data_list and isinstance(data_list, list) and len(data_list) > 0:
                # data is sorted by timestamp descending; first entry is most recent
                self._last_prices[symbol] = str(data_list[0].get("price", ""))
            # Don't emit a PriceState for TRADE — wait for DEPTH with bid/ask
            return None

        if topic == "DEPTH":
            data = raw_message.get("data")
            if data is None:
                return None

            bids = data.get("bids", [])
            asks = data.get("asks", [])

            bid = ""
            bid_qty = ""
            ask = ""
            ask_qty = ""

            if bids and len(bids) > 0:
                bid = str(bids[0][0]) if len(bids[0]) > 0 else ""
                bid_qty = str(bids[0][1]) if len(bids[0]) > 1 else ""
            if asks and len(asks) > 0:
                ask = str(asks[0][0]) if len(asks[0]) > 0 else ""
                ask_qty = str(asks[0][1]) if len(asks[0]) > 1 else ""

            price_state = PriceState(
                bid=bid,
                ask=ask,
                bid_qty=bid_qty,
                ask_qty=ask_qty,
                last_price=self._last_prices.get(symbol, ""),
                volume="",  # DEPTH doesn't include 24h volume
                updated_at=updated_at,
            )
            return symbol, price_state

        return None
