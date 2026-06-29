"""
Gate.io Spot WebSocket fetcher (v4 API).

Connects to Gate.io WebSocket API and streams real-time ticker data
for all configured symbols using the spot.tickers channel.

Gate.io spot.tickers fields:
    currency_pair = symbol (e.g., "BTC_USDT")
    highest_bid   = best bid price
    lowest_ask    = best ask price
    last          = last traded price
    base_volume   = 24h volume in base currency
    quote_volume  = 24h volume in quote currency
    change_percentage = 24h price change %
    high_24h / low_24h = 24h high/low

    NOTE: spot.tickers does NOT provide bid/ask quantities.
    Depth filtering relies on other exchanges for Gate.io pairs.

Connection notes:
    - Subscription is done post-connect via JSON messages
    - Symbol format: BTC_USDT (underscore-separated)
    - Application-level ping: send {"channel": "spot.ping"}, receive spot.pong
    - Each symbol needs a separate subscription message
    - spot.tickers updates at ~1s intervals
"""

import asyncio
import json
import logging
import time
from typing import Any

from config import GATEIO_EXCHANGE_NAME, GATEIO_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class GateIOFetcher(BaseFetcher):
    """Gate.io Spot WebSocket fetcher using the spot.tickers channel."""

    @property
    def exchange_name(self) -> str:
        return GATEIO_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return GATEIO_WS_URL

    @staticmethod
    def _to_gateio_symbol(symbol: str) -> str:
        """Convert BTCUSDT -> BTC_USDT."""
        if symbol.endswith("USDT"):
            return f"{symbol[:-4]}_USDT"
        return symbol

    @staticmethod
    def _from_gateio_symbol(gate_symbol: str) -> str:
        """Convert BTC_USDT -> BTCUSDT."""
        return gate_symbol.replace("_", "")

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to spot.tickers + spot.order_book for all symbols."""
        ts = int(time.time())
        msg_id = 0
        for s in self.symbols:
            gate_sym = self._to_gateio_symbol(s)
            msg_id += 1
            await ws.send(json.dumps({
                "time": ts,
                "id": msg_id,
                "channel": "spot.tickers",
                "event": "subscribe",
                "payload": [gate_sym],
            }))
            msg_id += 1
            await ws.send(json.dumps({
                "time": ts,
                "id": msg_id,
                "channel": "spot.order_book",
                "event": "subscribe",
                "payload": [gate_sym, "5", "100ms"],
            }))
        logger.info(
            f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers + order_book"
        )

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Gate.io uses application-level JSON ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send spot.ping every 15 seconds."""
        while self._running and self._ws_connected:
            try:
                msg = {"time": int(time.time()), "channel": "spot.ping"}
                await ws.send(json.dumps(msg))
            except Exception:
                break
            await asyncio.sleep(15)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a Gate.io spot.tickers or spot.order_book push message.

        Tickers: {"channel": "spot.tickers", "event": "update",
                  "result": {"currency_pair": "BTC_USDT", "highest_bid": "...", ...}}
        Order book: {"channel": "spot.order_book", "event": "update",
                     "result": {"s": "BTC_USDT", "bids": [["price","qty"], ...],
                                "asks": [["price","qty"], ...], "t": 1606293275723}}
        """
        channel = raw_message.get("channel", "")
        event = raw_message.get("event", "")
        if event != "update":
            return None

        result = raw_message.get("result")
        if result is None:
            return None

        if channel == "spot.order_book":
            gate_symbol = result.get("s", "")
            symbol = self._from_gateio_symbol(gate_symbol)
            existing = self._state.get(symbol, PriceState())

            bids_raw = result.get("bids", [])
            asks_raw = result.get("asks", [])

            depth_bids = [(b[0], b[1]) for b in bids_raw if len(b) >= 2] or None
            depth_asks = [(a[0], a[1]) for a in asks_raw if len(a) >= 2] or None

            ts_raw = result.get("t", 0)
            try:
                updated_at = int(ts_raw) / 1000.0
            except (ValueError, TypeError):
                updated_at = existing.updated_at

            price_state = PriceState(
                bid=bids_raw[0][0] if bids_raw else existing.bid,
                ask=asks_raw[0][0] if asks_raw else existing.ask,
                bid_qty=bids_raw[0][1] if bids_raw else existing.bid_qty,
                ask_qty=asks_raw[0][1] if asks_raw else existing.ask_qty,
                last_price=existing.last_price,
                volume=existing.volume,
                updated_at=updated_at,
                book_received_at=-1.0,
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        if channel != "spot.tickers":
            return None

        gate_symbol = result.get("currency_pair", "")
        symbol = self._from_gateio_symbol(gate_symbol)

        ts_raw = raw_message.get("time_ms", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        existing = self._state.get(symbol, PriceState())

        price_state = PriceState(
            bid=result.get("highest_bid", ""),
            ask=result.get("lowest_ask", ""),
            bid_qty=existing.bid_qty,
            ask_qty=existing.ask_qty,
            last_price=result.get("last", ""),
            volume=result.get("base_volume", ""),
            updated_at=updated_at,
            bids=existing.bids,
            asks=existing.asks,
        )

        return symbol, price_state
