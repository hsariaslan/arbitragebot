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
        """Subscribe to ticker + books5 for all symbols."""
        args = []
        for s in self.symbols:
            args.append({"instType": "SPOT", "channel": "ticker", "instId": s})
            args.append({"instType": "SPOT", "channel": "books5", "instId": s})
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        logger.info(f"[{self.exchange_name}] Subscribed to {len(self.symbols)} tickers + books5")

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
        Parse a Bitget ticker or books5 push message.

        Ticker: {"action": "snapshot", "arg": {"instType": "SPOT", "channel": "ticker",
                 "instId": "BTCUSDT"}, "data": [{...}]}
        Books5: {"action": "snapshot", "arg": {"instType": "SPOT", "channel": "books5",
                 "instId": "BTCUSDT"}, "data": [{"bids": [["price","qty"], ...],
                 "asks": [["price","qty"], ...], "ts": "..."}]}
        """
        arg = raw_message.get("arg")
        data = raw_message.get("data")
        if arg is None or data is None or not isinstance(data, list) or not data:
            return None

        channel = arg.get("channel", "")
        symbol = arg.get("instId", "")

        if channel == "books5":
            d = data[0]
            existing = self._state.get(symbol, PriceState())

            bids_raw = d.get("bids", [])
            asks_raw = d.get("asks", [])

            depth_bids = [(b[0], b[1]) for b in bids_raw if len(b) >= 2] or None
            depth_asks = [(a[0], a[1]) for a in asks_raw if len(a) >= 2] or None

            ts_raw = d.get("ts", 0)
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
                bids=depth_bids,
                asks=depth_asks,
            )
            return symbol, price_state

        if channel != "ticker":
            return None

        d = data[0]

        ts_raw = d.get("ts", 0)
        try:
            updated_at = int(ts_raw) / 1000.0
        except (ValueError, TypeError):
            updated_at = 0.0

        existing = self._state.get(symbol, PriceState())

        price_state = PriceState(
            bid=d.get("bidPr", ""),
            ask=d.get("askPr", ""),
            bid_qty=d.get("bidSz", ""),
            ask_qty=d.get("askSz", ""),
            last_price=d.get("lastPr", ""),
            volume=d.get("baseVolume", ""),
            updated_at=updated_at,
            bids=existing.bids,
            asks=existing.asks,
        )

        return symbol, price_state
