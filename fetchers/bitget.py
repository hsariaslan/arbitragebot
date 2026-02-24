"""
Bitget Spot WebSocket fetcher (v2 API).

Connects to Bitget v2 public WebSocket API and streams real-time
ticker data for all configured symbols.

Bitget ticker fields:
    bidPr   = best bid price
    askPr   = best ask price
    bidSz   = best bid quantity
    askSz   = best ask quantity
    lastPr  = last traded price
    baseVolume = 24h volume (base asset)

Connection notes:
    - Subscription is done post-connect via JSON message
    - Symbol format: BTCUSDT (matches our config)
    - Application-level ping: send string "ping", receive "pong"
    - Must ping every 30s (timeout after 120s without ping)
"""

import asyncio
import json
import logging
from typing import Any

from config import BITGET_EXCHANGE_NAME, BITGET_WS_URL
from fetchers.base import BaseFetcher, PriceState

logger = logging.getLogger(__name__)


class BitgetFetcher(BaseFetcher):
    """Bitget Spot WebSocket fetcher using the v2 ticker channel."""

    @property
    def exchange_name(self) -> str:
        return BITGET_EXCHANGE_NAME

    def _build_ws_url(self) -> str:
        return BITGET_WS_URL

    async def _on_connect(self, ws: Any) -> None:
        """Subscribe to ticker for all symbols."""
        args = [
            {"instType": "SPOT", "channel": "ticker", "instId": s}
            for s in self.symbols
        ]
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers")

    def _ws_connect_kwargs(self) -> dict[str, Any]:
        """Disable library-level ping; Bitget uses application-level string ping."""
        return {
            "ping_interval": None,
            "ping_timeout": None,
            "close_timeout": 10,
            "max_size": 2**20,
        }

    async def _keep_alive(self, ws: Any) -> None:
        """Send string 'ping' every 25 seconds (Bitget timeout is 120s)."""
        while self._running and self._ws_connected:
            try:
                await ws.send("ping")
            except Exception:
                break
            await asyncio.sleep(25)

    def _parse_message(self, raw_message: dict[str, Any]) -> tuple[str, PriceState] | None:
        """
        Parse a Bitget ticker push message.

        Format: {"action": "snapshot", "arg": {"instType": "SPOT", "channel": "ticker",
                 "instId": "BTCUSDT"}, "data": [{...}]}
        """
        arg = raw_message.get("arg")
        data = raw_message.get("data")
        if arg is None or data is None or not isinstance(data, list) or not data:
            return None

        channel = arg.get("channel", "")
        if channel != "ticker":
            return None

        symbol = arg.get("instId", "")
        d = data[0]

        ts_raw = d.get("ts", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        price_state = PriceState(
            bid=d.get("bidPr", ""),
            ask=d.get("askPr", ""),
            bid_qty=d.get("bidSz", ""),
            ask_qty=d.get("askSz", ""),
            last_price=d.get("lastPr", ""),
            volume=d.get("baseVolume", ""),
            updated_at=updated_at,
        )

        return symbol, price_state
