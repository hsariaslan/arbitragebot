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
    - All symbols subscribed in a single batch message (payload array)
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
        """Subscribe to spot.tickers for all symbols in a single batch message."""
        ts = int(time.time())
        payload = [self._to_gateio_symbol(s) for s in self.symbols]
        msg = {
            "time": ts,
            "id": 1,
            "channel": "spot.tickers",
            "event": "subscribe",
            "payload": payload,
        }
        await ws.send(json.dumps(msg))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers")

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
        Parse a Gate.io spot.tickers push message.

        Format: {"time": 1606293275, "time_ms": 1606293275723,
                 "channel": "spot.tickers", "event": "update",
                 "result": {"currency_pair": "BTC_USDT",
                            "highest_bid": "19177.79", "lowest_ask": "19179.38",
                            "last": "19178.50", "base_volume": "9110.47",
                            "quote_volume": "145082083.25", ...}}
        """
        channel = raw_message.get("channel", "")
        if channel != "spot.tickers":
            return None

        event = raw_message.get("event", "")
        if event != "update":
            return None

        result = raw_message.get("result")
        if result is None:
            return None

        gate_symbol = result.get("currency_pair", "")
        symbol = self._from_gateio_symbol(gate_symbol)

        ts_raw = raw_message.get("time_ms", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        price_state = PriceState(
            bid=result.get("highest_bid", ""),
            ask=result.get("lowest_ask", ""),
            bid_qty="",   # spot.tickers does not include quantities
            ask_qty="",   # spot.tickers does not include quantities
            last_price=result.get("last", ""),
            volume=result.get("base_volume", ""),
            updated_at=updated_at,
        )

        return symbol, price_state
