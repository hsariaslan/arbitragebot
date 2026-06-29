"""
Binance Spot WebSocket fetcher.

Connects to Binance Spot WebSocket API and streams real-time data
for all configured symbols using the combined streams endpoint:
    - @ticker for bid/ask prices, quantities, last price, volume
    - @depth5@100ms for 5-level order book depth

Binance Spot @ticker stream fields:
    b = best bid price,  B = best bid quantity
    a = best ask price,  A = best ask quantity
    c = last/close price
    v = 24h base asset volume
    E = event time (ms)

Binance @depth5@100ms fields:
    bids = [[price, qty], ...] up to 5 levels, descending
    asks = [[price, qty], ...] up to 5 levels, ascending
    lastUpdateId = sequence number

Connection notes:
    - Max 1024 streams per connection (we use ~120 for 60 symbols)
    - Auto-disconnects after 24 hours (handled by reconnection logic)
    - Server pings every ~20s (handled by websockets library)
"""

import logging
from typing import Any

from config import BINANCE_EXCHANGE_NAME, BINANCE_WS_BASE_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class BinanceFetcher(BaseFetcher):
    """Binance Spot WebSocket fetcher using @ticker + @depth5 streams."""

    @property
    def exchange_name(self) -> str:
        return BINANCE_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        """
        Build combined streams URL.

        Format: wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/btcusdt@depth5@100ms/...
        All streams are active immediately on connection — no subscription handshake needed.
        Includes both @ticker (bid/ask/last/volume) and @depth5@100ms (5-level order book).
        """
        parts = []
        for s in self.symbols:
            sym = s.lower()
            parts.append(f"{sym}@ticker")
            parts.append(f"{sym}@depth5@100ms")
        streams = "/".join(parts)
        return f"{BINANCE_WS_BASE_URL}?streams={streams}"

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a Binance combined stream message (@ticker or @depth5).

        Ticker: {"stream": "btcusdt@ticker", "data": {"e": "24hrTicker", ...}}
        Depth:  {"stream": "btcusdt@depth5@100ms", "data": {"lastUpdateId": ..., "bids": [...], "asks": [...]}}
        """
        stream = raw_message.get("stream", "")
        data = raw_message.get("data")
        if data is None:
            return None

        # Depth5 stream: update order book levels
        if "@depth5" in stream:
            # Extract symbol from stream name: "btcusdt@depth5@100ms" -> "BTCUSDT"
            symbol = stream.split("@")[0].upper()
            existing = self._state.get(symbol, PriceState())

            bids_raw = data.get("bids", [])
            asks_raw = data.get("asks", [])

            depth_bids = [(b[0], b[1]) for b in bids_raw if len(b) >= 2] or None
            depth_asks = [(a[0], a[1]) for a in asks_raw if len(a) >= 2] or None

            price_state = PriceState(
                bid=bids_raw[0][0] if bids_raw else existing.bid,
                ask=asks_raw[0][0] if asks_raw else existing.ask,
                bid_qty=bids_raw[0][1] if bids_raw else existing.bid_qty,
                ask_qty=asks_raw[0][1] if asks_raw else existing.ask_qty,
                last_price=existing.last_price,
                volume=existing.volume,
                updated_at=existing.updated_at,
                book_received_at=-1.0,
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        # Ticker stream
        if data.get("e") != "24hrTicker":
            return None

        symbol = data.get("s", "")
        existing = self._state.get(symbol, PriceState())

        price_state = PriceState(
            bid=data.get("b", ""),
            ask=data.get("a", ""),
            bid_qty=data.get("B", ""),
            ask_qty=data.get("A", ""),
            last_price=data.get("c", ""),
            volume=data.get("v", ""),
            updated_at=data.get("E", 0) / 1000.0,
            bids=existing.bids,
            asks=existing.asks,
        )

        return symbol, price_state
