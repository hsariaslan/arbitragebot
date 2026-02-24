"""
MEXC Spot WebSocket fetcher.

Connects to MEXC WebSocket API and streams real-time book ticker data
for all configured symbols.

MEXC bookTicker fields:
    bidPrice / B    = best bid price
    bidQuantity / b = best bid quantity
    askPrice / A    = best ask price
    askQuantity / a = best ask quantity

    NOTE: bookTicker does NOT provide last_price or volume.
    These fields remain empty. For arbitrage, bid/ask is sufficient.

Connection notes:
    - Subscription is done post-connect via JSON message
    - Symbol format: BTCUSDT uppercase (matches our config)
    - Application-level ping: send {"method": "PING"}, every 10-20s
    - Max 30 subscriptions per connection (we use 20)
"""

import asyncio
import json
import logging
from typing import Any

from config import MEXC_EXCHANGE_NAME, MEXC_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class MEXCFetcher(BaseFetcher):
    """MEXC Spot WebSocket fetcher using the bookTicker channel."""

    @property
    def exchange_name(self) -> str:
        return MEXC_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return MEXC_WS_URL

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to bookTicker for all symbols (batched, max 30 per message)."""
        params = [f"spot@public.bookTicker.v3.api@{s}" for s in self.symbols]
        batch_size = 30
        for i in range(0, len(params), batch_size):
            batch = params[i : i + batch_size]
            await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": batch}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} bookTickers")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; MEXC uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send {"method": "PING"} every 15 seconds (MEXC requires 10-20s)."""
        while self._running and self._ws_connected:
            try:
                await ws.send(json.dumps({"method": "PING"}))
            except Exception:
                break
            await asyncio.sleep(15)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a MEXC bookTicker push message.

        Handles both verbose and compact MEXC field names:
        Verbose: {"channel": "...", "symbol": "BTCUSDT",
                  "data": {"bidPrice": ..., "askPrice": ...}}
        Compact: {"c": "...", "s": "BTCUSDT",
                  "d": {"B": ..., "A": ...}}
        """
        channel = raw_message.get("channel") or raw_message.get("c", "")
        if "bookTicker" not in channel:
            return None

        data = raw_message.get("data") or raw_message.get("d")
        if data is None:
            return None

        symbol = raw_message.get("symbol") or raw_message.get("s", "")

        ts_raw = raw_message.get("t", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        bid = data.get("bidPrice") or data.get("B", "")
        ask = data.get("askPrice") or data.get("A", "")
        bid_qty = data.get("bidQuantity") or data.get("b", "")
        ask_qty = data.get("askQuantity") or data.get("a", "")

        price_state = PriceState(
            bid=bid,
            ask=ask,
            bid_qty=bid_qty,
            ask_qty=ask_qty,
            last_price="",
            volume="",
            updated_at=updated_at,
        )

        return symbol, price_state
