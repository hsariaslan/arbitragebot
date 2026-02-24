"""
Binance Spot WebSocket fetcher.

Connects to Binance Spot WebSocket API and streams real-time ticker data
for all configured symbols using the combined streams endpoint.

Binance Spot @ticker stream fields:
    b = best bid price,  B = best bid quantity
    a = best ask price,  A = best ask quantity
    c = last/close price
    v = 24h base asset volume
    E = event time (ms)

Connection notes:
    - Max 1024 streams per connection (we use 20)
    - Auto-disconnects after 24 hours (handled by reconnection logic)
    - Server pings every ~20s (handled by websockets library)
"""

import logging
from typing import Any

from config import BINANCE_EXCHANGE_NAME, BINANCE_WS_BASE_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class BinanceFetcher(BaseFetcher):
    """Binance Spot WebSocket fetcher using the @ticker stream."""

    @property
    def exchange_name(self) -> str:
        return BINANCE_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        """
        Build combined streams URL.

        Format: wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker/...
        All streams are active immediately on connection — no subscription handshake needed.
        """
        streams = "/".join(f"{s.lower()}@ticker" for s in self.symbols)
        return f"{BINANCE_WS_BASE_URL}?streams={streams}"

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a Binance combined stream ticker message.

        Combined stream wrapper: {"stream": "btcusdt@ticker", "data": {...}}
        Returns None for non-ticker messages (subscription confirmations, etc.).
        """
        data = raw_message.get("data")
        if data is None:
            return None

        if data.get("e") != "24hrTicker":
            return None

        symbol = data.get("s", "")

        price_state = PriceState(
            bid=data.get("b", ""),
            ask=data.get("a", ""),
            bid_qty=data.get("B", ""),
            ask_qty=data.get("A", ""),
            last_price=data.get("c", ""),
            volume=data.get("v", ""),
            updated_at=data.get("E", 0) / 1000.0,
        )

        return symbol, price_state
